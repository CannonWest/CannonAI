"""
Asynchronous ViewModel for application settings.
Handles API key validation and manages setting values.
"""

import asyncio
from typing import Dict, Any, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty, QVariant

from src.services.storage import SettingsManager
from src.services.async_api_service import AsyncApiService
from src.utils.qasync_bridge import run_coroutine
from src.utils.logging_utils import get_logger

# Get logger for this module
logger = get_logger(__name__)


class AsyncSettingsViewModel(QObject):
    """ViewModel for application settings with async support"""

    # Signal definitions
    settingsChanged = pyqtSignal(dict)  # Emitted when settings are updated
    settingChanged = pyqtSignal(str, object)  # Emitted when a specific setting is changed
    errorOccurred = pyqtSignal(str)  # Emitted when an error occurs
    apiKeyValidated = pyqtSignal(bool, str)  # Emitted when API key validation completes

    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self.api_service = None
        self._settings = self.settings_manager.load_settings()
        
        # Log initial settings load
        logger.debug(f"Initialized AsyncSettingsViewModel with settings: {list(self._settings.keys())}")

    def initialize(self, api_service: AsyncApiService):
        """Initialize with API service for validation"""
        self.api_service = api_service
        logger.debug("AsyncApiService set in AsyncSettingsViewModel")

    @pyqtSlot(result="QVariant")
    def get_settings(self):
        """Get the current settings as a dictionary
        This method is exposed to QML and called by the settings dialog
        """
        logger.debug("get_settings called from QML")
        return dict(self._settings)

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
                logger.debug("API key updated in AsyncApiService")

            # Emit signal for UI updates
            self.settingsChanged.emit(dict(self._settings))
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
            self.settingsChanged.emit(dict(self._settings))
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

        # Use run_coroutine to handle the async validation
        run_coroutine(
            self._validate_api_key_async(api_key),
            callback=lambda result: self.apiKeyValidated.emit(result[0], result[1]),
            error_callback=lambda e: self.apiKeyValidated.emit(False, str(e))
        )

    async def _validate_api_key_async(self, api_key: str) -> Tuple[bool, str]:
        """
        Async method to validate API key
        
        Args:
            api_key: The API key to validate
            
        Returns:
            Tuple of (is_valid, message)
        """
        try:
            # Create a temporary session with the API key
            session = await self.api_service.get_session()
            
            # Try a simple API call to validate the key
            # We'll just use the models endpoint which is lightweight
            url = f"{self.api_service._base_url}/models"
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return (True, "API key is valid")
                elif response.status == 401:
                    return (False, "Invalid API key")
                else:
                    return (False, f"API error: {response.status}")
        except Exception as e:
            logger.error(f"Error validating API key: {str(e)}")
            return (False, f"Error validating API key: {str(e)}")

    # Methods for model information - these don't need to be async as they're just reading local data

    @pyqtSlot(result="QVariant")
    def get_main_models(self):
        """Get the list of main models for display in QML"""
        from src.utils.constants import MODELS
        
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
        from src.utils.constants import MODEL_SNAPSHOTS
        
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
        from src.utils.constants import MODEL_CONTEXT_SIZES, MODEL_OUTPUT_LIMITS, REASONING_MODELS, MODEL_PRICING
        
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
        from src.utils.constants import REASONING_EFFORT
        return REASONING_EFFORT

    @pyqtSlot(result="QVariant")
    def get_response_formats(self):
        """Get list of response format options"""
        from src.utils.constants import RESPONSE_FORMATS
        return RESPONSE_FORMATS

    @pyqtSlot(str, result=bool)
    def is_reasoning_model(self, model_id: str):
        """Check if a model is a reasoning model"""
        from src.utils.constants import REASONING_MODELS
        return model_id in REASONING_MODELS or "o1" in model_id or "o3" in model_id

    @pyqtSlot(str, result=int)
    def get_max_tokens_for_model(self, model_id: str):
        """Get the maximum output tokens for a model"""
        from src.utils.constants import MODEL_OUTPUT_LIMITS
        if model_id in MODEL_OUTPUT_LIMITS:
            return MODEL_OUTPUT_LIMITS[model_id]
        return 1024  # Default fallback

    @pyqtSlot(str, result=int)
    def get_context_size_for_model(self, model_id: str):
        """Get the context size for a model"""
        from src.utils.constants import MODEL_CONTEXT_SIZES
        if model_id in MODEL_CONTEXT_SIZES:
            return MODEL_CONTEXT_SIZES[model_id]
        return 8192  # Default fallback

    @pyqtSlot(str, result="QVariant")
    def get_pricing_for_model(self, model_id: str):
        """Get pricing information for a model"""
        from src.utils.constants import MODEL_PRICING
        if model_id in MODEL_PRICING:
            return MODEL_PRICING[model_id]
        return {"input": 0.0, "output": 0.0}  # Default fallback
