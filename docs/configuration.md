# Configuration

This document outlines how to configure the Simple Slack Agent. Configuration includes setting up environment variables for credentials and API endpoints, as well as customizing the behavior of the LLM through model selection and system prompts.

## Environment Variables

The primary method of configuration is through environment variables. These variables should be defined in a `.env` file located in the root of the project directory. You can create this file by copying the `.env.example` file and populating it with your specific values.

The following environment variables are required:

-   `SLACK_ACCESS_TOKEN`:
    -   **Description:** Your Slack app's Bot User OAuth Token. This token allows the bot to connect to your Slack workspace and perform actions like reading and writing messages.
    -   **Example:** `xoxb-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
    -   **Source:** Obtain this token from your Slack app's configuration page under "OAuth & Permissions".

-   `SLACK_APP_TOKEN`:
    -   **Description:** An App-Level Token for your Slack app. This token is used to enable Socket Mode, which allows the bot to receive events from Slack without needing a publicly accessible HTTP endpoint.
    -   **Required Scope:** Ensure this token has the `connections:write` scope.
    -   **Example:** `xapp-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
    -   **Source:** Generate this token from your Slack app's "Basic Information" page, under the "App-Level Tokens" section.

-   `OLLAMA_HOST`:
    -   **Description:** The full URL of your running Ollama instance. This is where the bot will send requests to interact with the Large Language Model.
    -   **Example:** `http://localhost:11434` (if Ollama is running locally on the default port)
    -   **Source:** This depends on where your Ollama service is hosted.

## Ollama Model

The specific Large Language Model used by the bot is defined directly in the `main.py` file.

-   **Current Model:** The bot is currently hardcoded to use the `llama4:maverick` model.
-   **Location in Code:** You can find this setting within the `handle_app_mention` function in `main.py`:
    ```python
    res = await client.chat(
        model="llama4:maverick",  # <--- This line specifies the Ollama model
        messages=_messages[thread_ts]
    )
    ```
-   **Changing the Model:** To use a different model available in your Ollama instance, you can change the string value `"llama4:maverick"` to your desired model name (e.g., `"llama3:latest"`, `"mistral:latest"`).
-   **Available Models:** For a list of available models and how to download them, please refer to the [official Ollama library documentation](https://ollama.com/library).

## System Prompt

The system prompt is a set of initial instructions given to the LLM to define its persona, behavior, and the format of its responses. This prompt is also set directly in the `main.py` file.

-   **Current System Prompt:**
    ```
    あなたは優秀なエージェントです。謙虚に振る舞いユーザーと簡潔に対話を行います。markdown形式で回答してください
    ```
    *(Translation: "You are an excellent agent. Behave humbly and interact concisely with users. Please respond in markdown format.")*

-   **Location in Code:** This prompt is defined within the `handle_app_mention` function in `main.py` when a new conversation thread is initiated:
    ```python
    if not _messages.get(thread_ts):
        _messages[thread_ts].append(
            Message(role=UserRole.system, content=(
                "あなたは優秀なエージェントです。謙虚に振る舞いユーザーと簡潔に対話を行います。markdown形式で回答してください"  # <--- This is the system prompt
            )),
        )
    ```
-   **Changing the System Prompt:** You can modify the string content of this `Message` to change the bot's default behavior, tone, or instructions. For example, you could instruct it to always respond in a specific language, adopt a particular character, or focus on certain types of information.

---

By adjusting these configurations, you can tailor the Simple Slack Agent to better suit your needs and preferences. Remember to restart the bot application after making any changes to the `.env` file or `main.py`.
