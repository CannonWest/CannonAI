# src/utils/reactive.py

from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic, Union
import rx
from rx import operators as ops
from rx.subject import Subject, BehaviorSubject
from rx.core import Observable
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

# Type variable for generics
T = TypeVar('T')


class ReactiveProperty(Generic[T]):
    """
    A property that can be observed for changes

    This class wraps a BehaviorSubject to provide a property
    that can be observed for changes, similar to ReactiveX's
    BehaviorSubject but with property-like syntax.
    """

    def __init__(self, initial_value: T):
        self._subject = BehaviorSubject(initial_value)

    def get(self) -> T:
        """Get the current value"""
        return self._subject.value

    def set(self, value: T) -> None:
        """Set a new value"""
        self._subject.on_next(value)

    def observe(self) -> Observable:
        """Get an observable for this property"""
        return self._subject.as_observable()

    def __str__(self) -> str:
        return f"ReactiveProperty({self._subject.value})"


class ReactiveList(Generic[T]):
    """
    A reactive list that emits events when items are added or removed

    This class provides a list-like interface that emits events when
    items are added, removed, or when the list is cleared.
    """

    def __init__(self, initial_items: List[T] = None):
        self._items = initial_items or []
        self._subject = Subject()

        # Different event types
        self.added = Subject()
        self.removed = Subject()
        self.reset = Subject()

        # Forward all events to the main subject
        self.added.subscribe(lambda x: self._subject.on_next(('added', x)))
        self.removed.subscribe(lambda x: self._subject.on_next(('removed', x)))
        self.reset.subscribe(lambda x: self._subject.on_next(('reset', x)))

    def append(self, item: T) -> None:
        """Add an item to the list"""
        self._items.append(item)
        self.added.on_next(item)

    def extend(self, items: List[T]) -> None:
        """Add multiple items to the list"""
        self._items.extend(items)
        for item in items:
            self.added.on_next(item)

    def remove(self, item: T) -> None:
        """Remove an item from the list"""
        if item in self._items:
            self._items.remove(item)
            self.removed.on_next(item)

    def pop(self, index: int = -1) -> T:
        """Remove and return an item at index (default last)"""
        item = self._items.pop(index)
        self.removed.on_next(item)
        return item

    def clear(self) -> None:
        """Clear all items"""
        items = self._items.copy()
        self._items.clear()
        self.reset.on_next(items)

    def __getitem__(self, index: int) -> T:
        """Get an item by index"""
        return self._items[index]

    def __setitem__(self, index: int, value: T) -> None:
        """Set an item at index"""
        old_value = self._items[index]
        self._items[index] = value
        self.removed.on_next(old_value)
        self.added.on_next(value)

    def __len__(self) -> int:
        """Get the number of items"""
        return len(self._items)

    def __iter__(self):
        """Iterate over items"""
        return iter(self._items)

    def observe(self) -> Observable:
        """Get an observable for all events"""
        return self._subject.as_observable()

    def observe_added(self) -> Observable:
        """Get an observable for added events"""
        return self.added.as_observable()

    def observe_removed(self) -> Observable:
        """Get an observable for removed events"""
        return self.removed.as_observable()

    def observe_reset(self) -> Observable:
        """Get an observable for reset events"""
        return self.reset.as_observable()

    @property
    def items(self) -> List[T]:
        """Get a copy of the items"""
        return self._items.copy()


