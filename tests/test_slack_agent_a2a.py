import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
from collections import defaultdict

# Import the functions/classes to be tested from slack_agent.main
# This might require adjusting the Python path or how slack_agent is structured as a package.
# For this example, let's assume we can import `handle_app_mention` and necessary globals.
# If slack_agent.main is a script, we might need to refactor it or use more complex import methods.
# For now, let's assume direct import is possible for testing context.
# This often means ensuring 'agents' is in PYTHONPATH or running pytest from the root.

# To make this runnable, we'll mock the slack_agent.main dependencies.
# We need to patch them where they are looked up. If main.py uses 'from a2a.client import A2AClient',
# we patch 'agents.slack_agent.main.A2AClient'.

# Mock a subset of slack_agent.main's global state and dependencies
# These would normally be initialized in slack_agent.main
mock_app_client_token = "mock_slack_app_token"

# Path to the module/objects we need to mock
slack_main_path = "agents.slack_agent.main"

@pytest.fixture
def mock_slack_event_body(self):
    def _get_event(text, thread_ts="thread1", event_ts="event1"):
        return {
            "event": {
                "type": "message",
                "text": text,
                "user": "U123",
                "ts": event_ts,
                "channel": "C123",
                "thread_ts": thread_ts,
                "files": [] # Assuming no files for these tests
            },
            "client_msg_id": "some-uuid"
        }
    return _get_event

@pytest.fixture(autouse=True)
def mock_slack_agent_globals():
    # Mock globals that handle_app_mention might depend on from main.py
    # This is a simplified approach. A better way would be to refactor main.py
    # to make its dependencies injectable or its functions more self-contained.
    with patch(f"{slack_main_path}.SEARCH_AGENT_A2A_HOST", "testhost"),          patch(f"{slack_main_path}.SEARCH_AGENT_A2A_PORT", 1234),          patch(f"{slack_main_path}._messages", defaultdict(list)),          patch(f"{slack_main_path}._search_mode_state", defaultdict(bool)) as mock_search_state,          patch(f"{slack_main_path}.SYSTEM_PROMPT_RULES", []),          patch(f"{slack_main_path}.MEMORY_FEATURE_ENABLED", False),          patch(f"{slack_main_path}.app") as mock_app:
        # Mock app.client.token if download_and_encode_images were to be called
        mock_app.client.token = mock_app_client_token
        yield mock_search_state


@pytest.mark.asyncio
@patch(f"{slack_main_path}.send", new_callable=AsyncMock) # Mocks the send utility in slack_agent
@patch(f"{slack_main_path}.A2AClient") # Mocks the A2AClient class
async def test_slack_agent_enter_search_mode(mock_a2a_client_class, mock_send_func, mock_slack_event_body, mock_slack_agent_globals):
    from agents.slack_agent.main import handle_app_mention # Import here after mocks are set up

    mock_say = AsyncMock()
    mock_ack = AsyncMock()
    
    event_body = mock_slack_event_body("/search", thread_ts="t_search_enter")
    
    await handle_app_mention(body=event_body, say=mock_say, ack=mock_ack)
    
    mock_ack.assert_called_once()
    mock_send_func.assert_called_once_with(mock_say, "Entered search mode. Send your queries. Type '/search_exit' to leave.", "t_search_enter")
    assert mock_slack_agent_globals["t_search_enter"] is True # Check state was set

@pytest.mark.asyncio
@patch(f"{slack_main_path}.send", new_callable=AsyncMock)
@patch(f"{slack_main_path}.A2AClient")
async def test_slack_agent_exit_search_mode(mock_a2a_client_class, mock_send_func, mock_slack_event_body, mock_slack_agent_globals):
    from agents.slack_agent.main import handle_app_mention

    mock_say = AsyncMock()
    mock_ack = AsyncMock()
    
    # Enter search mode first
    mock_slack_agent_globals["t_search_exit"] = True
    
    event_body = mock_slack_event_body("/search_exit", thread_ts="t_search_exit")
    await handle_app_mention(body=event_body, say=mock_say, ack=mock_ack)
    
    mock_ack.assert_called_once()
    mock_send_func.assert_called_once_with(mock_say, "Exited search mode.", "t_search_exit")
    assert mock_slack_agent_globals["t_search_exit"] is False

