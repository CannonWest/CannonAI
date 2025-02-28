"""
Storage services for saving and loading application data.
"""

import os
import json
from typing import Dict, Any, Optional

from PyQt6.QtCore import QSettings

from src.utils import CONFIG_DIR, SETTINGS_FILE, DEFAULT_PARAMS


class SettingsManager:
    """Manages application settings"""

    def __init__(self):
        self.settings = DEFAULT_PARAMS.copy()

        # Ensure config directory exists
        os.makedirs(CONFIG_DIR, exist_ok=True)

        # Load settings from disk if they exist
        self.load_settings()

    def load_settings(self) -> Dict[str, Any]:
        """Load settings from disk"""
        # First try the JSON file
        # First check environment variable for API key
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            self.settings["api_key"] = api_key
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    stored_settings = json.load(f)

                # Update settings, excluding sensitive data
                self._update_settings_exclude_sensitive(stored_settings)
                return self.settings
            except Exception as e:
                print(f"Error loading settings from JSON: {e}")

        # Fall back to QSettings
        q_settings = QSettings("OpenAI", "ChatApp")
        stored_settings = q_settings.value("app_settings")
        if stored_settings:
            self._update_settings_exclude_sensitive(stored_settings)

        return self.settings

    def save_settings(self) -> bool:
        """Save settings to disk"""
        try:
            # Clone settings to avoid modifying the original
            settings_to_save = self.settings.copy()

            # Remove sensitive information
            if "api_key" in settings_to_save:
                del settings_to_save["api_key"]

            # Save to JSON file
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings_to_save, f, ensure_ascii=False, indent=2)

            # Also save to QSettings for backward compatibility
            q_settings = QSettings("OpenAI", "ChatApp")
            q_settings.setValue("app_settings", settings_to_save)

            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def get_settings(self) -> Dict[str, Any]:
        """Get the current settings"""
        return self.settings.copy()

    def update_settings(self, new_settings: Dict[str, Any]) -> None:
        """Update settings with new values"""
        self.settings.update(new_settings)
        self.save_settings()

    def _update_settings_exclude_sensitive(self, new_settings: Dict[str, Any]) -> None:
        """Update settings but preserve sensitive data like API keys"""
        api_key = self.settings.get("api_key")
        self.settings.update(new_settings)

        # Restore API key if it was removed
        if api_key and "api_key" not in new_settings:
            self.settings["api_key"] = api_key