"""
Base classes and implementations for AI provider services.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class Message(BaseModel):
    """Message model for AI provider communication."""
    role: str
    content: str

class ModelSettings(BaseModel):
    """Common settings for AI model requests."""
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    model_name: str
    # Additional settings can be added as needed

class ChatResponse(BaseModel):
    """Response model from AI provider."""
    message: Message
    raw_response: Dict[str, Any]
    
class AIProvider(ABC):
    """Abstract base class for AI provider implementations."""
    
    @abstractmethod
    async def chat_completion(
        self, 
        messages: List[Message], 
        settings: ModelSettings
    ) -> ChatResponse:
        """
        Send a chat completion request to the AI provider.
        
        Args:
            messages: List of messages representing the conversation history
            settings: Model settings for the request
            
        Returns:
            ChatResponse object with the AI's response
        """
        pass
    
    @abstractmethod
    async def stream_chat_completion(
        self, 
        messages: List[Message], 
        settings: ModelSettings
    ):
        """
        Stream a chat completion response from the AI provider.
        
        Args:
            messages: List of messages representing the conversation history
            settings: Model settings for the request
            
        Yields:
            Chunks of the AI's response as they become available
        """
        pass
    
    @abstractmethod
    def get_available_models(self) -> List[str]:
        """
        Get a list of available models from this provider.
        
        Returns:
            List of model names
        """
        pass

# TODO: Implement concrete provider classes (OpenAIProvider, GoogleProvider, etc.)
