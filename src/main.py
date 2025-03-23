# src/main.py

import sys
import os
from typing import Dict, Any, List, Optional
from PyQt6.QtWidgets import QApplication
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtCore import QUrl, QObject, pyqtSlot, QTimer

# Import logging utilities first to set up logging early
from src.utils.logging_utils import configure_logging, get_logger

# Configure logging for the application
configure_logging()

# Get a logger for this module
logger = get_logger(__name__)

# Import utilities for async support
from src.utils.qasync_bridge import install as install_qasync
from src.utils.qml_bridge import QmlBridge, QmlListModel

# Import ViewModels
from src.viewmodels.reactive_conversation_viewmodel import ReactiveConversationViewModel
from src.viewmodels.settings_viewmodel import SettingsViewModel

# Import services
from src.services.db_service import ConversationService
from src.services.api_service import ApiService

# Import other utilities
from dotenv import load_dotenv


class Application(QObject):
    """Main application class with enhanced QML-Python integration"""

    def __init__(self):
        """Initialize the application with improved error handling"""
        super().__init__()
        self.logger = get_logger("Application")

        # Initialize application
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("OpenAI Chat Interface")
        self.app.setOrganizationName("OpenAI")
        self.app.setOrganizationDomain("openai.com")

        # Set up application-wide error handling
        sys.excepthook = self._global_exception_handler

        # Load environment variables with better error handling
        self._load_env()

        # Initialize async support
        self.event_loop = install_qasync(self.app)

        # Initialize services
        self.initialize_services()

        # Initialize QML engine with proper setup
        self.initialize_qml_engine()

        # Create and register ViewModels
        self.initialize_viewmodels()

        # Load main QML file
        self.load_qml()

    def _global_exception_handler(self, exc_type, exc_value, exc_traceback):
        """Global exception handler for uncaught exceptions"""
        self.logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def _on_bridge_error(self, error_type: str, message: str):
        """Handle errors from the QML bridge"""
        self.logger.error(f"QML Bridge error ({error_type}): {message}")
        # Could show an error dialog or other UI feedback here

    def _on_object_created(self, obj, url):
        """Handle QML object creation events with safer error handling"""
        if not obj and url.isValid():
            self.logger.error(f"Failed to create QML object for {url.toString()}")

            # Get a list of all QML errors
            if hasattr(self.engine, 'errors'):
                qml_errors = self.engine.errors()
                if qml_errors:
                    for i, error in enumerate(qml_errors):
                        try:
                            if hasattr(error, 'toString'):
                                error_msg = f"QML Error {i + 1}: {error.toString()}"
                            elif hasattr(error, 'line') and hasattr(error, 'column') and hasattr(error, 'description'):
                                error_msg = f"QML Error {i + 1}: Line {error.line()}, Column {error.column()}: {error.description()}"
                            else:
                                error_msg = f"QML Error {i + 1}: {error}"
                            self.logger.error(error_msg)
                        except Exception as e:
                            self.logger.error(f"Error extracting QML error details: {e}")
                            self.logger.error(f"Original error: {error}")

                sys.exit(-1)

    def _on_qml_warning(self, warning):
        """Handle QML warnings with improved detail extraction"""
        try:
            # Determine the type of warning
            if isinstance(warning, list):
                # Handle list of warnings
                details = []
                for w in warning:
                    if hasattr(w, "toString"):
                        details.append(w.toString())
                    elif hasattr(w, "description"):
                        details.append(w.description())
                    elif hasattr(w, "message"):
                        details.append(w.message())
                    else:
                        details.append(str(w))
                detail = "\n".join(details)
            else:
                # Handle single warning
                if hasattr(warning, "toString"):
                    detail = warning.toString()
                elif hasattr(warning, "description"):
                    detail = warning.description()
                elif hasattr(warning, "message"):
                    detail = warning.message()
                else:
                    detail = str(warning)

            # Log the detailed warning
            self.logger.warning(f"QML Warning detail: {detail}")
        except Exception as e:
            self.logger.warning(f"Error processing QML warning: {e}")
            self.logger.warning(f"Original warning: {warning}")

    def _load_env(self):
        """Load environment variables from .env file with better error handling"""
        try:
            # Load environment variables from .env file if it exists
            load_dotenv()
            if os.environ.get("OPENAI_API_KEY"):
                self.logger.info("Loaded API key from environment")
            else:
                self.logger.warning("No API key found in environment")
        except Exception as e:
            self.logger.warning(f"Error loading .env file: {e}")
            # Continue with application startup even if .env loading fails

    def initialize_services(self):
        """Initialize application services with better error handling"""
        try:
            # Database service for conversation storage
            self.db_service = ConversationService()
            self.logger.info("Initialized ConversationService")

            # API service for OpenAI interaction
            self.api_service = ApiService()
            self.logger.info("Initialized ApiService")

            # Set API key from environment if available
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if api_key:
                self.api_service.set_api_key(api_key)
                self.logger.info("Set API key from environment")
        except Exception as e:
            self.logger.error(f"Error initializing services: {e}", exc_info=True)
            raise

    def initialize_viewmodels(self):
        """Initialize and register ViewModels with improved error handling"""
        try:
            # Create ViewModels
            self.conversation_vm = ReactiveConversationViewModel()
            self.settings_vm = SettingsViewModel()
            self.logger.info("Created ViewModels")

            # Initialize settings ViewModel with API service
            if hasattr(self.settings_vm, 'initialize'):
                self.settings_vm.initialize(self.api_service)
                self.logger.info("Initialized SettingsViewModel with ApiService")

            # Connect ViewModels to services
            self.conversation_vm.api_service = self.api_service
            self.conversation_vm.conversation_service = self.db_service
            self.logger.info("Connected ViewModel to services")

            # Register ViewModels with QML
            self.qml_bridge.register_context_property("conversationViewModel", self.conversation_vm)
            self.qml_bridge.register_context_property("settingsViewModel", self.settings_vm)
            self.logger.info("Registered ViewModels with QML")

            # Register bridge for QML logging and error handling
            self.qml_bridge.register_context_property("bridge", self.qml_bridge)
            self.logger.info("Registered bridge with QML")

            # Create and register list models
            self._create_list_models()
        except Exception as e:
            self.logger.error(f"Error initializing ViewModels: {e}", exc_info=True)
            raise

    def _create_list_models(self):
        """Create and register list models for QML"""
        try:
            # Create models with type information for proper conversion
            self.conversations_model = QmlListModel(role_types={
                "id": str,
                "name": str,
                "created_at": str,
                "modified_at": str
            })

            self.messages_model = QmlListModel(role_types={
                "id": str,
                "role": str,
                "content": str,
                "timestamp": str,
                "attachments": list
            })

            self.file_attachments_model = QmlListModel(role_types={
                "fileName": str,
                "filePath": str,
                "fileSize": str,
                "tokenCount": int
            })

            # Register models with QML
            self.qml_bridge.register_context_property("conversationsModel", self.conversations_model)
            self.qml_bridge.register_context_property("messagesModel", self.messages_model)
            self.qml_bridge.register_context_property("fileAttachmentsModel", self.file_attachments_model)
            self.logger.info("Created and registered list models")
        except Exception as e:
            self.logger.error(f"Error creating list models: {e}", exc_info=True)
            raise

    def load_qml(self):
        """Load the main QML file with enhanced error handling"""
        try:
            # Get the path to the QML file
            qml_path = os.path.join(os.path.dirname(__file__), "views", "qml", "MainWindow.qml")

            # Check if the file exists
            if not os.path.exists(qml_path):
                self.logger.critical(f"QML file not found: {qml_path}")
                raise FileNotFoundError(f"QML file not found: {qml_path}")

            # Log the attempt to load
            self.logger.info(f"Attempting to load QML file: {qml_path}")

            # Convert to QUrl
            qml_url = QUrl.fromLocalFile(qml_path)

            # Load the QML file
            self.engine.load(qml_url)

            # Check if loading was successful
            if not self.engine.rootObjects():
                self.logger.critical("Failed to load QML file")

                # Get a list of all QML errors
                qml_errors = self.engine.errors() if hasattr(self.engine, 'errors') else []
                if qml_errors:
                    for i, error in enumerate(qml_errors):
                        if hasattr(error, 'line') and hasattr(error, 'column') and hasattr(error, 'description'):
                            error_msg = f"QML Error {i + 1}: Line {error.line()}, Column {error.column()}: {error.description()}"
                        else:
                            error_msg = f"QML Error {i + 1}: {error}"
                        self.logger.error(error_msg)

                raise RuntimeError("Failed to load QML file")

            self.logger.info("QML file loaded successfully")

            # Connect to root QML object for direct interaction
            self._connect_to_root_object()
        except Exception as e:
            self.logger.critical(f"Error loading QML: {e}", exc_info=True)
            raise

    def _connect_to_root_object(self):
        """Connect to the root QML object for direct interaction"""
        try:
            # Get the root object (MainWindow)
            root = self.engine.rootObjects()[0]
            if not root:
                self.logger.warning("No root QML object found")
                return

            # Connect Python ViewModels to root properties directly
            root.setProperty("conversationViewModel", self.conversation_vm)
            root.setProperty("settingsViewModel", self.settings_vm)

            # Connect QML signals to Python slots
            self._connect_qml_signals(root)

            # Initialize view data
            self._initialize_view_data(root)
        except Exception as e:
            self.logger.error(f"Error connecting to root QML object: {e}", exc_info=True)

    def _connect_qml_signals(self, root):
        """Connect QML signals to Python slots"""
        # Example - connect signals from QML to Python methods
        # These would be signals defined in the MainWindow.qml file
        try:
            # Example connections
            self.qml_bridge.connect_qml_signal("mainWindow", "fileRequested", self._handle_file_request)
            self.qml_bridge.connect_qml_signal("mainWindow", "errorOccurred", self._handle_qml_error)
            self.logger.info("Connected QML signals to Python slots")
        except Exception as e:
            self.logger.error(f"Error connecting QML signals: {e}", exc_info=True)

    def _initialize_view_data(self, root):
        """Initialize view with initial data"""
        try:
            # Load conversations into model
            conversations = self.conversation_vm.get_all_conversations()
            if conversations:
                # Convert conversations to list of dicts for the model
                conv_dicts = []
                for conv in conversations:
                    conv_dicts.append({
                        "id": conv.get('id', ''),
                        "name": conv.get('name', 'Unnamed Conversation'),
                        "created_at": conv.get('created_at', ''),
                        "modified_at": conv.get('modified_at', '')
                    })

                # Update the model
                self.conversations_model.setItems(conv_dicts)
                self.logger.info(f"Loaded {len(conv_dicts)} conversations into model")

                # Load the first conversation if available
                if conv_dicts:
                    # Use a short delay to ensure QML is fully loaded
                    QTimer.singleShot(100, lambda: self.conversation_vm.load_conversation(conv_dicts[0]['id']))
            else:
                # No conversations - create a new one
                self.logger.info("No existing conversations found, creating new conversation")
                QTimer.singleShot(100, lambda: self.conversation_vm.create_new_conversation("New Conversation"))
        except Exception as e:
            self.logger.error(f"Error initializing view data: {e}", exc_info=True)

    # File handling helpers
    def _handle_file_request(self, file_url):
        """Handle file request from QML"""
        try:
            # Convert QML URL to Python path
            file_path = file_url.toString()
            if file_path.startswith("file:///"):
                # Remove file:/// prefix
                if sys.platform == "win32":
                    # Windows paths
                    file_path = file_path[8:]
                else:
                    # Unix paths
                    file_path = file_path[7:]

            # TODO: Process file and return information to QML
            self.logger.info(f"Processing file: {file_path}")

            # Example - could return file info to QML
            # self.qml_bridge.call_qml_method("mainWindow", "updateFileInfo", file_info)
        except Exception as e:
            self.logger.error(f"Error handling file request: {e}", exc_info=True)

    def _handle_qml_error(self, error_message):
        """Handle error from QML"""
        self.logger.error(f"Error from QML: {error_message}")

    def initialize_qml_engine(self):
        """Initialize the QML engine with proper import paths and error handling"""
        try:
            # Create the QML engine
            self.engine = QQmlApplicationEngine()

            # Connect error handlers
            self.engine.objectCreated.connect(self._on_object_created)
            self.engine.warnings.connect(self._on_qml_warning)

            # Set import paths for QML
            qml_dir = os.path.join(os.path.dirname(__file__), "views", "qml")
            self.engine.addImportPath(qml_dir)

            # Log the import paths to verify
            self.logger.info(f"Adding QML import path: {qml_dir}")

            # Create and initialize the bridge
            self.qml_bridge = QmlBridge(self.engine)
            self.qml_bridge.errorOccurred.connect(self._on_bridge_error)

            self.logger.info("QML engine initialized successfully")
        except Exception as e:
            self.logger.critical(f"Error initializing QML engine: {e}", exc_info=True)
            raise

    def run(self):
        """Run the application with enhanced error handling"""
        try:
            self.logger.info("Starting application")

            # Show the main window and run the application
            window = self.engine.rootObjects()[0]
            if window:
                window.show()

            # Run the application
            return self.app.exec()
        except Exception as e:
            self.logger.critical(f"Critical error running application: {e}", exc_info=True)
            return 1


def main():
    """Main application entry point with enhanced error handling"""
    try:
        # Create and run the application
        app = Application()
        return app.run()
    except Exception as e:
        logger.critical(f"Application failed to start: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())