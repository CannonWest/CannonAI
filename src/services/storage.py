"""
Storage services for saving and loading application data.
"""

import os
import json
from typing import Dict, Any, Optional

from PyQt6.QtCore import QSettings

from src.utils import CONFIG_DIR, SETTINGS_FILE, DEFAULT_PARAMS
from src.utils.logging_utils import get_logger, log_exception

# Get a logger for this module
logger = get_logger(__name__)


class SettingsManager:
    """Manages application settings"""

    def __init__(self):
        self.settings = DEFAULT_PARAMS.copy()
        self.logger = get_logger(f"{__name__}.SettingsManager")

        # Ensure config directory exists
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.logger.debug(f"Ensuring config directory exists: {CONFIG_DIR}")

        # Load settings from disk if they exist
        self.load_settings()

    def load_settings(self) -> Dict[str, Any]:
        """Load settings from disk"""
        self.logger.debug("Loading settings")

        # First check environment variable for API key
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            self.logger.debug("Found API key in environment variables")
            self.settings["api_key"] = api_key

        # Then try to load from JSON file
        if os.path.exists(SETTINGS_FILE):
            try:
                self.logger.debug(f"Loading settings from JSON file: {SETTINGS_FILE}")
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    stored_settings = json.load(f)

                # Update settings, excluding sensitive data
                self._update_settings_exclude_sensitive(stored_settings)
                self.logger.info("Successfully loaded settings from JSON file")
                return self.settings
            except Exception as e:
                self.logger.error(f"Error loading settings from JSON: {e}", exc_info=True)
                log_exception(self.logger, e, "Failed to load settings from JSON file")

        # Fall back to QSettings if JSON file not found or error occurred
        self.logger.debug("Falling back to QSettings")
        q_settings = QSettings("OpenAI", "ChatApp")
        stored_settings = q_settings.value("app_settings")
        if stored_settings:
            self._update_settings_exclude_sensitive(stored_settings)
            self.logger.info("Successfully loaded settings from QSettings")
        else:
            self.logger.info("No saved settings found, using defaults")

        return self.settings

    def save_settings(self) -> bool:
        """Save settings to disk"""
        try:
            self.logger.debug("Saving settings")

            # Clone settings to avoid modifying the original
            settings_to_save = self.settings.copy()

            # Remove sensitive information
            if "api_key" in settings_to_save:
                self.logger.debug("Removing API key from saved settings")
                del settings_to_save["api_key"]

            # Save to JSON file
            self.logger.debug(f"Saving settings to JSON file: {SETTINGS_FILE}")
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings_to_save, f, ensure_ascii=False, indent=2)

            # Also save to QSettings for backward compatibility
            self.logger.debug("Saving settings to QSettings for backward compatibility")
            q_settings = QSettings("OpenAI", "ChatApp")
            q_settings.setValue("app_settings", settings_to_save)

            self.logger.info("Settings saved successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}", exc_info=True)
            log_exception(self.logger, e, "Failed to save settings")
            return False

    def get_settings(self) -> Dict[str, Any]:
        """Get the current settings"""
        return self.settings.copy()

    @staticmethod
    def get_cached_settings() -> Dict[str, Any]:
        """
        Static method to get cached settings without creating a new instance.
        This is much more efficient for frequent access.
        """
        global _GLOBAL_SETTINGS_INSTANCE, _GLOBAL_SETTINGS_LOCK

        with _GLOBAL_SETTINGS_LOCK:
            if _GLOBAL_SETTINGS_INSTANCE is not None:
                return _GLOBAL_SETTINGS_INSTANCE.settings.copy()

        # No cached instance, create one (which will load settings)
        instance = SettingsManager()
        return instance.settings.copy()

    def update_settings(self, new_settings: Dict[str, Any]) -> None:
        """Update settings with new values"""
        self.logger.debug("Updating settings")
        self.settings.update(new_settings)
        self.save_settings()
        self.logger.info("Settings updated and saved")

    def _update_settings_exclude_sensitive(self, new_settings: Dict[str, Any]) -> None:
        """Update settings but preserve sensitive data like API keys"""
        # Save API key if present before update
        api_key = self.settings.get("api_key")

        # Update settings with new values
        self.settings.update(new_settings)

        # Restore API key if it was removed and we had a previous value
        if api_key and "api_key" not in new_settings:
            self.logger.debug("Restoring API key from original settings")
            self.settings["api_key"] = api_key