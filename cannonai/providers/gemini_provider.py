#!/usr/bin/env python3
"""
Google Gemini AI Provider Implementation.

This module implements the BaseAIProvider interface for Google's Gemini AI models.
It handles all Gemini-specific API interactions and conversions.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, Tuple

from .base_provider import BaseAIProvider, ProviderConfig, ProviderError

try:
    from google import genai
    from google.genai import types  # For GenerationConfig, Content, Part, etc.
except ImportError:
    logging.error("Failed to import google-genai. Please install with: pip install google-genai", exc_info=True)
    raise

# Initialize logger for this module
logger = logging.getLogger(__name__)


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI provider implementation."""

    DEFAULT_FALLBACK_MODELS = [
        "gemini-2.0-flash", "gemini-2.0-pro",
        "gemini-2.5-flash-preview-05-20", "gemini-2.5-pro-preview-05-06"
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not config.model.startswith("gemini") and not config.model.startswith("models/gemini"):
            logger.warning(f"Model name '{config.model}' might not be a Gemini model.")

    async def initialize(self) -> bool:
        """
        Initializes the Gemini client using the API key from the config.
        It attempts to list models to verify the connection but will not fail initialization
        if listing models fails, only log a warning.
        """
        try:
            self._client = genai.Client(api_key=self.config.api_key)
            try:
                await self.list_models()
                logger.info("GeminiProvider connected and successfully listed models during init.")
            except Exception as list_e:
                logger.warning(f"GeminiProvider connected, but failed to list models during init: {list_e}", exc_info=True)

            self._is_initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}", exc_info=True)
            self._is_initialized = False
            return False

    async def list_models(self) -> List[Dict[str, Any]]:
        """
        Retrieves a list of available Gemini models from the API that support 'generateContent'.
        If the API call fails or returns no models, it falls back to a default list.
        Uses the `config` parameter in the `list` call as per new documentation.
        """
        if not self._client:
            raise ProviderError("Gemini client not initialized in provider.")

        api_models = []
        models_seen_count = 0
        try:
            list_models_config = {'query_base': True}
            logger.debug(f"Listing models with config: {list_models_config}")

            models_response_pager = await self._client.aio.models.list(config=list_models_config)

            async for model_obj in models_response_pager:
                models_seen_count += 1
                model_name = getattr(model_obj, 'name', 'Unknown Name')
                supported_methods = getattr(model_obj, 'supported_generation_methods', [])
                logger.debug(f"API returned model: Name='{model_name}', SupportedMethods={supported_methods}")

                if 'generateContent' in supported_methods:
                    model_info = {
                        'name': model_obj.name,
                        'display_name': model_obj.display_name or model_obj.name,
                        'description': getattr(model_obj, 'description', ''),
                        'input_token_limit': getattr(model_obj, 'input_token_limit', None),
                        'output_token_limit': getattr(model_obj, 'output_token_limit', None),
                        'supported_methods': list(supported_methods)
                    }
                    api_models.append(model_info)
                    logger.debug(f"Added model to list: {model_obj.name}")
                else:
                    logger.debug(f"Skipped model (does not support 'generateContent'): {model_name}")

            logger.info(f"Total models processed from API: {models_seen_count}. Models matching criteria: {len(api_models)}.")

            if not api_models:
                logger.warning("No models returned from Gemini API with current config that support 'generateContent', using default fallback list.")
                return self._get_fallback_models()

            return api_models
        except Exception as e:
            logger.error(f"Failed to list Gemini models from API: {e}. Using fallback.", exc_info=True)
            return self._get_fallback_models()

    def _get_fallback_models(self) -> List[Dict[str, Any]]:
        """Returns a default list of Gemini model information for fallback purposes."""
        return [
            {
                'name': f"models/{model_name}" if not model_name.startswith("models/") else model_name,
                'display_name': model_name.replace('-', ' ').title(),
                'description': 'Default fallback model',
                'input_token_limit': None, 'output_token_limit': None,
                'supported_methods': ['generateContent']
            } for model_name in self.DEFAULT_FALLBACK_MODELS
        ]

    def _normalize_model_name(self, model_name: Optional[str] = None) -> str:
        """
        Ensures the model name is in a format suitable for the API.
        """
        name_to_use = model_name or self.config.model

        if name_to_use.startswith("tunedModels/"):
            return name_to_use
        if name_to_use.startswith("publishers/"):
            return name_to_use
        if not name_to_use.startswith("models/"):
            name_to_use = f"models/{name_to_use}"
        return name_to_use

    async def generate_response(
            self,
            messages: List[Dict[str, str]],
            params: Optional[Dict[str, Any]] = None,
            stream: bool = False
    ) -> Union[Tuple[str, Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
        """
        Generates a response from the Gemini model, either non-streamed or streamed.
        """
        if not self._is_initialized or not self._client:
            raise ProviderError("GeminiProvider not initialized.")

        normalized_messages = self._convert_messages_to_gemini_format(messages)
        generation_params_dict = self._build_generation_config(params)
        generation_config_obj = types.GenerationConfig(**generation_params_dict)

        model_name_to_use = self._normalize_model_name(self.config.model)

        if stream:
            return self._stream_gemini_response(model_name_to_use, normalized_messages, generation_config_obj)
        else:
            return await self._generate_gemini_response_non_stream(model_name_to_use, normalized_messages, generation_config_obj)

    async def _generate_gemini_response_non_stream(
            self, model_name: str, gemini_contents: List[types.Content], generation_config_obj: types.GenerationConfig
    ) -> Tuple[str, Dict[str, Any]]:
        """Handles non-streaming response generation from the Gemini API."""
        try:
            api_response = await self._client.aio.models.generate_content(
                model=model_name,
                contents=gemini_contents,
                config=generation_config_obj,
            )
            response_text = api_response.text or ""
            token_usage = self.extract_token_usage(api_response)
            return response_text, {'token_usage': token_usage}
        except Exception as e:
            logger.error(f"Error in Gemini non-streaming generation: {e}", exc_info=True)
            raise ProviderError(f"Gemini non-streaming generation error: {e}")

    async def _stream_gemini_response(
            self, model_name: str, gemini_contents: List[types.Content], generation_config_obj: types.GenerationConfig
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Handles streaming response generation from the Gemini API."""
        try:
            stream_gen = self._client.aio.models.generate_content_stream(
                model=model_name,
                contents=gemini_contents,
                config=generation_config_obj,
            )
            full_response_text = ""
            final_token_usage = {}
            async for chunk in stream_gen:
                chunk_text = chunk.text or ""
                full_response_text += chunk_text
                final_token_usage = self.extract_token_usage(chunk)
                yield {"chunk": chunk_text}
            yield {"done": True, "full_response": full_response_text, "token_usage": final_token_usage}
        except Exception as e:
            logger.error(f"Error in Gemini streaming generation: {e}", exc_info=True)
            yield {"error": str(e)}

    def _convert_messages_to_gemini_format(self, messages: List[Dict[str, str]]) -> List[types.Content]:
        """Converts a list of generic message dictionaries to Gemini's 'types.Content' format."""
        gemini_messages = []
        for msg in messages:
            role = msg.get('role', 'user').lower()
            content = msg.get('content', '')
            api_role = 'user' if role == 'user' else 'model'
            if role == 'model' and not content.strip():
                continue
            gemini_messages.append(types.Content(role=api_role, parts=[types.Part.from_text(text=content)]))
        return gemini_messages

    def _build_generation_config(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Merges provided parameters with defaults to create a valid GenerationConfig dictionary."""
        merged_params = self.get_default_params()
        if params:
            merged_params.update(params)

        valid_keys = ['temperature', 'top_p', 'top_k', 'candidate_count', 'max_output_tokens', 'stop_sequences']

        return {k: v for k, v in merged_params.items() if k in valid_keys and v is not None}

    def validate_model(self, model_name: str) -> bool:
        """Validates if the model name is likely a Gemini model (basic check)."""
        return "gemini" in model_name.lower() or \
            model_name.startswith("models/") or \
            model_name.startswith("tunedModels/") or \
            model_name.startswith("publishers/")

    def get_default_params(self) -> Dict[str, Any]:
        """Returns the default generation parameters for Gemini models."""
        return {
            "temperature": 0.7,
            "max_output_tokens": 800,
            "top_p": 0.95,
            "top_k": 40,
            "candidate_count": 1,
        }

    def extract_token_usage(self, response_or_chunk: Any) -> Dict[str, Any]:
        """Extracts token usage information from a Gemini API response or chunk."""
        usage = {}
        if hasattr(response_or_chunk, 'usage_metadata'):
            meta = response_or_chunk.usage_metadata
            if hasattr(meta, 'prompt_token_count'):
                usage['prompt_tokens'] = meta.prompt_token_count
            if hasattr(meta, 'candidates_token_count'):
                usage['completion_tokens'] = meta.candidates_token_count
            elif hasattr(meta, 'total_token_count') and 'prompt_tokens' in usage:
                usage['completion_tokens'] = meta.total_token_count - usage['prompt_tokens']
            if hasattr(meta, 'total_token_count'):
                usage['total_tokens'] = meta.total_token_count
        return usage