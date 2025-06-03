import os
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from pydantic import BaseModel, Field
from enum import Enum
import io
import sys
import traceback
import asyncio
import re # Added for code extraction
from ollama import AsyncClient, Image
from collections import defaultdict
import aiohttp
import json
from dotenv import load_dotenv
import sqlite3
import time
from a2a.client import A2AClient
from a2a.message import Message as A2AMessage # If needed for constructing requests

load_dotenv()

MODEL = "qwen3:32b"  # Default model, can be overridden by environment variable
DB_PATH = "memory.db"
MEMORY_FEATURE_ENABLED = os.getenv("MEMORY_FEATURE_ENABLED", "false").lower() == "true"

SEARCH_AGENT_A2A_HOST = os.getenv("SEARCH_AGENT_A2A_HOST", "localhost")
SEARCH_AGENT_A2A_PORT = int(os.getenv("SEARCH_AGENT_A2A_PORT", "8080"))

_search_mode_state = defaultdict(bool)


# Define Pydantic model for system prompt rules
class SystemPromptRule(BaseModel):
    condition: str
    prompt_template: str

# Initialize global variable for system prompt rules
SYSTEM_PROMPT_RULES: list[SystemPromptRule] = [
    SystemPromptRule(
        condition="レシピ",
        prompt_template="あなたはレシピ提案のエキスパートです。提供された食材の画像に基づいて、ユーザーが作れる料理のレシピ案を3つ考えてください。材料と分量だけを明確に、markdown形式で提示してください。"
    ),
    SystemPromptRule(
        condition="", # Default Fallback Rule
        prompt_template="あなたは優秀なエージェントです。謙虚に振る舞いユーザーと簡潔に対話を行います。markdown形式で回答してください"
    )
]


client = AsyncClient(
    host=os.environ["OLLAMA_HOST"],
)
app = AsyncApp(
    token=os.environ["SLACK_ACCESS_TOKEN"],
)


def execute_python_code(code_string: str) -> dict:
    """
    Executes a string of Python code and captures its stdout, stderr,
    and any exceptions.

    Args:
        code_string: The Python code to execute.

    Returns:
        A dictionary with "stdout" and "stderr" keys.
        "stderr" will contain the traceback if an exception occurred.
    """
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture
    
    try:
        exec(code_string)
        stdout_result = stdout_capture.getvalue()
        stderr_result = stderr_capture.getvalue()
    except Exception:
        stderr_result = traceback.format_exc()
        stdout_result = stdout_capture.getvalue() # Capture any stdout before exception
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        stdout_capture.close()
        stderr_capture.close()
        
    return {"stdout": stdout_result, "stderr": stderr_result}


def init_db():
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                thread_ts TEXT NOT NULL PRIMARY KEY,
                timestamp REAL NOT NULL,
                summary TEXT NOT NULL
            )
        ''')
        # Index on timestamp remains useful for ordering by last update time
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories (timestamp DESC)
        ''')
        con.commit()
        print("Database initialized successfully with updated schema.")
    except sqlite3.Error as e:
        print(f"Database initialization error: {e}")
    finally:
        if con:
            con.close()

def add_memory(thread_ts: str, summary: str):
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        current_time = time.time() # Capture time once
        cur.execute("""
            INSERT INTO memories (thread_ts, timestamp, summary) VALUES (?, ?, ?)
            ON CONFLICT(thread_ts) DO UPDATE SET
                timestamp = excluded.timestamp,
                summary = excluded.summary
        """, (thread_ts, current_time, summary)) # Pass current_time
        con.commit()
        print(f"Memory added/updated for thread {thread_ts}")
    except sqlite3.Error as e:
        print(f"Error adding/updating memory for thread {thread_ts}: {e}")
    finally:
        if con:
            con.close()

def get_recent_memories(limit: int = 5) -> list[str]: # New signature
    memories = []
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        # cur.execute("SELECT summary FROM memories WHERE thread_ts = ? ORDER BY timestamp DESC LIMIT ?",
        #             (thread_ts, limit)) # Old query
        cur.execute("SELECT summary FROM memories ORDER BY timestamp DESC LIMIT ?",
                    (limit,)) # New query
        rows = cur.fetchall()
        memories = [row[0] for row in rows]
        memories.reverse() # Maintain chronological order for the prompt
        # print(f"Retrieved {len(memories)} memories for thread {thread_ts}") # Old log
        print(f"Retrieved {len(memories)} global memories") # New log
    except sqlite3.Error as e:
        # print(f"Error retrieving memories for thread {thread_ts}: {e}") # Old log
        print(f"Error retrieving global memories: {e}") # New log
    finally:
        if con:
            con.close()
    return memories

