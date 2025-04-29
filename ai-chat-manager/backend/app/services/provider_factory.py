""" 
Factory for creating appropriate AI provider instances.
"""
from app.services.ai_provider import AIProvider
from app.services.openai_provider import OpenAIProvider
from app.services.anthropic_provider import AnthropicProvider
from app.core.config import settings
import logging
from app.utils.api_key_validator import validate_openai_api_key, validate_anthropic_api_key

# Get logger
logger = logging.getLogger(__name__)

class ProviderError(Exception):
    """Exception raised for provider-related errors."""
    pass

def get_provider(provider_name: str) -> AIProvider:
    """
    Get an AI provider instance based on the provider name.
    
    Args:
        provider_name: Name of the provider (e.g., "openai", "google")
        
    Returns:
        AIProvider instance
        
    Raises:
        ProviderError: If the provider's API key is invalid or missing
        ValueError: If the provider name is not supported
    """
    if provider_name.lower() == "openai":
        # Validate OpenAI API key
        if not settings.OPENAI_API_KEY:
            logger.error("OpenAI API key is missing")
            raise ProviderError("OpenAI API key is missing. Please set the OPENAI_API_KEY environment variable.")
            
        if not validate_openai_api_key(settings.OPENAI_API_KEY):
            logger.error("Invalid OpenAI API key format")
            logger.warning("OpenAI API key has invalid format")
            raise ProviderError("Invalid OpenAI API key format. The key should start with 'sk-' followed by a long string.")
            
        logger.info("Using OpenAI provider")
        return OpenAIProvider(api_key=settings.OPENAI_API_KEY)
        
    elif provider_name.lower() == "google":
        # Validate Google/Gemini API key
        if not settings.GOOGLE_API_KEY:
            logger.error("Google API key is missing")
            raise ProviderError("Google API key is missing. Please set the GOOGLE_API_KEY environment variable.")
            
        # Placeholder for Gemini key validation
        if False: # Temporarily disabled
            logger.error("Invalid Google API key format")
            raise ProviderError("Invalid Google API key format. The key should start with 'AIza' followed by a string.")
            
        logger.info("Using Google provider")
        # TODO: Implement and return GoogleProvider
        raise ProviderError("Google provider is not yet implemented. Please use OpenAI instead.")
        
    elif provider_name.lower() == "anthropic":
        # Validate Anthropic API key
        if not settings.ANTHROPIC_API_KEY:
            logger.error("Anthropic API key is missing")
            raise ProviderError("Anthropic API key is missing. Please set the ANTHROPIC_API_KEY environment variable.")
            
        if not validate_anthropic_api_key(settings.ANTHROPIC_API_KEY):
            logger.error("Invalid Anthropic API key format")
            logger.warning("Anthropic API key has invalid format")
            raise ProviderError("Invalid Anthropic API key format. The key should start with 'sk-ant-' followed by a long string.")
            
        logger.info("Using Anthropic provider")
        return AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY)
        
    # Add other providers as needed
    else:
        logger.error(f"Unsupported AI provider: {provider_name}")
        raise ValueError(f"Unsupported AI provider: {provider_name}")
