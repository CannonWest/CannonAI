# src/utils/qml_bridge.py

from typing import Any, Dict, List, Optional, Callable, Union, Type
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, pyqtProperty, QVariant, Qt, QModelIndex, QByteArray
from PyQt6.QtQml import QQmlApplicationEngine, QQmlContext, QJSValue


class QmlBridge(QObject):
    """
    Bridge class to expose Python objects to QML

    This class provides helper methods to register Python objects as context properties
    in QML and to connect QML signals to Python slots.
    """
    # Add error signal
    errorOccurred = pyqtSignal(str, str)

    def __init__(self, engine: QQmlApplicationEngine):
        super().__init__()
        self.engine = engine
        self.root_context = engine.rootContext()
        self.view_models = {}
        self.logger = None

        try:
            from src.utils.logging_utils import get_logger
            self.logger = get_logger(__name__)
        except ImportError:
            import logging
            self.logger = logging.getLogger(__name__)

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

    @pyqtSlot(str, str, str)
    def debug_object(self, object_name, property_name, context=""):
        """Debug a QML object property"""
        try:
            obj = self.get_qml_object(object_name)
            if not obj:
                self.logger.warning(f"DEBUG: QML object not found: {object_name} (context: {context})")
                return "Object not found"

            # Get the property
            if not property_name:
                # Just check if object exists
                self.logger.debug(f"DEBUG: QML object exists: {object_name} (context: {context})")
                return "Object exists"

            value = obj.property(property_name)
            if value is None:
                self.logger.warning(f"DEBUG: Property not found: {property_name} on {object_name} (context: {context})")
                return "Property not found"

            self.logger.debug(f"DEBUG: {object_name}.{property_name} = {value} (context: {context})")
            return str(value)
        except Exception as e:
            self.logger.error(f"DEBUG ERROR: {str(e)} (context: {context})")
            return f"Error: {str(e)}"

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


