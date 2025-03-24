"""
ViewModels package for the OpenAI Chat application.
Contains both async and reactive implementations for UI data binding.
"""

# Async viewmodels (preferred for new code)
from src.viewmodels.updated_async_conversation_viewmodel import FullAsyncConversationViewModel
from src.viewmodels.async_settings_viewmodel import AsyncSettingsViewModel


# Define preferred models for new code
ConversationViewModel = FullAsyncConversationViewModel
SettingsViewModel = AsyncSettingsViewModel
