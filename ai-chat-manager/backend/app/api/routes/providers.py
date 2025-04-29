""" 
API routes for AI providers.
"""
from typing import List, Dict
from fastapi import APIRouter, Body
import logging

from app.services.provider_factory import get_provider
from app.utils.api_key_validator import get_available_providers, validate_openai_api_key, validate_gemini_key, validate_anthropic_api_key
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/")
def get_providers() -> Dict[str, bool]:
    """Get a list of available AI providers with their validation status."""
    return get_available_providers(settings)

@router.get("/{provider_name}/models")
def get_provider_models(provider_name: str) -> Dict:
    """Get available models for a specific provider."""
    # First check if this provider is available (has valid API key)
    providers_status = get_available_providers(settings)
    if provider_name.lower() not in providers_status or not providers_status[provider_name.lower()]:
        logger.warning(f"Attempted to get models for {provider_name} but it has no valid API key")
        return {"error": f"Provider {provider_name} is not available or has no valid API key"}
    
    # Try to get models
    try:
        provider = get_provider(provider_name)
        return {"models": provider.get_available_models()}
    except Exception as e:
        logger.error(f"Error getting models for {provider_name}: {str(e)}")
        return {"error": str(e)}

@router.get("/capabilities")
def get_provider_capabilities() -> Dict[str, Dict[str, List[str]]]:
    """Get capabilities of different providers and models."""
    # Get providers with valid API keys
    providers_status = get_available_providers(settings)
    
    capabilities = {}
    
    # Only include providers with valid API keys
    if providers_status.get("openai", False):
        capabilities["openai"] = {
            "models": ["gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"],
            "features": ["chat", "stream"]
        }
        
    if providers_status.get("google", False):
        capabilities["google"] = {
            "models": ["gemini-pro", "gemini-pro-vision"],
            "features": ["chat", "stream"]
        }
        
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
