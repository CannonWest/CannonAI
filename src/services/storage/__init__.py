"""
Storage services package for the OpenAI Chat application.
"""

# Import SettingsManager from the existing file
try:
    from src.services.storage import SettingsManager
except ImportError:
    # Once we move the file to its new location, use this import
    from src.services.storage.settings_manager import SettingsManager