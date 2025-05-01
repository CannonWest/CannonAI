# AI Chat Manager - Advanced Logging System

This document provides an overview of the AI Chat Manager's logging system and how to use it effectively in your code.

## Overview

The logging system provides a structured, intuitive way to log events, errors, and API calls in your application. Key features include:

- **Organized Log Directory Structure**: Separate directories for different types of logs
- **Special API Call Logging**: Detailed tracking of API requests and responses
- **Automatic Sensitive Data Redaction**: API keys and other sensitive information are automatically hidden in logs
- **Color-Coded Console Output**: Makes log messages easier to read
- **Log Rotation**: Prevents log files from growing too large

## Log Directory Structure

Logs are organized into the following directories:

- `/logs/api/` - API call logs
- `/logs/errors/` - Error logs (all ERROR and CRITICAL level messages)
- `/logs/database/` - Database operation logs
- `/logs/websocket/` - WebSocket logs
- `/logs/general/` - General application logs

## Basic Usage

### Setting Up Application Logging

In your application's startup code (e.g., `main.py`):

```python
from app.logging import setup_application_logging

# Initialize logging system
setup_application_logging(
    default_level="INFO",  # or "DEBUG", "WARNING", "ERROR", "CRITICAL"
    console_output=True,   # Whether to output logs to console
    colored_console=True   # Use colored console output
)
```

### Getting a Logger

In your module:

```python
from app.logging import get_logger

# Get a logger for your module
logger = get_logger(__name__)

# You can now use standard logging methods
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical message")
```

## Advanced Features

### API Call Logging

For logging API calls with detailed information, use the `ApiClient` from `app.utils.api_client`:

```python
from app.utils.api_client import create_api_client

# Create an API client for a specific provider
client = create_api_client("openai", api_key)

# Make a request - all logging is handled automatically
response = client.request(
    method="POST",
    endpoint="/v1/chat/completions",
    json_data={...}
)
```

### Manual API Call Logging

If you need to log API calls manually:

```python
from app.logging import get_logger
from app.logging.config import log_api_call

logger = get_logger("app.api.openai")

# Log an API call
log_api_call(
    logger=logger,
    provider="openai",
    endpoint="/v1/chat/completions",
    request_data={...},  # Optional
    response_data={...},  # Optional
    error=exception,     # Optional, if the call failed
    duration_ms=200      # Optional, call duration in milliseconds
)
```

### Using the API Call Timer

For timing API calls:

```python
from app.logging.config import ApiCallTimer
from app.logging import get_logger

logger = get_logger("app.api.openai")

with ApiCallTimer(logger, "openai", "/v1/chat/completions") as timer:
    # Make your API call
    response = requests.post(url, json=data)
    
    # Set the response data to be logged
    timer.set_response(response.json())
```

## Log Files

All logs are automatically written to the appropriate files. By default, the main log files are:

- `logs/general/app.log` - General application logs
- `logs/errors/error.log` - Error and critical logs
- `logs/api/api_calls.log` - API call logs

These files are automatically rotated when they reach 10MB in size, and up to 10 backup files are kept.

## Configuration Options

You can customize the logging system by:

1. Setting the `LOG_LEVEL` environment variable
2. Setting the `LOG_DIR` environment variable to change the log directory
3. Passing parameters to `setup_application_logging()`

For specific components, you can create dedicated log files:

```python
logger = get_logger("app.api.openai", log_file="openai_api.log")
```

This will create a special log file in the appropriate subdirectory based on the logger name.
