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

                    except openai.BadRequestError as bad_req_error:
                        # Special handling for input length errors
                        error_msg = str(bad_req_error)
                        self.logger.error(f"Bad request error: {error_msg}")

                        if "string too long" in error_msg or "maximum context length" in error_msg:
                            # This is a token/character limit error
                            self.error_occurred.emit(
                                "Your message is too large for the API to process. Please reduce the size or number of file attachments."
                            )
                        else:
                            self.error_occurred.emit(f"Bad request: {error_msg}")
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
                    except openai.BadRequestError as bad_req_error:
                        # Special handling for input length errors
                        error_msg = str(bad_req_error)
                        self.logger.error(f"Bad request error: {error_msg}")

                        if "string too long" in error_msg or "maximum context length" in error_msg:
                            # This is a token/character limit error
                            self.error_occurred.emit(
                                "Your message is too large for the API to process. Please reduce the size or number of file attachments."
                            )
                        else:
                            self.error_occurred.emit(f"Bad request: {error_msg}")
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

            # Signal completion - use try/except to ensure we always emit the signal
            try:
                self.worker_finished.emit()
            except Exception as signal_error:
                self.logger.error(f"Error emitting worker finished signal: {str(signal_error)}")
                # Last resort - force emit with a new thread (not ideal, but better than crashing)
                try:
                    import threading
                    threading.Thread(target=lambda: self.worker_finished.emit()).start()
                except:
                    pass

            self.logger.info(f"Worker {self._worker_id} finished processing")

    def _prepare_response_api_params(self, model):
        """Prepare parameters for the Response API with consistent parameter handling"""
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

        # Handle token limit - always use max_output_tokens for Response API
        # Get token limit with fallbacks to ensure we get a value
        token_limit = self.settings.get("max_output_tokens",
                                        self.settings.get("max_completion_tokens",
                                                          self.settings.get("max_tokens", 1024)))
        params["max_output_tokens"] = token_limit
        self.logger.debug(f"Using max_output_tokens={token_limit} for Responses API")

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

        self.logger.debug(f"Final Responses API parameters: {list(params.keys())}")
        return params

    def _prepare_chat_completions_params(self, model):
        """Prepare parameters for the Chat Completions API with improved model compatibility"""
        # Process messages for the Chat API format
        prepared_messages = self.prepare_input(self.messages, "chat_completions")

        # Base parameters (common across models)
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

        # Get token limit with appropriate fallbacks
        token_limit = self.settings.get("max_completion_tokens",
                                        self.settings.get("max_tokens",
                                                          self.settings.get("max_output_tokens", 1024)))

        # Check if this is an o-series or reasoning model that requires max_completion_tokens
        from src.utils import REASONING_MODELS
        is_o_series = (
                model in REASONING_MODELS or
                model.startswith("o1") or
                model.startswith("o3") or
                model.startswith("deepseek-")
        )

        if is_o_series:
            # These models require max_completion_tokens instead of max_tokens
            params["max_completion_tokens"] = token_limit
            self.logger.debug(f"Using max_completion_tokens={token_limit} for model {model}")
        else:
            # Standard models use max_tokens
            params["max_tokens"] = token_limit
            self.logger.debug(f"Using max_tokens={token_limit} for model {model}")

        # Add seed if specified
        if self.settings.get("seed") is not None:
            params["seed"] = self.settings.get("seed")

        # Add other common parameters if specified
        for param in ["frequency_penalty", "presence_penalty", "logit_bias", "user"]:
            if param in self.settings and self.settings[param] is not None:
                params[param] = self.settings[param]

        return params

    def _handle_streaming_response(self, stream, api_type="responses"):
        """Handle streaming response from either API with improved structure and ordering"""
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

                    # Log detailed event information for debugging
                    event_type = getattr(event, 'type', None)
                    self.logger.debug(f"Processing event type: {event_type}")

                    if not event_type:
                        self.logger.debug(f"Event without type: {event}")
                        continue

                    if event_type == "response.created":
                        # Capture response ID from creation event
                        if hasattr(event, 'response') and hasattr(event.response, 'id'):
                            response_id = event.response.id
                            self.logger.info(f"Captured response ID: {response_id}")
                            self.completion_id.emit(response_id)
                        else:
                            self.logger.debug(f"Response created but couldn't extract ID: {event}")

                    elif event_type == "response.output_text.delta":
                        # Process text delta (the actual content chunk)
                        delta = getattr(event, 'delta', '')
                        if delta:
                            self._current_text_content += delta
                            full_text += delta
                            self.chunk_received.emit(delta)
                        else:
                            self.logger.debug("Empty delta in output_text.delta event")

                    elif event_type == "response.completed":
                        # Process completion event (final usage stats, etc.)
                        self.logger.info("Processing completion event")
                        if hasattr(event, 'response'):
                            # Log the entire response object
                            self.logger.debug(f"Completion response: {event.response}")

                            # Try to extract usage data with fallbacks
                            try:
                                if hasattr(event.response, 'usage'):
                                    self.logger.debug(f"Usage data from response: {event.response.usage}")
                                    usage_data = self._normalize_token_usage(event.response.usage, "responses")
                                    self.usage_info.emit(usage_data)
                                elif hasattr(event.response, 'token_usage'):
                                    self.logger.debug(f"Token usage data found: {event.response.token_usage}")
                                    usage_data = self._normalize_token_usage(event.response.token_usage, "responses")
                                    self.usage_info.emit(usage_data)
                                else:
                                    self.logger.warning("No usage data found in completion response")
                            except Exception as usage_error:
                                self.logger.error(f"Error processing usage data: {str(usage_error)}")

                            # Store model information with safe extraction
                            try:
                                if hasattr(event.response, 'model'):
                                    model_info["model"] = event.response.model
                                else:
                                    # Try to get model from different possible locations
                                    possible_model = getattr(event.response, 'model_name', None)
                                    if possible_model:
                                        model_info["model"] = possible_model
                                    else:
                                        # Use the model from settings as fallback
                                        model_info["model"] = self.settings.get("model", "unknown")

                                self.logger.info(f"Emitting model info: {model_info}")
                                self.system_info.emit(model_info)
                            except Exception as model_error:
                                self.logger.error(f"Error extracting model info: {str(model_error)}")

                        # CRITICAL: Do NOT emit full content here as it may cause duplication
                        # Just signal that we're done with streaming
                        self.logger.info("Streaming complete - emitting worker_finished")

                # Always emit the final accumulated text, but only once and only at the end
                if full_text:
                    self.logger.debug(f"Emitting final accumulated text (length: {len(full_text)})")
                    self.message_received.emit(full_text)

            else:
                # This is the chat_completions API streaming
                self.logger.info("Processing chat completions streaming")
                model_info = {}

                # Process each chunk in the stream
                for chunk in stream:
                    # Check for cancellation
                    if self._is_cancelled:
                        self.logger.info("API request cancelled during streaming")
                        break

                    self.logger.debug(f"Got chat completion chunk: {chunk}")

                    # Process the chunk based on the OpenAI API structure
                    if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                        choice = chunk.choices[0]

                        # Extract the model info if available
                        if hasattr(chunk, 'model') and chunk.model:
                            model_info["model"] = chunk.model
                            self.logger.debug(f"Extracted model: {chunk.model}")
                            self.system_info.emit(model_info)

                        # Extract completion ID if available
                        if hasattr(chunk, 'id') and chunk.id:
                            self.logger.debug(f"Extracted completion ID: {chunk.id}")
                            self.completion_id.emit(chunk.id)

                        # Handle delta content
                        if hasattr(choice, 'delta') and hasattr(choice.delta, 'content') and choice.delta.content:
                            delta = choice.delta.content
                            self.logger.debug(f"Extracted content delta: {delta[:20]}...")
                            self._current_text_content += delta
                            full_text += delta
                            self.chunk_received.emit(delta)

                        # Check for finish reason
                        if hasattr(choice, 'finish_reason') and choice.finish_reason:
                            self.logger.debug(f"Chat completion finished with reason: {choice.finish_reason}")

                    # Extract usage data if this is the final chunk
                    if hasattr(chunk, 'usage') and chunk.usage:
                        self.logger.debug(f"Extracted usage data: {chunk.usage}")
                        usage_data = self._normalize_token_usage(chunk.usage, "chat_completions")
                        self.usage_info.emit(usage_data)

                # Emit the full message when done
                if full_text:
                    self.logger.debug(f"Emitting complete message (length: {len(full_text)})")
                    self.message_received.emit(full_text)
        except Exception as e:
            self.logger.warning(f"Error: {str(e)}")
            return None

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
        """Process metadata from a completed response with comprehensive extraction"""
        try:
            self.logger.debug(f"Processing completion metadata. Response type: {type(response)}")
            self.logger.debug(f"Response attributes: {[attr for attr in dir(response) if not attr.startswith('_') and not callable(getattr(response, attr))]}")

            # Try multiple ways to get usage data
            usage_data = None

            # Method 1: Direct usage attribute
            if hasattr(response, "usage"):
                self.logger.debug("Found usage attribute")
                usage_data = self._normalize_token_usage(response.usage, "responses")

            # Method 2: token_usage attribute
            elif hasattr(response, "token_usage"):
                self.logger.debug("Found token_usage attribute")
                usage_data = self._normalize_token_usage(response.token_usage, "responses")

            # Method 3: Try other possible attribute names
            else:
                for attr_name in dir(response):
                    if ("usage" in attr_name.lower() or "token" in attr_name.lower()) and not attr_name.startswith("_"):
                        attr_value = getattr(response, attr_value)
                        if attr_value is not None:
                            self.logger.debug(f"Found potential usage data in {attr_name}")
                            usage_data = self._normalize_token_usage(attr_value, "responses")
                            break

            # Method 4: Last resort - try to build usage data from response properties
            if usage_data is None:
                self.logger.debug("Building usage data from response properties")
                model = getattr(response, "model", self.settings.get("model", "unknown"))
                token_data = {}

                # Search for token-related properties
                for attr_name in dir(response):
                    if "token" in attr_name.lower() and not attr_name.startswith("_"):
                        value = getattr(response, attr_name)
                        if isinstance(value, (int, float)):
                            token_data[attr_name] = value

                # If we found any token data, try to normalize it
                if token_data:
                    self.logger.debug(f"Found token data: {token_data}")
                    usage_data = self._normalize_token_usage(token_data, "responses")

            # Emit usage data if we found it
            if usage_data:
                self.logger.debug(f"Emitting usage data: {usage_data}")
                self.usage_info.emit(usage_data)
            else:
                self.logger.warning("No usage data found in completion metadata")
        except Exception as e:
            self.logger.error(f"Error processing completion metadata: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")

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
        """
        Handle non-streaming response from either API with comprehensive error handling.
        Works with any model type and API format by extracting data in the proper order.
        """
        try:
            content = ""
            self.logger.info(f"Processing full response from {api_type} API")
            response_id = None

            # Log response type and structure for debugging
            self.logger.debug(f"Response type: {type(response)}")
            try:
                self.logger.debug(f"Response attributes: {[attr for attr in dir(response) if not attr.startswith('_') and not callable(getattr(response, attr))]}")
            except Exception:
                pass  # Silently handle attribute inspection errors

            # STEP 1: Extract model information (do this FIRST)
            try:
                model_info = {}
                # Try multiple possible locations for model info
                if hasattr(response, "model"):
                    model_info["model"] = response.model
                    self.logger.debug(f"Found model attribute: {response.model}")
                elif hasattr(response, "model_name"):
                    model_info["model"] = response.model_name
                    self.logger.debug(f"Found model_name attribute: {response.model_name}")
                elif hasattr(response, "completion") and hasattr(response.completion, "model"):
                    model_info["model"] = response.completion.model
                    self.logger.debug(f"Found completion.model attribute: {response.completion.model}")
                elif api_type == "responses" and hasattr(response, "metadata") and hasattr(response.metadata, "model_name"):
                    model_info["model"] = response.metadata.model_name
                    self.logger.debug(f"Found metadata.model_name attribute: {response.metadata.model_name}")
                else:
                    # Use model from settings as fallback
                    model_info["model"] = self.settings.get("model", "unknown")
                    self.logger.debug(f"Using fallback model from settings: {model_info['model']}")

                # Emit model info first (critical for UI display)
                self.system_info.emit(model_info)
                self.logger.debug(f"Emitted model info: {model_info}")
            except Exception as model_error:
                self.logger.error(f"Error extracting model info: {str(model_error)}")
                # Still emit fallback model info to prevent UI issues
                self.system_info.emit({"model": self.settings.get("model", "unknown")})

            # STEP 2: Extract completion/response ID (second priority)
            try:
                if hasattr(response, "id"):
                    response_id = response.id
                    self.logger.debug(f"Found ID directly: {response_id}")
                elif api_type == "responses" and hasattr(response, "metadata") and hasattr(response.metadata, "id"):
                    response_id = response.metadata.id
                    self.logger.debug(f"Found ID in metadata: {response_id}")
                elif hasattr(response, "completion") and hasattr(response.completion, "id"):
                    response_id = response.completion.id
                    self.logger.debug(f"Found ID in completion: {response_id}")

                if response_id:
                    self.completion_id.emit(response_id)
                    self.logger.debug(f"Emitted completion ID: {response_id}")
            except Exception as id_error:
                self.logger.error(f"Error extracting completion ID: {str(id_error)}")

            # STEP 3: Extract and emit usage information (third priority)
            try:
                usage_data = None
                # Try all possible locations for usage data
                if hasattr(response, "usage"):
                    self.logger.debug(f"Found usage attribute")
                    usage_data = self._normalize_token_usage(response.usage, api_type)
                elif hasattr(response, "token_usage"):
                    self.logger.debug(f"Found token_usage attribute")
                    usage_data = self._normalize_token_usage(response.token_usage, api_type)
                elif hasattr(response, "completion") and hasattr(response.completion, "usage"):
                    self.logger.debug(f"Found completion.usage attribute")
                    usage_data = self._normalize_token_usage(response.completion.usage, api_type)
                elif api_type == "responses" and hasattr(response, "metadata") and hasattr(response.metadata, "usage"):
                    self.logger.debug(f"Found metadata.usage attribute")
                    usage_data = self._normalize_token_usage(response.metadata.usage, api_type)

                # If no direct match, search for any usage-like attributes
                if not usage_data:
                    for attr_name in dir(response):
                        if ("usage" in attr_name.lower() or "token" in attr_name.lower()) and not attr_name.startswith("_"):
                            try:
                                attr_value = getattr(response, attr_name)
                                if attr_value is not None:
                                    self.logger.debug(f"Found potential usage data in {attr_name}")
                                    usage_data = self._normalize_token_usage(attr_value, api_type)
                                    break
                            except Exception:
                                continue

                # Emit usage data if found
                if usage_data:
                    self.usage_info.emit(usage_data)
                    self.logger.debug(f"Emitted usage data: {usage_data}")
            except Exception as usage_error:
                self.logger.error(f"Error extracting usage data: {str(usage_error)}")

            # STEP 4: Extract content based on API type (different for each API)
            try:
                if api_type == "responses":
                    # Response API content extraction with multiple fallbacks

                    # Method 1: Direct output_text attribute (common in newer versions)
                    if hasattr(response, "output_text"):
                        content = response.output_text
                        self.logger.debug(f"Found content in output_text attribute, length: {len(content)}")

                    # Method 2: Classic format using output[].content[].text
                    elif hasattr(response, "output") and isinstance(response.output, list):
                        for output_item in response.output:
                            if hasattr(output_item, "type") and output_item.type == "message" and getattr(output_item, "role", "") == "assistant":
                                if hasattr(output_item, "content") and isinstance(output_item.content, list):
                                    for content_part in output_item.content:
                                        if hasattr(content_part, "type") and content_part.type == "output_text":
                                            content = getattr(content_part, "text", "")
                                            if content:
                                                self.logger.debug(f"Found content in output.content, length: {len(content)}")
                                                break

                    # Method 3: Check for completion.content or similar structure
                    elif hasattr(response, "completion") and hasattr(response.completion, "content"):
                        content = response.completion.content
                        self.logger.debug(f"Found content in completion.content, length: {len(content)}")

                    # Method 4: Check for message.content structure (used by some models)
                    elif hasattr(response, "message") and hasattr(response.message, "content"):
                        content = response.message.content
                        self.logger.debug(f"Found content in message.content, length: {len(content)}")

                    # Method 5: Check for choices structure (used by some Response API versions)
                    elif hasattr(response, "choices") and len(getattr(response, "choices", [])) > 0:
                        choice = response.choices[0]
                        if hasattr(choice, "message") and hasattr(choice.message, "content"):
                            content = choice.message.content
                            self.logger.debug(f"Found content in choices[0].message.content, length: {len(content)}")
                        elif hasattr(choice, "text"):
                            content = choice.text
                            self.logger.debug(f"Found content in choices[0].text, length: {len(content)}")

                    # Method 6: Look for direct text or content attributes
                    elif hasattr(response, "text"):
                        content = response.text
                        self.logger.debug(f"Found content in text attribute, length: {len(content)}")
                    elif hasattr(response, "content"):
                        content = response.content
                        self.logger.debug(f"Found content in content attribute, length: {len(content)}")

                else:  # Chat Completions API
                    # Chat Completions API content extraction
                    if hasattr(response, "choices") and len(getattr(response, "choices", [])) > 0:
                        choice = response.choices[0]
                        if hasattr(choice, "message") and hasattr(choice.message, "content"):
                            content = choice.message.content or ""
                            self.logger.debug(f"Found content in choices[0].message.content, length: {len(content)}")
                        elif hasattr(choice, "text"):
                            content = choice.text
                            self.logger.debug(f"Found content in choices[0].text, length: {len(content)}")
                    elif hasattr(response, "message") and hasattr(response.message, "content"):
                        content = response.message.content
                        self.logger.debug(f"Found content in message.content, length: {len(content)}")
                    elif hasattr(response, "content"):
                        content = response.content
                        self.logger.debug(f"Found content in content attribute, length: {len(content)}")

                # If still no content found, try last resort search
                if not content:
                    self.logger.warning("Could not extract content from standard locations, trying fallback methods")

                    # Last resort - search recursively for any content-like attribute
                    def search_for_content(obj, depth=0, max_depth=3):
                        if depth > max_depth or obj is None:
                            return None

                        # Check direct string attributes first
                        for attr_name in ["content", "text", "output_text", "value", "result"]:
                            if hasattr(obj, attr_name):
                                value = getattr(obj, attr_name)
                                if isinstance(value, str) and len(value) > 10:
                                    return value

                        # Then recursively check object attributes
                        for attr_name in dir(obj):
                            if attr_name.startswith('_') or callable(getattr(obj, attr_name, None)):
                                continue
                            try:
                                attr_value = getattr(obj, attr_name)
                                if isinstance(attr_value, str) and len(attr_value) > 10:
                                    return attr_value
                                elif isinstance(attr_value, (dict, list)) or hasattr(attr_value, "__dict__"):
                                    result = search_for_content(attr_value, depth + 1, max_depth)
                                    if result:
                                        return result
                            except Exception:
                                continue
                        return None

                    # Try to find content recursively
                    found_content = search_for_content(response)
                    if found_content:
                        content = found_content
                        self.logger.debug(f"Found content via recursive search, length: {len(content)}")
            except Exception as content_error:
                self.logger.error(f"Error extracting content: {str(content_error)}")

                # STEP 5: Extract any reasoning steps if available
                try:
                    # Reasoning extraction is currently disabled since it's not supported by OpenAI API
                    # Keeping the structure for future updates when reasoning becomes available
                    self.logger.debug("Reasoning extraction is disabled - skipping reasoning step extraction")
                    """
                    # Extract reasoning steps with robust fallbacks
                    if api_type == "responses":
                        reasoning_extracted = False

                        # Method 1: Standard reasoning attribute
                        if hasattr(response, "reasoning"):
                            reasoning_obj = response.reasoning

                            # Extract summary if available
                            if hasattr(reasoning_obj, "summary") and reasoning_obj.summary:
                                self.collected_reasoning_steps.append({
                                    "name": "Reasoning Summary",
                                    "content": reasoning_obj.summary
                                })
                                reasoning_extracted = True
                                self.logger.debug("Extracted reasoning summary")

                            # Extract steps list if available
                            if hasattr(reasoning_obj, "steps") and reasoning_obj.steps:
                                steps_list = reasoning_obj.steps
                                for step in steps_list:
                                    if isinstance(step, dict):
                                        self.collected_reasoning_steps.append({
                                            "name": step.get("name", "Step"),
                                            "content": step.get("content", "")
                                        })
                                    else:
                                        self.collected_reasoning_steps.append({
                                            "name": getattr(step, "name", "Step"),
                                            "content": getattr(step, "content", "")
                                        })
                                reasoning_extracted = True
                                self.logger.debug(f"Extracted {len(steps_list)} reasoning steps")

                        # Method 2: Check for thinking_steps attribute
                        if not reasoning_extracted and hasattr(response, "thinking_steps"):
                            thinking_steps = response.thinking_steps
                            if isinstance(thinking_steps, list):
                                for i, step in enumerate(thinking_steps):
                                    step_dict = {}
                                    if isinstance(step, dict):
                                        step_dict = step
                                    elif hasattr(step, "__dict__"):
                                        step_dict = {k: v for k, v in step.__dict__.items() if not k.startswith('_')}
                                    else:
                                        # Create from attributes
                                        step_dict = {
                                            "name": getattr(step, "name", f"Step {i + 1}"),
                                            "content": getattr(step, "content", str(step))
                                        }

                                    self.collected_reasoning_steps.append({
                                        "name": step_dict.get("name", f"Step {i + 1}"),
                                        "content": step_dict.get("content", "")
                                    })
                                reasoning_extracted = True
                                self.logger.debug(f"Extracted {len(thinking_steps)} thinking steps")

                        # Check for o3-mini and other reasoning models
                        model_name = model_info.get("model", "").lower()
                        is_reasoning_model = ("o1" in model_name or "o3" in model_name or
                                              "deepseek-reasoner" in model_name or
                                              model_name in self.settings.get("reasoning_models", []))

                        # For o3-mini, check usage data for reasoning tokens
                        if not reasoning_extracted and is_reasoning_model and hasattr(response, "usage"):
                            usage_obj = response.usage
                            reasoning_tokens = 0

                            # Try to extract reasoning tokens
                            if hasattr(usage_obj, "output_tokens_details"):
                                details = usage_obj.output_tokens_details
                                if isinstance(details, dict):
                                    reasoning_tokens = details.get("reasoning_tokens", 0)
                                else:
                                    reasoning_tokens = getattr(details, "reasoning_tokens", 0)

                            # Add placeholder step for models that used reasoning
                            if reasoning_tokens > 0:
                                self.collected_reasoning_steps.append({
                                    "name": f"{model_name.upper()} Reasoning",
                                    "content": f"Model performed internal reasoning using {reasoning_tokens} tokens (detailed steps not available)"
                                })
                                reasoning_extracted = True
                                self.logger.debug(f"Added reasoning placeholder for {model_name} with {reasoning_tokens} reasoning tokens")

                    # Emit collected reasoning steps if any were found
                    if self.collected_reasoning_steps:
                        self.reasoning_steps.emit(self.collected_reasoning_steps)
                        self.logger.debug(f"Emitted {len(self.collected_reasoning_steps)} reasoning steps")
                    """
                except Exception as reasoning_error:
                    self.logger.error(f"Error extracting reasoning steps: {str(reasoning_error)}")

            # STEP 6: FINALLY emit the content or error message
            if content:
                self.logger.debug(f"Emitting message content, length: {len(content)}")
                self.message_received.emit(content)
            else:
                self.logger.error(f"Failed to extract content from {api_type} response!")
                # Send a fallback message so UI isn't stuck
                error_msg = f"Error: Unable to extract response from {model_info.get('model', 'model')}. Please try again."
                self.message_received.emit(error_msg)

        except Exception as e:
            self.logger.error(f"Critical error in _handle_full_response: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            # Send a fallback message so UI isn't stuck
            self.message_received.emit("Error processing response. Please try again.")

    def cancel(self):
        """Mark the worker for cancellation"""
        self._is_cancelled = True
        self.logger.info("Worker marked for cancellation")

    def _handle_completed_event(self, event):
        """Handle completion event for Response API streaming with proper content management"""
        # Emit usage information if available
        if hasattr(event, "response"):
            response_data = event.response
            self.logger.info("Processing completion event with full response data")

            # Extract system info and response ID first (these should always be emitted)
            try:
                # Extract model info
                model_name = "unknown"
                if hasattr(response_data, "model"):
                    model_name = response_data.model
                elif isinstance(response_data, dict) and "model" in response_data:
                    model_name = response_data["model"]

                # Emit system information
                model_info = {"model": model_name}
                self.system_info.emit(model_info)
                self.logger.debug(f"Emitted model info: {model_name}")

                # Extract response ID if available
                response_id = None
                if hasattr(response_data, "id"):
                    response_id = response_data.id
                    self.completion_id.emit(response_id)
                    self.logger.debug(f"Emitted completion ID: {response_id}")
                elif isinstance(response_data, dict) and "id" in response_data:
                    response_id = response_data["id"]
                    self.completion_id.emit(response_id)
                    self.logger.debug(f"Emitted completion ID: {response_id}")
            except Exception as e:
                self.logger.error(f"Error extracting basic response data: {str(e)}")

            # Process token usage data if available
            try:
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
                elif isinstance(response_data, dict) and "usage" in response_data:
                    usage = response_data["usage"]
                    usage_data = self._normalize_token_usage(usage, "responses")
                    self.usage_info.emit(usage_data)
                else:
                    self.logger.warning("No usage data found in completion response")
            except Exception as e:
                self.logger.error(f"Error processing usage data: {str(e)}")

            # CRITICAL CHANGE: We DO NOT emit message_received with content from the completion event
            # This was causing duplicate/out-of-order content because:
            # 1. Chunks were already streaming into the UI
            # 2. The completion event was sending the full content again
            # 3. This was getting appended to what was already shown

            # Instead, we'll just log that we received the completion event
            try:
                if hasattr(response_data, "output_text"):
                    self.logger.debug(f"Completion event has output_text of length: {len(response_data.output_text)}")
                elif hasattr(response_data, "content"):
                    self.logger.debug(f"Completion event has content of length: {len(response_data.content)}")
                elif isinstance(response_data, dict) and "output_text" in response_data:
                    self.logger.debug(f"Completion event has output_text of length: {len(response_data['output_text'])}")
            except Exception as e:
                self.logger.error(f"Error logging completion content info: {str(e)}")

            # Signal that streaming is complete but WITHOUT sending the content again
            self.worker_finished.emit()

    def _normalize_token_usage(self, usage, api_type="responses"):
        """Normalize token usage data to a consistent format regardless of API type"""
        normalized = {}

        # Log the incoming usage data for better debugging
        self.logger.debug(f"Normalizing token usage from {api_type} API: {usage}")

        # Perform type detection to handle different response structures
        usage_dict = {}
        is_dict = isinstance(usage, dict)

        # Extract data from various object types
        if is_dict:
            usage_dict = usage
        elif hasattr(usage, "__dict__"):
            # Standard Python object with __dict__
            usage_dict = {k: v for k, v in usage.__dict__.items() if not k.startswith('_')}
        elif hasattr(usage, "model_dump"):
            # Pydantic model with model_dump() method
            usage_dict = usage.model_dump()
        elif hasattr(usage, "dict"):
            # Object with dict() method
            usage_dict = usage.dict()
        else:
            # Last resort - try to get attributes directly
            usage_dict = {}
            for attr in dir(usage):
                if not attr.startswith('_') and not callable(getattr(usage, attr)):
                    usage_dict[attr] = getattr(usage, attr)

        # Log the extracted dictionary for debugging
        self.logger.debug(f"Extracted usage dictionary: {usage_dict}")

        # Handle different API types
        if api_type == "responses":
            # Response API uses input_tokens/output_tokens
            normalized["prompt_tokens"] = self._safe_get(usage, usage_dict, "input_tokens", 0)
            normalized["completion_tokens"] = self._safe_get(usage, usage_dict, "output_tokens", 0)
            normalized["total_tokens"] = self._safe_get(usage, usage_dict, "total_tokens",
                                                        normalized["prompt_tokens"] + normalized["completion_tokens"])
        else:
            # Chat Completions API uses prompt_tokens/completion_tokens
            normalized["prompt_tokens"] = self._safe_get(usage, usage_dict, "prompt_tokens", 0)
            normalized["completion_tokens"] = self._safe_get(usage, usage_dict, "completion_tokens", 0)
            normalized["total_tokens"] = self._safe_get(usage, usage_dict, "total_tokens",
                                                        normalized["prompt_tokens"] + normalized["completion_tokens"])

        # Process reasoning data - check multiple possible locations
        model = self.settings.get("model", "")
        is_reasoning_model = model in REASONING_MODELS or "o1" in model or "o3" in model
        self.logger.debug(f"Processing model {model}, is_reasoning_model: {is_reasoning_model}")

        # Extract output_tokens_details using multiple methods
        details_dict = {}

        # Method 1: Try to get directly from usage_dict
        if "output_tokens_details" in usage_dict:
            raw_details = usage_dict["output_tokens_details"]
            details_dict = self._extract_details_dict(raw_details)
            self.logger.debug(f"Found output_tokens_details in usage_dict: {details_dict}")

        # Method 2: Try to get via attribute access
        elif hasattr(usage, "output_tokens_details"):
            raw_details = getattr(usage, "output_tokens_details")
            details_dict = self._extract_details_dict(raw_details)
            self.logger.debug(f"Found output_tokens_details via attribute: {details_dict}")

        # Method 3: Try other possible field names for reasoning metrics
        elif "reasoning_output_tokens" in usage_dict:
            details_dict["reasoning_tokens"] = usage_dict["reasoning_output_tokens"]
            self.logger.debug(f"Found reasoning_output_tokens: {details_dict['reasoning_tokens']}")
        elif "reasoning_tokens" in usage_dict:
            details_dict["reasoning_tokens"] = usage_dict["reasoning_tokens"]
            self.logger.debug(f"Found direct reasoning_tokens: {details_dict['reasoning_tokens']}")

        # Create standardized completion_tokens_details
        if details_dict:
            normalized["completion_tokens_details"] = {
                "reasoning_tokens": details_dict.get("reasoning_tokens", 0),
                "accepted_prediction_tokens": details_dict.get("accepted_prediction_tokens", 0),
                "rejected_prediction_tokens": details_dict.get("rejected_prediction_tokens", 0)
            }
        # Add placeholder for reasoning models even if not found
        elif is_reasoning_model:
            normalized["completion_tokens_details"] = {
                "reasoning_tokens": 0,
                "accepted_prediction_tokens": 0,
                "rejected_prediction_tokens": 0
            }
            self.logger.debug(f"Added placeholder reasoning data for {model}")

        self.logger.debug(f"Normalized token usage: {normalized}")
        return normalized

    def _safe_get(self, obj, obj_dict, key, default=0):
        """Safely get a value from either dict or object attributes"""
        # Try dict access first
        if key in obj_dict:
            return obj_dict[key]
        # Then try attribute access
        elif hasattr(obj, key):
            return getattr(obj, key)
        # Finally return default
        return default

    def _extract_details_dict(self, details):
        """Extract a dictionary from details object regardless of type"""
        if details is None:
            return {}
        if isinstance(details, dict):
            return details
        # Try standard object with __dict__
        if hasattr(details, "__dict__"):
            return {k: v for k, v in details.__dict__.items() if not k.startswith('_')}
        # Try Pydantic model
        if hasattr(details, "model_dump"):
            return details.model_dump()
        # Try dict() method
        if hasattr(details, "dict"):
            return details.dict()
        # Manually extract attributes
        result = {}
        for attr in ["reasoning_tokens", "accepted_prediction_tokens", "rejected_prediction_tokens"]:
            if hasattr(details, attr):
                result[attr] = getattr(details, attr)
        return result

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
