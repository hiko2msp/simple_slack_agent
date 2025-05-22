# Setup and Installation

This guide will walk you through the steps to set up and install the Simple Slack Agent.

## Prerequisites

Before you begin, ensure you have the following:

-   **Python:** Version 3.13 or higher. You can check your Python version by running `python --version`. If you don't have Python installed, download it from [python.org](https://www.python.org/).
-   **Slack Workspace Access:** You need access to a Slack workspace where you have permissions to install and configure an app.
-   **Ollama:** A running instance of Ollama. For download and setup instructions, please visit the official Ollama website: [https://ollama.com/](https://ollama.com/). Ensure the Ollama instance is reachable from the machine where you plan to run the bot.

## Installation Steps

1.  **Clone the Repository:**
    Open your terminal and clone the repository using the following command. Replace `<repository-url>` with the actual URL of the repository.
    ```bash
    git clone <repository-url>
    ```

2.  **Navigate to Project Directory:**
    Change your current directory to the newly cloned project folder:
    ```bash
    cd simple-slack-agent
    ```

3.  **Create and Activate Virtual Environment (Recommended):**
    It's highly recommended to use a virtual environment to manage project dependencies.
    ```bash
    python -m venv .venv
    ```
    Activate the virtual environment:
    -   On macOS and Linux:
        ```bash
        source .venv/bin/activate
        ```
    -   On Windows:
        ```bash
        .venv\Scripts\activate
        ```

4.  **Install Dependencies:**
    This project uses `uv` for fast dependency management. The dependencies are listed in `pyproject.toml`, and a `uv.lock` file is provided for consistent installs.
    *   **Using `uv` (Recommended):**
        If you don't have `uv` installed, you can typically install it via pip: `pip install uv`.
        Once `uv` is installed, run the following command in the project root to install dependencies:
        ```bash
        uv pip sync
        ```
    *   **Alternative using pip with a generated `requirements.txt`:**
        If you prefer to use pip directly with a `requirements.txt` file, you can generate one from the `uv.lock` file (or `pyproject.toml`) using `uv`:
        ```bash
        uv pip freeze > requirements.txt
        ```
        Then, install the dependencies using pip:
        ```bash
        pip install -r requirements.txt
        ```
        Alternatively, you can often install directly from `pyproject.toml` with a modern version of pip:
        ```bash
        pip install .
        ```

5.  **Configure Environment Variables:**
    The application uses a `.env` file to manage sensitive credentials and configuration settings.
    *   **Create the `.env` file:**
        Copy the example environment file to a new file named `.env`:
        ```bash
        cp .env.example .env
        ```
    *   **Edit the `.env` file** with your specific details:
        *   `SLACK_ACCESS_TOKEN`: This is your Slack app's Bot User OAuth Token. You can find this token in your Slack app's configuration page under the "OAuth & Permissions" section. It typically starts with `xoxb-`.
        *   `SLACK_APP_TOKEN`: This is an App-Level Token that allows the application to use Slack's Socket Mode. You can generate this token from your Slack app's "Basic Information" page, under the "App-Level Tokens" section. Ensure the token has the `connections:write` scope. It typically starts with `xapp-`.
        *   `OLLAMA_HOST`: The full URL of your running Ollama instance. The default value if Ollama is running on the same machine is `http://localhost:11434`. If Ollama is running on a different host or port, adjust this value accordingly.

## Troubleshooting Tips (Optional Placeholder)
Common issues might include incorrect Slack tokens, Ollama not being reachable, or firewall configurations blocking the connection. Ensure your Ollama instance is running and accessible from the machine where the bot is running. Double-check that the Slack tokens have the correct scopes and are copied accurately into the `.env` file.

---

After completing these steps, you should be ready to [run the application](./usage.md#running-the-application).
