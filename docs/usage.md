# Bot Usage

This page describes how to run the Simple Slack Agent and interact with it in your Slack workspace.

## Starting the Bot

1.  **Ensure Prerequisites are Met:** Before running the bot, make sure you have completed all steps in the [Setup and Installation guide](./setup.md), including installing dependencies and configuring your `.env` file.
2.  **Run the Application:**
    Navigate to the root directory of the project in your terminal (where `main.py` is located) and run the following command:
    ```bash
    python main.py
    ```
3.  **Keep the Bot Running:** The bot application must remain running in your terminal to listen for and respond to messages in Slack. If you close the terminal or stop the script, the bot will go offline.

## Interacting with the Bot in Slack

The bot listens for messages in channels it has been added to and in direct messages (DMs) sent to it.

1.  **Invite the Bot to a Channel (if applicable):**
    If you want to interact with the bot in a specific channel, you'll need to invite it to that channel first. You can usually do this by typing `/invite @YourBotName` in the desired channel (replace `@YourBotName` with your bot's actual Slack username).

2.  **Sending a Message:**
    Once the bot is in a channel or if you are in a DM with the bot, you can send a message. The current version of the bot processes all messages sent in channels it's a member of, or direct messages sent to it.

    *Example:*
    ```
    Hello bot, what's the weather like today?
    ```
    *(Note: While direct mentions like `@YourBotName` will also work, they are not strictly required for the bot to see your message in channels it's part of or in DMs.)*

3.  **Threaded Conversations:**
    The bot creates a new thread for each initial message it responds to. All subsequent interactions for that specific conversation will occur within that thread. This is important because **the bot maintains a separate conversation history for each thread.** This means the context from one thread will not leak into another.

4.  **Initial System Prompt:**
    When a new conversation thread is started, the bot is initialized with the following system prompt to guide its persona and response style:
    ```
    あなたは優秀なエージェントです。謙虚に振る舞いユーザーと簡潔に対話を行います。markdown形式で回答してください
    ```
    Translation: "You are an excellent agent. Behave humbly and interact concisely with users. Please respond in markdown format."
    This means the bot will aim to be helpful, polite, concise, and will format its answers using markdown.

## Slack Agent Search Mode

The Slack Agent features a dedicated "Search Mode" that allows you to send queries directly to the integrated `search_agent`. This mode is useful for when you specifically need web search results or other information the `search_agent` can provide, bypassing the Slack Agent's general LLM conversational abilities for that query.

**How to Use Search Mode:**

1.  **Enter Search Mode:**
    To enter search mode within a specific Slack thread, type the command:
    ```
    /search
    ```
    The bot will confirm that you have entered search mode for that thread.

2.  **Send Queries:**
    Once in search mode, any message you send in that thread will be treated as a query to the `search_agent`.
    For example:
    ```
    What are the latest developments in AI?
    ```
    The `slack_agent` will forward this query to the `search_agent`, and the results from the `search_agent` will be posted back into the thread.

3.  **Exit Search Mode:**
    To exit search mode and return to normal conversation with the Slack Agent's LLM in that thread, type the command:
    ```
    /search_exit
    ```
    The bot will confirm that you have exited search mode. Further messages in the thread will be processed by the Slack Agent's primary LLM again.

**Note:**
- Search mode is specific to each Slack thread. You can be in search mode in one thread and in normal conversation mode in another.
- If you send `/search` in a thread where you are already in search mode, it will effectively do nothing but might re-confirm you are in search mode. Similarly for `/search_exit`.

## Conversation Memory Feature (Optional)

This bot includes an optional conversation memory feature. If enabled by the administrator (using the `MEMORY_FEATURE_ENABLED` environment variable), the bot will:
1.  Generate a 'meeting minutes' style summary of the entire interaction history within the current Slack thread at the end of the exchange, focusing on key topics and outcomes without speaker attribution.
2.  Store this comprehensive summary locally in a shared database. If a summary for that specific Slack thread already exists, it will be overwritten with this latest comprehensive summary. This means only the most recent summary for any given thread is retained.
3.  When you start a new conversation, the bot will load a selection of the most recent comprehensive summaries from this global pool (featuring the latest updates from various threads). This helps the bot maintain context over longer periods or across sessions by providing it with a "memory" of what was previously discussed globally, consisting of the latest summary from various threads.

The memory is accessed globally, but storage is such that each thread only keeps its single, most up-to-date comprehensive summary in the global pool.

## Example Interaction

Here's a hypothetical example of an interaction:

**User** (in a channel where the bot is present, or in a DM):
> Can you explain what a Large Language Model is in simple terms?

**Bot** (replying in a thread):
> A Large Language Model (LLM) is like a very advanced computer program that has been trained on a massive amount of text and code. This training allows it to understand and generate human-like text.
>
> Think of it as a very knowledgeable assistant that can:
> - Answer your questions
> - Write different kinds of creative content
> - Summarize long texts
> - Translate languages
> - And much more!
>
> They don't "think" or "understand" in the way humans do, but they are very good at recognizing patterns in language and using those patterns to produce relevant and coherent responses.

## Using the Search Agent

This project also includes a **Search Agent**, which is a separate, standalone tool designed for more complex tasks involving web searches, file operations, and command execution. It operates independently of the Slack bot.

For detailed instructions on how to set up, configure, and run the Search Agent, please refer to its dedicated documentation:
- **[Search Agent Documentation](search_agent.md)**

---

Refer to the [Configuration](./configuration.md) page for details on how to customize the Slack bot's behavior, such as the Ollama model it uses.
