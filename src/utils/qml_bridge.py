# src/utils/qml_bridge.py

from typing import Any, Dict, List, Optional, Callable
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, pyqtProperty, QVariant, Qt, QModelIndex
from PyQt6.QtQml import QQmlApplicationEngine, QQmlContext


class QmlBridge(QObject):
    """
    Bridge class to expose Python objects to QML

    This class provides helper methods to register Python objects as context properties
    in QML and to connect QML signals to Python slots.
    """

    def __init__(self, engine: QQmlApplicationEngine):
        super().__init__()
        self.engine = engine
        self.root_context = engine.rootContext()
        self.view_models = {}

    def register_context_property(self, name: str, obj: Any) -> None:
        """
        Register a Python object as a context property in QML

        Args:
            name: The name to use in QML
            obj: The Python object to expose to QML
        """
        self.root_context.setContextProperty(name, obj)

        # Store view models for later reference
        if name.endswith("ViewModel"):
            self.view_models[name] = obj

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
        obj = self.get_qml_object(object_name)
        if not obj:
            raise ValueError(f"QML object '{object_name}' not found")

        # Get the method
        method = getattr(obj, method_name, None)
        if not method:
            raise ValueError(f"Method '{method_name}' not found on object '{object_name}'")

        # Call the method
        return method(*args)

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
        obj = self.get_qml_object(object_name)
        if not obj:
            return False

        # Get the signal
        signal = getattr(obj, signal_name, None)
        if not signal:
            return False

        # Connect the signal
        signal.connect(callback)
        return True


class QmlModelBase(QObject):
    """
    Base class for exposing Python models to QML

    This class provides basic functionality for creating QML-compatible
    list models backed by Python data.
    """

    modelChanged = pyqtSignal()

    def __init__(self, data: List[Dict[str, Any]] = None):
        super().__init__()
        self._data = data or []
        self._role_names = {}

        # Initialize with default roles if data is provided
        if data and len(data) > 0:
            self._init_roles_from_data(data[0])

    def _init_roles_from_data(self, sample_item: Dict[str, Any]) -> None:
        """Initialize role names from a sample data item"""
        for i, key in enumerate(sample_item.keys()):
            self._role_names[i + Qt.UserRole] = key.encode()

    @pyqtProperty(list, notify=modelChanged)
    def items(self) -> List[Dict[str, Any]]:
        """Get the model data as a list"""
        return self._data

    @items.setter
    def items(self, value: List[Dict[str, Any]]) -> None:
        """Set the model data"""
        if value != self._data:
            self._data = value

            # Reinitialize roles if needed
            if value and len(value) > 0:
                self._init_roles_from_data(value[0])

            self.modelChanged.emit()

    @pyqtSlot(int, result='QVariant')
    def get(self, index: int) -> Dict[str, Any]:
        """Get an item by index"""
        if 0 <= index < len(self._data):
            return self._data[index]
        return {}

    @pyqtSlot(int, str, 'QVariant')
    def set(self, index: int, key: str, value: Any) -> None:
        """Set a property of an item"""
        if 0 <= index < len(self._data):
            self._data[index][key] = value
            self.modelChanged.emit()

    @pyqtSlot('QVariant')
    def append(self, item: Dict[str, Any]) -> None:
        """Append an item to the model"""
        self._data.append(item)
        self.modelChanged.emit()

    @pyqtSlot(int)
    def remove(self, index: int) -> None:
        """Remove an item by index"""
        if 0 <= index < len(self._data):
            del self._data[index]
            self.modelChanged.emit()

    @pyqtSlot()
    def clear(self) -> None:
        """Clear all items"""
        self._data.clear()
        self.modelChanged.emit()

    @pyqtProperty(int, notify=modelChanged)
    def count(self) -> int:
        """Get the number of items"""
        return len(self._data)


# Note: For a complete QAbstractListModel implementation,
# we'd need to subclass QAbstractListModel and implement
# the necessary methods like rowCount, data, roleNames, etc.
# For simplicity, the QmlModelBase above provides a simpler
# list model that works well for basic cases but doesn't have
# the performance benefits of QAbstractListModel for large lists.

class QmlListModel(QObject):
    """
    A more complete QML list model implementation using QAbstractListModel

    This class can be used to expose Python lists to QML with better performance
    for large datasets.
    """

    from PyQt6.QtCore import QAbstractListModel, Qt

    class PyListModel(QAbstractListModel):
        """Inner class that implements QAbstractListModel"""

        def __init__(self, data=None, parent=None):
            super().__init__(parent)
            self._data = data or []
            self._roles = {}

            # Initialize roles from first item if available
            if data and len(data) > 0:
                for i, key in enumerate(data[0].keys()):
                    self._roles[Qt.ItemDataRole.UserRole + i] = key.encode()

        def rowCount(self, parent=None):
            return len(self._data)

        def data(self, index, role):
            if not index.isValid() or not (0 <= index.row() < len(self._data)):
                return QVariant()

            item = self._data[index.row()]

            # Find the key for this role
            for r, key_bytes in self._roles.items():
                if role == r:
                    key = key_bytes.decode()
                    return item.get(key, QVariant())

            return QVariant()

        def roleNames(self):
            return self._roles

        def setData(self, index, value, role):
            if not index.isValid() or not (0 <= index.row() < len(self._data)):
                return False

            # Find the key for this role
            key = None
            for r, key_bytes in self._roles.items():
                if role == r:
                    key = key_bytes.decode()
                    break

            if key is None:
                return False

            # Update the data
            self._data[index.row()][key] = value
            self.dataChanged.emit(index, index, [role])
            return True

        def append(self, item):
            self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
            self._data.append(item)
            self.endInsertRows()

        def remove(self, index):
            if 0 <= index < len(self._data):
                self.beginRemoveRows(QModelIndex(), index, index)
                del self._data[index]
                self.endRemoveRows()

        def clear(self):
            self.beginResetModel()
            self._data.clear()
            self.endResetModel()

        def get(self, index):
            if 0 <= index < len(self._data):
                return self._data[index]
            return {}

        def update(self, new_data):
            self.beginResetModel()
            self._data = new_data

            # Update roles if needed
            if new_data and len(new_data) > 0:
                new_roles = {}
                for i, key in enumerate(new_data[0].keys()):
                    new_roles[Qt.ItemDataRole.UserRole + i] = key.encode()
                self._roles = new_roles

            self.endResetModel()

    def __init__(self, data=None):
        super().__init__()
        self._model = self.PyListModel(data)

    @pyqtProperty(QAbstractListModel, constant=True)
    def model(self):
        return self._model

    @pyqtSlot(list)
    def setItems(self, items):
        self._model.update(items)

    @pyqtSlot('QVariant')
    def append(self, item):
        self._model.append(item)

    @pyqtSlot(int)
    def remove(self, index):
        self._model.remove(index)

    @pyqtSlot()
    def clear(self):
        self._model.clear()

    @pyqtSlot(int, result='QVariant')
    def get(self, index):
        return self._model.get(index)

    @pyqtProperty(int)
    def count(self):
        return self._model.rowCount()