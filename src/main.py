"""
Main entry point for the fully asynchronous OpenAI Chat application.
Implements improved error handling and complete asyncio integration with qasync.
"""

import asyncio
from datetime import datetime
import sys
import os
import traceback
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt6.QtQml import QQmlApplicationEngine
from PyQt6.QtCore import QUrl, QObject, QTimer, pyqtSlot, QCoreApplication

# Import logging utilities first to set up logging early
from src.utils.logging_utils import configure_logging, get_logger

# Configure logging for the application
configure_logging()

# Get a logger for this module
logger = get_logger(__name__)

# Import utilities for async support
from src.utils.qasync_bridge import install as install_qasync, run_coroutine, ensure_qasync_loop, run_sync, install
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
        # Initialize the QObject parent class
        super().__init__()

        # Setup logger
        self.logger = get_logger("AsyncApplication")
        self.main_window_shown = False

        # Run the actual initialization process
        try:
            self._initialize()
        except Exception as e:
            self.logger.critical(f"Error during application initialization: {e}", exc_info=True)
            self._show_error_window(str(e))

    def _initialize(self):
        """Initialize the application with comprehensive error handling"""
        try:
            # Initialize application
            self.app = QApplication.instance() or QApplication(sys.argv)
            self.app.setApplicationName("OpenAI Chat Interface")
            self.app.setOrganizationName("OpenAI")
            self.app.setOrganizationDomain("openai.com")

            # Set up application-wide error handling
            sys.excepthook = self._global_exception_handler

            # Load environment variables with better error handling
            self._load_env()

            # IMPROVED: qasync initialization with proper event loop setup
            self.logger.info("Initializing qasync event loop")

            # Install qasync with the application - USE THE IMPROVED VERSION
            self.event_loop = install(self.app)

            # Set it as the default loop
            asyncio.set_event_loop(self.event_loop)

            # Verify the event loop is running properly
            if not self.event_loop.is_running():
                self.logger.warning("Event loop not running after initialization, attempting to start it")
                # Start the loop and process events to activate it
                asyncio.ensure_future(asyncio.sleep(0.01), loop=self.event_loop)
                self.app.processEvents()

            # Set up a timer to process asyncio events regularly - IMPROVED APPROACH
            self.event_timer = QTimer()
            self.event_timer.timeout.connect(lambda: None)  # Wake up the event loop
            self.event_timer.start(16)  # 60fps (16ms) for smooth UI

            # Store the timer on the event loop to prevent garbage collection
            self.event_loop._event_timer = self.event_timer

            # Log the event loop status
            self.logger.info(f"Main event loop initialized: {id(self.event_loop)}, running={self.event_loop.is_running()}")

            # Initialize QML engine with proper setup
            self._initialize_qml_engine()

            # Initialize services and viewmodels with the improved qasync approach
            self._initialize_services()
            self._initialize_viewmodels()

            # Set up a timer to complete initialization after the event loop starts running
            QTimer.singleShot(50, self._complete_initialization)

            # Set up cleanup handlers
            self._setup_cleanup_handlers()

        except Exception as e:
            self.logger.critical(f"Error during application initialization: {e}", exc_info=True)
            raise

    def _initialize_services(self):
        """Initialize services using the improved qasync approach"""
        try:
            self.logger.info("Initializing services")

            # Make sure the event loop is set as the current loop and running
            ensure_qasync_loop()

            # Create API service
            self.api_service = AsyncApiService()
            self.logger.info("Initialized AsyncApiService")

            # Set API key from environment if available
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if api_key:
                self.api_service.set_api_key(api_key)
                self.logger.info("Set API key from environment")

            # Create conversation service
            self.db_service = AsyncConversationService()
            self.logger.info("Created AsyncConversationService")

            # Create file processor
            self.file_processor = AsyncFileProcessor()
            self.logger.info("Initialized AsyncFileProcessor")

            # Initialize database tables using run_sync - IMPROVED APPROACH
            try:
                # Use the improved run_sync that processes Qt events while waiting
                success = run_sync(self.db_service.initialize())
                self.logger.info(f"Database initialized synchronously: {success}")
            except Exception as e:
                self.logger.error(f"Error initializing database synchronously: {str(e)}")

                # Fall back to async initialization with proper error handling
                def on_init_complete(result):
                    self.logger.info(f"Database initialized asynchronously: {result}")

                def on_init_error(error):
                    self.logger.error(f"Database initialization error: {str(error)}")

                # Use the improved run_coroutine function
                run_coroutine(
                    self.db_service.initialize(),
                    callback=on_init_complete,
                    error_callback=on_init_error
                )

            self.logger.info("Services initialized")
        except Exception as e:
            self.logger.error(f"Error initializing services: {e}", exc_info=True)
            raise

    def _load_initial_data(self):
        """Load initial data after the UI is shown, using improved qasync approach"""
        try:
            self.logger.info("Loading initial data")

            # Check if the event loop is running before proceeding
            loop = ensure_qasync_loop()
            if not loop.is_running():
                self.logger.error("Cannot load initial data - event loop not running")
                return False

            # Use run_coroutine with improved error handling
            def on_success(success):
                self.logger.info(f"Initial data load {'succeeded' if success else 'failed'}")

            def on_error(e):
                self.logger.error(f"Error loading initial data: {str(e)}")
                # Try to recover with a new conversation
                self._initialize_fallback_conversation()

            # Use the improved run_coroutine function
            run_coroutine(
                self._load_initial_data_async(),
                callback=on_success,
                error_callback=on_error
            )

            return True
        except Exception as e:
            self.logger.error(f"Error setting up initial data load: {str(e)}")
            return False

    def _initialize_fallback_conversation(self):
        """Create a fallback conversation in case of data loading errors"""
        self.logger.warning("Attempting to create fallback conversation")

        def on_success(result):
            self.logger.info(f"Fallback conversation created: {result}")

        def on_error(e):
            self.logger.error(f"Failed to create fallback conversation: {str(e)}")
            # Show error to user
            self._show_error_window("Failed to create conversation - please restart the application")

        # Use the improved run_coroutine function
        run_coroutine(
            self._initialize_new_conversation(),
            callback=on_success,
            error_callback=on_error
        )

    def _complete_initialization(self):
        """Complete initialization after the event loop is running
        with improved async handling.
        """
        try:
            self.logger.info("Completing initialization")

            # CRITICAL FIX: Ensure the event loop is running
            self._check_event_loop()

            # Load main QML file
            self._load_qml()

            # Use a timer to create a proper separation of initialization steps
            # This ensures the QML engine has time to process events
            QTimer.singleShot(50, self._initialize_views)

        except Exception as e:
            self.logger.critical(f"Error completing initialization: {str(e)}")
            self._show_error_window(str(e))

    def _check_event_loop(self):
        """Check if the event loop is properly running and fix if needed"""
        if not self.event_loop.is_running():
            self.logger.warning("Event loop not running, trying to start it")

            # Create a new task that will force the loop to run
            asyncio.ensure_future(asyncio.sleep(0.1), loop=self.event_loop)

            # Process Qt events
            self.app.processEvents()

            # Check again
            if not self.event_loop.is_running():
                self.logger.error("Failed to start event loop")

                # Last resort - recreate the event loop
                self.event_loop = install_qasync(self.app)
                asyncio.set_event_loop(self.event_loop)

                # Create a task and process events
                asyncio.ensure_future(asyncio.sleep(0.1), loop=self.event_loop)
                self.app.processEvents()

        # Get the current running status
        is_running = self.event_loop.is_running()
        self.logger.info(f"Event loop check: id={id(self.event_loop)}, running={is_running}")

        return is_running

    def _show_error_window(self, error_message):
        """Create an error window to display critical errors"""
        window = QMainWindow()
        window.setWindowTitle("OpenAI Chat - Error")
        window.resize(800, 600)

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)

        error_label = QLabel(f"Critical Error: {error_message}")
        error_label.setStyleSheet("color: red; font-size: 16px; padding: 20px;")
        error_label.setWordWrap(True)
        layout.addWidget(error_label)

        details_label = QLabel("Please check the logs for more details. The application may not function correctly.")
        details_label.setStyleSheet("color: black; font-size: 14px; padding: 10px;")
        details_label.setWordWrap(True)
        layout.addWidget(details_label)

        window.setCentralWidget(central_widget)
        window.show()

        self.error_window = window
        self.logger.info("Showing error window")

    def run(self):
        """Run the application with enhanced error handling and proper shutdown support"""
        try:
            self.logger.info("Starting application main loop")

            # Create a timer to check if the main window appears
            self.startup_check_timer = QTimer()
            self.startup_check_timer.timeout.connect(self._check_startup)
            self.startup_check_timer.setSingleShot(True)
            self.startup_check_timer.start(5000)  # Check after 5 seconds

            # CRITICAL FIX: Ensure the event loop stays running
            # Start a background task that keeps the loop running
            self.keep_loop_alive_timer = QTimer()
            self.keep_loop_alive_timer.timeout.connect(self._ensure_loop_running)
            self.keep_loop_alive_timer.start(50)  # Every 50ms

            # Create and start a QML bridge message processor timer
            # This ensures QML messages are processed in the Qt event loop
            self.message_processor_timer = QTimer()
            self.message_processor_timer.timeout.connect(lambda: None)  # Just a dummy function to wake up the event loop
            self.message_processor_timer.start(50)  # 50ms interval

            # Log the event loop state
            is_running = self.event_loop.is_running()
            self.logger.info(f"Running event loop {id(self.event_loop)}, is_running={is_running}")

            # Schedule an initial task to make the loop "running"
            self._ensure_loop_running()

            # Use app.exec() which will return when quit() is called
            return self.app.exec()

        except Exception as e:
            self.logger.critical(f"Critical error running application: {e}", exc_info=True)
            traceback.print_exc()
            return 1

    def _ensure_loop_running(self):
        """Helper method to ensure the event loop is running"""
        try:
            # Check if the loop is already running
            if hasattr(self.event_loop, 'is_running') and self.event_loop.is_running():
                # Loop is already running, just log at DEBUG level
                self.logger.debug(f"Event loop already running: {id(self.event_loop)}")
                return

            # For qasync loops - process events to activate
            if hasattr(self.event_loop, '_process_events'):
                self.event_loop._process_events([])

            # Create a dummy task to help the loop recognize it's "running"
            asyncio.ensure_future(asyncio.sleep(0.1), loop=self.event_loop)

            # Also process Qt events
            self.app.processEvents()

            # For debugging, check the loop status
            running_status = hasattr(self.event_loop, 'is_running') and self.event_loop.is_running()
            self.logger.debug(f"Event loop check: id={id(self.event_loop)}, running={running_status}")
        except Exception as e:
            self.logger.error(f"Error ensuring loop is running: {str(e)}")

    def _handle_event_loop_exception(self, loop, context):
        """Handle exceptions in the event loop"""
        exception = context.get('exception')
        message = context.get('message', 'No error message')

        if exception:
            self.logger.critical(f"Event loop exception: {message}", exc_info=exception)
        else:
            self.logger.critical(f"Event loop error: {message}")

        # In case of fatal errors, try to quit the application
        if 'Fatal error' in message:
            try:
                self.app.quit()
            except Exception as e:
                self.logger.critical(f"Error during emergency quit: {e}")
                # Force exit as last resort
                import sys
                sys.exit(1)

    def _check_startup(self):
        """Check if the main window was ever shown"""
        if not self.main_window_shown:
            self.logger.critical("Application startup timed out - main window never appeared")
            self._show_error_window("Application startup timed out")

    def _initialize_services_sync(self):
        """Initialize services using synchronous methods for reliability"""
        try:
            self.logger.info("Initializing services")

            # Make sure the event loop is set as the current loop
            asyncio.set_event_loop(self.event_loop)

            # Create API service
            self.api_service = AsyncApiService()
            self.logger.info("Initialized AsyncApiService")

            # Set API key from environment if available
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if api_key:
                self.api_service.set_api_key(api_key)
                self.logger.info("Set API key from environment")

            # Create conversation service
            self.db_service = AsyncConversationService()
            self.logger.info("Created AsyncConversationService")

            # Create file processor
            self.file_processor = AsyncFileProcessor()
            self.logger.info("Initialized AsyncFileProcessor")

            # CRITICAL FIX: Initialize database tables using run_sync
            # This ensures the initialization happens before proceeding
            try:
                # Use the synchronous version to ensure tables are created
                success = run_sync(self.db_service.initialize())
                self.logger.info(f"Database initialized synchronously: {success}")
            except Exception as e:
                self.logger.error(f"Error initializing database synchronously: {str(e)}")
                # Fall back to async initialization but don't wait for it
                run_coroutine(
                    self.db_service.initialize(),
                    callback=lambda result: self.logger.info(f"Database initialized asynchronously: {result}"),
                    error_callback=lambda e: self.logger.error(f"Database initialization error: {str(e)}")
                )

            self.logger.info("Services initialized")
        except Exception as e:
            self.logger.error(f"Error initializing services: {e}", exc_info=True)
            raise

    def _initialize_viewmodels(self):
        """Initialize and register ViewModels"""
        try:
            # Create ViewModels
            self.conversation_vm = FullAsyncConversationViewModel()
            self.settings_vm = AsyncSettingsViewModel()
            self.logger.info("Created ViewModels")

            # Initialize settings ViewModel with API service
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

    def _global_exception_handler(self, exc_type, exc_value, exc_traceback):
        """Global exception handler for uncaught exceptions"""
        self.logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def _load_env(self):
        """Load environment variables from .env file"""
        try:
            # Load environment variables from .env file if it exists
            load_dotenv()
            if os.environ.get("OPENAI_API_KEY"):
                self.logger.info("Loaded API key from environment")
            else:
                self.logger.warning("No API key found in environment")
        except Exception as e:
            self.logger.warning(f"Error loading .env file: {e}")

    def _initialize_qml_engine(self):
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

            # Add components import path
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

    def _on_bridge_error(self, error_type: str, message: str):
        """Handle errors from the QML bridge"""
        self.logger.error(f"QML Bridge error ({error_type}): {message}")

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

            # Track common issues
            if "Binding loop detected" in detail:
                self.logger.warning("QML binding loop detected - this can cause performance issues")
            elif "TypeError" in detail:
                self.logger.error(f"QML TypeError detected: {detail}")
                # This could be serious enough to require intervention
                if not hasattr(self, 'qml_error_count'):
                    self.qml_error_count = 0
                self.qml_error_count += 1

                # If we have too many errors, we might need to show the error window
                if self.qml_error_count > 5:
                    self.logger.error("Too many QML errors, considering fallback")
                    QTimer.singleShot(500, self._check_for_critical_errors)
        except Exception as e:
            self.logger.warning(f"Error processing QML warning: {e}")
            self.logger.warning(f"Original warning: {warning}")

    def _check_for_critical_errors(self):
        """Check if we're encountering critical errors that require intervention"""
        # Only run if we haven't shown the main window yet
        if not self.main_window_shown:
            root_objects = self.engine.rootObjects()
            if not root_objects or not root_objects[0].isVisible():
                self.logger.error("QML health check failed - showing error window")
                self._show_error_window("Failed to initialize QML interface")

    def _load_qml(self):
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

            # Clear any previous root objects
            if self.engine.rootObjects():
                self.logger.info("Clearing previous root objects")
                for obj in self.engine.rootObjects():
                    if hasattr(obj, "deleteLater"):
                        obj.deleteLater()

            # Load the QML file
            self.engine.load(qml_url)

            # Check if QML loaded correctly
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

                raise RuntimeError("Failed to load QML interface")
            else:
                self.logger.info("QML file loaded successfully")

                # Connect to QML signals
                self._connect_qml_signals()

        except Exception as e:
            self.logger.critical(f"Error loading QML: {e}", exc_info=True)
            raise

    def _connect_qml_signals(self):
        """Connect QML signals to Python slots"""
        try:
            # Get the root object (MainWindow)
            root_objects = self.engine.rootObjects()
            if root_objects:
                root = root_objects[0]

                # Connect Python ViewModels to root properties
                root.setProperty("conversationViewModel", self.conversation_vm)
                root.setProperty("settingsViewModel", self.settings_vm)

                # Connect signals
                self.qml_bridge.connect_qml_signal("mainWindow", "fileRequested", self._handle_file_request)
                self.qml_bridge.connect_qml_signal("mainWindow", "errorOccurred", self._handle_qml_error)
                self.qml_bridge.connect_qml_signal("mainWindow", "cleanupRequested", self._handle_window_close)

                self.logger.info("Connected QML signals")
            else:
                self.logger.error("No root QML objects found - cannot connect signals")
        except Exception as e:
            self.logger.error(f"Error connecting QML signals: {e}", exc_info=True)

    # File handling helper
    def _handle_file_request(self, file_url):
        """Handle file request from QML using async file processor"""
        # Convert QML URL to Python path
        file_path = self.qml_bridge.file_url_to_path(file_url)
        self.logger.info(f"Processing file: {file_path}")

        # Start async file processing
        run_coroutine(self._process_file_async(file_path))

    async def _process_file_async(self, file_path):
        """Process file asynchronously with improved error handling"""
        try:
            # Use existing async file utilities but with proper qasync integration
            from src.utils.async_file_utils import get_file_info_async

            # Always ensure the loop is running before async operations
            ensure_qasync_loop()

            file_info = await get_file_info_async(
                file_path,
                progress_callback=lambda progress: self._update_file_progress(os.path.basename(file_path), progress)
            )

            if file_info:
                # Update file info in QML model
                model_info = {
                    "fileName": file_info["file_name"],
                    "filePath": file_path,
                    "fileSize": self.qml_bridge.format_file_size(file_info["size"]),
                    "tokenCount": file_info["token_count"]
                }

                # Use a QTimer.singleShot to safely call QML method from any thread
                QTimer.singleShot(0, lambda: self.qml_bridge.call_qml_method("mainWindow", "updateFileInfo", model_info))

                self.logger.info(f"File processed: {file_info['file_name']} "
                                 f"({file_info['token_count']} tokens)")
        except Exception as e:
            self.logger.error(f"Error in async file processing: {str(e)}", exc_info=True)
            # Use a QTimer.singleShot to safely call QML method from any thread
            file_name = os.path.basename(file_path)
            QTimer.singleShot(0, lambda: self._handle_file_error(file_name, str(e)))

    def _update_file_progress(self, file_name, progress):
        """Update file processing progress in QML with safer thread handling"""
        # Use QTimer to ensure we're on the main thread
        QTimer.singleShot(0, lambda: self.qml_bridge.call_qml_method("mainWindow", "updateFileProgress", file_name, progress))

    def _handle_file_error(self, file_name, error_message):
        """Handle file processing error"""
        self.logger.error(f"Error processing file {file_name}: {error_message}")
        # Call QML method safely on main thread
        QTimer.singleShot(0, lambda: self.qml_bridge.call_qml_method("mainWindow", "handleFileError", file_name, error_message))

    def _handle_qml_error(self, error_message):
        """Handle error from QML"""
        self.logger.error(f"Error from QML: {error_message}")


    async def _load_initial_data_async(self):
        """Async implementation of loading initial data with improved error handling"""
        # Ensure the event loop is properly running
        ensure_qasync_loop()

        # Initialize database if needed
        if not hasattr(self.db_service, '_initialized') or not self.db_service._initialized:
            self.logger.debug("Initializing database before loading data")
            result = await self.db_service.initialize()
            if not result:
                self.logger.error("Database initialization failed")
                return False

        try:
            # Load conversations
            conversations = await self._load_conversations()

            # Log the result
            count = len(conversations) if conversations else 0
            self.logger.info(f"Loaded {count} conversations")

            if conversations and count > 0:
                # Update the QML model on the main thread
                QTimer.singleShot(0, lambda: self.qml_bridge.call_qml_method(
                    "mainWindow", "updateConversationsModel", conversations
                ))

                # Load the first conversation after a short delay
                if count > 0:
                    first_id = conversations[0]['id']
                    QTimer.singleShot(100, lambda: self.conversation_vm.load_conversation(first_id))
                    return True
            else:
                # Create a new conversation if none exists
                self.logger.info("No conversations found, creating new one")
                result = await self._initialize_new_conversation()
                return result

        except Exception as e:
            self.logger.error(f"Error in load_initial_data_async: {str(e)}")
            # Try to create a new conversation as fallback
            return await self._initialize_new_conversation()

        return True

    async def _initialize_new_conversation(self):
        """Initialize a new conversation (async) with better error handling"""
        try:
            # Use the ViewModel to create a new conversation
            # We'll use a more direct approach to avoid potential issues
            ensure_qasync_loop()

            # Check if the database is initialized
            if not self.db_service._initialized:
                self.logger.warning("Database not initialized, trying to initialize")
                await self.db_service.initialize()

            # Create a new conversation
            await self.conversation_vm._create_conversation_impl("New Conversation")
            self.logger.info("Created new conversation")
            return True
        except Exception as e:
            self.logger.error(f"Error creating new conversation: {str(e)}")

            # As a last resort fallback, try a very direct approach
            try:
                self.logger.warning("Trying fallback conversation creation")
                # Create a conversation directly with the service
                conversation = await self.db_service.create_conversation("Emergency Conversation")
                if conversation:
                    self.logger.info(f"Created fallback conversation: {conversation.id}")
                    # Tell the view model to load it
                    QTimer.singleShot(0, lambda: self.conversation_vm.load_conversation(conversation.id))
                    return True
            except Exception as inner_e:
                self.logger.error(f"Fallback conversation creation failed: {str(inner_e)}")

            return False

    async def _load_conversations(self):
        """Load conversations (async) with better error handling"""
        try:
            # Make sure we have a running event loop
            loop = ensure_qasync_loop()

            # Get all conversations
            conversations = await self.db_service.get_all_conversations()

            if conversations:
                # Convert to list of dicts for the model
                conv_dicts = []
                for conv in conversations:
                    conv_dicts.append({
                        'id': conv.id,
                        'name': conv.name,
                        'created_at': conv.created_at.isoformat() if conv.created_at else None,
                        'modified_at': conv.modified_at.isoformat() if conv.modified_at else None
                    })
                return conv_dicts
            return []
        except Exception as e:
            self.logger.error(f"Error loading conversations: {str(e)}")
            # Return an empty list rather than raising an exception
            return []

    def _handle_conversations_loaded(self, conversations):
        """Handle loaded conversations on main thread"""
        count = len(conversations) if conversations else 0
        self.logger.info(f"Loaded {count} conversations")

        # Process conversations if any were loaded
        if conversations and count > 0:
            # Update the QML model
            root_objects = self.engine.rootObjects()
            if root_objects:
                self.qml_bridge.call_qml_method(
                    "mainWindow", "updateConversationsModel", conversations
                )

                # Load the first conversation after a short delay
                if count > 0:
                    first_id = conversations[0]['id']
                    QTimer.singleShot(100, lambda: self.conversation_vm.load_conversation(first_id))
        else:
            # Create a new conversation if none exists
            self.logger.info("No conversations found, creating new one")
            # Use run_coroutine instead of a direct function call
            run_coroutine(
                self._initialize_new_conversation(),
                callback=lambda result: self.logger.info(f"New conversation created: {result}"),
                error_callback=lambda e: self.logger.error(f"Error creating new conversation: {str(e)}")
            )

    def _handle_load_error(self, error_message):
        """Handle conversation loading error on main thread"""
        self.logger.error(f"Error loading conversations: {error_message}")

        # Despite error, try to create a new conversation
        self.logger.info("Creating fallback conversation due to loading error")
        run_coroutine(
            self._initialize_new_conversation(),
            callback=lambda result: self.logger.info(f"Fallback conversation created: {result}"),
            error_callback=lambda e: self.logger.error(f"Error creating fallback conversation: {str(e)}")
        )

    def _prepare_cleanup(self):
        """Prepare for cleanup - run async cleanup in the event loop"""
        run_coroutine(
            self._async_cleanup(),
            callback=lambda _: self.logger.info("Async cleanup completed"),
            error_callback=lambda e: self.logger.error(f"Error during cleanup: {str(e)}")
        )

        # Give some time for cleanup to complete before app exits
        QTimer.singleShot(500, lambda: None)

    def _setup_cleanup_handlers(self):
        """Set up cleanup handlers for application exit"""
        # Connect to app's aboutToQuit signal
        self.app.aboutToQuit.connect(self._prepare_cleanup)

    def _handle_window_close(self):
        """Handle the window close event (X button)"""
        self.logger.info("Window close event received, initiating cleanup")

        # Run cleanup in a non-blocking way
        run_coroutine(
            self._async_cleanup(),
            callback=lambda _: self._finish_application_exit(),
            error_callback=lambda e: self._emergency_exit(str(e))
        )

    def _finish_application_exit(self):
        """Finish the application exit after cleanup"""
        self.logger.info("Cleanup completed, exiting application")
        # This will trigger the aboutToQuit signal which runs _prepare_cleanup
        # We'll need to add a guard to prevent duplicate cleanup
        self.app.quit()

    def _emergency_exit(self, error_msg):
        """Handle emergency exit in case of cleanup failure"""
        self.logger.error(f"Error during cleanup: {error_msg}, forcing exit")
        self.app.exit(1)  # Exit with error code

    async def _async_cleanup(self):
        """Perform async cleanup operations before exiting"""
        # Guard against duplicate cleanup
        if hasattr(self, '_cleanup_in_progress') and self._cleanup_in_progress:
            self.logger.info("Cleanup already in progress, skipping")
            return

        self._cleanup_in_progress = True

        try:
            self.logger.info("Starting async cleanup")

            # Ensure the event loop is running for cleanup operations
            ensure_qasync_loop()

            # Add a timeout to ensure cleanup doesn't hang
            try:
                # Close database connections
                if hasattr(self, 'db_service'):
                    self.logger.info("Closing database service")
                    await self.db_service.close()

                # Close API connections
                if hasattr(self, 'api_service') and hasattr(self.api_service, 'close'):
                    self.logger.info("Closing API service")
                    await self.api_service.close()

                # Clean up conversation view model
                if hasattr(self, 'conversation_vm') and hasattr(self.conversation_vm, 'cleanup'):
                    self.logger.info("Cleaning up conversation view model")
                    await self.conversation_vm.cleanup()

                # Clean up QML bridge
                if hasattr(self, 'qml_bridge') and hasattr(self.qml_bridge, 'perform_async_cleanup'):
                    self.logger.info("Cleaning up QML bridge")
                    await self.qml_bridge.perform_async_cleanup()
            except Exception as e:
                self.logger.error(f"Error during specific cleanup step: {str(e)}")

            self.logger.info("Async cleanup completed successfully")
        except Exception as e:
            self.logger.error(f"Error during async cleanup: {str(e)}")
        finally:
            self._cleanup_in_progress = False

    def _initialize_views(self):
        """Initialize views after QML is loaded with improved async handling"""
        try:
            self.logger.info("Initializing views")

            # Get the root object (MainWindow)
            root_objects = self.engine.rootObjects()
            if not root_objects:
                self.logger.error("No root objects found, cannot show main window")
                self._show_error_window("Failed to create main window")
                return

            main_window = root_objects[0]

            # Show the main window
            self.logger.info("Showing main window")
            main_window.show()
            self.main_window_shown = True
            self.logger.info("Main window shown")

            # Delay data loading to allow UI to stabilize
            QTimer.singleShot(200, self._load_initial_data)

        except Exception as e:
            self.logger.critical(f"Error initializing views: {str(e)}")
            self._show_error_window(str(e))


