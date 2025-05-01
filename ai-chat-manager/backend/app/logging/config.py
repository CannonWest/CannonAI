"""
Advanced logging configuration for the AI Chat Manager application.

This module provides a comprehensive logging setup with:
1. Multiple log files for different components
2. Structured log directory organization
3. Special handling for API errors
4. Configurable log levels
5. Log rotation
6. Color-coded console output
"""
import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Dict, Optional, Union

# Define log levels
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# ANSI color codes for colored console output
COLORS = {
    "RESET": "\033[0m",
    "BLACK": "\033[30m",
    "RED": "\033[31m",
    "GREEN": "\033[32m",
    "YELLOW": "\033[33m",
    "BLUE": "\033[34m",
    "MAGENTA": "\033[35m",
    "CYAN": "\033[36m",
    "WHITE": "\033[37m",
    "BOLD": "\033[1m",
    "UNDERLINE": "\033[4m",
}

# Log level colors
LEVEL_COLORS = {
    "DEBUG": COLORS["BLUE"],
    "INFO": COLORS["GREEN"],
    "WARNING": COLORS["YELLOW"],
    "ERROR": COLORS["RED"],
    "CRITICAL": COLORS["BOLD"] + COLORS["RED"],
}

class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored console output"""
    
    def format(self, record):
        levelname = record.levelname
        if levelname in LEVEL_COLORS:
            colored_levelname = f"{LEVEL_COLORS[levelname]}{levelname}{COLORS['RESET']}"
            record.levelname = colored_levelname
        return super().format(record)


class ApiCallFilter(logging.Filter):
    """Filter to capture only API call logs"""
    
    def filter(self, record):
        return hasattr(record, 'api_call') and record.api_call


def get_log_directory() -> Path:
    """
    Get the log directory based on environment.
    
    Returns:
        Path: The log directory path
    """
    # Base directories
    default_log_dir = Path(__file__).parents[3] / "logs"
    env_log_dir = os.environ.get("LOG_DIR")
    
    # Use environment variable if set, otherwise use default
    if env_log_dir:
        log_dir = Path(env_log_dir)
    else:
        log_dir = default_log_dir
    
    # Create log directory structure
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories for different log types
    (log_dir / "api").mkdir(exist_ok=True)
    (log_dir / "errors").mkdir(exist_ok=True)
    (log_dir / "database").mkdir(exist_ok=True)
    (log_dir / "websocket").mkdir(exist_ok=True)
    (log_dir / "general").mkdir(exist_ok=True)
    
    return log_dir


def setup_application_logging(
    default_level: str = "INFO",
    console_output: bool = True,
    colored_console: bool = True,
    config_file: Optional[str] = None,
) -> None:
    """
    Set up application-wide logging configuration.
    
    Args:
        default_level: Default logging level
        console_output: Whether to output logs to console
        colored_console: Whether to use colored output in console
        config_file: Optional logging config file
    """
    # Get log level from environment
    log_level_name = os.environ.get("LOG_LEVEL", default_level).upper()
    log_level = LOG_LEVELS.get(log_level_name, logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers to avoid duplicates
    if root_logger.handlers:
        root_logger.handlers.clear()
    
    # Set up console logging if enabled
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        
        if colored_console:
            fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
            formatter = ColoredFormatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        else:
            fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
            formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
            
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)
    
    # Get log directory
    log_dir = get_log_directory()
    
    # Set up general application log file
    general_log_path = log_dir / "general" / "app.log"
    file_handler = RotatingFileHandler(
        general_log_path,
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=10
    )
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(log_level)
    root_logger.addHandler(file_handler)
    
    # Set up error log file
    error_log_path = log_dir / "errors" / "error.log"
    error_handler = RotatingFileHandler(
        error_log_path,
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=10
    )
    error_handler.setFormatter(file_formatter)
    error_handler.setLevel(logging.ERROR)
    root_logger.addHandler(error_handler)
    
    # Set up API log file with special filter
    api_log_path = log_dir / "api" / "api_calls.log"
    api_handler = RotatingFileHandler(
        api_log_path,
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=10
    )
    api_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(provider)s | %(endpoint)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    api_handler.setFormatter(api_formatter)
    api_handler.addFilter(ApiCallFilter())
    api_handler.setLevel(logging.INFO)
    root_logger.addHandler(api_handler)
    
    # Log startup information
    logging.info(f"Logging initialized with level: {log_level_name}")
    logging.info(f"Log files located at: {log_dir}")


def get_logger(
    name: str, 
    log_file: Optional[str] = None,
    level: Optional[str] = None
) -> logging.Logger:
    """
    Get a logger with optional dedicated log file.
    
    Args:
        name: Logger name
        log_file: Optional dedicated log file for this logger
        level: Optional specific level for this logger
        
    Returns:
        Logger instance
    """
    # Get logger
    logger = logging.getLogger(name)
    
    # Set specific level if provided
    if level:
        level_value = LOG_LEVELS.get(level.upper(), logging.INFO)
        logger.setLevel(level_value)
    
    # Add dedicated file handler if specified
    if log_file:
        log_dir = get_log_directory()
        category = name.split(".")[-1]
        
        # Determine appropriate subdirectory
        if "api" in name:
            subdir = "api"
        elif "db" in name or "database" in name:
            subdir = "database"
        elif "websocket" in name:
            subdir = "websocket"
        else:
            subdir = "general"
            
        full_path = log_dir / subdir / log_file
        
        handler = RotatingFileHandler(
            full_path,
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=5
        )
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def log_api_call(
    logger: logging.Logger,
    provider: str,
    endpoint: str,
    request_data: Optional[dict] = None,
    response_data: Optional[dict] = None,
    error: Optional[Exception] = None,
    level: str = "INFO",
    duration_ms: Optional[float] = None,
) -> None:
    """
    Log API call with structured information.
    
    Args:
        logger: Logger instance
        provider: API provider (e.g., 'openai', 'anthropic')
        endpoint: API endpoint called
        request_data: Optional request payload
        response_data: Optional response data
        error: Optional exception if the call failed
        level: Log level to use
        duration_ms: Optional API call duration in milliseconds
    """
    log_level = LOG_LEVELS.get(level.upper(), logging.INFO)
    
    # Create record with extra data
    if error:
        message = f"API call failed: {str(error)}"
        log_level = logging.ERROR
    elif duration_ms:
        message = f"API call completed in {duration_ms:.2f}ms"
    else:
        message = "API call executed"
    
    # Create extra context for the log record
    extra = {
        "api_call": True,
        "provider": provider,
        "endpoint": endpoint,
    }
    
    # Log with extra context
    logger.log(log_level, message, extra=extra)
    
    # For debug level, add detailed request/response info
    if logger.isEnabledFor(logging.DEBUG):
        if request_data:
            # Sanitize sensitive data
            safe_request = sanitize_sensitive_data(request_data)
            logger.debug(f"Request: {safe_request}", extra=extra)
        
        if response_data and not error:
            logger.debug(f"Response: {response_data}", extra=extra)


def sanitize_sensitive_data(data: dict) -> dict:
    """Remove sensitive information like API keys from log data."""
    if not isinstance(data, dict):
        return data
        
    sanitized = data.copy()
    
    # List of sensitive field names
    sensitive_fields = [
        "api_key", "apikey", "key", "secret", "password", "token",
        "authorization", "auth", "access_token", "refresh_token"
    ]
    
    # Replace sensitive values with "[REDACTED]"
    for key, value in data.items():
        key_lower = key.lower()
        
        # Check if this is a sensitive field
        if any(sensitive in key_lower for sensitive in sensitive_fields):
            if isinstance(value, str) and value:  # Only redact non-empty strings
                sanitized[key] = "[REDACTED]"
        
        # Recursively sanitize nested dictionaries
        elif isinstance(value, dict):
            sanitized[key] = sanitize_sensitive_data(value)
        
        # Sanitize list items if they are dictionaries
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_sensitive_data(item) if isinstance(item, dict) else item
                for item in value
            ]
    
    return sanitized


# Example implementation for timing API calls
class ApiCallTimer:
    """Context manager for timing API calls"""
    
    def __init__(self, logger, provider, endpoint, request_data=None):
        self.logger = logger
        self.provider = provider
        self.endpoint = endpoint
        self.request_data = request_data
        self.start_time = None
        self.response_data = None
        self.error = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        
        log_api_call(
            logger=self.logger,
            provider=self.provider,
            endpoint=self.endpoint,
            request_data=self.request_data,
            response_data=self.response_data,
            error=exc_val,
            duration_ms=duration_ms
        )
        
        # Don't suppress the exception
        return False
    
    def set_response(self, response_data):
        """Set response data to be logged"""
        self.response_data = response_data
