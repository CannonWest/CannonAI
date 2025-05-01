"""
Core functionality package initialization.
"""
# Explicitly expose important modules to simplify imports
try:
    from app.core.config import settings
    from app.core.database import get_db, Base, engine
    from app.core.middleware import LoggingMiddleware
    
    __all__ = ['settings', 'get_db', 'Base', 'engine', 'LoggingMiddleware']
except ImportError as e:
    # This will be handled by the logger in app/__init__.py
    pass
