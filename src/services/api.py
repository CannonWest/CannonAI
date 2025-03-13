"""
API services for interacting with the OpenAI API.
"""

from typing import Dict, List, Optional, Any, Callable
from PyQt6.QtCore import QThread, pyqtSignal, QObject, pyqtSlot

import openai
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
        try:
            # Make copies of input data to prevent shared state issues
            self.messages = list(messages) if messages else []
            self.settings = settings.copy() if settings else {}

            # Initialize logger
            self.logger = get_logger(f"{__name__}.OpenAIAPIWorker")

            # Initialize worker state
            self.collected_reasoning_steps = []
            self._is_cancelled = False
            self._current_text_content = ""  # To accumulate text during streaming

            # Add worker ID for debugging
            import uuid
            self._worker_id = str(uuid.uuid4())[:8]
            self.logger.debug(f"Worker {self._worker_id} initialized")

            # Set max content size to prevent memory issues
            self._max_content_size = 1024 * 1024  # 1MB limit

            # Initialize processing state
            self._is_processing = False
        except Exception as e:
            print(f"Error initializing API worker: {str(e)}")
            # Continue anyway, we'll handle errors in the process method

    @pyqtSlot()
    def process(self):
        """Execute the API call with memory safety and robust error handling"""
        # Prevent duplicate processing
        if self._is_processing:
            self.logger.warning(f"Worker {self._worker_id} already processing, ignoring duplicate call")
            return

        self._is_processing = True

        try:
            self.logger.info(f"Worker {self._worker_id} starting processing")

            # Check if we have valid input
            if not self.messages:
                raise ValueError("No messages provided")

            # Extract settings with defaults
            api_key = self.settings.get("api_key", "")
            api_base = self.settings.get("api_base", "")
            model = self.settings.get("model", "gpt-4o")
            api_type = self.settings.get("api_type", "responses")

            self.logger.info(f"Using model: {model} with API type: {api_type}")

            # Check for API key
            if not api_key:
                raise ValueError("No API key provided. Please check your settings.")

            # Create client with timeout
            client_kwargs = {
                "api_key": api_key,
                "timeout": 60.0  # 60 second timeout
            }

            if api_base:
                client_kwargs["base_url"] = api_base

            # Create client in a try block
            try:
                client = OpenAI(**client_kwargs)
            except Exception as client_error:
                self.logger.error(f"Error creating OpenAI client: {str(client_error)}")
                self.error_occurred.emit(f"Error initializing API client: {str(client_error)}")
                raise

            # Prepare parameters in a separate try block
            try:
                if api_type == "responses":
                    params = self._prepare_response_api_params(model)
                else:
                    params = self._prepare_chat_completions_params(model)

                # Limit max tokens to reasonable values to prevent memory issues
                if "max_tokens" in params and params["max_tokens"] > 16384:
                    self.logger.warning(f"Limiting max_tokens from {params['max_tokens']} to 16384")
                    params["max_tokens"] = 16384

                if "max_output_tokens" in params and params["max_output_tokens"] > 16384:
                    self.logger.warning(f"Limiting max_output_tokens from {params['max_output_tokens']} to 16384")
                    params["max_output_tokens"] = 16384
            except Exception as param_error:
                self.logger.error(f"Error preparing parameters: {str(param_error)}")
                self.error_occurred.emit(f"Error preparing request: {str(param_error)}")
                raise

            # Check for cancellation before making the request
            if self._is_cancelled:
                self.logger.info(f"Worker {self._worker_id} cancelled before execution")
                return

            # Import needed modules right before use
            import openai
            import gc

            # Execute API call with proper error handling
            try:
                # Handle streaming vs non-streaming
                streaming_mode = params.get("stream", False)

                if streaming_mode:
                    # Make streaming request
                    try:
                        if api_type == "responses":
                            stream = client.responses.create(**params)
                        else:
                            stream = client.chat.completions.create(**params)

                        # Stream is ready, process it with timeout protection
                        import threading
                        from PyQt6.QtCore import QTimer

                        # Set a timer to abort if streaming takes too long
                        self._stream_timeout = QTimer()
                        self._stream_timeout.setSingleShot(True)
                        self._stream_timeout.timeout.connect(self._handle_stream_timeout)
                        self._stream_timeout.start(60000)  # 60 second timeout

                        # Process the stream
                        self._handle_streaming_response(stream, api_type)

                        # Stop the timeout timer
                        self._stream_timeout.stop()

                    except Exception as stream_error:
                        # Classify and handle different types of errors
                        error_type = type(stream_error).__name__
                        error_msg = str(stream_error)

                        if hasattr(openai, 'BadRequestError') and isinstance(stream_error, openai.BadRequestError):
                            self.logger.error(f"Bad request error: {error_msg}")
                            self.error_occurred.emit(f"Bad request: {error_msg}")
                        elif hasattr(openai, 'RateLimitError') and isinstance(stream_error, openai.RateLimitError):
                            self.logger.error(f"Rate limit error: {error_msg}")
                            self.error_occurred.emit(f"Rate limit exceeded: {error_msg}")
                        elif hasattr(openai, 'APITimeoutError') and isinstance(stream_error, openai.APITimeoutError):
                            self.logger.error(f"API timeout: {error_msg}")
                            self.error_occurred.emit(f"Request timed out: {error_msg}")
                        elif hasattr(openai, 'APIConnectionError') and isinstance(stream_error, openai.APIConnectionError):
                            self.logger.error(f"API connection error: {error_msg}")
                            self.error_occurred.emit(f"Connection error: {error_msg}")
                        elif hasattr(openai, 'AuthenticationError') and isinstance(stream_error, openai.AuthenticationError):
                            self.logger.error(f"Authentication error: {error_msg}")
                            self.error_occurred.emit(f"Authentication failed: Please check your API key")
                        elif hasattr(openai, 'InternalServerError') and isinstance(stream_error, openai.InternalServerError):
                            self.logger.error(f"OpenAI server error: {error_msg}")
                            self.error_occurred.emit(f"OpenAI server error: Please try again later")
                        else:
                            self.logger.error(f"Unexpected error ({error_type}) during streaming: {error_msg}")
                            self.error_occurred.emit(f"Unexpected error: {error_msg}")
                else:
                    # Make non-streaming request with timeout protection
                    try:
                        if api_type == "responses":
                            response = client.responses.create(**params)
                        else:
                            response = client.chat.completions.create(**params)

                        self._handle_full_response(response, api_type)
                    except Exception as resp_error:
                        # Classify and handle different types of errors
                        error_type = type(resp_error).__name__
                        error_msg = str(resp_error)

                        if hasattr(openai, 'BadRequestError') and isinstance(resp_error, openai.BadRequestError):
                            self.logger.error(f"Bad request error: {error_msg}")
                            self.error_occurred.emit(f"Bad request: {error_msg}")
                        elif hasattr(openai, 'RateLimitError') and isinstance(resp_error, openai.RateLimitError):
                            self.logger.error(f"Rate limit error: {error_msg}")
                            self.error_occurred.emit(f"Rate limit exceeded: {error_msg}")
                        elif hasattr(openai, 'APITimeoutError') and isinstance(resp_error, openai.APITimeoutError):
                            self.logger.error(f"API timeout: {error_msg}")
                            self.error_occurred.emit(f"Request timed out: {error_msg}")
                        elif hasattr(openai, 'APIConnectionError') and isinstance(resp_error, openai.APIConnectionError):
                            self.logger.error(f"API connection error: {error_msg}")
                            self.error_occurred.emit(f"Connection error: {error_msg}")
                        elif hasattr(openai, 'AuthenticationError') and isinstance(resp_error, openai.AuthenticationError):
                            self.logger.error(f"Authentication error: {error_msg}")
                            self.error_occurred.emit(f"Authentication failed: Please check your API key")
                        elif hasattr(openai, 'InternalServerError') and isinstance(resp_error, openai.InternalServerError):
                            self.logger.error(f"OpenAI server error: {error_msg}")
                            self.error_occurred.emit(f"OpenAI server error: Please try again later")
                        else:
                            self.logger.error(f"Unexpected error ({error_type}) during request: {error_msg}")
                            self.error_occurred.emit(f"Unexpected error: {error_msg}")

            except Exception as api_error:
                self.logger.error(f"API request failed: {str(api_error)}")
                self.error_occurred.emit(f"API request failed: {str(api_error)}")

            # Force garbage collection after API calls
            gc.collect()

        except Exception as process_error:
            self.logger.error(f"Critical error in process method: {str(process_error)}")
            self.error_occurred.emit(f"Critical error: {str(process_error)}")

            # Log stack trace for debugging
            import traceback
            self.logger.error(f"Stack trace: {traceback.format_exc()}")
        finally:
            # Reset processing flag
            self._is_processing = False

            # Signal completion
            try:
                self.worker_finished.emit()
            except Exception as signal_error:
                self.logger.error(f"Error emitting worker finished signal: {str(signal_error)}")

            self.logger.info(f"Worker {self._worker_id} finished processing")

    def _prepare_response_api_params(self, model):
        """Prepare parameters for the Response API with cleaner parameter handling"""
        self.logger.debug(f"Settings for prepare_response_api_params: {self.settings}")

        # Process messages for the Response API format
        prepared_input = self.prepare_input(self.messages, "responses")

        # Base parameters (common across all API types)
        params = {
            "model": model,
            "input": prepared_input,
            "temperature": self.settings.get("temperature", 0.7),
            "top_p": self.settings.get("top_p", 1.0),
            "stream": self.settings.get("stream", True),
        }

        # Add Response API specific parameters
        if "store" in self.settings:
            params["store"] = self.settings.get("store")

        # Handle text format (response format)
        format_type = "text"  # default format type
        if self.settings.get("text") and isinstance(self.settings["text"], dict):
            params["text"] = self.settings["text"]
            # Extract format type for potential JSON handling
            if "format" in self.settings["text"] and isinstance(self.settings["text"]["format"], dict):
                format_type = self.settings["text"]["format"].get("type", "text")
        else:
            # Default text format
            params["text"] = {"format": {"type": "text"}}

        # For json_object format, ensure input contains JSON hint
        if format_type == "json_object" and "json" not in prepared_input.lower():
            if "instructions" in params:
                params["instructions"] += " Please provide the response in JSON format."
            else:
                # Try to extract system message
                system_message = next((msg for msg in self.messages if msg.get("role") == "system"), None)
                if system_message and isinstance(system_message, dict) and "content" in system_message:
                    params["instructions"] = system_message["content"] + " Please provide the response in JSON format."
                else:
                    params["instructions"] = "Please provide the response in JSON format."

        # Handle token limit - for Responses API, we always use max_output_tokens
        token_limit = self.settings.get("max_output_tokens", self.settings.get("max_tokens", 1024))
        params["max_output_tokens"] = token_limit

        # Add reasoning parameters for supported models
        if model in self.settings.get("reasoning_models", []) and "reasoning" in self.settings:
            params["reasoning"] = self.settings["reasoning"]

        # Add seed if specified
        if self.settings.get("seed") is not None:
            params["seed"] = self.settings.get("seed")

        # Add user identifier if present
        if self.settings.get("user") is not None:
            params["user"] = self.settings.get("user")

        # Add advanced parameters if present
        for param in ["metadata", "include", "previous_response_id", "parallel_tool_calls"]:
            if param in self.settings and self.settings[param] is not None:
                params[param] = self.settings[param]

        self.logger.debug(f"Final Responses API parameters: {params}")
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

    def _handle_streaming_response(self, stream, api_type="responses"):
        """Handle streaming response from either API with improved structure"""
        full_text = ""

        try:
            self.logger.info(f"Starting to process streaming response from {api_type} API")

            if api_type == "responses":
                # Track response metadata
                response_id = None
                model_info = {}

                # Process each event in the stream
                for event in stream:
                    # Check for cancellation
                    if self._is_cancelled:
                        self.logger.info("API request cancelled during streaming")
                        break

                    # Process by event type
                    event_type = getattr(event, 'type', None)

                    if not event_type:
                        continue

                    if event_type == "response.created":
                        # Capture response ID from creation event
                        if hasattr(event, 'response') and hasattr(event.response, 'id'):
                            response_id = event.response.id
                            self.completion_id.emit(response_id)

                    elif event_type == "response.output_text.delta":
                        # Process text delta (the actual content chunk)
                        delta = getattr(event, 'delta', '')
                        if delta:
                            self._current_text_content += delta
                            full_text += delta
                            self.chunk_received.emit(delta)

                    elif event_type in ["response.thinking_step.added", "response.thinking.added"]:
                        # Extract reasoning step information
                        step_info = self._extract_thinking_step(event)
                        if step_info:
                            step_name, step_content = step_info
                            self.collected_reasoning_steps.append({
                                "name": step_name,
                                "content": step_content
                            })
                            self.thinking_step.emit(step_name, step_content)

                    elif event_type == "response.completed":
                        # Process completion event (final usage stats, etc.)
                        if hasattr(event, 'response'):
                            self._process_completion_metadata(event.response)

                            # Store model information
                            if hasattr(event.response, 'model'):
                                model_info["model"] = event.response.model
                                self.system_info.emit(model_info)

            else:  # Chat Completions API
                for chunk in stream:
                    # Check for cancellation
                    if self._is_cancelled:
                        self.logger.info("API request cancelled during streaming")
                        break

                    # Extract content from the chunk
                    if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                        choice = chunk.choices[0]

                        # Process content delta
                        if hasattr(choice, 'delta') and hasattr(choice.delta, 'content'):
                            delta_content = choice.delta.content or ""
                            if delta_content:
                                self._current_text_content += delta_content
                                full_text += delta_content
                                self.chunk_received.emit(delta_content)

                        # Check for completion
                        if choice.finish_reason is not None:
                            # Emit completion ID
                            if hasattr(chunk, 'id'):
                                self.completion_id.emit(chunk.id)

                            # Process usage statistics
                            if hasattr(chunk, 'usage'):
                                self._process_chat_usage(chunk.usage)

                            # Process model info
                            if hasattr(chunk, 'model'):
                                self.system_info.emit({"model": chunk.model})

            # Emit the full collected content
            if full_text:
                self.message_received.emit(full_text)
            else:
                self.message_received.emit("")

            # Emit collected reasoning steps
            if self.collected_reasoning_steps:
                self.reasoning_steps.emit(self.collected_reasoning_steps)

        except Exception as e:
            self.logger.error(f"Error handling streaming response: {str(e)}")
            self.error_occurred.emit(f"Streaming error: {str(e)}")

    def _extract_thinking_step(self, event):
        """Extract thinking step name and content from various event formats"""
        try:
            # Handle different event structures
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
                return None

            return step_name, step_content
        except Exception as e:
            self.logger.warning(f"Error extracting thinking step: {str(e)}")
            return None

    def _process_completion_metadata(self, response):
        """Process metadata from a completed response"""
        try:
            if hasattr(response, "usage"):
                usage_data = self._normalize_token_usage(
                    {
                        "input_tokens": getattr(response.usage, "input_tokens", 0),
                        "output_tokens": getattr(response.usage, "output_tokens", 0),
                        "total_tokens": getattr(response.usage, "total_tokens", 0),
                        "output_tokens_details": getattr(response.usage, "output_tokens_details", None)
                    },
                    "responses"
                )
                self.usage_info.emit(usage_data)
        except Exception as e:
            self.logger.error(f"Error processing completion metadata: {str(e)}")

    def _process_chat_usage(self, usage):
        """Process usage information from chat completion"""
        try:
            usage_data = self._normalize_token_usage(
                {
                    "prompt_tokens": getattr(usage, 'prompt_tokens', 0),
                    "completion_tokens": getattr(usage, 'completion_tokens', 0),
                    "total_tokens": getattr(usage, 'total_tokens', 0)
                },
                "chat_completions"
            )
            self.usage_info.emit(usage_data)
        except Exception as e:
            self.logger.warning(f"Error processing usage data: {str(e)}")

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
                if hasattr(response, "usage"):
                    try:
                        # Create usage data dictionary with safe attribute access
                        usage_data_dict = {
                            "input_tokens": getattr(response.usage, "input_tokens", 0),
                            "output_tokens": getattr(response.usage, "output_tokens", 0),
                            "total_tokens": getattr(response.usage, "total_tokens", 0)
                        }

                        # Handle output_tokens_details safely
                        if hasattr(response.usage, "output_tokens_details"):
                            usage_data_dict["output_tokens_details"] = response.usage.output_tokens_details

                        usage_data = self._normalize_token_usage(usage_data_dict, "responses")
                        self.usage_info.emit(usage_data)
                    except Exception as e:
                        self.logger.error(f"Error processing usage data: {str(e)}")

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

    def _normalize_token_usage(self, usage, api_type="responses"):
        """Normalize token usage data to a consistent format regardless of API type"""
        normalized = {}

        # Log the incoming usage data for better debugging
        self.logger.debug(f"Normalizing token usage from {api_type} API: {usage}")

        if api_type == "responses":
            # Handle Response API token usage
            normalized["prompt_tokens"] = usage.get("input_tokens", 0)
            normalized["completion_tokens"] = usage.get("output_tokens", 0)

            # Ensure total_tokens gets set even if not in the response
            if "total_tokens" in usage:
                normalized["total_tokens"] = usage.get("total_tokens", 0)
            else:
                # Calculate if not provided
                normalized["total_tokens"] = normalized["prompt_tokens"] + normalized["completion_tokens"]

            # Handle o3-mini model specifically
            model = self.settings.get("model", "")
            is_o3_model = "o3" in model

            # Include reasoning tokens if available or set to 0 for o3 models that may not report it
            if "output_tokens_details" in usage and usage["output_tokens_details"]:
                details = usage["output_tokens_details"]
                # Handle both dictionary and object types
                if isinstance(details, dict):
                    normalized["completion_tokens_details"] = {
                        "reasoning_tokens": details.get("reasoning_tokens", 0)
                    }
                else:
                    # Handle OutputTokensDetails as an object with attributes
                    normalized["completion_tokens_details"] = {
                        "reasoning_tokens": getattr(details, "reasoning_tokens", 0)
                    }
            elif is_o3_model:
                # For o3 models, add a placeholder for reasoning tokens even if not provided
                normalized["completion_tokens_details"] = {
                    "reasoning_tokens": 0
                }
                self.logger.debug(f"Added placeholder reasoning tokens for {model}")

        self.logger.debug(f"Normalized token usage: {normalized}")
        return normalized

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

    def _handle_stream_timeout(self):
        """Handle timeout for streaming responses"""
        self.logger.warning(f"Worker {self._worker_id} streaming operation timed out")
        self._is_cancelled = True
        self.error_occurred.emit("Streaming operation timed out. Please try again.")

        # Force completion with current content
        if self._current_text_content:
            try:
                self.message_received.emit(self._current_text_content)
            except Exception as e:
                self.logger.error(f"Error emitting message in timeout handler: {str(e)}")
