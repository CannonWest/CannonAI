"""
OpenAI Chat Application Package.
A desktop application for interacting with OpenAI language models.

This package provides a PyQt6-based UI for interacting with the OpenAI API,
with support for multiple conversations, file attachments, and model customization.
"""

# Package version
__version__ = "1.0.0"

# Import core components
from src.models import Conversation, Message, FileAttachment
from src.services import AsyncApiService, AsyncConversationService, SettingsManager
from src.viewmodels import ConversationViewModel, SettingsViewModel

# For convenience, also import the qasync tools
from src.utils import install_qasync, run_coroutine