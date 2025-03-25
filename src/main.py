#!/usr/bin/env python3
"""
Main entry point for the fully asynchronous OpenAI Chat application.
Implements improved error handling and complete asyncio integration.
"""

import asyncio
import sys
import os
from typing import Dict, Any, List, Optional
from PyQt6.QtWidgets import QApplication
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtCore import QUrl, QObject, pyqtSlot, QTimer, QCoreApplication


# Import logging utilities first to set up logging early
from src.utils.logging_utils import configure_logging, get_logger
from src.utils.qasync_utilities import setup_async_task_processor

# Configure logging for the application
configure_logging()

# Get a logger for this module
logger = get_logger(__name__)

# Import utilities for async support
from src.utils.qasync_bridge import install as install_qasync, run_coroutine
from src.utils.async_qml_bridge import AsyncQmlBridge

# Import the fully async ViewModels
from src.viewmodels.updated_async_conversation_viewmodel import FullAsyncConversationViewModel
from src.viewmodels.async_settings_viewmodel import AsyncSettingsViewModel

# Import services
from src.services.database import AsyncConversationService
from src.services.api.async_api_service import AsyncApiService

# Import async file utilities
from src.utils.async_file_utils import AsyncFileProcessor, get_file_info_async

# Import the environment variable loader
from dotenv import load_dotenv


