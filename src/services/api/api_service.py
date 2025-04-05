"""
Service for interacting with OpenAI API.
Adapted for web-based architecture with FastAPI.
"""

# Standard library imports
import json
import time
import logging
from typing import Any, Dict, List, Optional, Union, Iterator, Tuple, AsyncGenerator

# Third-party library imports
import httpx
import asyncio

# Create logger for this module
logger = logging.getLogger(__name__)


class ApiService:
    """
    Service for interacting with OpenAI API.
    Supports both synchronous and asynchronous operations.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__ + ".ApiService")
        self._api_key = ""
        self._base_url = "https://api.openai.com/v1"
        self._api_settings = {}

        # Use httpx for HTTP requests (supports both sync and async)
        self._client = httpx.Client(timeout=60.0, headers={"Content-Type": "application/json"})
        self._async_client = None  # Initialized on demand

        # For tracking API response metadata
        self.last_token_usage = {}
        self.last_reasoning_steps = []
        self.last_response_id = None
        self.last_model = None
        self.logger.info("ApiService initialized.")

    def set_api_key(self, api_key: str) -> None:
        """Set the API key."""
        self._api_key = api_key
        # Update session header
        self._client.headers["Authorization"] = f"Bearer {self._api_key}"
        if self._async_client:
            self._async_client.headers["Authorization"] = f"Bearer {self._api_key}"
        self.logger.debug("API key updated")

    def set_base_url(self, base_url: str) -> None:
        """Set the base URL for API calls."""
        self._base_url = base_url
        self.logger.debug(f"Base URL set to: {base_url}")

    def update_settings(self, settings: Dict[str, Any]) -> None:
        """Update API settings (used for payload generation)."""
        self._api_settings.update(settings)
        self.logger.debug(f"Updated API settings with keys: {list(settings.keys())}")
        # Re-apply API key from settings if present
        if "api_key" in settings and settings["api_key"]:
            self.set_api_key(settings["api_key"])

    def close(self) -> None:
        """Close the HTTP clients."""
        if self._client:
            self._client.close()
        if self._async_client:
            asyncio.create_task(self._async_close())
        self.logger.debug("HTTP clients closed")

    async def _async_close(self) -> None:
        """Close the async client properly."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

    def _ensure_async_client(self) -> httpx.AsyncClient:
        """Ensure the async client is initialized."""
        if not self._async_client:
            self._async_client = httpx.AsyncClient(
                timeout=120.0,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}"
                }
            )
        return self._async_client

    async def validate_api_key(self, api_key: str) -> Tuple[bool, str]:
        """Validate an API key asynchronously."""
        client = self._ensure_async_client()
        temp_headers = dict(client.headers)
        temp_headers["Authorization"] = f"Bearer {api_key}"
        url = f"{self._base_url}/models"

        try:
            async with httpx.AsyncClient(headers=temp_headers, timeout=10.0) as temp_client:
                response = await temp_client.get(url)

            if response.status_code == 200:
                return (True, "API key is valid")
            elif response.status_code == 401:
                return (False, "Invalid API key")
            else:
                return (False, f"API error ({response.status_code}): {response.text[:100]}")
        except httpx.RequestError as e:
            logger.error(f"Error validating API key: {e}")
            return (False, f"Network/Request Error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error validating API key: {e}")
            return (False, f"Unexpected Error: {e}")

    def validate_api_key_sync(self, api_key: str) -> Tuple[bool, str]:
        """Synchronously validate an API key."""
        temp_headers = dict(self._client.headers)
        temp_headers["Authorization"] = f"Bearer {api_key}"
        url = f"{self._base_url}/models"

        try:
            with httpx.Client(headers=temp_headers, timeout=10.0) as temp_client:
                response = temp_client.get(url)

            if response.status_code == 200:
                return (True, "API key is valid")
            elif response.status_code == 401:
                return (False, "Invalid API key")
            else:
                return (False, f"API error ({response.status_code}): {response.text[:100]}")
        except httpx.RequestError as e:
            logger.error(f"Error validating API key (sync): {e}")
            return (False, f"Network/Request Error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error validating API key (sync): {e}")
            return (False, f"Unexpected Error: {e}")

    # Synchronous API Methods

    def get_completion(self, messages: List[Dict], settings: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get a completion from the OpenAI API (non-streaming, synchronous).

        Args:
            messages: List of message objects.
            settings: Optional settings to override the default settings.

        Returns:
            Response data from the API.
        """
        self.logger.debug("Starting synchronous non-streaming API request")
        start_time = time.time()

        try:
            merged_settings = self._api_settings.copy()
            if settings:
                merged_settings.update(settings)

            # Ensure API key is set from merged settings if available
            if "api_key" in merged_settings and merged_settings["api_key"]:
                self._client.headers["Authorization"] = f"Bearer {merged_settings['api_key']}"
            elif not self._api_key:
                raise ValueError("API key is not set.")

            # Force stream to False
            merged_settings["stream"] = False
            api_type = merged_settings.get("api_type", "responses")

            if api_type == "responses":
                response_data = self._call_response_api(messages, merged_settings)
            else:  # chat_completions
                response_data = self._call_chat_completions_api(messages, merged_settings)

            self.logger.debug(f"API request successful. Keys: {list(response_data.keys())}")
            return response_data

        except httpx.RequestError as req_err:
            error_msg = f"API Network/Request Error: {str(req_err)}"
            self.logger.error(error_msg, exc_info=True)
            raise
        except Exception as e:
            error_msg = f"API Call Error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise
        finally:
            duration = time.time() - start_time
            self.logger.debug(f"API request finished in {duration:.3f} seconds")

    def get_streaming_completion(self, messages: List[Dict], settings: Optional[Dict] = None) -> Iterator[Dict]:
        """
        Get a streaming completion from the OpenAI API (synchronous iterator).

        Args:
            messages: List of message objects.
            settings: Optional settings to override the default settings.

        Yields:
            Dictionaries representing Server-Sent Events (SSE) data chunks.
        """
        self.logger.debug("Starting synchronous streaming API request")
        start_time = time.time()

        try:
            merged_settings = self._api_settings.copy()
            if settings:
                merged_settings.update(settings)

            # Ensure API key is set from merged settings if available
            if "api_key" in merged_settings and merged_settings["api_key"]:
                self._client.headers["Authorization"] = f"Bearer {merged_settings['api_key']}"
            elif not self._api_key:
                raise ValueError("API key is not set.")

            # Force stream to True
            merged_settings["stream"] = True
            api_type = merged_settings.get("api_type", "responses")

            # Reset tracking variables
            self.last_token_usage = {}
            self.last_reasoning_steps = []
            self.last_response_id = None
            self.last_model = None

            if api_type == "responses":
                yield from self._stream_response_api(messages, merged_settings)
            else:  # chat_completions
                yield from self._stream_chat_completions_api(messages, merged_settings)

        except httpx.RequestError as req_err:
            error_msg = f"API Streaming Network/Request Error: {str(req_err)}"
            self.logger.error(error_msg, exc_info=True)
            raise
        except Exception as e:
            error_msg = f"API Streaming Call Error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise
        finally:
            duration = time.time() - start_time
            self.logger.debug(f"API streaming request finished in {duration:.3f} seconds")

    # Asynchronous API Methods

    async def get_completion_async(self, messages: List[Dict], settings: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get a completion from the OpenAI API asynchronously (non-streaming).

        Args:
            messages: List of message objects.
            settings: Optional settings to override the default settings.

        Returns:
            Response data from the API.
        """
        self.logger.debug("Starting asynchronous non-streaming API request")
        start_time = time.time()

        try:
            merged_settings = self._api_settings.copy()
            if settings:
                merged_settings.update(settings)

            # Ensure API key is set from merged settings if available
            client = self._ensure_async_client()
            if "api_key" in merged_settings and merged_settings["api_key"]:
                client.headers["Authorization"] = f"Bearer {merged_settings['api_key']}"
            elif not self._api_key:
                raise ValueError("API key is not set.")

            # Force stream to False
            merged_settings["stream"] = False
            api_type = merged_settings.get("api_type", "responses")

            if api_type == "responses":
                response_data = await self._call_response_api_async(messages, merged_settings)
            else:  # chat_completions
                response_data = await self._call_chat_completions_api_async(messages, merged_settings)

            self.logger.debug(f"API request successful. Keys: {list(response_data.keys())}")
            return response_data

        except httpx.RequestError as req_err:
            error_msg = f"API Network/Request Error: {str(req_err)}"
            self.logger.error(error_msg, exc_info=True)
            raise
        except Exception as e:
            error_msg = f"API Call Error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise
        finally:
            duration = time.time() - start_time
            self.logger.debug(f"API request finished in {duration:.3f} seconds")

    async def get_streaming_completion_async(self, messages: List[Dict], settings: Optional[Dict] = None) -> AsyncGenerator[Dict, None]:
        """
        Get a streaming completion from the OpenAI API asynchronously.

        Args:
            messages: List of message objects.
            settings: Optional settings to override the default settings.

        Yields:
            Dictionaries representing Server-Sent Events (SSE) data chunks.
        """
        self.logger.debug("Starting asynchronous streaming API request")
        start_time = time.time()

        try:
            merged_settings = self._api_settings.copy()
            if settings:
                merged_settings.update(settings)

            # Ensure API key is set from merged settings if available
            client = self._ensure_async_client()
            if "api_key" in merged_settings and merged_settings["api_key"]:
                client.headers["Authorization"] = f"Bearer {merged_settings['api_key']}"
            elif not self._api_key:
                raise ValueError("API key is not set.")

            # Force stream to True
            merged_settings["stream"] = True
            api_type = merged_settings.get("api_type", "responses")

            # Reset tracking variables
            self.last_token_usage = {}
            self.last_reasoning_steps = []
            self.last_response_id = None
            self.last_model = None

            if api_type == "responses":
                async for chunk in self._stream_response_api_async(messages, merged_settings):
                    yield chunk
            else:  # chat_completions
                async for chunk in self._stream_chat_completions_api_async(messages, merged_settings):
                    yield chunk

        except httpx.RequestError as req_err:
            error_msg = f"API Streaming Network/Request Error: {str(req_err)}"
            self.logger.error(error_msg, exc_info=True)
            raise
        except Exception as e:
            error_msg = f"API Streaming Call Error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            raise
        finally:
            duration = time.time() - start_time
            self.logger.debug(f"API streaming request finished in {duration:.3f} seconds")

    # Internal methods - Synchronous API calls

    def _call_response_api(self, messages: List[Dict], settings: Dict) -> Dict[str, Any]:
        """Call the Response API (non-streaming) using httpx."""
        url = f"{self._base_url}/responses"
        payload = self._prepare_response_api_payload(messages, settings)
        self.logger.debug(f"Calling Response API: {url} with keys {list(payload.keys())}")

        response = self._client.post(url, json=payload)

        if response.status_code != 200:
            error_text = response.text
            self.logger.error(f"API error ({response.status_code}): {error_text}")
            response.raise_for_status()

        data = response.json()
        return self._process_response_api_response(data)

    def _call_chat_completions_api(self, messages: List[Dict], settings: Dict) -> Dict[str, Any]:
        """Call the Chat Completions API (non-streaming) using httpx."""
        url = f"{self._base_url}/chat/completions"
        payload = self._prepare_chat_completions_payload(messages, settings)
        self.logger.debug(f"Calling Chat Completions API: {url} with keys {list(payload.keys())}")

        response = self._client.post(url, json=payload)

        if response.status_code != 200:
            error_text = response.text
            self.logger.error(f"API error ({response.status_code}): {error_text}")
            response.raise_for_status()

        data = response.json()
        return self._process_chat_completions_response(data)

    def _stream_response_api(self, messages: List[Dict], settings: Dict) -> Iterator[Dict]:
        """Stream from the Response API using httpx."""
        url = f"{self._base_url}/responses"
        payload = self._prepare_response_api_payload(messages, settings)
        self.logger.debug(f"Streaming Response API: {url} with keys {list(payload.keys())}")

        with self._client.stream("POST", url, json=payload, timeout=120.0) as response:
            if response.status_code != 200:
                error_text = response.read()
                self.logger.error(f"API streaming error ({response.status_code}): {error_text}")
                response.raise_for_status()

            self.logger.debug("Streaming connection established.")
            for line in response.iter_lines():
                if not line or not line.startswith(b'data: '):
                    continue

                data_str = line[6:].decode('utf-8')
                if data_str == '[DONE]':
                    self.logger.debug("Received [DONE] marker.")
                    break

                try:
                    event = json.loads(data_str)
                    # Process and store metadata internally
                    self._process_stream_event(event, "responses")
                    yield event
                except json.JSONDecodeError:
                    self.logger.warning(f"Invalid JSON in streaming response: {data_str[:100]}...")
                    continue

        self.logger.debug("Finished processing stream.")

    def _stream_chat_completions_api(self, messages: List[Dict], settings: Dict) -> Iterator[Dict]:
        """Stream from the Chat Completions API using httpx."""
        url = f"{self._base_url}/chat/completions"
        payload = self._prepare_chat_completions_payload(messages, settings)
        self.logger.debug(f"Streaming Chat Completions API: {url} with keys {list(payload.keys())}")

        with self._client.stream("POST", url, json=payload, timeout=120.0) as response:
            if response.status_code != 200:
                error_text = response.read()
                self.logger.error(f"API streaming error ({response.status_code}): {error_text}")
                response.raise_for_status()

            self.logger.debug("Streaming connection established.")
            for line in response.iter_lines():
                if not line or not line.startswith(b'data: '):
                    continue

                data_str = line[6:].decode('utf-8')
                if data_str == '[DONE]':
                    self.logger.debug("Received [DONE] marker.")
                    break

                try:
                    chunk = json.loads(data_str)
                    # Process and store metadata internally
                    self._process_stream_event(chunk, "chat_completions")
                    yield chunk
                except json.JSONDecodeError:
                    self.logger.warning(f"Invalid JSON in streaming response: {data_str[:100]}...")
                    continue

        self.logger.debug("Finished processing stream.")

    # Internal methods - Asynchronous API calls

    async def _call_response_api_async(self, messages: List[Dict], settings: Dict) -> Dict[str, Any]:
        """Call the Response API (non-streaming) using async httpx."""
        url = f"{self._base_url}/responses"
        payload = self._prepare_response_api_payload(messages, settings)
        self.logger.debug(f"Calling Response API async: {url} with keys {list(payload.keys())}")

        client = self._ensure_async_client()
        response = await client.post(url, json=payload)

        if response.status_code != 200:
            error_text = response.text
            self.logger.error(f"API error ({response.status_code}): {error_text}")
            response.raise_for_status()

        data = response.json()
        return self._process_response_api_response(data)

    async def _call_chat_completions_api_async(self, messages: List[Dict], settings: Dict) -> Dict[str, Any]:
        """Call the Chat Completions API (non-streaming) using async httpx."""
        url = f"{self._base_url}/chat/completions"
        payload = self._prepare_chat_completions_payload(messages, settings)
        self.logger.debug(f"Calling Chat Completions API async: {url} with keys {list(payload.keys())}")

        client = self._ensure_async_client()
        response = await client.post(url, json=payload)

        if response.status_code != 200:
            error_text = response.text
            self.logger.error(f"API error ({response.status_code}): {error_text}")
            response.raise_for_status()

        data = response.json()
        return self._process_chat_completions_response(data)

    async def _stream_response_api_async(self, messages: List[Dict], settings: Dict) -> AsyncGenerator[Dict, None]:
        """Stream from the Response API using async httpx."""
        url = f"{self._base_url}/responses"
        payload = self._prepare_response_api_payload(messages, settings)
        self.logger.debug(f"Streaming Response API async: {url} with keys {list(payload.keys())}")

        client = self._ensure_async_client()
        async with client.stream("POST", url, json=payload, timeout=120.0) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                self.logger.error(f"API streaming error ({response.status_code}): {error_text}")
                response.raise_for_status()

            self.logger.debug("Streaming connection established.")
            async for line in response.aiter_lines():
                if not line or not line.startswith('data: '):
                    continue

                data_str = line[6:]
                if data_str == '[DONE]':
                    self.logger.debug("Received [DONE] marker.")
                    break

                try:
                    event = json.loads(data_str)
                    # Process and store metadata internally
                    self._process_stream_event(event, "responses")
                    yield event
                except json.JSONDecodeError:
                    self.logger.warning(f"Invalid JSON in streaming response: {data_str[:100]}...")
                    continue

        self.logger.debug("Finished async processing stream.")

    async def _stream_chat_completions_api_async(self, messages: List[Dict], settings: Dict) -> AsyncGenerator[Dict, None]:
        """Stream from the Chat Completions API using async httpx."""
        url = f"{self._base_url}/chat/completions"
        payload = self._prepare_chat_completions_payload(messages, settings)
        self.logger.debug(f"Streaming Chat Completions API async: {url} with keys {list(payload.keys())}")

        client = self._ensure_async_client()
        async with client.stream("POST", url, json=payload, timeout=120.0) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                self.logger.error(f"API streaming error ({response.status_code}): {error_text}")
                response.raise_for_status()

            self.logger.debug("Streaming connection established.")
            async for line in response.aiter_lines():
                if not line or not line.startswith('data: '):
                    continue

                data_str = line[6:]
                if data_str == '[DONE]':
                    self.logger.debug("Received [DONE] marker.")
                    break

                try:
                    chunk = json.loads(data_str)
                    # Process and store metadata internally
                    self._process_stream_event(chunk, "chat_completions")
                    yield chunk
                except json.JSONDecodeError:
                    self.logger.warning(f"Invalid JSON in streaming response: {data_str[:100]}...")
                    continue

        self.logger.debug("Finished async processing stream.")

    # Helper methods - these are shared between sync and async versions

    def _process_stream_event(self, event: Dict, api_type: str):
        """Helper to process metadata from stream events (used internally)."""
        try:
            if api_type == "responses":
                event_type = event.get('type')
                if event_type == 'response.created':
                    if 'response' in event and 'id' in event['response']:
                        self.last_response_id = event['response']['id']
                elif event_type == 'response.completed':
                    if 'response' in event and 'usage' in event['response']:
                        usage = event['response']['usage']
                        self.last_token_usage = {
                            "prompt_tokens": usage.get('input_tokens', 0),
                            "completion_tokens": usage.get('output_tokens', 0),
                            "total_tokens": usage.get('total_tokens', 0)
                        }
                    if 'response' in event and 'model' in event['response']:
                        self.last_model = event['response']['model']
                elif event_type == 'response.thinking_step':
                    if 'thinking_step' in event:
                        step = event['thinking_step']
                        step_data = {"name": step.get('name', 'Thinking'), "content": step.get('content', '')}
                        if not self.last_reasoning_steps:
                            self.last_reasoning_steps = []
                        self.last_reasoning_steps.append(step_data)

            elif api_type == "chat_completions":
                if 'id' in event and not self.last_response_id:
                    self.last_response_id = event['id']
                if 'model' in event and not self.last_model:
                    self.last_model = event['model']
                if 'choices' in event and len(event['choices']) > 0:
                    choice = event['choices'][0]
                    if choice.get('finish_reason') and 'usage' in event:
                        usage = event['usage']
                        self.last_token_usage = {
                            "prompt_tokens": usage.get('prompt_tokens', 0),
                            "completion_tokens": usage.get('completion_tokens', 0),
                            "total_tokens": usage.get('total_tokens', 0)
                        }
        except Exception as e:
            self.logger.warning(f"Error processing stream metadata event: {e} - Event: {event}")

    def _prepare_response_api_payload(self, messages: List[Dict], settings: Dict) -> Dict[str, Any]:
        """Prepare a payload for the Response API"""
        # Convert messages to text input for Response API
        input_text = self._prepare_input(messages, "responses")

        # Get the system message for instructions
        system_message = None
        for message in messages:
            if message.get("role") == "system":
                system_message = message.get("content", "")
                break

        # Base parameters
        payload = {
            "model": settings.get("model", "gpt-4o"),
            "input": input_text,
            "temperature": settings.get("temperature", 0.7),
            "top_p": settings.get("top_p", 1.0),
            "stream": settings.get("stream", True),
        }

        # Add instructions from system message if available
        if system_message:
            payload["instructions"] = system_message

        # Add Response API specific parameters
        if "store" in settings:
            payload["store"] = settings.get("store")

        # Handle text format (response format)
        if "text" in settings and isinstance(settings["text"], dict):
            payload["text"] = settings["text"]
        else:
            # Default text format
            payload["text"] = {"format": {"type": "text"}}

        # Add token limit parameter
        token_limit = settings.get(
            "max_output_tokens",
            settings.get("max_completion_tokens", settings.get("max_tokens", 1024))
        )
        payload["max_output_tokens"] = token_limit

        # Add reasoning parameters for supported models
        if "reasoning" in settings:
            payload["reasoning"] = settings["reasoning"]

        # Add seed if specified
        if settings.get("seed") is not None:
            payload["seed"] = settings.get("seed")

        # Add user identifier if present
        if settings.get("user") is not None:
            payload["user"] = settings.get("user")

        return payload

    def _prepare_chat_completions_payload(self, messages: List[Dict], settings: Dict) -> Dict[str, Any]:
        """Prepare a payload for the Chat Completions API"""
        # Process messages for the Chat API format
        prepared_messages = self._prepare_input(messages, "chat_completions")

        # Base parameters
        payload = {
            "model": settings.get("model", "gpt-4o"),
            "messages": prepared_messages,
            "temperature": settings.get("temperature", 0.7),
            "top_p": settings.get("top_p", 1.0),
            "stream": settings.get("stream", True),
        }

        # Add response format if specified
        if "response_format" in settings:
            payload["response_format"] = settings["response_format"]

        # Get token limit with appropriate fallbacks
        token_limit = settings.get(
            "max_completion_tokens",
            settings.get("max_tokens", settings.get("max_output_tokens", 1024))
        )

        # Check if this is an o-series or reasoning model that requires max_completion_tokens
        is_o_series = (
                "o1" in settings.get("model", "") or
                "o3" in settings.get("model", "") or
                settings.get("model", "").startswith("deepseek-")
        )

        if is_o_series:
            # These models require max_completion_tokens instead of max_tokens
            payload["max_completion_tokens"] = token_limit
        else:
            # Standard models use max_tokens
            payload["max_tokens"] = token_limit

        # Add seed if specified
        if settings.get("seed") is not None:
            payload["seed"] = settings.get("seed")

        # Add other common parameters if specified
        for param in ["frequency_penalty", "presence_penalty", "logit_bias", "user"]:
            if param in settings and settings[param] is not None:
                payload[param] = settings[param]

        return payload

    def _prepare_input(self, messages: List[Dict], api_type: str) -> Union[str, List[Dict]]:
        """
        Prepare messages for the API format based on api_type

        Args:
            messages: The raw messages
            api_type: Either "responses" or "chat_completions"

        Returns:
            Either formatted text (for responses API) or a list of messages (for chat API)
        """
        if api_type == "responses":
            # Format for Response API - combine into text
            all_content = []

            for message in messages:
                # Skip system messages as they will be handled as 'instructions'
                if message.get("role") == "system":
                    continue

                role_prefix = ""
                if message.get("role") == "user":
                    role_prefix = "User: "
                elif message.get("role") == "assistant":
                    role_prefix = "Assistant: "

                # Add message content
                if "content" in message:
                    all_content.append(f"{role_prefix}{message['content']}")

                # Handle file attachments if present
                if "attached_files" in message and message["attached_files"]:
                    file_sections = ["\n\n# ATTACHED FILES"]

                    for file_info in message["attached_files"]:
                        file_name = file_info.get("file_name", "")
                        file_content = file_info.get("content", "")

                        file_sections.append(f"""
                            ### FILE: {file_name}
                            {file_content}
                        """)

                    all_content.append("\n".join(file_sections))

            # Return the combined text as the input
            return "\n\n".join(all_content)
        else:
            # Format for Chat Completions API - as message objects
            prepared_messages = []

            for message in messages:
                # Clone the message with only the necessary fields
                prepared_message = {
                    "role": message.get("role", "user"),
                    "content": message.get("content", "")
                }

                # Handle file attachments if present
                if "attached_files" in message and message["attached_files"]:
                    file_content = "\n\n# ATTACHED FILES\n"

                    for file_info in message["attached_files"]:
                        file_name = file_info.get("file_name", "")
                        file_content += f"\n### FILE: {file_name}\n{file_info.get('content', '')}\n"

                    # Append file content to message content
                    prepared_message["content"] += file_content

                prepared_messages.append(prepared_message)

            return prepared_messages

    def _process_response_api_response(self, data: Dict) -> Dict[str, Any]:
        """Process a non-streaming response from the Response API"""
        result = {}

        # Extract content
        if "output_text" in data:
            result["content"] = data["output_text"]

        # Extract response ID
        if "id" in data:
            result["response_id"] = data["id"]
            self.last_response_id = data["id"]

        # Extract model info
        if "model" in data:
            result["model"] = data["model"]
            self.last_model = data["model"]

        # Extract token usage
        if "usage" in data:
            usage = data["usage"]
            self.last_token_usage = {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }
            result["token_usage"] = self.last_token_usage

        # Extract reasoning steps if available
        if "reasoning" in data and "steps" in data["reasoning"]:
            steps = data["reasoning"]["steps"]
            self.last_reasoning_steps = [
                {
                    "name": step.get("name", f"Step {i + 1}"),
                    "content": step.get("content", "")
                }
                for i, step in enumerate(steps)
            ]
            result["reasoning_steps"] = self.last_reasoning_steps

        return result

    def _process_chat_completions_response(self, data: Dict) -> Dict[str, Any]:
        """Process a non-streaming response from the Chat Completions API"""
        result = {}

        # Extract content
        if "choices" in data and len(data["choices"]) > 0:
            choice = data["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                result["content"] = choice["message"]["content"]

        # Extract response ID
        if "id" in data:
            result["response_id"] = data["id"]
            self.last_response_id = data["id"]

        # Extract model info
        if "model" in data:
            result["model"] = data["model"]
            self.last_model = data["model"]

        # Extract token usage
        if "usage" in data:
            usage = data["usage"]
            self.last_token_usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }
            result["token_usage"] = self.last_token_usage

        return result