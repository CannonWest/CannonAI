"""
Logging utilities for the OpenAI Chat application.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional, Any

from src.utils.constants import DATA_DIR

# Create a logs directory inside the data directory
LOGS_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Default log file path
DEFAULT_LOG_FILE = os.path.join(LOGS_DIR, "openai_chat.log")

# Default log format
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DETAILED_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

# Default logging configuration
DEFAULT_LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': DEFAULT_LOG_FORMAT,
        },
        'detailed': {
            'format': DETAILED_LOG_FORMAT,
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
        },
        'file': {
            'level': 'DEBUG',
            'formatter': 'detailed',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': DEFAULT_LOG_FILE,
            'maxBytes': 52428800,  # 50MB
            'backupCount': 10,
            'encoding': 'utf8',
        },
    },
    'loggers': {
        '': {  # Root logger
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'openai': {  # OpenAI API logger
            'level': 'INFO',
        },
        'PyQt6': {  # PyQt logger
            'level': 'WARNING',
        },
    },
}


def configure_logging(config: Optional[Dict[str, Any]] = None) -> None:
    """
    Configure logging for the application.

    Args:
        config: Optional custom logging configuration. If None, default config is used.
    """
    from logging.config import dictConfig

    # Use provided config or default
    logging_config = config or DEFAULT_LOGGING_CONFIG

    # Apply the configuration
    dictConfig(logging_config)

    # Log the startup information
    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully")
    logger.debug(f"Log files will be stored in: {LOGS_DIR}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.

    Args:
        name: Name for the logger, typically __name__ of the calling module

    Returns:
        A configured logger instance
    """
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, exc: Exception, message: str = "An exception occurred:") -> None:
    """
    Log an exception with appropriate level and traceback.

    Args:
        logger: The logger instance to use
        exc: The exception to log
        message: Optional message to include with the exception
    """
    logger.exception(f"{message} {str(exc)}")


def monitor_stack_depth(max_depth=500):
    """
    Decorator to monitor stack depth to help catch potential stack overflow issues.

    Usage:
        @monitor_stack_depth(max_depth=50)
        def my_recursive_function(...):
            ...
    """
    import sys
    import traceback
    import functools

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            frame = sys._getframe()
            depth = 0

            # Count stack frames
            while frame:
                depth += 1
                frame = frame.f_back

                # Check if we're approaching a dangerous depth
                if depth > max_depth:
                    # Get the stack trace
                    stack_trace = traceback.format_stack()
                    # Log warning with stack trace
                    print(f"WARNING: Deep recursion detected in {func.__name__} - depth {depth} exceeds {max_depth}")
                    print("Stack trace:")
                    for line in stack_trace[-20:]:  # Print the last 20 frames
                        print(line.strip())
                    # Return early to prevent stack overflow
                    return None

            # Call the original function
            return func(*args, **kwargs)

        return wrapper

    return decorator
