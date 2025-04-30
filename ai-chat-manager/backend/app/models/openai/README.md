# OpenAI Models Configuration

This module provides a comprehensive configuration for OpenAI models, including:

- Full model list with version information
- Pricing details (input/output token costs)
- Model capabilities (text, vision, audio, etc.)
- Context window sizes
- Helper functions for model management

## Usage

```python
from app.models.openai import (
    OPENAI_MODELS,
    get_default_model,
    get_model_by_id,
    get_model_by_version,
    get_models_by_capability,
    ModelCapabilities
)

# Get the default model
default_model = get_default_model()

# Get a specific model by ID
gpt4_model = get_model_by_id("gpt-4o")

# Get models with specific capabilities
vision_models = get_models_by_capability(ModelCapabilities.VISION)
```

## Model Information Structure

Each model is represented by a `ModelInfo` object with the following attributes:

- `display_name`: Human-readable name for the UI
- `model_id`: Model identifier for API calls
- `version`: Version identifier with date (e.g., "gpt-4o-2024-08-06")
- `pricing`: Token pricing information
- `capabilities`: List of model capabilities
- `context_window`: Maximum context window size
- `is_preview`: Whether the model is a preview version
- `is_default`: Whether this is a default model

## API Integration

The OpenAI provider in `app.services.openai_provider` has been updated to:

1. Properly resolve model names to their versioned equivalents
2. Provide model information via new endpoints
3. Calculate token costs for different models
4. Filter models by capability

## New API Endpoints

The following new endpoints are available:

- `GET /api/v1/providers/{provider_name}/models?capability={capability}`: Get models, optionally filtered by capability
- `GET /api/v1/providers/{provider_name}/models/{model_name}`: Get detailed information about a specific model
- `GET /api/v1/providers/{provider_name}/token-cost`: Calculate token costs for a model
- `GET /api/v1/settings/provider-models`: Get default model settings for each provider

## Model Updates

To update the model list in the future:

1. Edit `model_config.py` and update the `OPENAI_MODELS` list
2. Add new models with appropriate display names, pricing, and capabilities
3. Set `is_default=True` for the model that should be used by default

The code is designed to automatically use the correct versioned model names in API calls.
