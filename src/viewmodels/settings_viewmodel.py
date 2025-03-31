# src/viewmodels/settings_viewmodel.py
"""
ViewModel for application settings (Synchronous).
"""
# Standard library imports
from typing import Dict, Any, List, Optional, Tuple

# Third-party imports
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QVariant, QThread # Added QThread

# Application-specific imports
from src.services.api.api_service import ApiService # Import sync version
from src.services.storage import SettingsManager
from src.utils.logging_utils import get_logger
# Import constants directly
from src.utils import constants

# Get logger for this module
logger = get_logger(__name__)

# Worker for API Key Validation
class ApiKeyValidatorWorker(QObject):
    validationResult = pyqtSignal(bool, str) # isValid, message
    finished = pyqtSignal()

    def __init__(self, api_key, api_service: ApiService, parent=None):
        super().__init__(parent)
        self.api_key = api_key
        self.api_service = api_service

    @pyqtSlot()
    def run(self):
        """Perform the API key validation."""
        is_valid = False
        message = "Validation failed"
        try:
            # Need a synchronous validation method in ApiService
            if hasattr(self.api_service, 'validate_api_key_sync'):
                 is_valid, message = self.api_service.validate_api_key_sync(self.api_key)
            else:
                 message = "Validation method not found in ApiService."
                 logger.warning(message)
        except Exception as e:
            logger.error(f"Error during API key validation worker: {e}", exc_info=True)
            message = f"Validation error: {e}"
        finally:
            self.validationResult.emit(is_valid, message)
            self.finished.emit()


