#src/services/database/__init__.py
"""
Database services package for the CannonAI application.
Provides synchronous database operations using SQLAlchemy 2.0.
"""

# Import path configuration to ensure directories exist
from src.config.paths import ensure_directories, DATABASE_DIR

# Ensure database directory exists
ensure_directories()

# Import synchronous database classes
from src.services.database.db_manager import DatabaseManager
from src.services.database.conversation_service import ConversationService

# Optional: Define __all__
__all__ = [
    "DatabaseManager",
    "ConversationService",
]
