"""
Enhanced QML bridge with qasync support for better integration with PyQt.
"""

import asyncio
from typing import Any, Dict, List, Optional, Callable, Union, Type, Awaitable
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, pyqtProperty, QVariant, Qt, QModelIndex, QByteArray
from PyQt6.QtQml import QQmlApplicationEngine, QQmlContext, QJSValue

from src.utils.qasync_bridge import run_coroutine, ensure_qasync_loop
from src.utils.logging_utils import get_logger


class AsyncQmlBridge(QObject):
    """
    Enhanced bridge class to expose Python objects to QML with qasync support

    This class adds support for calling async methods from QML and handling
    the results with callbacks or events.
    """
    # Add error signal
    errorOccurred = pyqtSignal(str, str)

    # Add task signals
    taskStarted = pyqtSignal(str)
    taskFinished = pyqtSignal(str, 'QVariant')
    taskError = pyqtSignal(str, str)

    def __init__(self, engine: QQmlApplicationEngine):
        super().__init__()
        self.engine = engine
        self.root_context = engine.rootContext()
        self.view_models = {}
        self.logger = get_logger(__name__)

        # Dictionary to track running tasks
        self._tasks = {}

        # Set up cleanup
        self._async_cleanup_pending = False

    def register_context_property(self, name: str, obj: Any) -> None:
        """
        Register a Python object as a context property in QML

        Args:
            name: The name to use in QML
            obj: The Python object to expose to QML
        """
        try:
            self.root_context.setContextProperty(name, obj)

            # Store view models for later reference
            if name.endswith("ViewModel"):
                self.view_models[name] = obj

            if self.logger:
                self.logger.debug(f"Registered context property: {name}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to register context property {name}: {str(e)}")
            self.errorOccurred.emit("RegistrationError", f"Failed to register {name}: {str(e)}")

    @pyqtSlot(str, result=QObject)
    def get_view_model(self, name: str) -> Optional[QObject]:
        """
        Get a view model by name from QML

        Args:
            name: The name of the view model (e.g., "conversationViewModel")

        Returns:
            The view model if found, None otherwise
        """
        return self.view_models.get(name)

    def get_qml_object(self, object_name: str) -> Optional[QObject]:
        """
        Get a QML object by name

        Args:
            object_name: The objectName property of the QML object

        Returns:
            The QML object if found, None otherwise
        """
        root_objects = self.engine.rootObjects()
        if not root_objects:
            return None

        for obj in root_objects:
            # Try to find by objectName property
            if obj.objectName() == object_name:
                return obj

            # Recursively search children
            found = self._find_object_by_name(obj, object_name)
            if found:
                return found

        return None

    def _find_object_by_name(self, parent: QObject, name: str) -> Optional[QObject]:
        """Recursively find a QML object by name"""
        # Check children
        for child in parent.children():
            if child.objectName() == name:
                return child

            # Recursively search grandchildren
            found = self._find_object_by_name(child, name)
            if found:
                return found

        return None

    @pyqtSlot(str, str, 'QVariant', result=str)
    def call_async_method(self, object_name: str, method_name: str, args=None) -> str:
        """
        Call an async method on a Python object from QML using qasync

        Args:
            object_name: The name of the object (e.g., "conversationViewModel")
            method_name: The method to call
            args: Arguments to pass to the method

        Returns:
            Task ID that can be used to track the task
        """
        try:
            # Generate a unique task ID
            import uuid
            task_id = str(uuid.uuid4())

            # Get the object
            obj = self.view_models.get(object_name)
            if not obj:
                obj = self.get_qml_object(object_name)

            if not obj:
                raise ValueError(f"Object '{object_name}' not found")

            # Get the method
            method = getattr(obj, method_name, None)
            if not method:
                raise ValueError(f"Method '{method_name}' not found on object '{object_name}'")

            # Process arguments
            processed_args = self._process_qml_args(args)

            # Check if the method is a coroutine function
            if asyncio.iscoroutinefunction(method):
                # It's an async method, run it with run_coroutine
                self._run_async_method(task_id, method, processed_args)
            else:
                # It's a regular method, run it directly and emit result
                result = method(*processed_args)
                self.taskFinished.emit(task_id, result)

            return task_id

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error calling async method {method_name}: {str(e)}")
            self.errorOccurred.emit("MethodCallError", f"Error calling {method_name}: {str(e)}")
            return ""

    def _run_async_method(self, task_id: str, method: Callable, args: List):
        """Run an async method using qasync and handle the result"""
        self.taskStarted.emit(task_id)

        def on_success(result):
            self.taskFinished.emit(task_id, result)
            if task_id in self._tasks:
                del self._tasks[task_id]

        def on_error(error):
            error_msg = str(error)
            self.logger.error(f"Task {task_id} failed: {error_msg}")
            self.taskError.emit(task_id, error_msg)
            if task_id in self._tasks:
                del self._tasks[task_id]

        # Run the coroutine using run_coroutine instead of creating threads
        try:
            coro = method(*args)
            task = run_coroutine(coro, on_success, on_error)
            self._tasks[task_id] = task
        except Exception as e:
            on_error(e)

    def _process_qml_args(self, args):
        """Process arguments from QML to Python"""
        if args is None:
            return []

        # If it's a single value, make it a list
        if not isinstance(args, list):
            args = [args]

        # Convert QJSValue to Python
        processed_args = []
        for arg in args:
            if isinstance(arg, QJSValue):
                processed_args.append(arg.toVariant())
            else:
                processed_args.append(arg)

        return processed_args

    @pyqtSlot(str)
    def cancel_task(self, task_id: str):
        """Cancel a running task"""
        if task_id in self._tasks:
            self.logger.debug(f"Cancelling task {task_id}")
            task = self._tasks[task_id]
            if hasattr(task, 'cancel'):
                task.cancel()
            del self._tasks[task_id]

    def call_qml_method(self, object_name: str, method_name: str, *args) -> Any:
        """
        Call a method on a QML object

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
                raise ValueError(f"QML object '{object_name}' not found")

            # Get the method
            method = getattr(obj, method_name, None)
            if not method:
                raise ValueError(f"Method '{method_name}' not found on object '{object_name}'")

            # Call the method
            return method(*args)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error calling QML method {method_name}: {str(e)}")
            self.errorOccurred.emit("MethodCallError", f"Error calling {method_name}: {str(e)}")
            return None

    def connect_qml_signal(self, object_name: str, signal_name: str,
                           callback: Callable) -> bool:
        """
        Connect a QML signal to a Python callback

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
                if self.logger:
                    self.logger.warning(f"QML object not found: {object_name}")
                return False

            # Get the signal
            signal = getattr(obj, signal_name, None)
            if not signal:
                if self.logger:
                    self.logger.warning(f"Signal not found: {signal_name}")
                return False

            # Connect the signal
            signal.connect(callback)
            if self.logger:
                self.logger.debug(f"Connected signal {object_name}.{signal_name}")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error connecting signal {signal_name}: {str(e)}")
            self.errorOccurred.emit("SignalConnectionError", f"Error connecting {signal_name}: {str(e)}")
            return False

    @pyqtSlot(str, str)
    def log_from_qml(self, level: str, message: str) -> None:
        """
        Log a message from QML

        Args:
            level: Log level (debug, info, warning, error, critical)
            message: Message to log
        """
        if not self.logger:
            print(f"[{level.upper()}] {message}")
            return

        level = level.lower()
        if level == "debug":
            self.logger.debug(message)
        elif level == "info":
            self.logger.info(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        elif level == "critical":
            self.logger.critical(message)
        else:
            self.logger.info(message)

    @pyqtSlot(str, str)
    def report_error_from_qml(self, error_type: str, message: str) -> None:
        """
        Report an error from QML

        Args:
            error_type: Type of error
            message: Error message
        """
        if self.logger:
            self.logger.error(f"QML Error ({error_type}): {message}")
        self.errorOccurred.emit(error_type, message)

    @pyqtSlot(str, result=str)
    def file_url_to_path(self, file_url: str) -> str:
        """
        Convert a QML file URL to a file path

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
        Format a file size in bytes to a human-readable string

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
        Clean up async resources

        This method should be called before application shutdown
        """
        if self._async_cleanup_pending:
            return

        self._async_cleanup_pending = True

        # Clean up running tasks
        for task_id, task in list(self._tasks.items()):
            try:
                if hasattr(task, 'cancel'):
                    task.cancel()
            except Exception as e:
                self.logger.error(f"Error cancelling task {task_id}: {str(e)}")

        self._tasks.clear()

        # Clean up view models
        for name, vm in list(self.view_models.items()):
            try:
                if hasattr(vm, 'cleanup'):
                    if asyncio.iscoroutinefunction(vm.cleanup):
                        await vm.cleanup()
                    else:
                        vm.cleanup()
            except Exception as e:
                self.logger.error(f"Error cleaning up view model {name}: {str(e)}")

        self.logger.info("AsyncQmlBridge cleanup completed")