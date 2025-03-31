"""
Main entry point for the CannonAI application using standard PyQt threading.
"""
# 1. Standard library imports
import sys
import os
import traceback
import platform
from datetime import datetime

# 2. Third-party library imports (non-Qt)
from dotenv import load_dotenv

# 3. Logging setup (must be before other app imports)
from src.utils.logging_utils import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

# 4. Qt imports
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtQml import QQmlApplicationEngine, QQmlError
from PyQt6.QtCore import QUrl, QObject, QTimer, pyqtSlot, QCoreApplication, Qt, QThread

# 5. App-specific service imports (Synchronous/Threaded versions)
from src.services.database.conversation_service import ConversationService
from src.services.api.api_service import ApiService
from src.services.storage.settings_manager import SettingsManager

# 6. ViewModel imports (Threaded versions)
from src.viewmodels.conversation_viewmodel import ConversationViewModel
from src.viewmodels.settings_viewmodel import SettingsViewModel

# 7. Utility imports
from src.utils.qml_bridge import QmlBridge


class ApplicationController(QObject):
    """
    Main application controller using standard PyQt threading model.
    Manages initialization, QML engine, ViewModels, and application lifecycle.
    """

    def __init__(self):
        """Initialize the application controller."""
        super().__init__()
        self.logger = get_logger("ApplicationController")
        self.app = None
        self.engine = None
        self.qml_bridge = None
        self.settings_manager = None
        self.conversation_vm = None
        self.settings_vm = None
        self.api_service = None
        self.db_service = None
        self.main_window = None

        try:
            self._initialize()
        except Exception as e:
            self.logger.critical(f"CRITICAL ERROR during application initialization: {e}", exc_info=True)
            self._show_emergency_error(f"Initialization Failed: {str(e)}\n\nCheck logs for details.")
            sys.exit(1)

    def _initialize(self):
        """Initialize the application components."""
        self.logger.info("--- Starting Application Initialization (Threaded) ---")

        # 1. Initialize QApplication
        self.logger.debug("Step 1: Initializing QApplication...")
        self.app = QApplication.instance() or QApplication(sys.argv)
        QCoreApplication.setApplicationName("CannonAI")
        QCoreApplication.setOrganizationName("YourOrganization")
        QCoreApplication.setOrganizationDomain("yourdomain.com")
        self.logger.debug("QApplication initialized.")

        # 2. Set up global exception handling
        self.logger.debug("Step 2: Setting up global exception handler...")
        sys.excepthook = self._global_exception_handler
        self.logger.debug("Global exception handler set.")

        # 3. Load environment variables
        self.logger.debug("Step 3: Loading environment variables...")
        self._load_env()
        self.logger.debug("Environment variables loaded.")

        # 4. Initialize Services
        self.logger.debug("Step 4: Creating service instances...")
        self.settings_manager = SettingsManager()
        self.logger.info("Created SettingsManager instance")

        self.api_service = ApiService()
        self.logger.info("Created ApiService instance")
        api_key = os.environ.get("OPENAI_API_KEY") or self.settings_manager.get_settings().get("api_key")
        if api_key:
            self.api_service.set_api_key(api_key)
            self.logger.info("Set API key for ApiService")
        else:
            self.logger.warning("No API key found in environment or settings.")

        self.db_service = ConversationService()
        if not self.db_service._initialized:
             self.logger.critical("Database Service failed to initialize. Application might not function correctly.")
             self._show_emergency_error("Database connection failed. Check logs.")
             # sys.exit(1) # Optionally exit

        self.logger.info("Created ConversationService instance")
        self.logger.debug("Services created.")

        # 5. Initialize ViewModels
        self.logger.debug("Step 5: Initializing ViewModels...")
        self.settings_vm = SettingsViewModel()
        self.settings_vm.initialize(self.api_service)
        self.api_service.update_settings(self.settings_vm.get_settings())
        self.logger.info("Initialized SettingsViewModel.")

        self.conversation_vm = ConversationViewModel()
        self.conversation_vm.conversation_service = self.db_service
        self.conversation_vm.api_service = self.api_service
        self.conversation_vm.settings_vm = self.settings_vm
        self.logger.info("Initialized ConversationViewModel.")
        self.logger.debug("ViewModels initialized.")

        # 6. Initialize QML Engine and Bridge
        self.logger.debug("Step 6: Initializing QML engine and bridge...")
        self._initialize_qml_engine()
        self.logger.debug("QML engine and bridge initialized.")

        # 7. Register ViewModels and Bridge with QML
        self.logger.debug("Step 7: Registering context properties...")
        if self.qml_bridge:
            self.qml_bridge.register_context_property("conversationViewModel", self.conversation_vm)
            self.qml_bridge.register_context_property("settingsViewModel", self.settings_vm)
            self.qml_bridge.register_context_property("bridge", self.qml_bridge)
            self.logger.info("Registered ViewModels and Bridge with QML")
        else:
            self.logger.error("QML Bridge not initialized, cannot register properties.")
            raise RuntimeError("QML Bridge failed to initialize.")
        self.logger.debug("Context properties registered.")

        # 8. Load Main QML File
        self.logger.debug("Step 8: Loading main QML file...")
        self._load_qml()
        self.logger.debug("Main QML file loaded successfully.")

        # 9. Connect Signals
        self.logger.debug("Step 9: Connecting essential QML signals...")
        self._connect_qml_signals()
        self.logger.debug("QML signals connected.")

        # 10. Setup Application Exit Hook
        self.logger.debug("Step 10: Setting up application exit handler...")
        self.app.aboutToQuit.connect(self._on_about_to_quit)
        self.logger.debug("Application exit handler set.")

        self.logger.info("--- Application Initialization Sequence Complete ---")


    def _load_env(self):
        """Load environment variables from .env file"""
        try:
            load_dotenv()
            if os.environ.get("OPENAI_API_KEY"):
                self.logger.info("Loaded API key from environment variable.")
        except Exception as e:
            self.logger.warning(f"Could not load .env file: {e}")

    def _initialize_qml_engine(self):
        """Initialize the QML engine and the standard QML bridge."""
        try:
            self.engine = QQmlApplicationEngine()
            # Connect signals *before* loading QML
            # Connection needs the method to exist, hence defining _on_object_created
            self.engine.objectCreated.connect(self._on_object_created, Qt.ConnectionType.DirectConnection)
            self.engine.warnings.connect(self._on_qml_warning)

            self.engine.rootContext().setContextProperty("DEBUG_MODE", os.environ.get('DEBUG', 'False').lower() == 'true')

            script_dir = os.path.dirname(os.path.abspath(__file__))
            qml_dir = os.path.join(script_dir, "views", "qml")
            self.engine.addImportPath(qml_dir)
            self.engine.addImportPath(os.path.join(qml_dir, "components"))
            self.engine.addImportPath(os.path.join(qml_dir, "utils"))
            self.logger.debug(f"QML import paths added: {self.engine.importPathList()}")

            self.qml_bridge = QmlBridge(self.engine)
            if hasattr(self.qml_bridge, 'errorOccurred'):
                self.qml_bridge.errorOccurred.connect(self._on_bridge_error)

            self.logger.info("QML engine and QmlBridge initialized successfully")
        except Exception as e:
            self.logger.critical(f"Error initializing QML engine: {e}", exc_info=True)
            raise

    def _load_qml(self):
        """Load the main QML file."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            qml_path = os.path.join(script_dir, "views", "qml", "MainWindow.qml")
            if not os.path.exists(qml_path):
                raise FileNotFoundError(f"QML file not found: {qml_path}")

            self.logger.info(f"Attempting to load QML file: {qml_path}")
            qml_url = QUrl.fromLocalFile(qml_path)
            self.engine.load(qml_url)

            if not self.engine.rootObjects():
                self.logger.critical("Failed to load QML file - no root objects created.")
                raise RuntimeError("Failed to load QML interface. Check logs for QML errors.")
            else:
                self.logger.info("Root QML objects created.")
                self.main_window = self.engine.rootObjects()[0]
                if not self.main_window:
                     self.logger.error("QML loaded but main_window object is None.")
                     raise RuntimeError("Failed to get main window object after QML load.")
                elif self.main_window.objectName() != "mainWindow":
                     self.logger.warning(f"MainWindow QML root object found, but objectName is not 'mainWindow' (found: '{self.main_window.objectName()}').")

        except FileNotFoundError as e:
             self.logger.critical(f"{e}", exc_info=True)
             raise
        except Exception as e:
            self.logger.critical(f"Error during QML loading or object creation: {e}", exc_info=True)
            raise

    def _connect_qml_signals(self):
        """Connect essential QML signals to Python slots."""
        try:
            if not self.main_window:
                 self.logger.error("Cannot connect QML signals: Main window object not available.")
                 return

            if hasattr(self.main_window, 'cleanupRequested'):
                 self.main_window.cleanupRequested.connect(self._on_about_to_quit)
                 self.logger.info("Connected mainWindow.cleanupRequested signal to _on_about_to_quit.")
            else:
                 self.logger.warning("MainWindow QML object does not have 'cleanupRequested' signal.")

            if hasattr(self.main_window, 'errorOccurred'):
                 self.main_window.errorOccurred.connect(self._on_qml_error)
                 self.logger.info("Connected mainWindow.errorOccurred signal to _on_qml_error.")

        except Exception as e:
            self.logger.error(f"Error connecting QML signals: {e}", exc_info=True)

    # --- Slots for Application Lifecycle and Errors ---

    @pyqtSlot()
    def _on_about_to_quit(self):
        """Slot called before application quit."""
        self.logger.info("AboutToQuit signal received. Starting application cleanup...")
        self._cleanup()

    # ADDED this missing method
    @pyqtSlot(QObject, QUrl)
    def _on_object_created(self, obj: QObject, url: QUrl):
        """Slot connected to QQmlApplicationEngine.objectCreated signal."""
        # Check if the root object failed to load
        if obj is None and url.isValid() and url.fileName() == "MainWindow.qml":
            self.logger.error(f"Failed to create root QML object from URL: {url.toString()}. Check QML warnings.")
            # No need to raise an error here, the _load_qml method already checks rootObjects()

    @pyqtSlot(list)
    def _on_qml_warning(self, warnings: list):
        """Handle QML warnings/errors reported by the engine."""
        if warnings:
            for warning in warnings: # warnings is a list of QQmlError
                try:
                    detail = warning.toString()
                    self.logger.warning(f"QML Info: {detail}")
                    if "module \"QtQuick.Controls\" is not installed" in detail:
                        self.logger.critical("Essential QML module QtQuick.Controls not found!")
                    if "Cannot load library" in detail and "plugin.dll" in detail:
                         self.logger.critical(f"Failed to load Qt plugin: {detail}. Check PyQt6 installation.")
                    if "Type Menu unavailable" in detail or "Type MenuItem unavailable" in detail:
                         self.logger.critical(f"Basic QML Control type unavailable: {detail}. Check PyQt6 installation.")
                    if "Binding loop detected" in detail:
                        self.logger.error("QML binding loop detected - review QML bindings.")
                except Exception as e:
                    self.logger.warning(f"Error processing QML warning object: {e}")

    @pyqtSlot(str, str)
    def _on_bridge_error(self, error_type: str, message: str):
        """Handle errors reported by the QML bridge."""
        self.logger.error(f"QML Bridge Error ({error_type}): {message}")

    @pyqtSlot(str)
    def _on_qml_error(self, message: str):
        """Handles errors emitted from QML side."""
        self.logger.error(f"Error signal received from QML: {message}")

    def _cleanup(self):
        """Perform application cleanup: Stop threads, close services."""
        self.logger.info("Executing cleanup tasks...")
        if self.conversation_vm and hasattr(self.conversation_vm, 'cleanup'):
            self.logger.debug("Cleaning up ConversationViewModel...")
            try: self.conversation_vm.cleanup()
            except Exception as e: self.logger.error(f"Error cleaning up ConversationViewModel: {e}", exc_info=True)
        if self.settings_vm and hasattr(self.settings_vm, 'cleanup'):
            self.logger.debug("Cleaning up SettingsViewModel...")
            try: self.settings_vm.cleanup()
            except Exception as e: self.logger.error(f"Error cleaning up SettingsViewModel: {e}", exc_info=True)

        if self.db_service and hasattr(self.db_service, 'close'):
            self.logger.debug("Closing DB service...")
            try: self.db_service.close()
            except Exception as e: self.logger.error(f"Error closing DB service: {e}", exc_info=True)
        if self.api_service and hasattr(self.api_service, 'close'):
            self.logger.debug("Closing API service...")
            try: self.api_service.close()
            except Exception as e: self.logger.error(f"Error closing API service: {e}", exc_info=True)

        if self.qml_bridge and hasattr(self.qml_bridge, 'cleanup'):
            self.logger.debug("Cleaning up QmlBridge...")
            self.qml_bridge.cleanup()

        self.logger.info("Application cleanup finished.")

    # --- Global Error Handling ---
    def _global_exception_handler(self, exc_type, exc_value, exc_traceback):
        """Global exception handler for uncaught exceptions."""
        error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self.logger.critical(f"Unhandled exception caught by global handler:\n{error_message}")
        self._show_emergency_error(f"An unexpected error occurred: {exc_value}\n\nCheck logs for details.")
        try:
             self._cleanup()
        except Exception as cleanup_e:
             self.logger.error(f"Error during cleanup in global exception handler: {cleanup_e}", exc_info=True)
        if self.app:
             self.app.exit(1)
        else:
             sys.exit(1)

    def _show_emergency_error(self, message: str):
        """Displays a simple error message box if GUI is available."""
        self.logger.error(f"Displaying emergency error: {message}")
        try:
            app = QApplication.instance()
            if app:
                 if QThread.currentThread() != app.thread():
                      QTimer.singleShot(0, lambda: self._display_qmessagebox(message))
                 else:
                      self._display_qmessagebox(message)
            else:
                 print(f"CRITICAL ERROR (NO GUI): {message}", file=sys.stderr)
                 self._try_tkinter_fallback(message)
        except ImportError:
             print(f"CRITICAL ERROR (PyQt6.QtWidgets not available): {message}", file=sys.stderr)
             self._try_tkinter_fallback(message)
        except Exception as e:
             print(f"ERROR displaying error message: {e}", file=sys.stderr)
             print(f"Original error: {message}", file=sys.stderr)
             self._try_tkinter_fallback(message)

    def _display_qmessagebox(self, message: str):
        """Helper to display QMessageBox (must be called on main thread)."""
        try:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setWindowTitle("CannonAI - Critical Error")
            msg_box.setText("A critical error occurred:")
            msg_box.setInformativeText(message)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()
        except Exception as e:
             self.logger.error(f"Failed to display QMessageBox: {e}", exc_info=True)
             # Fallback if even QMessageBox fails
             print(f"CRITICAL ERROR (QMessageBox failed): {message}", file=sys.stderr)


    def _try_tkinter_fallback(self, message: str):
        """Attempt to show a Tkinter error box if Qt fails."""
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("CannonAI - Critical Error", f"Application failed:\n\n{message}")
            root.destroy()
        except ImportError: pass
        except Exception as tk_e: print(f"Error showing Tkinter fallback message: {tk_e}", file=sys.stderr)

    # --- Run Method ---
    def run(self):
        """Run the application's main event loop."""
        if not self.app or not self.engine or not self.main_window:
             self.logger.critical("Application not fully initialized. Cannot run.")
             self._show_emergency_error("Application failed to initialize properly.")
             return 1

        self.logger.info("Entering Qt main event loop (app.exec)...")
        result = self.app.exec()
        self.logger.info(f"Exited Qt main event loop with result: {result}")
        return result


