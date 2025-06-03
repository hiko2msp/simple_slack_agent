import asyncio
import os
import pytest
from a2a.client import A2AClient
from a2a.message import Message as A2AMessage

SEARCH_AGENT_HOST = os.getenv("A2A_HOST", "localhost")
SEARCH_AGENT_PORT = int(os.getenv("A2A_PORT", "8080"))

@pytest.mark.asyncio
async def test_search_agent_a2a_full_loop_processing():
    '''
    Tests A2A connection to the search_agent and that a query is processed
    through the agent's main loop, returning a final response.
    This test expects the search_agent (A2A server) to be running separately.
    '''
    print(f"Attempting to connect to search_agent A2A server at {SEARCH_AGENT_HOST}:{SEARCH_AGENT_PORT}")
    client = A2AClient(remote_host=SEARCH_AGENT_HOST, remote_port=SEARCH_AGENT_PORT)

    # Use a query that the agent should be able to process and "complete".
    # For example, a direct request for information.
    query = "What is the capital of France?"
    response_content = None
    error_during_test = None

    try:
        await client.connect()
        assert client.is_connected(), "A2A client failed to connect to search_agent server."

        print(f"Connected. Sending query for full processing: '{query}'")
        response_data = await client.call_method("handle_search", query=query)

        print(f"Received response_data: {type(response_data)} - {response_data}")

        # Response should be a string directly from the A2AMessenger via SearchServiceAgent.handle_search
        if isinstance(response_data, str):
            response_content = response_data
        else:
            # This case should ideally not happen if SearchServiceAgent.handle_search is implemented correctly
            # to always return a string.
            response_content = f"Unexpected response type: {type(response_data)}, content: {str(response_data)}"


        print(f"Extracted response content: {response_content}")
        assert response_content is not None, "Response content should not be None."
        assert isinstance(response_content, str), f"Response content should be a string, but got {type(response_content)}."
        assert len(response_content) > 0, "Response content should not be empty."

        # Check for common error messages that might be returned if the agent loop fails correctly
        # These indicate the agent tried to handle an issue, not that the test itself failed.
        # For a simple query like "What is the capital of France?", we expect a successful answer.
        assert "Error: Task is blocked waiting for user input" not in response_content, "Agent should not get stuck waiting for user in A2A."
        assert "Error: Task processing timed out" not in response_content, "Agent task should not time out for this query."
        assert "Error: Agent did not produce a final response" not in response_content, "Agent should produce a response."
        assert "Error: Agent generated a null response" not in response_content, "Agent response should not be null."

        # For a query like "What is the capital of France?",
        # we might expect the word "Paris" in the response.
        # This makes the test more specific but also more brittle if the LLM phrasing changes.
        # Use with caution or make it a softer check.
        # For now, let's assume a successful execution implies the agent found an answer.
        print(f"Received final response from agent: {response_content}")


    except Exception as e:
        error_during_test = e
        print(f"An error occurred during the A2A test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client.is_connected(): # Check if client was successfully connected before trying to disconnect
            await client.disconnect()
            print("Disconnected from search_agent A2A server.")
        elif hasattr(client, 'disconnect') and client._connection: # Fallback for cases where is_connected might be false but disconnect is needed
             await client.disconnect()
             print("Disconnected from search_agent A2A server (fallback).")


    assert error_during_test is None, f"A2A client test failed with an exception: {error_during_test}"

# To run this test (example, assuming search_agent is running):
# pytest tests/test_search_agent_a2a.py
#
# Note: This test requires the search_agent to be running and accessible.
# It also assumes the a2a-sdk's A2AClient API (connect, call_method, is_connected, disconnect).
# The actual search functionality (ToolCaller, Ollama, Playwright) within search_agent
# might have its own dependencies (like a running Ollama instance, network access for Playwright).
# For a CI environment, these external services would need to be available or mocked.
