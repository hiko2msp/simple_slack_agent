import os
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from pydantic import BaseModel, Field
from enum import Enum
import asyncio
from ollama import AsyncClient
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()


client = AsyncClient(
    host=os.environ["OLLAMA_HOST"],
)
app = AsyncApp(
    token=os.environ["SLACK_ACCESS_TOKEN"],
)



class UserRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"

class Message(BaseModel):
    role: UserRole = Field(..., description="The user who sent the message")
    content: str = Field(..., description="The text of the message")

    def __str__(self):
        return f"{self.role}: {self.content}"



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
        ]
    }
    await say(text, thread_ts=thread_ts)

_messages = defaultdict(list)

@app.event("message")
async def handle_app_mention(body, say, ack):
    global _messages
    user_message = body["event"]["text"]
    thread_ts = body["event"].get("thread_ts", body["event"]["ts"])
    await ack()
    if not _messages.get(thread_ts):
        _messages[thread_ts].append(
            Message(role=UserRole.system, content=(
                "あなたは優秀なエージェントです。謙虚に振る舞いユーザーと簡潔に対話を行います。markdown形式で回答してください"
            )),
        )

    _messages[thread_ts].append(Message(role=UserRole.user, content=user_message))
    res = await client.chat(
        model="qwen3:32b",
        messages=_messages[thread_ts]
    )
    assistant_message = res.message.content.split('</think>')[-1]
    _messages[thread_ts].append(Message(role=UserRole.assistant, content=assistant_message))
    await send(say, assistant_message, thread_ts)



if __name__ == "__main__":
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"], loop=asyncio.get_event_loop())
    asyncio.get_event_loop().run_until_complete(handler.start_async())