class SettingsViewModel(QObject): # Renamed class
    """ViewModel for application settings with threading for validation."""

    # Signal definitions
    settingsChanged = pyqtSignal(dict)
    settingChanged = pyqtSignal(str, object)
    errorOccurred = pyqtSignal(str)
    apiKeyValidated = pyqtSignal(bool, str) # Keep this signal

    def __init__(self):
        super().__init__()
        self.settings_manager = SettingsManager()
        self.api_service = None # Will be set by initialize
        self._settings = self.settings_manager.load_settings()
        self._validation_thread = None # To manage validation worker thread
        logger.debug(f"Initialized SettingsViewModel with settings: {list(self._settings.keys())}")

    def initialize(self, api_service: ApiService): # Expect sync ApiService
        """Initialize with API service for validation."""
        self.api_service = api_service
        logger.debug("ApiService set in SettingsViewModel")

    @pyqtSlot(result="QVariant")
    def get_settings(self) -> Dict[str, Any]:
        """Get the current settings as a dictionary."""
        logger.debug("get_settings called")
        # Return a copy to prevent direct modification
        return dict(self._settings)

    @pyqtSlot(dict)
    def update_settings(self, settings: Dict[str, Any]):
        """Update settings with new values and save to disk."""
        try:
            logger.debug(f"Updating settings with: {list(settings.keys())}")
            self._settings.update(settings)
            self.settings_manager.update_settings(settings) # This saves synchronously

            # Update API key in service if present
            if self.api_service and "api_key" in settings:
                 # Check if key actually changed before setting
                 current_key = getattr(self.api_service, '_api_key', None)
                 if settings["api_key"] != current_key:
                      self.api_service.set_api_key(settings["api_key"])
                      logger.debug("API key updated in ApiService")

            self.settingsChanged.emit(dict(self._settings))
            logger.info("Settings updated successfully")
        except Exception as e:
            logger.error(f"Error updating settings: {str(e)}")
            self.errorOccurred.emit(f"Failed to update settings: {str(e)}")

    @pyqtSlot(str, "QVariant")
    def update_setting(self, key: str, value: Any):
        """Update a single setting."""
        try:
            logger.debug(f"Updating single setting: {key} = {value}")
            if key not in self._settings or self._settings[key] != value:
                 self._settings[key] = value
                 self.settings_manager.update_settings({key: value}) # Save single change
                 self.settingChanged.emit(key, value) # Emit specific change
                 self.settingsChanged.emit(dict(self._settings)) # Emit full settings
                 # Update API key if relevant
                 if key == "api_key" and self.api_service:
                      self.api_service.set_api_key(value)
            else:
                 logger.debug(f"Setting '{key}' unchanged.")
        except Exception as e:
            logger.error(f"Error updating setting '{key}': {str(e)}")
            self.errorOccurred.emit(f"Failed to update setting '{key}': {str(e)}")

    @pyqtSlot(str, result="QVariant")
    def get_setting(self, key: str, default=None):
        """Get a specific setting value."""
        return self._settings.get(key, default)

    # --- API Key Validation (Using Worker Thread) ---
    @pyqtSlot(str)
    def validate_api_key(self, api_key: str):
        """Validate an API key using a background thread."""
        if not self.api_service:
            logger.warning("Cannot validate API key: API service not initialized")
            self.apiKeyValidated.emit(False, "API service not initialized")
            return
        if not hasattr(self.api_service, 'validate_api_key_sync'):
             logger.error("Cannot validate API key: ApiService missing 'validate_api_key_sync' method.")
             self.apiKeyValidated.emit(False, "Validation method not available.")
             return

        # Stop previous validation if running
        if self._validation_thread and self._validation_thread.isRunning():
            logger.debug("Terminating previous API key validation thread.")
            # self._validation_thread.quit() # Ask politely first
            self._validation_thread.wait(100) # Brief wait
            if self._validation_thread.isRunning(): # Force if needed
                 self._validation_thread.terminate()
            self._validation_thread = None

        logger.debug(f"Starting API key validation worker for key: {'*' * (len(api_key) - 4)}{api_key[-4:]}")
        self._validation_thread = QThread()
        worker = ApiKeyValidatorWorker(api_key, self.api_service)
        worker.moveToThread(self._validation_thread)

        # Connect signals
        worker.validationResult.connect(self.apiKeyValidated) # Directly connect worker signal to VM signal
        worker.finished.connect(self._validation_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self._validation_thread.finished.connect(self._validation_thread.deleteLater)
        self._validation_thread.started.connect(worker.run)

        self._validation_thread.start()

    # Removed _validate_api_key_async

    # --- Methods for Model Information (Already Synchronous) ---
    # These methods access constants and don't need threads

    @pyqtSlot(result="QVariant")
    def get_main_models(self) -> List[Dict[str, str]]:
        """Get the list of main models for display in QML."""
        try:
            model_list = [{"text": display_name, "value": model_id}
                          for display_name, model_id in constants.MODELS.items()]
            logger.debug(f"Returning {len(model_list)} main models")
            return model_list
        except Exception as e:
            logger.error(f"Error getting main models: {str(e)}")
            return []

    @pyqtSlot(result="QVariant")
    def get_model_snapshots(self) -> List[Dict[str, str]]:
        """Get the list of model snapshots for display in QML."""
        try:
            snapshot_list = [{"text": display_name, "value": model_id}
                             for display_name, model_id in constants.MODEL_SNAPSHOTS.items()]
            logger.debug(f"Returning {len(snapshot_list)} model snapshots")
            return snapshot_list
        except Exception as e:
            logger.error(f"Error getting model snapshots: {str(e)}")
            return []

    @pyqtSlot(str, result="QVariant")
    def get_model_info(self, model_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific model."""
        try:
            info = {}
            info["context_size"] = constants.MODEL_CONTEXT_SIZES.get(model_id, 8192) # Default fallback
            info["output_limit"] = constants.MODEL_OUTPUT_LIMITS.get(model_id, 4096) # Default fallback
            info["pricing"] = constants.MODEL_PRICING.get(model_id, {"input": 0.0, "output": 0.0}) # Default fallback
            info["is_reasoning_model"] = model_id in constants.REASONING_MODELS or "o1" in model_id or "o3" in model_id

            logger.debug(f"Returning info for model {model_id}: {info}")
            return info
        except Exception as e:
            logger.error(f"Error getting model info for {model_id}: {str(e)}")
            return {} # Return empty dict on error

    @pyqtSlot(result="QVariant")
    def get_reasoning_efforts(self) -> List[str]:
        """Get list of reasoning effort options."""
        return constants.REASONING_EFFORT

    @pyqtSlot(result="QVariant")
    def get_response_formats(self) -> List[str]:
        """Get list of response format options."""
        return constants.RESPONSE_FORMATS

    @pyqtSlot(str, result=bool)
    def is_reasoning_model(self, model_id: str) -> bool:
        """Check if a model is a reasoning model."""
        return model_id in constants.REASONING_MODELS or "o1" in model_id or "o3" in model_id