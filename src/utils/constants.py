"""
Constants and configuration values for the OpenAI Chat application.
"""

import os
from typing import Dict, Any

# Default OpenAI API key
DEFAULT_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Application paths
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
DATA_DIR = os.path.join(APP_DIR, "data")
CONVERSATIONS_DIR = os.path.join(DATA_DIR, "conversations")
CONFIG_DIR = os.path.join(APP_DIR, "config")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
DATABASE_DIR = os.path.join(DATA_DIR, "database")
DATABASE_FILE = os.path.join(DATABASE_DIR, "conversations.db")

# Ensure directories exist
os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(DATABASE_DIR, exist_ok=True)

# Main models (latest aliases)
MODELS = {
    "GPT-4.5 Turbo (Preview)": "gpt-4.5-preview",
    "GPT-4o": "gpt-4o",
    "GPT-4o Mini": "gpt-4o-mini",
    "o1": "o1",
    "o1-preview": "o1-preview",
    "o1-mini": "o1-mini",
    "o3-mini": "o3-mini",
    "GPT-4 Turbo": "gpt-4-turbo",
    "GPT-4": "gpt-4",
    "GPT-3.5 Turbo": "gpt-3.5-turbo",
    "GPT-3.5 Turbo Instruct": "gpt-3.5-turbo-instruct",
    "Davinci-002": "davinci-002",
    "Babbage-002": "babbage-002"
}

# For those who want specific model versions
MODEL_SNAPSHOTS = {
    # GPT-4.5 snapshots
    "GPT-4.5 Turbo (2025-02-27)": "gpt-4.5-preview-2025-02-27",

    # GPT-4o snapshots
    "GPT-4o (2024-08-06)": "gpt-4o-2024-08-06",
    "GPT-4o (2024-11-20)": "gpt-4o-2024-11-20",
    "GPT-4o (2024-05-13)": "gpt-4o-2024-05-13",
    "GPT-4o Mini (2024-07-18)": "gpt-4o-mini-2024-07-18",

    # Reasoning model snapshots
    "o1 (2024-12-17)": "o1-2024-12-17",
    "o1 Preview (2024-09-12)": "o1-preview-2024-09-12",
    "o1-mini (2024-09-12)": "o1-mini-2024-09-12",
    "o3-mini (2025-01-31)": "o3-mini-2025-01-31",

    # GPT-4 snapshots
    "GPT-4 Turbo (2024-04-09)": "gpt-4-turbo-2024-04-09",
    "GPT-4 (0125-Preview)": "gpt-4-0125-preview",
    "GPT-4 (1106-Preview)": "gpt-4-1106-preview",
    "GPT-4 (0613)": "gpt-4-0613",
    "GPT-4 (0314)": "gpt-4-0314",

    # GPT-3.5 snapshots
    "GPT-3.5 Turbo (0125)": "gpt-3.5-turbo-0125",
    "GPT-3.5 Turbo (1106)": "gpt-3.5-turbo-1106",
    "GPT-3.5 Turbo (0613)": "gpt-3.5-turbo-0613"
}

# Combine for all model options
ALL_MODELS = {**MODELS, **MODEL_SNAPSHOTS}

# Model categories to show the right settings
REASONING_MODELS = ["o1", "o1-mini", "o3-mini", "o1-2024-12-17", "o1-mini-2024-09-12", "o3-mini-2025-01-31", "o1-preview-2024-09-12", "o1-preview"]
GPT_MODELS = ["gpt-4.5-preview", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
              "gpt-4.5-preview-2025-02-27", "gpt-4o-2024-08-06", "gpt-4o-2024-11-20", "gpt-4o-mini-2024-07-18"]

# Reasoning effort options for o1 and o3 models
REASONING_EFFORT = ["low", "medium", "high"]

# Response format options
RESPONSE_FORMATS = ["text", "json_object"]

# Default token limits (to show max limits in UI)
MODEL_CONTEXT_SIZES = {
    # GPT-4.5 models
    "gpt-4.5-preview": 128000,
    "gpt-4.5-preview-2025-02-27": 128000,

    # GPT-4o models
    "gpt-4o": 128000,
    "gpt-4o-2024-08-06": 128000,
    "gpt-4o-2024-11-20": 128000,
    "gpt-4o-2024-05-13": 128000,

    # GPT-4o Mini models
    "gpt-4o-mini": 128000,
    "gpt-4o-mini-2024-07-18": 128000,

    # Reasoning models
    "o1": 200000,
    "o1-2024-12-17": 200000,
    "o1-preview": 200000,
    "o1-preview-2024-09-12": 200000,
    "o1-mini": 128000,
    "o1-mini-2024-09-12": 128000,
    "o3-mini": 200000,
    "o3-mini-2025-01-31": 200000,

    # GPT-4 models
    "gpt-4-turbo": 128000,
    "gpt-4-turbo-2024-04-09": 128000,
    "gpt-4-0125-preview": 128000,
    "gpt-4-1106-preview": 128000,
    "gpt-4": 8192,
    "gpt-4-0613": 8192,
    "gpt-4-0314": 8192,

    # GPT-3.5 models
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-0125": 16385,
    "gpt-3.5-turbo-1106": 16385,
    "gpt-3.5-turbo-0613": 16385,
    "gpt-3.5-turbo-instruct": 4096,

    # Base models
    "davinci-002": 16384,
    "babbage-002": 16384
}

