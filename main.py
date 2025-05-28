import os
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from pydantic import BaseModel, Field
from enum import Enum
import io
import sys
import traceback
import asyncio
import re
from ollama import AsyncClient, Image
from collections import defaultdict
import aiohttp
import json
from dotenv import load_dotenv

load_dotenv()


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
        print("Executing code:")
        print(code_string)
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

    is_recipe_request = "レシピ" in user_message

    if not _messages.get(thread_ts):
        system_prompt_content = ""
        if is_recipe_request:
            system_prompt_content = "あなたはレシピ提案のエキスパートです。提供された食材の画像に基づいて、ユーザーが作れる料理のレシピ案を3つ考えてください。材料と分量だけを明確に、markdown形式で提示してください。"
        else:
            system_prompt_content = (
                "あなたは優秀なエージェントです。謙虚に振る舞いユーザーと簡潔に対話を行います。markdown形式で回答してください\n"
                "pythonコードを含む場合は、コードブロックを使用して、実行可能なコードを提供してください。\n"
                "例: ```python\nprint('Hello, World!')\n```\n"
            )
        _messages[thread_ts].append(
            Message(role=UserRole.system, content=system_prompt_content),
        )

    base64_images = []
    if is_recipe_request and body["event"].get("files"):
        base64_images = await download_and_encode_images(body["event"]["files"], app.client.token)
    
    _messages[thread_ts].append(Message(role=UserRole.user, content=user_message, images=base64_images if base64_images else None))
    
    ollama_messages_for_first_call = []
    for msg in _messages[thread_ts]:
        msg_dict = {"role": msg.role.value, "content": msg.content}
        if msg.images:
            msg_dict["images"] = msg.images
        ollama_messages_for_first_call.append(msg_dict)

    res = await client.chat(
        model="llama4:maverick",
        messages=ollama_messages_for_first_call
    )
    assistant_message_content = res.message.get('content', '').split('</think>')[-1]

    codes_to_execute = extract_python_code(assistant_message_content)
    if codes_to_execute:
        _messages[thread_ts].append(Message(role=UserRole.assistant, content=assistant_message_content))

        for code_string in codes_to_execute:
            execution_result = execute_python_code(code_string)
            tool_message_content = json.dumps(execution_result)
            _messages[thread_ts].append(Message(role=UserRole.tool, content=tool_message_content))

        ollama_messages_for_second_call = []
        for msg in _messages[thread_ts]:
            msg_dict = {"role": msg.role.value, "content": msg.content}
            ollama_messages_for_second_call.append(msg_dict)
        
        res = await client.chat(
            model="llama4:maverick",
            messages=ollama_messages_for_second_call
        )
        assistant_message_content = res.message.get('content', '').split('</think>')[-1]
    
    _messages[thread_ts].append(Message(role=UserRole.assistant, content=assistant_message_content))
    await send(say, assistant_message_content, thread_ts)



if __name__ == "__main__":
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"], loop=asyncio.get_event_loop())
    asyncio.get_event_loop().run_until_complete(handler.start_async())