class ReactiveDict(Generic[T]):
    """
    A reactive dictionary that emits events when items are added, removed, or changed

    This class provides a dict-like interface that emits events when
    items are added, removed, or changed.
    """

    def __init__(self, initial_items: Dict[str, T] = None):
        self._items = initial_items or {}
        self._subject = Subject()

        # Different event types
        self.added = Subject()
        self.removed = Subject()
        self.changed = Subject()
        self.reset = Subject()

        # Forward all events to the main subject
        self.added.subscribe(lambda x: self._subject.on_next(('added', x)))
        self.removed.subscribe(lambda x: self._subject.on_next(('removed', x)))
        self.changed.subscribe(lambda x: self._subject.on_next(('changed', x)))
        self.reset.subscribe(lambda x: self._subject.on_next(('reset', x)))

    def __setitem__(self, key: str, value: T) -> None:
        """Set an item"""
        if key in self._items:
            old_value = self._items[key]
            self._items[key] = value
            self.changed.on_next((key, old_value, value))
        else:
            self._items[key] = value
            self.added.on_next((key, value))

    def __getitem__(self, key: str) -> T:
        """Get an item"""
        return self._items[key]

    def __delitem__(self, key: str) -> None:
        """Delete an item"""
        if key in self._items:
            value = self._items[key]
            del self._items[key]
            self.removed.on_next((key, value))

    def get(self, key: str, default: Any = None) -> Union[T, Any]:
        """Get an item with a default value"""
        return self._items.get(key, default)

    def clear(self) -> None:
        """Clear all items"""
        items = self._items.copy()
        self._items.clear()
        self.reset.on_next(items)

    def update(self, items: Dict[str, T]) -> None:
        """Update with items from another dict"""
        for key, value in items.items():
            self[key] = value

    def __len__(self) -> int:
        """Get the number of items"""
        return len(self._items)

    def __iter__(self):
        """Iterate over keys"""
        return iter(self._items)

    def items(self):
        """Iterate over items"""
        return self._items.items()

    def keys(self):
        """Iterate over keys"""
        return self._items.keys()

    def values(self):
        """Iterate over values"""
        return self._items.values()

    def observe(self) -> Observable:
        """Get an observable for all events"""
        return self._subject.as_observable()

    def observe_added(self) -> Observable:
        """Get an observable for added events"""
        return self.added.as_observable()

    def observe_removed(self) -> Observable:
        """Get an observable for removed events"""
        return self.removed.as_observable()

    def observe_changed(self) -> Observable:
        """Get an observable for changed events"""
        return self.changed.as_observable()

    def observe_reset(self) -> Observable:
        """Get an observable for reset events"""
        return self.reset.as_observable()

    def observe_key(self, key: str) -> Observable:
        """Get an observable for a specific key"""
        # Initial value if key exists
        if key in self._items:
            initial = [(key, self._items[key])]
        else:
            initial = []

        # Create an observable that emits when the key is added, changed, or removed
        return rx.merge(
            rx.from_iterable(initial),
            self.added.pipe(
                ops.filter(lambda x: x[0] == key),
                ops.map(lambda x: (key, x[1]))
            ),
            self.changed.pipe(
                ops.filter(lambda x: x[0] == key),
                ops.map(lambda x: (key, x[2]))
            ),
            self.removed.pipe(
                ops.filter(lambda x: x[0] == key),
                ops.map(lambda x: (key, None))
            )
        )


class RxSignalAdapter(QObject):
    """
    Adapter to connect RxPy Observables to Qt signals

    This class allows connecting RxPy Observables to Qt signals,
    bridging the gap between the reactive and imperative worlds.
    """

    # Define a generic signal that can emit any value
    valueChanged = pyqtSignal(object)

    def __init__(self, observable: Observable):
        super().__init__()
        self.observable = observable
        self.disposable = None

    def connect(self):
        """Connect the observable to the signal"""
        if self.disposable:
            self.disposable.dispose()

        self.disposable = self.observable.subscribe(
            on_next=lambda x: self.valueChanged.emit(x),
            on_error=lambda e: print(f"Error in RxSignalAdapter: {e}")
        )

    def disconnect(self):
        """Disconnect the observable from the signal"""
        if self.disposable:
            self.disposable.dispose()
            self.disposable = None


def connect_observable_to_slot(observable: Observable, slot: Callable) -> rx.disposable.Disposable:
    """
    Connect an observable to a Qt slot

    Args:
        observable: The RxPy Observable to subscribe to
        slot: The Qt slot to call when the observable emits

    Returns:
        A disposable that can be used to unsubscribe
    """
    return observable.subscribe(
        on_next=slot,
        on_error=lambda e: print(f"Error in observable: {e}")
    )


# Example of a reactive ViewModel base class
class ReactiveViewModel(QObject):
    """
    Base class for ViewModels using reactive programming

    This class provides base functionality for ViewModels
    that use reactive programming for state management.
    """

    def __init__(self):
        super().__init__()
        self._adapters = []  # Keep references to prevent garbage collection

    def connect_reactive_property(self, prop: ReactiveProperty, signal_name: str) -> None:
        """
        Connect a reactive property to a signal

        Args:
            prop: The ReactiveProperty to observe
            signal_name: The name of the signal to emit when the property changes
        """
        # Get the signal from the class
        signal = getattr(self.__class__, signal_name, None)
        if not signal:
            raise ValueError(f"Signal {signal_name} not found")

        # Create an adapter
        adapter = RxSignalAdapter(prop.observe())
        adapter.valueChanged.connect(lambda x: getattr(self, signal_name).emit(x))
        adapter.connect()

        # Keep a reference to prevent garbage collection
        self._adapters.append(adapter)

    def connect_observable_to_signal(self, observable: Observable, signal_name: str) -> None:
        """
        Connect an observable to a signal

        Args:
            observable: The Observable to subscribe to
            signal_name: The name of the signal to emit when the observable emits
        """
        # Get the signal from the class
        signal = getattr(self.__class__, signal_name, None)
        if not signal:
            raise ValueError(f"Signal {signal_name} not found")

        # Create an adapter
        adapter = RxSignalAdapter(observable)
        adapter.valueChanged.connect(lambda x: getattr(self, signal_name).emit(x))
        adapter.connect()

        # Keep a reference to prevent garbage collection
        self._adapters.append(adapter)

    def dispose(self) -> None:
        """Dispose all adapters"""
        for adapter in self._adapters:
            adapter.disconnect()
        self._adapters.clear()