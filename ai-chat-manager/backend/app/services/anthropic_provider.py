"""
Anthropic AI provider implementation.
"""
from typing import AsyncGenerator, Dict, Any, List
import aiohttp
import json
import logging
from app.services.ai_provider import AIProvider

logger = logging.getLogger(__name__)

class AnthropicProvider(AIProvider):
    """
    Implementation of the AIProvider interface for Anthropic's Claude API.
    """
    
    def __init__(self, api_key: str):
        """
        Initialize the Anthropic provider with the given API key.
        
        Args:
            api_key: Anthropic API key
        """
        self.api_key = api_key
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
        logger.info("Anthropic provider initialized")
    
    async def generate_response(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False,
        settings: Dict[str, Any] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a response from the Anthropic API.
        
        Args:
            prompt: The user's message
            model: The model to use
            temperature: The temperature for sampling
            max_tokens: The maximum number of tokens to generate
            stream: Whether to stream the response
            settings: Additional settings for the request
            
        Yields:
            Chunks of the generated response if streaming, or the full response
            
        Raises:
            Exception: If there is an error from the API
        """
        # Use default values if settings not provided
        settings = settings or {}
        
        # Build request payload
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream
        }
        
        # Add any additional settings
        for key, value in settings.items():
            if key not in payload:
                payload[key] = value
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Anthropic API error: {response.status} - {error_text}")
                        raise Exception(f"Anthropic API error: {response.status} - {error_text}")
                    
                    if stream:
                        # Process streaming response
                        async for line in response.content:
                            if line:
                                try:
                                    # Parse SSE line
                                    line = line.decode("utf-8").strip()
                                    if line.startswith("data: "):
                                        data = json.loads(line[6:])
                                        
                                        if data.get("type") == "content_block_delta":
                                            chunk = data.get("delta", {}).get("text", "")
                                            if chunk:
                                                yield chunk
                                        
                                        elif data.get("type") == "message_stop":
                                            break
                                            
                                except Exception as e:
                                    logger.error(f"Error parsing Anthropic stream response: {str(e)}")
                    else:
                        # Process non-streaming response
                        response_json = await response.json()
                        content = response_json.get("content", [{}])[0].get("text", "")
                        yield content
                        
        except Exception as e:
            logger.error(f"Error communicating with Anthropic API: {str(e)}")
            raise Exception(f"Error communicating with Anthropic API: {str(e)}")
    
    def get_available_models(self) -> List[str]:
        """
        Get the list of available models for Anthropic.
        
        Returns:
            List of model names
        """
        return [
            "claude-3-opus",
            "claude-3-sonnet",
            "claude-3-haiku"
        ]
