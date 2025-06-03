import os
import pathlib
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from pydantic import BaseModel, Field
from typing import List, Tuple
from enum import Enum
import asyncio
import subprocess
from search import batch_search, get_content
from ollama import AsyncClient
from datetime import datetime
import traceback
from playwright.async_api import async_playwright, Browser

from abc import ABC, abstractmethod
class Messenger(ABC):
    def __init__(self, thread_ts: str):
        self._thread_ts = thread_ts
        self._pending_input = None  # 追加

    @abstractmethod
    async def send(self, message: str) -> None:
        pass

    def get_thread_ts(self) -> str:
        return self._thread_ts


SYSTEM_PROMPT = """
You are Taro, a highly skilled software engineer with extensive knowledge in many programming languages, frameworks, design patterns, and best practices.

====

TOOL USE

You have access to a set of tools that are executed upon the user's approval. You can use one tool per message, and will receive the result of that tool use in the user's response. You use tools step-by-step to accomplish a given task, with each tool use informed by the result of the previous tool use.

# Tool Use Guidelines

1. Choose the most appropriate tool based on the task and the tool descriptions provided. Assess if you need additional information to proceed, and which of the available tools would be most effective for gathering this information. For example using the list_files tool is more effective than running a command like `ls` in the terminal. It's critical that you think about each available tool and use the one that best fits the current step in the task.
2. If multiple actions are needed, use one tool at a time per message to accomplish the task iteratively, with each tool use being informed by the result of the previous tool use. Do not assume the outcome of any tool use. Each step must be informed by the previous step's result.
3. After each tool use, the user will respond with the result of that tool use. This result will provide you with the necessary information to continue your task or make further decisions. This response may include:
  - Information about whether the tool succeeded or failed, along with any reasons for failure.
  - Linter errors that may have arisen due to the changes you made, which you'll need to address.
  - New terminal output in reaction to the changes, which you may need to consider or act upon.
  - Any other relevant feedback or information related to the tool use.
4. 同じ目的で同じツールは使わないこと
5. ユーザーから与えられるタスクは、内容が曖昧なことがあります。ユーザーの意図が汲み取れない時は積極的にask_to_userのツールを使ってユーザーに意図を確認しましょう
6. 実行計画が決まったら、report_to_userのツールを使ってユーザーに伝えること
7. 回答をする際に根拠となる情報のURLも合わせて回答すること
8. infer_knowledge_by_urlを使うときはwhat_to_searchには検索したい背景や目的を明確に詳細に指定してください

"""

client = AsyncClient(
    host='http://localhost:12345',
    timeout=3*60,
)

_playwright = None
_browser: Browser | None = None

async def initialize_browser():
    global _playwright, _browser
    if _browser is None:
        print("Initializing Playwright browser...")
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
        print("Playwright browser initialized.")

async def shutdown_browser():
    global _playwright, _browser
    # ... (ブラウザと Playwright を閉じる処理) ...
    if _browser:
        print("Shutting down Playwright browser...")
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    print("Playwright browser shut down.")


class UserRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"

class Message(BaseModel):
    role: UserRole = Field(..., description="The user who sent the message")
    content: str = Field(..., description="The text of the message")

    @staticmethod
    def init():
        return [
            Message(role=UserRole.system, content=SYSTEM_PROMPT + "\n今日は" + datetime.now().strftime('%Y年%m月%d日') + "です。"),
        ]

    def __str__(self):
        return f"{self.role}: {self.content}"

# Agent state management
class AgentState:
    def __init__(self):
        self.running = True
        self.busy_with_user = True
        self.last_user_interaction = None
        self.messenger = None

    def set_messenger(self, messenger: Messenger):
        self.messenger = messenger

class AgentLocalState(BaseModel):
    messages: List[Message] = []
    current_task: str = ""


agent_state = AgentState()

