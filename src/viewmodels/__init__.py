"""
ViewModels package for the CannonAI application.
Contains ViewModels implementing the MVVM pattern using standard PyQt threading.
"""

# Import the actual threaded ViewModel classes
from src.viewmodels.conversation_viewmodel import ConversationViewModel
from src.viewmodels.settings_viewmodel import SettingsViewModel

# Define exports (optional but good practice)
__all__ = [
    "ConversationViewModel",
    "SettingsViewModel",
]