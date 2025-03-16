"""
Shared fixtures and configurations for pytest.
"""

import os
import sys
import pytest
import tempfile
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv

# Find the project root directory and .env file
if os.path.basename(os.getcwd()) == "tests":
    # We're in the tests directory, .env is one level up
    project_root = os.path.dirname(os.getcwd())
else:
    # We're in the project root or elsewhere
    project_root = os.getcwd()

# Try to load .env from possible locations
dotenv_paths = [
    os.path.join(project_root, '.env'),               # project root
    os.path.join(os.path.dirname(project_root), '.env')  # parent directory
]

for dotenv_path in dotenv_paths:
    if os.path.exists(dotenv_path):
        print(f"Loading environment variables from: {dotenv_path}")
        load_dotenv(dotenv_path=dotenv_path)
        break
else:
    print("Warning: No .env file found! API tests may fail.")

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.constants import DEFAULT_PARAMS
from src.models.db_conversation import DBMessageNode


@pytest.fixture
def sample_messages():
    """Sample messages for testing."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, this is a test message."}
    ]


@pytest.fixture
def default_settings():
    """Default settings for testing using real API key from environment."""
    # Get the real API key from environment variable
    api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        print("WARNING: No OpenAI API key found in environment variables!")
        print("Set your API key in the .env file or environment variables.")

    return {
        "api_key": api_key,  # Use real API key from environment
        "model": "gpt-4o",
        "temperature": 0.7,
        "max_output_tokens": 1024,
        "top_p": 1.0,
        "stream": True,
        "api_type": "responses"
    }


@pytest.fixture
def mock_signal_receiver():
    """Mock object to receive signals."""
    class SignalReceiver:
        def __init__(self):
            self.received_messages = []
            self.received_chunks = []
            self.received_errors = []
            self.received_usage_info = []
            self.received_system_info = []
            self.worker_finished_called = False
            self.thinking_steps = []
            self.reasoning_steps = []
            self.completion_ids = []

        def on_message_received(self, message):
            self.received_messages.append(message)

        def on_chunk_received(self, chunk):
            self.received_chunks.append(chunk)

        def on_error_occurred(self, error):
            self.received_errors.append(error)

        def on_usage_info(self, info):
            self.received_usage_info.append(info)

        def on_system_info(self, info):
            self.received_system_info.append(info)

        def on_worker_finished(self):
            self.worker_finished_called = True

        def on_thinking_step(self, step, content):
            self.thinking_steps.append((step, content))

        def on_reasoning_steps(self, steps):
            self.reasoning_steps.append(steps)

        def on_completion_id(self, id):
            self.completion_ids.append(id)

    return SignalReceiver()


@pytest.fixture
def temp_test_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def sample_message_node():
    """Sample message node for testing."""
    node = MagicMock(spec=DBMessageNode)
    node.id = "test-node-id"
    node.role = "assistant"
    node.content = "This is a test response."
    node.parent_id = "parent-node-id"
    node.timestamp = "2023-01-01T12:00:00"
    node.model_info = {"model": "gpt-4o"}
    node.parameters = {"temperature": 0.7}
    node.token_usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    node.attached_files = []
    node.children = []

    return node


@pytest.fixture
def temp_db_dir():
    """Create a temporary directory for database files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test.db")

        # Patch database file path
        with patch('src.models.db_manager.DATABASE_FILE', db_path):
            yield db_path


@pytest.fixture
def qapp():
    """Fixture to create a QApplication instance for UI tests."""
    # Only import Qt if the fixture is used
    from PyQt6.QtWidgets import QApplication

    # Only create a QApplication if it doesn't already exist
    if not QApplication.instance():
        app = QApplication([])
        yield app
        app.quit()
    else:
        yield QApplication.instance()


@pytest.fixture
def enable_qtest():
    """Enable QtTest functionality for UI testing."""
    try:
        from PyQt6 import QtTest
        return QtTest.QTest
    except ImportError:
        pytest.skip("QtTest not available")


# Define test categories for easier filtering
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: mark a test as a unit test")
    config.addinivalue_line("markers", "integration: mark a test as an integration test")
    config.addinivalue_line("markers", "api: mark a test as an API test")
    config.addinivalue_line("markers", "ui: mark a test as a UI test")
    config.addinivalue_line("markers", "slow: mark a test as slow running")


# Skip UI tests if running headless
def pytest_collection_modifyitems(config, items):
    """Skip UI tests if running in a headless environment."""
    # Check for CI environment or specific skipping flag
    skip_ui = (
        os.environ.get('CI', 'false').lower() == 'true' or
        os.environ.get('SKIP_UI_TESTS', 'false').lower() == 'true'
    )

    # If we should skip UI tests
    if skip_ui:
        skip_ui_marker = pytest.mark.skip(reason="UI tests skipped in headless environment")
        for item in items:
            if "ui" in item.keywords:
                item.add_marker(skip_ui_marker)