async def agent_main_loop():
    await initialize_browser()
    if not _browser:
        print("Failed to initialize browser. Agent loop cannot start.")
        return
    local_state = AgentLocalState(messages=Message.init(), current_task="")
    try:
        while agent_state.running:
            tool_caller = ToolCaller(client, agent_state.messenger, _browser)
            if agent_state.busy_with_user:
                await asyncio.sleep(3)
                continue

            if agent_state.last_user_interaction:
                if not local_state.current_task:
                    # res = await client.chat(
                    #     model=tool_caller.model,
                    #     messages=[Message(role=UserRole.system, content="ユーザーの入力から、ユーザーが何をしたいのかを考えてください。そして、タスクとして、箇条書きでmarkdown形式で出力してください。"),
                    #                Message(role=UserRole.user, content=f"ユーザーの入力: {agent_state.last_user_interaction}")],
                    # )
                    # print('res', res.message)
                    # task = res.message.content.split('</think>')[-1].strip()
                    task = agent_state.last_user_interaction.strip()
                    # local_state.messages.append(Message(role=UserRole.user, content='<task>' + task + '</task>\n以上の内容をタスクとして実行してください'))
                    local_state.messages.append(Message(role=UserRole.user, content=task))
                    local_state.current_task = task
                else:
                    local_state.messages.append(Message(role=UserRole.user, content=agent_state.last_user_interaction))
                agent_state.last_user_interaction = None

            local_state, wait_for_user, done = await tool_caller.action(local_state)
            await asyncio.sleep(1)
            print('-----最新のメッセージ-----')
            for message in local_state.messages[-2:]:
                print(message)

            if wait_for_user:
                agent_state.busy_with_user = True

            if done:
                print('終了しました')
                local_state = AgentLocalState(messages=Message.init(), current_task="")
                agent_state.busy_with_user = True
    finally:
        await shutdown_browser()




async def select_tool(model, messages, tools):
    all_message = ''
    try:
        async for part in await client.chat(model=model, messages=messages, tools=tools, stream=True, format='json'):
            if part['message'].get('tool_calls'):
                tool_call = part['message']['tool_calls'][0]
                function_name = tool_call['function']['name']
                arguments = tool_call['function']['arguments']
                return function_name, arguments, None
            if part['message'].get('content'):
                print(part['message']['content'], end='', flush=True)
                all_message += part['message']['content']
    except Exception as e:
        print('Error in select_tool:', e)
        traceback.print_exc()
        return None, None, f"<failed>\n{str(e)}\n</failed>"
    return None, None, all_message.split('</think>')[-1].strip()



