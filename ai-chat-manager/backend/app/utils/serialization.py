"""
Utility functions for serializing data objects.
"""
from datetime import datetime
from typing import Any, Dict, List, Union


def serialize_datetime(dt: datetime) -> str:
    """
    Serialize a datetime object to ISO format string.
    
    Args:
        dt: The datetime object to serialize
        
    Returns:
        ISO format string representation of the datetime
    """
    if not isinstance(dt, datetime):
        return dt
    return dt.isoformat()


def serialize_model(obj: Any) -> Any:
    """
    Recursively serialize a model or dict, converting datetime objects to strings.
    
    Args:
        obj: The object to serialize (SQLAlchemy model, dict, list, etc.)
        
    Returns:
        Serialized object with all datetime objects converted to strings
    """
    if isinstance(obj, dict):
        return {k: serialize_model(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_model(item) for item in obj]
    elif hasattr(obj, "__dict__"):
        # Handle SQLAlchemy models or any object with __dict__
        result = {}
        for key, value in obj.__dict__.items():
            # Skip private attributes and SQLAlchemy internal attributes
            if not key.startswith('_'):
                result[key] = serialize_model(value)
        return result
    elif isinstance(obj, datetime):
        return serialize_datetime(obj)
    else:
        return obj
