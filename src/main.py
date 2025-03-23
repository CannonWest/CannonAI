# src/main.py

import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtCore import QUrl, QObject, pyqtSlot

# Import logging utilities first to set up logging early
from src.utils.logging_utils import configure_logging, get_logger

# Configure logging for the application
configure_logging()

# Get a logger for this module
logger = get_logger(__name__)

# Import utilities for async support
from src.utils.qasync_bridge import install as install_qasync
from src.utils.qml_bridge import QmlBridge

# Import ViewModels
from src.viewmodels.reactive_conversation_viewmodel import ReactiveConversationViewModel
from src.viewmodels.settings_viewmodel import SettingsViewModel

# Import services
from src.services.db_service import ConversationService
from src.services.api_service import ApiService

# Import other utilities
from dotenv import load_dotenv


class Application(QObject):
    """Main application class"""

    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("OpenAI Chat Interface")
        self.app.setOrganizationName("OpenAI")
        self.app.setOrganizationDomain("openai.com")

        # Load environment variables
        self._load_env()

        # Initialize async support
        self.event_loop = install_qasync(self.app)

        # Initialize services
        self.initialize_services()

        # Initialize QML engine
        self.engine = QQmlApplicationEngine()
        self.qml_bridge = QmlBridge(self.engine)

        # Create and register ViewModels
        self.initialize_viewmodels()

        # Load main QML file
        self.load_qml()

    def _load_env(self):
        """Load environment variables from .env file"""
        try:
            # Load environment variables from .env file if it exists
            load_dotenv()
            if os.environ.get("OPENAI_API_KEY"):
                logger.info("Loaded API key from environment")
            else:
                logger.warning("No API key found in environment")
        except Exception as e:
            logger.warning(f"Error loading .env file: {e}")

    def initialize_services(self):
        """Initialize application services"""
        # Database service for conversation storage
        self.db_service = ConversationService()

        # API service for OpenAI interaction
        self.api_service = ApiService()

        # Set API key from environment if available
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            self.api_service.set_api_key(api_key)

    def initialize_viewmodels(self):
        """Initialize and register ViewModels"""
        # Create ViewModels
        self.conversation_vm = ReactiveConversationViewModel()
        self.settings_vm = SettingsViewModel()

        # Initialize settings ViewModel with API service
        self.settings_vm.initialize(self.api_service)

        # Connect ViewModels to services
        self.conversation_vm.api_service = self.api_service

        # Register ViewModels with QML
        self.qml_bridge.register_context_property("conversationViewModel", self.conversation_vm)
        self.qml_bridge.register_context_property("settingsViewModel", self.settings_vm)

    def load_qml(self):
        """Load the main QML file"""
        # Get the path to the QML file
        qml_path = os.path.join(os.path.dirname(__file__), "views", "qml", "MainWindow.qml")

        # Check if the file exists
        if not os.path.exists(qml_path):
            logger.critical(f"QML file not found: {qml_path}")
            raise FileNotFoundError(f"QML file not found: {qml_path}")

        # Convert to QUrl
        qml_url = QUrl.fromLocalFile(qml_path)

        # Load the QML file
        self.engine.load(qml_url)

        # Check if loading was successful
        if not self.engine.rootObjects():
            logger.critical("Failed to load QML file")
            raise RuntimeError("Failed to load QML file")

        logger.info("QML file loaded successfully")

    def run(self):
        """Run the application"""
        logger.info("Starting application")

        # Run the application
        return self.app.exec()


def main():
    """Main application entry point"""
    try:
        # Create and run the application
        app = Application()
        return app.run()
    except Exception as e:
        logger.critical(f"Application failed to start: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())