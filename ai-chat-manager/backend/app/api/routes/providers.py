""" 
API routes for AI providers.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Body, Query
import logging

from app.services.provider_factory import get_provider
from app.utils.api_key_validator import get_available_providers, validate_openai_api_key, validate_gemini_key, validate_anthropic_api_key
from app.core.config import settings
from app.models.openai.model_config import ModelCapabilities

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/")
def get_providers() -> Dict[str, bool]:
    """Get a list of available AI providers with their validation status."""
    return get_available_providers(settings)

@router.get("/{provider_name}/models")
def get_provider_models(
    provider_name: str,
    capability: Optional[str] = Query(None, description="Filter models by capability")
) -> Dict:
    """
    Get available models for a specific provider.
    
    Can optionally filter by capability (e.g., 'vision', 'audio', 'text', 'reasoning').
    """
    # First check if this provider is available (has valid API key)
    providers_status = get_available_providers(settings)
    if provider_name.lower() not in providers_status or not providers_status[provider_name.lower()]:
        logger.warning(f"Attempted to get models for {provider_name} but it has no valid API key")
        return {"error": f"Provider {provider_name} is not available or has no valid API key"}
    
    # Try to get models
    try:
        provider = get_provider(provider_name)
        
        # If it's OpenAI and a capability is specified, use our enhanced filtering
        if provider_name.lower() == "openai" and capability:
            return {
                "models": provider.get_model_by_capability(capability)
            }
        
        # Standard model listing
        return {"models": provider.get_available_models()}
    except Exception as e:
        logger.error(f"Error getting models for {provider_name}: {str(e)}")
        return {"error": str(e)}

@router.get("/{provider_name}/models/{model_name}")
def get_model_details(provider_name: str, model_name: str) -> Dict:
    """
    Get detailed information about a specific model.
    
    For OpenAI models, this includes pricing, capabilities, context window, etc.
    """
    # First check if this provider is available
    providers_status = get_available_providers(settings)
    if provider_name.lower() not in providers_status or not providers_status[provider_name.lower()]:
        logger.warning(f"Attempted to get model details for {provider_name} but it has no valid API key")
        return {"error": f"Provider {provider_name} is not available or has no valid API key"}
    
    try:
        provider = get_provider(provider_name)
        
        # For OpenAI, use our enhanced model details method
        if provider_name.lower() == "openai" and hasattr(provider, "get_model_details"):
            details = provider.get_model_details(model_name)
            if details:
                return details
            return {"error": f"Model {model_name} not found"}
        
        # For other providers, return a simple response
        return {
            "name": model_name,
            "provider": provider_name,
            "available": model_name in provider.get_available_models()
        }
    except Exception as e:
        logger.error(f"Error getting model details for {provider_name}/{model_name}: {str(e)}")
        return {"error": str(e)}

@router.get("/capabilities")
def get_provider_capabilities() -> Dict[str, Dict[str, Any]]:
    """Get capabilities of different providers and models."""
    # Get providers with valid API keys
    providers_status = get_available_providers(settings)
    
    capabilities = {}
    
    # Only include providers with valid API keys
    if providers_status.get("openai", False):
        try:
            provider = get_provider("openai")
            
            # Use our enhanced provider to get model groups
            if hasattr(provider, "get_model_groups"):
                model_groups = provider.get_model_groups()
                model_list = provider.get_available_models()
                default_model = provider.get_default_model()
                
                capabilities["openai"] = {
                    "models": model_list,
                    "model_groups": model_groups,
                    "default_model": default_model,
                    "capabilities": [cap.value for cap in ModelCapabilities],
                    "features": ["chat", "stream"]
                }
            else:
                # Fallback to basic information
                capabilities["openai"] = {
                    "models": provider.get_available_models(),
                    "features": ["chat", "stream"]
                }
        except Exception as e:
            logger.error(f"Error getting OpenAI capabilities: {str(e)}")
            capabilities["openai"] = {
                "models": [],
                "error": str(e)
            }
    
    # Google provider (limited functionality)
    if providers_status.get("google", False):
        capabilities["google"] = {
            "models": ["gemini-pro", "gemini-pro-vision"],
            "features": ["chat", "stream"]
        }
    
    # Anthropic provider
    if providers_status.get("anthropic", False):
        capabilities["anthropic"] = {
            "models": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku", "claude-3.5-sonnet", "claude-3.7-sonnet"],
            "features": ["chat", "stream"]
        }
    
    logger.info(f"Reporting capabilities for providers: {list(capabilities.keys())}")
    return capabilities

@router.post("/validate-key")
def validate_api_key(provider: str = Body(...), api_key: str = Body(...)) -> Dict[str, bool]:
    """Validate an API key for a given provider."""
    logger.info(f"Validating API key for provider: {provider}")
    
    result = {"valid": False}
    
    # Validate based on provider type
    if provider.lower() == "openai":
        result["valid"] = validate_openai_api_key(api_key)
    elif provider.lower() == "google":
        result["valid"] = validate_gemini_key(api_key)
    elif provider.lower() == "anthropic":
        result["valid"] = validate_anthropic_api_key(api_key)
    else:
        result["error"] = f"Unknown provider: {provider}"
    
    return result

@router.get("/{provider_name}/token-cost")
def calculate_token_cost(
    provider_name: str,
    model_name: str = Query(..., description="Model name to calculate cost for"),
    input_tokens: int = Query(..., description="Number of input tokens"),
    output_tokens: int = Query(..., description="Number of output tokens"),
    use_cached_input: bool = Query(False, description="Whether to use cached input pricing")
) -> Dict:
    """
    Calculate the estimated cost for a given number of tokens.
    
    Currently only implemented for OpenAI models.
    """
    # Check if provider is available
    providers_status = get_available_providers(settings)
    if provider_name.lower() not in providers_status or not providers_status[provider_name.lower()]:
        logger.warning(f"Attempted to calculate token cost for {provider_name} but it has no valid API key")
        return {"error": f"Provider {provider_name} is not available or has no valid API key"}
    
    try:
        provider = get_provider(provider_name)
        
        # Currently only OpenAI supports token cost calculation
        if provider_name.lower() == "openai" and hasattr(provider, "calculate_token_cost"):
            cost = provider.calculate_token_cost(
                model_name=model_name, 
                input_tokens=input_tokens, 
                output_tokens=output_tokens, 
                use_cached_input=use_cached_input
            )
            
            if cost is not None:
                return {
                    "cost": cost,
                    "currency": "USD",
                    "details": {
                        "model": model_name,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                        "use_cached_input": use_cached_input
                    }
                }
            return {"error": f"Model {model_name} not found"}
        
        # For other providers, return a not implemented response
        return {"error": f"Token cost calculation not implemented for {provider_name}"}
    except Exception as e:
        logger.error(f"Error calculating token cost for {provider_name}/{model_name}: {str(e)}")
        return {"error": str(e)}
