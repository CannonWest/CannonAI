# src/models/__init__.py

"""
Data models package for the OpenAI Chat application.
"""

# Original conversation models (keep for backward compatibility)
from src.models.conversation import (
    MessageNode,
    ConversationTree,
    ConversationManager,
)

# New database-backed models
from src.models.db_manager import DatabaseManager
from src.models.db_conversation import DBMessageNode, DBConversationTree
from src.models.db_conversation_manager import DBConversationManager