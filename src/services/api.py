"""
API services for interacting with the OpenAI API.
"""

from typing import Dict, List, Optional, Any, Callable
from PyQt6.QtCore import QThread, pyqtSignal

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from src.utils import REASONING_MODELS
from src.utils.logging_utils import get_logger, log_exception

# Get a logger for this module
logger = get_logger(__name__)


class OpenAIChatWorker(QThread):
    """Worker thread for making OpenAI API calls"""

    message_received = pyqtSignal(str)  # Full final message
    chunk_received = pyqtSignal(str)  # Streaming chunks
    thinking_step = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    usage_info = pyqtSignal(dict)
    system_info = pyqtSignal(dict)
    completion_id = pyqtSignal(str)

    def __init__(self, messages: List[ChatCompletionMessageParam], settings: Dict[str, Any]):
        super().__init__()
        self.messages = messages
        self.settings = settings
        self.logger = get_logger(f"{__name__}.OpenAIChatWorker")

    def run(self):
        """Execute the API call in a separate thread"""
        try:
            self.logger.debug("Starting OpenAI API request")

            api_key = self.settings.get("api_key")
            api_base = self.settings.get("api_base")

            client_kwargs = {}
            if api_key:
                client_kwargs["api_key"] = api_key
            if api_base:
                self.logger.debug(f"Using custom API base URL: {api_base}")
                client_kwargs["base_url"] = api_base

            client = OpenAI(**client_kwargs)

            # Process messages to include file content
            processed_messages = self.prepare_messages(self.messages)
            self.logger.debug(f"Prepared {len(processed_messages)} messages for API request")

            # Extract model parameters from settings
            model = self.settings.get("model")
            self.logger.info(f"Using model: {model}")

            params = {
                "model": model,
                "messages": processed_messages,
                "temperature": self.settings.get("temperature"),
                "top_p": self.settings.get("top_p"),
                "frequency_penalty": self.settings.get("frequency_penalty"),
                "presence_penalty": self.settings.get("presence_penalty"),
                "stream": self.settings.get("stream", True),
            }

            # Add newer parameters if they're set in settings
            if "max_completion_tokens" in self.settings:
                params["max_completion_tokens"] = self.settings.get("max_completion_tokens")
                self.logger.debug(f"Setting max_completion_tokens: {params['max_completion_tokens']}")
            elif "max_tokens" in self.settings:
                # For backward compatibility
                params["max_tokens"] = self.settings.get("max_tokens")
                self.logger.debug(f"Setting max_tokens: {params['max_tokens']}")

            # Add response format if specified
            if "response_format" in self.settings:
                params["response_format"] = self.settings.get("response_format")
                self.logger.debug(f"Setting response_format: {params['response_format']}")

            # Add reasoning effort for o1/o3 models
            if self.settings.get("reasoning_effort") and self.settings.get("model") in REASONING_MODELS:
                params["reasoning_effort"] = self.settings.get("reasoning_effort")
                self.logger.debug(f"Setting reasoning_effort: {params['reasoning_effort']}")

            # Add seed if specified
            if self.settings.get("seed") is not None:
                params["seed"] = self.settings.get("seed")
                self.logger.debug(f"Setting seed: {params['seed']}")

            # Add service tier if specified
            if self.settings.get("service_tier"):
                params["service_tier"] = self.settings.get("service_tier")
                self.logger.debug(f"Setting service_tier: {params['service_tier']}")

            # Add store parameter if specified
            if self.settings.get("store"):
                params["store"] = True
                self.logger.debug("Enabling completion storage")

            # Add metadata if present
            if self.settings.get("metadata") and len(self.settings.get("metadata")) > 0:
                params["metadata"] = self.settings.get("metadata")
                self.logger.debug(f"Setting metadata: {params['metadata']}")

            # Set up streaming options if needed
            if params["stream"]:
                params["stream_options"] = {"include_usage": True}
                self.logger.debug("Streaming mode enabled with usage info")

            if params["stream"]:
                # Streaming mode
                self.logger.debug("Starting streaming request")
                full_response = ""
                stream = client.chat.completions.create(**params)

                # Store the completion ID if available
                if hasattr(stream, 'id'):
                    completion_id = stream.id
                    self.logger.debug(f"Received completion ID: {completion_id}")
                    self.completion_id.emit(completion_id)

                for chunk in stream:
                    # Handle usage information if available
                    if hasattr(chunk, 'usage') and chunk.usage is not None:
                        completion_details = {}
                        if hasattr(chunk.usage, 'completion_tokens_details'):
                            completion_details = {
                                "reasoning_tokens": getattr(chunk.usage.completion_tokens_details, 'reasoning_tokens', 0),
                                "accepted_prediction_tokens": getattr(chunk.usage.completion_tokens_details, 'accepted_prediction_tokens', 0),
                                "rejected_prediction_tokens": getattr(chunk.usage.completion_tokens_details, 'rejected_prediction_tokens', 0)
                            }

                        usage_info = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens,
                            "completion_tokens_details": completion_details
                        }

                        self.logger.debug(f"Token usage update: {usage_info}")
                        self.usage_info.emit(usage_info)

                    # Emit system information
                    if hasattr(chunk, 'system_fingerprint'):
                        system_info = {
                            "system_fingerprint": chunk.system_fingerprint,
                            "model": chunk.model
                        }
                        self.logger.debug(f"System info: {system_info}")
                        self.system_info.emit(system_info)

                    # Handle content chunks
                    if chunk.choices and len(chunk.choices) > 0:
                        choice = chunk.choices[0]

                        # For content delta
                        if hasattr(choice.delta, 'content') and choice.delta.content:
                            content = choice.delta.content
                            full_response += content
                            self.chunk_received.emit(content)

                            # Auto-detect reasoning steps for o1 models or explicit steps
                            if self._is_reasoning_step(content):
                                step_name = self._extract_step_name(content)
                                self.logger.debug(f"Detected reasoning step: {step_name}")
                                self.thinking_step.emit(step_name, content)

                self.logger.info(f"Completed streaming response ({len(full_response)} chars)")
                # Emit the full message at the end only for reference
                # In streaming mode, we don't use this for UI updates to avoid duplication
                self.message_received.emit(full_response)
            else:
                # Non-streaming mode
                self.logger.debug("Starting non-streaming request")
                response = client.chat.completions.create(**params)

                # Save and emit completion ID if available
                if hasattr(response, 'id'):
                    completion_id = response.id
                    self.logger.debug(f"Received completion ID: {completion_id}")
                    self.completion_id.emit(completion_id)

                # Get the content from the response
                content = response.choices[0].message.content
                self.logger.info(f"Received non-streaming response ({len(content)} chars)")
                self.message_received.emit(content)

                # Emit usage information
                if hasattr(response, 'usage'):
                    completion_details = {}
                    if hasattr(response.usage, 'completion_tokens_details'):
                        completion_details = {
                            "reasoning_tokens": getattr(response.usage.completion_tokens_details, 'reasoning_tokens', 0),
                            "accepted_prediction_tokens": getattr(response.usage.completion_tokens_details, 'accepted_prediction_tokens', 0),
                            "rejected_prediction_tokens": getattr(response.usage.completion_tokens_details, 'rejected_prediction_tokens', 0)
                        }

                    usage_info = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                        "completion_tokens_details": completion_details
                    }

                    self.logger.debug(f"Token usage: {usage_info}")
                    self.usage_info.emit(usage_info)

                # Emit system information
                if hasattr(response, 'system_fingerprint'):
                    system_info = {
                        "system_fingerprint": response.system_fingerprint,
                        "model": response.model
                    }
                    self.logger.debug(f"System info: {system_info}")
                    self.system_info.emit(system_info)

        except Exception as e:
            error_message = str(e)
            self.logger.error(f"API request failed: {error_message}", exc_info=True)
            self.error_occurred.emit(error_message)

    def prepare_messages(self, messages):
        """Prepare messages for API call, including file attachments"""
        self.logger.debug(f"Preparing {len(messages)} messages for API call")
        prepared_messages = []

        for message in messages:
            prepared_message = {
                "role": message["role"],
                "content": message["content"]
            }

            # Check for attachments
            if "attached_files" in message and message["attached_files"]:
                file_count = len(message["attached_files"])
                self.logger.debug(f"Processing {file_count} attached files for message")
                # For messages with attachments, include file content
                file_contents = []

                for file_info in message["attached_files"]:
                    file_name = file_info["file_name"]
                    file_content = file_info["content"]
                    token_count = file_info.get("token_count", "unknown")

                    self.logger.debug(f"Attaching file: {file_name} ({token_count} tokens)")

                    # Add file content to the message
                    file_contents.append(f"\n\n```{file_name}\n{file_content}\n```")

                # Append file contents to the message content
                if file_contents:
                    # Ensure there's a visual separator
                    if not prepared_message["content"].endswith("\n\n"):
                        prepared_message["content"] += "\n\n"
                    prepared_message["content"] += "Attached files:\n" + "\n".join(file_contents)

            prepared_messages.append(prepared_message)

        return prepared_messages

    def _is_reasoning_step(self, content: str) -> bool:
        """Detect if a chunk appears to be a reasoning step"""
        content_strip = content.strip()
        return (
                content_strip.startswith("Step ") or
                content_strip.startswith("Let's think") or
                content_strip.startswith("I'll solve") or
                content_strip.startswith("Let me think") or
                content_strip.startswith("First, I")
        )

    def _extract_step_name(self, content: str) -> str:
        """Extract a step name from content if possible"""
        content_strip = content.strip()
        if content_strip.startswith("Step "):
            try:
                return content_strip.split('\n')[0].strip()
            except:
                pass
        return "Reasoning"