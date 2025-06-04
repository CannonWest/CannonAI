#!/usr/bin/env python3
"""
Google Gemini AI Provider Implementation (New SDK Pattern).

This module implements the BaseAIProvider interface for Google's Gemini AI models,
using the new `google-genai` SDK pattern with `genai.Client()`.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Union, AsyncGenerator, Tuple

from .base_provider import BaseAIProvider, ProviderConfig, ProviderError

try:
    from google import genai  # For genai.Client()
    from google.genai import types as genai_types  # For Content, Part, GenerateContentConfig etc.
    # The new SDK's list_models returns an AsyncPager that yields Model objects directly.
    # We might not need to import AsyncIterator from google.api_core explicitly if
    # the type hint for the return of client.aio.models.list() is sufficient.
    # from google.api_core.page_iterator_async import AsyncIterator # Keep for clarity if needed
except ImportError:
    logging.error(
        "Failed to import 'google.genai'. "
        "Please ensure the new 'google-genai' SDK is installed correctly. "
        "Try: pip install -U google-genai",
        exc_info=True
    )
    raise

logger = logging.getLogger(__name__)


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI provider implementation using the new SDK pattern."""

    DEFAULT_FALLBACK_MODELS = [  # Fallback if API listing fails
        "gemini-2.0-flash",  # Ensure these are valid model IDs for client.models.generate_content
        "gemini-1.5-flash-latest",  # Example, adjust to actual valid model IDs
        "gemini-pro"
    ]

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        # _sdk_client will store the genai.Client() instance
        self._sdk_client: Optional[genai.Client] = None
        # _async_sdk_interface will store client.aio
        self._async_sdk_interface: Optional[Any] = None

        # Model name normalization is less critical if client.models takes short names,
        # but good to keep for consistency if full paths are ever needed.
        # The new SDK seems flexible with model names for client.models.generate_content.
        # Example: 'gemini-2.0-flash' or 'models/gemini-2.0-flash'
        if not self.config.model.startswith("models/") and \
                not self.config.model.startswith("tunedModels/") and \
                not self.config.model.startswith("publishers/"):
            logger.info(f"Model name '{self.config.model}' might be a short ID. The SDK typically handles this.")
            # No automatic prefixing here, as the new SDK methods accept short names.

    async def initialize(self) -> bool:
        """
        Initializes the Gemini provider using genai.Client().
        """
        try:
            if not self.config.api_key:
                logger.error("API key not found in provider configuration.")
                self._is_initialized = False
                return False

            # Initialize the client using the new SDK pattern
            self._sdk_client = genai.Client(api_key=self.config.api_key)
            if hasattr(self._sdk_client, 'aio'):
                self._async_sdk_interface = self._sdk_client.aio
                logger.info("Initialized Gemini provider using new SDK: genai.Client() and client.aio.")
            else:
                logger.error("genai.Client successfully instantiated but has no .aio attribute. Async operations may fail.")
                self._is_initialized = False
                return False

            await self.list_models()  # Attempt to list models to verify connection
            logger.info("GeminiProvider initialization attempt complete.")
            self._is_initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Gemini provider with new SDK: {e}", exc_info=True)
            self._is_initialized = False
            return False

    async def list_models(self) -> List[Dict[str, Any]]:
        if not self._is_initialized or not self._async_sdk_interface or not hasattr(self._async_sdk_interface, 'models'):
            logger.error("Gemini provider not properly initialized or async interface not found, cannot list models.")
            return self._get_fallback_models()

        models_iterator: Optional[Any] = None  # Type will be an AsyncPager from the SDK
        try:
            logger.debug("Listing models using self._async_sdk_interface.models.list()")
            # The new SDK's client.aio.models.list() returns an Awaitable[AsyncPager[types.Model]]
            # The AsyncPager itself is the async iterator.
            models_iterator = await self._async_sdk_interface.models.list()
        except Exception as e_list_call:
            logger.error(f"Call to list Gemini models failed: {e_list_call}. Using fallback models.", exc_info=True)
            return self._get_fallback_models()

        if models_iterator is None: return self._get_fallback_models()

        api_models = []
        models_seen_count = 0
        try:
            # Iterate directly over the AsyncPager
            async for model_obj in models_iterator:  # model_obj is genai_types.Model
                models_seen_count += 1
                model_name = getattr(model_obj, 'name', 'Unknown Name')
                # The attribute for supported methods in genai_types.Model is supported_generation_methods
                # The new SDK docs show `supported_actions` for `client.models.list()` results.
                supported_methods = getattr(model_obj, 'supported_generation_methods', [])  # Keep this for now
                supported_actions = getattr(model_obj, 'supported_actions', [])  # As per new SDK docs for client.models.list()

                # Check for content generation capability
                can_generate_content = 'generateContent' in supported_methods or 'generateContent' in supported_actions

                is_known_generative_by_name = any(k in model_name.lower() for k in ["flash", "pro", "ultra", "gemini"])

                if can_generate_content or (is_known_generative_by_name and not (supported_methods or supported_actions)):
                    if is_known_generative_by_name and not (supported_methods or supported_actions):
                        logger.warning(f"Model '{model_name}' assuming 'generateContent' support based on name as supported_methods/actions is empty.")
                    api_models.append({'name': model_obj.name,
                                       'display_name': model_obj.display_name or model_obj.name.split('/')[-1],
                                       'description': getattr(model_obj, 'description', ''),
                                       'input_token_limit': getattr(model_obj, 'input_token_limit', None),
                                       'output_token_limit': getattr(model_obj, 'output_token_limit', None),
                                       'supported_methods': list(supported_methods or supported_actions)})  # Combine or prioritize
            logger.info(f"Models processed from API: {models_seen_count}. Matching criteria: {len(api_models)}.")
            if not api_models:
                logger.warning("No models matching criteria found via API. Using fallback.")
                return self._get_fallback_models()
            return api_models
        except Exception as e_iter:
            logger.error(f"Error processing models from iterator: {e_iter}. Using fallback.", exc_info=True)
            return self._get_fallback_models()

    def _get_fallback_models(self) -> List[Dict[str, Any]]:
        logger.info("Using fallback model list for GeminiProvider.")
        return [{'name': m, 'display_name': m.replace('-', ' ').title(),  # Use short names for fallback
                 'description': 'Fallback model', 'input_token_limit': None, 'output_token_limit': None,
                 'supported_methods': ['generateContent']} for m in self.DEFAULT_FALLBACK_MODELS]

    def _normalize_model_name(self, model_name: Optional[str] = None) -> str:
        # The new SDK's client.models.generate_content seems to handle short names like 'gemini-2.0-flash'
        # or prefixed names like 'models/gemini-2.0-flash'.
        # So, extensive normalization might not be strictly needed if we pass what the user/config provides.
        # However, for consistency or if a specific format is ever required, this can be adjusted.
        name_to_use = model_name or self.config.model
        # if not name_to_use.startswith("models/"): # Example: only prefix if not already prefixed
        #     return f"models/{name_to_use}"
        return name_to_use  # Return as is, assuming SDK handles it.

    async def generate_response(
            self, messages: List[Dict[str, Any]], params: Optional[Dict[str, Any]] = None, stream: bool = False
    ) -> Union[Tuple[str, Dict[str, Any]], AsyncGenerator[Dict[str, Any], None]]:
        if not self._is_initialized or not self._async_sdk_interface or not hasattr(self._async_sdk_interface, 'models'):
            raise ProviderError("GeminiProvider not properly initialized or async interface not available.")

        model_name_str = self._normalize_model_name(self.config.model)  # Get the model name to use
        normalized_contents = self._convert_messages_to_gemini_format(messages)

        if not normalized_contents:
            logger.warning("No valid messages after normalization.")
            if stream:
                async def empty_stream_gen():
                    yield {"done": True, "full_response": "", "token_usage": {}}

                return empty_stream_gen()
            else:
                return "", {'token_usage': {}}

        # Build the config object for the SDK
        # System instruction is now part of GenerateContentConfig as per new SDK docs
        system_instruction_text = messages[0].get("system_instruction_override") if messages and messages[0].get("system_instruction_override") else None

        gen_config_obj = self._build_generation_config_object(params, system_instruction_text)

        logger.debug(f"Gemini Request: Model='{model_name_str}', Stream={stream}, Config={gen_config_obj}, Msgs Count={len(normalized_contents)}")

        # Ensure the methods exist on the SDK interface
        if stream and not hasattr(self._async_sdk_interface.models, 'generate_content_stream'):
            raise ProviderError("SDK async interface does not support 'generate_content_stream'.")
        if not stream and not hasattr(self._async_sdk_interface.models, 'generate_content'):
            raise ProviderError("SDK async interface does not support 'generate_content'.")

        if stream:
            return self._stream_gemini_response(model_name_str, normalized_contents, gen_config_obj)
        else:
            return await self._generate_gemini_response_non_stream(model_name_str, normalized_contents, gen_config_obj)

    async def _generate_gemini_response_non_stream(
            self, model_id: str, contents: List[genai_types.Content], gen_config: genai_types.GenerateContentConfig
    ) -> Tuple[str, Dict[str, Any]]:
        try:
            # Call using client.aio.models.generate_content
            api_response = await self._async_sdk_interface.models.generate_content(  # type: ignore
                model=model_id,  # Pass model ID string
                contents=contents,
                config=gen_config  # Pass the config object
            )
            response_text = api_response.text or ""
            token_usage = self.extract_token_usage(api_response)
            return response_text, {'token_usage': token_usage}
        except Exception as e:
            logger.error(f"Gemini non-streaming error: {e}", exc_info=True)
            raise ProviderError(f"Gemini non-streaming error: {getattr(e, 'message', str(e))}")

    async def _stream_gemini_response(
            self, model_id: str, contents: List[genai_types.Content], gen_config: genai_types.GenerateContentConfig
    ) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            # Call using client.aio.models.generate_content_stream
            stream_iterator = await self._async_sdk_interface.models.generate_content_stream(  # type: ignore
                model=model_id,  # Pass model ID string
                contents=contents,
                config=gen_config  # Pass the config object
            )
            full_response_text = ""
            final_token_usage = {}
            async for chunk in stream_iterator:  # chunk is types.GenerateContentResponse
                chunk_text = chunk.text if hasattr(chunk, 'text') else ""
                full_response_text += chunk_text
                current_chunk_token_usage = self.extract_token_usage(chunk)
                if current_chunk_token_usage: final_token_usage.update(current_chunk_token_usage)
                yield {"chunk": chunk_text}
            yield {"done": True, "full_response": full_response_text, "token_usage": final_token_usage}
        except Exception as e:
            logger.error(f"Gemini streaming error: {e}", exc_info=True)
            yield {"error": f"Gemini streaming error: {getattr(e, 'message', str(e))}"}

    def _convert_messages_to_gemini_format(self, messages: List[Dict[str, Any]]) -> List[genai_types.Content]:
        """
        Converts messages to Gemini's Content format.
        The first message in the list might contain a 'system_instruction_override' key,
        which is handled by _build_generation_config_object now.
        This method focuses only on user/model roles and their content/parts.
        """
        gemini_messages: List[genai_types.Content] = []
        last_role = None
        for i, msg in enumerate(messages):
            role = msg.get('role', 'user').lower()
            # Skip system instruction placeholder if it was part of the 'messages' list
            if role == "system" or (i == 0 and msg.get("system_instruction_override")):
                continue

            content_text = msg.get('content', '')
            attachments = msg.get('attachments')
            api_role = 'user' if role == 'user' else 'model'

            if api_role == last_role: logger.warning(f"Consecutive roles: '{api_role}'")
            if api_role == 'model' and not content_text.strip() and not attachments: continue

            message_parts = []
            if content_text.strip():
                try:
                    message_parts.append(genai_types.Part(text=content_text))
                except Exception as e:
                    logger.error(f"Error creating Part from text: {e}", exc_info=True); continue
            if attachments and isinstance(attachments, list):
                for att in attachments:
                    mime, data, uri = att.get('mime_type'), att.get('data'), att.get('uri')
                    if not mime: logger.warning(f"Attachment missing mime_type: {att}"); continue
                    try:
                        if data:
                            message_parts.append(genai_types.Part.from_data(data=data, mime_type=mime))
                        elif uri:
                            message_parts.append(genai_types.Part.from_uri(uri=uri, mime_type=mime))
                        else:
                            logger.warning(f"Attachment structure unknown: {att}")
                    except Exception as e:
                        logger.error(f"Error creating Part from attachment: {e}", exc_info=True)
            if not message_parts: logger.warning(f"No parts for role '{api_role}'. Skipping."); continue
            gemini_messages.append(genai_types.Content(role=api_role, parts=message_parts))
            last_role = api_role
        if not gemini_messages:
            logger.warning("Empty message list for Gemini after conversion.")
        # The first message role check is important for many models.
        elif gemini_messages and gemini_messages[0].role != 'user':
            logger.warning(f"First message to Gemini is not 'user' (it's '{gemini_messages[0].role}'). This may cause API errors.")
        return gemini_messages

    def _build_generation_config_object(self, params: Optional[Dict[str, Any]] = None, system_instruction_text: Optional[str] = None) -> genai_types.GenerateContentConfig:
        """
        Builds the genai_types.GenerateContentConfig object.
        System instruction is now passed here.
        """
        merged_params = self.get_default_params()  # Start with provider defaults
        if params: merged_params.update(params)  # Layer conversation/session params

        # Keys for genai_types.GenerationConfig constructor
        # `system_instruction` is handled separately below.
        # `tools` and `tool_config` are also handled separately.
        valid_direct_keys = ['candidate_count', 'stop_sequences', 'max_output_tokens',
                             'temperature', 'top_p', 'top_k', 'response_mime_type', 'seed']  # Added seed

        config_kwargs = {k: v for k, v in merged_params.items() if k in valid_direct_keys and v is not None}

        if 'stop_sequences' in config_kwargs and not isinstance(config_kwargs['stop_sequences'], list):
            if isinstance(config_kwargs['stop_sequences'], str):
                config_kwargs['stop_sequences'] = [config_kwargs['stop_sequences']]
            else:
                logger.error(f"Invalid stop_sequences type: {type(config_kwargs['stop_sequences'])}. Removing.")
                del config_kwargs['stop_sequences']

        # Handle system_instruction
        if system_instruction_text and system_instruction_text.strip():
            try:
                # System instruction can be a string or Content object.
                # For simplicity, if it's text, we wrap it in a Part and Content.
                config_kwargs['system_instruction'] = genai_types.Content(
                    parts=[genai_types.Part(text=system_instruction_text)],
                    role="system"  # Or "user" if "system" role isn't directly supported by the model for system_instruction field.
                    # The SDK docs for GenerateContentConfig show system_instruction as ContentUnion.
                    # A simple string might also work directly: `system_instruction=system_instruction_text`
                )
                logger.debug(f"Applying system instruction via GenerateContentConfig: '{system_instruction_text[:50]}...'")
            except Exception as e_si:
                logger.warning(f"Could not create Content object for system_instruction: {e_si}")

        # Handle tools and tool_config (AFC)
        # If tools are explicitly provided in params, use them.
        if 'tools' in merged_params and merged_params['tools'] is not None:
            config_kwargs['tools'] = merged_params['tools']
            # If tools are present, AFC is typically enabled by default unless tool_config specifies otherwise.
            if 'tool_config' in merged_params and merged_params['tool_config'] is not None:
                config_kwargs['tool_config'] = merged_params['tool_config']
            # else: AFC is on by default with tools.
            logger.debug(f"Tools provided, AFC likely enabled by default or by tool_config: {config_kwargs.get('tools')}")
        else:
            # No tools provided. Explicitly disable AFC to avoid the AttributeError.
            # The new SDK way: automatic_function_calling={'disable': True}
            # This seems to be an attribute of the config object itself, not a dict key.
            # Let's try setting it in tool_config as per previous fix, which is more structured.
            # The docs show: config=types.GenerateContentConfig(tools=[...], automatic_function_calling={'disable': True})
            # This implies 'automatic_function_calling' is a direct parameter of GenerateContentConfig.
            # Let's add it to valid_keys if it is.
            # For now, stick to the ToolConfig method as it's more robust if `automatic_function_calling` isn't a direct kwarg.

            # Re-evaluating based on new SDK docs:
            # `automatic_function_calling={'disable': True}` is passed within the `config` dict to `client.models.generate_content`
            # which means it should be a field in `types.GenerateContentConfig`.
            # If it's not a direct field, then the `ToolConfig(mode=NONE)` is the alternative.
            # The error `AttributeError: 'GenerationConfig' object has no attribute 'automatic_function_calling'`
            # suggests it's *not* a direct attribute of the Pydantic `GenerationConfig` model.
            # So, the `ToolConfig` approach is safer.

            if 'tool_config' not in config_kwargs:  # Only add if not already set
                try:
                    config_kwargs['tool_config'] = genai_types.ToolConfig(
                        function_calling_config=genai_types.FunctionCallingConfig(
                            mode=genai_types.FunctionCallingConfig.Mode.NONE
                        )
                    )
                    logger.debug("No tools specified; explicitly added ToolConfig with Mode.NONE to disable AFC.")
                except Exception as e_tc:
                    logger.warning(f"Could not create default ToolConfig(mode=NONE): {e_tc}")
        try:
            return genai_types.GenerateContentConfig(**config_kwargs)
        except Exception as e_final_cfg:
            logger.error(f"Error creating final GenerateContentConfig with kwargs {config_kwargs}: {e_final_cfg}", exc_info=True)
            raise ProviderError(f"Final GenerateContentConfig creation failed: {e_final_cfg}")

    def validate_model(self, model_name: str) -> bool:
        # The new SDK is flexible with model names (e.g., 'gemini-2.0-flash', 'models/gemini-2.0-flash')
        return bool(model_name)  # Basic check, actual validation happens at API call

    def get_default_params(self) -> Dict[str, Any]:
        # These are parameters that can be part of genai_types.GenerateContentConfig
        return {
            "temperature": 0.7,
            "max_output_tokens": 800,
            "top_p": 0.95,
            "top_k": 40,
            "candidate_count": 1,
            "stop_sequences": None,
            # system_instruction, tools, tool_config are handled in _build_generation_config_object
        }

    def extract_token_usage(self, resp_chunk: Any) -> Dict[str, Any]:
        usage = {}
        # In the new SDK, token count might be under `usage_metadata` or directly for `count_tokens`
        # For GenerateContentResponse (from generate_content and stream chunks):
        if hasattr(resp_chunk, 'usage_metadata') and resp_chunk.usage_metadata:
            meta = resp_chunk.usage_metadata
            # Attributes are directly on usage_metadata object
            if hasattr(meta, 'prompt_token_count'): usage['prompt_tokens'] = meta.prompt_token_count
            if hasattr(meta, 'candidates_token_count'): usage['completion_tokens'] = meta.candidates_token_count
            if hasattr(meta, 'total_token_count'): usage['total_tokens'] = meta.total_token_count
            # Infer if some counts are missing
            if 'completion_tokens' not in usage and 'prompt_tokens' in usage and 'total_tokens' in usage:
                usage['completion_tokens'] = usage['total_tokens'] - usage['prompt_tokens']
        # TODO: Add handling for `client.models.count_tokens` response if different.
        return usage
