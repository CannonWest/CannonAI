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

from src.utils.file_utils import (
    get_file_info,
    get_file_info_async,
    extract_display_text,
    format_size,
    FileCacheManager
)

from src.utils.qasync_bridge import (
    install as install_qasync,
    run_coroutine
)

from src.utils.qml_bridge import (
    QmlBridge,
    QmlModelBase,
    QmlListModel
)

from src.utils.reactive import (
    ReactiveProperty,
    ReactiveList,
    ReactiveDict,
    ReactiveViewModel,
    RxSignalAdapter,
    connect_observable_to_slot
)