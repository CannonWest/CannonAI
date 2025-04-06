#src/services/database/__init__.py
"""
Database services package for the CannonAI application.
Provides synchronous database operations using SQLAlchemy 2.0.
"""

# Import synchronous database classes
from src.services.database.db_manager import DatabaseManager
from src.services.database.conversation_service import ConversationService

# Removed Base import/export (import Base from src.models where needed)

# Optional: Define __all__
__all__ = [
    "DatabaseManager",
    "ConversationService",
]
