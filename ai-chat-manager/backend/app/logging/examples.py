"""
Example usage of the logging system for the AI Chat Manager.

This module demonstrates how to properly use the logging system
for various scenarios, including API calls, database operations,
and general application events.
"""
import logging
import time
from app.logging import get_logger
from app.logging.config import log_api_call, ApiCallTimer


def example_log_api_call():
    """Example of how to log an API call"""
    # Get a logger for API interactions
    logger = get_logger("app.api.openai")
    
    # Example 1: Basic API call logging
    log_api_call(
        logger=logger,
        provider="openai",
        endpoint="/v1/chat/completions",
        request_data={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "api_key": "sk-123456789"  # This will be automatically redacted
        }
    )
    
    # Example 2: API call with an error
    try:
        # Simulate an API call that fails
        raise ConnectionError("API server not responding")
    except Exception as e:
        log_api_call(
            logger=logger,
            provider="openai",
            endpoint="/v1/chat/completions",
            error=e
        )
    
    # Example 3: Using the context manager for timing
    with ApiCallTimer(logger, "anthropic", "/v1/complete") as timer:
        # Simulate API call
        time.sleep(0.5)  # Pretend request takes 500ms
        
        # Set the response data
        timer.set_response({
            "completion": "Hello, how can I help you today?",
            "model": "claude-3-opus-20240229"
        })


def example_general_logging():
    """Example of general application logging"""
    # Get loggers for different components
    app_logger = get_logger("app.core")
    db_logger = get_logger("app.database", log_file="database_operations.log")
    ws_logger = get_logger("app.websocket", log_file="websocket.log")
    
    # Log different levels of messages
    app_logger.debug("Starting application initialization")
    app_logger.info("Application started successfully")
    
    # Log database operations
    db_logger.info("Connecting to database")
    try:
        # Simulate a database operation that fails
        raise ValueError("Invalid connection string")
    except Exception as e:
        db_logger.error(f"Database connection failed: {str(e)}", exc_info=True)
    
    # Log websocket events
    ws_logger.info("WebSocket connection established with client 123")
    ws_logger.warning("Client 123 sending messages too rapidly, throttling")


if __name__ == "__main__":
    # This would typically be done in the main application entry point
    from app.logging import setup_application_logging
    
    # Initialize logging system
    setup_application_logging(default_level="DEBUG", colored_console=True)
    
    # Run examples
    example_log_api_call()
    example_general_logging()
