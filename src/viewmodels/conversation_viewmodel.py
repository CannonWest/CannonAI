# src/viewmodels/conversation_viewmodel.py

# Standard library imports
# Removed asyncio, concurrent.futures
import uuid
from datetime import datetime
import platform
import traceback
from typing import List, Dict, Optional, Any # Keep typing

# Third-party imports
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QThread # Added QThread

# Application-specific imports - utilities first
from src.utils.logging_utils import get_logger
# Removed: qasync_bridge imports

# Application-specific imports - services (Synchronous versions)
# Make sure these point to the renamed synchronous service files/classes
from src.services.api.api_service import ApiService
from src.services.database.conversation_service import ConversationService
from src.models import Conversation, Message # Import models for type hints


logger = get_logger(__name__)

# Define Worker QObject (Example for send_message - can be moved/refined)
class BaseWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    # Add specific result signals as needed, e.g.,
    # Results should be basic Python types (dict, list, str, int, etc.) or QVariant compatible
    conversationResult = pyqtSignal(object) # Could be Conversation object or dict
    conversationListResult = pyqtSignal(list) # List of dicts
    messageResult = pyqtSignal(object) # Could be Message object or dict
    branchResult = pyqtSignal(list) # List of Message objects or dicts

    def __init__(self, *args, **kwargs):
        super().__init__()
        # Store necessary services or data passed from ViewModel
        # Make kwargs accessible to subclasses
        self.args = args
        self.kwargs = kwargs
        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")


    @pyqtSlot()
    def run(self):
        """Main worker task. Override in subclasses."""
        # Base implementation does nothing, subclasses should override
        self.logger.warning("BaseWorker.run() called - subclass should override.")
        self.finished.emit()

