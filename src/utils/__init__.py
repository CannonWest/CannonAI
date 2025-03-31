"""
Utility functions and constants for the OpenAI Chat application.
"""

from src.utils.constants import (
    # Constants
    DEFAULT_API_KEY,
    MODELS,
    MODEL_SNAPSHOTS,
    ALL_MODELS,
    REASONING_MODELS,
    GPT_MODELS,
    REASONING_EFFORT,
    RESPONSE_FORMATS,
    MODEL_CONTEXT_SIZES,
    MODEL_OUTPUT_LIMITS,
    MODEL_PRICING,
    DEFAULT_PARAMS,
    DARK_MODE,

    # Paths
    APP_DIR,
    DATA_DIR,
    CONFIG_DIR,
    SETTINGS_FILE,
    DATABASE_DIR,
    DATABASE_FILE
)

from src.utils.logging_utils import (
    configure_logging,
    get_logger,
    log_exception
)

# file utilities
from src.utils.file_utils import (
    count_tokens,
    read_text_file,
    get_file_mime_type
)

# QML bridge
from src.utils.qml_bridge import QmlBridge