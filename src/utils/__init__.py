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

# Async file utilities (preferred)
from src.utils.async_file_utils import (
    get_file_info_async,
    AsyncFileProcessor,
    AsyncFileCacheManager,
    count_tokens,
    read_text_file,
    get_file_mime_type
)

# Async QML bridge (preferred)
from src.utils.async_qml_bridge import AsyncQmlBridge

# Event loop management
from src.utils.event_loop_manager import EventLoopManager

# Enhanced async utilities with improved Windows support
from src.utils.qasync_bridge import (
    patch_qasync,
    ensure_qasync_loop,
    run_coroutine,
    run_sync,
    install as install_qasync,
    get_event_loop_manager
)