class SendMessageWorker(BaseWorker):
    # Signals specific to sending a message
    userMessageSaved = pyqtSignal(object)      # Emits the saved user Message object/dict
    assistantMessageSaved = pyqtSignal(object) # Emits the saved assistant Message object/dict
    streamChunkReady = pyqtSignal(str)         # Emits a text chunk from streaming API
    tokenUsageReady = pyqtSignal(dict)         # Emits token usage info
    reasoningStepsReady = pyqtSignal(list)     # Emits reasoning steps info (if any)
    messagingDone = pyqtSignal()               # Indicates the entire send/receive cycle is complete

    @pyqtSlot()
    def run(self):
        """
        Handles sending user message, calling API, processing response, saving assistant message.
        """
        conversation_id, content, attachments = self.args
        api_settings_override = self.kwargs.get('api_settings_override', {}) # Allow overriding settings per call
        task_id = self.kwargs.get('task_id', 'send_message_task')
        view_model: 'ConversationViewModel' = self.kwargs['view_model']
        conv_service: ConversationService = self.kwargs['conversation_service']
        api_service: ApiService = self.kwargs['api_service']

        user_message = None
        assistant_message = None
        stream_buffer = ""
        collected_metadata = {} # To store metadata from stream

        try:
            self.logger.debug(f"SendMessageWorker running for conv {conversation_id}")

            # 1. Save User Message
            self.logger.debug("Saving user message...")
            # Determine parent ID based on ViewModel's current branch state
            parent_id = view_model._current_branch[-1].id if view_model._current_branch else None
            user_message = conv_service.add_user_message(conversation_id, content, parent_id=parent_id)
            if not user_message:
                raise Exception("Failed to save user message to database.")
            # TODO: Handle saving attachments synchronously if needed
            # for attachment_info in (attachments or []):
            #     conv_service.add_file_attachment(user_message.id, attachment_info)
            self.userMessageSaved.emit(user_message) # Notify ViewModel immediately
            self.logger.debug(f"User message {user_message.id} saved.")

            # 2. Prepare for API Call
            # Get current branch *after* adding user message
            current_branch = conv_service.get_message_branch(user_message.id)
            if not current_branch:
                 raise Exception("Failed to retrieve message branch after saving user message.")

            # Get API settings from SettingsViewModel via main ViewModel instance
            # This assumes settings_vm is accessible or settings are passed differently
            # For now, using api_service internal settings + overrides
            api_settings = api_service._api_settings.copy() # Start with base settings
            api_settings.update(view_model.settings_vm.get_settings()) # Layer current settings
            api_settings.update(api_settings_override) # Layer call-specific settings

            # Determine if streaming is enabled
            use_streaming = api_settings.get("stream", True)
            api_type = api_settings.get("api_type", "responses") # Get API type

            # Prepare messages payload for the API
            messages_payload = api_service._prepare_input(current_branch, api_type) # Use service's helper


            # 3. Call API (Streaming or Non-Streaming)
            if use_streaming:
                self.logger.debug("Calling API (Streaming)...")
                stream_iterator = api_service.get_streaming_completion(current_branch, api_settings) # Pass branch directly
                for event in stream_iterator:
                    # Process different event types (adapt based on ApiService output)
                    if api_type == "responses":
                        event_type = event.get('type')
                        if event_type == 'response.output_text.delta' and 'delta' in event:
                            chunk = event['delta']
                            stream_buffer += chunk
                            self.streamChunkReady.emit(chunk)
                        elif event_type == 'response.completed' and 'response' in event:
                             if 'usage' in event['response']: collected_metadata['token_usage'] = api_service.last_token_usage
                             if 'model' in event['response']: collected_metadata['model'] = api_service.last_model
                        elif event_type == 'response.created' and 'response' in event:
                             if 'id' in event['response']: collected_metadata['response_id'] = api_service.last_response_id
                        elif event_type == 'response.thinking_step':
                             if 'thinking_step' in event:
                                  if 'reasoning_steps' not in collected_metadata: collected_metadata['reasoning_steps'] = []
                                  collected_metadata['reasoning_steps'].append(api_service.last_reasoning_steps[-1]) # Get latest step
                    else: # chat_completions
                        if 'choices' in event and event['choices']:
                             delta = event['choices'][0].get('delta', {})
                             if 'content' in delta and delta['content']:
                                  chunk = delta['content']
                                  stream_buffer += chunk
                                  self.streamChunkReady.emit(chunk)
                        # Metadata (like usage) often comes at the end or in separate events for chat completions
                        if 'usage' in event: collected_metadata['token_usage'] = api_service.last_token_usage
                        if 'model' in event: collected_metadata['model'] = api_service.last_model
                        if 'id' in event: collected_metadata['response_id'] = api_service.last_response_id

                self.logger.debug(f"Streaming finished. Collected content length: {len(stream_buffer)}")
                # Emit collected metadata after stream ends
                if collected_metadata.get('token_usage'): self.tokenUsageReady.emit(collected_metadata['token_usage'])
                if collected_metadata.get('reasoning_steps'): self.reasoningStepsReady.emit(collected_metadata['reasoning_steps'])

            else: # Non-streaming
                self.logger.debug("Calling API (Non-Streaming)...")
                response_data = api_service.get_completion(current_branch, api_settings) # Pass branch directly
                stream_buffer = response_data.get("content", "")
                # Extract metadata directly from response
                if response_data.get("token_usage"):
                     collected_metadata['token_usage'] = response_data['token_usage']
                     self.tokenUsageReady.emit(response_data['token_usage'])
                if response_data.get("reasoning_steps"):
                     collected_metadata['reasoning_steps'] = response_data['reasoning_steps']
                     self.reasoningStepsReady.emit(response_data['reasoning_steps'])
                if response_data.get("model"): collected_metadata['model'] = response_data['model']
                if response_data.get("response_id"): collected_metadata['response_id'] = response_data['response_id']
                self.logger.debug(f"Non-streaming response received. Content length: {len(stream_buffer)}")


            # 4. Save Assistant Message
            self.logger.debug("Saving assistant message...")
            if stream_buffer: # Only save if we got some content
                assistant_message = conv_service.add_assistant_message(
                    conversation_id,
                    stream_buffer,
                    parent_id=user_message.id, # Link to the user message we saved
                    model_info=collected_metadata.get('model'), # Pass collected metadata
                    token_usage=collected_metadata.get('token_usage'),
                    reasoning_steps=collected_metadata.get('reasoning_steps'),
                    response_id=collected_metadata.get('response_id')
                )
                if not assistant_message:
                    # Don't raise, just log error, maybe emit specific signal?
                    self.logger.error("Failed to save assistant message to database.")
                    self.error.emit("Failed to save assistant response.")
                else:
                    self.assistantMessageSaved.emit(assistant_message)
                    self.logger.debug(f"Assistant message {assistant_message.id} saved.")
            else:
                 self.logger.warning("No content received from API to save for assistant message.")
                 # Maybe emit an error or a specific signal indicating no response?
                 self.error.emit("No response content received from API.")


        except Exception as e:
            self.logger.error(f"Error in SendMessageWorker: {e}", exc_info=True)
            self.error.emit(f"Failed to send message: {e}") # Emit generic error signal
        finally:
            self.messagingDone.emit() # Signal completion of the cycle
            self.finished.emit() # Signal QThread worker is done

