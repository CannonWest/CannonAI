# src/services/api_service.py

import asyncio
from typing import Dict, List, Any, Optional, Generator, Union
import json
import aiohttp
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class ApiService(QObject):
    """
    Service for interacting with OpenAI API using asyncio
    """

    # Define signals
    responseReceived = pyqtSignal(dict)
    chunkReceived = pyqtSignal(str)
    errorOccurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.last_token_usage = {}
        self.last_reasoning_steps = []
        self.last_response_id = None
        self._api_key = ""
        self._base_url = "https://api.openai.com/v1"

    def set_api_key(self, api_key: str) -> None:
        """Set the API key"""
        self._api_key = api_key

    def set_base_url(self, base_url: str) -> None:
        """Set the base URL for API calls"""
        self._base_url = base_url

    def get_response(self, messages: List[Dict], settings: Dict) -> Dict:
        """
        Synchronous method to get a chat completion
        """
        # Create and run the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Run the async method and get the result
            response = loop.run_until_complete(
                self._async_get_response(messages, settings)
            )
            return response
        finally:
            loop.close()

    def get_streaming_response(self, messages: List[Dict], settings: Dict) -> Generator[Union[str, Dict], None, None]:
        """
        Get a streaming response - returns a generator that yields chunks
        """
        # Create and run the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Create an async generator adapter
        async def run_stream():
            async for chunk in self._async_get_streaming_response(messages, settings):
                yield chunk

        # Get the generator from the event loop
        gen = run_stream()

        try:
            # Run the generator until it's exhausted
            while True:
                try:
                    chunk = loop.run_until_complete(gen.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    async def _async_get_response(self, messages: List[Dict], settings: Dict) -> Dict:
        """
        Async method to get a chat completion
        """
        # Use settings or defaults
        api_key = settings.get("api_key", self._api_key)
        model = settings.get("model", "gpt-4o")
        temperature = settings.get("temperature", 0.7)
        max_tokens = settings.get("max_tokens", 1024)
        api_type = settings.get("api_type", "chat_completions")  # or "responses"

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        # Prepare URL based on API type
        if api_type == "responses":
            url = f"{self._base_url}/responses"
            # Convert messages to input format for Response API
            input_text = self._prepare_input_for_response_api(messages)

            # Prepare payload for Response API
            payload = {
                "model": model,
                "input": input_text,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "stream": False  # Non-streaming
            }

            # Add system message as instructions if available
            system_message = next((msg["content"] for msg in messages if msg["role"] == "system"), None)
            if system_message:
                payload["instructions"] = system_message

            # Add response format
            payload["text"] = {"format": {"type": "text"}}

        else:  # chat_completions
            url = f"{self._base_url}/chat/completions"

            # Filter out file attachments before sending (not supported in simple format)
            cleaned_messages = []
            for msg in messages:
                message_copy = {
                    "role": msg["role"],
                    "content": msg["content"]
                }
                cleaned_messages.append(message_copy)

            # Prepare payload for Chat Completions API
            payload = {
                "model": model,
                "messages": cleaned_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False  # Non-streaming
            }

        # Make the API request
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API Error ({response.status}): {error_text}")

                    data = await response.json()

                    # Process the response based on API type
                    if api_type == "responses":
                        result = self._process_response_api_response(data)
                    else:
                        result = self._process_chat_completions_response(data)

                    return result
            except aiohttp.ClientError as e:
                raise Exception(f"Connection error: {str(e)}")

    async def _async_get_streaming_response(self, messages: List[Dict], settings: Dict):
        """
        Async method to get a streaming chat completion
        """
        # Use settings or defaults
        api_key = settings.get("api_key", self._api_key)
        model = settings.get("model", "gpt-4o")
        temperature = settings.get("temperature", 0.7)
        max_tokens = settings.get("max_tokens", 1024)
        api_type = settings.get("api_type", "chat_completions")  # or "responses"

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        # Prepare URL and payload based on API type
        if api_type == "responses":
            url = f"{self._base_url}/responses"
            # Convert messages to input format for Response API
            input_text = self._prepare_input_for_response_api(messages)

            # Prepare payload for Response API
            payload = {
                "model": model,
                "input": input_text,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "stream": True  # Enable streaming
            }

            # Add system message as instructions if available
            system_message = next((msg["content"] for msg in messages if msg["role"] == "system"), None)
            if system_message:
                payload["instructions"] = system_message

            # Add response format
            payload["text"] = {"format": {"type": "text"}}

        else:  # chat_completions
            url = f"{self._base_url}/chat/completions"

            # Filter out file attachments before sending (not supported in simple format)
            cleaned_messages = []
            for msg in messages:
                message_copy = {
                    "role": msg["role"],
                    "content": msg["content"]
                }
                cleaned_messages.append(message_copy)

            # Prepare payload for Chat Completions API
            payload = {
                "model": model,
                "messages": cleaned_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True  # Enable streaming
            }

        # Reset token usage and response ID for new request
        self.last_token_usage = {}
        self.last_reasoning_steps = []
        self.last_response_id = None

        # Make the API request
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"API Error ({response.status}): {error_text}")

                    # Process the streaming response
                    if api_type == "responses":
                        async for chunk in self._process_response_api_stream(response):
                            yield chunk
                    else:
                        async for chunk in self._process_chat_completions_stream(response):
                            yield chunk

            except aiohttp.ClientError as e:
                raise Exception(f"Connection error: {str(e)}")

    async def _process_response_api_stream(self, response):
        """Process a streaming response from the Response API"""
        buffer = ""

        async for line in response.content:
            line = line.decode('utf-8').strip()
            if not line:
                continue

            if not line.startswith('data: '):
                continue

            # Remove the 'data: ' prefix
            data = line[6:]

            # Skip [DONE] marker
            if data == '[DONE]':
                break

            try:
                event = json.loads(data)
                event_type = event.get('type')

                if event_type == 'response.output_text.delta':
                    # Text content
                    if 'delta' in event and event['delta']:
                        delta = event['delta']
                        buffer += delta
                        yield delta  # Yield just the new text

                elif event_type == 'response.created':
                    # Capture response ID
                    if 'response' in event and 'id' in event['response']:
                        self.last_response_id = event['response']['id']
                        # Yield a metadata dictionary
                        yield {"response_id": self.last_response_id}

                elif event_type == 'response.completed':
                    # Final event with metadata like token usage
                    if 'response' in event and 'usage' in event['response']:
                        usage = event['response']['usage']
                        self.last_token_usage = {
                            "prompt_tokens": usage.get('input_tokens', 0),
                            "completion_tokens": usage.get('output_tokens', 0),
                            "total_tokens": usage.get('total_tokens', 0)
                        }
                        # Yield token usage as metadata
                        yield {"token_usage": self.last_token_usage}

                # For o1 models with reasoning steps
                elif event_type == 'response.thinking_step':
                    if 'thinking_step' in event:
                        step = event['thinking_step']
                        step_data = {
                            "name": step.get('name', 'Thinking'),
                            "content": step.get('content', '')
                        }
                        if not self.last_reasoning_steps:
                            self.last_reasoning_steps = []
                        self.last_reasoning_steps.append(step_data)
                        # Yield the reasoning step
                        yield {"reasoning_step": step_data}

            except json.JSONDecodeError:
                # Ignore invalid JSON
                continue

    async def _process_chat_completions_stream(self, response):
        """Process a streaming response from the Chat Completions API"""
        buffer = ""

        async for line in response.content:
            line = line.decode('utf-8').strip()
            if not line:
                continue

            if not line.startswith('data: '):
                continue

            # Remove the 'data: ' prefix
            data = line[6:]

            # Skip [DONE] marker
            if data == '[DONE]':
                break

            try:
                chunk = json.loads(data)

                # Extract completion ID
                if 'id' in chunk and not self.last_response_id:
                    self.last_response_id = chunk['id']
                    yield {"response_id": self.last_response_id}

                # Process choices
                if 'choices' in chunk and len(chunk['choices']) > 0:
                    choice = chunk['choices'][0]

                    # Check if this is a delta with content
                    if 'delta' in choice and 'content' in choice['delta']:
                        delta = choice['delta']['content']
                        buffer += delta
                        yield delta  # Yield just the new text

                    # Check for finish_reason to get usage info
                    if choice.get('finish_reason') and 'usage' in chunk:
                        usage = chunk['usage']
                        self.last_token_usage = {
                            "prompt_tokens": usage.get('prompt_tokens', 0),
                            "completion_tokens": usage.get('completion_tokens', 0),
                            "total_tokens": usage.get('total_tokens', 0)
                        }
                        # Yield token usage as metadata
                        yield {"token_usage": self.last_token_usage}

            except json.JSONDecodeError:
                # Ignore invalid JSON
                continue

    def _prepare_input_for_response_api(self, messages: List[Dict]) -> str:
        """Convert message list to text input for Response API"""
        result = []

        for message in messages:
            # Skip system messages as they'll go in instructions
            if message["role"] == "system":
                continue

            # Format based on role
            if message["role"] == "user":
                prefix = "User: "
            elif message["role"] == "assistant":
                prefix = "Assistant: "
            else:
                prefix = f"{message['role'].capitalize()}: "

            # Add message content
            result.append(f"{prefix}{message['content']}")

            # Handle file attachments if present
            if "attached_files" in message and message["attached_files"]:
                file_sections = ["\n\n# ATTACHED FILES"]

                for file_info in message["attached_files"]:
                    file_name = file_info["file_name"]
                    file_content = file_info.get("content", "")

                    file_sections.append(f"""
                        ### FILE: {file_name}
                        {file_content}
                    """)

                result.append("\n".join(file_sections))

        return "\n\n".join(result)

    def _process_response_api_response(self, data: Dict) -> Dict:
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

    def _process_chat_completions_response(self, data: Dict) -> Dict:
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