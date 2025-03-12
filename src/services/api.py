"""
API services for interacting with the OpenAI API.
"""

from typing import Dict, List, Optional, Any, Callable
from PyQt6.QtCore import QThread, pyqtSignal, QObject, pyqtSlot

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from src.utils import REASONING_MODELS
from src.utils.logging_utils import get_logger, log_exception

# Get a logger for this module
logger = get_logger(__name__)


class OpenAIThreadManager:
    """Manager for OpenAI API worker threads"""

    def __init__(self):
        self.active_threads = {}  # Map of thread IDs to (thread, worker) tuples
        self.logger = get_logger(f"{__name__}.OpenAIThreadManager")

    def create_worker(self, messages, settings):
        """Create a worker thread for API calls and return connection endpoints"""
        # Create thread and worker
        thread = QThread()
        worker = OpenAIAPIWorker(messages, settings)

        # Move worker to thread
        worker.moveToThread(thread)

        # Connect thread signals
        thread.started.connect(worker.process)
        worker.worker_finished.connect(thread.quit)
        worker.worker_finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Store references
        thread_id = id(thread)
        self.active_threads[thread_id] = (thread, worker)

        # Set up cleanup when thread finishes
        thread.finished.connect(lambda: self._cleanup_thread(thread_id))

        return thread_id, worker

    def start_worker(self, thread_id):
        """Start the worker thread"""
        if thread_id in self.active_threads:
            thread, _ = self.active_threads[thread_id]
            thread.start()
            return True
        return False

    def cancel_worker(self, thread_id):
        """Cancel an active worker with improved cleanup"""
        if thread_id in self.active_threads:
            thread, worker = self.active_threads[thread_id]

            # Mark worker for cancellation
            worker.cancel()

            # Set a timeout for the thread to finish gracefully
            if thread.isRunning():
                if not thread.wait(3000):  # 3 second timeout
                    self.logger.warning(f"Thread {thread_id} did not finish in time, forcing quit")
                    thread.terminate()  # Force termination as last resort

            # Clean up references immediately
            self._cleanup_thread(thread_id)
            return True
        return False

    def cancel_all(self):
        """Cancel all active workers"""
        for thread_id in list(self.active_threads.keys()):
            self.cancel_worker(thread_id)

    def _cleanup_thread(self, thread_id):
        """Remove thread references when thread completes"""
        if thread_id in self.active_threads:
            del self.active_threads[thread_id]
            self.logger.debug(f"Thread {thread_id} cleaned up, {len(self.active_threads)} active threads remaining")