@pytest.mark.asyncio
@patch(f"{slack_main_path}.send", new_callable=AsyncMock)
@patch(f"{slack_main_path}.A2AClient") # Mock the A2AClient class itself
async def test_slack_agent_perform_search_a2a_call_success(mock_a2a_client_class, mock_send_func, mock_slack_event_body, mock_slack_agent_globals):
    from agents.slack_agent.main import handle_app_mention
    
    # Configure the mock A2AClient instance that will be created
    mock_a2a_client_instance = AsyncMock()
    mock_a2a_client_instance.call_method.return_value = "Test search result" # Simulate successful string response
    mock_a2a_client_class.return_value = mock_a2a_client_instance # A2AClient() will return our mock instance

    mock_say = AsyncMock()
    mock_ack = AsyncMock()
    
    thread_id = "t_search_do"
    mock_slack_agent_globals[thread_id] = True # Set to search mode

    query = "what is A2A?"
    event_body = mock_slack_event_body(query, thread_ts=thread_id)
    
    await handle_app_mention(body=event_body, say=mock_say, ack=mock_ack)
    
    mock_ack.assert_called_once()
    
    # Check A2AClient instantiation and calls
    mock_a2a_client_class.assert_called_once_with(remote_host="testhost", remote_port=1234)
    mock_a2a_client_instance.connect.assert_called_once()
    mock_a2a_client_instance.call_method.assert_called_once_with("handle_search", query=query)
    mock_a2a_client_instance.disconnect.assert_called_once()
    
    # Check that search result is sent to Slack
    mock_send_func.assert_called_once_with(mock_say, f"Search results:\nTest search result", thread_id)

@pytest.mark.asyncio
@patch(f"{slack_main_path}.send", new_callable=AsyncMock)
@patch(f"{slack_main_path}.A2AClient")
async def test_slack_agent_perform_search_a2a_call_failure(mock_a2a_client_class, mock_send_func, mock_slack_event_body, mock_slack_agent_globals):
    from agents.slack_agent.main import handle_app_mention

    mock_a2a_client_instance = AsyncMock()
    mock_a2a_client_instance.call_method.side_effect = Exception("A2A connection error")
    mock_a2a_client_class.return_value = mock_a2a_client_instance

    mock_say = AsyncMock()
    mock_ack = AsyncMock()

    thread_id = "t_search_fail"
    mock_slack_agent_globals[thread_id] = True # Set to search mode
    
    query = "search that fails"
    event_body = mock_slack_event_body(query, thread_ts=thread_id)

    await handle_app_mention(body=event_body, say=mock_say, ack=mock_ack)
    
    mock_ack.assert_called_once()
    mock_a2a_client_class.assert_called_once_with(remote_host="testhost", remote_port=1234)
    mock_a2a_client_instance.connect.assert_called_once()
    mock_a2a_client_instance.call_method.assert_called_once_with("handle_search", query=query)
    # disconnect should still be called in finally block
    mock_a2a_client_instance.disconnect.assert_called_once() 
    
    mock_send_func.assert_called_once_with(mock_say, "Error communicating with search agent: A2A connection error", thread_id)

# Note: For these tests to run, you might need to:
# 1. Ensure the project root is in PYTHONPATH so `from agents.slack_agent.main import ...` works.
#    (e.g., by running pytest from the root directory of the project).
# 2. The global variables in slack_agent.main might need to be initialized or mocked appropriately
#    if they are accessed outside of functions or are more complex. The `@mock_slack_agent_globals`
#    fixture attempts to handle this for some key variables.
# 3. `AsyncApp` and `AsyncSocketModeHandler` are not directly tested here, only the `handle_app_mention` logic.
