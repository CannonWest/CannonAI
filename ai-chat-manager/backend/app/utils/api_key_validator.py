import re
import logging
from typing import Dict, Any
from app.logging import get_logger

logger = get_logger(__name__)

def validate_openai_api_key(api_key: str) -> bool:
    """
    Validates OpenAI API key format
    Format examples: 
    - sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890
    - sk-proj-9RN0FSd7Ne8JnZKTpiYUSjYyJOEx9H_zzyrJ3iU7Fgc6tuEe...
    """
    if not api_key:
        return False
    
    # OpenAI API keys can start with "sk-" or "sk-proj-" and may contain various characters
    pattern = r'^sk-[A-Za-z0-9_-]+$'
    is_valid = bool(re.match(pattern, api_key))
    
    if not is_valid:
        logger.debug("Invalid OpenAI API key format")
    
    return is_valid

def validate_anthropic_api_key(api_key: str) -> bool:
    """
    Validates Anthropic API key format
    Format example: sk-ant-api03-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-aaaaaaaa
    """
    if not api_key:
        return False
    
    # Anthropic API keys typically start with "sk-ant-" and may contain various characters
    pattern = r'^sk-ant-[A-Za-z0-9_-]+$'
    is_valid = bool(re.match(pattern, api_key))
    
    if not is_valid:
        logger.debug("Invalid Anthropic API key format")
    
    return is_valid

def validate_gemini_key(api_key: str) -> bool:
    """
    Validates Google/Gemini API key format
    Format example: AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6
    """
    if not api_key:
        return False
    
    # Google API keys typically start with "AIza"
    pattern = r'^AIza[A-Za-z0-9_-]+$'
    is_valid = bool(re.match(pattern, api_key))
    
    if not is_valid:
        logger.debug("Invalid Google/Gemini API key format")
    
    return is_valid

def get_available_providers(settings) -> Dict[str, bool]:
    """
    Checks which AI providers are available based on API key validation.
    
    Args:
        settings: Application settings containing API keys
        
    Returns:
        Dictionary with provider names as keys and availability as boolean values
    """
    available = {
        "openai": False,
        "google": False,
        "anthropic": False
    }
    
    # Check OpenAI
    if hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY and validate_openai_api_key(settings.OPENAI_API_KEY):
        available["openai"] = True
        logger.info("OpenAI provider is available")
    else:
        logger.warning("OpenAI API key has invalid format")
    
    # Check Google/Gemini
    if hasattr(settings, 'GOOGLE_API_KEY') and settings.GOOGLE_API_KEY and validate_gemini_key(settings.GOOGLE_API_KEY):
        available["google"] = True
        logger.info("Google/Gemini provider is available")
    else:
        logger.warning("Google API key has invalid format")
        
    # Check Anthropic
    if hasattr(settings, 'ANTHROPIC_API_KEY') and settings.ANTHROPIC_API_KEY and validate_anthropic_api_key(settings.ANTHROPIC_API_KEY):
        available["anthropic"] = True
        logger.info("Anthropic provider is available")
    else:
        logger.warning("Anthropic API key has invalid format")
    
    return available
