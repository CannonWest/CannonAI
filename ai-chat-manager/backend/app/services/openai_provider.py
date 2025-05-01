"""
OpenAI implementation of the AI provider interface.
"""
from typing import List, Dict, Any, AsyncGenerator, Optional
import json
import logging
import httpx
from app.services.ai_provider import AIProvider, Message, ModelSettings, ChatResponse
from app.core.config import settings
from app.logging import get_logger
from app.models.openai.model_config import (
    ModelInfo, 
    OPENAI_MODELS,
    get_default_model,
    get_model_by_id,
    get_model_by_version,
    get_model_names,
    get_versioned_model_names,
    ModelCapabilities
)

# Configure logger
logger = get_logger(__name__)

class OpenAIProvider(AIProvider):
    """OpenAI implementation of AIProvider."""
    
    def __init__(self, api_key: str = None):
        """
        Initialize OpenAI provider.
        
        Args:
            api_key: OpenAI API key (defaults to settings.OPENAI_API_KEY)
        """
        self.api_key = api_key or settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        self.base_url = "https://api.openai.com/v1"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
    
    def _resolve_model_name(self, model_name: str) -> str:
        """
        Resolve a model name to its versioned API equivalent.
        
        Args:
            model_name: The model name as provided in settings
            
        Returns:
            The versioned model name to use in API calls
        """
        # If the model name already includes a version, use it directly
        if "-202" in model_name:  # Quick check if it's already a versioned model
            return model_name
            
        # Otherwise, look up the model and get its versioned name
        model = get_model_by_id(model_name)
        if model:
            return model.version
            
        # Fallback to the provided name if not found
        logger.warning(f"Unknown model: {model_name}, using as is")
        return model_name
    
    async def chat_completion(
        self, 
        messages: List[Message], 
        settings: ModelSettings
    ) -> ChatResponse:
        """Implement chat completion for OpenAI."""
        
        # Convert our message format to OpenAI format
        openai_messages = [
            {"role": msg.role, "content": msg.content} 
            for msg in messages
        ]
        
        # Resolve the model name to its versioned equivalent
        model_name = self._resolve_model_name(settings.model_name)
        
        # Prepare request payload
        payload = {
            "model": model_name,
            "messages": openai_messages,
            "temperature": settings.temperature,
        }
        
        if settings.max_tokens:
            payload["max_tokens"] = settings.max_tokens
        
        logger.debug(f"Sending chat completion request to OpenAI with model: {model_name}")
        
        # Send request to OpenAI
        response = await self.client.post(
            f"{self.base_url}/chat/completions", 
            json=payload
        )
        response.raise_for_status()
        response_data = response.json()
        
        # Extract the message from the response
        ai_message = Message(
            role="assistant",
            content=response_data["choices"][0]["message"]["content"]
        )
        
        return ChatResponse(
            message=ai_message,
            raw_response=response_data
        )
    
    async def stream_chat_completion(
        self, 
        messages: List[Message], 
        settings: ModelSettings
    ) -> AsyncGenerator[str, None]:
        """Implement streaming chat completion for OpenAI."""
        
        # Convert our message format to OpenAI format
        openai_messages = [
            {"role": msg.role, "content": msg.content} 
            for msg in messages
        ]
        
        # Resolve the model name to its versioned equivalent
        model_name = self._resolve_model_name(settings.model_name)
        
        # Prepare request payload
        payload = {
            "model": model_name,
            "messages": openai_messages,
            "temperature": settings.temperature,
            "stream": True
        }
        
        if settings.max_tokens:
            payload["max_tokens"] = settings.max_tokens
        
        logger.debug(f"Sending streaming chat completion request to OpenAI with model: {model_name}")
        
        # Send streaming request to OpenAI
        async with self.client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=60.0
        ) as response:
            response.raise_for_status()
            
            # Process the streaming response
            async for chunk in response.aiter_lines():
                if not chunk.strip():
                    continue
                
                if chunk.startswith("data:"):
                    chunk = chunk[5:].strip()
                    
                if chunk == "[DONE]":
                    break
                
                try:
                    # Parse the chunk JSON
                    chunk_data = json.loads(chunk)
                    delta = chunk_data["choices"][0].get("delta", {})
                    if "content" in delta:
                        yield delta["content"]
                except Exception as e:
                    logger.error(f"Error processing chunk: {e}")
    
    def get_available_models(self) -> List[str]:
        """
        Get available models from OpenAI.
        
        Returns:
            List of model display names
        """
        return [model.display_name for model in OPENAI_MODELS]
    
    def get_model_details(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific model.
        
        Args:
            model_name: The model name to get details for
            
        Returns:
            Dictionary with model details or None if not found
        """
        model = get_model_by_id(model_name)
        if not model:
            model = get_model_by_version(model_name)
            
        if not model:
            return None
            
        return {
            "display_name": model.display_name,
            "model_id": model.model_id,
            "version": model.version,
            "pricing": {
                "input_price": model.pricing.input_price,
                "cached_input_price": model.pricing.cached_input_price,
                "output_price": model.pricing.output_price,
            },
            "capabilities": [cap.value for cap in model.capabilities],
            "context_window": model.context_window,
            "is_preview": model.is_preview,
            "is_default": model.is_default,
        }
    
    def get_model_groups(self) -> Dict[str, List[str]]:
        """
        Get models grouped by series.
        
        Returns:
            Dictionary with model series as keys and lists of model IDs as values
        """
        groups = {
            "gpt4": [],
            "gpt4o": [],
            "o_series": [],
        }
        
        for model in OPENAI_MODELS:
            if model.model_id.startswith("gpt-4."):
                groups["gpt4"].append(model.model_id)
            elif model.model_id.startswith("gpt-4o"):
                groups["gpt4o"].append(model.model_id)
            elif model.model_id.startswith("o"):
                groups["o_series"].append(model.model_id)
                
        return groups
    
    def calculate_token_cost(
        self, 
        model_name: str, 
        input_tokens: int, 
        output_tokens: int, 
        use_cached_input: bool = False
    ) -> Optional[float]:
        """
        Calculate the estimated cost for a given number of tokens.
        
        Args:
            model_name: The model to calculate costs for
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            use_cached_input: Whether to use cached input pricing
            
        Returns:
            Estimated cost in USD or None if model not found
        """
        model = get_model_by_id(model_name)
        if not model:
            model = get_model_by_version(model_name)
            
        if not model:
            return None
            
        input_price = model.pricing.cached_input_price if use_cached_input and model.pricing.cached_input_price else model.pricing.input_price
        output_price = model.pricing.output_price
        
        # Calculate cost (converting from per 1M tokens to per token)
        input_cost = (input_tokens * input_price) / 1_000_000
        output_cost = (output_tokens * output_price) / 1_000_000
        
        return input_cost + output_cost
    
    def get_model_by_capability(self, capability: str) -> List[str]:
        """
        Get models that support a specific capability.
        
        Args:
            capability: The capability to filter by (e.g., "vision", "audio")
            
        Returns:
            List of model IDs that support the capability
        """
        try:
            cap = ModelCapabilities(capability)
            return [model.model_id for model in OPENAI_MODELS if cap in model.capabilities]
        except ValueError:
            logger.warning(f"Unknown capability: {capability}")
            return []
    
    def get_default_model(self) -> str:
        """
        Get the default model for general use.
        
        Returns:
            Model ID of the default model
        """
        return get_default_model().model_id
