"""
Asynchronous API service for interacting with OpenAI API.
"""

import asyncio
import json
from typing import Dict, List, Any, Optional, AsyncGenerator, Union
import aiohttp
from PyQt6.QtCore import QObject, pyqtSignal

from src.utils.logging_utils import get_logger


class AsyncApiService(QObject):
    """
    Service for interacting with OpenAI API using proper async/await patterns.
    This service integrates with Qt's event loop using signals for communication.
    """

    # Define signals
    responseReceived = pyqtSignal(dict)
    chunkReceived = pyqtSignal(str)
    metadataReceived = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)
    requestStarted = pyqtSignal()
    requestFinished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.logger = get_logger(__name__)
        self._api_key = ""
        self._base_url = "https://api.openai.com/v1"
        self._api_settings = {}
        self._session = None
        
        # For tracking API response metadata
        self.last_token_usage = {}
        self.last_reasoning_steps = []
        self.last_response_id = None
        self.last_model = None

    def set_api_key(self, api_key: str) -> None:
        """Set the API key"""
        self._api_key = api_key
        self.logger.debug("API key set")

    def set_base_url(self, base_url: str) -> None:
        """Set the base URL for API calls"""
        self._base_url = base_url
        self.logger.debug(f"Base URL set to: {base_url}")

    def update_settings(self, settings: Dict[str, Any]) -> None:
        """Update API settings"""
        self._api_settings.update(settings)
        self.logger.debug(f"Updated API settings with keys: {list(settings.keys())}")

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=60)  # 60 second timeout
            # Create a new session, make sure to close it when done
            self._session = aiohttp.ClientSession(timeout=timeout)
            self.logger.debug("Created new aiohttp session")
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self.logger.debug("Closed aiohttp session")

    async def get_completion(self, messages: List[Dict], settings: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get a completion from the OpenAI API (non-streaming)

        Args:
            messages: List of message objects
            settings: Optional settings to override the default settings

        Returns:
            Response data from the API
        """
        self.requestStarted.emit()
        self.logger.debug("Starting non-streaming API request")

        try:
            merged_settings = self._api_settings.copy()
            if settings:
                merged_settings.update(settings)

            # Force stream to False for this method
            merged_settings["stream"] = False

            # Select API type
            api_type = merged_settings.get("api_type", "responses")

            if api_type == "responses":
                response = await self._call_response_api(messages, merged_settings)
            else:  # chat_completions
                response = await self._call_chat_completions_api(messages, merged_settings)

            self.responseReceived.emit(response)
            self.logger.debug(f"Emitted API response: {list(response.keys()) if response else 'None'}")
            return response

        except Exception as e:
            error_msg = f"API Error: {str(e)}"
            self.logger.error(error_msg)
            self.errorOccurred.emit(error_msg)
            raise
        finally:
            self.requestFinished.emit()
            self.logger.debug("API request finished")

    async def get_streaming_completion(self, messages: List[Dict], settings: Optional[Dict] = None) -> AsyncGenerator[Union[str, Dict], None]:
        """
        Get a streaming completion from the OpenAI API

        Args:
            messages: List of message objects
            settings: Optional settings to override the default settings

        Yields:
            Either text chunks (str) or metadata (Dict)
        """
        self.requestStarted.emit()
        self.logger.debug("Starting streaming API request")

        try:
            merged_settings = self._api_settings.copy()
            if settings:
                merged_settings.update(settings)

            # Force stream to True for this method
            merged_settings["stream"] = True

            # Reset tracking variables
            self.last_token_usage = {}
            self.last_reasoning_steps = []
            self.last_response_id = None
            self.last_model = None

            # Select API type
            api_type = merged_settings.get("api_type", "responses")
            self.logger.debug(f"Using API type: {api_type}")

            if api_type == "responses":
                async for item in self._stream_response_api(messages, merged_settings):
                    if isinstance(item, str):
                        self.logger.debug(f"Emitting text chunk (len {len(item)})")
                        self.chunkReceived.emit(item)
                    else:
                        self.logger.debug(f"Emitting metadata: {list(item.keys()) if item else 'None'}")
                        self.metadataReceived.emit(item)
                    yield item
            else:  # chat_completions
                async for item in self._stream_chat_completions_api(messages, merged_settings):
                    if isinstance(item, str):
                        self.logger.debug(f"Emitting text chunk (len {len(item)})")
                        self.chunkReceived.emit(item)
                    else:
                        self.logger.debug(f"Emitting metadata: {list(item.keys()) if item else 'None'}")
                        self.metadataReceived.emit(item)
                    yield item

        except Exception as e:
            error_msg = f"API Streaming Error: {str(e)}"
            self.logger.error(error_msg)
            self.errorOccurred.emit(error_msg)
            raise
        finally:
            self.requestFinished.emit()
            self.logger.debug("Streaming API request finished")

    async def _call_response_api(self, messages: List[Dict], settings: Dict) -> Dict[str, Any]:
        """Call the Response API (non-streaming)"""
        url = f"{self._base_url}/responses"
        self.logger.debug(f"Calling Response API at URL: {url}")

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.get('api_key', self._api_key)}"
        }

        # Prepare payload
        payload = self._prepare_response_api_payload(messages, settings)
        self.logger.debug(f"Response API payload keys: {list(payload.keys())}")

        # Make the API request
        session = await self.get_session()
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                self.logger.error(f"API error ({response.status}): {error_text}")
                raise Exception(f"API Error ({response.status}): {error_text}")

            data = await response.json()
            self.logger.debug("Received Response API data")

            # Process the response
            processed_response = self._process_response_api_response(data)
            return processed_response

    async def _call_chat_completions_api(self, messages: List[Dict], settings: Dict) -> Dict[str, Any]:
        """Call the Chat Completions API (non-streaming)"""
        url = f"{self._base_url}/chat/completions"
        self.logger.debug(f"Calling Chat Completions API at URL: {url}")

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.get('api_key', self._api_key)}"
        }

        # Prepare payload
        payload = self._prepare_chat_completions_payload(messages, settings)
        self.logger.debug(f"Chat Completions API payload keys: {list(payload.keys())}")

        # Make the API request
        session = await self.get_session()
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                self.logger.error(f"API error ({response.status}): {error_text}")
                raise Exception(f"API Error ({response.status}): {error_text}")

            data = await response.json()
            self.logger.debug("Received Chat Completions API data")

            # Process the response
            processed_response = self._process_chat_completions_response(data)
            return processed_response

    async def _stream_response_api(self, messages: List[Dict], settings: Dict) -> AsyncGenerator[Union[str, Dict], None]:
        """Stream from the Response API"""
        url = f"{self._base_url}/responses"
        self.logger.debug(f"Streaming from Response API at URL: {url}")

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.get('api_key', self._api_key)}"
        }

        # Prepare payload
        payload = self._prepare_response_api_payload(messages, settings)
        self.logger.debug(f"Response API streaming payload keys: {list(payload.keys())}")

        # Make the API request
        session = await self.get_session()
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"API error ({response.status}): {error_text}")
                    raise Exception(f"API Error ({response.status}): {error_text}")

                # Process the streaming response
                line_count = 0
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue

                    if not line.startswith('data: '):
                        continue

                    # Remove the 'data: ' prefix
                    data = line[6:]
                    line_count += 1

                    # Skip [DONE] marker
                    if data == '[DONE]':
                        self.logger.debug("Received [DONE] marker")
                        break

                    try:
                        event = json.loads(data)
                        event_type = event.get('type')

                        if event_type == 'response.output_text.delta':
                            # Text content
                            if 'delta' in event and event['delta']:
                                delta = event['delta']
                                self.logger.debug(f"Received text delta (len {len(delta)})")
                                yield delta  # Yield just the new text

                        elif event_type == 'response.created':
                            # Capture response ID
                            if 'response' in event and 'id' in event['response']:
                                self.last_response_id = event['response']['id']
                                self.logger.debug(f"Received response ID: {self.last_response_id}")
                                # Yield a metadata dictionary
                                metadata = {"response_id": self.last_response_id}
                                yield metadata

                        elif event_type == 'response.completed':
                            # Final event with metadata like token usage
                            self.logger.debug("Received completion event")
                            if 'response' in event and 'usage' in event['response']:
                                usage = event['response']['usage']
                                self.last_token_usage = {
                                    "prompt_tokens": usage.get('input_tokens', 0),
                                    "completion_tokens": usage.get('output_tokens', 0),
                                    "total_tokens": usage.get('total_tokens', 0)
                                }
                                self.logger.debug(f"Extracted token usage: {self.last_token_usage}")
                                # Yield token usage as metadata
                                metadata = {"token_usage": self.last_token_usage}
                                yield metadata

                            # Capture model information if available
                            if 'response' in event and 'model' in event['response']:
                                self.last_model = event['response']['model']
                                self.logger.debug(f"Extracted model: {self.last_model}")
                                metadata = {"model": self.last_model}
                                yield metadata

                        # For o1 models with reasoning steps
                        elif event_type == 'response.thinking_step':
                            if 'thinking_step' in event:
                                step = event['thinking_step']
                                step_data = {
                                    "name": step.get('name', 'Thinking'),
                                    "content": step.get('content', '')
                                }
                                self.logger.debug(f"Received thinking step: {step_data['name']}")
                                if not self.last_reasoning_steps:
                                    self.last_reasoning_steps = []
                                self.last_reasoning_steps.append(step_data)
                                # Yield the reasoning step
                                metadata = {"reasoning_step": step_data}
                                yield metadata

                    except json.JSONDecodeError:
                        # Ignore invalid JSON
                        self.logger.warning(f"Invalid JSON in streaming response: {data[:50]}...")
                        continue

                self.logger.debug(f"Processed {line_count} streaming response lines")
        except Exception as e:
            self.logger.error(f"Error in _stream_response_api: {str(e)}")
            raise

    async def _stream_chat_completions_api(self, messages: List[Dict], settings: Dict) -> AsyncGenerator[Union[str, Dict], None]:
        """Stream from the Chat Completions API"""
        url = f"{self._base_url}/chat/completions"
        self.logger.debug(f"Streaming from Chat Completions API at URL: {url}")

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.get('api_key', self._api_key)}"
        }

        # Prepare payload
        payload = self._prepare_chat_completions_payload(messages, settings)
        self.logger.debug(f"Chat Completions API streaming payload keys: {list(payload.keys())}")

        # Make the API request
        session = await self.get_session()
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"API error ({response.status}): {error_text}")
                    raise Exception(f"API Error ({response.status}): {error_text}")

                # Process the streaming response
                line_count = 0
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue

                    if not line.startswith('data: '):
                        continue

                    # Remove the 'data: ' prefix
                    data = line[6:]
                    line_count += 1

                    # Skip [DONE] marker
                    if data == '[DONE]':
                        self.logger.debug("Received [DONE] marker")
                        break

                    try:
                        chunk = json.loads(data)

                        # Extract completion ID
                        if 'id' in chunk and not self.last_response_id:
                            self.last_response_id = chunk['id']
                            self.logger.debug(f"Received completion ID: {self.last_response_id}")
                            metadata = {"response_id": self.last_response_id}
                            yield metadata

                        # Extract model information
                        if 'model' in chunk and not self.last_model:
                            self.last_model = chunk['model']
                            self.logger.debug(f"Extracted model: {self.last_model}")
                            metadata = {"model": self.last_model}
                            yield metadata

                        # Process choices
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            choice = chunk['choices'][0]

                            # Check if this is a delta with content
                            if 'delta' in choice and 'content' in choice['delta']:
                                delta = choice['delta']['content']
                                self.logger.debug(f"Received content delta (len {len(delta)})")
                                yield delta  # Yield just the new text

                            # Check for finish_reason to get usage info
                            if choice.get('finish_reason') and 'usage' in chunk:
                                usage = chunk['usage']
                                self.last_token_usage = {
                                    "prompt_tokens": usage.get('prompt_tokens', 0),
                                    "completion_tokens": usage.get('completion_tokens', 0),
                                    "total_tokens": usage.get('total_tokens', 0)
                                }
                                self.logger.debug(f"Extracted token usage: {self.last_token_usage}")
                                # Yield token usage as metadata
                                metadata = {"token_usage": self.last_token_usage}
                                yield metadata

                    except json.JSONDecodeError:
                        # Ignore invalid JSON
                        self.logger.warning(f"Invalid JSON in streaming response: {data[:50]}...")
                        continue

                self.logger.debug(f"Processed {line_count} streaming response lines")
        except Exception as e:
            self.logger.error(f"Error in _stream_chat_completions_api: {str(e)}")
            raise

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