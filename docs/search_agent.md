# Search Agent

## Overview
The Search Agent is an autonomous component designed for research, task completion, and interaction with local files and web resources. It leverages an Ollama-based Large Language Model (LLM), specifically Qwen (model `qwen3_30_64:latest` by default), for reasoning, tool selection, and decision-making throughout its operation.

The primary purpose of the Search Agent is to understand user-provided tasks or queries and utilize a suite of available tools to gather information, manipulate files, and ultimately provide a comprehensive answer or complete the assigned objective.

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

3.  **Playwright Browsers:**
    The agent uses Playwright for web browsing. If you haven't used Playwright before or if the necessary browser binaries are missing, you may need to install them. Playwright attempts to download these automatically when the agent initializes its browser. However, you can also install them manually:
    ```bash
    playwright install
    ```
    This command should be run in your project's virtual environment if you are using one.

## Running the Search Agent

The Search Agent is a standalone script and runs separately from the main Slack bot application.

1.  **Command-Line Execution:**
    Navigate to the root directory of the project and run the agent using:
    ```bash
    python agents/search_agent/search_agent.py
    ```

2.  **Interaction Flow:**
    *   Upon starting, the agent initializes its components, including the Playwright browser.
    *   The agent operates in a loop. The `agent_state.busy_with_user` flag (initially `True`) suggests it waits for an initial user input or task. The exact mechanism for providing this initial task in the current `search_agent.py` script (e.g., if it prompts directly or if `agent_state.last_user_interaction` needs to be set programmatically for an initial task) might require inspection of how `main()` or `agent_main_loop()` is triggered and if it includes initial user input handling.
    *   Once a task is provided (e.g., typed into the console when the agent is ready for input), the agent's LLM (`select_tool`) decides on the next action or tool to use.
    *   If a tool is selected (e.g., `search`, `read_file`), the `ToolCaller` executes it.
    *   The results of the tool are then fed back into the LLM's context.
    *   If the agent needs user input (e.g., using `ask_to_user`), it will print a message to the console and wait for the user to type a response.
    *   This process (LLM reasoning -> tool use -> result processing -> LLM reasoning) continues until the task is completed (using the `complete` tool) or if the agent cannot proceed.
    *   Console output will show the agent's thoughts, selected tools, tool outputs, and messages to the user.

## How it Works (Simplified)

-   **Main Loop (`agent_main_loop`):** The core of the agent, continuously processing tasks. It initializes the browser and enters a loop that manages the agent's state and interactions.
-   **State Management (`AgentState`, `AgentLocalState`):**
    *   `AgentState`: Global state, including whether the agent is running, busy with the user, and the last user interaction.
    *   `AgentLocalState`: Contains the conversation history (`messages`) and the `current_task`.
-   **Messages (`Message` class):** Pydantic models representing messages in the conversation, with roles like `system`, `user`, `assistant`, and `tool`. The conversation history is a list of these messages.
-   **Tool Selection and Execution (`ToolCaller`):**
    *   The `ToolCaller.action` method is central to the agent's operation.
    *   It calls `select_tool`, where the LLM analyzes the current conversation and task to choose an appropriate tool and its arguments.
    *   The selected tool function (e.g., `read_file`, `search`) is then invoked.
    *   The output of the tool is formatted and added to the message history as a `user` message (simulating the environment's response), so the LLM can process the result in the next iteration.
-   **User Interaction:** The `Messenger` class (abstract) is intended to handle communication. In the standalone script, this is implicitly console input/output, especially for tools like `ask_to_user` and `report_to_user`. The `agent_state.busy_with_user` flag and `agent_state.last_user_interaction` manage when the agent waits for or processes user input.
