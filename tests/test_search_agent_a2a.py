import asyncio
import os
import pytest
from a2a.client import A2AClient
from a2a.message import Message as A2AMessage # Assuming this might be needed, or for consistency

# Configuration for the search_agent A2A server
# These should match how the server is run, possibly from environment variables
SEARCH_AGENT_HOST = os.getenv("A2A_HOST", "localhost") # Assuming search_agent uses A2A_HOST
SEARCH_AGENT_PORT = int(os.getenv("A2A_PORT", "8080")) # Assuming search_agent uses A2A_PORT

@pytest.mark.asyncio
async def test_search_agent_a2a_connectivity_and_search():
    '''
    Tests basic A2A connection to the search_agent and a simple search query.
    This test expects the search_agent (A2A server) to be running separately.
    '''
    print(f"Attempting to connect to search_agent A2A server at {SEARCH_AGENT_HOST}:{SEARCH_AGENT_PORT}")
    client = A2AClient(remote_host=SEARCH_AGENT_HOST, remote_port=SEARCH_AGENT_PORT)

    query = "test query"
    response_content = None
    error = None

    try:
        await client.connect()
        assert client.is_connected(), "A2A client failed to connect to search_agent server."
        
        print(f"Connected. Sending search query: '{query}'")
        # Assuming 'handle_search' is the method exposed by SearchServiceAgent
        response_data = await client.call_method("handle_search", query=query)
        
        print(f"Received response_data: {type(response_data)} - {response_data}")

        if isinstance(response_data, A2AMessage):
            response_content = response_data.content
        elif isinstance(response_data, str):
            response_content = response_data
        elif isinstance(response_data, dict) and 'result' in response_data:
            response_content = response_data['result']
        else:
            response_content = str(response_data) # Fallback

        print(f"Extracted response content: {response_content}")
        assert response_content is not None, "Response content should not be None."
        assert isinstance(response_content, str), "Response content should be a string."
        # A very basic check; ideally, we'd know more about expected success/failure format
        assert "Error performing search:" not in response_content if "Error" not in query else True

    except Exception as e:
        error = e
        print(f"An error occurred during the A2A test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client.is_connected():
            await client.disconnect()
            print("Disconnected from search_agent A2A server.")

    assert error is None, f"A2A client test failed with error: {error}"
    # If the query was not designed to cause an error, then response_content should not be empty.
    if "Error" not in query:
        assert response_content, "Search result content should not be empty for a valid query."

# To run this test (example, assuming search_agent is running):
# pytest tests/test_search_agent_a2a.py 
#
# Note: This test requires the search_agent to be running and accessible.
# It also assumes the a2a-sdk's A2AClient API (connect, call_method, is_connected, disconnect).
# The actual search functionality (ToolCaller, Ollama, Playwright) within search_agent
# might have its own dependencies (like a running Ollama instance, network access for Playwright).
# For a CI environment, these external services would need to be available or mocked.
