"""
Logger configuration for the application.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
import os

def setup_logger(name: str = None, log_file: str = None, level=None):
    """
    Set up a logger with console and file handlers.
    
    Args:
        name: Logger name (defaults to root logger)
        log_file: Path to log file (defaults to logs/app.log)
        level: Logging level
        
    Returns:
        Configured logger
    """
    name = name or __name__
    log_file = log_file or "logs/app.log"
    
    # Get log level from environment variable or use default
    if level is None:
        log_level_str = os.environ.get("LOG_LEVEL", "INFO")
        level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)
    
    # Create file handler
    try:
        # Ensure log directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5
        )
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Could not set up file logging: {e}")
    
    return logger
