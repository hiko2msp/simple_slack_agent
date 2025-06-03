# Search Agent

## Overview
The Search Agent is an autonomous component designed for research and information retrieval. It leverages an Ollama-based Large Language Model (LLM), specifically Qwen (model `qwen3_30_64:latest` by default), for reasoning and executing search tasks.

The Search Agent now operates as an **A2A (Agent-to-Agent) server**. Its primary purpose is to expose its search capabilities as a service that other agents (like the Slack Agent) can connect to and utilize. It listens for incoming A2A requests and uses its suite of tools, particularly web search and URL content inference, to gather information and return it to the calling agent.

## Features / Capabilities

The Search Agent is equipped with a variety of tools to interact with its environment:

-   **`read_file(file_path: str)`**: Reads the content of a specified file. For security, access is restricted to files within the agent's current working directory and its subdirectories.
-   **`write_file(file_path: str, content: str)`**: Writes the given content to a specified file. Similar to `read_file`, write operations are restricted to the current working directory and its subdirectories.
-   **`run_command(command: str)`**: Executes a shell command.
    *   Note: For security reasons, `curl` and `wget` commands are explicitly disallowed.
-   **`report_to_user(message: str)`**: Sends a message to the user. In the current standalone execution mode, this is typically printed to the console.
-   **`ask_to_user(message: str)`**: Poses a question or requests confirmation from the user. The agent will pause and wait for user input from the console.
-   **`complete(message: str)`**: Reports the successful completion of a task to the user, often summarizing the outcome, and then terminates the current interaction loop.
-   **`search(query: str, augmented_query1: str, augmented_query2: str)`**: Performs a web search using the Google Custom Search API. It takes a primary query and two augmented queries to improve search results, returning a list of search snippets and links.
    *   Requires `GOOGLE_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID` environment variables.
-   **`infer_knowledge_by_url(url: str, what_to_search: str)`**: Fetches the content of a given URL and then uses the LLM to extract specific information related to the `what_to_search` parameter.
    *   This tool utilizes Playwright for browser automation to retrieve web page content.
    *   It employs a caching mechanism for fetched URLs (stored in `.cache/search_agent/memory/`) and maintains a blacklist of problematic domains.
-   **`refine_task(current_task: str, context: str)`**: An internal mechanism where the agent can use the LLM to refine or clarify the current task based on gathered context. This helps in breaking down complex tasks or re-evaluating its approach.

The agent uses Playwright for robust web browsing capabilities, particularly within the `infer_knowledge_by_url` tool. Playwright manages browser instances to accurately render and interact with web pages.

## Setup and Configuration

To run the Search Agent, ensure the following setup and configuration steps are completed:

1.  **Environment Variables:**
    The Search Agent requires specific environment variables for its web search capabilities:
    *   `GOOGLE_API_KEY`: Your Google Custom Search API Key.
    *   `GOOGLE_SEARCH_ENGINE_ID`: Your Google Custom Search Engine ID.
    These should be set in your environment or in a `.env` file at the root of the project.

2.  **Ollama Instance:**
    The Search Agent is configured to connect to an Ollama instance at `http://localhost:12345` by default. This is hardcoded in `agents/search_agent/search_agent.py`.
    *   This is different from the main Slack bot's Ollama configuration (`OLLAMA_HOST` environment variable, typically `http://localhost:11434`).
    *   Ensure an Ollama instance is running and accessible at this address, with the required model (e.g., `qwen3_30_64:latest`) available.

3.  **A2A Server Configuration:**
    The Search Agent runs as an A2A server. Configure its listening host and port using these environment variables (also documented in [Configuration](./configuration.md#search-agent-a2a-server-configuration)):
    *   `A2A_HOST`: Host for the A2A server (default: `0.0.0.0`).
    *   `A2A_PORT`: Port for the A2A server (default: `8080`).

4.  **Playwright Browsers:**
    The agent uses Playwright for web browsing. If you haven't used Playwright before or if the necessary browser binaries are missing, you may need to install them. Playwright attempts to download these automatically when the agent initializes its browser. However, you can also install them manually:
    ```bash
    playwright install
    ```
    This command should be run in your project's virtual environment if you are using one.

## Running the Search Agent as an A2A Server

The Search Agent now primarily runs as an A2A server, making its search capabilities available to other agents.

1.  **Command-Line Execution:**
    Navigate to the root directory of the project and run the agent using:
    ```bash
    python agents/search_agent/search_agent.py
    ```
    This will start the A2A server on the host and port defined by the `A2A_HOST` and `A2A_PORT` environment variables (or their defaults).

2.  **Server Operation:**
    *   Upon starting, the agent initializes its components, including the Playwright browser and the Ollama client.
    *   It then starts the A2A server and waits for incoming connections and requests.
    *   The main exposed service method is `handle_search(query: str)`, which takes a search query string.
    *   When a request is received (e.g., from the Slack Agent in search mode), the `SearchServiceAgent` uses its `ToolCaller` instance (specifically the `search` tool) to perform the web search.
    *   The search results are then returned to the calling A2A client.
    *   Console output will show server startup messages, incoming search queries, and any errors encountered during search operations.

## How it Works (A2A Server Mode)

-   **A2A Server Initialization (`main` function):**
    *   The `main` function in `agents/search_agent/search_agent.py` now initializes and starts the `A2AServer`.
    *   It sets up the `SearchServiceAgent` instance, passing it the Ollama client and the initialized Playwright browser.
-   **`SearchServiceAgent(Agent)`:**
    *   This class, derived from the A2A SDK's `Agent` class, defines the server-side agent logic.
    *   Its `__init__` method initializes a `ToolCaller` instance. Note that the `messenger` component of `ToolCaller` is set to `None`, as direct user interaction (like `ask_to_user`) is not expected in this A2A service mode.
    *   The key method is `async def handle_search(self, query: str) -> str`. This method is exposed via the A2A server. When called, it uses the `search` function from its `ToolCaller`'s available functions to perform the search using the provided `query`. The original `search` tool expects `augmented_query1` and `augmented_query2`; in the `handle_search` adapter, the main `query` is currently passed for these as well for simplicity.
-   **Tool Usage (`ToolCaller`):**
    *   The `ToolCaller` remains responsible for managing and executing the actual search tools (`search`, `infer_knowledge_by_url`).
    *   The `search` tool utilizes `batch_search` (Google Custom Search API) and `get_content` (Playwright for fetching URLs from search results if needed, though `handle_search` primarily returns raw search results).
-   **No Direct User Interaction Loop:** Unlike its previous standalone version, the A2A server mode does not involve a direct console-based interaction loop for tasks, tool selection by an LLM for general purposes, or user prompts via `ask_to_user`. Its interaction is now solely based on handling A2A requests for the `handle_search` method.
