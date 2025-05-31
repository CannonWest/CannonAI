#!/usr/bin/env python3
"""
Google Gemini AI Provider Implementation.

This module implements the BaseAIProvider interface for Google's Gemini AI models.
It handles all Gemini-specific API interactions and conversions.
"""

import os
import asyncio
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, Tuple

from .base_provider import BaseAIProvider, ProviderConfig, ProviderError

try:
    from google import genai
    from google.genai import types
    # print("DEBUG: Successfully imported google.genai in gemini_provider")
except ImportError as e:
    print(f"ERROR: Failed to import google-genai in gemini_provider: {e}")
    print("Please install with: pip install google-genai")
    raise


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI provider implementation."""

    DEFAULT_FALLBACK_MODELS = [
        "gemini-2.0-flash", "gemini-2.0-pro", 
        "gemini-2.5-flash-preview-05-20", "gemini-2.5-pro-preview-05-06"
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        # print(f"DEBUG: GeminiProvider init with model: {config.model}")
        if not config.model.startswith("gemini") and not config.model.startswith("models/gemini"):
            print(f"WARNING: Model name '{config.model}' might not be a Gemini model.")

    async def initialize(self) -> bool:
        try:
            # print(f"DEBUG: GeminiProvider initializing client with API key: {self.config.api_key[:8]}...")
            self._client = genai.Client(api_key=self.config.api_key)
            # Test connection by listing models, but don't fail init if listing fails, just warn.
            try:
                await self.list_models() 
                # print(f"DEBUG: GeminiProvider successfully connected. Found models.")
            except Exception as list_e:
                print(f"WARNING: GeminiProvider connected, but failed to list models during init: {list_e}")

            self._is_initialized = True
            return True
        except Exception as e:
            print(f"ERROR: Failed to initialize Gemini client: {e}")
            self._is_initialized = False
            return False

    async def list_models(self) -> List[Dict[str, Any]]:
        # print("DEBUG: GeminiProvider fetching available models...")
        if not self._client:
            raise ProviderError("Gemini client not initialized in provider.")

        api_models = []
        try:
            models_response = await self._client.models.list()
            async for model_obj in models_response:
                if hasattr(model_obj, 'supported_generation_methods') and \
                   'generateContent' in model_obj.supported_generation_methods:
                    model_info = {
                        'name': model_obj.name,
                        'display_name': model_obj.display_name or model_obj.name,
                        'description': getattr(model_obj, 'description', ''),
                        'input_token_limit': getattr(model_obj, 'input_token_limit', None),
                        'output_token_limit': getattr(model_obj, 'output_token_limit', None),
                        'supported_methods': list(model_obj.supported_generation_methods)
                    }
                    api_models.append(model_info)
            if not api_models:
                 print("WARNING: No models returned from Gemini API, using default fallback list.")
                 return self._get_fallback_models()
            return api_models
        except Exception as e:
            print(f"ERROR: Failed to list Gemini models from API: {e}. Using fallback.")
            return self._get_fallback_models()

    def _get_fallback_models(self) -> List[Dict[str, Any]]:
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
        name_to_use = model_name or self.config.model
        if not name_to_use.startswith("models/"):
            name_to_use = f"models/{name_to_use}"
        return name_to_use

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        params: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ) -> Union[Tuple[str, Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
        if not self._is_initialized or not self._client:
            raise ProviderError("GeminiProvider not initialized.")

        normalized_messages = self._convert_messages_to_gemini_format(messages)
        gen_config_dict = self._build_generation_config(params)
        
        # print(f"DEBUG: GeminiProvider generating response. Model: {self.config.model}, Stream: {stream}, Params: {gen_config_dict}")

        model_name_to_use = self._normalize_model_name()

        if stream:
            return self._stream_gemini_response(model_name_to_use, normalized_messages, gen_config_dict)
        else:
            return await self._generate_gemini_response_non_stream(model_name_to_use, normalized_messages, gen_config_dict)

    async def _generate_gemini_response_non_stream(
        self, model_name: str, gemini_contents: List[types.Content], gen_config_dict: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        try:
            api_response = await self._client.models.generate_content(
                model=model_name,
                contents=gemini_contents,
                generation_config=types.GenerationConfig(**gen_config_dict)
            )
            response_text = api_response.text or ""
            token_usage = self.extract_token_usage(api_response)
            # print(f"DEBUG: Gemini non-stream response text length: {len(response_text)}")
            return response_text, {'token_usage': token_usage}
        except Exception as e:
            print(f"ERROR: Gemini non-streaming generation failed: {e}")
            raise ProviderError(f"Gemini non-streaming generation error: {e}")

    async def _stream_gemini_response(
        self, model_name: str, gemini_contents: List[types.Content], gen_config_dict: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            stream_gen = self._client.models.generate_content_stream(
                model=model_name,
                contents=gemini_contents,
                generation_config=types.GenerationConfig(**gen_config_dict)
            )
            full_response_text = ""
            final_token_usage = {}
            async for chunk in stream_gen:
                chunk_text = chunk.text or ""
                full_response_text += chunk_text
                final_token_usage = self.extract_token_usage(chunk) # Takes the latest
                yield {"chunk": chunk_text}
            
            yield {"done": True, "full_response": full_response_text, "token_usage": final_token_usage}
            # print(f"DEBUG: Gemini streaming finished. Full length: {len(full_response_text)}")
        except Exception as e:
            print(f"ERROR: Gemini streaming generation failed: {e}")
            yield {"error": str(e)}


    def _convert_messages_to_gemini_format(self, messages: List[Dict[str, str]]) -> List[types.Content]:
        gemini_messages = []
        for msg in messages:
            role = msg.get('role', 'user').lower()
            content = msg.get('content', '')
            api_role = 'user' if role == 'user' else 'model'
            
            # Gemini API requires alternating user/model roles and no empty parts.
            # If the last message has the same role, this might be an issue,
            # but the client should enforce alternating turns.
            # Also, system messages need special handling if they are to be supported.
            # For now, assume client sends valid sequence.
            if not content.strip() and role == 'model': # Skip empty model messages if any
                continue

            gemini_messages.append(types.Content(role=api_role, parts=[types.Part.from_text(text=content)]))
        return gemini_messages

    def _build_generation_config(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        merged_params = self.get_default_params()
        if params:
            merged_params.update(params)
        
        # Map to Gemini's GenerationConfig field names if necessary
        # current names (temperature, max_output_tokens, top_p, top_k) are compatible
        return {
            'temperature': merged_params.get('temperature'),
            'max_output_tokens': merged_params.get('max_output_tokens'),
            'top_p': merged_params.get('top_p'),
            'top_k': merged_params.get('top_k'),
            # 'stop_sequences': merged_params.get('stop_sequences') # if you add this
        }

    def validate_model(self, model_name: str) -> bool:
        # print(f"DEBUG: GeminiProvider validating model: {model_name}")
        # Simple check, actual validation happens when listing or using.
        return "gemini" in model_name.lower()

    def get_default_params(self) -> Dict[str, Any]:
        return {
            "temperature": 0.7,
            "max_output_tokens": 800,
            "top_p": 0.95,
            "top_k": 40
        }

    def extract_token_usage(self, response_or_chunk: Any) -> Dict[str, Any]:
        usage = {}
        if hasattr(response_or_chunk, 'usage_metadata'):
            meta = response_or_chunk.usage_metadata
            if hasattr(meta, 'prompt_token_count'):
                usage['prompt_tokens'] = meta.prompt_token_count
            if hasattr(meta, 'candidates_token_count'): # For non-streaming, this is completion
                usage['completion_tokens'] = meta.candidates_token_count
            elif hasattr(meta, 'total_token_count') and 'prompt_tokens' in usage : # For streaming, may only get total
                 usage['completion_tokens'] = meta.total_token_count - usage['prompt_tokens']

            if hasattr(meta, 'total_token_count'):
                usage['total_tokens'] = meta.total_token_count
        return usage