# src/utils/constants.py
"""
Constants used throughout the application.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any

# Determine base directory for the application
if getattr(sys, 'frozen', False):
    # If the application is run as a bundle (frozen)
    ROOT_DIR = Path(sys.executable).parent
else:
    # If the application is run from script
    ROOT_DIR = Path(__file__).parent.parent.parent


# Data directory is at the project root level
DATA_DIR = os.path.join(ROOT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Define the logs directory
LOGS_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Define other important directories
DATABASE_DIR = os.path.join(DATA_DIR, "database")
os.makedirs(DATABASE_DIR, exist_ok=True)

# Define the database path
DATABASE_PATH = os.path.join(DATABASE_DIR, "conversation.db")

# Default OpenAI API key
DEFAULT_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Application paths
CONFIG_DIR = os.path.join(ROOT_DIR, "config")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

# Ensure directories exist
os.makedirs(CONFIG_DIR, exist_ok=True)

# Main models (latest aliases)
MODELS = {
    "DeepSeek R1": "deepseek-reasoner",
    "DeepSeek V3": "deepseek-chat",
    "GPT-4.5 Turbo (Preview)": "gpt-4.5-preview",
    "GPT-4o": "gpt-4o",
    "GPT-4o Mini": "gpt-4o-mini",
    "o1": "o1",
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
REASONING_MODELS = ["deepseek-reasoner", "o1", "o3-mini", "o1-2024-12-17", "o1-mini-2024-09-12", "o3-mini-2025-01-31", "o1-preview-2024-09-12", "o1-preview"]
GPT_MODELS = ["deepseek-chat","gpt-4.5-preview", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
              "gpt-4.5-preview-2025-02-27", "gpt-4o-2024-08-06", "gpt-4o-2024-11-20", "gpt-4o-mini-2024-07-18"]

# Reasoning effort options for o1 and o3 models
REASONING_EFFORT = ["low", "medium", "high"]

# Response format options
RESPONSE_FORMATS = ["text", "json_object"]

# Default token limits (to show max limits in UI) - Updated for 2025
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

    # GPT-4 models (some may be deprecated, kept for compatibility)
    "gpt-4-turbo": 128000,
    "gpt-4-turbo-2024-04-09": 128000,
    "gpt-4-0125-preview": 128000,
    "gpt-4-1106-preview": 128000,
    "gpt-4": 8192,
    "gpt-4-0613": 8192,
    "gpt-4-0314": 8192,

    # GPT-3.5 models (some may be deprecated, kept for compatibility)
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-0125": 16385,
    "gpt-3.5-turbo-1106": 16385,
    "gpt-3.5-turbo-0613": 16385,
    "gpt-3.5-turbo-instruct": 4096,

    # Base models
    "davinci-002": 16384,
    "babbage-002": 16384,

    # Claude models (if we want to support them in the future)
    "claude-3-5-sonnet-20240620": 200000,
    "claude-3-opus-20240229": 200000,
    "claude-3-haiku-20240307": 200000
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
    "max_output_tokens": 1024,  # New Response API parameter
    "top_p": 1.0,
    "stream": True,
    "text": {"format": {"type": "text"}},  # New Response API parameter
    "reasoning": {"effort": "medium"},  # For o1/o3 models
    "store": True,  # Whether to store responses for later retrieval
    "seed": None,    # For deterministic outputs
    "api_key": DEFAULT_API_KEY,
    "api_type": "responses",  # Options: "responses" or "chat_completions"
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

MODEL_CONTEXT_SIZES["deepseek-reasoner"] = 64000
MODEL_OUTPUT_LIMITS["deepseek-reasoner"] = 8000
MODEL_PRICING["deepseek-reasoner"] = {"input": 0.55, "output": 2.19}

MODEL_CONTEXT_SIZES["deepseek-chat"] = 64000
MODEL_OUTPUT_LIMITS["deepseek-chat"] = 8000
MODEL_PRICING["deepseek-chat"] = {"input": 0.27, "output": 1.10}

# Calculate cost per token (USD per token, converted from per million)
MODEL_PRICE_PER_TOKEN = {}
for model, prices in MODEL_PRICING.items():
    MODEL_PRICE_PER_TOKEN[model] = {
        "input": prices["input"] / 1_000_000,
        "output": prices["output"] / 1_000_000
    }
    if "cached_input" in prices:
        MODEL_PRICE_PER_TOKEN[model]["cached_input"] = prices["cached_input"] / 1_000_000

# Cache settings
CACHE_SIZE = 1000  # Maximum number of items to store in the cache
CACHE_TTL = 300  # Time-to-live for cached items in seconds (5 minutes)


def DEFAULT_SYSTEM_MESSAGE():
    return "You are a helpful assistant."