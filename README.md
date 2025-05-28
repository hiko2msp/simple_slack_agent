# simple_slack_agent

## Overview
This project is a Slack bot that interacts with an Ollama-based Large Language Model (LLM). It allows users to communicate with the LLM through Slack messages.

## Features
- Listens to messages in Slack threads.
- Maintains a separate conversation history for each thread.
- Interacts with a configurable Ollama model.
- Responds in markdown format.
- **Conversation Memory (Optional):** When enabled via the `MEMORY_FEATURE_ENABLED` environment variable, the bot generates a 'meeting minutes' style summary of the entire conversation within a thread. These comprehensive summaries are stored globally, with each conversation thread keeping only its latest summary (updated upon new activity in the thread). These global summaries are then used as context for new interactions.

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
-   `OLLAMA_HOST`: (Required) The URL of your Ollama instance.
-   `MEMORY_FEATURE_ENABLED`: (Optional) Set to `true` to enable the conversation memory feature. Defaults to `false`. When enabled, the bot generates a 'meeting minutes' style summary of the entire conversation within a thread. Each conversation thread's latest comprehensive summary is stored and updated in a global database. The bot then recalls a selection of recent global summaries from this database to provide context for new interactions.
-   **Default Ollama Model**: The bot currently uses the `llama4:maverick` model by default. This is hardcoded in `main.py`.

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
