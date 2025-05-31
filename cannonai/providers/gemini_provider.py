"""
Google Gemini AI Provider Implementation.

This module implements the BaseAIProvider interface for Google's Gemini AI models.
It handles all Gemini-specific API interactions and conversions.
"""

import os
import asyncio
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, Tuple
from pathlib import Path

from .base_provider import BaseAIProvider, ProviderConfig, ProviderError

# Import Gemini-specific libraries
try:
    from google import genai
    from google.genai import types
    print("DEBUG: Successfully imported google.genai")
except ImportError as e:
    print(f"ERROR: Failed to import google-genai: {e}")
    print("Please install with: pip install google-genai")
    raise


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI provider implementation."""
    
    # Default models list in case API call fails
    DEFAULT_MODELS = [
        "gemini-2.0-flash",
        "gemini-2.0-pro", 
        "gemini-2.5-flash-preview-05-20",
        "gemini-2.5-pro-preview-05-06"
    ]
    
    def __init__(self, config: ProviderConfig):
        """Initialize the Gemini provider.
        
        Args:
            config: Provider configuration with API key and model
        """
        super().__init__(config)
        print(f"DEBUG: Initializing GeminiProvider with model: {config.model}")
        
        # Validate model name format
        if not config.model.startswith("gemini") and not config.model.startswith("models/gemini"):
            print(f"WARNING: Model name '{config.model}' doesn't look like a Gemini model")
    
    async def initialize(self) -> bool:
        """Initialize the Gemini client with API key."""
        try:
            print(f"DEBUG: Initializing Gemini client with API key: {self.config.api_key[:8]}...")
            
            # Initialize the Gemini client
            self._client = genai.Client(api_key=self.config.api_key)
            
            # Test the connection by listing models
            models = await self.list_models()
            print(f"DEBUG: Successfully connected to Gemini. Found {len(models)} models.")
            
            self._is_initialized = True
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to initialize Gemini client: {e}")
            self._is_initialized = False
            return False
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """Get list of available Gemini models."""
        print("DEBUG: Fetching available Gemini models...")
        
        try:
            if not self._client:
                raise ProviderError("Gemini client not initialized")
            
            # Get models from API
            models_response = await self._client.models.list()
            models = []
            
            async for model in models_response:
                # Only include models that support generateContent
                if hasattr(model, 'supported_generation_methods') and \
                   'generateContent' in model.supported_generation_methods:
                    
                    model_info = {
                        'name': model.name,
                        'display_name': model.display_name or model.name,
                        'description': getattr(model, 'description', ''),
                        'input_token_limit': getattr(model, 'input_token_limit', None),
                        'output_token_limit': getattr(model, 'output_token_limit', None),
                        'supported_methods': list(model.supported_generation_methods)
                    }
                    models.append(model_info)
                    print(f"DEBUG: Found model: {model_info['name']} ({model_info['display_name']})")
            
            if not models:
                print("WARNING: No models returned from API, using default list")
                # Fallback to default models
                models = [
                    {
                        'name': f"models/{model}",
                        'display_name': model.replace('-', ' ').title(),
                        'description': 'Default model',
                        'input_token_limit': None,
                        'output_token_limit': None,
                        'supported_methods': ['generateContent']
                    }
                    for model in self.DEFAULT_MODELS
                ]
            
            print(f"DEBUG: Total models available: {len(models)}")
            return models
            
        except Exception as e:
            print(f"ERROR: Failed to list Gemini models: {e}")
            # Return default models on error
            return [
                {
                    'name': f"models/{model}",
                    'display_name': model.replace('-', ' ').title(),
                    'description': 'Default model (API unavailable)',
                    'input_token_limit': None,
                    'output_token_limit': None,
                    'supported_methods': ['generateContent']
                }
                for model in self.DEFAULT_MODELS
            ]
    
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> Union[Tuple[str, Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
        """Generate a response from Gemini.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            params: Generation parameters
            stream: Whether to stream the response
            
        Returns:
            If stream=False: Tuple of (response_text, metadata)
            If stream=True: AsyncGenerator yielding response chunks
        """
        print(f"DEBUG: Generating {'streaming' if stream else 'non-streaming'} response with {len(messages)} messages")
        
        if not self._client:
            raise ProviderError("Gemini client not initialized")
        
        # Normalize messages for Gemini format
        normalized_messages = self._convert_to_gemini_format(messages)
        
        # Get generation config
        gen_config = self._build_generation_config(params)
        
        # Ensure model name has correct format
        model_name = self.config.model
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"
        
        print(f"DEBUG: Using model: {model_name}")
        print(f"DEBUG: Generation config: {gen_config}")
        
        if stream:
            return self._stream_response(model_name, normalized_messages, gen_config)
        else:
            return await self._generate_response(model_name, normalized_messages, gen_config)
    
    async def _generate_response(
        self, 
        model_name: str, 
        messages: List[types.Content],
        gen_config: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """Generate a non-streaming response."""
        print("DEBUG: Generating non-streaming response...")
        
        try:
            response = await self._client.models.generate_content(
                model=model_name,
                contents=messages,
                config=types.GenerateContentConfig(**gen_config)
            )
            
            # Extract text from response
            if hasattr(response, 'text'):
                response_text = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                # Handle multiple candidates if present
                response_text = response.candidates[0].content.parts[0].text
            else:
                raise ProviderError("No text found in Gemini response")
            
            # Extract token usage
            token_usage = self.extract_token_usage(response)
            
            print(f"DEBUG: Generated response: {response_text[:100]}... (length: {len(response_text)})")
            print(f"DEBUG: Token usage: {token_usage}")
            
            return response_text, {'token_usage': token_usage}
            
        except Exception as e:
            print(f"ERROR: Failed to generate response: {e}")
            raise ProviderError(f"Gemini generation failed: {e}")
    
    async def _stream_response(
        self,
        model_name: str,
        messages: List[types.Content],
        gen_config: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Generate a streaming response."""
        print("DEBUG: Starting streaming response...")
        
        try:
            # Create streaming response
            response_stream = self._client.models.generate_content_stream(
                model=model_name,
                contents=messages,
                config=types.GenerateContentConfig(**gen_config)
            )
            
            accumulated_text = ""
            token_usage = {}
            
            async for chunk in response_stream:
                if hasattr(chunk, 'text') and chunk.text:
                    chunk_text = chunk.text
                    accumulated_text += chunk_text
                    
                    yield {
                        'chunk': chunk_text,
                        'accumulated': accumulated_text
                    }
                
                # Try to extract token usage from chunk
                if hasattr(chunk, 'usage_metadata'):
                    token_usage = self.extract_token_usage(chunk)
            
            # Send final message with token usage
            yield {
                'done': True,
                'full_response': accumulated_text,
                'token_usage': token_usage
            }
            
            print(f"DEBUG: Streaming complete. Total length: {len(accumulated_text)}")
            
        except Exception as e:
            print(f"ERROR: Streaming failed: {e}")
            yield {'error': str(e)}
    
    def _convert_to_gemini_format(self, messages: List[Dict[str, str]]) -> List[types.Content]:
        """Convert messages to Gemini's Content format."""
        print(f"DEBUG: Converting {len(messages)} messages to Gemini format")
        
        gemini_messages = []
        
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            
            # Map roles to Gemini format
            if role in ['user', 'human']:
                gemini_role = 'user'
            elif role in ['assistant', 'ai', 'model']:
                gemini_role = 'model'
            elif role == 'system':
                # Gemini doesn't have a system role, prepend to first user message
                print("WARNING: Gemini doesn't support system role, converting to user message")
                gemini_role = 'user'
                content = f"System: {content}"
            else:
                print(f"WARNING: Unknown role '{role}', defaulting to 'user'")
                gemini_role = 'user'
            
            # Create Content object
            gemini_content = types.Content(
                role=gemini_role,
                parts=[types.Part.from_text(text=content)]
            )
            
            gemini_messages.append(gemini_content)
        
        return gemini_messages
    
    def _build_generation_config(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build generation configuration for Gemini."""
        # Start with default parameters
        config = self.get_default_params().copy()
        
        # Override with provided parameters
        if params:
            config.update(params)
        
        # Map common parameter names to Gemini's expected names
        gemini_config = {
            'temperature': config.get('temperature', 0.7),
            'max_output_tokens': config.get('max_tokens', config.get('max_output_tokens', 800)),
            'top_p': config.get('top_p', 0.95),
            'top_k': config.get('top_k', 40),
        }
        
        # Remove None values
        gemini_config = {k: v for k, v in gemini_config.items() if v is not None}
        
        return gemini_config
    
    def validate_model(self, model_name: str) -> bool:
        """Check if a model name is valid for Gemini."""
        print(f"DEBUG: Validating model name: {model_name}")
        
        # Accept both formats: "gemini-1.5-pro" and "models/gemini-1.5-pro"
        if model_name.startswith("models/"):
            model_name = model_name[7:]  # Remove "models/" prefix
        
        # Check if it's a Gemini model
        is_valid = model_name.startswith("gemini")
        print(f"DEBUG: Model '{model_name}' is {'valid' if is_valid else 'invalid'} for Gemini")
        
        return is_valid
    
    def get_default_params(self) -> Dict[str, Any]:
        """Get default generation parameters for Gemini."""
        return {
            'temperature': 0.7,
            'max_output_tokens': 800,
            'top_p': 0.95,
            'top_k': 40,
        }
    
    def extract_token_usage(self, response: Any) -> Dict[str, Any]:
        """Extract token usage from Gemini response."""
        token_usage = {}
        
        try:
            if hasattr(response, 'usage_metadata'):
                metadata = response.usage_metadata
                
                # Extract token counts
                if hasattr(metadata, 'prompt_token_count'):
                    token_usage['prompt_tokens'] = metadata.prompt_token_count
                if hasattr(metadata, 'candidates_token_count'):
                    token_usage['completion_tokens'] = metadata.candidates_token_count
                if hasattr(metadata, 'total_token_count'):
                    token_usage['total_tokens'] = metadata.total_token_count
                
                print(f"DEBUG: Extracted token usage: {token_usage}")
                
        except Exception as e:
            print(f"WARNING: Failed to extract token usage: {e}")
        
        return token_usage
