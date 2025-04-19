#src/services/storage/settings_manager.py
"""
Settings manager for saving and loading application configuration.
Adapted for web-based architecture with FastAPI.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

# Default constants
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

# Create logger for this module
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_PARAMS: Dict[str, Any] = {
    "model": "gpt-4o",
    "temperature": 0.7,
    "max_output_tokens": 1024,
    "top_p": 1.0,
    "stream": True,
    "text": {"format": {"type": "text"}},
    "reasoning": {"effort": "medium"},
    "store": True,
    "seed": None,
    "api_key": "",
    "api_type": "responses",
    "system_message": "You are a helpful assistant."
}

# Pydantic model for settings validation
class Settings(BaseModel):
    """Validate and enforce types for settings."""
    model: str = Field(default="gpt-4o")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, ge=64, le=32768)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    stream: bool = Field(default=True)
    text: Dict[str, Any] = Field(default={"format": {"type": "text"}})
    reasoning: Dict[str, Any] = Field(default={"effort": "medium"})
    store: bool = Field(default=True)
    seed: Optional[int] = Field(default=None)
    api_key: str = Field(default="")
    api_type: str = Field(default="responses")
    system_message: str = Field(default="You are a helpful assistant.")

    class Config:
        extra = "allow"  # Allow additional fields


class SettingsManager:
    """
    Manages application settings with secure storage of sensitive data.
    Settings are persisted to disk for server restarts.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, config_dir: Optional[str] = None, settings_file: Optional[str] = None):
        """
        Initialize the settings manager if not already initialized.

        Args:
            config_dir: Directory for configuration files
            settings_file: Path to settings JSON file
        """
        # Only initialize once due to singleton pattern
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.logger = logging.getLogger(f"{__name__}.SettingsManager")

        # Set file paths
        self.config_dir = config_dir or CONFIG_DIR
        self.settings_file = settings_file or SETTINGS_FILE

        # Initialize settings with defaults
        self.settings = DEFAULT_PARAMS.copy()

        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        self.logger.debug(f"Ensuring config directory exists: {self.config_dir}")

        # Load existing settings
        self.load_settings()

        # Mark as initialized
        self._initialized = True

    def load_settings(self) -> Dict[str, Any]:
        """
        Load settings from disk and environment.
        Environment variables take precedence over saved settings.

        Returns:
            Dictionary of current settings
        """
        self.logger.debug("Loading settings")

        # First check environment variable for API key
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            self.logger.debug("Found API key in environment variables")
            self.settings["api_key"] = api_key

        # Then try to load from JSON file
        if os.path.exists(self.settings_file):
            try:
                self.logger.debug(f"Loading settings from JSON file: {self.settings_file}")
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    stored_settings = json.load(f)

                # Update settings, excluding sensitive data if not present
                self._update_settings_exclude_sensitive(stored_settings)
                self.logger.info("Successfully loaded settings from JSON file")
            except Exception as e:
                self.logger.error(f"Error loading settings from JSON: {e}", exc_info=True)
        else:
            self.logger.info("No saved settings file found, using defaults")

        # Validate settings with Pydantic
        try:
            validated_settings = Settings(**self.settings)
            # Update with validated values (handles type conversion)
            self.settings.update(validated_settings.dict())
            self.logger.debug("Settings validated successfully")
        except Exception as e:
            self.logger.error(f"Settings validation error: {e}", exc_info=True)

        return self.settings

    def save_settings(self) -> bool:
        """
        Save settings to disk (excluding sensitive data).

        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.debug("Saving settings")

            # Clone settings to avoid modifying the original
            settings_to_save = self.settings.copy()

            # Remove sensitive information
            if "api_key" in settings_to_save:
                self.logger.debug("Removing API key from saved settings")
                del settings_to_save["api_key"]

            # Save to JSON file
            self.logger.debug(f"Saving settings to JSON file: {self.settings_file}")
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings_to_save, f, ensure_ascii=False, indent=2)

            self.logger.info("Settings saved successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}", exc_info=True)
            return False

    async def get_settings(self) -> Dict[str, Any]:
        """
        Get a copy of the current settings.

        Returns:
            Dictionary of current settings
        """
        settings = self.settings
        return settings

    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a specific setting value.

        Args:
            key: Setting key
            default: Default value if key not found

        Returns:
            Setting value or default
        """
        return self.settings.get(key, default)

    def update_settings(self, new_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update settings with new values and save to disk.

        Args:
            new_settings: Dictionary of settings to update

        Returns:
            Updated settings dictionary
        """
        self.logger.debug(f"Updating settings with keys: {list(new_settings.keys())}")

        # Validate with Pydantic before updating
        try:
            # Only validate the new settings
            partial_validated = Settings(**{**self.settings, **new_settings})
            # Get the updated fields as a dict
            validated_updates = {k: v for k, v in partial_validated.dict().items()
                               if k in new_settings}
            # Update settings with validated values
            self.settings.update(validated_updates)
        except Exception as e:
            self.logger.error(f"Settings validation error: {e}", exc_info=True)
            # Continue with the update for backward compatibility,
            # but only for valid keys
            for k, v in new_settings.items():
                if k in DEFAULT_PARAMS:
                    self.settings[k] = v

        # Save to disk
        self.save_settings()

        self.logger.info("Settings updated and saved")
        return self.get_settings()

    def update_setting(self, key: str, value: Any) -> Dict[str, Any]:
        """
        Update a single setting and save to disk.

        Args:
            key: Setting key
            value: New value

        Returns:
            Updated settings dictionary
        """
        return self.update_settings({key: value})

    def _update_settings_exclude_sensitive(self, new_settings: Dict[str, Any]) -> None:
        """
        Update settings but preserve sensitive data if missing in new settings.

        Args:
            new_settings: Dictionary of new settings
        """
        # Save API key if present before update
        api_key = self.settings.get("api_key")

        # Update settings with new values
        self.settings.update(new_settings)

        # Restore API key if it was removed and we had a previous value
        if api_key and "api_key" not in new_settings:
            self.logger.debug("Restoring API key from original settings")
            self.settings["api_key"] = api_key

    def reset_to_defaults(self) -> Dict[str, Any]:
        """
        Reset settings to defaults (preserving API key).

        Returns:
            Default settings dictionary
        """
        # Save API key
        api_key = self.settings.get("api_key", "")

        # Reset to defaults
        self.settings = DEFAULT_PARAMS.copy()

        # Restore API key
        if api_key:
            self.settings["api_key"] = api_key

        # Save to disk
        self.save_settings()

        self.logger.info("Settings reset to defaults")
        return self.get_settings()

    # --- Web API specific methods ---

    def get_frontend_settings(self) -> Dict[str, Any]:
        """
        Get settings safe for sending to the frontend.
        Excludes sensitive information like API keys.

        Returns:
            Dictionary of settings safe for the frontend
        """
        settings = self.get_settings()

        # Remove sensitive information
        if "api_key" in settings:
            settings["api_key"] = bool(settings["api_key"])  # Just indicate if present

        return settings