def main():
    """Main application entry point with comprehensive error handling"""
    app_instance = None
    try:
        # Import qasync first to ensure it's available
        import qasync

        # Configure logging first to set up logging early
        from src.utils.logging_utils import configure_logging, get_logger
        configure_logging()
        logger = get_logger(__name__)
        logger.info("Starting OpenAI Chat application")

        # Create and run the application
        try:
            app_instance = AsyncApplication()
            logger.info("Application instance created, starting main loop")
            result = app_instance.run()
            logger.info(f"Application exited with result: {result}")
            return result
        except Exception as e:
            logger.critical(f"Error creating or running application: {e}", exc_info=True)

            # Create emergency fallback to show error
            from PyQt6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is None:
                app = QApplication(sys.argv)
            else:
                app = QApplication.instance()

            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("OpenAI Chat - Critical Error")
            msg.setText("The application could not be started due to a critical error.")
            msg.setDetailedText(f"Error: {str(e)}\n\nPlease check the logs for more details.")
            msg.exec()
            return 1

    except Exception as e:
        # Final fallback for truly catastrophic errors
        import traceback
        print(f"CRITICAL ERROR: Application failed to start: {e}")
        traceback.print_exc()

        try:
            # Try to write to a log file directly
            with open("critical_error.log", "a") as f:
                f.write(f"\n{'-' * 50}\n")
                f.write(f"{datetime.now().isoformat()} - CRITICAL ERROR: {str(e)}\n")
                f.write(traceback.format_exc())
        except:
            pass

        return 1
    finally:
        # Ensure proper shutdown of any lingering resources
        if app_instance:
            try:
                import asyncio
                if hasattr(app_instance, '_async_cleanup') and callable(app_instance._async_cleanup):
                    # Try to run cleanup synchronously as a last resort
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(app_instance._async_cleanup())
                    except Exception as e:
                        print(f"Error during emergency cleanup: {e}")
                    finally:
                        loop.close()
            except Exception as e:
                print(f"Error during final cleanup: {e}")

        # Force Python garbage collection
        import gc
        gc.collect()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Unhandled exception in main thread: {e}")
        traceback.print_exc()
        sys.exit(1)