def main():
    """Main application entry point."""
    logger.info(f"--- Starting CannonAI Application ---")
    logger.info(f"Python Version: {sys.version}")
    try: from PyQt6 import Qt
    except ImportError: Qt = None
    logger.info(f"PyQt Version: {getattr(Qt, 'PYQT_VERSION_STR', 'N/A')}")
    logger.info(f"Qt Version: {getattr(Qt, 'QT_VERSION_STR', 'N/A')}")
    logger.info(f"OS: {platform.system()} {platform.release()}")
    logger.info(f"Application Directory: {os.path.dirname(os.path.abspath(__file__))}")

    controller = None
    exit_code = 0
    try:
        controller = ApplicationController()
        exit_code = controller.run()
    except Exception as e:
        logger.critical(f"Fatal error during application startup or run: {e}", exc_info=True)
        if controller and controller.app:
             controller._show_emergency_error(f"Fatal Error: {e}\n\nCheck logs for details.")
        else:
             print(f"\nFATAL ERROR (Initialization Failed):\n{e}\n", file=sys.stderr)
             traceback.print_exc(file=sys.stderr)
             if not controller or not controller.app:
                  dummy_controller = ApplicationController() # Create dummy instance for fallback method
                  dummy_controller._try_tkinter_fallback(f"Application failed to start:\n\n{e}\n\nCheck logs for details.")
        exit_code = 1
    finally:
        logger.info(f"--- CannonAI Application Shutdown (Exit Code: {exit_code}) ---")
        return exit_code


if __name__ == "__main__":
    sys.exit(main())
