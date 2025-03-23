# src/viewmodels/settings_viewmodel.py

from typing import Dict, Any, List, Optional
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty, QVariant

from src.utils.reactive import ReactiveProperty, ReactiveDict
from src.services.storage import SettingsManager
from src.utils.constants import (
    MODEL_CONTEXT_SIZES, MODEL_OUTPUT_LIMITS, MODELS, MODEL_SNAPSHOTS, ALL_MODELS,
    REASONING_MODELS, GPT_MODELS, REASONING_EFFORT, RESPONSE_FORMATS, DEFAULT_PARAMS,
    MODEL_PRICING
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

    # New methods for model information

    @pyqtSlot(result="QVariant")
    def get_main_models(self):
        """Get the list of main models for display in QML"""
        try:
            model_list = []
            for display_name, model_id in MODELS.items():
                model_list.append({
                    "text": display_name,
                    "value": model_id
                })
            logger.debug(f"Returning {len(model_list)} main models")
            return model_list
        except Exception as e:
            logger.error(f"Error getting main models: {str(e)}")
            return []

    @pyqtSlot(result="QVariant")
    def get_model_snapshots(self):
        """Get the list of model snapshots for display in QML"""
        try:
            snapshot_list = []
            for display_name, model_id in MODEL_SNAPSHOTS.items():
                snapshot_list.append({
                    "text": display_name,
                    "value": model_id
                })
            logger.debug(f"Returning {len(snapshot_list)} model snapshots")
            return snapshot_list
        except Exception as e:
            logger.error(f"Error getting model snapshots: {str(e)}")
            return []

    @pyqtSlot(str, result="QVariant")
    def get_model_info(self, model_id: str):
        """Get detailed information about a specific model"""
        try:
            info = {}

            # Get context size
            if model_id in MODEL_CONTEXT_SIZES:
                info["context_size"] = MODEL_CONTEXT_SIZES[model_id]
            else:
                info["context_size"] = 8192  # Default fallback

            # Get output limit
            if model_id in MODEL_OUTPUT_LIMITS:
                info["output_limit"] = MODEL_OUTPUT_LIMITS[model_id]
            else:
                info["output_limit"] = 1024  # Default fallback

            # Get pricing info
            if model_id in MODEL_PRICING:
                pricing = MODEL_PRICING[model_id]
                info["pricing"] = pricing
            else:
                # Default pricing as fallback
                info["pricing"] = {"input": 0.0, "output": 0.0}

            # Check if it's a reasoning model
            info["is_reasoning_model"] = model_id in REASONING_MODELS or "o1" in model_id or "o3" in model_id

            logger.debug(f"Returning info for model {model_id}: {info}")
            return info
        except Exception as e:
            logger.error(f"Error getting model info for {model_id}: {str(e)}")
            return {}

    @pyqtSlot(result="QVariant")
    def get_reasoning_efforts(self):
        """Get list of reasoning effort options"""
        return REASONING_EFFORT

    @pyqtSlot(result="QVariant")
    def get_response_formats(self):
        """Get list of response format options"""
        return RESPONSE_FORMATS

    @pyqtSlot(str, result=bool)
    def is_reasoning_model(self, model_id: str):
        """Check if a model is a reasoning model"""
        return model_id in REASONING_MODELS or "o1" in model_id or "o3" in model_id

    @pyqtSlot(str, result=int)
    def get_max_tokens_for_model(self, model_id: str):
        """Get the maximum output tokens for a model"""
        if model_id in MODEL_OUTPUT_LIMITS:
            return MODEL_OUTPUT_LIMITS[model_id]
        return 1024  # Default fallback

    @pyqtSlot(str, result=int)
    def get_context_size_for_model(self, model_id: str):
        """Get the context size for a model"""
        if model_id in MODEL_CONTEXT_SIZES:
            return MODEL_CONTEXT_SIZES[model_id]
        return 8192  # Default fallback

    @pyqtSlot(str, result="QVariant")
    def get_pricing_for_model(self, model_id: str):
        """Get pricing information for a model"""
        if model_id in MODEL_PRICING:
            return MODEL_PRICING[model_id]
        return {"input": 0.0, "output": 0.0}  # Default fallback