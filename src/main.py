#!/usr/bin/env python3
"""
Main entry point for the OpenAI Chat application.
"""

import sys
import os
import logging
from PyQt6.QtWidgets import QApplication

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("openai_chat.log"),
        logging.StreamHandler()
    ]
)
# Import the main application components
from src.ui import MainWindow

from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()


def main():
    """
    Main application entry point.
    """
    try:
        # Create the Qt application
        app = QApplication(sys.argv)
        app.setStyle("Fusion")  # Use Fusion style for consistent cross-platform look

        # Create and show the main window
        window = MainWindow()
        window.show()

        # Run the application event loop
        return app.exec()
    except Exception as e:
        logging.error(f"Application error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())