class ToolCaller:
    def __init__(self, client: AsyncClient, messenger: Messenger, browser: Browser):
        self.client = client
        # self.model = "deepseek-r1:70b"
        # self.model = "qwen2.5-coder:32b"
        # self.model = "qwen3:235b-a22b"
        # self.model = "qwen3_64:latest"
        # self.model = "qwen3_8_64:latest"
        self.model = "qwen3_30_64:latest"
        # self.model = "granite3.3:latest"
        # self.model = "qwq:latest"
        # self.model = "qwq_jap:latest"
        self.messenger = messenger
        self.browser = browser
        self.no_tool_count = 0

        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            # メインスレッド以外で初期化された場合など、
            # ループがまだ実行されていない場合のフォールバック (通常は不要かも)
            self.loop = asyncio.get_event_loop()

        def read_file(file_path: str) -> str:
            """Read the contents of a specified file."""
            try:
                cwd = pathlib.Path.cwd()
                file_path_obj = pathlib.Path(file_path)
                if cwd not in file_path_obj.parents:
                    return "Error: Access to files outside the current working directory is not allowed."
                with open(file_path_obj, 'r') as file:
                    return file.read()
            except Exception as e:
                return str(e)

        def write_file(file_path: str, content: str) -> str:
            """Write content to a specified file, with optional user confirmation."""
            # TODO: read_fileと同様にcwd以下かチェックする
            try:
                cwd = pathlib.Path.cwd()
                file_path_obj = pathlib.Path(file_path)
                if cwd not in file_path_obj.parents:
                    return "Error: Access to files outside the current working directory is not allowed."
                with open(file_path, 'w') as file:
                    file.write(content)
                    return "File written successfully"
            except Exception as e:
                return str(e)

        def run_command(command):
            """Run a shell command on Mac and return the output. curl and wget are not supported."""
            if not command.strip():
                return "<failed>\nコマンドが指定されていません\n</failed>"
            first_command = command.strip().split()[0]
            if first_command not in ["curl", "wget"]:
                return "<failed>\ncurlまたはwgetは使用できません\n</failed>"
            try:
                asyncio.run_coroutine_threadsafe(self.messenger.send("コマンドを実行します:" + command[:30]), self.loop)
                result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
                return "<success>\n" + result.stdout + "\n</success>"
            except subprocess.CalledProcessError as e:
                # コマンドが失敗した場合 (非ゼロの終了コード)
                # 標準エラー出力を含めてエラー情報を返す
                error_message = f"<failed>\n終了コード: {e.returncode}\n標準出力:\n{e.stdout}\n標準エラー出力:\n{e.stderr}\n</failed>"
                print(error_message) # エラー情報をログ出力 (任意)
                return error_message

            except Exception as e:
                # その他の予期せぬエラー (ファイルが見つからないなど)
                error_message = f"<failed>\nエラーが発生しました:\n{str(e)}\n</failed>"
                print(error_message) # エラー情報をログ出力 (任意)
                return error_message
            except Exception as e:
                return str(e)

        def report_to_user(message: str) -> str:
            """Report to user about the progress."""
            asyncio.run_coroutine_threadsafe(self.messenger.send(message), self.loop)
            return f"以下のメッセージを送信しました\n\n{message}\n"

        def ask_to_user(message: str) -> str:
            """Ask for confirmation."""
            asyncio.run_coroutine_threadsafe(self.messenger.send(message), self.loop)
            return "[PENDING]"

        def complete(message: str):
            """Report to user abount finish task with message. タスクの完了した旨を、すべての文脈を省略せずに内容を要約してメッセージを送信します"""
            asyncio.run_coroutine_threadsafe(self.messenger.send(message + "\n会話を終了します"), self.loop)
            return None

        async def search(query: str, augmented_query1: str, augmented_query2: str) -> str:
            """Search Google using the Custom Search API. And return the summary of the results."""
            not_found_message = f"<query>{query}</query>\n<augmented_query1>{augmented_query1}</augmented_query1>\n<augmented_query2>{augmented_query2}</augmented_query2>\n検索結果が見つかりませんでした。検索クエリを変えて再度試してください"
            try:
                print('use search google', query, augmented_query1, augmented_query2)
                queries = [query, augmented_query1, augmented_query2]
                results = await batch_search(queries, num_results=10)
                if not results:
                    return not_found_message

                #now = datetime.now().strftime('%Y%m%d_%H%M%S')
                #with open(f"search_results/r{now}.txt", "w") as f:
                #    f.write(json.dumps(results, ensure_ascii=False, indent=2))

                output_text = ""
                for result in results[:5]:
                    title = result['title']
                    og_description = result['og:description']
                    link = result['link']
                    snippet = result['snippet']
                    output_text += f"<reference><title>{title}</title><desc>{og_description}</desc><snippet>{snippet}</snippet><link>{link}</link></reference>\n"

                print('results', output_text)
                return output_text

            except Exception as e:
                import traceback
                print(traceback.format_exc())
                return f"Error searching Google: {str(e)}"

        async def infer_knowledge_by_url(url: str, what_to_search: str) -> str:
            """Infer knowledge from a given URL about a specific what_to_search (this argument should also include objective of what_to_search)."""
            await self.messenger.send(f"{url} を取得し{what_to_search}についての情報を抜き出します")
            content = await get_content(self.browser, url)
            prompt = (
                "以下の文章はWebページをテキスト化したものです。what_to_searchに関連する情報を、以下のcontentから抜き出してください"
                "<what_to_search>" + what_to_search + "</what_to_search>\n<content>\n" + content + "\n</content>"
            )
            res = await client.chat(
                model=self.model,
                messages=[
                    Message(role=UserRole.system, content=(
                        "あなたは優秀な編集者です。入力はWebページの内容で関係のない情報も多く含まれるため、慎重に重要な情報を取捨選択します。抜き出す箇所にURLがある場合はURLも抜き出します"
                    )),
                    Message(role=UserRole.user, content=prompt)
                ]
            )
            return res.message.content.split('</think>')[-1].strip()

        def refine_task(self, current_task: str, context: str) -> str:
            """
            現在のタスクとコンテキストに基づいてタスクをリファインメントします。
            新しいタスクの内容や背景を精緻化します。
            """
            prompt = (
                "以下のタスクを精緻化してください。\n"
                "<current_task>\n" + current_task + "\n</current_task>\n"
                "<context>\n" + context + "\n</context>\n"
                "タスクの内容や背景をより明確かつ詳細にした、改善されたタスクを返してください。"
            )
            res = asyncio.run_coroutine_threadsafe(
                self.client.chat(
                    model=self.model,
                    messages=[
                        Message(role= UserRole.system, content=(
                            "あなたはタスクのリファイナーです。"
                            "与えられたタスクをより明確かつ詳細に精緻化してください。"
                            "タスクの背景や要件を深く理解し、"
                            "具体的な詳細を追加して、より良くしてください。"
                        )),
                        Message(role= UserRole.user, content=prompt)
                    ]
                ),
                self.loop
            ).result()
            return res.message.content.split('</think>')[-1].strip()

        self.tools = [
            read_file,
            write_file,
            run_command,
            report_to_user,
            ask_to_user,
            complete,
            # remember_string,
            # recall_string,
            search,
            infer_knowledge_by_url,
            refine_task,
        ]
        self.available_functions = {
            tool_func.__name__: tool_func
            for tool_func in self.tools
        }

    async def action(self, state: AgentLocalState) -> Tuple[List[Message], bool, bool]:
        copy_messages = state.messages.copy()
        current_task = state.current_task

        print('length:', len(copy_messages))
        function_name, arguments, all_messages = await select_tool(self.model, copy_messages, self.tools)
        print('function_name:', function_name)
        if function_name is None:
            self.no_tool_count += 1
            print('No tool selected', self.no_tool_count)
            if self.no_tool_count >= 3:
                complete_message = "過去3回ツールが選択されなかったため、タスクを終了します。"
                function_to_call = self.available_functions['complete']
                function_to_call(message=complete_message)
                return AgentLocalState(messages=copy_messages, current_task=current_task), True, True
            if not all_messages:
                all_messages = "ツールを使用しませんでした。"
            copy_messages.append(Message(role=UserRole.assistant, content=all_messages))
            copy_messages.append(Message(role=UserRole.user, content=f"ツールが選択されませんでした。\nタスク: {current_task}\nを遂行するために、どのツールを使うべきか考えてください。"))
            return AgentLocalState(messages=copy_messages, current_task=current_task), False, False
        else:
            self.no_tool_count = 0

        results = ""
        try:
            if function_to_call := self.available_functions.get(function_name):
                print('Calling function:', function_name)
                print('Arguments:', arguments)
                if function_name == 'ask_to_user':
                    function_to_call(**arguments)
                    copy_messages.append(Message(role=UserRole.assistant, content=arguments['message']))
                    return AgentLocalState(messages=copy_messages, current_task=current_task), True, False
                if function_name == 'complete':
                    function_to_call(**arguments)
                    copy_messages.append(Message(role=UserRole.assistant, content="タスクを完了しました"))
                    return AgentLocalState(messages=copy_messages, current_task=current_task), True, True
                if function_name == 'refine_task':
                    current_task = function_to_call(**arguments)
                    copy_messages.append(Message(role=UserRole.assistant, content="タスクを更新しました"))
                    return AgentLocalState(messages=copy_messages, current_task=current_task), False, False
                if function_name in ['search', 'infer_knowledge_by_url']:
                    output = await function_to_call(**arguments)
                else:
                    output = function_to_call(**arguments)
                print('Function output:', output)
                results += "tool used: " + function_name + "\n<result>\n" + str(output) + "\n</result>\nこれを踏まえて、次に何をするべきか考えてください。\n\nタスク: " + current_task
            else:
                print('Function', function_name, 'not found')
        except Exception as e:
            print('Error calling function:', e)
            traceback.print_exc()
            results = f"<failed>\n{str(e)}\n</failed>"
            copy_messages.append(Message(role=UserRole.assistant, content="ツールの実行に失敗しました: " + str(e)))

        copy_messages.append(Message(role=UserRole.assistant, content=str(function_name) + "を実行します"))
        copy_messages.append(Message(role=UserRole.user, content=results))
        print('message length:', len(copy_messages))
        return AgentLocalState(messages=copy_messages, current_task=current_task), False, False




if __name__ == "__main__":
    asyncio.run(main())
