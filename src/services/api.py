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
            api_key = self.settings.get("api_key")
            api_base = self.settings.get("api_base")
            model = self.settings.get("model")

            # Log which model we're using
            self.logger.info(f"Using model: {model}")

            client_kwargs = {}
            if api_key:
                client_kwargs["api_key"] = api_key
            if api_base:
                client_kwargs["base_url"] = api_base

            client = OpenAI(**client_kwargs)

            # Process messages to include file content and handle model-specific requirements
            processed_messages = self.prepare_messages(self.messages)

            # Extract model parameters from settings
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
            elif "max_tokens" in self.settings:
                # For backward compatibility
                params["max_tokens"] = self.settings.get("max_tokens")

            # Add response format if specified
            if "response_format" in self.settings:
                params["response_format"] = self.settings.get("response_format")

            # Add reasoning effort for o1/o3 models
            is_reasoning_model = model in REASONING_MODELS
            if is_reasoning_model:
                self.logger.info(f"Using reasoning model: {model}")

            # Add seed if specified
            if self.settings.get("seed") is not None:
                params["seed"] = self.settings.get("seed")

            # Add service tier if specified
            if self.settings.get("service_tier"):
                params["service_tier"] = self.settings.get("service_tier")

            # Add store parameter if specified
            if self.settings.get("store"):
                params["store"] = True

                # Add metadata if present and store is enabled
                if self.settings.get("metadata") and len(self.settings.get("metadata")) > 0:
                    params["metadata"] = self.settings.get("metadata")
                # Note: metadata can only be included when store=True

            # Set up streaming options if needed
            if params["stream"]:
                params["stream_options"] = {"include_usage": True}

            try:
                if params["stream"]:
                    # Streaming mode
                    full_response = ""
                    stream = client.chat.completions.create(**params)

                    # Store the completion ID if available
                    if hasattr(stream, 'id'):
                        self.completion_id.emit(stream.id)

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

                            self.usage_info.emit({
                                "prompt_tokens": chunk.usage.prompt_tokens,
                                "completion_tokens": chunk.usage.completion_tokens,
                                "total_tokens": chunk.usage.total_tokens,
                                "completion_tokens_details": completion_details
                            })

                        # Emit system information
                        if hasattr(chunk, 'system_fingerprint'):
                            self.system_info.emit({
                                "system_fingerprint": chunk.system_fingerprint,
                                "model": chunk.model
                            })

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
                                    self.thinking_step.emit(step_name, content)

                    # Emit the full message at the end only for reference
                    # In streaming mode, we don't use this for UI updates to avoid duplication
                    self.message_received.emit(full_response)
                else:
                    # Non-streaming mode
                    response = client.chat.completions.create(**params)

                    # Save and emit completion ID if available
                    if hasattr(response, 'id'):
                        self.completion_id.emit(response.id)

                    # Get the content from the response
                    content = response.choices[0].message.content
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

                        self.usage_info.emit({
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens,
                            "completion_tokens_details": completion_details
                        })

                    # Emit system information
                    if hasattr(response, 'system_fingerprint'):
                        self.system_info.emit({
                            "system_fingerprint": response.system_fingerprint,
                            "model": response.model
                        })
            except Exception as e:
                # Log the error for debugging
                self.logger.error(f"API request failed: {str(e)}")
                if hasattr(e, '__traceback__'):
                    import traceback
                    traceback.print_tb(e.__traceback__)
                self.error_occurred.emit(str(e))

        except Exception as e:
            self.error_occurred.emit(str(e))

    def prepare_messages(self, messages):
        """Prepare messages for API call, including file attachments and handling model-specific requirements"""
        prepared_messages = []
        model = self.settings.get("model", "")

        # Check if this is a reasoning model
        is_reasoning_model = model in REASONING_MODELS

        for message in messages:
            if is_reasoning_model:
                # For reasoning models, only user and assistant roles are supported
                if message["role"] in ["system", "developer"]:
                    # Convert system or developer messages to user messages
                    prepared_message = {
                        "role": "user",
                        "content": f"[System Instruction] {message['content']}"
                    }
                    self.logger.info(f"Converting '{message['role']}' role to 'user' for reasoning model")
                else:
                    prepared_message = {
                        "role": message["role"],
                        "content": message["content"]
                    }
            else:
                # Standard handling for GPT models
                prepared_message = {
                    "role": message["role"],
                    "content": message["content"]
                }

            # Check for attachments
            if "attached_files" in message and message["attached_files"]:
                # For messages with attachments, include file content
                file_contents = []

                for file_info in message["attached_files"]:
                    file_name = file_info["file_name"]
                    file_content = file_info["content"]

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
