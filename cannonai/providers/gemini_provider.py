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
    from google.genai import types  # For GenerationConfig, Content, Part, GenerateContentConfig
except ImportError:
    logging.error("Failed to import google-genai. Please install with: pip install google-genai", exc_info=True)
    raise

# Initialize logger for this module
logger = logging.getLogger(__name__)


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI provider implementation."""

    DEFAULT_FALLBACK_MODELS = [
        "gemini-2.0-flash", "gemini-2.0-pro",  # Corrected model names based on common usage, API might list them differently
        "gemini-2.5-flash-preview-05-20", "gemini-2.5-pro-preview-05-06"  # Example newer models
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        # It's good practice to ensure the model name passed in config is prefixed if necessary,
        # or handle it consistently where the model name is used.
        # For now, _normalize_model_name will handle it.
        if not self.config.model.startswith(("models/", "tunedModels/", "publishers/")):
            logger.info(f"Model name '{self.config.model}' will be prefixed with 'models/' if not a special path.")

    async def initialize(self) -> bool:
        """
        Initializes the Gemini client using the API key from the config.
        It attempts to list models to verify the connection but will not fail initialization
        if listing models fails, only log a warning.
        """
        try:
            # Ensure self.config.api_key is correctly accessed
            if not self.config.api_key:
                logger.error("API key not found in provider configuration.")
                self._is_initialized = False
                return False

            self._client = genai.Client(api_key=self.config.api_key)
            try:
                # Attempt to list models to verify the connection and API key validity.
                await self.list_models()  # This now uses the async client
                logger.info("GeminiProvider connected and successfully listed models during init.")
            except Exception as list_e:
                # Log the error but don't prevent initialization if listing fails,
                # as the primary function might still work with a known model.
                logger.warning(f"GeminiProvider connected, but failed to list models during init: {list_e}", exc_info=True)
                # Consider if this should be a critical failure. For now, allowing init to proceed.

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
        """
        if not self._client:  # Check if client object exists
            logger.error("Gemini client not available in provider for listing models.")
            raise ProviderError("Gemini client not initialized in provider.")
        if not hasattr(self._client, 'aio') or not hasattr(self._client.aio, 'models'):
            logger.error("Gemini client's async interface (aio.models) not available.")
            # This might happen if the client initialization failed or the library version is unexpected.
            # Fallback or raise an error.
            return self._get_fallback_models()

        api_models = []
        models_seen_count = 0
        try:
            # The genai library's list method for async models might not take a 'config' argument directly.
            # It typically lists all models, and we filter them.
            # If 'query_base' was intended for a specific API feature, ensure it's correctly applied.
            # For now, assuming a direct list call.
            # list_models_config = {'query_base': True} # This config might not be applicable here.
            # logger.debug(f"Listing models with config: {list_models_config}")

            # Use the asynchronous client's model listing
            models_response_pager = self._client.aio.models.list()  # Removed config, adjust if API supports it

            async for model_obj in models_response_pager:
                models_seen_count += 1
                model_name = getattr(model_obj, 'name', 'Unknown Name')
                supported_methods = getattr(model_obj, 'supported_generation_methods', [])
                # logger.debug(f"API returned model: Name='{model_name}', SupportedMethods={supported_methods}")

                # Heuristic check for generative models by name, in case supported_methods is empty but it's a known type
                is_known_generative_by_name = any(keyword in model_name.lower() for keyword in ["flash", "pro", "ultra"])

                if 'generateContent' in supported_methods or (is_known_generative_by_name and not supported_methods):
                    if is_known_generative_by_name and not supported_methods:
                        logger.warning(f"Model '{model_name}' has empty SupportedMethods, but assuming 'generateContent' based on name.")

                    model_info = {
                        'name': model_obj.name,  # Should be the full path like 'models/gemini-x.y-flash'
                        'display_name': model_obj.display_name or model_obj.name.split('/')[-1],  # Use short name if display_name is missing
                        'description': getattr(model_obj, 'description', ''),
                        'input_token_limit': getattr(model_obj, 'input_token_limit', None),
                        'output_token_limit': getattr(model_obj, 'output_token_limit', None),
                        'supported_methods': list(supported_methods)  # Convert to list if it's an iterable
                    }
                    api_models.append(model_info)

            logger.info(f"Total models processed from API: {models_seen_count}. Models matching criteria: {len(api_models)}.")

            if not api_models and models_seen_count > 0:
                logger.warning("Models were seen from API, but none matched 'generateContent' criteria. Check model permissions or API version.")
                return self._get_fallback_models()
            elif not api_models:  # No models seen at all
                logger.warning("No models returned from Gemini API. Using default fallback list.")
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
                'description': 'Default fallback model (check API for latest)',
                'input_token_limit': None,  # Indicate unknown or variable
                'output_token_limit': None,  # Indicate unknown or variable
                'supported_methods': ['generateContent']
            } for model_name in self.DEFAULT_FALLBACK_MODELS
        ]

    def _normalize_model_name(self, model_name: Optional[str] = None) -> str:
        """
        Ensures the model name is in a format suitable for the API (e.g., 'models/gemini-2.0-flash').
        """
        name_to_use = model_name or self.config.model  # Use instance's configured model if arg is None

        # Handle special paths like tunedModels or publishers
        if name_to_use.startswith("tunedModels/") or name_to_use.startswith("publishers/"):
            return name_to_use
        # Ensure standard models are prefixed with "models/"
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
        if not normalized_messages:
            logger.warning("No valid messages to send to Gemini after normalization.")
            if stream:
                async def empty_stream():
                    yield {"done": True, "full_response": "", "token_usage": {}}
                    # Explicitly return to satisfy AsyncGenerator type hint
                    return

                return empty_stream()
            else:
                return "", {'token_usage': {}}

        # This creates a dictionary of parameters like temperature, top_p, etc.
        generation_params_dict = self._build_generation_config_dict(params)

        # Construct the GenerateContentConfig by unpacking the generation_params_dict
        # This passes temperature, top_p, etc., as direct keyword arguments.
        try:
            # Ensure that only valid parameters for GenerateContentConfig are passed
            request_config_obj = types.GenerateContentConfig(**generation_params_dict)
        except TypeError as te:
            logger.error(f"TypeError creating GenerateContentConfig with params: {generation_params_dict}. Error: {te}", exc_info=True)
            # Log which specific parameter caused the issue if possible (Python 3.11+ includes param name in TypeError)
            raise ProviderError(f"Failed to create GenerateContentConfig due to invalid parameter: {te}")
        except Exception as e:
            logger.error(f"Error creating GenerateContentConfig with params: {generation_params_dict}. Error: {e}", exc_info=True)
            raise ProviderError(f"Failed to create GenerateContentConfig: {e}")

        model_name_to_use = self._normalize_model_name(self.config.model)
        logger.debug(f"Gemini Request: Model='{model_name_to_use}', Stream={stream}, Params={generation_params_dict}, Messages Count={len(normalized_messages)}")

        if stream:
            return self._stream_gemini_response(model_name_to_use, normalized_messages, request_config_obj)
        else:
            return await self._generate_gemini_response_non_stream(model_name_to_use, normalized_messages, request_config_obj)

    async def _generate_gemini_response_non_stream(
            self, model_name: str, gemini_contents: List[types.Content], request_config_obj: types.GenerateContentConfig
    ) -> Tuple[str, Dict[str, Any]]:
        """Handles non-streaming response generation from the Gemini API."""
        try:
            api_response = await self._client.aio.models.generate_content(  # Use aio.models
                model=model_name,
                contents=gemini_contents,
                config=request_config_obj,  # Pass the object here
            )
            response_text = api_response.text or ""
            token_usage = self.extract_token_usage(api_response)
            logger.debug(f"Gemini Non-Stream Response: Text='{response_text[:50]}...', TokenUsage={token_usage}")
            return response_text, {'token_usage': token_usage}
        except Exception as e:
            logger.error(f"Error in Gemini non-streaming generation: {e}", exc_info=True)
            # Attempt to get more details from the exception if it's a google.api_core.exceptions type
            if hasattr(e, 'message'):
                error_message = e.message
            else:
                error_message = str(e)
            raise ProviderError(f"Gemini non-streaming generation error: {error_message}")

    async def _stream_gemini_response(
            self, model_name: str, gemini_contents: List[types.Content], request_config_obj: types.GenerateContentConfig
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Handles streaming response generation from the Gemini API."""
        try:
            # *** FIX: await the call to generate_content_stream ***
            stream_gen_iterator = await self._client.aio.models.generate_content_stream(  # Use aio.models
                model=model_name,
                contents=gemini_contents,
                config=request_config_obj,  # Pass the object here
            )
            full_response_text = ""
            final_token_usage = {}
            async for chunk in stream_gen_iterator:  # Iterate over the awaited iterator
                chunk_text = chunk.text if hasattr(chunk, 'text') else ""  # Handle potential empty chunks or different structure
                full_response_text += chunk_text
                # Token usage might only be available in the last chunk or aggregated.
                # For Gemini, it's often in usage_metadata of the final chunk or the overall response object.
                # We'll try to extract it from each chunk and update if present.
                current_chunk_token_usage = self.extract_token_usage(chunk)
                if current_chunk_token_usage:  # Update if new token info is found
                    final_token_usage.update(current_chunk_token_usage)

                yield {"chunk": chunk_text}
            logger.debug(f"Gemini Stream Response Complete: FullText='{full_response_text[:50]}...', TokenUsage={final_token_usage}")
            yield {"done": True, "full_response": full_response_text, "token_usage": final_token_usage}
        except Exception as e:
            logger.error(f"Error in Gemini streaming generation: {e}", exc_info=True)
            if hasattr(e, 'message'):
                error_message = e.message
            else:
                error_message = str(e)
            yield {"error": f"Gemini streaming error: {error_message}"}

    def _convert_messages_to_gemini_format(self, messages: List[Dict[str, str]]) -> List[types.Content]:
        """
        Converts a list of generic message dictionaries to Gemini's 'types.Content' format.
        Ensures alternating user/model roles and handles system messages if necessary.
        """
        gemini_messages: List[types.Content] = []
        last_role = None

        for msg in messages:
            role = msg.get('role', 'user').lower()
            content_text = msg.get('content', '')

            # Map to 'user' or 'model'
            current_api_role = 'user' if role == 'user' else 'model'

            # Ensure alternating roles if the API requires it.
            # Gemini generally expects user/model alternation.
            if current_api_role == last_role:
                # This can happen if two user messages are consecutive.
                # Depending on strictness, either merge, skip, or error.
                # For now, let's log a warning and potentially skip or try to adapt.
                # If the last message was 'model' and current is 'model', this is an issue.
                # If last was 'user' and current is 'user', also an issue.
                logger.warning(f"Consecutive messages with the same role ('{current_api_role}') detected. "
                               f"Gemini API expects alternating roles. Attempting to proceed, but this may cause issues.")
                # A simple strategy: if it's a user message following a user message,
                # and the previous content was just added, maybe append.
                # However, the Content object is immutable. Better to ensure input list is correct.
                # For now, we'll just add it and let the API handle it or error.
                # A more robust solution would be to preprocess `messages` in AsyncClient.

            # Skip empty model messages as they can cause issues. User messages can be empty.
            if current_api_role == 'model' and not content_text.strip():
                logger.debug("Skipping empty model message.")
                continue

            # Handle system messages: Gemini doesn't have a 'system' role in the same way as OpenAI.
            # System instructions are often prepended to the first user message or handled via specific API features.
            # For a general chat, a common approach is to convert a 'system' message into a 'user' message
            # followed by an 'assistant' message that acknowledges or incorporates the instruction.
            # Or, if it's the first message, prepend its content to the first actual user message.
            # The current `normalize_messages` in BaseAIProvider does not do this, so this provider
            # will receive 'system' as 'user' or 'model' based on that.
            # If a 'system' role were to arrive here, it would be mapped to 'user' by default.
            # For now, this basic conversion is fine.

            gemini_messages.append(types.Content(role=current_api_role, parts=[types.Part.from_text(text=content_text)]))
            last_role = current_api_role

        if not gemini_messages:
            logger.warning("Message list for Gemini is empty after conversion.")
        elif gemini_messages[0].role != 'user':
            # Gemini API typically expects the first message in a conversation to be from the 'user'.
            # If the history starts with a model/assistant message, this can lead to errors.
            logger.warning(f"First message to Gemini is not from 'user' role (it's '{gemini_messages[0].role}'). This might cause API errors.")
            # Consider prepending a dummy user message if this becomes a frequent issue,
            # or enforce this constraint in the calling client logic.

        return gemini_messages

    def _build_generation_config_dict(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Builds a dictionary of parameters suitable for direct unpacking into types.GenerateContentConfig
        (e.g., temperature, top_p). It merges provided params with defaults.
        """
        # Start with provider's defaults
        merged_params = self.get_default_params()
        if params:
            merged_params.update(params)

        # These are the keys that google.generativeai.types.GenerateContentConfig accepts as keyword arguments.
        # Refer to the official documentation for the exact list for the SDK version being used.
        valid_config_keys = [
            'candidate_count',
            'stop_sequences',  # List[str]
            'max_output_tokens',  # int
            'temperature',  # float
            'top_p',  # float
            'top_k',  # int
            # 'presence_penalty', # Not standard in Gemini GenConfig, more OpenAI
            # 'frequency_penalty', # Not standard in Gemini GenConfig, more OpenAI
            # 'response_mime_type' # For specific response types like JSON
        ]

        # Filter merged_params to include only valid keys and non-None values
        generation_config_dict = {
            k: v for k, v in merged_params.items() if k in valid_config_keys and v is not None
        }

        # Ensure types are correct, e.g., stop_sequences should be a list of strings.
        if 'stop_sequences' in generation_config_dict and not isinstance(generation_config_dict['stop_sequences'], list):
            logger.warning(f"stop_sequences parameter is not a list: {generation_config_dict['stop_sequences']}. Converting to list.")
            # Attempt to convert or wrap if it's a single string
            if isinstance(generation_config_dict['stop_sequences'], str):
                generation_config_dict['stop_sequences'] = [generation_config_dict['stop_sequences']]
            else:
                # If it's some other type that's not easily convertible, remove it to prevent errors
                logger.error(f"Cannot convert stop_sequences of type {type(generation_config_dict['stop_sequences'])} to list. Removing.")
                del generation_config_dict['stop_sequences']

        return generation_config_dict

    def validate_model(self, model_name: str) -> bool:
        """Validates if the model name is likely a Gemini model (basic check)."""
        # This check is quite basic. A more robust validation might involve
        # trying to fetch model details from the API if the model list isn't already cached.
        # For now, relying on naming conventions.
        is_gemini_keyword = "gemini" in model_name.lower()
        is_prefixed = model_name.startswith("models/") or \
                      model_name.startswith("tunedModels/") or \
                      model_name.startswith("publishers/")

        # If it has a Gemini keyword but isn't prefixed, it's likely a short name that needs normalization.
        # If it's prefixed, it's assumed to be a valid path format.
        # If it has neither, it's less likely to be a valid Gemini model identifier for this provider.
        return is_prefixed or is_gemini_keyword

    def get_default_params(self) -> Dict[str, Any]:
        """
        Returns the default parameters that can be directly unpacked into types.GenerateContentConfig.
        """
        return {
            "temperature": 0.7,
            "max_output_tokens": 800,  # Default value, can be overridden
            "top_p": 0.95,
            "top_k": 40,
            "candidate_count": 1,
            "stop_sequences": None,  # Example: ["\nObservation:"]
        }

    def extract_token_usage(self, response_or_chunk: Any) -> Dict[str, Any]:
        """Extracts token usage information from a Gemini API response or chunk."""
        usage = {}
        # The usage_metadata might be on the main response or on individual candidates/chunks

        # Check directly on the response/chunk object
        if hasattr(response_or_chunk, 'usage_metadata'):
            meta = response_or_chunk.usage_metadata
            if hasattr(meta, 'prompt_token_count'):
                usage['prompt_tokens'] = meta.prompt_token_count
            if hasattr(meta, 'candidates_token_count'):  # This is usually the sum for all candidates
                usage['completion_tokens'] = meta.candidates_token_count
            elif hasattr(meta, 'total_token_count') and 'prompt_tokens' in usage:
                # If candidates_token_count is missing, try to infer from total
                usage['completion_tokens'] = meta.total_token_count - usage['prompt_tokens']

            if hasattr(meta, 'total_token_count'):
                usage['total_tokens'] = meta.total_token_count
            return usage  # Return if found directly on response/chunk

        # If not directly on response, check if it's a GenerateContentResponse with candidates
        if hasattr(response_or_chunk, 'candidates') and response_or_chunk.candidates:
            # Token usage in Gemini is often associated with the overall response rather than per candidate in the same way
            # as some other APIs. The `usage_metadata` on the top-level response is usually the place.
            # However, if it were per candidate, you might iterate:
            # for candidate in response_or_chunk.candidates:
            #     if hasattr(candidate, 'token_count'): # Fictional attribute, check actual SDK
            #         usage['completion_tokens'] = candidate.token_count # Or add to a sum
            #         break # Assuming first candidate's token count for simplicity if it were structured this way
            pass  # Placeholder for more complex extraction if needed from candidates

        return usage  # Return empty or partially filled if not found
