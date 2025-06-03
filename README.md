# simple_slack_agent

## Overview
This project is a Slack bot that interacts with an Ollama-based Large Language Model (LLM). It allows users to communicate with the LLM through Slack messages.

## Features
- Listens to messages in Slack threads.
- Maintains a separate conversation history for each thread.
- Interacts with a configurable Ollama model.
- Responds in markdown format.
- **Integrated Search Mode:** Offers a special `/search` mode in Slack that communicates with a dedicated `search_agent` via an A2A (Agent-to-Agent) protocol. This allows users to directly leverage the `search_agent`'s web search capabilities.
- **Conversation Memory (Optional):** When enabled via the `MEMORY_FEATURE_ENABLED` environment variable, the bot generates a 'meeting minutes' style summary of the entire conversation within a thread. These comprehensive summaries are stored globally, with each conversation thread keeping only its latest summary (updated upon new activity in the thread). These global summaries are then used as context for new interactions.

## Search Agent
The Search Agent is a sophisticated component that now runs as an **A2A (Agent-to-Agent) server**. It is capable of performing web searches, browsing URLs, and potentially other tasks, exposing these as services to other agents. It utilizes an Ollama-based Large Language Model (LLM) for reasoning, tool selection, and task execution when handling requests.

Key features of the Search Agent include:
- **Web Search:** Leverages the Google Custom Search API to find relevant information online.
- **URL Browsing:** Can navigate to web pages and extract their content using Playwright.
- **File System Operations:** Able to read from and write to files within its designated workspace.
- **Command Execution:** Can run shell commands (with some restrictions, e.g., `curl` and `wget` are disabled by default).
- **LLM-Powered Tool Use:** Employs an LLM (e.g., Qwen) via Ollama to intelligently choose and use available tools in a step-by-step manner to achieve objectives based on A2A requests.
- **A2A Service:** Exposes its functionality, primarily search, via an A2A server interface (see `A2A_HOST`, `A2A_PORT` in configuration).

The core logic for the Search Agent is located in the `agents/search_agent/` directory, primarily within `search_agent.py`.

### Running the Search Agent
The Search Agent is now run as an A2A server. Ensure you have the necessary environment variables configured (see "Configuration" section, particularly A2A settings).
To run the agent:
```bash
python agents/search_agent/search_agent.py
```
This starts the A2A server, making it available for agents like the `slack_agent` to connect.
Note: The Search Agent uses Playwright for browser automation, which may require installing browser binaries the first time it runs or if they are not found. Playwright will attempt to download them automatically. The agent also uses a separate Ollama instance, configured by default to `http://localhost:12345`.

## Prerequisites
- Python 3.13 or higher
- A Slack App with the necessary permissions and tokens (Bot Token Scopes: `app_mentions:read`, `chat:write`, `channels:history`, `groups:history`, `im:history`, `mpim:history`)
- An running Ollama instance (refer to [Ollama documentation](https://ollama.com/library/qwen) for setup)

## Setup and Installation
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/simple_slack_agent.git
    cd simple_slack_agent
    ```
2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```
3.  **Install dependencies:**
    This project uses `uv` for dependency management. If you don't have `uv` installed, you can install it via pip: `pip install uv`.
    The dependencies are listed in `pyproject.toml` and a lock file `uv.lock` is provided. To install the dependencies, run:
    ```bash
    uv pip sync
    ```
    Alternatively, if you prefer to use pip with a requirements file (though one is not explicitly provided in the root):
    You can generate a `requirements.txt` from `pyproject.toml` if needed or install directly.
    A common way to install from `pyproject.toml` using pip is:
    ```bash
    pip install .
    ```

4.  **Set up the `.env` file:**
    Copy the `.env.example` file to `.env`:
    ```bash
    cp .env.example .env
    ```
    Then, edit the `.env` file with your specific credentials:
    -   `SLACK_ACCESS_TOKEN`: Your Slack app's Bot User OAuth Token (starts with `xoxb-`).
    -   `SLACK_APP_TOKEN`: Your Slack app's App-Level Token (starts with `xapp-`). This is required for Socket Mode.
    -   `OLLAMA_HOST`: The URL of your running Ollama instance (e.g., `http://localhost:11434`).

## Running the Application
Once the setup is complete, you can run the bot with:
```bash
python main.py
```
Ensure your Ollama instance is running and accessible at the `OLLAMA_HOST` specified in your `.env` file.

## How to Use
1.  Invite the bot to a Slack channel.
2.  Mention the bot in a message to start a conversation. For example, `@your_bot_name How are you?`.
3.  The bot will create a thread for the conversation. Continue interacting with the bot by replying within that thread.
4.  The bot will maintain the context of the conversation within that specific thread.

## Configuration
The application is configured through environment variables:

-   `SLACK_ACCESS_TOKEN`: (Required) Your Slack app's Bot User OAuth Token.
-   `SLACK_APP_TOKEN`: (Required) Your Slack app's App-Level Token for Socket Mode.
-   `OLLAMA_HOST`: (Required) The URL of your Ollama instance (e.g., `http://localhost:11434` for the Slack bot).
-   `MEMORY_FEATURE_ENABLED`: (Optional) Set to `true` to enable the conversation memory feature for the Slack bot. Defaults to `false`.
-   **Default Ollama Model**: The Slack bot currently uses the `MODEL` variable defined in `main.py` (e.g. "qwen3:32b"). This can be changed there.

### Search Agent Specific Configuration
The following environment variables are used by the Search Agent:
-   `A2A_HOST`: Host for the `search_agent` A2A server (default: `0.0.0.0`).
-   `A2A_PORT`: Port for the `search_agent` A2A server (default: `8080`).
-   `SEARCH_AGENT_A2A_HOST`: Host of the `search_agent` A2A server that `slack_agent` connects to (default: `localhost`).
-   `SEARCH_AGENT_A2A_PORT`: Port of the `search_agent` A2A server that `slack_agent` connects to (default: `8080`).
-   `GOOGLE_API_KEY`: (Required for Search Agent) Your Google Custom Search API Key. Used for the web search functionality.
-   `GOOGLE_SEARCH_ENGINE_ID`: (Required for Search Agent) Your Google Custom Search Engine ID. Used for the web search functionality.
-   `OLLAMA_HOST` (for Search Agent): The Search Agent is configured to use an Ollama instance at `http://localhost:12345` by default (see `agents/search_agent/search_agent.py`). If you need to change this, you might need to modify the script directly or adapt it to use an environment variable.

## Viewing Conversation Memories

A utility script `view_memories.py` is provided to inspect the contents of the `memory.db` SQLite database, where conversation summaries are stored (if the memory feature is enabled).

To use it, run the following command from the root of the repository:

```bash
python view_memories.py
```

The script will print a formatted list of all stored memories, with the newest entries appearing first. It displays the timestamp (in UTC), the thread timestamp (`thread_ts`) associated with the memory, and a snippet of the summary.

## Contributing
Contributions are welcome! Please open an issue or submit a pull request.

## License
This project is licensed under the terms of the LICENSE file. (Note: A LICENSE file was not explicitly provided in the initial file listing, but this is a standard placeholder).