class OpenAIAPIWorker(QObject):
    """Worker object for making OpenAI API calls using either the Responses or Chat Completions API"""
    message_received = pyqtSignal(str)  # Full final message
    chunk_received = pyqtSignal(str)  # Streaming chunks
    thinking_step = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    usage_info = pyqtSignal(dict)
    system_info = pyqtSignal(dict)
    completion_id = pyqtSignal(str)
    reasoning_steps = pyqtSignal(list)
    worker_finished = pyqtSignal()

    def __init__(self, messages, settings):
        super().__init__()
        self.messages = messages
        self.settings = settings
        self.logger = get_logger(f"{__name__}.OpenAIAPIWorker")
        self.collected_reasoning_steps = []
        self._is_cancelled = False
        self._current_text_content = ""  # To accumulate text during streaming

    @pyqtSlot()
    def process(self):
        """Execute the API call when the thread starts"""
        try:
            api_key = self.settings.get("api_key")
            api_base = self.settings.get("api_base")
            model = self.settings.get("model")
            api_type = self.settings.get("api_type", "responses")  # Get API type

            # Log which model and API type we're using
            self.logger.info(f"Using model: {model} with API type: {api_type}")

            client_kwargs = {}
            if api_key:
                client_kwargs["api_key"] = api_key
            if api_base:
                client_kwargs["base_url"] = api_base

            client = OpenAI(**client_kwargs)

            # Prepare parameters based on selected API type
            if api_type == "responses":
                params = self._prepare_response_api_params(model)
            else:
                params = self._prepare_chat_completions_params(model)

            # Check for cancellation before making the request
            if self._is_cancelled:
                self.logger.info("API request cancelled before execution")
                self.worker_finished.emit()
                return

            try:
                # Handle streaming vs non-streaming
                if params.get("stream", False):
                    # Make streaming request based on API type
                    if api_type == "responses":
                        stream = client.responses.create(**params)
                        self._handle_streaming_response(stream, api_type)
                    else:
                        stream = client.chat.completions.create(**params)
                        self._handle_streaming_response(stream, api_type)
                else:
                    # Make non-streaming request based on API type
                    if api_type == "responses":
                        response = client.responses.create(**params)
                        self._handle_full_response(response, api_type)
                    else:
                        response = client.chat.completions.create(**params)
                        self._handle_full_response(response, api_type)
            except Exception as e:
                # Log the error for debugging
                self.logger.error(f"API request failed: {str(e)}")
                self.error_occurred.emit(str(e))

        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            # Signal completion
            self.worker_finished.emit()

    #########NEW CODE###########
    def _prepare_response_api_params(self, model):
        """Prepare parameters for the Response API"""
        # Process messages for the Response API format
        prepared_input = self.prepare_input(self.messages, "responses")

        # Extract model parameters from settings for Response API
        params = {
            "model": model,
            "input": prepared_input,
            "temperature": self.settings.get("temperature"),
            "top_p": self.settings.get("top_p"),
            "stream": self.settings.get("stream", True),
        }

        # Add response format if specified (now under 'text' parameter)
        if "text" in self.settings and "format" in self.settings["text"]:
            params["text"] = self.settings["text"]
        elif "response_format" in self.settings:
            format_type = self.settings.get("response_format", {}).get("type", "text")
            params["text"] = {"format": {"type": format_type}}

        # Add max_output_tokens parameter
        if "max_completion_tokens" in self.settings:
            params["max_output_tokens"] = self.settings.get("max_completion_tokens")
        elif "max_tokens" in self.settings:
            params["max_output_tokens"] = self.settings.get("max_tokens")

        # Add reasoning configuration for o1/o3 models
        is_reasoning_model = model in REASONING_MODELS
        if is_reasoning_model and "reasoning" in self.settings:
            params["reasoning"] = self.settings["reasoning"]
        elif is_reasoning_model:
            reasoning_effort = self.settings.get("reasoning_effort", "medium")
            params["reasoning"] = {"effort": reasoning_effort}

        # Add seed if specified
        if self.settings.get("seed") is not None:
            params["seed"] = self.settings.get("seed")

        # Add store parameter if specified
        if "store" in self.settings:
            params["store"] = self.settings.get("store")

            # Add metadata if present and store is enabled
            if self.settings.get("metadata") and len(self.settings.get("metadata")) > 0:
                params["metadata"] = self.settings.get("metadata")

        # Add system instructions if available (from system message)
        system_message = next((msg for msg in self.messages if msg["role"] == "system"), None)
        if system_message:
            params["instructions"] = system_message["content"]

        return params

    def _prepare_chat_completions_params(self, model):
        """Prepare parameters for the Chat Completions API"""
        # Process messages for the Chat API format
        prepared_messages = self.prepare_input(self.messages, "chat_completions")

        # Extract model parameters from settings for Chat API
        params = {
            "model": model,
            "messages": prepared_messages,
            "temperature": self.settings.get("temperature"),
            "top_p": self.settings.get("top_p"),
            "stream": self.settings.get("stream", True),
        }

        # Add response format if specified
        if "response_format" in self.settings:
            format_type = self.settings.get("response_format", {}).get("type", "text")
            params["response_format"] = {"type": format_type}

        # Add max_tokens parameter
        if "max_completion_tokens" in self.settings:
            params["max_tokens"] = self.settings.get("max_completion_tokens")
        elif "max_tokens" in self.settings:
            params["max_tokens"] = self.settings.get("max_tokens")

        # Add seed if specified
        if self.settings.get("seed") is not None:
            params["seed"] = self.settings.get("seed")

        return params

    #########END BLOCK ADD###########

    def _handle_streaming_response(self, stream, api_type="responses"):
        """Handle streaming response from either API"""
        full_text = ""

        try:
            self.logger.info(f"Starting to process streaming response from {api_type} API")

            if api_type == "responses":
                # Handle Response API streaming
                for event in stream:
                    # Check for cancellation during streaming
                    if self._is_cancelled:
                        self.logger.info("API request cancelled during streaming")
                        break

                    # Process various event types
                    event_type = getattr(event, 'type', None)
                    if not event_type:
                        self.logger.warning("Received event with no type, skipping")
                        continue

                    # Handle response.created event
                    if event_type == "response.created":
                        response_id = getattr(event.response, 'id', None)
                        if response_id:
                            self.completion_id.emit(response_id)

                    # Handle text deltas - these are the actual content chunks
                    elif event_type == "response.output_text.delta":
                        # Get the delta text and emit it
                        delta = getattr(event, 'delta', '')
                        if delta:
                            self._current_text_content += delta
                            full_text += delta
                            self.chunk_received.emit(delta)

                    # Handle reasoning steps (for o1/o3 models)
                    elif event_type == "response.thinking_step.added" or (hasattr(event, 'thinking') and event.thinking):
                        # Extract thinking step info
                        if hasattr(event, 'thinking') and event.thinking:
                            thinking_info = event.thinking

                            if isinstance(thinking_info, dict):
                                step_name = thinking_info.get("step", "Reasoning")
                                step_content = thinking_info.get("content", "")
                            else:
                                step_name = getattr(thinking_info, "step", "Reasoning")
                                step_content = getattr(thinking_info, "content", "")
                        elif hasattr(event, 'step'):
                            if isinstance(event.step, dict):
                                step_name = event.step.get("name", "Reasoning")
                                step_content = event.step.get("content", "")
                            else:
                                step_name = getattr(event.step, "name", "Reasoning")
                                step_content = getattr(event.step, "content", "")
                        else:
                            step_name = "Reasoning"
                            step_content = str(event)

                        self.collected_reasoning_steps.append({
                            "name": step_name,
                            "content": step_content
                        })
                        self.thinking_step.emit(step_name, step_content)

                    # Handle completed response
                    elif event_type == "response.completed":
                        self._handle_completed_event(event)

            else:
                # Handle Chat Completions API streaming
                for chunk in stream:
                    # Check for cancellation
                    if self._is_cancelled:
                        self.logger.info("API request cancelled during streaming")
                        break

                    # Get delta content from the chunk
                    delta_content = ""
                    if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                        choice = chunk.choices[0]
                        if hasattr(choice, 'delta') and hasattr(choice.delta, 'content'):
                            delta_content = choice.delta.content or ""

                    # Emit the chunk if it has content
                    if delta_content:
                        self._current_text_content += delta_content
                        full_text += delta_content
                        self.chunk_received.emit(delta_content)

                    # Check for completion (finish_reason is present)
                    if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                        choice = chunk.choices[0]
                        if choice.finish_reason is not None:
                            # Emit completion ID if available
                            if hasattr(chunk, 'id'):
                                self.completion_id.emit(chunk.id)

                            # Emit usage info if available in the final chunk
                            if hasattr(chunk, 'usage'):
                                usage_data = self._normalize_token_usage(
                                    {
                                        "prompt_tokens": chunk.usage.prompt_tokens,
                                        "completion_tokens": chunk.usage.completion_tokens,
                                        "total_tokens": chunk.usage.total_tokens
                                    },
                                    "chat_completions"
                                )
                                self.usage_info.emit(usage_data)

                            # Emit model info
                            model_info = {"model": getattr(chunk, "model", "unknown")}
                            self.system_info.emit(model_info)

            # Emit the full content at the end
            if full_text:
                self.message_received.emit(full_text)
            else:
                # Emit empty message to ensure completion
                self.message_received.emit("")

            # Emit reasoning steps if collected
            if self.collected_reasoning_steps:
                self.reasoning_steps.emit(self.collected_reasoning_steps)

        except Exception as e:
            self.logger.error(f"Error handling streaming response: {str(e)}")
            self.error_occurred.emit(f"Streaming error: {str(e)}")

    def _handle_full_response(self, response, api_type="responses"):
        """Handle non-streaming response from either API"""
        try:
            content = ""

            if api_type == "responses":
                # Extract content from Response API
                for output_item in response.output:
                    if output_item.type == "message" and output_item.role == "assistant":
                        for content_part in output_item.content:
                            if content_part.type == "output_text":
                                content = content_part.text
                                break

                # Extract reasoning steps if available
                if hasattr(response, "reasoning") and response.reasoning:
                    if hasattr(response.reasoning, "summary") and response.reasoning.summary:
                        self.collected_reasoning_steps.append({
                            "name": "Reasoning Summary",
                            "content": response.reasoning.summary
                        })

                # Emit completion ID
                self.completion_id.emit(response.id)

                # Emit usage information
                if hasattr(response, "usage"):
                    usage_data = self._normalize_token_usage(
                        {
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                            "total_tokens": response.usage.total_tokens,
                            "output_tokens_details": getattr(response.usage, "output_tokens_details", None)
                        },
                        "responses"
                    )
                    self.usage_info.emit(usage_data)

                # Emit system information
                model_info = {"model": response.model}
                self.system_info.emit(model_info)

            else:
                # Extract content from Chat Completions API
                if hasattr(response, 'choices') and len(response.choices) > 0:
                    content = response.choices[0].message.content or ""

                # Emit completion ID
                if hasattr(response, 'id'):
                    self.completion_id.emit(response.id)

                # Emit usage information
                if hasattr(response, 'usage'):
                    usage_data = self._normalize_token_usage(
                        {
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens
                        },
                        "chat_completions"
                    )
                    self.usage_info.emit(usage_data)

                # Emit system information
                model_info = {"model": response.model}
                self.system_info.emit(model_info)

            # Emit the content
            if content:
                self.message_received.emit(content)

            # Emit reasoning steps if collected
            if self.collected_reasoning_steps:
                self.reasoning_steps.emit(self.collected_reasoning_steps)

        except Exception as e:
            self.logger.error(f"Error handling full response: {str(e)}")
            self.error_occurred.emit(f"Response processing error: {str(e)}")

        except Exception as e:
            self.logger.error(f"Error handling full response: {str(e)}")
            self.error_occurred.emit(f"Response processing error: {str(e)}")

    def cancel(self):
        """Mark the worker for cancellation"""
        self._is_cancelled = True
        self.logger.info("Worker marked for cancellation")

    #########NEW CODE###########
    #########NEW CODE###########
    def _handle_completed_event(self, event):
        """Handle completion event for Response API streaming"""
        # Emit usage information if available
        if hasattr(event, "response"):
            response_data = event.response

            # Handle dictionary-style or attribute-style response object
            if isinstance(response_data, dict):
                # Dictionary access
                if "usage" in response_data:
                    usage = response_data["usage"]
                    usage_data = self._normalize_token_usage(usage, "responses")
                    self.usage_info.emit(usage_data)

                # Emit system information
                model_info = {
                    "model": response_data.get("model", "unknown")
                }
                self.system_info.emit(model_info)
            else:
                # Attribute access (original approach)
                if hasattr(response_data, "usage"):
                    usage = response_data.usage
                    usage_data = self._normalize_token_usage(
                        {
                            "input_tokens": getattr(usage, "input_tokens", 0),
                            "output_tokens": getattr(usage, "output_tokens", 0),
                            "total_tokens": getattr(usage, "total_tokens", 0),
                            "output_tokens_details": getattr(usage, "output_tokens_details", None)
                        },
                        "responses"
                    )
                    self.usage_info.emit(usage_data)

                # Emit system information
                model_info = {
                    "model": getattr(response_data, "model", "unknown")
                }
                self.system_info.emit(model_info)

    #########END BLOCK ADD##########
    #########END BLOCK ADD###########
    #########NEW CODE###########
    def _normalize_token_usage(self, usage, api_type="responses"):
        """Normalize token usage data to a consistent format regardless of API type"""
        normalized = {}

        if api_type == "responses":
            normalized["prompt_tokens"] = usage.get("input_tokens", 0)
            normalized["completion_tokens"] = usage.get("output_tokens", 0)
            normalized["total_tokens"] = usage.get("total_tokens", 0)

            # Include reasoning tokens if available
            if "output_tokens_details" in usage and usage["output_tokens_details"]:
                details = usage["output_tokens_details"]
                normalized["completion_tokens_details"] = {
                    "reasoning_tokens": details.get("reasoning_tokens", 0)
                }
        else:
            normalized["prompt_tokens"] = usage.get("prompt_tokens", 0)
            normalized["completion_tokens"] = usage.get("completion_tokens", 0)
            normalized["total_tokens"] = usage.get("total_tokens", 0)

        return normalized

    #########END BLOCK ADD###########

    def prepare_input(self, messages, api_type="responses"):
        """
        Prepare messages for the API format based on api_type

        Args:
            messages: The raw messages
            api_type: Either "responses" or "chat_completions"

        Returns:
            Formatted input for the specified API
        """
        if api_type == "responses":
            # Format for Response API - combine into text
            all_content = []

            for message in messages:
                # Skip system messages as they will be handled as 'instructions'
                if message["role"] == "system":
                    continue

                role_prefix = ""
                if message["role"] == "user":
                    role_prefix = "User: "
                elif message["role"] == "assistant":
                    role_prefix = "Assistant: "

                # Add message content
                if "content" in message:
                    all_content.append(f"{role_prefix}{message['content']}")

                # Handle file attachments if present
                if "attached_files" in message and message["attached_files"]:
                    file_sections = ["\n\n# ATTACHED FILES"]

                    for file_info in message["attached_files"]:
                        file_name = file_info["file_name"]
                        file_type = file_info.get("mime_type", "Unknown type")
                        file_size = file_info.get("size", 0)
                        file_content = file_info["content"]

                        file_sections.append(f"""
                        ### FILE: {file_name}
                        {file_content}
                        Copy""")

                    all_content.append("\n".join(file_sections))

            # Return the combined text as the input
            return "\n\n".join(all_content)
        else:
            # Format for Chat Completions API - as message objects
            prepared_messages = []

            for message in messages:
                # Clone the message with only the necessary fields
                prepared_message = {
                    "role": message["role"],
                    "content": message["content"]
                }

                # Handle file attachments if present
                if "attached_files" in message and message["attached_files"]:
                    file_content = "\n\n# ATTACHED FILES\n"

                    for file_info in message["attached_files"]:
                        file_name = file_info["file_name"]
                        file_content += f"\n### FILE: {file_name}\n{file_info['content']}\n"

                    # Append file content to message content
                    prepared_message["content"] += file_content

                prepared_messages.append(prepared_message)

            return prepared_messages



    def _get_file_extension(self, filename):
        """Extract extension from filename for syntax highlighting"""
        try:
            ext = filename.split('.')[-1].lower()
            # Map common extensions to language names for syntax highlighting
            extension_map = {
                'py': 'python',
                'js': 'javascript',
                'ts': 'typescript',
                'html': 'html',
                'css': 'css',
                'java': 'java',
                'c': 'c',
                'cpp': 'cpp',
                'h': 'cpp',
                'json': 'json',
                'md': 'markdown',
                'txt': '',  # No specific highlighting
                'csv': '',
                'sh': 'bash',
                'sql': 'sql',
                'xml': 'xml',
                'yml': 'yaml',
                'yaml': 'yaml'
            }
            return extension_map.get(ext, '')
        except IndexError:
            return ''  # If no extension is found

    def _extract_step_name(self, content: str) -> str:
        """Extract a step name from content if possible"""
        content_strip = content.strip()
        if content_strip.startswith("Step "):
            try:
                return content_strip.split('\n')[0].strip()
            except:
                pass
        return "Reasoning"

    def _is_reasoning_step(self, content: str) -> bool:
        """
        Detect if a chunk appears to be a reasoning step
        Enhanced to handle more reasoning patterns
        """
        content_strip = content.strip()
        return (
                content_strip.startswith("Step ") or
                content_strip.startswith("Let's think") or
                content_strip.startswith("I'll solve") or
                content_strip.startswith("Let me think") or
                content_strip.startswith("First, I") or
                content_strip.startswith("**Solution:") or
                content_strip.startswith("**Step") or
                content_strip.startswith("**Puzzle:")
        )