def _construct_initial_system_prompt(thread_ts: str, user_message: str) -> str:
    system_prompt_content = ""
    default_prompt_template = "" # Initialize default_prompt_template

    for rule in SYSTEM_PROMPT_RULES:
        if not rule.condition: # Check if condition is empty for default rule
            default_prompt_template = rule.prompt_template
        elif rule.condition in user_message:
            system_prompt_content = rule.prompt_template
            break # First match wins

    if not system_prompt_content: # If no specific rule matched
        if default_prompt_template: # Check if a default was found
            system_prompt_content = default_prompt_template
        else:
            # Fallback if SYSTEM_PROMPT_RULES is empty or has no default rule
            # This case should ideally be avoided by ensuring SYSTEM_PROMPT_RULES is well-defined
            system_prompt_content = "あなたは一般的なアシスタントです。ユーザーの質問に答えてください。"
            print(f"Warning: No matching system prompt rule found for user message and no default rule set. Using a generic default.")

    if MEMORY_FEATURE_ENABLED:
        recent_memories = get_recent_memories()
        if recent_memories:
            memory_header = "\n\n## Reference from Past Conversations (Summaries) - Use these lightly for context if relevant:\n"
            formatted_memories = "\n".join([f"- {mem}" for mem in recent_memories])
            system_prompt_content += memory_header + formatted_memories
            print(f"System prompt for thread {thread_ts} now includes {len(recent_memories)} memories.")
    return system_prompt_content

# Function to manage system prompt rules
def manage_system_prompt_rules(user_message: str) -> str:
    global SYSTEM_PROMPT_RULES # Required to modify the global list

    # Regex to parse the user message
    # Expected format: "システムプロンプト: 条件=<keyword>, プロンプト=<prompt_text>"
    # Using re.DOTALL so that . matches newlines in prompt_text
    match = re.match(r"システムプロンプト:\s*条件=(.+?),\s*プロンプト=(.+)", user_message, re.DOTALL)

    if not match:
        return "無効なルール形式です。期待される形式: 「システムプロンプト: 条件=キーワード, プロンプト=プロンプトテキスト」"

    condition = match.group(1).strip()
    prompt_text = match.group(2).strip()

    if not condition or not prompt_text: # Should not happen if regex matches and groups are non-empty
        return "無効なルール形式です。条件とプロンプトの両方が必要です。"

    # Check if a rule with this condition already exists
    for rule in SYSTEM_PROMPT_RULES:
        if rule.condition == condition:
            rule.prompt_template = prompt_text
            return f"システムプロンプトのルールを更新しました。条件: '{condition}'"

    # If no rule with the condition exists, create a new one
    new_rule = SystemPromptRule(condition=condition, prompt_template=prompt_text)

    # Add the new rule before the default rule (empty condition string)
    default_rule_index = -1
    for i, rule in enumerate(SYSTEM_PROMPT_RULES):
        if rule.condition == "":
            default_rule_index = i
            break

    if default_rule_index != -1:
        SYSTEM_PROMPT_RULES.insert(default_rule_index, new_rule)
    else:
        # Fallback: if no default rule is found (should not happen with current setup),
        # append to the end. This ensures the rule is added.
        SYSTEM_PROMPT_RULES.append(new_rule)
        print("Warning: Default system prompt rule not found. New rule appended to the end.")

    return f"新しいシステムプロンプトのルールを作成しました。条件: '{condition}'"


def extract_python_code(text: str) -> list[str]:
    """
    Extracts all Python code snippets from markdown-like code blocks.
    Returns a list of string code snippets.
    """
    # Pattern to find ```python ... ```
    # re.findall will return a list of all captured groups (the code itself)
    pattern = re.compile(r"```python\s*\n(.*?)\n```", re.DOTALL)
    matches = pattern.findall(text)
    # strip() each matched code block content
    return [match.strip() for match in matches]

class UserRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"

class Message(BaseModel):
    role: UserRole = Field(..., description="The user who sent the message")
    content: str = Field(..., description="The text of the message")
    images: list[Image] | None = Field(default=None, description="A list of base64-encoded images")

    def __str__(self):
        return f"{self.role}: {self.content}"


