"""
Fully asynchronous ViewModel for managing conversation interactions.
Uses pure asyncio without dependencies on the reactive model.
"""

import asyncio
import uuid
from typing import List, Dict, Any, Optional, AsyncGenerator, Union

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from src.services.database import AsyncConversationService
from src.services.api import AsyncApiService
from src.utils.qasync_bridge import run_coroutine
from src.utils.logging_utils import get_logger


class FullAsyncConversationViewModel(QObject):
    """
    ViewModel for managing conversation interactions using pure async/await patterns
    without reactive programming dependencies.
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

        # Set up signal connections from API service
        self.api_service.requestStarted.connect(self._on_request_started)
        self.api_service.requestFinished.connect(self._on_request_finished)
        self.api_service.chunkReceived.connect(self._on_chunk_received)
        self.api_service.metadataReceived.connect(self._on_metadata_received)
        self.api_service.errorOccurred.connect(self._on_error_occurred)

        # Initialize the services asynchronously
        run_coroutine(
            self.initialize(),
            callback=lambda _: self.logger.info("ViewModel initialized"),
            error_callback=lambda e: self.logger.error(f"Failed to initialize services: {str(e)}")
        )

        self.logger.info("FullAsyncConversationViewModel constructor completed")

    # API event handlers
    def _on_request_started(self):
        """Handle API request started"""
        self._is_loading = True
        self.loadingStateChanged.emit(True)

    def _on_request_finished(self):
        """Handle API request finished"""
        self._is_loading = False
        self.loadingStateChanged.emit(False)
        self.messagingComplete.emit()

    def _on_chunk_received(self, chunk):
        """Handle streaming chunk received"""
        self._stream_buffer += chunk
        self.messageStreamChunk.emit(chunk)

    def _on_metadata_received(self, metadata):
        """Handle metadata received from API"""
        if "token_usage" in metadata:
            self._token_usage = metadata["token_usage"]
            self.tokenUsageUpdated.emit(metadata["token_usage"])

        if "model" in metadata:
            self._model_info = {"model": metadata["model"]}

        if "reasoning_step" in metadata:
            self._reasoning_steps.append(metadata["reasoning_step"])
            self.reasoningStepsChanged.emit(self._reasoning_steps)

    def _on_error_occurred(self, error_message):
        """Handle API error"""
        self.errorOccurred.emit(error_message)

    # Initialization
    async def initialize(self):
        """Initialize services"""
        if not self._initialized:
            try:
                await self.conversation_service.initialize()
                self._initialized = True
                self.logger.info("Services initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize services: {str(e)}")
                self.errorOccurred.emit(f"Failed to initialize services: {str(e)}")

    # Conversation management methods
    @pyqtSlot(str)
    def load_conversation(self, conversation_id):
        """Load a conversation by ID (public slot)"""
        if conversation_id == self._current_conversation_id:
            return  # Already loaded

        self._current_conversation_id = conversation_id

        run_coroutine(
            self._load_conversation_async(conversation_id),
            error_callback=lambda e: self.errorOccurred.emit(f"Error loading conversation: {str(e)}")
        )

    async def _load_conversation_async(self, conversation_id):
        """Async implementation of load_conversation"""
        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            # Load the conversation from database
            conversation = await self.conversation_service.get_conversation(conversation_id)
            if conversation:
                self.conversationLoaded.emit(conversation)

                # Also get the current message branch
                current_node_id = conversation.current_node_id
                if current_node_id:
                    branch = await self.conversation_service.get_message_branch(current_node_id)
                    self._current_branch = branch
                    self.messageBranchChanged.emit(branch)

            return conversation
        except Exception as e:
            self.logger.error(f"Error loading conversation: {str(e)}")
            self.errorOccurred.emit(f"Error loading conversation: {str(e)}")
            return None

    @pyqtSlot(str)
    def create_new_conversation(self, name="New Conversation"):
        """Create a new conversation"""
        run_coroutine(
            self._create_new_conversation_async(name),
            callback=lambda conversation: self.load_conversation(conversation.id) if conversation else None,
            error_callback=lambda e: self.errorOccurred.emit(f"Error creating conversation: {str(e)}")
        )

    async def _create_new_conversation_async(self, name="New Conversation"):
        """Async implementation of create_new_conversation"""
        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            self.logger.info(f"Creating new conversation with name: {name}")
            conversation = await self.conversation_service.create_conversation(name=name)

            if conversation:
                self.logger.info(f"Created conversation with ID: {conversation.id}")
                return conversation
            else:
                self.errorOccurred.emit("Failed to create conversation")
                return None
        except Exception as e:
            self.logger.error(f"Error creating conversation: {str(e)}")
            self.errorOccurred.emit(f"Error creating conversation: {str(e)}")
            return None

    @pyqtSlot(str, str)
    def rename_conversation(self, conversation_id, new_name):
        """Rename a conversation"""
        run_coroutine(
            self._rename_conversation_async(conversation_id, new_name),
            callback=lambda success: self.load_conversation(conversation_id) if success and conversation_id == self._current_conversation_id else None,
            error_callback=lambda e: self.errorOccurred.emit(f"Error renaming conversation: {str(e)}")
        )

    async def _rename_conversation_async(self, conversation_id, new_name):
        """Async implementation of rename_conversation"""
        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            return await self.conversation_service.update_conversation(conversation_id, name=new_name)
        except Exception as e:
            self.logger.error(f"Error renaming conversation: {str(e)}")
            self.errorOccurred.emit(f"Error renaming conversation: {str(e)}")
            return False

    @pyqtSlot(str)
    def delete_conversation(self, conversation_id):
        """Delete a conversation"""
        run_coroutine(
            self._delete_conversation_async(conversation_id),
            callback=lambda success: self._clear_current_conversation() if success and conversation_id == self._current_conversation_id else None,
            error_callback=lambda e: self.errorOccurred.emit(f"Error deleting conversation: {str(e)}")
        )

    def _clear_current_conversation(self):
        """Clear current conversation after deletion"""
        self._current_conversation_id = None
        self._current_branch = []
        self.messageBranchChanged.emit([])

    async def _delete_conversation_async(self, conversation_id):
        """Async implementation of delete_conversation"""
        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            return await self.conversation_service.delete_conversation(conversation_id)
        except Exception as e:
            self.logger.error(f"Error deleting conversation: {str(e)}")
            self.errorOccurred.emit(f"Error deleting conversation: {str(e)}")
            return False

    @pyqtSlot(str, str, list)
    def send_message(self, conversation_id, content, attachments=None):
        """Send a user message and get the assistant's response"""
        # Return early if already loading
        if self._is_loading:
            self.errorOccurred.emit("Already processing a message")
            return

        # Start the async process
        run_coroutine(
            self._send_message_async(conversation_id, content, attachments),
            error_callback=lambda e: self.errorOccurred.emit(f"Error sending message: {str(e)}")
        )

    async def _send_message_async(self, conversation_id, content, attachments=None):
        """Async implementation of send_message"""
        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            # 1. Reset state
            self._stream_buffer = ""
            self._reasoning_steps = []

            # 2. Add the user message to the database
            user_message = await self.conversation_service.add_user_message(conversation_id, content)
            if not user_message:
                raise Exception("Failed to add user message")

            # 3. Add file attachments if any
            if attachments:
                for attachment in attachments:
                    await self.conversation_service.add_file_attachment(user_message.id, attachment)

            # 4. Emit that message was added and update branch
            self.messageAdded.emit(user_message)
            branch = await self.conversation_service.get_message_branch(user_message.id)
            self._current_branch = branch
            self.messageBranchChanged.emit(branch)

            # 5. Get all messages in the branch for API call
            messages = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "attached_files": self._prepare_attachments(msg) if hasattr(msg, 'file_attachments') else []
                }
                for msg in branch
            ]

            # 6. Start streaming API call
            try:
                async for _ in self.api_service.get_streaming_completion(messages):
                    # Events are handled through signals, we don't need to do anything here
                    pass

                # 7. Save the assistant response after streaming completes
                await self._save_assistant_response_async(conversation_id)

            except Exception as e:
                self.logger.error(f"Error in streaming API call: {str(e)}")
                self.errorOccurred.emit(f"Error in streaming API call: {str(e)}")

        except Exception as e:
            self.logger.error(f"Error sending message: {str(e)}")
            self.errorOccurred.emit(f"Error sending message: {str(e)}")

    def _prepare_attachments(self, message):
        """Prepare attachments for API call"""
        if not hasattr(message, 'file_attachments') or not message.file_attachments:
            return []

        attachments = []
        for attachment in message.file_attachments:
            attachments.append({
                "file_name": attachment.file_name,
                "mime_type": attachment.mime_type,
                "content": attachment.content,
                "token_count": attachment.token_count
            })
        return attachments

    async def _save_assistant_response_async(self, conversation_id):
        """Async implementation of saving assistant response"""
        # Get the final content from the stream buffer
        content = self._stream_buffer
        if not content:
            return

        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            # Save to database
            assistant_message = await self.conversation_service.add_assistant_message(
                conversation_id=conversation_id,
                content=content,
                model_info=self._model_info,
                token_usage=self._token_usage,
                reasoning_steps=self._reasoning_steps,
                response_id=self.api_service.last_response_id
            )

            # Update branch and notify UI
            self.messageAdded.emit(assistant_message)
            branch = await self.conversation_service.get_message_branch(assistant_message.id)
            self._current_branch = branch
            self.messageBranchChanged.emit(branch)

        except Exception as e:
            self.logger.error(f"Error saving assistant response: {str(e)}")
            self.errorOccurred.emit(f"Error saving assistant response: {str(e)}")

    @pyqtSlot(str)
    def navigate_to_message(self, message_id):
        """Navigate to a specific message in the conversation"""
        current_id = self._current_conversation_id
        if not current_id:
            return

        run_coroutine(
            self._navigate_to_message_async(current_id, message_id),
            error_callback=lambda e: self.errorOccurred.emit(f"Error navigating to message: {str(e)}")
        )

    async def _navigate_to_message_async(self, conversation_id, message_id):
        """Async implementation of navigate_to_message"""
        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            success = await self.conversation_service.navigate_to_message(conversation_id, message_id)

            if success:
                # Update branch
                branch = await self.conversation_service.get_message_branch(message_id)
                self._current_branch = branch
                self.messageBranchChanged.emit(branch)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error navigating to message: {str(e)}")
            self.errorOccurred.emit(f"Error navigating to message: {str(e)}")
            return False

    @pyqtSlot()
    def retry_last_response(self):
        """Retry generating a response for the current user message"""
        if not self._current_conversation_id or self._is_loading:
            return

        run_coroutine(
            self._retry_last_response_async(),
            error_callback=lambda e: self.errorOccurred.emit(f"Error retrying message: {str(e)}")
        )

    async def _retry_last_response_async(self):
        """Async implementation of retry_last_response"""
        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            # Get the current conversation
            conversation_id = self._current_conversation_id
            conversation = await self.conversation_service.get_conversation(conversation_id)
            if not conversation or not conversation.current_node_id:
                return

            current_message = await self.conversation_service.get_message(conversation.current_node_id)

            # If current message is assistant, navigate to its parent (user message)
            if current_message.role == "assistant" and current_message.parent_id:
                # Navigate to parent message
                await self._navigate_to_message_async(conversation_id, current_message.parent_id)

                # Get the branch up to the user message
                branch = await self.conversation_service.get_message_branch(current_message.parent_id)

                # Prepare messages for API call
                messages = [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "attached_files": self._prepare_attachments(msg) if hasattr(msg, 'file_attachments') else []
                    }
                    for msg in branch
                ]

                # Reset state for the new response
                self._stream_buffer = ""
                self._reasoning_steps = []

                # Start streaming API call
                try:
                    async for _ in self.api_service.get_streaming_completion(messages):
                        # Events are handled through signals
                        pass

                    # Save the assistant response after streaming completes
                    await self._save_assistant_response_async(conversation_id)

                except Exception as e:
                    self.logger.error(f"Error in streaming API call during retry: {str(e)}")
                    self.errorOccurred.emit(f"Error in streaming API call: {str(e)}")

        except Exception as e:
            self.logger.error(f"Error retrying message: {str(e)}")
            self.errorOccurred.emit(f"Error retrying message: {str(e)}")

    # Search methods
    @pyqtSlot(str, str, result=list)
    def search_conversations(self, search_term, conversation_id=None):
        """Search for messages containing the search term"""
        try:
            if not search_term:
                return []

            # Execute search asynchronously but in a blocking way for QML
            from qasync import QEventLoop
            loop = asyncio.get_event_loop()
            if not isinstance(loop, QEventLoop):
                self.logger.warning("Not running in QEventLoop - search may be unstable")

            future = asyncio.run_coroutine_threadsafe(
                self._search_conversations_async(search_term, conversation_id),
                loop
            )

            # Wait for result with timeout
            try:
                return future.result(timeout=10)
            except asyncio.TimeoutError:
                self.logger.error("Search timed out")
                self.errorOccurred.emit("Search timed out")
                return []

        except Exception as e:
            self.logger.error(f"Error executing search: {str(e)}")
            self.errorOccurred.emit(f"Error searching conversations: {str(e)}")
            return []

    async def _search_conversations_async(self, search_term, conversation_id=None) -> List[Dict[str, Any]]:
        """
        Async implementation of search_conversations

        Args:
            search_term: Text to search for
            conversation_id: Optional conversation ID to limit search

        Returns:
            List of matching message dictionaries
        """
        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            self.logger.debug(f"Performing async search for: {search_term}")
            return await self.conversation_service.search_conversations(search_term, conversation_id)
        except Exception as e:
            self.logger.error(f"Error searching conversations: {str(e)}")
            raise

    # Duplicate conversation
    @pyqtSlot(str, str, result=str)
    def duplicate_conversation(self, conversation_id: str, new_name: str = None) -> str:
        """Duplicate a conversation, making it the active conversation"""
        try:
            from qasync import QEventLoop
            loop = asyncio.get_event_loop()
            if not isinstance(loop, QEventLoop):
                self.logger.warning("Not running in QEventLoop - operation may be unstable")

            future = asyncio.run_coroutine_threadsafe(
                self._duplicate_conversation_async(conversation_id, new_name),
                loop
            )

            # Wait for result with timeout
            try:
                return future.result(timeout=30) or ""
            except asyncio.TimeoutError:
                self.logger.error("Duplication timed out")
                self.errorOccurred.emit("Duplication timed out")
                return ""

        except Exception as e:
            self.logger.error(f"Error duplicating conversation: {str(e)}")
            self.errorOccurred.emit(f"Error duplicating conversation: {str(e)}")
            return ""

    async def _duplicate_conversation_async(self, conversation_id: str, new_name: str = None) -> Optional[str]:
        """Async implementation of duplicate_conversation"""
        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            new_conversation = await self.conversation_service.duplicate_conversation(conversation_id, new_name)

            if new_conversation:
                # Set the current conversation ID
                self._current_conversation_id = new_conversation.id
                # Load the conversation
                await self._load_conversation_async(new_conversation.id)
                return new_conversation.id
            else:
                self.errorOccurred.emit("Failed to duplicate conversation")
                return None
        except Exception as e:
            self.logger.error(f"Error duplicating conversation: {str(e)}")
            raise

    # API methods used by QML
    @pyqtSlot(result=list)
    def get_all_conversations(self):
        """Get all conversations for display in UI"""
        try:
            from qasync import QEventLoop
            loop = asyncio.get_event_loop()
            if not isinstance(loop, QEventLoop):
                self.logger.warning("Not running in QEventLoop - operation may be unstable")

            future = asyncio.run_coroutine_threadsafe(
                self._get_all_conversations_async(),
                loop
            )

            # Wait for result with timeout
            try:
                return future.result(timeout=10) or []
            except asyncio.TimeoutError:
                self.logger.error("Get all conversations timed out")
                self.errorOccurred.emit("Get all conversations timed out")
                return []

        except Exception as e:
            self.logger.error(f"Error getting all conversations: {str(e)}")
            self.errorOccurred.emit(f"Error getting all conversations: {str(e)}")
            return []

    async def _get_all_conversations_async(self):
        """Async implementation of get_all_conversations"""
        try:
            # Ensure initialized
            if not self._initialized:
                await self.initialize()

            conversations = await self.conversation_service.get_all_conversations()

            # Convert to list of dicts for QML
            return [
                {
                    'id': conv.id,
                    'name': conv.name,
                    'created_at': conv.created_at.isoformat(),
                    'modified_at': conv.modified_at.isoformat()
                }
                for conv in conversations
            ]
        except Exception as e:
            self.logger.error(f"Error loading conversations: {str(e)}")
            raise

    async def cleanup(self):
        """Clean up resources"""
        self.logger.debug("Cleaning up FullAsyncConversationViewModel resources")

        # Close the async conversation service
        if hasattr(self.conversation_service, 'close'):
            await self.conversation_service.close()

        self.logger.info("FullAsyncConversationViewModel resources cleaned up")