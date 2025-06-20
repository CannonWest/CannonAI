#!/usr/bin/env python3
"""
OpenAI AI Provider Implementation.

This module implements the BaseAIProvider interface for OpenAI's GPT models.
Currently a placeholder implementation that will be completed when OpenAI API integration is added.
"""

import os
import asyncio
import logging
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, Tuple
from pathlib import Path

from .base_provider import BaseAIProvider, ProviderConfig, ProviderError

try:
    from openai import OpenAI, AsyncOpenAI
    from openai.types import ChatCompletionMessage
    from openai.types.chat import ChatCompletionChunk
except ImportError:
    logging.error(
        "Failed to import 'openai'. "
        "Please ensure the OpenAI SDK is installed correctly. "
        "Try: pip install openai",
        exc_info=True
    )
    raise

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseAIProvider):
    """OpenAI AI provider implementation."""
    
    # Default OpenAI models - updated to latest available models
    DEFAULT_MODELS = [
        "gpt-4o",
        "gpt-4o-mini", 
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1-preview",
        "o1-mini"
    ]
    
    def __init__(self, config: ProviderConfig):
        """Initialize the OpenAI provider.
        
        Args:
            config: Provider configuration with API key and model
        """
        super().__init__(config)
        logger.info(f"Initializing OpenAIProvider with model: {config.model}")
        
        # Store SDK clients
        self._sync_client: Optional[OpenAI] = None
        self._async_client: Optional[AsyncOpenAI] = None
        
        # Set API base URL if not provided
        if not config.api_base_url:
            config.api_base_url = "https://api.openai.com/v1"
    
    async def initialize(self) -> bool:
        """Initialize the OpenAI client with API key."""
        try:
            if not self.config.api_key:
                logger.error("API key not found in provider configuration.")
                self._is_initialized = False
                return False
                
            logger.info(f"Initializing OpenAI client with API key: {self.config.api_key[:8]}...")
            
            # Initialize both sync and async clients
            self._sync_client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.api_base_url if self.config.api_base_url != "https://api.openai.com/v1" else None
            )
            
            self._async_client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.api_base_url if self.config.api_base_url != "https://api.openai.com/v1" else None
            )
            
            # Test the connection by listing models
            await self.list_models()
            
            logger.info("OpenAI provider initialized successfully")
            self._is_initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI provider: {e}", exc_info=True)
            self._is_initialized = False
            return False
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """Get list of available OpenAI models."""
        if not self._is_initialized or not self._async_client:
            logger.error("OpenAI provider not properly initialized, cannot list models.")
            return self._get_fallback_models()
            
        try:
            logger.debug("Fetching available OpenAI models from API...")
            
            # Use the async client to list models
            models_response = await self._async_client.models.list()
            
            models = []
            api_model_ids = set()
            
            for model in models_response.data:
                # Filter for chat models
                if 'gpt' in model.id or 'o1' in model.id:
                    api_model_ids.add(model.id)
                    
            logger.info(f"Found {len(api_model_ids)} chat models from API")
            
            # Define token limits for known models
            model_limits = {
                "gpt-4o": (128000, 4096),
                "gpt-4o-mini": (128000, 16384),
                "gpt-4-turbo": (128000, 4096),
                "gpt-4-turbo-preview": (128000, 4096),
                "gpt-4": (8192, 8192),
                "gpt-3.5-turbo": (16385, 4096),
                "gpt-3.5-turbo-16k": (16385, 16384),
                "o1-preview": (128000, 32768),
                "o1-mini": (128000, 65536)
            }
            
            # Add models with their metadata
            for model_id in sorted(api_model_ids):
                # Skip deprecated or non-chat models
                if any(skip in model_id for skip in ['instruct', 'davinci', 'curie', 'babbage', 'ada']):
                    continue
                    
                input_limit, output_limit = model_limits.get(model_id, (8192, 4096))
                
                model_info = {
                    'name': model_id,
                    'display_name': model_id.upper().replace('-', ' '),
                    'description': f'OpenAI {model_id} model',
                    'input_token_limit': input_limit,
                    'output_token_limit': output_limit,
                    'supported_methods': ['chat']
                }
                models.append(model_info)
                logger.debug(f"Added model: {model_info['name']}")
            
            if not models:
                logger.warning("No suitable chat models found from API, using fallback list")
                return self._get_fallback_models()
                
            logger.info(f"Total OpenAI chat models available: {len(models)}")
            return models
            
        except Exception as e:
            logger.error(f"Error listing OpenAI models: {e}", exc_info=True)
            return self._get_fallback_models()
    
    def _get_fallback_models(self) -> List[Dict[str, Any]]:
        """Get fallback model list if API call fails."""
        logger.info("Using fallback model list for OpenAI")
        
        model_limits = {
            "gpt-4o": (128000, 4096),
            "gpt-4o-mini": (128000, 16384),
            "gpt-4-turbo": (128000, 4096),
            "gpt-4": (8192, 8192),
            "gpt-3.5-turbo": (16385, 4096),
            "o1-preview": (128000, 32768),
            "o1-mini": (128000, 65536)
        }
        
        models = []
        for model_id in self.DEFAULT_MODELS:
            input_limit, output_limit = model_limits.get(model_id, (8192, 4096))
            
            model_info = {
                'name': model_id,
                'display_name': model_id.upper().replace('-', ' '),
                'description': f'OpenAI {model_id} model (fallback)',
                'input_token_limit': input_limit,
                'output_token_limit': output_limit,
                'supported_methods': ['chat']
            }
            models.append(model_info)
            
        return models
    
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> Union[Tuple[str, Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
        """Generate a response from OpenAI.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            params: Generation parameters
            stream: Whether to stream the response
            
        Returns:
            If stream=False: Tuple of (response_text, metadata)
            If stream=True: AsyncGenerator yielding response chunks
        """
        if not self._is_initialized or not self._async_client:
            raise ProviderError("OpenAI provider not properly initialized")
            
        logger.debug(f"Generating {'streaming' if stream else 'non-streaming'} response with {len(messages)} messages")
        
        # Normalize messages for OpenAI format
        normalized_messages = self.normalize_messages(messages)
        
        # Extract system instruction if present
        system_instruction = None
        if messages and messages[0].get('system_instruction_override'):
            system_instruction = messages[0]['system_instruction_override']
            logger.debug(f"Using system instruction: {system_instruction[:50]}...")
            
        # Build final message list
        final_messages = []
        
        # Add system message if present
        if system_instruction:
            final_messages.append({
                'role': 'system',
                'content': system_instruction
            })
            
        # Add normalized messages
        final_messages.extend(normalized_messages)
        
        # Prepare parameters
        merged_params = self.get_default_params()
        if params:
            merged_params.update(params)
            
        # Map parameters to OpenAI format
        openai_params = {
            'model': self.config.model,
            'messages': final_messages,
            'temperature': merged_params.get('temperature', 0.7),
            'max_tokens': merged_params.get('max_output_tokens', 800),
            'top_p': merged_params.get('top_p', 1.0),
            'frequency_penalty': merged_params.get('frequency_penalty', 0.0),
            'presence_penalty': merged_params.get('presence_penalty', 0.0),
            'stream': stream
        }
        
        # Add stop sequences if provided
        if 'stop_sequences' in merged_params and merged_params['stop_sequences']:
            openai_params['stop'] = merged_params['stop_sequences']
            
        # Special handling for o1 models - they don't support some parameters
        if self.config.model.startswith('o1'):
            logger.info(f"Using o1 model {self.config.model}, removing unsupported parameters")
            # o1 models only support max_completion_tokens, not max_tokens
            if 'max_tokens' in openai_params:
                openai_params['max_completion_tokens'] = openai_params.pop('max_tokens')
            # Remove unsupported parameters
            for param in ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty']:
                openai_params.pop(param, None)
        
        logger.debug(f"OpenAI request params: model={openai_params['model']}, stream={stream}")
        
        if stream:
            return self._stream_openai_response(openai_params)
        else:
            return await self._generate_openai_response_non_stream(openai_params)
    
    async def _generate_openai_response_non_stream(
        self,
        params: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """Generate non-streaming response from OpenAI."""
        try:
            response = await self._async_client.chat.completions.create(**params)
            
            # Extract response text
            response_text = response.choices[0].message.content or ""
            
            # Extract token usage
            token_usage = {}
            if response.usage:
                token_usage = {
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens
                }
                
            logger.debug(f"OpenAI response generated. Tokens: {token_usage}")
            
            return response_text, {'token_usage': token_usage}
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}", exc_info=True)
            raise ProviderError(f"OpenAI API error: {str(e)}")
    
    async def _stream_openai_response(
        self,
        params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream response from OpenAI."""
        try:
            # Create the stream
            stream = await self._async_client.chat.completions.create(**params)
            
            full_response = ""
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    chunk_text = chunk.choices[0].delta.content
                    full_response += chunk_text
                    
                    yield {
                        'chunk': chunk_text,
                        'accumulated': full_response
                    }
            
            # Final yield with token usage (note: streaming doesn't provide token counts in real-time)
            yield {
                'done': True,
                'full_response': full_response,
                'token_usage': {
                    'prompt_tokens': 0,  # Not available in streaming
                    'completion_tokens': 0,  # Not available in streaming
                    'total_tokens': 0  # Not available in streaming
                }
            }
            
        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}", exc_info=True)
            yield {
                'error': f"OpenAI streaming error: {str(e)}"
            }
    
    def validate_model(self, model_name: str) -> bool:
        """Check if a model name is valid for OpenAI."""
        logger.debug(f"Validating model name: {model_name}")
        
        # Check if it's an OpenAI model
        is_valid = (
            model_name.startswith("gpt") or 
            model_name.startswith("o1") or
            model_name in self.DEFAULT_MODELS
        )
        logger.debug(f"Model '{model_name}' is {'valid' if is_valid else 'invalid'} for OpenAI")
        
        return is_valid
    
    def get_default_params(self) -> Dict[str, Any]:
        """Get default generation parameters for OpenAI."""
        return {
            'temperature': 0.7,
            'max_tokens': 800,
            'top_p': 0.95,
            'frequency_penalty': 0.0,
            'presence_penalty': 0.0,
            'stop_sequences': None
        }
    
    def normalize_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Normalize message format for OpenAI API."""
        logger.debug(f"Normalizing {len(messages)} messages for OpenAI format")
        
        normalized = []
        
        for i, msg in enumerate(messages):
            # Skip the first message if it only contains system instruction
            if i == 0 and msg.get('system_instruction_override') and not msg.get('content'):
                continue
                
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            
            # Skip empty messages
            if not content.strip():
                continue
            
            # Map roles to OpenAI format
            if role in ['human', 'user']:
                role = 'user'
            elif role in ['ai', 'assistant', 'model']:
                role = 'assistant'
            elif role == 'system':
                # Skip system role here as it's handled separately
                continue
            else:
                logger.warning(f"Unknown role '{role}', defaulting to 'user'")
                role = 'user'
            
            normalized.append({
                'role': role,
                'content': content
            })
        
        return normalized
