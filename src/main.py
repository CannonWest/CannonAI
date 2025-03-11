#!/usr/bin/env python3
"""
Main entry point for the OpenAI Chat application.
"""

import sys
import os
from PyQt6.QtWidgets import QApplication

# Import logging utilities first to set up logging early
from src.utils.logging_utils import configure_logging, get_logger

# Configure logging for the application
configure_logging()

# Get a logger for this module
logger = get_logger(__name__)

# Import the main application components
from src.ui import MainWindow
from dotenv import load_dotenv

try:
    # Load environment variables from .env file if it exists
    load_dotenv()
    if os.environ.get("OPENAI_API_KEY"):
        logger.info("Loaded API key from environment")
    else:
        logger.warning("No API key found in environment")
except Exception as e:
    logger.warning(f"Error loading .env file: {e}")


def main():
    """
    Main application entry point.
    """
    try:
        # Create the Qt application
        app = QApplication(sys.argv)
        app.setStyle("Fusion")  # Use Fusion style for consistent cross-platform look

        logger.debug("Created Qt application")

        # Create and show the main window
        window = MainWindow()
        window.show()

        logger.info("Application UI initialized and displayed")

        # Run the application event loop
        return app.exec()
    except Exception as e:
        logger.critical(f"Application failed to start: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
