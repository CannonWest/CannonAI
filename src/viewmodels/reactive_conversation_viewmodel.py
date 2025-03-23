# src/viewmodels/reactive_conversation_viewmodel.py

import rx
from rx import operators as ops
from rx.subject import Subject, BehaviorSubject
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from src.utils.reactive import ReactiveProperty, ReactiveList, ReactiveDict, ReactiveViewModel
from src.services.db_service import ConversationService
from src.services.api_service import ApiService


class ReactiveConversationViewModel(ReactiveViewModel):
    """ViewModel for managing conversation interactions using reactive programming"""

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
        self.conversation_service = ConversationService()
        self.api_service = ApiService()

        # Reactive state
        self.current_conversation_id = ReactiveProperty(None)
        self.current_branch = ReactiveProperty([])
        self.is_loading = ReactiveProperty(False)
        self.token_usage = ReactiveProperty({})
        self.stream_buffer = ReactiveProperty("")
        self.model_info = ReactiveProperty({})
        self.reasoning_steps = ReactiveList()

        # Set up reactive data flow

        # 1. When current_conversation_id changes, load the conversation
        self.current_conversation_id.observe().pipe(
            ops.filter(lambda x: x is not None),
            ops.distinct_until_changed()
        ).subscribe(self._load_conversation_by_id)

        # 2. Connect reactive properties to signals
        self.connect_reactive_property(self.is_loading, 'loadingStateChanged')
        self.connect_reactive_property(self.token_usage, 'tokenUsageUpdated')
        self.connect_reactive_property(self.current_branch, 'messageBranchChanged')

        # 3. Set up reasoning steps observation
        self.reasoning_steps.observe_added().subscribe(
            lambda step: self.reasoningStepsChanged.emit(self.reasoning_steps.items)
        )

        # 4. Set up stream buffer handling
        self.stream_buffer.observe().pipe(
            ops.distinct_until_changed(),
            ops.pairwise(),  # Get previous and current value
            ops.map(lambda pair: pair[1][len(pair[0]):])  # Get only the new part
        ).subscribe(
            lambda chunk: self.messageStreamChunk.emit(chunk) if chunk else None
        )

    def _load_conversation_by_id(self, conversation_id):
        """Load a conversation by ID (private method)"""
        try:
            conversation = self.conversation_service.get_conversation(conversation_id)
            if conversation:
                self.conversationLoaded.emit(conversation)

                # Also get the current message branch
                current_node_id = conversation.current_node_id
                if current_node_id:
                    branch = self.conversation_service.get_message_branch(current_node_id)
                    self.current_branch.set(branch)
        except Exception as e:
            self.errorOccurred.emit(f"Error loading conversation: {str(e)}")

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
            self.errorOccurred.emit(f"Error loading conversations: {str(e)}")
            return []

    @pyqtSlot(str)
    def create_new_conversation(self, name="New Conversation"):
        """Create a new conversation"""
        try:
            conversation = self.conversation_service.create_conversation(name=name)
            self.current_conversation_id.set(conversation.id)
        except Exception as e:
            self.errorOccurred.emit(f"Error creating conversation: {str(e)}")

    @pyqtSlot(str, str)
    def rename_conversation(self, conversation_id, new_name):
        """Rename a conversation"""
        try:
            success = self.conversation_service.update_conversation(conversation_id, name=new_name)
            if success and conversation_id == self.current_conversation_id.get():
                # Reload the conversation to refresh UI
                self._load_conversation_by_id(conversation_id)
        except Exception as e:
            self.errorOccurred.emit(f"Error renaming conversation: {str(e)}")

    @pyqtSlot(str)
    def delete_conversation(self, conversation_id):
        """Delete a conversation"""
        try:
            success = self.conversation_service.delete_conversation(conversation_id)
            if success and conversation_id == self.current_conversation_id.get():
                # Clear current conversation
                self.current_conversation_id.set(None)
                self.current_branch.set([])
        except Exception as e:
            self.errorOccurred.emit(f"Error deleting conversation: {str(e)}")

    @pyqtSlot(str, str, list)
    def send_message(self, conversation_id, content, attachments=None):
        """Send a user message and get the assistant's response"""
        # Return early if already loading
        if self.is_loading.get():
            self.errorOccurred.emit("Already processing a message")
            return

        # Update loading state
        self.is_loading.set(True)

        try:
            # 1. Add the user message to the database
            user_message = self.conversation_service.add_user_message(conversation_id, content)
            if not user_message:
                raise Exception("Failed to add user message")

            # 2. Add file attachments if any
            if attachments:
                for attachment in attachments:
                    self.conversation_service.add_file_attachment(user_message.id, attachment)

            # 3. Emit that message was added and update branch
            self.messageAdded.emit(user_message)
            branch = self.conversation_service.get_message_branch(user_message.id)
            self.current_branch.set(branch)

            # 4. Get all messages in the branch for API call
            messages = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "attached_files": self._prepare_attachments(msg) if hasattr(msg, 'file_attachments') else []
                }
                for msg in branch
            ]

            # 5. Start API call using reactive approach
            self._process_api_call(conversation_id, messages)

        except Exception as e:
            self.is_loading.set(False)
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

    def _process_api_call(self, conversation_id, messages):
        """Process API call using reactive streams"""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        import threading

        # Reset stream buffer and reasoning steps
        self.stream_buffer.set("")
        self.reasoning_steps.clear()

        # Create a Subject for handling streaming chunks
        chunk_stream = Subject()

        # Set up processing of the stream
        chunk_stream.pipe(
            # Accumulate chunks into the buffer
            ops.scan(lambda acc, chunk: acc + chunk, seed="")
        ).subscribe(
            on_next=lambda buffer: self.stream_buffer.set(buffer),
            on_error=lambda e: self.errorOccurred.emit(f"Streaming error: {str(e)}")
        )

        # Create observable for API call
        def run_api_call():
            try:
                # Use either streaming or non-streaming based on settings
                if self.api_service._api_settings.get("stream", True):
                    # Process streaming response
                    for chunk in self.api_service.get_streaming_response(messages, self.api_service._api_settings):
                        if isinstance(chunk, str):
                            # Text chunk
                            chunk_stream.on_next(chunk)
                        elif isinstance(chunk, dict):
                            # Metadata like token usage
                            if "token_usage" in chunk:
                                self.token_usage.set(chunk["token_usage"])
                            elif "reasoning_steps" in chunk:
                                for step in chunk["reasoning_steps"]:
                                    self.reasoning_steps.append(step)
                            elif "model" in chunk:
                                self.model_info.set({"model": chunk["model"]})
                else:
                    # Non-streaming response
                    response = self.api_service.get_response(messages, self.api_service._api_settings)

                    # Handle response content
                    if "content" in response:
                        self.stream_buffer.set(response["content"])

                    # Handle metadata
                    if "token_usage" in response:
                        self.token_usage.set(response["token_usage"])
                    if "reasoning_steps" in response:
                        for step in response["reasoning_steps"]:
                            self.reasoning_steps.append(step)
                    if "model" in response:
                        self.model_info.set({"model": response["model"]})

                # Process complete - add assistant response to database
                self._save_assistant_response(conversation_id)

            except Exception as e:
                self.errorOccurred.emit(f"API error: {str(e)}")
            finally:
                # Always reset loading state
                self.is_loading.set(False)
                self.messagingComplete.emit()

                # Complete the stream
                chunk_stream.on_completed()

        # Run in a separate thread
        threading.Thread(target=run_api_call, daemon=True).start()

    def _save_assistant_response(self, conversation_id):
        """Save the assistant response to the database"""
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
        except Exception as e:
            self.errorOccurred.emit(f"Error navigating to message: {str(e)}")

    @pyqtSlot(dict)
    def update_api_settings(self, settings):
        """Update API settings"""
        self.api_service._api_settings = settings.copy()

    @pyqtSlot()
    def retry_last_response(self):
        """Retry generating a response for the current user message"""
        if not self.current_conversation_id.get() or self.is_loading.get():
            return

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

                # Start API call
                self.is_loading.set(True)
                self._process_api_call(conversation_id, messages)
        except Exception as e:
            self.is_loading.set(False)
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
            self.errorOccurred.emit(f"Error searching conversations: {str(e)}")
            return []

    @pyqtSlot(str, str, result=str)
    def duplicate_conversation(self, conversation_id: str, new_name: str = None) -> str:
        """
        Duplicate a conversation, making it the active conversation

        Args:
            conversation_id: ID of the conversation to duplicate
            new_name: Optional new name for the duplicate, defaults to "<original_name> (Copy)"

        Returns:
            The ID of the new conversation, or None if duplication failed
        """
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
            self.errorOccurred.emit(f"Error duplicating conversation: {str(e)}")
            return None