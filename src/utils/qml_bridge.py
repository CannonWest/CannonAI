# src/utils/qml_bridge.py
"""
Bridge class to expose Python objects to QML and facilitate basic communication
in a standard PyQt threading environment.
"""

# Standard library imports
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Union

# Third-party imports
from PyQt6.QtCore import QByteArray, QModelIndex, QObject, QTimer, Qt, QVariant, pyqtSignal, pyqtSlot, QUrl
from PyQt6.QtQml import QJSValue, QQmlApplicationEngine, QQmlContext

# Local application imports
from src.utils.logging_utils import get_logger

class QmlBridge(QObject):
    """
    Bridge class to expose Python objects to QML and handle basic interactions.
    Designed for use with standard PyQt threading (not asyncio/qasync).
    """
    # Signal for generic error reporting from Python to QML/logging
    errorOccurred = pyqtSignal(str, str) # error_type, message

    def __init__(self, engine: QQmlApplicationEngine):
        """
        Initialize the bridge with a QML engine.

        Args:
            engine: The QQmlApplicationEngine instance
        """
        super().__init__()
        self.engine = engine
        self.root_context = engine.rootContext()
        self.view_models = {}
        self.logger = get_logger(__name__ + ".QmlBridge") # Updated logger name
        self._registered_properties = set()
        self.logger.info("QmlBridge initialized")

    def register_context_property(self, name: str, obj: Any) -> None:
        """
        Register a Python object as a context property in QML with proper error handling.

        Args:
            name: The name to use in QML
            obj: The Python object to expose to QML
        """
        try:
            if name in self._registered_properties:
                self.logger.warning(f"Property '{name}' already registered, updating")

            self.root_context.setContextProperty(name, obj)
            self._registered_properties.add(name)

            if name.endswith("ViewModel"):
                self.view_models[name] = obj

            self.logger.debug(f"Registered context property: {name}")
        except Exception as e:
            self.logger.error(f"Failed to register context property {name}: {str(e)}")
            self.errorOccurred.emit("RegistrationError", f"Failed to register {name}: {str(e)}")

    @pyqtSlot(str, result=QObject)
    def get_view_model(self, name: str) -> Optional[QObject]:
        """
        Get a view model by name from QML.

        Args:
            name: The name of the view model (e.g., "conversationViewModel")

        Returns:
            The view model if found, None otherwise
        """
        vm = self.view_models.get(name)
        if vm:
            return vm
        # Fallback check for case variations
        for key, vm_obj in self.view_models.items():
            if key.lower() == name.lower():
                return vm_obj
        self.logger.warning(f"get_view_model: ViewModel '{name}' not found.")
        return None

    def get_qml_object(self, object_name: str) -> Optional[QObject]:
        """
        Get a QML object by name with robust error handling.

        Args:
            object_name: The objectName property of the QML object

        Returns:
            The QML object if found, None otherwise
        """
        try:
            root_objects = self.engine.rootObjects()
            if not root_objects:
                self.logger.warning("No root QML objects found")
                return None

            for root in root_objects:
                if root and root.objectName() == object_name:
                    return root
                # Recursively search children if the root itself isn't the target
                if root:
                    found = self._find_object_by_name(root, object_name)
                    if found:
                        return found

            self.logger.debug(f"QML object not found: {object_name}")
            return None
        except Exception as e:
            self.logger.error(f"Error finding QML object {object_name}: {str(e)}")
            return None

    def _find_object_by_name(self, parent: QObject, name: str) -> Optional[QObject]:
        """
        Recursively find a QML object by name.

        Args:
            parent: The parent QObject to search
            name: The objectName to find

        Returns:
            The found QObject or None
        """
        try:
            # Check children
            for child in parent.findChildren(QObject, name=name, options=Qt.FindChildOption.FindDirectChildrenOnly):
                 # Check if the direct child has the correct objectName
                 if hasattr(child, 'objectName') and child.objectName() == name:
                      return child

            # If not found in direct children, search recursively deeper
            for child in parent.children():
                 found = self._find_object_by_name(child, name)
                 if found:
                     return found

        except Exception as e:
             # Catch potential errors during traversal (e.g., object deleted)
             self.logger.warning(f"Error during QML object search: {e}")
        return None


    # Removed call_async_method, _run_async_method, cancel_task
    # The ViewModels will now handle threading and signal results back directly.

    def _process_qml_args(self, args):
        """
        Process arguments from QML to Python with improved type conversion.
        (Kept as it might still be useful for direct QML->Python slot calls)

        Args:
            args: Arguments from QML

        Returns:
            Processed Python arguments list
        """
        if args is None:
            return []

        # Handle cases where args might not be a list from QML
        if isinstance(args, (list, tuple)):
            args_list = list(args)
        else:
            args_list = [args] # Treat single value as a list with one item


        processed_args = []
        for i, arg in enumerate(args_list):
            if isinstance(arg, QJSValue):
                processed_args.append(arg.toVariant())
            elif isinstance(arg, QModelIndex) and arg.isValid():
                 # Provide more context for model index if needed
                 processed_args.append({
                     'row': arg.row(),
                     'column': arg.column(),
                     'parent_row': arg.parent().row() if arg.parent().isValid() else -1,
                     # Potentially add data from the model if accessible here
                 })
            elif isinstance(arg, QByteArray):
                try:
                    # Try decoding as UTF-8 first
                    processed_args.append(bytes(arg).decode('utf-8'))
                except UnicodeDecodeError:
                    # Fallback for non-UTF8 data (e.g., keep as bytes or try latin-1)
                    self.logger.warning(f"Argument {i} is QByteArray with non-UTF8 data, keeping as bytes.")
                    processed_args.append(bytes(arg))
            elif isinstance(arg, QUrl):
                 processed_args.append(arg.toString()) # Convert QUrl to string path/url
            else:
                # Keep other types (int, float, bool, str, dict, list) as they are
                processed_args.append(arg)

        return processed_args

    # Keep call_qml_method - still useful
    # Use QTimer.singleShot to ensure calls happen on the main thread if called from workers
    def call_qml_method(self, object_name: str, method_name: str, *args) -> None:
        """
        Safely schedule a call to a method on a QML object from any thread.

        Args:
            object_name: The objectName of the QML object
            method_name: The method to call
            *args: Arguments to pass to the method
        """
        # Use QTimer.singleShot to ensure the call happens on the main Qt thread
        QTimer.singleShot(0, lambda: self._call_qml_method_on_main_thread(object_name, method_name, *args))

    def _call_qml_method_on_main_thread(self, object_name: str, method_name: str, *args) -> None:
        """Internal method that executes the QML call on the main thread."""
        try:
            obj = self.get_qml_object(object_name)
            if not obj:
                self.logger.warning(f"QML object '{object_name}' not found for method call '{method_name}'")
                return

            method = getattr(obj, method_name, None)
            if not method or not callable(method):
                self.logger.warning(f"Method '{method_name}' not found or not callable on QML object '{object_name}'")
                return

            # Convert Python args to QVariant if necessary for QML? Usually automatic.
            # Consider potential type mismatches between Python args and QML method signatures.
            method(*args) # Call the QML method

        except Exception as e:
            self.logger.error(f"Error calling QML method {object_name}.{method_name}: {str(e)}", exc_info=True)
            self.errorOccurred.emit("QmlMethodCallError", f"Error calling {object_name}.{method_name}: {str(e)}")


    # Keep connect_qml_signal - still useful
    def connect_qml_signal(self, object_name: str, signal_name: str,
                           callback: Callable) -> bool:
        """
        Connect a QML signal to a Python callback with robust error handling.

        Args:
            object_name: The objectName of the QML object
            signal_name: The signal to connect to
            callback: The Python function/slot to call when the signal is emitted

        Returns:
            True if the connection was successful, False otherwise
        """
        try:
            obj = self.get_qml_object(object_name)
            if not obj:
                self.logger.warning(f"QML object not found for signal connection: {object_name}")
                return False

            # Access the signal attribute dynamically
            signal_attr = getattr(obj, signal_name, None)

            # Check if the attribute exists and has a 'connect' method (typical for signals)
            if signal_attr is None or not hasattr(signal_attr, 'connect') or not callable(signal_attr.connect):
                self.logger.warning(f"Signal '{signal_name}' not found or not connectable on QML object '{object_name}'")
                # Log available members for debugging if object exists
                # if obj: self.logger.debug(f"Available members on {object_name}: {dir(obj)}")
                return False

            # Connect the signal to the callback
            signal_attr.connect(callback)
            self.logger.debug(f"Connected QML signal {object_name}.{signal_name} to Python callback {callback.__name__}")
            return True

        except Exception as e:
            self.logger.error(f"Error connecting QML signal {object_name}.{signal_name}: {str(e)}", exc_info=True)
            self.errorOccurred.emit("SignalConnectionError", f"Error connecting {signal_name}: {str(e)}")
            return False

    # Keep logging slots - still useful
    @pyqtSlot(str, str)
    def log_from_qml(self, level: str, message: str) -> None:
        """
        Log a message from QML.

        Args:
            level: Log level (debug, info, warning, error, critical) - case-insensitive
            message: Message to log
        """
        level_lower = level.lower()
        log_func = getattr(self.logger, level_lower, self.logger.info) # Default to info
        log_func(f"QML: {message}")


    @pyqtSlot(str, str)
    def log_error_from_qml(self, error_type: str, message: str) -> None:
        """
        Report an error from QML.

        Args:
            error_type: Type of error
            message: Error message
        """
        self.logger.error(f"QML Error ({error_type}): {message}")
        self.errorOccurred.emit(error_type, message) # Emit signal for potential Python handling


    # Keep utility slots - still useful
    @pyqtSlot(str, result=str)
    def file_url_to_path(self, file_url: str) -> str:
        """
        Convert a QML file URL to a file path.

        Args:
            file_url: QML file URL (e.g., "file:///C:/path/to/file.txt")

        Returns:
            File path (e.g., "C:/path/to/file.txt")
        """
        # Improved handling for different OS and URL formats
        if file_url.startswith("file://"):
            path = file_url[len("file://"):]
            # Handle Windows paths starting with /C:/
            if sys.platform == "win32" and path.startswith("/"):
                 # Remove leading slash only if it's followed by a drive letter pattern
                 if len(path) > 2 and path[1] == ":" and path[2] == "/":
                      path = path[1:]
            # Handle standard Unix paths where // means localhost
            elif not sys.platform == "win32" and path.startswith("//"):
                 path = path[1:] # Keep one slash for root /

            # Decode URL encoding
            from urllib.parse import unquote
            return unquote(path)

        return file_url # Return as is if not starting with file://


    @pyqtSlot(int, result=str)
    def format_file_size(self, size: int) -> str:
        """
        Format a file size in bytes to a human-readable string.

        Args:
            size: Size in bytes

        Returns:
            Formatted string (e.g., "1.2 MB")
        """
        if size < 0: return "Invalid size"
        if size == 0: return "0 B"
        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
        i = 0
        while size >= 1024 and i < len(units) - 1:
            size /= 1024.0
            i += 1
        # Format with 1 decimal place if not bytes, otherwise 0
        f = "{:.1f}" if i > 0 else "{:.0f}"
        return f.format(size) + f" {units[i]}"

    # Removed perform_async_cleanup
    def cleanup(self):
        """Synchronous cleanup for the bridge."""
        self.logger.info("QmlBridge cleanup initiated.")
        # Clear references - Python garbage collector will handle the objects
        self.view_models.clear()
        self._registered_properties.clear()
        self.logger.info("QmlBridge cleanup finished.")
