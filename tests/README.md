# Testing Framework for OpenAI Chat Application

This document describes the testing framework for the OpenAI Chat application, including the testing structure, setup, and guidelines for creating new tests.

## Overview

The testing framework uses pytest and is organized into the following categories:

1. **Unit Tests**: Test individual components in isolation
2. **Integration Tests**: Test interactions between components
3. **API Tests**: Test OpenAI API communication
4. **UI Tests**: Test PyQt6 components and interactions

## Test Directory Structure

```
tests/
├── __init__.py
├── conftest.py                     # Shared pytest fixtures
├── unit/
│   ├── __init__.py
│   ├── test_settings.py            # Test SettingsManager
│   ├── test_api_worker.py          # Test OpenAIAPIWorker
│   ├── test_thread_manager.py      # Test OpenAIThreadManager
│   ├── test_db_manager.py          # Test DatabaseManager
│   ├── test_db_conversation.py     # Test DBConversationTree and DBMessageNode
│   ├── test_db_conversation_manager.py  # Test DBConversationManager
│   └── test_utils.py               # Test utility functions
├── integration/
│   ├── __init__.py
│   ├── test_api_integration.py     # Test API to database flow
│   └── test_settings_integration.py # Test settings effect on API calls
├── api/
│   ├── __init__.py
│   ├── test_openai_response.py     # Test Response API
│   ├── test_openai_chat.py         # Test Chat Completions API
│   └── test_error_handling.py      # Test API error conditions
└── ui/
    ├── __init__.py
    ├── test_components.py          # Test UI components
    ├── test_graph_view.py          # Test ConversationGraphView
    ├── test_conversation_tab.py    # Test ConversationBranchTab
    └── test_main_window.py         # Test MainWindow
```

## Running Tests

You can run tests using the `run_tests.py` script:

```bash
# Run all tests
python run_tests.py --all

# Run only unit tests
python run_tests.py --unit

# Run only UI tests
python run_tests.py --ui

# Run with coverage report
python run_tests.py --all --coverage

# Run tests matching a pattern
python run_tests.py --pattern test_api_worker
```

Alternatively, you can use pytest directly:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_settings.py

# Run with coverage
pytest --cov=src --cov-report=html
```

## Test Fixtures

Common fixtures are defined in `conftest.py` and include:

- `sample_messages`: Sample conversation messages
- `default_settings`: Default application settings
- `mock_signal_receiver`: Mock object to receive signals
- `temp_test_dir`: Temporary directory for test files
- `sample_message_node`: Sample message node
- `temp_db_dir`: Temporary directory for database files
- `qapp`: QApplication instance for UI tests
- `enable_qtest`: Enable QtTest functionality for UI testing

## Writing New Tests

### Guidelines for Writing Tests

1. **Test Isolation**: Each test should be independent and not rely on the state from previous tests.
2. **Use Fixtures**: Use fixtures from `conftest.py` for common test setup.
3. **Mock External Dependencies**: Use mocks for external APIs and libraries.
4. **Test Categories**: Use appropriate test category based on what you're testing.

### Example: Writing a Unit Test

```python
import pytest
from unittest.mock import patch, MagicMock

def test_some_function():
    # Arrange: Set up test data and mocks
    test_data = "test"
    mock_dependency = MagicMock()
    
    # Act: Call the function being tested
    with patch('module.dependency', mock_dependency):
        result = function_under_test(test_data)
    
    # Assert: Verify expected behavior
    assert result == expected_result
    mock_dependency.assert_called_once_with(test_data)
```

### Example: Writing a UI Test

```python
def test_ui_component(qapp):
    # Create the widget
    widget = MyWidget()
    
    # Set initial state
    widget.setValue("test")
    
    # Trigger an action
    widget.button.click()
    
    # Verify expected result
    assert widget.result() == "expected output"
```

## Test Coverage

The test framework includes coverage reporting via pytest-cov. To generate a coverage report:

```bash
python run_tests.py --all --coverage
```

This will generate an HTML report in the `htmlcov` directory that shows which lines of code are covered by tests.

## Continuous Integration

The test suite is designed to run in CI environments. UI tests are automatically skipped in headless environments or when the `SKIP_UI_TESTS` environment variable is set to `true`.

## Dependencies

The test framework requires:

- pytest
- pytest-cov (for coverage reporting)
- pytest-qt (for PyQt testing)
- pytest-html (optional, for HTML reports)

To install all dependencies:

```bash
pip install pytest pytest-cov pytest-qt pytest-html
```