async def download_and_encode_images(files, slack_client_token):
    """
    Downloads images from Slack file objects and encodes them in base64.
    """
    base64_images = []
    async with aiohttp.ClientSession() as session:
        for file_info in files:
            if file_info.get("mimetype", "").startswith("image/"):
                image_url = file_info.get("url_private_download")
                if image_url:
                    try:
                        # Slack API requires Authorization header with bot token
                        headers = {"Authorization": f"Bearer {slack_client_token}"}
                        async with session.get(image_url, headers=headers) as resp:
                            if resp.status == 200:
                                image_bytes = await resp.read()
                                if not image_bytes:
                                    print(f"Empty image bytes for {image_url}")
                                    continue
                                base64_images.append(Image(value=image_bytes))
                            else:
                                print(f"Error downloading image: {resp.status} from {image_url}")
                    except Exception as e:
                        print(f"Exception during image processing: {e}")
    return base64_images

async def send(say, message: str, thread_ts):
    text = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            },
        ],
        "text": message,
    }
    await say(text, thread_ts=thread_ts)

_messages = defaultdict(list)

@app.event("message")
async def handle_app_mention(body, say, ack):
    global _messages
    await ack()

    user_message = body["event"].get("text", "") or body["event"].get("message", {}).get("text", "")
    thread_ts = body["event"].get("thread_ts", body["event"]["ts"])
    # channel_id = body["event"]["channel"] # Useful for potential logging or context

    # Search mode command handling
    user_message_lower = user_message.strip().lower()
    if user_message_lower == "/search":
        _search_mode_state[thread_ts] = True
        await send(say, "Entered search mode. Send your queries. Type `/search_exit` to leave.", thread_ts)
        return
    elif user_message_lower == "/search_exit":
        _search_mode_state[thread_ts] = False
        await send(say, "Exited search mode.", thread_ts)
        return

    # If in search mode, handle query
    if _search_mode_state[thread_ts]:
        client_a2a = A2AClient(remote_host=SEARCH_AGENT_A2A_HOST, remote_port=SEARCH_AGENT_A2A_PORT)
        try:
            print(f"Search mode active for {thread_ts}. Query: {user_message}. Contacting A2A server at {SEARCH_AGENT_A2A_HOST}:{SEARCH_AGENT_A2A_PORT}")
            await client_a2a.connect()
            response_data = await client_a2a.call_method("handle_search", query=user_message)
            
            if isinstance(response_data, A2AMessage):
                search_result = response_data.content
            elif isinstance(response_data, str):
                search_result = response_data
            elif isinstance(response_data, dict) and 'result' in response_data:
                search_result = response_data['result']
            else:
                search_result = str(response_data)

            await send(say, f"Search results:\n{search_result}", thread_ts)

        except Exception as e:
            error_message = f"Error communicating with search agent: {e}"
            print(error_message)
            traceback.print_exc()
            await send(say, error_message, thread_ts)
        finally:
            if hasattr(client_a2a, 'is_connected') and client_a2a.is_connected():
                await client_a2a.disconnect()
        return

    # --- START NEW INTEGRATION ---
    if user_message.startswith("システムプロンプト:"):
        response_message = manage_system_prompt_rules(user_message)
        await send(say, response_message, thread_ts)
        return
    # --- END NEW INTEGRATION ---

    # is_recipe_request is no longer needed here for system prompt construction,
    # but it's used below for image handling.
    # base_system_prompt is also no longer needed here.

    if not _messages.get(thread_ts):
        # Construct system prompt based on user message using the new rule-based function
        final_system_prompt = _construct_initial_system_prompt(thread_ts, user_message)
        _messages[thread_ts].append(
            Message(role=UserRole.system, content=final_system_prompt)
        )

    base64_images = []
    if body["event"].get("files"):
        base64_images = await download_and_encode_images(body["event"]["files"], app.client.token)
    
    _messages[thread_ts].append(Message(role=UserRole.user, content=user_message, images=base64_images if base64_images else None))
    
    # Convert Message objects to dictionaries for Ollama client
    # The ollama client expects a list of dicts.
    # If Message Pydantic models are passed directly, the ollama library handles serialisation.
    # Let's ensure this by passing the list of Message objects directly.
    
    ollama_messages_for_first_call = []
    for msg in _messages[thread_ts]:
        msg_dict = {"role": msg.role.value, "content": msg.content}
        if msg.images: # Only include images if present
            msg_dict["images"] = msg.images
        ollama_messages_for_first_call.append(msg_dict)

    res = await client.chat(
        model=MODEL, # Or your preferred model
        messages=ollama_messages_for_first_call # Pass the list of dicts
    )
    assistant_message_content = res.message.get('content', '').split('</think>')[-1] # Ensure content key exists

    # Attempt to extract python code from the assistant's message
    codes_to_execute = extract_python_code(assistant_message_content) # Now a list
    print(f"Extracted code blocks: {assistant_message_content}")
    print(f"Extracted code blocks: {codes_to_execute}")

    if codes_to_execute: # Check if the list is not empty
        # Store the original assistant message that contained the code blocks
        _messages[thread_ts].append(Message(role=UserRole.assistant, content=assistant_message_content))

        # Loop through each extracted code string and process it
        for code_string in codes_to_execute:
            execution_result = execute_python_code(code_string)
            tool_message_content = json.dumps(execution_result)
            print(f"Execution result: {tool_message_content}")
            _messages[thread_ts].append(Message(role=UserRole.tool, content=tool_message_content))

        # Prepare messages for the second Ollama call, after all tool messages are added
        ollama_messages_for_second_call = []
        for msg in _messages[thread_ts]:
            msg_dict = {"role": msg.role.value, "content": msg.content}
            # Images are not typically sent with tool responses or subsequent system messages
            # if msg.images: 
            #     msg_dict["images"] = msg.images
            ollama_messages_for_second_call.append(msg_dict)
        
        # Call Ollama again with the tool's output
        res = await client.chat(
            model=MODEL,
            messages=ollama_messages_for_second_call
        )
        assistant_message_content = res.message.get('content', '').split('</think>')[-1]
    
    # Append the final assistant message (either from the first or second call)
    _messages[thread_ts].append(Message(role=UserRole.assistant, content=assistant_message_content))

    if MEMORY_FEATURE_ENABLED:
        summarization_history_parts = []
        # _messages[thread_ts] already contains the history up to the point *before* the current assistant's response is added.
        # The current assistant's response (assistant_message_content) also needs to be included.

        temp_history_for_summarization = list(_messages[thread_ts]) # Make a copy
        # Add the latest assistant message to this temporary history for summarization
        temp_history_for_summarization.append(Message(role=UserRole.assistant, content=assistant_message_content))

        for msg in temp_history_for_summarization:
            if msg.role == UserRole.system: # Skip system messages for the summarization input
                continue
            # For tool messages, we might want to indicate the output clearly.
            # For user/assistant, just their content.
            if msg.role == UserRole.tool:
                summarization_history_parts.append(f"Tool Output: {msg.content}")
            else: # User and Assistant messages
                summarization_history_parts.append(f"{msg.role.value.capitalize()}: {msg.content}")
                
        full_conversation_history_text = "\n".join(summarization_history_parts)

        if full_conversation_history_text: # Proceed only if there's something to summarize
            summarization_prompt_content = (
                "You are a minute-taking assistant. Based on the following conversation history, "
                "create a concise summary or overview of the discussion. "
                "Do not include who said what (no speaker attribution). "
                "Focus on the key topics, decisions, and outcomes discussed.\n\n"
                "Conversation History:\n"
                f"{full_conversation_history_text}"
            )
            summarization_messages = [{"role": "user", "content": summarization_prompt_content}]

            try:
                summary_res = await client.chat(
                    model=MODEL, # Or your preferred model
                    messages=summarization_messages
                )
                interaction_summary = summary_res.message.get('content', '').strip()
                if interaction_summary:
                    add_memory(thread_ts, interaction_summary) # thread_ts is still key for storage
                else:
                    print(f"Summarization result was empty for thread {thread_ts}")
            except Exception as e:
                print(f"Error during summarization call for thread {thread_ts}: {e}")

    await send(say, assistant_message_content, thread_ts)


async def warm_up():
    """
    Warm up the Ollama client by making a simple request.
    This can help avoid cold start issues.
    """
    try:
        await client.chat(
            model=MODEL,
            messages=[]
        )
        print("Ollama client warmed up successfully.")
    except Exception as e:
        print(f"Error during warm-up: {e}")


if __name__ == "__main__":
    init_db()
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"], loop=asyncio.get_event_loop())
    asyncio.get_event_loop().run_until_complete(warm_up())
    asyncio.get_event_loop().run_until_complete(handler.start_async())
