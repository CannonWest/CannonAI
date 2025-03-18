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
    Main application entry point with improved error handling.
    """
    try:
        # Create the Qt application
        app = QApplication(sys.argv)
        app.setStyle("Fusion")  # Use Fusion style for consistent cross-platform look

        logger.debug("Created Qt application")

        # Register shutdown handler to run before application exit
        app.aboutToQuit.connect(shutdown_application)

        # Ensure the database directory exists
        try:
            from src.utils import DATABASE_DIR
            import os
            os.makedirs(DATABASE_DIR, exist_ok=True)
            logger.debug(f"Ensured database directory exists: {DATABASE_DIR}")
        except Exception as e:
            logger.error(f"Error creating database directory: {e}")

        # Create and show the main window
        try:
            window = MainWindow()
            window.show()
            logger.info("Application UI initialized and displayed")
        except Exception as window_error:
            logger.error(f"Error creating main window: {window_error}", exc_info=True)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(
                None,
                "Error Starting Application",
                f"Failed to initialize the application: {window_error}\n\nThe application will now exit."
            )
            return 1

        # Run the application event loop
        return app.exec()
    except Exception as e:
        logger.critical(f"Application failed to start: {e}", exc_info=True)
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None,
            "Fatal Error",
            f"A critical error occurred during startup: {e}\n\nThe application will now exit."
        )
        return 1


def shutdown_application():
    """Clean shutdown for the application to ensure all resources are released"""
    logger.info("Starting application shutdown")

    # Cleanup database connections
    try:
        from src.models.db_manager import DatabaseManager
        # Get the global instance if one exists (without creating a new one)
        db_manager = getattr(DatabaseManager, '_instance', None)
        if db_manager:
            logger.info("Shutting down database manager")
            db_manager.shutdown()
    except Exception as e:
        logger.error(f"Error shutting down database manager: {e}")

    # Release any remaining file resources
    try:
        import gc
        gc.collect()
    except Exception as e:
        logger.error(f"Error during garbage collection: {e}")

    logger.info("Application shutdown complete")

if __name__ == "__main__":
    sys.exit(main())
