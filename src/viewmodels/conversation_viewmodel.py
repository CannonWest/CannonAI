# src/viewmodels/conversation_viewmodel.py

from typing import List, Dict, Any, Optional, Callable
import asyncio
import threading
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer

from src.services.db_service import ConversationService
from src.models.orm_models import Conversation, Message, FileAttachment
from src.services.api_service import ApiService


class ConversationViewModel(QObject):
    """ViewModel for managing conversation interactions"""

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
        super().__init__()
        self.conversation_service = ConversationService()
        self.api_service = ApiService()

        # State management
        self.current_conversation_id = None
        self.is_streaming = False
        self.is_loading = False
        self._api_settings = {}
        self._current_api_call = None
        self._buffer = ""

    @pyqtSlot(str)
    def load_conversation(self, conversation_id: str) -> None:
        """Load a conversation by ID"""
        try:
            conversation = self.conversation_service.get_conversation(conversation_id)
            if conversation:
                self.current_conversation_id = conversation_id
                self.conversationLoaded.emit(conversation)

                # Also emit the current message branch
                current_node_id = conversation.current_node_id
                if current_node_id:
                    branch = self.conversation_service.get_message_branch(current_node_id)
                    self.messageBranchChanged.emit(branch)
        except Exception as e:
            self.errorOccurred.emit(f"Error loading conversation: {str(e)}")

    @pyqtSlot(result=list)
    def get_all_conversations(self) -> List[Dict]:
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
            self.errorOccurred.emit(f"Error loading conversations: {str(e)}")
            return []

    @pyqtSlot(str)
    def create_new_conversation(self, name: str = "New Conversation") -> None:
        """Create a new conversation"""
        try:
            conversation = self.conversation_service.create_conversation(name=name)
            self.current_conversation_id = conversation.id
            self.conversationLoaded.emit(conversation)

            # Emit the initial branch (just the system message)
            branch = [self.conversation_service.get_message(conversation.current_node_id)]
            self.messageBranchChanged.emit(branch)
        except Exception as e:
            self.errorOccurred.emit(f"Error creating conversation: {str(e)}")

    @pyqtSlot(str, str)
    def rename_conversation(self, conversation_id: str, new_name: str) -> None:
        """Rename a conversation"""
        try:
            success = self.conversation_service.update_conversation(conversation_id, name=new_name)
            if success and conversation_id == self.current_conversation_id:
                # Reload the conversation to refresh UI
                self.load_conversation(conversation_id)
        except Exception as e:
            self.errorOccurred.emit(f"Error renaming conversation: {str(e)}")

    @pyqtSlot(str)
    def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation"""
        try:
            success = self.conversation_service.delete_conversation(conversation_id)
            if success and conversation_id == self.current_conversation_id:
                # Clear current conversation
                self.current_conversation_id = None
        except Exception as e:
            self.errorOccurred.emit(f"Error deleting conversation: {str(e)}")

    @pyqtSlot(str, str, list)
    def send_message(self, conversation_id: str, content: str, attachments: List[Dict] = None) -> None:
        """Send a user message and get the assistant's response"""
        if self.is_loading:
            self.errorOccurred.emit("Already processing a message")
            return

        self.is_loading = True
        self.loadingStateChanged.emit(True)

        try:
            # 1. Add the user message to the database
            user_message = self.conversation_service.add_user_message(conversation_id, content)
            if not user_message:
                raise Exception("Failed to add user message")

            # 2. Add file attachments if any
            if attachments:
                for attachment in attachments:
                    self.conversation_service.add_file_attachment(user_message.id, attachment)

            # 3. Emit the updated branch
            branch = self.conversation_service.get_message_branch(user_message.id)
            self.messageBranchChanged.emit(branch)
            self.messageAdded.emit(user_message)

            # 4. Get all messages in the branch for API call
            messages = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "attached_files": self._prepare_attachments(msg) if hasattr(msg, 'file_attachments') else []
                }
                for msg in branch
            ]

            # 5. Start the API call in a separate thread
            self._start_api_call(conversation_id, messages)

        except Exception as e:
            self.is_loading = False
            self.loadingStateChanged.emit(False)
            self.errorOccurred.emit(f"Error sending message: {str(e)}")

    def _prepare_attachments(self, message: Message) -> List[Dict]:
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

    def _start_api_call(self, conversation_id: str, messages: List[Dict]) -> None:
        """Start the API call in a separate thread"""
        # Reset state for new call
        self.is_streaming = True
        self._buffer = ""

        # Create a thread to handle the API call
        thread = threading.Thread(
            target=self._execute_api_call,
            args=(conversation_id, messages,),
            daemon=True
        )
        thread.start()

    def _execute_api_call(self, conversation_id: str, messages: List[Dict]) -> None:
        """Execute the API call and handle the response"""
        try:
            # 1. Get the API response
            if self._api_settings.get("stream", True):
                # Streaming mode
                for chunk in self.api_service.get_streaming_response(messages, self._api_settings):
                    if isinstance(chunk, str):
                        # Text chunk
                        self._buffer += chunk
                        self.messageStreamChunk.emit(chunk)
                    elif isinstance(chunk, dict):
                        # Metadata like token usage, model info
                        if "token_usage" in chunk:
                            self.tokenUsageUpdated.emit(chunk["token_usage"])
                        elif "reasoning_steps" in chunk:
                            self.reasoningStepsChanged.emit(chunk["reasoning_steps"])
            else:
                # Non-streaming mode
                response = self.api_service.get_response(messages, self._api_settings)
                self._buffer = response.get("content", "")

                # Emit token usage if available
                if "token_usage" in response:
                    self.tokenUsageUpdated.emit(response["token_usage"])

                # Emit reasoning steps if available
                if "reasoning_steps" in response:
                    self.reasoningStepsChanged.emit(response["reasoning_steps"])

            # 2. Add assistant response to database
            assistant_message = self.conversation_service.add_assistant_message(
                conversation_id=conversation_id,
                content=self._buffer,
                model_info={"model": self._api_settings.get("model", "unknown")},
                token_usage=self.api_service.last_token_usage,
                reasoning_steps=self.api_service.last_reasoning_steps,
                response_id=self.api_service.last_response_id
            )

            # 3. Emit updated branch
            branch = self.conversation_service.get_message_branch(assistant_message.id)
            self.messageBranchChanged.emit(branch)
            self.messageAdded.emit(assistant_message)

        except Exception as e:
            self.errorOccurred.emit(f"API error: {str(e)}")
        finally:
            # Reset state
            self.is_streaming = False
            self.is_loading = False
            self.loadingStateChanged.emit(False)
            self.messagingComplete.emit()

    @pyqtSlot(str)
    def navigate_to_message(self, message_id: str) -> None:
        """Navigate to a specific message in the conversation"""
        if not self.current_conversation_id:
            return

        try:
            success = self.conversation_service.navigate_to_message(
                self.current_conversation_id, message_id
            )

            if success:
                # Emit the new branch
                branch = self.conversation_service.get_message_branch(message_id)
                self.messageBranchChanged.emit(branch)
        except Exception as e:
            self.errorOccurred.emit(f"Error navigating to message: {str(e)}")

    @pyqtSlot(dict)
    def update_api_settings(self, settings: Dict[str, Any]) -> None:
        """Update API settings"""
        self._api_settings = settings.copy()

    @pyqtSlot()
    def retry_last_response(self) -> None:
        """Retry generating a response for the current user message"""
        if not self.current_conversation_id or self.is_loading:
            return

        try:
            # Get the current message
            conversation = self.conversation_service.get_conversation(self.current_conversation_id)
            if not conversation or not conversation.current_node_id:
                return

            current_message = self.conversation_service.get_message(conversation.current_node_id)

            # If current message is assistant, navigate to its parent (user message)
            if current_message.role == "assistant" and current_message.parent_id:
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

                # Start API call
                self.is_loading = True
                self.loadingStateChanged.emit(True)
                self._start_api_call(self.current_conversation_id, messages)
        except Exception as e:
            self.is_loading = False
            self.loadingStateChanged.emit(False)
            self.errorOccurred.emit(f"Error retrying message: {str(e)}")

    @pyqtSlot(str, str, result=list)
    def search_conversations(self, search_term: str, conversation_id: str = None) -> List[Dict]:
        """Search for messages containing the search term"""
        try:
            results = self.conversation_service.search_conversations(
                search_term,
                conversation_id=conversation_id if conversation_id else None
            )
            return results
        except Exception as e:
            self.errorOccurred.emit(f"Error searching conversations: {str(e)}")
            return []