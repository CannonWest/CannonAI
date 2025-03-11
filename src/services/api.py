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
        worker = OpenAIResponseWorker(messages, settings)

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


class OpenAIResponseWorker(QObject):
    """Worker object for making OpenAI API calls using the Responses API"""
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
        self.logger = get_logger(f"{__name__}.OpenAIResponseWorker")
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

            # Log which model we're using
            self.logger.info(f"Using model: {model}")

            client_kwargs = {}
            if api_key:
                client_kwargs["api_key"] = api_key
            if api_base:
                client_kwargs["base_url"] = api_base

            client = OpenAI(**client_kwargs)

            # Process messages for the new format
            prepared_input = self.prepare_input(self.messages)

            # Extract model parameters from settings for Response API
            params = {
                "model": model,
                "input": prepared_input,
                "temperature": self.settings.get("temperature"),
                "top_p": self.settings.get("top_p"),
                "stream": self.settings.get("stream", True),
            }

            # Add response format if specified (now under 'text' parameter)
            if "response_format" in self.settings:
                format_type = self.settings.get("response_format", {}).get("type", "text")
                params["text"] = {"format": {"type": format_type}}

            # Add max_output_tokens parameter
            if "max_completion_tokens" in self.settings:
                params["max_output_tokens"] = self.settings.get("max_completion_tokens")
            elif "max_tokens" in self.settings:
                params["max_output_tokens"] = self.settings.get("max_tokens")

            # Add reasoning configuration for o1/o3 models
            is_reasoning_model = model in REASONING_MODELS
            if is_reasoning_model:
                self.logger.info(f"Using reasoning model: {model}")
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

            # Check for cancellation before making the request
            if self._is_cancelled:
                self.logger.info("API request cancelled before execution")
                self.worker_finished.emit()
                return

            try:
                # Handle streaming vs non-streaming
                if params["stream"]:
                    # Make streaming request (stream is already in params, don't pass it again)
                    stream = client.responses.create(**params)
                    self._handle_streaming_response(stream)
                else:
                    # Make non-streaming request
                    response = client.responses.create(**params)
                    self._handle_full_response(response)
            except Exception as e:
                # Log the error for debugging
                self.logger.error(f"API request failed: {str(e)}")
                self.error_occurred.emit(str(e))

        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            # Signal completion
            self.worker_finished.emit()

    def _handle_streaming_response(self, stream):
        """Handle streaming response from the Response API"""
        full_text = ""

        try:
            self.logger.info("Starting to process streaming response")
            for event in stream:
                # Check for cancellation during streaming
                if self._is_cancelled:
                    self.logger.info("API request cancelled during streaming")
                    break

                # Detailed debug for each event
                self.logger.debug(f"Received event type: {getattr(event, 'type', 'unknown')}")

                # Process various event types
                event_type = getattr(event, 'type', None)
                if not event_type:
                    self.logger.warning("Received event with no type, skipping")
                    continue

                # Handle response.created event
                if event_type == "response.created":
                    self.logger.info("Response created event received")
                    response_id = getattr(event.response, 'id', None)
                    if response_id:
                        self.completion_id.emit(response_id)
                    else:
                        self.logger.warning("Response created event missing response ID")

                # Handle text deltas - these are the actual content chunks
                elif event_type == "response.output_text.delta":
                    # Get the delta text and emit it
                    delta = getattr(event, 'delta', '')
                    if delta:
                        self.logger.debug(f"Received delta: {delta[:20]}...")  # Log first 20 chars
                        self._current_text_content += delta
                        full_text += delta
                        self.chunk_received.emit(delta)
                    else:
                        self.logger.debug("Received empty delta text")

                # Handle reasoning steps (for o1/o3 models)
                elif event_type == "response.thinking_step.added" or (hasattr(event, 'thinking') and event.thinking):
                    # First handle when 'thinking' is a direct attribute
                    if hasattr(event, 'thinking') and event.thinking:
                        thinking_info = event.thinking
                        self.logger.info("Received thinking step from direct attribute")

                        # Handle different thinking info structures
                        if isinstance(thinking_info, dict):
                            step_name = thinking_info.get("step", "Reasoning")
                            step_content = thinking_info.get("content", "")
                        else:
                            step_name = getattr(thinking_info, "step", "Reasoning")
                            step_content = getattr(thinking_info, "content", "")

                    # Then handle thinking_step specific events
                    elif hasattr(event, 'step'):
                        self.logger.info("Received thinking_step.added event")

                        if isinstance(event.step, dict):
                            step_name = event.step.get("name", "Reasoning")
                            step_content = event.step.get("content", "")
                        else:
                            step_name = getattr(event.step, "name", "Reasoning")
                            step_content = getattr(event.step, "content", "")
                    else:
                        # Fallback if structure is unexpected
                        self.logger.warning("Received thinking event with unexpected structure")
                        step_name = "Reasoning"
                        step_content = str(event)

                    self.logger.info(f"Processing thinking step: {step_name}")
                    self.collected_reasoning_steps.append({
                        "name": step_name,
                        "content": step_content
                    })
                    self.thinking_step.emit(step_name, step_content)

                # Handle completed response
                elif event_type == "response.completed":
                    # Emit usage information if available
                    if hasattr(event, "response"):
                        response_data = event.response

                        # Handle dictionary-style or attribute-style response object
                        if isinstance(response_data, dict):
                            # Dictionary access
                            if "usage" in response_data:
                                usage = response_data["usage"]
                                usage_data = {
                                    "prompt_tokens": usage.get("input_tokens", 0),
                                    "completion_tokens": usage.get("output_tokens", 0),
                                    "total_tokens": usage.get("total_tokens", 0)
                                }

                                # Add completion tokens details if available
                                if "output_tokens_details" in usage:
                                    details = usage["output_tokens_details"]
                                    usage_data["completion_tokens_details"] = {
                                        "reasoning_tokens": details.get("reasoning_tokens", 0)
                                    }

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
                                usage_data = {
                                    "prompt_tokens": getattr(usage, "input_tokens", 0),
                                    "completion_tokens": getattr(usage, "output_tokens", 0),
                                    "total_tokens": getattr(usage, "total_tokens", 0)
                                }

                                # Add completion tokens details if available
                                if hasattr(usage, "output_tokens_details"):
                                    details = usage.output_tokens_details
                                    usage_data["completion_tokens_details"] = {
                                        "reasoning_tokens": getattr(details, "reasoning_tokens", 0)
                                    }

                                self.usage_info.emit(usage_data)

                            # Emit system information
                            model_info = {
                                "model": getattr(response_data, "model", "unknown")
                            }
                            self.system_info.emit(model_info)

            # At the end of _handle_streaming_response:
            # Emit additional completion logging
            self.logger.info(f"Stream processing complete, collected {len(full_text)} chars of content")
            self.logger.info(f"Collected {len(self.collected_reasoning_steps)} reasoning steps")

            # Emit the full content at the end
            if full_text:
                self.logger.info("Emitting complete message")
                self.message_received.emit(full_text)
            else:
                self.logger.warning("No content collected during streaming")
                # Emit empty message to ensure completion
                self.message_received.emit("")

            # Emit reasoning steps if collected
            if self.collected_reasoning_steps:
                self.logger.info("Emitting reasoning steps")
                self.reasoning_steps.emit(self.collected_reasoning_steps)
            else:
                self.logger.info("No reasoning steps to emit")

        except Exception as e:
            self.logger.error(f"Error handling streaming response: {str(e)}")
            self.error_occurred.emit(f"Streaming error: {str(e)}")

    def _handle_full_response(self, response):
        """Handle non-streaming response from the Response API"""
        try:
            # Extract the text content from the response
            content = ""

            # Find the text content in the output items
            for output_item in response.output:
                if output_item.type == "message" and output_item.role == "assistant":
                    for content_part in output_item.content:
                        if content_part.type == "output_text":
                            content = content_part.text
                            break

            # Emit the content
            if content:
                self.message_received.emit(content)

            # Extract and emit reasoning steps
            if hasattr(response, "reasoning") and response.reasoning:
                if hasattr(response.reasoning, "summary") and response.reasoning.summary:
                    self.collected_reasoning_steps.append({
                        "name": "Reasoning Summary",
                        "content": response.reasoning.summary
                    })

            # Emit reasoning steps if collected
            if self.collected_reasoning_steps:
                self.reasoning_steps.emit(self.collected_reasoning_steps)

            # Emit completion ID
            self.completion_id.emit(response.id)

            # Emit usage information
            if hasattr(response, "usage"):
                usage_data = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.total_tokens
                }

                # Add completion tokens details if available
                if hasattr(response.usage, "output_tokens_details"):
                    details = response.usage.output_tokens_details
                    usage_data["completion_tokens_details"] = {
                        "reasoning_tokens": getattr(details, "reasoning_tokens", 0)
                    }

                self.usage_info.emit(usage_data)

            # Emit system information
            model_info = {
                "model": response.model
            }
            self.system_info.emit(model_info)

        except Exception as e:
            self.logger.error(f"Error handling full response: {str(e)}")
            self.error_occurred.emit(f"Response processing error: {str(e)}")

    def cancel(self):
        """Mark the worker for cancellation"""
        self._is_cancelled = True
        self.logger.info("Worker marked for cancellation")

    def prepare_input(self, messages):
        """
        Prepare messages for the Response API format
        For Response API, 'input' can be a string or an array of message objects
        """
        # Simplest approach: combine all messages into a single prompt string
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
