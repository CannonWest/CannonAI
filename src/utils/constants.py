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

# Ensure directories exist
os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

# Models
MODELS = {
    "GPT-4.5 Turbo (Preview)": "gpt-4.5-preview",
    "GPT-4o": "gpt-4o",
    "GPT-4o Mini": "gpt-4o-mini",
    "o1": "o1",
    "o1-mini": "o1-mini",
    "o3-mini": "o3-mini",
    "GPT-4 Turbo": "gpt-4-turbo",
    "GPT-3.5 Turbo": "gpt-3.5-turbo"
}

# For those who want specific model versions
MODEL_SNAPSHOTS = {
    "GPT-4.5 Turbo (2025-02-27)": "gpt-4.5-preview-2025-02-27",
    "GPT-4o (2024-08-06)": "gpt-4o-2024-08-06",
    "GPT-4o (2024-11-20)": "gpt-4o-2024-11-20",
    "GPT-4o Mini (2024-07-18)": "gpt-4o-mini-2024-07-18",
    "o1 (2024-12-17)": "o1-2024-12-17",
    "o1-mini (2024-09-12)": "o1-mini-2024-09-12",
    "o3-mini (2025-01-31)": "o3-mini-2025-01-31"
}

# Combine for all model options
ALL_MODELS = {**MODELS, **MODEL_SNAPSHOTS}

# Model categories to show the right settings
REASONING_MODELS = ["o1", "o1-mini", "o3-mini", "o1-2024-12-17", "o1-mini-2024-09-12", "o3-mini-2025-01-31"]
GPT_MODELS = ["gpt-4.5-preview", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
              "gpt-4.5-preview-2025-02-27", "gpt-4o-2024-08-06", "gpt-4o-2024-11-20", "gpt-4o-mini-2024-07-18"]

# Reasoning effort options for o1 and o3 models
REASONING_EFFORT = ["low", "medium", "high"]

# Response format options
RESPONSE_FORMATS = ["text", "json_object"]

# Default token limits (to show max limits in UI)
MODEL_CONTEXT_SIZES = {
    "gpt-4.5-preview": 128000,
    "gpt-4.5-preview-2025-02-27": 128000,
    "gpt-4o": 128000,
    "gpt-4o-2024-08-06": 128000,
    "gpt-4o-2024-11-20": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4o-mini-2024-07-18": 128000,
    "o1": 200000,
    "o1-2024-12-17": 200000,
    "o1-mini": 128000,
    "o1-mini-2024-09-12": 128000,
    "o3-mini": 200000,
    "o3-mini-2025-01-31": 200000,
    "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16385
}

# Default max output tokens
MODEL_OUTPUT_LIMITS = {
    "gpt-4.5-preview": 16384,
    "gpt-4.5-preview-2025-02-27": 16384,
    "gpt-4o": 16384,
    "gpt-4o-2024-08-06": 16384,
    "gpt-4o-2024-11-20": 16384,
    "gpt-4o-mini": 16384,
    "gpt-4o-mini-2024-07-18": 16384,
    "o1": 100000,
    "o1-2024-12-17": 100000,
    "o1-mini": 65536,
    "o1-mini-2024-09-12": 65536,
    "o3-mini": 100000,
    "o3-mini-2025-01-31": 100000,
    "gpt-4-turbo": 4096,
    "gpt-3.5-turbo": 4096
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