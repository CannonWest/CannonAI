"""
OpenAI implementation of the AI provider interface.
"""
from typing import List, Dict, Any, AsyncGenerator
import json
import httpx
from app.services.ai_provider import AIProvider, Message, ModelSettings, ChatResponse
from app.core.config import settings

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
        
        # Prepare request payload
        payload = {
            "model": settings.model_name,
            "messages": openai_messages,
            "temperature": settings.temperature,
        }
        
        if settings.max_tokens:
            payload["max_tokens"] = settings.max_tokens
        
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
        
        # Prepare request payload
        payload = {
            "model": settings.model_name,
            "messages": openai_messages,
            "temperature": settings.temperature,
            "stream": True
        }
        
        if settings.max_tokens:
            payload["max_tokens"] = settings.max_tokens
        
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
                    print(f"Error processing chunk: {e}")
    
    def get_available_models(self) -> List[str]:
        """Get available models from OpenAI."""
        # TODO: Implement actual API call to get models
        # For now, return a static list of common models
        return [
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo"
        ]

# TODO: Add more provider-specific methods as needed
