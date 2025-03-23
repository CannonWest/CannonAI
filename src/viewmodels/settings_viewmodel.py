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
        self