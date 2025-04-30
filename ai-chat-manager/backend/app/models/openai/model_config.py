"""
OpenAI model configurations for the AI Chat Manager.
This file contains information about available OpenAI models, their capabilities,
and pricing information.
"""
from enum import Enum
from typing import Dict, List, Optional, TypedDict
from pydantic import BaseModel

class ModelCapabilities(Enum):
    """Capabilities that models may support."""
    TEXT = "text"
    VISION = "vision"
    AUDIO = "audio"
    REALTIME = "realtime"
    SEARCH = "search"
    REASONING = "reasoning"

class PricingInfo(BaseModel):
    """Pricing information for a model."""
    input_price: float  # Price per 1M input tokens
    cached_input_price: Optional[float] = None  # Price per 1M cached input tokens
    output_price: float  # Price per 1M output tokens
    
class ModelInfo(BaseModel):
    """Information about an OpenAI model."""
    display_name: str  # Human-readable display name
    model_id: str  # Model ID to use in API calls
    version: str  # Version identifier
    pricing: PricingInfo  # Pricing information
    capabilities: List[ModelCapabilities] = [ModelCapabilities.TEXT]  # Model capabilities
    context_window: int = 16000  # Default context window size
    is_preview: bool = False  # Whether this is a preview model
    is_default: bool = False  # Whether this is a default model
    
