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
    DEFAULT_PARAMS,
    DARK_MODE,

    # Paths
    APP_DIR,
    DATA_DIR,
    CONVERSATIONS_DIR,
    CONFIG_DIR,
    SETTINGS_FILE,
)

# Import file utilities
from src.utils.file_utils import (
    get_file_info,
    count_tokens,
    read_text_file,
    format_size
)

# Import logging utilities
from src.utils.logging_utils import (
    configure_logging,
    get_logger,
    log_exception,
    LOGS_DIR
)