class ConversationViewModel(QObject): # Renamed class
    """
    ViewModel for managing conversation interactions using QThread workers.
    """
    # --- Signals ---
    # Keep existing signals - they are still relevant for UI updates
    conversationLoaded = pyqtSignal(object) # Emits Conversation obj or dict
    messageAdded = pyqtSignal(object) # Emits Message obj or dict
    messageUpdated = pyqtSignal(object) # Emits Message obj or dict
    messageBranchChanged = pyqtSignal(list) # Emits list of Message obj or dict
    # Streaming signals might need rethinking or careful implementation in worker/ViewModel interaction
    messageStreamChunk = pyqtSignal(str) # Keep for now
    messagingComplete = pyqtSignal()
    errorOccurred = pyqtSignal(str)
    loadingStateChanged = pyqtSignal(bool)
    tokenUsageUpdated = pyqtSignal(dict)
    reasoningStepsChanged = pyqtSignal(list)
    # Signal to update the list of conversations in the UI
    conversationListUpdated = pyqtSignal(list) # Added for convenience

    def __init__(self):
        """Initialize the ViewModel with synchronous services."""
        super().__init__()
        self.logger = get_logger(__name__ + ".ConversationViewModel")

        # Initialize services (assuming they are passed or instantiated here)
        # These should be the synchronous versions
        self.conversation_service = ConversationService()
        self.api_service = ApiService()

        # State variables
        self._current_conversation_id = None
        self._current_branch = []
        self._is_loading = False
        self._token_usage = {}
        self._stream_buffer = "" # May need different handling with threads
        self._model_info = {}
        self._reasoning_steps = [] # May need different handling with threads
        self._initialized = False # Track sync initialization
        self._threads = {} # To keep track of running threads {task_id: QThread}

        self.logger.info("ConversationViewModel (Sync) constructor completed")
        # Perform synchronous initialization directly or via a method
        self._initialize_sync()

    def _initialize_sync(self):
        """Initialize services synchronously."""
        self.logger.debug("Starting synchronous initialization")
        # The conversation service now initializes itself in its constructor
        self._initialized = self.conversation_service.ensure_initialized()
        if self._initialized:
            self.logger.info("ViewModel initialization completed successfully")
            # Load initial data using a worker thread
            self.load_all_conversations_threaded() # Trigger load
        else:
            self.logger.error("ViewModel initialization failed: DB Service could not initialize.")
            self.errorOccurred.emit("Database initialization failed. Cannot load conversations.")

    # --- Worker Management ---
    def _start_worker(self, task_id: str, worker_class: type, *args, **kwargs):
        """Helper method to create, configure, and start a QThread worker."""
        # Prevent starting the same task ID if already running
        if task_id in self._threads and self._threads[task_id].isRunning():
             self.logger.warning(f"Task '{task_id}' is already running. Ignoring request.")
             return

        # If a previous thread for this task ID exists but isn't running (e.g., finished uncleanly?), clean it up.
        if task_id in self._threads:
             self.logger.warning(f"Cleaning up previous non-running thread for task: {task_id}")
             # Ensure signals are disconnected? QThread cleanup should handle this.
             del self._threads[task_id]


        self.logger.debug(f"Starting worker for task: {task_id}")
        thread = QThread()
        # Pass required services and arguments to the worker's constructor
        kwargs['conversation_service'] = self.conversation_service
        kwargs['api_service'] = self.api_service
        # Pass the ViewModel instance itself so worker can emit signals *on* it
        kwargs['view_model'] = self
        kwargs['task_id'] = task_id # Pass task_id for context in worker/signals

        worker = worker_class(*args, **kwargs)
        worker.moveToThread(thread)

        # Connect signals from Worker to ViewModel Slots
        # Note: Ensure slots exist in the ViewModel!
        worker.conversationResult.connect(self._handle_conversation_loaded)
        worker.conversationListResult.connect(self._handle_conversation_list_loaded)
        worker.messageResult.connect(self._handle_message_added)
        worker.branchResult.connect(self._handle_branch_changed)
        # Connect generic error signal
        worker.error.connect(self._handle_worker_error)

        # Thread lifecycle signals
        worker.finished.connect(thread.quit)
        # Ensure cleanup happens *after* thread quits
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # Connect thread started signal to worker's run method
        thread.started.connect(worker.run)
        # Clean up ViewModel's tracking when thread finishes
        thread.finished.connect(lambda tid=task_id: self._cleanup_thread(tid)) # Use lambda to capture task_id

        self._threads[task_id] = thread # Store thread reference
        self.loadingStateChanged.emit(True) # Indicate loading started

        thread.start() # Start the thread's event loop

    def _cleanup_thread(self, task_id: str):
        """Remove thread reference upon completion and update loading state."""
        self.logger.debug(f"Cleaning up finished thread for task: {task_id}")
        if task_id in self._threads:
            del self._threads[task_id]
        # Only set loading to false if NO threads are running
        if not self._threads:
             self.loadingStateChanged.emit(False)
             self.logger.debug("All worker threads finished, setting loading state to False.")
        else:
             self.logger.debug(f"{len(self._threads)} worker threads still running.")

    # --- Slots for Worker Results/Errors ---

    @pyqtSlot(str) # Add task_id parameter if error signal includes it
    def _handle_worker_error(self, error_message: str):
        # TODO: Modify worker error signal to include task_id for better context
        self.logger.error(f"Worker thread reported error: {error_message}")
        self.errorOccurred.emit(error_message)
        # We don't know which task failed without task_id, so just set loading false if no threads left
        if not self._threads:
             self.loadingStateChanged.emit(False)

    @pyqtSlot(list) # Expecting list of dicts
    def _handle_conversation_list_loaded(self, conversations_list: list):
        self.logger.info(f"Received conversation list with {len(conversations_list)} items.")
        self.conversationListUpdated.emit(conversations_list)
        if conversations_list:
            first_id = conversations_list[0].get('id')
            if first_id:
                self.logger.debug(f"Loading first conversation: {first_id}")
                self.load_conversation(first_id) # Trigger load worker
            else:
                self.logger.warning("First conversation in list has no ID.")
                # If loading the list was the only task, set loading false
                if len(self._threads) == 1 and "load_all_convs" in list(self._threads.keys())[0]:
                     self.loadingStateChanged.emit(False)
        else:
             self.logger.info("No conversations found, creating a new one.")
             self.create_new_conversation("New Conversation") # Starts another worker

    @pyqtSlot(object) # Expecting Conversation object (or dict)
    def _handle_conversation_loaded(self, conversation: Optional[Conversation]):
        # This slot is triggered when LoadConversationWorker emits conversationResult
        if conversation:
             task_id = f"load_conv_{conversation.id}" # Reconstruct task ID (or pass it back)
             self.logger.info(f"Handling loaded conversation: {conversation.id} from task {task_id}")

             # Make sure the received conversation is the one we currently want
             # This prevents race conditions if the user clicks another conversation quickly
             if conversation.id == self._current_conversation_id:
                 self.conversationLoaded.emit(conversation) # Emit for potential UI updates

                 # Now load the message branch for this conversation
                 if conversation.current_node_id:
                     self.load_message_branch(conversation.current_node_id)
                 else:
                     # Conversation has no messages yet (e.g., newly created)
                     self.logger.warning(f"Loaded conversation {conversation.id} has no current node_id.")
                     self._current_branch = []
                     self.messageBranchChanged.emit([])
                     # If no branch loading follows, potentially stop loading indicator here,
                     # but _cleanup_thread handles the final loading state.
             else:
                  self.logger.warning(f"Received loaded conversation {conversation.id}, but current selection is now {self._current_conversation_id}. Discarding.")
                  # Don't proceed with branch loading for the wrong conversation.
                  # Let _cleanup_thread handle loading state when this worker's thread finishes.

        else:
             self.logger.error("Handling loaded conversation: Received None")
             # Loading state handled by _cleanup_thread

    @pyqtSlot(list) # Expecting list of Message objects (or dicts?)
    def _handle_branch_changed(self, branch: List[Message]):
         # This slot is triggered when LoadBranchWorker emits branchResult
         # Assume this corresponds to the _current_conversation_id
         self.logger.info(f"Handling branch change for conv {self._current_conversation_id}, {len(branch)} messages.")
         self._current_branch = branch
         self.messageBranchChanged.emit(branch)
         # Loading state is handled by _cleanup_thread when the worker finishes

    @pyqtSlot(object) # Expecting Message object (or dict?)
    def _handle_message_added(self, message: Optional[Message]):
         # This slot could be triggered by AddUserMessageWorker or AddAssistantMessageWorker
         if message:
             self.logger.info(f"Handling added message: {message.id} (Role: {message.role})")
             self.messageAdded.emit(message)
             # If assistant message added, load its branch
             if message.role == 'assistant':
                  self.load_message_branch(message.id) # Triggers another worker
             # If user message, the 'send_message' flow should continue to get assistant response
         else:
             self.logger.error("Handling added message: Received None")


    # --- Worker Definitions and Method Implementations ---

    # Load All Conversations Worker (Refined)
    class LoadConversationsWorker(BaseWorker):
        # conversationListResult = pyqtSignal(list) # Defined in BaseWorker

        @pyqtSlot()
        def run(self):
            """Fetches all conversations and emits the result."""
            try:
                self.logger.debug("LoadConversationsWorker running...")
                conv_service: ConversationService = self.kwargs.get('conversation_service')
                conversations = conv_service.get_all_conversations() # Sync call
                conv_list_dicts = []
                for conv in conversations:
                     # Ensure essential fields exist
                     conv_id = getattr(conv, 'id', None)
                     conv_name = getattr(conv, 'name', 'Unnamed')
                     mod_at = getattr(conv, 'modified_at', None)
                     if conv_id:
                          conv_list_dicts.append({
                              'id': conv_id, 'name': conv_name,
                              'modified_at': mod_at.isoformat() if mod_at else datetime.utcnow().isoformat()
                          })
                # Emit signal via the ViewModel instance passed in kwargs
                self.kwargs['view_model'].conversationListResult.emit(conv_list_dicts)
                self.logger.debug("LoadConversationsWorker finished successfully.")
            except Exception as e:
                self.logger.error(f"Error in LoadConversationsWorker: {e}", exc_info=True)
                self.error.emit(str(e))
            finally:
                self.finished.emit()

    def load_all_conversations_threaded(self):
        """Loads all conversations using a background thread."""
        if not self._initialized:
             self.logger.warning("Cannot load conversations: Service not initialized.")
             # Emit empty list or error?
             self.conversationListUpdated.emit([])
             return
        self.logger.debug("Initiating background load for all conversations.")
        self._start_worker("load_all_convs", self.LoadConversationsWorker)


    # Load Specific Conversation Worker
    class LoadConversationWorker(BaseWorker):
         # conversationResult = pyqtSignal(object) # Defined in BaseWorker

         # No need for __init__ if args are handled by BaseWorker

         @pyqtSlot()
         def run(self):
              """Fetches a specific conversation."""
              conv_id = self.args[0] # Get conv_id from args passed to _start_worker
              try:
                  self.logger.debug(f"LoadConversationWorker running for ID: {conv_id}")
                  conv_service: ConversationService = self.kwargs.get('conversation_service')
                  conversation = conv_service.get_conversation(conv_id) # Sync call
                  # Emit signal via the ViewModel instance
                  self.kwargs['view_model'].conversationResult.emit(conversation)
                  self.logger.debug(f"LoadConversationWorker finished for ID: {conv_id}")
              except Exception as e:
                  self.logger.error(f"Error in LoadConversationWorker for ID {conv_id}: {e}", exc_info=True)
                  self.error.emit(f"Failed to load conversation {conv_id}: {e}")
              finally:
                  self.finished.emit()

    @pyqtSlot(str)
    def load_conversation(self, conversation_id: str):
        """Load a conversation by ID using a background thread."""
        if not conversation_id:
             self.logger.error("load_conversation called with empty ID.")
             return
        # Avoid reloading if it's the current one AND no thread is active for it
        task_id = f"load_conv_{conversation_id}"
        if conversation_id == self._current_conversation_id and task_id not in self._threads:
             self.logger.debug(f"Conversation {conversation_id} already current and not loading.")
             # Ensure branch is loaded if needed, start branch load if not running
             branch_task_id = f"load_branch_{self._current_branch[-1].id if self._current_branch else None}"
             if self._current_branch and branch_task_id not in self._threads:
                  self.load_message_branch(self._current_branch[-1].id)
             elif not self._current_branch and self._current_conversation_id:
                  # Maybe the conversation exists but branch failed? Try loading based on conversation.current_node_id
                  conv = self.conversation_service._conversation_cache.get(self._current_conversation_id)
                  if conv and conv.current_node_id and f"load_branch_{conv.current_node_id}" not in self._threads:
                       self.load_message_branch(conv.current_node_id)

             return

        self.logger.debug(f"Initiating background load for conversation: {conversation_id}")
        # Update the *target* ID immediately so _handle_conversation_loaded can check it
        self._current_conversation_id = conversation_id
        self._start_worker(task_id, self.LoadConversationWorker, conversation_id) # Pass conv_id as positional arg


    # Load Message Branch Worker
    class LoadBranchWorker(BaseWorker):
         # branchResult = pyqtSignal(list) # Defined in BaseWorker

         @pyqtSlot()
         def run(self):
              """Fetches the message branch."""
              msg_id = self.args[0] # Get msg_id from args
              try:
                  self.logger.debug(f"LoadBranchWorker running for message ID: {msg_id}")
                  conv_service: ConversationService = self.kwargs.get('conversation_service')
                  branch = conv_service.get_message_branch(msg_id) # Sync call
                  # Emit signal via the ViewModel instance
                  self.kwargs['view_model'].branchResult.emit(branch)
                  self.logger.debug(f"LoadBranchWorker finished for message ID: {msg_id}")
              except Exception as e:
                  self.logger.error(f"Error in LoadBranchWorker for message ID {msg_id}: {e}", exc_info=True)
                  self.error.emit(f"Failed to load branch for message {msg_id}: {e}")
              finally:
                  self.finished.emit()

    # Keep the load_message_branch method mostly the same, just uses the worker class above
    def load_message_branch(self, message_id: str):
        """Loads message branch up to message_id using a background thread."""
        if not message_id:
             self.logger.warning("load_message_branch called with no message_id.")
             self._current_branch = []
             self.messageBranchChanged.emit([])
             # If this was the last step in loading, ensure loading indicator stops
             if not self._threads: self.loadingStateChanged.emit(False)
             return

        self.logger.debug(f"Initiating background load for message branch ending at: {message_id}")
        task_id = f"load_branch_{message_id}"
        self._start_worker(task_id, self.LoadBranchWorker, message_id) # Pass msg_id as positional arg


    # --- Other Methods Requiring Workers (Implement similarly) ---

    # Create Conversation Worker
    class CreateConversationWorker(BaseWorker):
        # conversationResult = pyqtSignal(object) # Defined in BaseWorker

        @pyqtSlot()
        def run(self):
            conv_name = self.args[0]
            try:
                self.logger.debug(f"CreateConversationWorker running for name: {conv_name}")
                conv_service: ConversationService = self.kwargs.get('conversation_service')
                system_message = "You are a helpful assistant." # TODO: Make configurable
                new_conv = conv_service.create_conversation(name=conv_name, system_message=system_message)
                # Emit via ViewModel
                self.kwargs['view_model'].conversationResult.emit(new_conv)
                # Trigger list reload *after* emitting the new conversation result
                # This uses another worker started from the ViewModel slot
                QTimer.singleShot(0, self.kwargs['view_model'].load_all_conversations_threaded)

            except Exception as e:
                self.logger.error(f"Error in CreateConversationWorker for name {conv_name}: {e}", exc_info=True)
                self.error.emit(f"Failed to create conversation '{conv_name}': {e}")
            finally:
                self.finished.emit()

    @pyqtSlot(str)
    def create_new_conversation(self, name="New Conversation"):
        """Create a new conversation using a background thread."""
        self.logger.debug(f"Initiating background creation for new conversation: {name}")
        self._start_worker("create_conv", self.CreateConversationWorker, name)


    # Rename Conversation Worker
    class RenameConversationWorker(BaseWorker):
        renameComplete = pyqtSignal(bool, str) # success, conversation_id

        @pyqtSlot()
        def run(self):
            conv_id, new_name = self.args
            success = False
            try:
                self.logger.debug(f"RenameConversationWorker running for {conv_id} to '{new_name}'")
                conv_service: ConversationService = self.kwargs.get('conversation_service')
                success = conv_service.update_conversation(conv_id, name=new_name)
                self.renameComplete.emit(success, conv_id)
                # Trigger list reload if successful
                if success:
                     QTimer.singleShot(0, self.kwargs['view_model'].load_all_conversations_threaded)
            except Exception as e:
                self.logger.error(f"Error in RenameConversationWorker for {conv_id}: {e}", exc_info=True)
                self.error.emit(f"Failed to rename conversation {conv_id}: {e}")
            finally:
                self.finished.emit()

    @pyqtSlot(bool, str)
    def _handle_rename_complete(self, success: bool, conversation_id: str):
        """Slot to handle rename completion."""
        if success:
             self.logger.info(f"Conversation {conversation_id} renamed successfully.")
             # List is reloaded by worker, UI should update via conversationListUpdated
        else:
             self.logger.error(f"Failed to rename conversation {conversation_id}.")
             # Error already emitted by worker

    @pyqtSlot(str, str)
    def rename_conversation(self, conversation_id, new_name):
        """Rename a conversation using a background thread."""
        self.logger.debug(f"Initiating background rename for conv {conversation_id} to '{new_name}'")
        task_id = f"rename_conv_{conversation_id}"
        # Need to connect the worker's specific signal here
        # self._start_worker handles generic signals, need manual connect for specific ones
        thread = QThread()
        kwargs = {'conversation_service': self.conversation_service, 'api_service': self.api_service, 'view_model': self, 'task_id': task_id}
        worker = self.RenameConversationWorker(conversation_id, new_name, **kwargs)
        worker.moveToThread(thread)

        # Connect standard signals
        worker.error.connect(self._handle_worker_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda tid=task_id: self._cleanup_thread(tid))
        # Connect specific signal
        worker.renameComplete.connect(self._handle_rename_complete) # Connect here
        # Connect start
        thread.started.connect(worker.run)

        self._threads[task_id] = thread
        self.loadingStateChanged.emit(True)
        thread.start()


    # Delete Conversation Worker
    class DeleteConversationWorker(BaseWorker):
        deleteComplete = pyqtSignal(bool, str) # success, deleted_id

        @pyqtSlot()
        def run(self):
            conv_id = self.args[0]
            success = False
            try:
                self.logger.debug(f"DeleteConversationWorker running for {conv_id}")
                conv_service: ConversationService = self.kwargs.get('conversation_service')
                success = conv_service.delete_conversation(conv_id)
                self.deleteComplete.emit(success, conv_id)
                 # Trigger list reload if successful
                if success:
                     QTimer.singleShot(0, self.kwargs['view_model'].load_all_conversations_threaded)
            except Exception as e:
                self.logger.error(f"Error in DeleteConversationWorker for {conv_id}: {e}", exc_info=True)
                self.error.emit(f"Failed to delete conversation {conv_id}: {e}")
            finally:
                self.finished.emit()

    @pyqtSlot(bool, str)
    def _handle_delete_complete(self, success: bool, deleted_id: str):
        """Slot to handle delete completion."""
        if success:
             self.logger.info(f"Conversation {deleted_id} deleted successfully.")
             # If the deleted one was current, the list reload should handle loading the next one
             if self._current_conversation_id == deleted_id:
                  self._current_conversation_id = None
                  self._current_branch = []
                  # Don't clear UI yet, wait for list reload and subsequent load
        else:
             self.logger.error(f"Failed to delete conversation {deleted_id}.")

    @pyqtSlot(str)
    def delete_conversation(self, conversation_id):
        """Delete a conversation using a background thread."""
        self.logger.debug(f"Initiating background delete for conversation: {conversation_id}")
        task_id = f"delete_conv_{conversation_id}"
        # Manual connection needed for specific signal
        thread = QThread()
        kwargs = {'conversation_service': self.conversation_service, 'api_service': self.api_service, 'view_model': self, 'task_id': task_id}
        worker = self.DeleteConversationWorker(conversation_id, **kwargs)
        worker.moveToThread(thread)

        # Connect standard signals
        worker.error.connect(self._handle_worker_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda tid=task_id: self._cleanup_thread(tid))
        # Connect specific signal
        worker.deleteComplete.connect(self._handle_delete_complete) # Connect here
        # Connect start
        thread.started.connect(worker.run)

        self._threads[task_id] = thread
        self.loadingStateChanged.emit(True)
        thread.start()

    @pyqtSlot(str, str, "QVariant")
    def send_message(self, conversation_id, content, attachments=None):
        """Send a user message and get response using SendMessageWorker."""
        if not conversation_id:
            self.logger.error("send_message called with no conversation ID.")
            self.errorOccurred.emit("Cannot send message: No conversation selected.")
            return
        if not content.strip():
            self.logger.warning("send_message called with empty content.")
            # Optionally provide feedback to user
            # self.errorOccurred.emit("Cannot send empty message.")
            return

        self.logger.debug(f"Initiating SendMessageWorker for conversation {conversation_id}")
        task_id = f"send_msg_{conversation_id}_{uuid.uuid4().hex[:6]}"

        # Prepare attachments if any (convert QML list/objects to simple dicts if needed)
        processed_attachments = []
        if attachments:
            # Assuming attachments is a list of objects/dicts from QML
            for attach in attachments:
                # Extract necessary info (adjust based on QML model structure)
                processed_attachments.append({
                    'fileName': getattr(attach, 'fileName', attach.get('fileName', 'unknown')),
                    'filePath': getattr(attach, 'filePath', attach.get('filePath', None)),
                    # Add other relevant fields like content if pre-loaded
                })

        # --- Manual Signal Connection for SendMessageWorker ---
        # We need to connect specific signals from this worker
        thread = QThread()
        kwargs = {
            'conversation_service': self.conversation_service,
            'api_service': self.api_service,
            'view_model': self,
            'task_id': task_id,
            'api_settings_override': {}  # Pass any specific overrides if needed
        }
        worker = SendMessageWorker(conversation_id, content, processed_attachments, **kwargs)
        worker.moveToThread(thread)

        # Connect standard signals
        worker.error.connect(self._handle_worker_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda tid=task_id: self._cleanup_thread(tid))

        # Connect SendMessageWorker specific signals
        worker.userMessageSaved.connect(self._handle_user_message_saved)
        worker.assistantMessageSaved.connect(self._handle_assistant_message_saved)
        worker.streamChunkReady.connect(self._handle_stream_chunk)
        worker.tokenUsageReady.connect(self._handle_api_metadata)  # Reuse metadata handler
        worker.reasoningStepsReady.connect(self._handle_api_metadata)  # Reuse metadata handler
        worker.messagingDone.connect(self._handle_messaging_done)

        # Connect start
        thread.started.connect(worker.run)

        self._threads[task_id] = thread
        self.loadingStateChanged.emit(True)  # Set loading true
        thread.start()

    @pyqtSlot()
    def _handle_messaging_done(self):
        """Handles the completion of the send/receive cycle."""
        self.logger.debug("Slot received messaging cycle complete.")
        self.messagingComplete.emit()

    @pyqtSlot(object)
    def _handle_user_message_saved(self, user_message: Message):
        """Handles the user message being saved by the worker."""
        self.logger.debug(f"Slot received saved user message: {user_message.id}")
        # Add message to the UI immediately
        self.messageAdded.emit(user_message)
        # Update internal branch state (optional, branch update usually happens after assistant response)
        # self._current_branch.append(user_message)
        # self.messageBranchChanged.emit(self._current_branch) # <-- This might cause jumpiness

    @pyqtSlot(str)
    def _handle_stream_chunk(self, chunk: str):
        """Handles incoming stream chunks."""
        # Append chunk to the last message in the UI model if it's an assistant message
        # This requires access to the QML model or managing the buffer here
        self.logger.debug(f"Slot received stream chunk (len {len(chunk)})")
        self.messageStreamChunk.emit(chunk)  # Forward signal to QML

    @pyqtSlot(dict)
    def _handle_api_metadata(self, metadata: dict):
        """Handles metadata received during/after API call."""
        self.logger.debug(f"Slot received API metadata: {metadata.keys()}")
        if "token_usage" in metadata:
            self._token_usage = metadata["token_usage"]
            self.tokenUsageUpdated.emit(self._token_usage)
        if "reasoning_steps" in metadata:
            self._reasoning_steps = metadata["reasoning_steps"]
            self.reasoningStepsChanged.emit(self._reasoning_steps)
        # Handle other metadata like model, response_id if needed

    @pyqtSlot(object)
    def _handle_assistant_message_saved(self, assistant_message: Message):
        """Handles the assistant message being saved by the worker."""
        self.logger.debug(f"Slot received saved assistant message: {assistant_message.id}")
        # Add the complete assistant message to the UI
        # QML side might need logic to replace the streaming message with the final one
        self.messageAdded.emit(assistant_message)
        # Trigger final branch update
        self.load_message_branch(assistant_message.id)

    # navigate_to_message still needs implementation
    @pyqtSlot(str)
    def navigate_to_message(self, message_id):
        """Navigate to a specific message using a background thread."""
        self.logger.debug(f"Initiating navigation to message: {message_id}")
        # TODO: Implement NavigateWorker (which calls load_message_branch internally or emits result)
        self.logger.warning("navigate_to_message worker not implemented yet")
        self.loadingStateChanged.emit(True)
        # Need to call load_message_branch worker here
        self.load_message_branch(message_id) # Reuse existing worker for branch loading
        # The loading state will be handled by the branch worker's completion


    # retry_last_response still needs implementation
    @pyqtSlot()
    def retry_last_response(self):
        """Retry the last assistant response using background thread."""
        self.logger.debug("Initiating retry last response")
        # TODO: Implement RetryWorker
        self.logger.warning("retry_last_response worker not implemented yet")
        self.loadingStateChanged.emit(True)
        QTimer.singleShot(100, lambda: self.loadingStateChanged.emit(False))


    # Search can remain synchronous for now
    @pyqtSlot(str, str, result="QVariant")
    def search_conversations(self, search_term, conversation_id=None):
        """Search conversations (synchronous)."""
        self.logger.debug(f"Searching conversations (sync) for '{search_term}'")
        if not self.ensure_initialized(): return []
        try:
            results = self.conversation_service.search_conversations(search_term, conversation_id)
            return results # Return directly
        except Exception as e:
            self.logger.error(f"Error during synchronous search: {e}", exc_info=True)
            self.errorOccurred.emit(f"Search failed: {e}")
            return []

    # get_all_conversations sync method remains
    @pyqtSlot(result="QVariant")
    def get_all_conversations(self):
        """Synchronously returns the currently known list of conversations from cache."""
        self.logger.debug("get_all_conversations (sync fetch for QML init - potentially stale)")
        cached_convs = list(self.conversation_service._conversation_cache.values())
        conv_list_dicts = []
        for conv in cached_convs:
             conv_list_dicts.append({
                 'id': conv.id, 'name': conv.name,
                 'modified_at': conv.modified_at.isoformat() if conv.modified_at else None
             })
        return conv_list_dicts


    # Cleanup method remains
    def cleanup(self):
        """Cleanup resources, including stopping threads."""
        self.logger.info("Cleaning up ConversationViewModel resources")
        active_thread_ids = list(self._threads.keys())
        if active_thread_ids:
             self.logger.warning(f"Waiting for {len(active_thread_ids)} worker threads to finish...")
             for thread_id in active_thread_ids:
                  thread = self._threads.get(thread_id)
                  if thread and thread.isRunning():
                      thread.quit() # Ask thread to quit
                      if not thread.wait(3000): # Wait up to 3 seconds
                           self.logger.error(f"Thread for task {thread_id} did not finish gracefully, terminating.")
                           thread.terminate() # Force terminate if necessary
        self._threads.clear()

        # Close services
        if hasattr(self.api_service, 'close'): self.api_service.close()
        if hasattr(self.conversation_service, 'close'): self.conversation_service.close()

        self.logger.info("ConversationViewModel cleanup completed")

