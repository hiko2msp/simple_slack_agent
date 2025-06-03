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
from a2a.server import A2AServer
from a2a.agent import Agent
from a2a.message import Message as A2AMessage # Alias to avoid conflict with existing Message


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


class A2AMessenger(Messenger):
    def __init__(self, thread_ts: str = "a2a_thread"): # thread_ts might be less relevant for A2A direct responses
        super().__init__(thread_ts)
        self.final_response: str | None = None
        self.response_ready: bool = False

    async def send(self, message: str) -> None:
        # This send is called by tools like 'complete' or 'report_to_user'.
        # For A2A, the message from 'complete' tool is the critical one.
        # If other tools use 'send', their messages might be ignored or logged.
        # We are primarily interested in the message from the 'complete' tool.
        # A simple approach: the last message sent, especially if it ends with
        # a specific marker from the 'complete' tool, is the final response.
        # Or, the 'complete' tool itself will call this, and that's our signal.

        print(f"A2AMessenger received message: {message}")
        # For now, let's assume any message sent to this messenger could be a candidate
        # for the final response. The logic in 'complete' tool will be key.
        # If 'complete' calls this, it means this is the final message.
        self.final_response = message
        self.response_ready = True
        # In a more complex scenario, we might check if the message comes from
        # the 'complete' tool specifically.

    def get_final_response(self) -> str | None:
        return self.final_response

    def is_response_ready(self) -> bool:
        return self.response_ready


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

# Agent state management (AgentState class removed)

class AgentLocalState(BaseModel):
    messages: List[Message] = []
    current_task: str = ""


# agent_state = AgentState() # Removed

# async def agent_main_loop(): # Commented out / To be removed
#     await initialize_browser()
#     if not _browser:
#         print("Failed to initialize browser. Agent loop cannot start.")
#         return
#     local_state = AgentLocalState(messages=Message.init(), current_task="")
#     try:
#         while agent_state.running: # agent_state would be undefined
#             tool_caller = ToolCaller(client, agent_state.messenger, _browser) # agent_state would be undefined
#             if agent_state.busy_with_user: # agent_state would be undefined
#                 await asyncio.sleep(3)
#                 continue
#
#             if agent_state.last_user_interaction: # agent_state would be undefined
#                 if not local_state.current_task:
#                     task = agent_state.last_user_interaction.strip() # agent_state would be undefined
#                     local_state.messages.append(Message(role=UserRole.user, content=task))
#                     local_state.current_task = task
#                 else:
#                     local_state.messages.append(Message(role=UserRole.user, content=agent_state.last_user_interaction)) # agent_state would be undefined
#                 agent_state.last_user_interaction = None # agent_state would be undefined
#
#             local_state, wait_for_user, done = await tool_caller.action(local_state)
#             await asyncio.sleep(1)
#             print('-----最新のメッセージ-----')
#             for message in local_state.messages[-2:]:
#                 print(message)
#
#             if wait_for_user: # agent_state would be undefined
#                 agent_state.busy_with_user = True
#
#             if done:
#                 print('終了しました')
#                 local_state = AgentLocalState(messages=Message.init(), current_task="")
#                 agent_state.busy_with_user = True # agent_state would be undefined
#     finally:
#         await shutdown_browser()

async def agent_process_single_task(current_task_state: AgentLocalState, tool_caller: ToolCaller) -> AgentLocalState:
    temp_local_state = current_task_state
    max_iterations = 10 # Max iterations to prevent infinite loops

    for i in range(max_iterations):
        print(f"Agent iteration {i+1}/{max_iterations} for task: {temp_local_state.current_task}")

        # Ensure the messenger is of type A2AMessenger for checking response_ready
        # This check is more for type safety / debugging if other messengers were used.
        messenger_is_a2a = isinstance(tool_caller.messenger, A2AMessenger)

        # If the A2AMessenger already has a response (e.g. from 'complete' tool), we can stop early.
        if messenger_is_a2a and tool_caller.messenger.is_response_ready():
            print("A2AMessenger has a response ready. Ending task processing early.")
            break

        temp_local_state, wait_for_user, done = await tool_caller.action(temp_local_state)

        if done:
            print(f"Task '{temp_local_state.current_task}' marked as done.")
            # The 'complete' tool should have used the messenger to set the final response.
            break
        if wait_for_user:
            # In A2A, 'ask_to_user' might not be directly usable or mean something different.
            # If it's used, it implies the agent is stuck waiting for external input not available in A2A.
            # The 'complete' tool should be used for final output.
            print(f"Task '{temp_local_state.current_task}' is waiting for user input, which is not supported in A2A. Task may be stuck.")
            if tool_caller.messenger and messenger_is_a2a and not tool_caller.messenger.is_response_ready():
                 await tool_caller.messenger.send("Error: Task is blocked waiting for user input in A2A mode.")
            break

        # Optional: Add a small delay if needed, e.g., await asyncio.sleep(0.1)

    else: # For loop completed without break (max_iterations reached)
        print(f"Max iterations reached for task: {temp_local_state.current_task}")
        if tool_caller.messenger and messenger_is_a2a and not tool_caller.messenger.is_response_ready():
            # If loop finishes and 'complete' wasn't called (or messenger not ready)
            await tool_caller.messenger.send("Error: Task processing timed out after max iterations.")

    return temp_local_state


