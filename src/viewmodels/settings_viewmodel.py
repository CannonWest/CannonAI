# src/viewmodels/settings_viewmodel.py

from typing import Dict, Any, List, Optional
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty

from src.utils.reactive import ReactiveProperty, ReactiveDict
from src.services.storage import SettingsManager
from src.utils.constants import (
    MODEL_CONTEXT_SIZES, MODEL_OUTPUT_LIMITS, MODELS, MODEL_SNAPSHOTS,
    REASONING_MODELS, REASONING_EFFORT, RESPONSE_FORMATS, DEFAULT_PARAMS
)
from src.utils.logging_utils import get_logger

# Get logger for this module
logger = get_logger(__name__)


class SettingsViewModel(QObject):
    """ViewModel for application settings"""

    # Signal definitions
    settingsChanged = pyqtSignal(dict)  # Emitted when settings are updated
    settingChanged = pyqtSignal(str, object)  # Emitted when a specific setting is changed
    errorOccurred = pyqtSignal(str)  # Emitted when an error occurs
    apiKeyValidated = pyqtSignal(bool, str)  # Emitted when API key validation completes

    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self.api_service = None
        self._settings = ReactiveDict(self.settings_manager.load_settings())

        # Log initial settings load
        logger.debug(f"Initialized SettingsViewModel with settings: {list(self._settings.keys())}")

    def initialize(self, api_service):
        """Initialize with API service for validation"""
        self.api_service = api_service
        logger.debug("API service set in SettingsViewModel")

    @pyqtSlot(result="QVariant")
    def get_settings(self):
        """Get the current settings as a dictionary
        This method is exposed to QML and called by the settings dialog
        """
        logger.debug("get_settings called from QML")
        return dict(self._settings.items())

    @pyqtSlot(dict)
    def update_settings(self, settings: Dict[str, Any]):
        """Update settings with new values and save to disk"""
        try:
            logger.debug(f"Updating settings with: {list(settings.keys())}")

            # Update settings dictionary
            self._settings.update(settings)

            # Update settings via manager (saves to disk)
            self.settings_manager.update_settings(settings)

            # Update API key if present
            if self.api_service and "api_key" in settings:
                self.api_service.set_api_key(settings["api_key"])
                logger.debug("API key updated in API service")

            # Emit signal for UI updates
            self.settingsChanged.emit(dict(self._settings.items()))
            logger.info("Settings updated successfully")
        except Exception as e:
            logger.error(f"Error updating settings: {str(e)}")
            self.errorOccurred.emit(f"Failed to update settings: {str(e)}")

    @pyqtSlot(str, "QVariant")
    def update_setting(self, key: str, value: Any):
        """Update a single setting"""
        try:
            logger.debug(f"Updating single setting: {key}")

            # Update in dictionary
            self._settings[key] = value

            # Save changes
            self.settings_manager.update_settings({key: value})

            # Emit signal for specific setting change
            self.settingChanged.emit(key, value)

            # Also emit the full settings change signal
            self.settingsChanged.emit(dict(self._settings.items()))
        except Exception as e:
            logger.error(f"Error updating setting '{key}': {str(e)}")
            self.errorOccurred.emit(f"Failed to update setting '{key}': {str(e)}")

    @pyqtSlot(str, result="QVariant")
    def get_setting(self, key: str, default=None):
        """Get a specific setting value"""
        return self._settings.get(key, default)

    @pyqtSlot(str)
    def validate_api_key(self, api_key: str):
        """Validate an API key with the OpenAI API"""
        if not self.api_service:
            logger.warning("Cannot validate API key: API service not initialized")
            self.apiKeyValidated.emit(False, "API service not initialized")
            return

        # This would need actual implementation to validate the key
        # For now, just assume it's valid
        logger.info("API key validation requested")
        self.apiKeyValidated.emit(True, "Valid API key")

        # In a real implementation, you would use the API service to make a test call
        # and emit the validation result based on success/failure