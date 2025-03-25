"""
ViewModel for managing conversation interactions using qasync for PyQt integration.
"""
# Standard library imports
import asyncio
import concurrent.futures  # Use the full module name for clarity

# Third-party imports
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

# Application-specific imports - utilities first
from src.utils.logging_utils import get_logger
from src.utils.qasync_bridge import run_coroutine, ensure_qasync_loop

# Application-specific imports - services
from src.services.api import AsyncApiService
from src.services.database import AsyncConversationService

class FullAsyncConversationViewModel(QObject):
    """
    ViewModel for managing conversation interactions using qasync for proper PyQt integration.
    Eliminates thread-based approaches in favor of proper qasync integration.
    """

    # Signal definitions
    conversationLoaded = pyqtSignal(object)  # Emitted when a conversation is loaded
    messageAdded = pyqtSignal(object)  # Emitted when a message is added
    messageUpdated = pyqtSignal(object)  # Emitted when a message is updated
    messageBranchChanged = pyqtSignal(list)  # Emitted when navigation changes the current branch
    messageStreamChunk = pyqtSignal(str)  # Emitted for each chunk during streaming
    messagingComplete = pyqtSignal()  # Emitted when a messaging operation is complete
    errorOccurred = pyqtSignal(str)  # Emitted when an error occurs
    loadingStateChanged = pyqtSignal(bool)  # Emitted when loading state changes
    tokenUsageUpdated = pyqtSignal(dict)  # Emitted when token usage information is updated
    reasoningStepsChanged = pyqtSignal(list)  # Emitted when reasoning steps are available

    def __init__(self):
        """Initialize the ViewModel with async services"""
        super().__init__()
        self.logger = get_logger(__name__)

        # Initialize services
        self.conversation_service = AsyncConversationService()
        self.api_service = AsyncApiService()

        # State variables
        self._current_conversation_id = None
        self._current_branch = []
        self._is_loading = False
        self._token_usage = {}
        self._stream_buffer = ""
        self._model_info = {}
        self._reasoning_steps = []
        self._initialized = False
        self._initialization_in_progress = False

        # Set up signal connections from API service
        self.api_service.requestStarted.connect(self._on_request_started)
        self.api_service.requestFinished.connect(self._on_request_finished)
        self.api_service.chunkReceived.connect(self._on_chunk_received)
        self.api_service.metadataReceived.connect(self._on_metadata_received)
        self.api_service.errorOccurred.connect(self._on_error_occurred)

        # Log initialization progress
        self.logger.info("FullAsyncConversationViewModel constructor completed")

        # Schedule initialization for after the UI is set up (300ms delay)
        QTimer.singleShot(300, self._initialize)

    def _initialize(self):
        """Initialize services using qasync"""
        self.logger.debug("Starting initialization with qasync")

        run_coroutine(
            self._initialize_async(),
            callback=self._handle_init_complete,
            error_callback=lambda e: self.errorOccurred.emit(f"Initialization error: {str(e)}")
        )

    def _handle_init_complete(self, success):
        """Handle initialization completion on the main thread"""
        self._initialized = success
        if success:
            self.logger.info("ViewModel initialization completed successfully")
        else:
            self.logger.error("ViewModel initialization failed")

    async def _initialize_async(self):
        """Actual async initialization implementation"""
        if self._initialized or self._initialization_in_progress:
            return True

        self._initialization_in_progress = True
        try:
            # Initialize conversation service
            result = await self.conversation_service.initialize()
            self.logger.info(f"Conversation service initialized: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Failed to initialize services: {str(e)}")
            return False
        finally:
            self._initialization_in_progress = False

    @pyqtSlot(str)
    def load_conversation(self, conversation_id):
        """Load a conversation by ID"""
        if conversation_id == self._current_conversation_id:
            return  # Already loaded

        self._current_conversation_id = conversation_id
        self.logger.debug(f"Loading conversation: {conversation_id}")

        # Use run_coroutine instead of thread-based approach
        run_coroutine(
            self._load_conversation_impl(conversation_id),
            error_callback=lambda e: self.errorOccurred.emit(f"Error loading conversation: {str(e)}")
        )

    async def _load_conversation_impl(self, conversation_id):
        """Implementation of load_conversation"""
        try:
            # Make sure database is initialized
            if not self._initialized:
                success = await self.conversation_service.initialize()
                if not success:
                    raise RuntimeError("Failed to initialize database")

            # Load the conversation
            conversation = await self.conversation_service.get_conversation(conversation_id)
            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Emit signal - QTimer not needed as run_coroutine handles threading
            self.conversationLoaded.emit(conversation)

            # Load message branch
            if conversation.current_node_id:
                branch = await self.conversation_service.get_message_branch(conversation.current_node_id)
                self._current_branch = branch
                self.messageBranchChanged.emit(branch)

            return conversation
        except Exception as e:
            self.logger.error(f"Error loading conversation: {str(e)}")
            raise  # run_coroutine will handle the error

    @pyqtSlot(str)
    def create_new_conversation(self, name="New Conversation"):
        """Create a new conversation"""
        self.logger.debug(f"Creating new conversation with name: {name}")

        # Use run_coroutine instead of thread-based approach
        run_coroutine(
            self._create_conversation_impl(name),
            error_callback=lambda e: self.errorOccurred.emit(f"Error creating conversation: {str(e)}")
        )

    async def _create_conversation_impl(self, name):
        """Implementation of create_new_conversation"""
        try:
            # Make sure database is initialized
            if not self._initialized:
                success = await self.conversation_service.initialize()
                if not success:
                    raise RuntimeError("Failed to initialize database")

            # Create the conversation
            conversation = await self.conversation_service.create_conversation(name=name)
            if not conversation:
                raise RuntimeError("Failed to create conversation")

            # Load the new conversation - this will be handled on main thread
            # Use QTimer to ensure we're on the main thread for UI operations
            QTimer.singleShot(0, lambda: self.load_conversation(conversation.id))

            return conversation
        except Exception as e:
            self.logger.error(f"Error creating conversation: {str(e)}")
            raise  # run_coroutine will handle the error

    @pyqtSlot(str, str)
    def rename_conversation(self, conversation_id, new_name):
        """Rename a conversation"""
        self.logger.debug(f"Renaming conversation {conversation_id} to '{new_name}'")

        run_coroutine(
            self._rename_conversation_impl(conversation_id, new_name),
            error_callback=lambda e: self.errorOccurred.emit(f"Error renaming conversation: {str(e)}")
        )

    async def _rename_conversation_impl(self, conversation_id, new_name):
        """Implementation of rename_conversation"""
        try:
            # Update the conversation
            success = await self.conversation_service.update_conversation(
                conversation_id, name=new_name
            )

            if success:
                # Reload the conversation to update UI
                if conversation_id == self._current_conversation_id:
                    await self._load_conversation_impl(conversation_id)

            return success
        except Exception as e:
            self.logger.error(f"Error renaming conversation: {str(e)}")
            raise

    @pyqtSlot(str)
    def delete_conversation(self, conversation_id):
        """Delete a conversation"""
        self.logger.debug(f"Deleting conversation: {conversation_id}")

        run_coroutine(
            self._delete_conversation_impl(conversation_id),
            error_callback=lambda e: self.errorOccurred.emit(f"Error deleting conversation: {str(e)}")
        )

    async def _delete_conversation_impl(self, conversation_id):
        """Implementation of delete_conversation"""
        try:
            # Delete the conversation
            success = await self.conversation_service.delete_conversation(conversation_id)

            if success:
                # If this was the current conversation, load a different one or create new
                if conversation_id == self._current_conversation_id:
                    # Get all conversations
                    conversations = await self.conversation_service.get_all_conversations()

                    if conversations:
                        # Load the first one
                        await self._load_conversation_impl(conversations[0].id)
                    else:
                        # Create a new one
                        await self._create_conversation_impl("New Conversation")

            return success
        except Exception as e:
            self.logger.error(f"Error deleting conversation: {str(e)}")
            raise

    @pyqtSlot(str, str)
    def duplicate_conversation(self, conversation_id, new_name=None):
        """Duplicate a conversation"""
        self.logger.debug(f"Duplicating conversation: {conversation_id}")

        run_coroutine(
            self._duplicate_conversation_impl(conversation_id, new_name),
            error_callback=lambda e: self.errorOccurred.emit(f"Error duplicating conversation: {str(e)}")
        )

    async def _duplicate_conversation_impl(self, conversation_id, new_name=None):
        """Implementation of duplicate_conversation"""
        try:
            # Duplicate the conversation
            new_conv = await self.conversation_service.duplicate_conversation(conversation_id, new_name)

            if new_conv:
                # Load the new conversation
                QTimer.singleShot(0, lambda: self.load_conversation(new_conv.id))

            return new_conv
        except Exception as e:
            self.logger.error(f"Error duplicating conversation: {str(e)}")
            raise

    @pyqtSlot(str, str, "QVariant")
    def send_message(self, conversation_id, content, attachments=None):
        """Send a user message and get a response"""
        self.logger.debug(f"Sending message to conversation {conversation_id}")

        # Set loading state
        self._is_loading = True
        self.loadingStateChanged.emit(True)

        run_coroutine(
            self._send_message_impl(conversation_id, content, attachments),
            callback=lambda _: self._finish_messaging(),
            error_callback=self._handle_messaging_error
        )

    async def _send_message_impl(self, conversation_id, content, attachments=None):
        """Implementation of send_message"""
        try:
            # Process attachments if any
            file_attachments = []
            if attachments:
                for attachment in attachments:
                    # Process file attachment
                    file_info = attachment

                    if 'filePath' in file_info:
                        # Convert filePath to standard path if it's a QUrl
                        path = file_info['filePath']
                        if hasattr(path, 'toString'):
                            path = path.toString()

                        # Remove file:/// prefix if present
                        if path.startswith('file:///'):
                            path = path[8:] if path[9] == ':' else path[7:]  # Handle Windows paths

                        file_info['filePath'] = path

                    file_attachments.append(file_info)

            # Add user message
            user_message = await self.conversation_service.add_user_message(
                conversation_id, content
            )

            if not user_message:
                raise RuntimeError("Failed to add user message")

            # Add file attachments if any
            for file_info in file_attachments:
                await self.conversation_service.add_file_attachment(
                    user_message.id, file_info
                )

            # Update UI
            self.messageAdded.emit(user_message)

            # Get the updated branch
            branch = await self.conversation_service.get_message_branch(user_message.id)
            self._current_branch = branch
            self.messageBranchChanged.emit(branch)

            # Get API settings
            settings = {}  # You would get this from a settings service

            # Prepare messages for API
            messages = self._prepare_messages_for_api(branch)

            # Get streaming response
            async for item in self.api_service.get_streaming_completion(messages, settings):
                # This will be handled by signal connections
                pass

            # Add assistant message with accumulated content
            assistant_message = await self.conversation_service.add_assistant_message(
                conversation_id,
                self._stream_buffer,
                parent_id=user_message.id,
                model_info=self._model_info,
                token_usage=self._token_usage,
                reasoning_steps=self._reasoning_steps,
                response_id=self.api_service.last_response_id
            )

            # Reset buffer
            self._stream_buffer = ""

            # Update UI
            self.messageAdded.emit(assistant_message)

            # Get the updated branch
            branch = await self.conversation_service.get_message_branch(assistant_message.id)
            self._current_branch = branch
            self.messageBranchChanged.emit(branch)

            return assistant_message
        except Exception as e:
            self.logger.error(f"Error in send_message: {str(e)}")
            raise

    def _finish_messaging(self):
        """Handle completion of messaging"""
        self._is_loading = False
        self.loadingStateChanged.emit(False)
        self.messagingComplete.emit()

    def _handle_messaging_error(self, error):
        """Handle error during messaging"""
        self.logger.error(f"Messaging error: {str(error)}")
        self.errorOccurred.emit(f"Error during messaging: {str(error)}")

        # Reset loading state
        self._is_loading = False
        self.loadingStateChanged.emit(False)

    @pyqtSlot(str)
    def navigate_to_message(self, message_id):
        """Navigate to a specific message in the conversation"""
        self.logger.debug(f"Navigating to message: {message_id}")

        run_coroutine(
            self._navigate_to_message_impl(message_id),
            error_callback=lambda e: self.errorOccurred.emit(f"Error navigating to message: {str(e)}")
        )

    async def _navigate_to_message_impl(self, message_id):
        """Implementation of navigate_to_message"""
        try:
            # Get the message
            message = await self.conversation_service.get_message(message_id)

            if not message:
                raise ValueError(f"Message {message_id} not found")

            # Set as current message in conversation
            success = await self.conversation_service.navigate_to_message(
                message.conversation_id, message_id
            )

            if not success:
                raise RuntimeError(f"Failed to navigate to message {message_id}")

            # Get the branch
            branch = await self.conversation_service.get_message_branch(message_id)
            self._current_branch = branch
            self.messageBranchChanged.emit(branch)

            return branch
        except Exception as e:
            self.logger.error(f"Error navigating to message: {str(e)}")
            raise

    @pyqtSlot()
    def retry_last_response(self):
        """Retry the last assistant response"""
        self.logger.debug("Retrying last response")

        if not self._current_branch or len(self._current_branch) < 2:
            self.logger.warning("Cannot retry - no message to retry")
            return

        # Find the last user message
        user_message = None
        for i in range(len(self._current_branch) - 1, -1, -1):
            if self._current_branch[i].role == "user":
                user_message = self._current_branch[i]
                break

        if not user_message:
            self.logger.warning("Cannot retry - no user message found")
            return

        # Navigate to the user message and then send it again
        run_coroutine(
            self._retry_last_response_impl(user_message),
            error_callback=lambda e: self.errorOccurred.emit(f"Error retrying response: {str(e)}")
        )

    async def _retry_last_response_impl(self, user_message):
        """Implementation of retry_last_response"""
        try:
            # Navigate to the user message
            await self._navigate_to_message_impl(user_message.id)

            # Get attachments if any
            attachments = []
            if user_message.file_attachments:
                for attachment in user_message.file_attachments:
                    attachments.append({
                        'fileName': attachment.file_name,
                        'filePath': attachment.storage_path,
                        'content': attachment.content,
                        'tokenCount': attachment.token_count,
                        'size': attachment.file_size
                    })

            # Re-send the message
            await self._send_message_impl(
                user_message.conversation_id,
                user_message.content,
                attachments
            )

            return True
        except Exception as e:
            self.logger.error(f"Error retrying response: {str(e)}")
            raise

    @pyqtSlot(str, str, result="QVariant")
    def search_conversations(self, search_term, conversation_id=None):
        """
        Search for messages containing the search term

        This is a synchronous method that returns a Future, since QML expects
        a direct return value. The Future will be resolved when the search completes.
        """
        self.logger.debug(f"Searching for '{search_term}' in conversations")

        loop = ensure_qasync_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._search_conversations_impl(search_term, conversation_id),
            loop
        )

        # Return empty results for now, search will update the model when done
        return []

    async def _search_conversations_impl(self, search_term, conversation_id=None):
        """Implementation of search_conversations"""
        try:
            # Perform the search
            results = await self.conversation_service.search_conversations(
                search_term, conversation_id
            )

            return results
        except Exception as e:
            self.logger.error(f"Error searching conversations: {str(e)}")
            raise

    @pyqtSlot(result="QVariant")
    def get_all_conversations(self):
        """
        Get all conversations

        This is a synchronous method that returns a Future, since QML expects
        a direct return value. The Future will be resolved when the data is ready.
        """
        self.logger.debug("Getting all conversations")

        loop = ensure_qasync_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._get_all_conversations_impl(),
            loop
        )

        try:
            # Wait for a short time to get the result
            return future.result(0.5)  # 500ms timeout
        except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
            # Return empty list if timeout
            self.logger.warning("Timeout getting conversations, returning empty list")
            return []
        except Exception as e:
            self.logger.error(f"Error getting conversations: {str(e)}")
            return []

    async def _get_all_conversations_impl(self):
        """Implementation of get_all_conversations"""
        try:
            # Get all conversations
            conversations = await self.conversation_service.get_all_conversations()

            # Convert to list of dicts
            result = []
            for conv in conversations:
                result.append({
                    'id': conv.id,
                    'name': conv.name,
                    'modified_at': conv.modified_at.isoformat() if conv.modified_at else None,
                    'created_at': conv.created_at.isoformat() if conv.created_at else None
                })

            return result
        except Exception as e:
            self.logger.error(f"Error getting all conversations: {str(e)}")
            raise

    def _prepare_messages_for_api(self, messages):
        """Prepare messages for the API from a branch"""
        # This would extract the relevant data from the message objects
        # and format it as expected by the API service
        result = []
        for msg in messages:
            if msg.role == "system" and msg == messages[0]:
                # First message is system message
                result.append({
                    "role": "system",
                    "content": msg.content
                })
            elif msg.role in ["user", "assistant"]:
                message_data = {
                    "role": msg.role,
                    "content": msg.content
                }

                # Add file attachments if any
                if msg.file_attachments:
                    message_data["attached_files"] = []
                    for attachment in msg.file_attachments:
                        message_data["attached_files"].append({
                            "file_name": attachment.file_name,
                            "content": attachment.content
                        })

                result.append(message_data)

        return result

    # Signal handlers for API service
    def _on_request_started(self):
        """Handle API request started"""
        self._is_loading = True
        self.loadingStateChanged.emit(True)

    def _on_request_finished(self):
        """Handle API request finished"""
        self._is_loading = False
        self.loadingStateChanged.emit(False)

    def _on_chunk_received(self, chunk):
        """Handle receiving a chunk from streaming API"""
        # Accumulate in buffer
        self._stream_buffer += chunk

        # Emit signal with the chunk
        self.messageStreamChunk.emit(chunk)

    def _on_metadata_received(self, metadata):
        """Handle receiving metadata from API"""
        if "token_usage" in metadata:
            self._token_usage = metadata["token_usage"]
            self.tokenUsageUpdated.emit(self._token_usage)

        if "model" in metadata:
            self._model_info = {"model": metadata["model"]}

        if "reasoning_step" in metadata:
            if not self._reasoning_steps:
                self._reasoning_steps = []

            self._reasoning_steps.append(metadata["reasoning_step"])
            self.reasoningStepsChanged.emit(self._reasoning_steps)

    def _on_error_occurred(self, error_message):
        """Handle API error"""
        self.errorOccurred.emit(f"API Error: {error_message}")

        # Reset loading state
        self._is_loading = False
        self.loadingStateChanged.emit(False)

    async def cleanup(self):
        """Cleanup resources"""
        self.logger.info("Cleaning up ViewModel resources")

        # Clean up API service if it has a cleanup method
        if hasattr(self.api_service, 'close'):
            await self.api_service.close()

        self.logger.info("ViewModel cleanup completed")