#!/usr/bin/env python3
"""
DeepSeek AI Provider Implementation.

This module implements the BaseAIProvider interface for DeepSeek's AI models.
DeepSeek provides both chat and reasoning models with different capabilities.
"""

import os
import asyncio
import logging
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, Tuple
from pathlib import Path

from .base_provider import BaseAIProvider, ProviderConfig, ProviderError

try:
    from openai import OpenAI, AsyncOpenAI
except ImportError:
    logging.error(
        "Failed to import 'openai'. "
        "DeepSeek uses the OpenAI SDK for API compatibility. "
        "Please ensure the OpenAI SDK is installed correctly. "
        "Try: pip install openai",
        exc_info=True
    )
    raise

logger = logging.getLogger(__name__)


class DeepSeekProvider(BaseAIProvider):
    """DeepSeek AI provider implementation."""
    
    # DeepSeek models
    DEFAULT_MODELS = [
        "deepseek-chat",
        "deepseek-reasoner"
    ]
    
    # Model specifications from documentation
    MODEL_SPECS = {
        "deepseek-chat": {
            "context_window": 64000,  # 64K
            "default_output": 4096,   # 4K default
            "max_output_tokens": 8192  # 8K max
        },
        "deepseek-reasoner": {
            "context_window": 64000,   # 64K
            "default_output": 32768,   # 32K default
            "max_output_tokens": 65536  # 64K max
        }
    }
    
    def __init__(self, config: ProviderConfig):
        """Initialize the DeepSeek provider.
        
        Args:
            config: Provider configuration with API key and model
        """
        super().__init__(config)
        logger.info(f"Initializing DeepSeekProvider with model: {config.model}")
        
        # Store SDK clients
        self._sync_client: Optional[OpenAI] = None
        self._async_client: Optional[AsyncOpenAI] = None
        
        # Set API base URL if not provided
        if not config.api_base_url:
            config.api_base_url = "https://api.deepseek.com"
            logger.debug(f"Using default DeepSeek API base URL: {config.api_base_url}")
    
    async def initialize(self) -> bool:
        """Initialize the DeepSeek client with API key."""
        try:
            if not self.config.api_key:
                logger.error("API key not found in provider configuration.")
                self._is_initialized = False
                return False
                
            logger.info(f"Initializing DeepSeek client with API key: {self.config.api_key[:8]}...")
            
            # Initialize both sync and async clients using OpenAI SDK
            self._sync_client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.api_base_url
            )
            
            self._async_client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.api_base_url
            )
            
            # Test the connection by listing models
            await self.list_models()
            
            logger.info("DeepSeek provider initialized successfully")
            self._is_initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize DeepSeek provider: {e}", exc_info=True)
            self._is_initialized = False
            return False
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """Get list of available DeepSeek models."""
        if not self._is_initialized or not self._async_client:
            logger.error("DeepSeek provider not properly initialized, cannot list models.")
            return self._get_fallback_models()
            
        try:
            logger.debug("Fetching available DeepSeek models from API...")
            
            # Use the async client to list models
            models_response = await self._async_client.models.list()
            
            models = []
            api_model_ids = set()
            
            # Extract model IDs from API response
            for model in models_response.data:
                api_model_ids.add(model.id)
                logger.debug(f"Found model from API: {model.id}")
            
            logger.info(f"Found {len(api_model_ids)} models from DeepSeek API")
            
            # Build model list with specifications
            for model_id in sorted(api_model_ids):
                if model_id in self.MODEL_SPECS:
                    spec = self.MODEL_SPECS[model_id]
                    model_info = {
                        'name': model_id,
                        'display_name': model_id.replace('-', ' ').title(),
                        'description': f'DeepSeek {model_id} model',
                        'input_token_limit': spec['context_window'],
                        'output_token_limit': spec['max_output_tokens'],
                        'default_output_tokens': spec['default_output'],
                        'supported_methods': ['chat']
                    }
                    models.append(model_info)
                    logger.debug(f"Added model: {model_info['name']} with context: {spec['context_window']}, max output: {spec['max_output_tokens']}")
                else:
                    # For unknown models from API
                    model_info = {
                        'name': model_id,
                        'display_name': model_id.replace('-', ' ').title(),
                        'description': f'DeepSeek {model_id} model',
                        'input_token_limit': 64000,  # Default to 64K
                        'output_token_limit': 8192,   # Default to 8K
                        'supported_methods': ['chat']
                    }
                    models.append(model_info)
                    logger.warning(f"Added unknown model {model_id} with default specs")
            
            if not models:
                logger.warning("No models found from API, using fallback list")
                return self._get_fallback_models()
                
            logger.info(f"Total DeepSeek models available: {len(models)}")
            return models
            
        except Exception as e:
            logger.error(f"Error listing DeepSeek models: {e}", exc_info=True)
            return self._get_fallback_models()
    
    def _get_fallback_models(self) -> List[Dict[str, Any]]:
        """Get fallback model list if API call fails."""
        logger.info("Using fallback model list for DeepSeek")
        
        models = []
        for model_id in self.DEFAULT_MODELS:
            spec = self.MODEL_SPECS[model_id]
            model_info = {
                'name': model_id,
                'display_name': model_id.replace('-', ' ').title(),
                'description': f'DeepSeek {model_id} model (fallback)',
                'input_token_limit': spec['context_window'],
                'output_token_limit': spec['max_output_tokens'],
                'default_output_tokens': spec['default_output'],
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
        """Generate a response from DeepSeek.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            params: Generation parameters
            stream: Whether to stream the response
            
        Returns:
            If stream=False: Tuple of (response_text, metadata)
            If stream=True: AsyncGenerator yielding response chunks
        """
        if not self._is_initialized or not self._async_client:
            raise ProviderError("DeepSeek provider not properly initialized")
            
        logger.debug(f"Generating {'streaming' if stream else 'non-streaming'} response with {len(messages)} messages")
        
        # Normalize messages for DeepSeek format
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
            
        # Get model-specific max tokens
        model_spec = self.MODEL_SPECS.get(self.config.model, self.MODEL_SPECS['deepseek-chat'])
        max_tokens = merged_params.get('max_output_tokens', model_spec['default_output'])
        
        # Ensure max_tokens doesn't exceed model limit
        if max_tokens > model_spec['max_output_tokens']:
            logger.warning(f"Requested max_tokens {max_tokens} exceeds model limit {model_spec['max_output_tokens']}, capping to limit")
            max_tokens = model_spec['max_output_tokens']
            
        # Map parameters to DeepSeek/OpenAI format
        deepseek_params = {
            'model': self.config.model,
            'messages': final_messages,
            'temperature': merged_params.get('temperature', 0.7),
            'max_tokens': max_tokens,
            'top_p': merged_params.get('top_p', 1.0),
            'frequency_penalty': merged_params.get('frequency_penalty', 0.0),
            'presence_penalty': merged_params.get('presence_penalty', 0.0),
            'stream': stream
        }
        
        # Add response format if specified
        if 'response_format' in merged_params:
            deepseek_params['response_format'] = merged_params['response_format']
            
        # Add stop sequences if provided
        if 'stop_sequences' in merged_params and merged_params['stop_sequences']:
            deepseek_params['stop'] = merged_params['stop_sequences']
            
        # Add tool-related parameters if provided
        if 'tools' in merged_params:
            deepseek_params['tools'] = merged_params['tools']
        if 'tool_choice' in merged_params:
            deepseek_params['tool_choice'] = merged_params['tool_choice']
            
        # Add logprobs parameters if provided
        if 'logprobs' in merged_params:
            deepseek_params['logprobs'] = merged_params['logprobs']
        if 'top_logprobs' in merged_params:
            deepseek_params['top_logprobs'] = merged_params['top_logprobs']
        
        logger.debug(f"DeepSeek request params: model={deepseek_params['model']}, max_tokens={max_tokens}, stream={stream}")
        
        if stream:
            return self._stream_deepseek_response(deepseek_params)
        else:
            return await self._generate_deepseek_response_non_stream(deepseek_params)
    
    async def _generate_deepseek_response_non_stream(
        self,
        params: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """Generate non-streaming response from DeepSeek."""
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
                
            logger.debug(f"DeepSeek response generated. Tokens: {token_usage}")
            
            return response_text, {'token_usage': token_usage}
            
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}", exc_info=True)
            raise ProviderError(f"DeepSeek API error: {str(e)}")
    
    async def _stream_deepseek_response(
        self,
        params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream response from DeepSeek."""
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
            logger.error(f"DeepSeek streaming error: {e}", exc_info=True)
            yield {
                'error': f"DeepSeek streaming error: {str(e)}"
            }
    
    def validate_model(self, model_name: str) -> bool:
        """Check if a model name is valid for DeepSeek."""
        logger.debug(f"Validating model name: {model_name}")
        
        # Check if it's a DeepSeek model
        is_valid = (
            model_name.startswith("deepseek") or 
            model_name in self.DEFAULT_MODELS
        )
        logger.debug(f"Model '{model_name}' is {'valid' if is_valid else 'invalid'} for DeepSeek")
        
        return is_valid
    
    def get_default_params(self) -> Dict[str, Any]:
        """Get default generation parameters for DeepSeek."""
        # Get model-specific defaults
        model_spec = self.MODEL_SPECS.get(self.config.model, self.MODEL_SPECS['deepseek-chat'])
        
        return {
            'temperature': 0.7,
            'max_output_tokens': model_spec['default_output'],
            'top_p': 1.0,
            'frequency_penalty': 0.0,
            'presence_penalty': 0.0,
            'stop_sequences': None,
            'response_format': {'type': 'text'}  # Default to text format
        }
    
    def normalize_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Normalize message format for DeepSeek API."""
        logger.debug(f"Normalizing {len(messages)} messages for DeepSeek format")
        
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
            
            # Map roles to DeepSeek/OpenAI format
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
