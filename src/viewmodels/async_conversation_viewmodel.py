"""
ViewModel for managing conversation interactions using properly integrated async patterns.
"""

import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator, Union

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from src.utils.reactive import ReactiveProperty, ReactiveList, ReactiveDict, ReactiveViewModel
from src.services.db_service import ConversationService
from src.services.async_api_service import AsyncApiService
from src.utils.qasync_bridge import run_coroutine
from src.utils.logging_utils import get_logger


class AsyncConversationViewModel(ReactiveViewModel):
    """ViewModel for managing conversation interactions using async/await patterns"""

    # Signal definitions (these must match what QML expects)
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
        super().__init__()
        self.logger = get_logger(__name__)
        self.conversation_service = ConversationService()
        self.api_service = AsyncApiService()

        # Reactive state
        self.current_conversation_id = ReactiveProperty(None)
        self.current_branch = ReactiveProperty([])
        self.is_loading = ReactiveProperty(False)
        self.token_usage = ReactiveProperty({})
        self.stream_buffer = ReactiveProperty("")
        self.model_info = ReactiveProperty({})
        self.reasoning_steps = ReactiveList()
        
        # Set up signal connections from API service
        self.api_service.requestStarted.connect(self._on_request_started)
        self.api_service.requestFinished.connect(self._on_request_finished)
        self.api_service.chunkReceived.connect(self._on_chunk_received)
        self.api_service.metadataReceived.connect(self._on_metadata_received)
        self.api_service.errorOccurred.connect(self._on_error_occurred)

        # Set up reactive data flow using old-style connects to avoid async issues
        self.current_conversation_id.observe().subscribe(self._react_to_conversation_id)

        # 2. Connect reactive properties to signals
        self.connect_reactive_property(self.is_loading, 'loadingStateChanged')
        self.connect_reactive_property(self.token_usage, 'tokenUsageUpdated')
        self.connect_reactive_property(self.current_branch, 'messageBranchChanged')

        # 3. Set up reasoning steps observation
        self.reasoning_steps.observe_added().subscribe(
            lambda step: self.reasoningStepsChanged.emit(self.reasoning_steps.items)
        )

        # 4. Set up stream buffer handling
        self.stream_buffer.observe().subscribe(
            lambda buffer: self._handle_buffer_update(buffer)
        )

    def _react_to_conversation_id(self, conversation_id):
        """React to conversation ID changes safely without directly using async"""
        if conversation_id:
            # Use direct synchronous database access instead of async
            self._load_conversation_by_id_sync(conversation_id)

    def _on_request_started(self):
        """Handle API request started"""
        self.is_loading.set(True)

    def _on_request_finished(self):
        """Handle API request finished"""
        self.is_loading.set(False)
        self.messagingComplete.emit()

    def _on_chunk_received(self, chunk):
        """Handle streaming chunk received"""
        # Append to the buffer
        current_buffer = self.stream_buffer.get()
        self.stream_buffer.set(current_buffer + chunk)

        # Also emit the chunk directly for UI updates
        self.messageStreamChunk.emit(chunk)

    def _on_metadata_received(self, metadata):
        """Handle metadata received from API"""
        if "token_usage" in metadata:
            self.token_usage.set(metadata["token_usage"])
            self.tokenUsageUpdated.emit(metadata["token_usage"])

        if "model" in metadata:
            self.model_info.set({"model": metadata["model"]})

        if "reasoning_step" in metadata:
            self.reasoning_steps.append(metadata["reasoning_step"])

    def _on_error_occurred(self, error_message):
        """Handle API error"""
        self.errorOccurred.emit(error_message)

    def _handle_buffer_update(self, buffer):
        """Handle updates to the stream buffer"""
        # This is just for debugging or additional processing if needed
        pass

    def _load_conversation_by_id_sync(self, conversation_id):
        """Load a conversation by ID (synchronous version)"""
        if not conversation_id:
            return

        try:
            # Load the conversation from database
            conversation = self.conversation_service.get_conversation(conversation_id)
            if conversation:
                self.conversationLoaded.emit(conversation)

                # Also get the current message branch
                current_node_id = conversation.current_node_id
                if current_node_id:
                    branch = self.conversation_service.get_message_branch(current_node_id)
                    self.current_branch.set(branch)
        except Exception as e:
            self.logger.error(f"Error loading conversation: {str(e)}")
            self.errorOccurred.emit(f"Error loading conversation: {str(e)}")

    async def _load_conversation_by_id(self, conversation_id):
        """Async version - only used when explicitly called with run_coroutine"""
        return self._load_conversation_by_id_sync(conversation_id)

    @pyqtSlot(str)
    def load_conversation(self, conversation_id):
        """Load a conversation by ID (public slot)"""
        self.current_conversation_id.set(conversation_id)

    @pyqtSlot(result=list)
    def get_all_conversations(self):
        """Get all conversations for display in UI"""
        try:
            conversations = self.conversation_service.get_all_conversations()
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
            self.errorOccurred.emit(f"Error loading conversations: {str(e)}")
            return []

    @pyqtSlot(str)
    def create_new_conversation(self, name="New Conversation"):
        """Create a new conversation"""
        try:
            self.logger.info(f"Creating new conversation with name: {name}")
            conversation = self.conversation_service.create_conversation(name=name)
            if conversation:
                self.logger.info(f"Created conversation with ID: {conversation.id}")
                # Set as current conversation
                self.current_conversation_id.set(conversation.id)
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
        try:
            success = self.conversation_service.update_conversation(conversation_id, name=new_name)
            if success and conversation_id == self.current_conversation_id.get():
                # Reload the conversation to refresh UI
                self._load_conversation_by_id_sync(conversation_id)
            return success
        except Exception as e:
            self.logger.error(f"Error renaming conversation: {str(e)}")
            self.errorOccurred.emit(f"Error renaming conversation: {str(e)}")
            return False

    @pyqtSlot(str)
    def delete_conversation(self, conversation_id):
        """Delete a conversation"""
        try:
            success = self.conversation_service.delete_conversation(conversation_id)
            if success and conversation_id == self.current_conversation_id.get():
                # Clear current conversation
                self.current_conversation_id.set(None)
                self.current_branch.set([])
            return success
        except Exception as e:
            self.logger.error(f"Error deleting conversation: {str(e)}")
            self.errorOccurred.emit(f"Error deleting conversation: {str(e)}")
            return False

    @pyqtSlot(str, str, list)
    def send_message(self, conversation_id, content, attachments=None):
        """Send a user message and get the assistant's response"""
        # Return early if already loading
        if self.is_loading.get():
            self.errorOccurred.emit("Already processing a message")
            return

        # Start the process without depending on async/await
        self._send_message_impl(conversation_id, content, attachments)

    def _send_message_impl(self, conversation_id, content, attachments=None):
        """Implementation of send_message without async/await"""
        try:
            # 1. Reset stream buffer and reasoning steps
            self.stream_buffer.set("")
            self.reasoning_steps.clear()

            # 2. Add the user message to the database
            user_message = self.conversation_service.add_user_message(conversation_id, content)
            if not user_message:
                raise Exception("Failed to add user message")

            # 3. Add file attachments if any
            if attachments:
                for attachment in attachments:
                    self.conversation_service.add_file_attachment(user_message.id, attachment)

            # 4. Emit that message was added and update branch
            self.messageAdded.emit(user_message)
            branch = self.conversation_service.get_message_branch(user_message.id)
            self.current_branch.set(branch)

            # 5. Get all messages in the branch for API call
            messages = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "attached_files": self._prepare_attachments(msg) if hasattr(msg, 'file_attachments') else []
                }
                for msg in branch
            ]

            # 6. Set up callbacks to handle API response
            def on_streaming_done(result):
                # When streaming is complete, save the assistant's response
                self._save_assistant_response_sync(conversation_id)

            def on_streaming_error(err):
                self.is_loading.set(False)
                self.logger.error(f"Error in streaming: {str(err)}")
                self.errorOccurred.emit(f"Error in streaming: {str(err)}")

            # 7. Start streaming API call using run_coroutine
            run_coroutine(
                self._do_streaming(messages),
                callback=on_streaming_done,
                error_callback=on_streaming_error
            )

        except Exception as e:
            self.is_loading.set(False)
            self.logger.error(f"Error sending message: {str(e)}")
            self.errorOccurred.emit(f"Error sending message: {str(e)}")

    async def _do_streaming(self, messages):
        """Coroutine to handle the streaming API call"""
        try:
            # Start streaming API call
            async for _ in self.api_service.get_streaming_completion(messages):
                # No need to do anything here as we're using signals for handling events
                pass
            return True
        except Exception as e:
            self.logger.error(f"Error in _do_streaming: {str(e)}")
            raise

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

    def _save_assistant_response_sync(self, conversation_id):
        """Save the assistant response to the database after streaming completes"""
        # Get the final content from the stream buffer
        content = self.stream_buffer.get()
        if not content:
            return

        try:
            # Save to database
            assistant_message = self.conversation_service.add_assistant_message(
                conversation_id=conversation_id,
                content=content,
                model_info=self.model_info.get(),
                token_usage=self.token_usage.get(),
                reasoning_steps=self.reasoning_steps.items,
                response_id=self.api_service.last_response_id
            )

            # Update branch and notify UI
            self.messageAdded.emit(assistant_message)
            branch = self.conversation_service.get_message_branch(assistant_message.id)
            self.current_branch.set(branch)

        except Exception as e:
            self.logger.error(f"Error saving assistant response: {str(e)}")
            self.errorOccurred.emit(f"Error saving assistant response: {str(e)}")

    @pyqtSlot(str)
    def navigate_to_message(self, message_id):
        """Navigate to a specific message in the conversation"""
        current_id = self.current_conversation_id.get()
        if not current_id:
            return

        try:
            success = self.conversation_service.navigate_to_message(current_id, message_id)

            if success:
                # Update branch
                branch = self.conversation_service.get_message_branch(message_id)
                self.current_branch.set(branch)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error navigating to message: {str(e)}")
            self.errorOccurred.emit(f"Error navigating to message: {str(e)}")
            return False

    @pyqtSlot()
    def retry_last_response(self):
        """Retry generating a response for the current user message"""
        if not self.current_conversation_id.get() or self.is_loading.get():
            return

        # Start the process without depending on async/await
        self._retry_last_response_impl()

    def _retry_last_response_impl(self):
        """Implementation of retry_last_response without async/await"""
        try:
            # Get the current conversation
            conversation_id = self.current_conversation_id.get()
            conversation = self.conversation_service.get_conversation(conversation_id)
            if not conversation or not conversation.current_node_id:
                return

            current_message = self.conversation_service.get_message(conversation.current_node_id)

            # If current message is assistant, navigate to its parent (user message)
            if current_message.role == "assistant" and current_message.parent_id:
                # Navigate to parent message
                self.navigate_to_message(current_message.parent_id)

                # Get the branch up to the user message
                branch = self.conversation_service.get_message_branch(current_message.parent_id)

                # Prepare messages for API call
                messages = [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "attached_files": self._prepare_attachments(msg) if hasattr(msg, 'file_attachments') else []
                    }
                    for msg in branch
                ]

                # Reset stream buffer and reasoning steps
                self.stream_buffer.set("")
                self.reasoning_steps.clear()

                # Set up callbacks to handle API response
                def on_streaming_done(result):
                    # When streaming is complete, save the assistant's response
                    self._save_assistant_response_sync(conversation_id)

                def on_streaming_error(err):
                    self.is_loading.set(False)
                    self.logger.error(f"Error in streaming: {str(err)}")
                    self.errorOccurred.emit(f"Error in streaming: {str(err)}")

                # Start streaming API call using run_coroutine
                run_coroutine(
                    self._do_streaming(messages),
                    callback=on_streaming_done,
                    error_callback=on_streaming_error
                )

        except Exception as e:
            self.is_loading.set(False)
            self.logger.error(f"Error retrying message: {str(e)}")
            self.errorOccurred.emit(f"Error retrying message: {str(e)}")

    @pyqtSlot(str, str, result=list)
    def search_conversations(self, search_term, conversation_id=None):
        """Search for messages containing the search term"""
        try:
            results = self.conversation_service.search_conversations(
                search_term,
                conversation_id=conversation_id if conversation_id else None
            )
            return results
        except Exception as e:
            self.logger.error(f"Error searching conversations: {str(e)}")
            self.errorOccurred.emit(f"Error searching conversations: {str(e)}")
            return []

    @pyqtSlot(str, str, result=str)
    def duplicate_conversation(self, conversation_id: str, new_name: str = None) -> str:
        """Duplicate a conversation, making it the active conversation"""
        try:
            # Duplicate the conversation using the service
            new_conversation = self.conversation_service.duplicate_conversation(conversation_id, new_name)

            if new_conversation:
                # Set the current conversation ID using the reactive property
                self.current_conversation_id.set(new_conversation.id)
                return new_conversation.id
            else:
                self.errorOccurred.emit(f"Failed to duplicate conversation")
                return None
        except Exception as e:
            self.logger.error(f"Error duplicating conversation: {str(e)}")
            self.errorOccurred.emit(f"Error duplicating conversation: {str(e)}")
            return None