class AsyncApplication(QObject):
    """Main application class using fully asynchronous architecture"""

    def __init__(self):
        """Initialize the application with comprehensive error handling"""
        super().__init__()
        self.logger = get_logger("AsyncApplication")

        # Initialize application
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("OpenAI Chat Interface")
        self.app.setOrganizationName("OpenAI")
        self.app.setOrganizationDomain("openai.com")

        # Set up application-wide error handling
        sys.excepthook = self._global_exception_handler

        # Load environment variables with better error handling
        self._load_env()

        # Initialize qasync with the QApplication instance
        # This is critical for proper async integration
        self.event_loop = install_qasync(self.app)

        # Set up periodic task processor for event loop integration
        self.task_processor_timer = setup_async_task_processor()

        self.logger.info("Initialized qasync event loop")

        # Initialize QML engine with proper setup
        self.initialize_qml_engine()

        # Initialize services
        self.initialize_services()

        # Create and register ViewModels
        self.initialize_viewmodels()

        # Load main QML file
        self.load_qml()

        # Set up cleanup handlers
        self._setup_cleanup_handlers()

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

    def get_event_loop(self):
        """Get the event loop, ensuring it exists and is running"""
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            # If we're here, we need to use the previously stored event loop
            if hasattr(self, 'event_loop') and self.event_loop:
                # Set it as the current thread's event loop
                asyncio.set_event_loop(self.event_loop)
                return self.event_loop
            else:
                # Last resort - create a new one (but this indicates a design issue)
                self.logger.warning("Creating new event loop - this might indicate an architectural issue")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop

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
        """Connect to the root QML object for direct interaction with improved error handling"""
        try:
            # Get the root object (MainWindow)
            root_objects = self.engine.rootObjects()
            if not root_objects:
                self.logger.error("No root QML objects found - QML loading failed")
                return

            root = root_objects[0]
            if not root:
                self.logger.error("First root object is null - QML loading failed")
                return

            self.logger.info(f"Root QML object found: {root.objectName()}")

            # Connect Python ViewModels to root properties directly
            # Store previous value to check if it was actually set
            prev_conv_vm = root.property("conversationViewModel")

            root.setProperty("conversationViewModel", self.conversation_vm)
            root.setProperty("settingsViewModel", self.settings_vm)

            # Verify property was set correctly
            new_conv_vm = root.property("conversationViewModel")
            if new_conv_vm and new_conv_vm != prev_conv_vm:
                self.logger.info("Successfully set conversationViewModel property")
            else:
                self.logger.error("Failed to set conversationViewModel property!")
                # Try the context property approach again as a fallback
                self.root_context.setContextProperty("conversationViewModel", self.conversation_vm)
                self.logger.info("Tried setting conversationViewModel via context property as fallback")

            # Connect QML signals to Python slots
            self._connect_qml_signals(root)

            # Initialize view data
            self._initialize_view_data(root)
        except Exception as e:
            self.logger.error(f"Error connecting to root QML object: {e}", exc_info=True)
            import traceback
            self.logger.error(f"Stack trace: {traceback.format_exc()}")

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
        """Initialize view with initial data using async patterns"""
        # Use a small delay to ensure QML is fully loaded,
        # then start the async initialization
        QTimer.singleShot(100, self._start_async_initialization)


    # File handling helper
    def _handle_file_request(self, file_url):
        """Handle file request from QML using async file processor"""
        # Convert QML URL to Python path
        file_path = self.qml_bridge.file_url_to_path(file_url)
        self.logger.info(f"Processing file: {file_path}")

        # Start async file processing
        asyncio.create_task(self._process_file_async(file_path))

    async def _process_file_async(self, file_path):
        """Process file asynchronously"""
        try:
            # Use async file processing
            file_info = await get_file_info_async(
                file_path,
                progress_callback=lambda progress: self._update_file_progress(os.path.basename(file_path), progress),
                error_callback=lambda error: self._handle_file_error(os.path.basename(file_path), error)
            )

            if file_info:
                # Update file info in QML model
                model_info = {
                    "fileName": file_info["file_name"],
                    "filePath": file_path,
                    "fileSize": self.qml_bridge.format_file_size(file_info["size"]),
                    "tokenCount": file_info["token_count"]
                }

                # Find the file in the model and update it
                self.qml_bridge.call_qml_method("mainWindow", "updateFileInfo", model_info)

                self.logger.info(f"File processed: {file_info['file_name']} "
                                 f"({file_info['token_count']} tokens)")
        except Exception as e:
            self.logger.error(f"Error in async file processing: {str(e)}", exc_info=True)
            self._handle_file_error(os.path.basename(file_path), str(e))

    def _update_file_progress(self, file_name, progress):
        """Update file processing progress in QML"""
        self.qml_bridge.call_qml_method("mainWindow", "updateFileProgress", file_name, progress)

    def _handle_file_error(self, file_name, error_message):
        """Handle file processing error"""
        self.logger.error(f"Error processing file {file_name}: {error_message}")
        self.qml_bridge.call_qml_method("mainWindow", "handleFileError", file_name, error_message)

    def _handle_qml_error(self, error_message):
        """Handle error from QML"""
        self.logger.error(f"Error from QML: {error_message}")

    def initialize_qml_engine(self):
        """Initialize the QML engine with proper import paths and error handling"""
        try:
            # Set environment variable for QML style
            os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

            # Create the QML engine
            self.engine = QQmlApplicationEngine()

            # Connect error handlers
            self.engine.objectCreated.connect(self._on_object_created)
            self.engine.warnings.connect(self._on_qml_warning)

            # Enable QML debugging
            self.engine.rootContext().setContextProperty("DEBUG_MODE", True)

            # Set import paths for QML
            qml_dir = os.path.join(os.path.dirname(__file__), "views", "qml")
            self.engine.addImportPath(qml_dir)

            # ADDED: Explicitly add components import path
            components_dir = os.path.join(qml_dir, "components")
            utils_dir = os.path.join(qml_dir, "utils")

            # Log paths for debugging
            self.logger.info(f"Adding QML import paths:")
            self.logger.info(f"  - Main QML dir: {qml_dir}")
            self.logger.info(f"  - Components dir: {components_dir}")
            self.logger.info(f"  - Utils dir: {utils_dir}")

            # Verify qmldir files exist
            comp_qmldir = os.path.join(components_dir, "qmldir")
            utils_qmldir = os.path.join(utils_dir, "qmldir")
            self.logger.info(f"Checking qmldir files:")
            self.logger.info(f"  - Components qmldir exists: {os.path.exists(comp_qmldir)}")
            self.logger.info(f"  - Utils qmldir exists: {os.path.exists(utils_qmldir)}")

            # Create and initialize the bridge
            self.qml_bridge = AsyncQmlBridge(self.engine)
            self.qml_bridge.errorOccurred.connect(self._on_bridge_error)

            # Store root context for convenience
            self.root_context = self.engine.rootContext()

            self.logger.info("QML engine initialized successfully")
        except Exception as e:
            self.logger.critical(f"Error initializing QML engine: {e}", exc_info=True)
            raise

    def _setup_cleanup_handlers(self):
        """Set up cleanup handlers for application exit"""
        # Connect to app's aboutToQuit signal
        self.app.aboutToQuit.connect(self._prepare_cleanup)

    async def _async_cleanup(self):
        """Perform async cleanup operations before exiting"""
        try:
            # Close database connections
            if hasattr(self, 'db_service'):
                await self.db_service.close()

            # Close API connections
            if hasattr(self, 'api_service') and hasattr(self.api_service, 'close'):
                await self.api_service.close()

            self.logger.info("Async cleanup completed")
        except Exception as e:
            self.logger.error(f"Error during async cleanup: {str(e)}")

    def _global_exception_handler(self, exc_type, exc_value, exc_traceback):
        """Global exception handler for uncaught exceptions"""
        self.logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def _on_bridge_error(self, error_type: str, message: str):
        """Handle errors from the QML bridge"""
        self.logger.error(f"QML Bridge error ({error_type}): {message}")
        # Could show an error dialog or other UI feedback here

    def initialize_services(self):
        """Initialize application services with better error handling"""
        try:
            # Use AsyncApiService for API calls
            self.api_service = AsyncApiService()
            self.logger.info("Initialized AsyncApiService")

            # Set API key from environment if available
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if api_key:
                self.api_service.set_api_key(api_key)
                self.logger.info("Set API key from environment")

            # Use AsyncConversationService for database operations
            self.db_service = AsyncConversationService()
            self.logger.info("Initialized AsyncConversationService")

            # Create an AsyncFileProcessor for handling file operations
            self.file_processor = AsyncFileProcessor()
            self.logger.info("Initialized AsyncFileProcessor")

            # Create ViewModels
            self.conversation_vm = FullAsyncConversationViewModel()
            self.settings_vm = AsyncSettingsViewModel()

            from src.utils.qasync_bridge import run_coroutine
            run_coroutine(
                self._async_initialize_services(),
                callback=lambda _: self.logger.info("Services initialized"),
                error_callback=lambda e: self.logger.error(f"Error in async service initialization: {str(e)}")
            )

            self.logger.info("Services created successfully")
        except Exception as e:
            self.logger.error(f"Error initializing services: {e}", exc_info=True)
            raise

    def initialize_viewmodels(self):
        """Initialize and register ViewModels with improved error handling"""
        try:
            # Create FullAsyncConversationViewModel
            self.conversation_vm = FullAsyncConversationViewModel()
            self.settings_vm = AsyncSettingsViewModel()
            self.logger.info("Created ViewModels")

            # Initialize settings ViewModel with API service if needed
            if hasattr(self.settings_vm, 'initialize'):
                self.settings_vm.initialize(self.api_service)
                self.logger.info("Initialized AsyncSettingsViewModel with AsyncApiService")

            # Register ViewModels with QML
            self.qml_bridge.register_context_property("conversationViewModel", self.conversation_vm)
            self.qml_bridge.register_context_property("settingsViewModel", self.settings_vm)
            self.logger.info("Registered ViewModels with QML")

            # Register bridge for QML logging and error handling
            self.qml_bridge.register_context_property("bridge", self.qml_bridge)
            self.logger.info("Registered bridge with QML")

            # Create QmlAsyncHelper for better QML-async integration
            from src.utils.qml_async_helper import QmlAsyncHelper
            self.qml_async_helper = QmlAsyncHelper()
            self.qml_bridge.register_context_property("asyncHelper", self.qml_async_helper)
            self.logger.info("Registered QmlAsyncHelper with QML")
        except Exception as e:
            self.logger.error(f"Error initializing ViewModels: {e}", exc_info=True)
            raise

    async def _async_initialize_services(self):
        """Initialize async services"""
        try:
            # Initialize database service
            await self.db_service.initialize()
            self.logger.info("Database service initialized")
        except Exception as e:
            self.logger.error(f"Error in async service initialization: {str(e)}")
            raise

    def _start_async_initialization(self):
        """Start the async initialization process"""
        try:
            # Ensure we're using the right event loop
            from src.utils.qasync_bridge import run_coroutine, ensure_qasync_loop
            ensure_qasync_loop()

            # Use run_coroutine with proper error handling
            run_coroutine(
                self._async_initialize_view_data(),
                callback=lambda result: self.logger.info("View data initialization completed"),
                error_callback=lambda e: self._handle_async_init_error(e)
            )
        except Exception as e:
            # Improve error logging
            import traceback
            self.logger.error(f"Error starting async initialization: {str(e)}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")

    # 2. Add a dedicated error handler method
    def _handle_async_init_error(self, error):
        """Handle errors during async initialization"""
        import traceback
        error_msg = str(error)
        self.logger.error(f"Error initializing view data: {error_msg}")

        # Get the full traceback
        tb = getattr(error, "__traceback__", None)
        if tb:
            tb_str = "".join(traceback.format_tb(tb))
            self.logger.error(f"Traceback: {tb_str}")

        # Create a more user-friendly error message
        user_msg = "Failed to initialize application data."
        if "loop" in error_msg.lower():
            user_msg += " Event loop configuration issue detected."
        elif "database" in error_msg.lower():
            user_msg += " Database connection issue detected."

        # Show error to user but continue with the application
        if hasattr(self, 'engine') and self.engine:
            root_objects = self.engine.rootObjects()
            if root_objects:
                # Find error dialog object
                for obj in root_objects:
                    if hasattr(obj, "showError"):
                        obj.showError(user_msg)
                        break

    # 3. Update _async_initialize_view_data method
    async def _async_initialize_view_data(self):
        """Asynchronously initialize view data"""
        try:
            # Ensure we're using the right event loop
            from src.utils.qasync_bridge import ensure_qasync_loop
            ensure_qasync_loop()

            # Asynchronously load conversations
            self.logger.debug("Starting to load conversations asynchronously")

            # Ensure the database service is initialized
            await self.db_service.initialize()

            # Now get all conversations
            conversations = await self.db_service.get_all_conversations()
            self.logger.debug(f"Loaded {len(conversations) if conversations else 0} conversations")

            if conversations:
                # Convert conversations to list of dicts for the model
                conv_dicts = []
                for conv in conversations:
                    conv_dicts.append({
                        "id": conv.id,
                        "name": conv.name,
                        "created_at": conv.created_at.isoformat(),
                        "modified_at": conv.modified_at.isoformat()
                    })

                # Update model in QML by calling a method on the mainWindow
                self.logger.debug("Updating QML conversation model")
                self.qml_bridge.call_qml_method("mainWindow", "updateConversationsModel", conv_dicts)
                self.logger.info(f"Loaded {len(conv_dicts)} conversations into model")

                # Load the first conversation if available
                if conv_dicts:
                    self.logger.debug(f"Loading first conversation: {conv_dicts[0]['id']}")
                    await asyncio.sleep(0.1)  # Small delay to ensure UI is ready

                    # Use run_coroutine instead of directly calling to ensure proper loop usage
                    from src.utils.qasync_bridge import run_coroutine
                    run_coroutine(
                        self._load_first_conversation(conv_dicts[0]['id']),
                        error_callback=lambda e: self.logger.error(f"Error loading first conversation: {str(e)}")
                    )
            else:
                # No conversations - create a new one
                self.logger.info("No existing conversations found, creating new conversation")
                await asyncio.sleep(0.1)  # Small delay to ensure UI is ready
                from src.utils.qasync_bridge import run_coroutine
                run_coroutine(
                    self._create_initial_conversation(),
                    error_callback=lambda e: self.logger.error(f"Error creating initial conversation: {str(e)}")
                )

            return True  # Signal successful completion
        except Exception as e:
            # Log error and re-raise to ensure proper error handling
            import traceback
            self.logger.error(f"Error initializing view data: {str(e)}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            # Re-raise to be handled by the error callback
            raise

    # 4. Add helper methods for loading/creating initial conversations
    async def _load_first_conversation(self, conversation_id):
        """Helper to load the first conversation"""
        # Ensure we're using the right event loop
        from src.utils.qasync_bridge import ensure_qasync_loop
        ensure_qasync_loop()

        # Load the conversation
        self.conversation_vm.load_conversation(conversation_id)

    async def _create_initial_conversation(self):
        """Helper to create initial conversation"""
        # Ensure we're using the right event loop
        from src.utils.qasync_bridge import ensure_qasync_loop
        ensure_qasync_loop()

        # Create a new conversation
        self.conversation_vm.create_new_conversation("New Conversation")

    def _prepare_cleanup(self):
        """Prepare for cleanup - run async cleanup in the event loop"""
        # Use run_coroutine instead of asyncio.create_task()
        run_coroutine(
            self._async_cleanup(),
            callback=lambda _: self.logger.info("Async cleanup completed"),
            error_callback=lambda e: self.logger.error(f"Error during cleanup: {str(e)}")
        )

        # Give some time for cleanup to complete before app exits
        QTimer.singleShot(500, lambda: None)

    def run(self):
        """Run the application with enhanced error handling"""
        try:
            self.logger.info("Starting application")

            # Show the main window
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
        # Import qasync first, before other imports
        import qasync

        # Standard imports
        import sys
        import os
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtQml import QQmlApplicationEngine

        # Configure logging first to set up logging early
        from src.utils.logging_utils import configure_logging, get_logger
        configure_logging()
        logger = get_logger(__name__)

        # Create QApplication
        app = QApplication(sys.argv)
        app.setApplicationName("OpenAI Chat Interface")
        app.setOrganizationName("OpenAI")
        app.setOrganizationDomain("openai.com")

        # Set up global exception handler
        sys.excepthook = lambda exc_type, exc_value, exc_tb: (
            logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb)),
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        )

        # Initialize asyncio loop with qasync
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        app_instance = AsyncApplication()

        # Run the application with qasync
        with loop:
            # Exit with the result of app.exec() through loop.run_forever()
            return loop.run_forever()

    except Exception as e:
        logger.critical(f"Application failed to start: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