# Default max output tokens
MODEL_OUTPUT_LIMITS = {
    # GPT-4.5 models
    "gpt-4.5-preview": 16384,
    "gpt-4.5-preview-2025-02-27": 16384,

    # GPT-4o models
    "gpt-4o": 16384,
    "gpt-4o-2024-08-06": 16384,
    "gpt-4o-2024-11-20": 16384,
    "gpt-4o-2024-05-13": 4096,

    # GPT-4o Mini models
    "gpt-4o-mini": 16384,
    "gpt-4o-mini-2024-07-18": 16384,

    # Reasoning models
    "o1": 100000,
    "o1-2024-12-17": 100000,
    "o1-preview": 100000,
    "o1-preview-2024-09-12": 100000,
    "o1-mini": 65536,
    "o1-mini-2024-09-12": 65536,
    "o3-mini": 100000,
    "o3-mini-2025-01-31": 100000,

    # GPT-4 models
    "gpt-4-turbo": 4096,
    "gpt-4-turbo-2024-04-09": 4096,
    "gpt-4-0125-preview": 4096,
    "gpt-4-1106-preview": 4096,
    "gpt-4": 8192,
    "gpt-4-0613": 8192,
    "gpt-4-0314": 8192,

    # GPT-3.5 models
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-0125": 4096,
    "gpt-3.5-turbo-1106": 4096,
    "gpt-3.5-turbo-0613": 4096,
    "gpt-3.5-turbo-instruct": 4096,

    # Base models
    "davinci-002": 16384,
    "babbage-002": 16384
}
# Default parameters for API calls
DEFAULT_PARAMS: Dict[str, Any] = {
    "model": "gpt-4o",
    "temperature": 0.7,
    "max_completion_tokens": 1024,  # Using the newer parameter instead of max_tokens
    "top_p": 1.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "stream": True,
    "reasoning_effort": "medium",
    "response_format": {"type": "text"},
    "store": False,  # Whether to store chat completions for later retrieval
    "seed": None,    # For deterministic outputs
    "service_tier": "auto",
    "api_key": DEFAULT_API_KEY,
}

# Theme Colors
DARK_MODE = {
    "background": "#2B2B2B",
    "foreground": "#F8F8F2",
    "accent": "#6272A4",
    "highlight": "#44475A",
    "user_message": "#50FA7B",
    "assistant_message": "#8BE9FD",
    "system_message": "#FFB86C",
    "error_message": "#FF5555"
}

# Model pricing information (USD per 1M tokens)
MODEL_PRICING = {
    # GPT-4.5 models
    "gpt-4.5-preview": {"input": 75.00, "cached_input": 37.50, "output": 150.00},
    "gpt-4.5-preview-2025-02-27": {"input": 75.00, "cached_input": 37.50, "output": 150.00},

    # GPT-4o models
    "gpt-4o": {"input": 2.50, "cached_input": 1.25, "output": 10.00},
    "gpt-4o-2024-08-06": {"input": 2.50, "cached_input": 1.25, "output": 10.00},
    "gpt-4o-2024-11-20": {"input": 2.50, "cached_input": 1.25, "output": 10.00},
    "gpt-4o-2024-05-13": {"input": 5.00, "output": 15.00},

    # GPT-4o Mini models
    "gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "cached_input": 0.075, "output": 0.60},

    # Reasoning models (o-series)
    "o1": {"input": 15.00, "cached_input": 7.50, "output": 60.00},
    "o1-2024-12-17": {"input": 15.00, "cached_input": 7.50, "output": 60.00},
    "o1-preview": {"input": 15.00, "cached_input": 7.50, "output": 60.00},
    "o1-preview-2024-09-12": {"input": 15.00, "cached_input": 7.50, "output": 60.00},
    "o1-mini": {"input": 1.10, "cached_input": 0.55, "output": 4.40},
    "o1-mini-2024-09-12": {"input": 1.10, "cached_input": 0.55, "output": 4.40},
    "o3-mini": {"input": 1.10, "cached_input": 0.55, "output": 4.40},
    "o3-mini-2025-01-31": {"input": 1.10, "cached_input": 0.55, "output": 4.40},

    # GPT-4 models
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4-turbo-2024-04-09": {"input": 10.00, "output": 30.00},
    "gpt-4-0125-preview": {"input": 10.00, "output": 30.00},
    "gpt-4-1106-preview": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-4-0613": {"input": 30.00, "output": 60.00},
    "gpt-4-0314": {"input": 30.00, "output": 60.00},

    # GPT-3.5 models
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-3.5-turbo-0125": {"input": 0.50, "output": 1.50},
    "gpt-3.5-turbo-1106": {"input": 1.00, "output": 2.00},
    "gpt-3.5-turbo-0613": {"input": 1.50, "output": 2.00},
    "gpt-3.5-turbo-instruct": {"input": 1.50, "output": 2.00},

    # Base models
    "davinci-002": {"input": 2.00, "output": 2.00},
    "babbage-002": {"input": 0.40, "output": 0.40}
}

# Calculate cost per token (USD per token, converted from per million)
MODEL_PRICE_PER_TOKEN = {}
for model, prices in MODEL_PRICING.items():
    MODEL_PRICE_PER_TOKEN[model] = {
        "input": prices["input"] / 1_000_000,
        "output": prices["output"] / 1_000_000
    }
    if "cached_input" in prices:
        MODEL_PRICE_PER_TOKEN[model]["cached_input"] = prices["cached_input"] / 1_000_000

