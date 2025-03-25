# Standard library imports
import asyncio
import time
import traceback
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, Union

# Third-party imports
from PyQt6.QtCore import QByteArray, QModelIndex, QObject, QTimer, Qt, QVariant, pyqtSignal, pyqtSlot
from PyQt6.QtQml import QJSValue, QQmlApplicationEngine, QQmlContext

# Local application imports
from src.utils.logging_utils import get_logger
from src.utils.qasync_bridge import ensure_qasync_loop, run_coroutine

class AsyncQmlBridge(QObject):
    """
    Enhanced bridge class to expose Python objects to QML with reliable qasync support.

    This class provides a robust way to:
    1. Register Python objects in the QML context
    2. Call async methods from QML and handle results properly
    3. Connect Python signals to QML and vice versa
    4. Run async code safely from sync code
    """
    # Define signals for error reporting and task tracking
    errorOccurred = pyqtSignal(str, str)
    taskStarted = pyqtSignal(str)
    taskFinished = pyqtSignal(str, 'QVariant')
    taskError = pyqtSignal(str, str)
    taskProgress = pyqtSignal(str, int)

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
        self.logger = get_logger(__name__)

        # Dictionary to track running tasks and registered properties
        self._tasks = {}
        self._registered_properties = set()

        # Set up automatic cleanup on Python exit
        self._async_cleanup_pending = False

        # Log initialization
        self.logger.info("AsyncQmlBridge initialized")

    def register_context_property(self, name: str, obj: Any) -> None:
        """
        Register a Python object as a context property in QML with proper error handling.

        Args:
            name: The name to use in QML
            obj: The Python object to expose to QML
        """
        try:
            # Check if already registered to avoid duplicates
            if name in self._registered_properties:
                self.logger.warning(f"Property '{name}' already registered, updating")

            # Set the context property
            self.root_context.setContextProperty(name, obj)
            self._registered_properties.add(name)

            # Store view models separately for easy access
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
        if name in self.view_models:
            return self.view_models[name]

        # Try with different cases (QML is sometimes case-insensitive)
        for key, vm in self.view_models.items():
            if key.lower() == name.lower():
                return vm

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

            # First check root objects
            for obj in root_objects:
                # Try to find by objectName property
                if obj.objectName() == object_name:
                    return obj

                # Recursively search children
                found = self._find_object_by_name(obj, object_name)
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
        # Check children
        for child in parent.children():
            if hasattr(child, 'objectName') and child.objectName() == name:
                return child

            # Recursively search grandchildren
            found = self._find_object_by_name(child, name)
            if found:
                return found

        return None

    @pyqtSlot(str, str, 'QVariant', result=str)
    def call_async_method(self, object_name: str, method_name: str, args=None) -> str:
        """
        Call an async method on a Python object from QML using qasync with reliable task tracking.

        Args:
            object_name: The name of the object (e.g., "conversationViewModel")
            method_name: The method to call
            args: Arguments to pass to the method

        Returns:
            Task ID that can be used to track the task
        """
        try:
            # Generate a unique task ID
            task_id = str(uuid.uuid4())
            self.logger.debug(f"Call async method: {object_name}.{method_name} (task_id={task_id})")

            # Get the object
            obj = self.view_models.get(object_name)
            if not obj:
                obj = self.get_qml_object(object_name)

            if not obj:
                error_msg = f"Object '{object_name}' not found"
                self.logger.error(error_msg)
                self.errorOccurred.emit("ObjectNotFound", error_msg)
                return ""

            # Get the method
            method = getattr(obj, method_name, None)
            if not method:
                error_msg = f"Method '{method_name}' not found on object '{object_name}'"
                self.logger.error(error_msg)
                self.errorOccurred.emit("MethodNotFound", error_msg)
                return ""

            # Process arguments from QML to Python
            processed_args = self._process_qml_args(args)

            # Check if the method is a coroutine function
            if asyncio.iscoroutinefunction(method):
                # It's an async method, run it with our improved run_coroutine
                self._run_async_method(task_id, method, processed_args)
            else:
                # It's a regular method, run it directly and emit result
                try:
                    result = method(*processed_args)
                    self.taskFinished.emit(task_id, result)
                except Exception as e:
                    self.logger.error(f"Error calling sync method {method_name}: {str(e)}")
                    self.taskError.emit(task_id, str(e))

            return task_id

        except Exception as e:
            self.logger.error(f"Error in call_async_method: {str(e)}", exc_info=True)
            self.errorOccurred.emit("MethodCallError", f"Error calling {method_name}: {str(e)}")
            return ""

    def _run_async_method(self, task_id: str, method: Callable, args: List):
        """
        Run an async method using qasync and handle the result with proper tracking.

        Args:
            task_id: Unique ID for tracking the task
            method: The async method to call
            args: Arguments to pass to the method
        """
        self.taskStarted.emit(task_id)

        def on_success(result):
            """Handle successful completion"""
            self.logger.debug(f"Task {task_id} completed successfully")
            self.taskFinished.emit(task_id, result)

            # Clean up task tracking
            if task_id in self._tasks:
                del self._tasks[task_id]

        def on_error(error):
            """Handle task error"""
            error_msg = str(error)
            self.logger.error(f"Task {task_id} failed: {error_msg}")
            self.taskError.emit(task_id, error_msg)

            # Clean up task tracking
            if task_id in self._tasks:
                del self._tasks[task_id]

        def on_progress(progress):
            """Handle progress updates"""
            self.taskProgress.emit(task_id, progress)

        # Run the coroutine using improved run_coroutine with timeout
        try:
            # Make sure event loop is properly running
            ensure_qasync_loop()

            # Call the method with args to get the coroutine
            coro = method(*args)

            # Run the coroutine with our wrapper
            runner = run_coroutine(
                coro,
                callback=on_success,
                error_callback=on_error,
                timeout=60  # Default 60 second timeout
            )

            # Track the runner for potential cancellation
            self._tasks[task_id] = runner

        except Exception as e:
            on_error(e)

    def _process_qml_args(self, args):
        """
        Process arguments from QML to Python with improved type conversion.

        Args:
            args: Arguments from QML

        Returns:
            Processed Python arguments
        """
        if args is None:
            return []

        # If it's a single value, make it a list
        if not isinstance(args, list):
            args = [args]

        # Convert QJSValue and other Qt types to Python
        processed_args = []
        for arg in args:
            # Handle QJSValue
            if isinstance(arg, QJSValue):
                processed_args.append(arg.toVariant())
            # Handle Qt model index
            elif isinstance(arg, QModelIndex):
                processed_args.append({
                    'row': arg.row(),
                    'column': arg.column(),
                    'valid': arg.isValid()
                })
            # Handle QByteArray
            elif isinstance(arg, QByteArray):
                processed_args.append(bytes(arg))
            else:
                processed_args.append(arg)

        return processed_args

    @pyqtSlot(str)
    def cancel_task(self, task_id: str):
        """
        Cancel a running task.

        Args:
            task_id: ID of the task to cancel
        """
        if task_id in self._tasks:
            self.logger.debug(f"Cancelling task {task_id}")
            runner = self._tasks[task_id]

            if hasattr(runner, 'cancel'):
                runner.cancel()

            del self._tasks[task_id]
            self.logger.info(f"Task {task_id} cancelled")

    def call_qml_method(self, object_name: str, method_name: str, *args) -> Any:
        """
        Call a method on a QML object with proper thread safety.

        Args:
            object_name: The objectName of the QML object
            method_name: The method to call
            *args: Arguments to pass to the method

        Returns:
            The result of the method call
        """
        try:
            obj = self.get_qml_object(object_name)
            if not obj:
                self.logger.warning(f"QML object '{object_name}' not found")
                return None

            # Get the method
            method = getattr(obj, method_name, None)
            if not method:
                self.logger.warning(f"Method '{method_name}' not found on object '{object_name}'")
                return None

            # Call the method and return the result
            return method(*args)
        except Exception as e:
            self.logger.error(f"Error calling QML method {method_name}: {str(e)}")
            self.errorOccurred.emit("MethodCallError", f"Error calling {method_name}: {str(e)}")
            return None

    def connect_qml_signal(self, object_name: str, signal_name: str,
                           callback: Callable) -> bool:
        """
        Connect a QML signal to a Python callback with robust error handling.

        Args:
            object_name: The objectName of the QML object
            signal_name: The signal to connect to
            callback: The Python function to call when the signal is emitted

        Returns:
            True if the connection was successful, False otherwise
        """
        try:
            obj = self.get_qml_object(object_name)
            if not obj:
                self.logger.warning(f"QML object not found: {object_name}")
                return False

            # Get the signal
            signal = getattr(obj, signal_name, None)
            if not signal or not callable(getattr(signal, 'connect', None)):
                self.logger.warning(f"Signal not found or not connectable: {signal_name}")
                return False

            # Connect the signal
            signal.connect(callback)
            self.logger.debug(f"Connected signal {object_name}.{signal_name}")
            return True
        except Exception as e:
            self.logger.error(f"Error connecting signal {signal_name}: {str(e)}")
            self.errorOccurred.emit("SignalConnectionError", f"Error connecting {signal_name}: {str(e)}")
            return False

    @pyqtSlot(str, str)
    def log_from_qml(self, level: str, message: str) -> None:
        """
        Log a message from QML.

        Args:
            level: Log level (debug, info, warning, error, critical)
            message: Message to log
        """
        if not self.logger:
            print(f"[{level.upper()}] {message}")
            return

        level = level.lower()
        if level == "debug":
            self.logger.debug(f"QML: {message}")
        elif level == "info":
            self.logger.info(f"QML: {message}")
        elif level == "warning":
            self.logger.warning(f"QML: {message}")
        elif level == "error":
            self.logger.error(f"QML: {message}")
        elif level == "critical":
            self.logger.critical(f"QML: {message}")
        else:
            self.logger.info(f"QML: {message}")

    @pyqtSlot(str, str)
    def log_error_from_qml(self, error_type: str, message: str) -> None:
        """
        Report an error from QML.

        Args:
            error_type: Type of error
            message: Error message
        """
        self.logger.error(f"QML Error ({error_type}): {message}")
        self.errorOccurred.emit(error_type, message)

    @pyqtSlot(str, result=str)
    def file_url_to_path(self, file_url: str) -> str:
        """
        Convert a QML file URL to a file path.

        Args:
            file_url: QML file URL (e.g., "file:///C:/path/to/file.txt")

        Returns:
            File path (e.g., "C:/path/to/file.txt")
        """
        import sys

        if file_url.startswith("file:///"):
            if sys.platform == "win32":
                # Windows paths
                return file_url[8:]
            else:
                # Unix paths
                return file_url[7:]
        return file_url

    @pyqtSlot(int, result=str)
    def format_file_size(self, size: int) -> str:
        """
        Format a file size in bytes to a human-readable string.

        Args:
            size: Size in bytes

        Returns:
            Formatted string (e.g., "1.2 MB")
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    async def perform_async_cleanup(self):
        """
        Clean up async resources before application shutdown.

        This method should be called before application shutdown to ensure
        proper cleanup of async resources.
        """
        if self._async_cleanup_pending:
            self.logger.debug("Cleanup already in progress, skipping")
            return

        self._async_cleanup_pending = True
        self.logger.info("Starting AsyncQmlBridge cleanup")

        try:
            # Ensure the event loop is running for cleanup
            loop = ensure_qasync_loop()

            # Cancel all running tasks
            for task_id, runner in list(self._tasks.items()):
                try:
                    if hasattr(runner, 'cancel'):
                        runner.cancel()
                        self.logger.debug(f"Cancelled task {task_id}")
                except Exception as e:
                    self.logger.warning(f"Error cancelling task {task_id}: {str(e)}")

            self._tasks.clear()

            # Clean up view models
            for name, vm in list(self.view_models.items()):
                try:
                    if hasattr(vm, 'cleanup'):
                        self.logger.debug(f"Cleaning up view model {name}")
                        if asyncio.iscoroutinefunction(vm.cleanup):
                            await vm.cleanup()
                        else:
                            vm.cleanup()
                except Exception as e:
                    self.logger.warning(f"Error cleaning up view model {name}: {str(e)}")

            # Clear references to QML objects
            self._registered_properties.clear()

            self.logger.info("AsyncQmlBridge cleanup completed")
        except Exception as e:
            self.logger.error(f"Error during AsyncQmlBridge cleanup: {str(e)}")
        finally:
            self._async_cleanup_pending = False