class QmlListModel(QObject):
    """
    A more complete QML list model implementation using QAbstractListModel

    This class can be used to expose Python lists to QML with better performance
    for large datasets and type conversion support.
    """

    from PyQt6.QtCore import QAbstractListModel, Qt

    modelChanged = pyqtSignal()

    class PyListModel(QAbstractListModel):
        """Inner class that implements QAbstractListModel"""

        def __init__(self, data=None, role_types=None, parent=None):
            super().__init__(parent)
            self._data = data or []
            self._roles = {}
            self._role_names = {}
            self._role_types = role_types or {}
            self._type_converters = {
                str: lambda x: str(x),
                int: lambda x: int(x) if x is not None else 0,
                float: lambda x: float(x) if x is not None else 0.0,
                bool: lambda x: bool(x),
                list: lambda x: list(x) if x is not None else [],
                dict: lambda x: dict(x) if x is not None else {},
                datetime: lambda x: x.isoformat() if isinstance(x, datetime) else str(x)
            }

            # Initialize roles from first item if available
            if data and len(data) > 0:
                self._initialize_roles(data[0])

        def _initialize_roles(self, sample_item):
            """Initialize role mappings from a sample item"""
            if not sample_item:
                return

            roles = {}
            for i, key in enumerate(sample_item.keys()):
                role = Qt.ItemDataRole.UserRole + i
                roles[role] = key.encode()
                self._roles[key] = role

            self._role_names = roles

        def roleNames(self):
            """Return the role names for QML"""
            return self._role_names

        def rowCount(self, parent=None):
            """Return the number of rows in the model"""
            return len(self._data)

        def data(self, index, role):
            """Return data for the specified index and role"""
            if not index.isValid() or not (0 <= index.row() < len(self._data)):
                return QVariant()

            item = self._data[index.row()]

            # Find the role name
            for role_id, role_name_bytes in self._role_names.items():
                if role == role_id:
                    role_name = role_name_bytes.decode()
                    if role_name in item:
                        # Convert value based on role type if specified
                        value = item[role_name]
                        if role_name in self._role_types and value is not None:
                            expected_type = self._role_types[role_name]
                            converter = self._type_converters.get(expected_type)
                            if converter and not isinstance(value, expected_type):
                                try:
                                    value = converter(value)
                                except (ValueError, TypeError):
                                    # If conversion fails, return the original value
                                    pass
                        return value

            return QVariant()

        def setData(self, index, value, role):
            """Set data for the specified index and role"""
            if not index.isValid() or not (0 <= index.row() < len(self._data)):
                return False

            # Find the role name
            role_name = None
            for r, name_bytes in self._role_names.items():
                if role == r:
                    role_name = name_bytes.decode()
                    break

            if role_name is None:
                return False

            # Convert QJSValue if needed
            if isinstance(value, QJSValue):
                value = value.toVariant()

            # Convert value based on role type if specified
            if role_name in self._role_types and value is not None:
                expected_type = self._role_types[role_name]
                converter = self._type_converters.get(expected_type)
                if converter and not isinstance(value, expected_type):
                    try:
                        value = converter(value)
                    except (ValueError, TypeError):
                        # If conversion fails, use the original value
                        pass

            # Update the data
            self._data[index.row()][role_name] = value
            self.dataChanged.emit(index, index, [role])
            return True

        def flags(self, index):
            """Return the item flags for the specified index"""
            if not index.isValid():
                return Qt.ItemFlag.NoItemFlags

            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable

        def insertRows(self, row, count, parent=None):
            """Insert rows into the model"""
            if parent is None:
                parent = QModelIndex()

            if row < 0 or row > len(self._data):
                return False

            self.beginInsertRows(parent, row, row + count - 1)

            # Create empty items
            for i in range(count):
                self._data.insert(row + i, {})

            self.endInsertRows()
            return True

        def removeRows(self, row, count, parent=None):
            """Remove rows from the model"""
            if parent is None:
                parent = QModelIndex()

            if row < 0 or row + count > len(self._data):
                return False

            self.beginRemoveRows(parent, row, row + count - 1)

            # Remove items
            del self._data[row:row + count]

            self.endRemoveRows()
            return True

        def append(self, item):
            """Append an item to the model"""
            # Initialize roles if this is the first item
            if not self._role_names and len(self._data) == 0:
                self._initialize_roles(item)

            self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
            self._data.append(item)
            self.endInsertRows()
            return True

        def insert(self, index, item):
            """Insert an item at the specified index"""
            if index < 0 or index > len(self._data):
                return False

            # Initialize roles if this is the first item
            if not self._role_names and len(self._data) == 0:
                self._initialize_roles(item)

            self.beginInsertRows(QModelIndex(), index, index)
            self._data.insert(index, item)
            self.endInsertRows()
            return True

        def remove(self, index):
            """Remove an item at the specified index"""
            if not (0 <= index < len(self._data)):
                return False

            self.beginRemoveRows(QModelIndex(), index, index)
            del self._data[index]
            self.endRemoveRows()
            return True

        def clear(self):
            """Clear all items from the model"""
            if not self._data:
                return

            self.beginResetModel()
            self._data = []
            self.endResetModel()

        def get(self, index):
            """Get the item at the specified index"""
            if 0 <= index < len(self._data):
                return self._data[index]
            return {}

        def update(self, new_data):
            """Update the model with new data"""
            self.beginResetModel()

            # Save the old roles in case new_data is empty
            old_roles = self._role_names.copy()
            old_role_mappings = self._roles.copy()

            self._data = new_data

            # Update roles if we have data
            if new_data and len(new_data) > 0:
                self._initialize_roles(new_data[0])
            else:
                # Restore old roles if new_data is empty
                self._role_names = old_roles
                self._roles = old_role_mappings

            self.endResetModel()

    def __init__(self, data=None, role_types=None):
        """
        Initialize the QML list model

        Args:
            data: Initial data for the model
            role_types: Dictionary mapping role names to Python types for automatic conversion
        """
        super().__init__()
        self._model = self.PyListModel(data, role_types)

    @pyqtProperty(QAbstractListModel, constant=True)
    def model(self):
        """Get the QAbstractListModel for QML"""
        return self._model

    @pyqtSlot(list)
    def setItems(self, items):
        """Set the model data from a list of items"""
        self._model.update(items)
        self.modelChanged.emit()

    @pyqtSlot(dict)
    def append(self, item):
        """Append an item to the model"""
        self._model.append(item)
        self.modelChanged.emit()

    @pyqtSlot(int, dict)
    def insert(self, index, item):
        """Insert an item at the specified index"""
        self._model.insert(index, item)
        self.modelChanged.emit()

    @pyqtSlot(int)
    def remove(self, index):
        """Remove an item at the specified index"""
        self._model.remove(index)
        self.modelChanged.emit()

    @pyqtSlot()
    def clear(self):
        """Clear all items from the model"""
        self._model.clear()
        self.modelChanged.emit()

    @pyqtSlot(int, result='QVariant')
    def get(self, index):
        """Get an item by index"""
        return self._model.get(index)

    @pyqtSlot(int, str, 'QVariant')
    def set(self, index, key, value):
        """Set a property of an item"""
        model_index = self._model.index(index, 0)
        role = self._model._roles.get(key)
        if role:
            self._model.setData(model_index, value, role)
            self.modelChanged.emit()
            return True
        return False

    @pyqtProperty(int, notify=modelChanged)
    def count(self):
        """Get the number of items in the model"""
        return self._model.rowCount()