async def main():
    await initialize_browser() # Keep browser initialization
    if not _browser:
        print("Failed to initialize browser. A2A Server cannot start.")
        return

    # Ollama client is already global
    # global client

    search_agent_service = SearchServiceAgent(client, _browser)

    # Configure the server (host and port should be from env vars or defaults)
    host = os.getenv("A2A_HOST", "0.0.0.0")
    port = int(os.getenv("A2A_PORT", "8080"))

    server = A2AServer(search_agent_service, host, port)
    print(f"Starting A2A server for Search Agent on {host}:{port}")
    try:
        await server.start() # Assuming a start() method
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        await server.stop() # Assuming a stop() method
        await shutdown_browser() # Keep browser shutdown

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

        async def complete(message: str):
            """Report to user about finish task with message. For A2A, this message becomes the final response."""
            if hasattr(self.messenger, 'send') and asyncio.iscoroutinefunction(self.messenger.send):
                await self.messenger.send(message)
            elif self.messenger and hasattr(self.messenger, 'send'):
                # Synchronous fallback, though A2AMessenger is async
                self.messenger.send(message)
            else:
                print(f"Warning: 'complete' tool called but no messenger or send method available. Message: {message}")
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
                    function_to_call(**arguments) # This is sync, but ask_to_user sends to messenger which might be async.
                                                 # For A2A, ask_to_user is problematic anyway.
                    copy_messages.append(Message(role=UserRole.assistant, content=arguments['message']))
                    return AgentLocalState(messages=copy_messages, current_task=current_task), True, False # wait_for_user = True
                if function_name == 'complete':
                    await function_to_call(**arguments) # Now awaiting the async complete
                    # The message for the assistant's turn, confirming task completion.
                    # This is for the internal message history. The actual A2A response is set by messenger.send.
                    copy_messages.append(Message(role=UserRole.assistant, content="タスク「" + current_task + "」を完了しました。結果をA2Aクライアントに返します。"))
                    # 'done' is True, 'wait_for_user' can also be True to signal the loop to stop.
                    return AgentLocalState(messages=copy_messages, current_task=current_task), True, True
                if function_name == 'refine_task':
                    current_task = function_to_call(**arguments) # refine_task is synchronous
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


class SearchServiceAgent(Agent): # Assuming Agent is from a2a.agent
    def __init__(self, ollama_client, browser):
        super().__init__()
        self.ollama_client = ollama_client # Store the Ollama client
        self.browser = browser       # Store the browser instance
        # ToolCaller will be instantiated per request in handle_search

    async def handle_search(self, query: str) -> str:
        print(f"A2A SearchServiceAgent: Received search query: {query}")

        # 1. Instantiate A2AMessenger for this request
        a2a_messenger = A2AMessenger()

        # 2. Instantiate ToolCaller with the A2AMessenger
        # Make sure the ToolCaller is compatible with receiving the ollama_client and browser if needed
        tool_caller = ToolCaller(client=self.ollama_client, messenger=a2a_messenger, browser=self.browser)

        # 3. Prepare AgentLocalState for the task
        # The initial messages might need to include the system prompt and the user's query.
        initial_messages = Message.init() # Gets SYSTEM_PROMPT and current date
        initial_messages.append(Message(role=UserRole.user, content=query))

        current_task_state = AgentLocalState(
            messages=initial_messages,
            current_task=query # The query itself is the task description
        )

        # 4. Call a refactored version of the agent's main loop
        # This loop will run until the task is 'done' (e.g., 'complete' tool is called).
        # We'll define `agent_process_single_task` in the next plan step.
        # It will take current_task_state and tool_caller as arguments.
        # For now, assume it modifies current_task_state and uses tool_caller.

        # Placeholder for the call to the refactored loop:
        # final_task_state = await agent_process_single_task(current_task_state, tool_caller)

        # For this subtask, we'll just simulate that the loop ran and the messenger was used.
        # In a real scenario, the agent_process_single_task would call tool_caller.complete()
        # which would use a2a_messenger.send().
        # Simulating this:
        # await a2a_messenger.send(f"Simulated processed result for: {query}")

        # The actual call will be implemented/refined in conjunction with Step 4 of the plan.
        # For now, let's assume the loop will run and use the messenger.
        # The test for this step will focus on the setup.
        # We need to integrate the actual loop call later.

        # What we expect:
        # After `agent_process_single_task` runs, `a2a_messenger.is_response_ready()` should be true,
        # and `a2a_messenger.get_final_response()` should have the result.

        # This subtask focuses on setting up handle_search.
        # The actual execution logic using agent_process_single_task will be the next step.
        # For now, return a placeholder indicating setup.

        print(f"SearchServiceAgent: Placeholder for running agent_process_single_task with query: {query}")
        # In the fully implemented version, we would wait for the loop and then:
        # if a2a_messenger.is_response_ready():
        #     final_response = a2a_messenger.get_final_response()
        #     print(f"A2A SearchServiceAgent: Sending response: {final_response}")
        #     return final_response if final_response is not None else "Error: No response generated."
        # else:
        #     print("A2A SearchServiceAgent: Error: Response not ready after task processing.")
        #     return "Error: Agent did not produce a final response."


        # 4. Call the agent processing loop
        processed_task_state = await agent_process_single_task(current_task_state, tool_caller)

        # 5. Retrieve and return the response from the A2AMessenger
        if a2a_messenger.is_response_ready():
            final_response = a2a_messenger.get_final_response()
            print(f"A2A SearchServiceAgent: Sending response: {final_response}")
            # Ensure a string is always returned.
            return final_response if final_response is not None else "Error: Agent generated a null response."
        else:
            # This case might occur if the loop finished due to max_iterations
            # or another condition without the 'complete' tool being called successfully.
            print("A2A SearchServiceAgent: Error: Response not ready after task processing.")
            # Check if a timeout message was set by agent_process_single_task
            timeout_response = a2a_messenger.get_final_response()
            if timeout_response and "Error: Task processing timed out" in timeout_response:
                return timeout_response
            return "Error: Agent did not produce a final response or timed out without specific error."
