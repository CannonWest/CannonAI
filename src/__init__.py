"""
CannonAI Application Package.
A desktop application for interacting with various AI models using PyQt6 and MVVM.
"""

# Package version
__version__ = "1.0.0" # Consider updating version if making significant changes

# Import core components (ensure these align with exports from sub-packages)
from src.models import Conversation, Message, FileAttachment, Base
from src.services import ApiService, ConversationService, SettingsManager, DatabaseManager # Use correct service names


# Optional: Define __all__ for explicit public API
__all__ = [
    "Conversation", "Message", "FileAttachment", "Base",
    "ApiService", "ConversationService", "SettingsManager", "DatabaseManager",
    "ConversationViewModel", "SettingsViewModel",
    "__version__",
]