# List of all available OpenAI models
OPENAI_MODELS: List[ModelInfo] = [
    ModelInfo(
        display_name="GPT-4.1",
        model_id="gpt-4.1",
        version="gpt-4.1-2025-04-14",
        pricing=PricingInfo(
            input_price=2.00,
            cached_input_price=0.50,
            output_price=8.00
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.REASONING],
        context_window=128000,
    ),
    ModelInfo(
        display_name="GPT-4.1 Mini",
        model_id="gpt-4.1-mini",
        version="gpt-4.1-mini-2025-04-14",
        pricing=PricingInfo(
            input_price=0.40,
            cached_input_price=0.10,
            output_price=1.60
        ),
        capabilities=[ModelCapabilities.TEXT],
        context_window=128000,
        is_default=True  # Setting this as default due to good balance of cost/performance
    ),
    ModelInfo(
        display_name="GPT-4.1 Nano",
        model_id="gpt-4.1-nano",
        version="gpt-4.1-nano-2025-04-14",
        pricing=PricingInfo(
            input_price=0.10,
            cached_input_price=0.025,
            output_price=0.40
        ),
        capabilities=[ModelCapabilities.TEXT],
        context_window=128000,
    ),
    ModelInfo(
        display_name="GPT-4.5 (Preview)",
        model_id="gpt-4.5-preview",
        version="gpt-4.5-preview-2025-02-27",
        pricing=PricingInfo(
            input_price=75.00,
            cached_input_price=37.50,
            output_price=150.00
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.REASONING],
        context_window=128000,
        is_preview=True
    ),
    ModelInfo(
        display_name="GPT-4o",
        model_id="gpt-4o",
        version="gpt-4o-2024-08-06",
        pricing=PricingInfo(
            input_price=2.50,
            cached_input_price=1.25,
            output_price=10.00
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.VISION],
        context_window=128000,
    ),
    ModelInfo(
        display_name="GPT-4o Audio (Preview)",
        model_id="gpt-4o-audio-preview",
        version="gpt-4o-audio-preview-2024-12-17",
        pricing=PricingInfo(
            input_price=2.50,
            cached_input_price=None,
            output_price=10.00
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.AUDIO],
        context_window=128000,
        is_preview=True
    ),
    ModelInfo(
        display_name="GPT-4o Realtime (Preview)",
        model_id="gpt-4o-realtime-preview",
        version="gpt-4o-realtime-preview-2024-12-17",
        pricing=PricingInfo(
            input_price=5.00,
            cached_input_price=2.50,
            output_price=20.00
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.REALTIME],
        context_window=128000,
        is_preview=True
    ),
    ModelInfo(
        display_name="GPT-4o Mini",
        model_id="gpt-4o-mini",
        version="gpt-4o-mini-2024-07-18",
        pricing=PricingInfo(
            input_price=0.15,
            cached_input_price=0.075,
            output_price=0.60
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.VISION],
        context_window=128000,
    ),
    ModelInfo(
        display_name="GPT-4o Mini Audio (Preview)",
        model_id="gpt-4o-mini-audio-preview",
        version="gpt-4o-mini-audio-preview-2024-12-17",
        pricing=PricingInfo(
            input_price=0.15,
            cached_input_price=None,
            output_price=0.60
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.AUDIO],
        context_window=128000,
        is_preview=True
    ),
    ModelInfo(
        display_name="GPT-4o Mini Realtime (Preview)",
        model_id="gpt-4o-mini-realtime-preview",
        version="gpt-4o-mini-realtime-preview-2024-12-17",
        pricing=PricingInfo(
            input_price=0.60,
            cached_input_price=0.30,
            output_price=2.40
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.REALTIME],
        context_window=128000,
        is_preview=True
    ),
    ModelInfo(
        display_name="O1",
        model_id="o1",
        version="o1-2024-12-17",
        pricing=PricingInfo(
            input_price=15.00,
            cached_input_price=7.50,
            output_price=60.00
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.REASONING],
        context_window=200000,
    ),
    ModelInfo(
        display_name="O1 Pro",
        model_id="o1-pro",
        version="o1-pro-2025-03-19",
        pricing=PricingInfo(
            input_price=150.00,
            cached_input_price=None,
            output_price=600.00
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.REASONING],
        context_window=200000,
    ),
    ModelInfo(
        display_name="O3",
        model_id="o3",
        version="o3-2025-04-16",
        pricing=PricingInfo(
            input_price=10.00,
            cached_input_price=2.50,
            output_price=40.00
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.REASONING],
        context_window=200000,
    ),
    ModelInfo(
        display_name="O4 Mini",
        model_id="o4-mini",
        version="o4-mini-2025-04-16",
        pricing=PricingInfo(
            input_price=1.10,
            cached_input_price=0.275,
            output_price=4.40
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.REASONING],
        context_window=200000,
    ),
    ModelInfo(
        display_name="O3 Mini",
        model_id="o3-mini",
        version="o3-mini-2025-01-31",
        pricing=PricingInfo(
            input_price=1.10,
            cached_input_price=0.55,
            output_price=4.40
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.REASONING],
        context_window=200000,
    ),
    ModelInfo(
        display_name="O1 Mini",
        model_id="o1-mini",
        version="o1-mini-2024-09-12",
        pricing=PricingInfo(
            input_price=1.10,
            cached_input_price=0.55,
            output_price=4.40
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.REASONING],
        context_window=128000,
    ),
    ModelInfo(
        display_name="GPT-4o Mini Search (Preview)",
        model_id="gpt-4o-mini-search-preview",
        version="gpt-4o-mini-search-preview-2025-03-11",
        pricing=PricingInfo(
            input_price=0.15,
            cached_input_price=None,
            output_price=0.60
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.SEARCH],
        context_window=128000,
        is_preview=True
    ),
    ModelInfo(
        display_name="GPT-4o Search (Preview)",
        model_id="gpt-4o-search-preview",
        version="gpt-4o-search-preview-2025-03-11",
        pricing=PricingInfo(
            input_price=2.50,
            cached_input_price=None,
            output_price=10.00
        ),
        capabilities=[ModelCapabilities.TEXT, ModelCapabilities.SEARCH],
        context_window=128000,
        is_preview=True
    ),
]

# Helper function to get the default model
def get_default_model() -> ModelInfo:
    """Get the default OpenAI model."""
    for model in OPENAI_MODELS:
        if model.is_default:
            return model
    # Fallback to first model if no default is set
    return OPENAI_MODELS[0]

# Helper function to get a model by ID
def get_model_by_id(model_id: str) -> Optional[ModelInfo]:
    """Get a model by its ID."""
    for model in OPENAI_MODELS:
        if model.model_id == model_id:
            return model
    return None

# Helper function to get a model by version
def get_model_by_version(version: str) -> Optional[ModelInfo]:
    """Get a model by its version identifier."""
    for model in OPENAI_MODELS:
        if model.version == version:
            return model
    return None

# Helper function to get models by capability
def get_models_by_capability(capability: ModelCapabilities) -> List[ModelInfo]:
    """Get all models that support a specific capability."""
    return [model for model in OPENAI_MODELS if capability in model.capabilities]

# Get model names for API calls
def get_model_names() -> List[str]:
    """Get a list of all model IDs for API calls."""
    return [model.model_id for model in OPENAI_MODELS]

# Get versioned model names for API calls
def get_versioned_model_names() -> List[str]:
    """Get a list of all versioned model IDs for API calls."""
    return [model.version for model in OPENAI_MODELS]
