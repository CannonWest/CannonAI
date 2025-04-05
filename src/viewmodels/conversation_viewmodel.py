# src/viewmodels/conversation_viewmodel.py

# Standard library imports
import uuid
from datetime import datetime
import platform
import traceback
from typing import List, Dict, Optional, Any

# Third-party imports
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QThread, QVariant

# Application-specific imports - utilities first
from src.utils.logging_utils import get_logger

# Application-specific imports - services (Synchronous versions)
from src.services.api.api_service import ApiService
from src.services.database.conversation_service import ConversationService
from src.models import Conversation, Message, FileAttachment # Import models for type hints
# Import SettingsViewModel for type hinting and access
from src.viewmodels.settings_viewmodel import SettingsViewModel


logger = get_logger(__name__)

# ==============================
# Base Worker Definition
# ==============================
class BaseWorker(QObject):
    """Base class for QThread workers in the ViewModel."""
    finished = pyqtSignal()
    error = pyqtSignal(str) # Emits error message string

    # Define common result signals - subclasses can emit these or define more specific ones
    conversationResult = pyqtSignal(object) # Emits Conversation object or dict, or None
    conversationListResult = pyqtSignal(list) # Emits List of conversation dicts
    messageResult = pyqtSignal(object) # Emits Message object or dict, or None
    branchResult = pyqtSignal(list) # Emits List of Message objects or dicts

    def __init__(self, *args, **kwargs):
        super().__init__()
        # Store necessary services or data passed from ViewModel
        self.args = args
        self.kwargs = kwargs
        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")
        # Extract common services for convenience, check they exist
        self.conv_service: Optional[ConversationService] = kwargs.get('conversation_service')
        self.api_service: Optional[ApiService] = kwargs.get('api_service')
        self.view_model: Optional['ConversationViewModel'] = kwargs.get('view_model')
        self.logger.debug("Worker initialized.")
        if not self.conv_service or not self.api_service or not self.view_model:
            # Log error, but allow execution to continue to emit proper error signal
            self.logger.error("Worker initialized without required services/viewmodel reference.")

    @pyqtSlot()
    def run(self):
        """Main worker task. Override in subclasses."""
        self.logger.info(f">>> Worker run() method started.")
        try:
            # Check for essential services again before running subclass logic
            if not self.conv_service or not self.api_service or not self.view_model:
                raise ValueError("Required services or ViewModel reference missing.")
            self.logger.debug("Calling _run_task()...")
            self._run_task()  # Call the subclass implementation
            self.logger.debug("_run_task() completed.")
        except Exception as e:
            self.logger.error(f"Unhandled exception in worker {self.__class__.__name__}: {e}", exc_info=True)
            self.error.emit(f"Worker error: {str(e)}")
        finally:
            # Ensure finished is always emitted
            self.logger.debug("Emitting finished signal.")
            self.finished.emit()
            self.logger.info(f"<<< Worker run() method finished.")

    def _run_task(self):
        """Subclasses must implement their specific task logic here."""
        raise NotImplementedError("Subclasses must implement the _run_task method.")


# ==============================
# Worker Definitions
# ==============================

class LoadConversationsWorker(BaseWorker):
    """Worker to fetch all conversations."""
    # Emits conversationListResult from BaseWorker

    def _run_task(self):
        self.logger.info(">>> LoadConversationsWorker _run_task entered.")
        self.logger.debug("LoadConversationsWorker running...") # Keep existing debug log
        conversations = self.conv_service.get_all_conversations() # Sync call
        self.logger.debug(f"Service call get_all_conversations returned {len(conversations)} items.")
        conv_list_dicts = []
        for conv in conversations:
            conv_id = getattr(conv, 'id', None)
            conv_name = getattr(conv, 'name', 'Unnamed')
            mod_at = getattr(conv, 'modified_at', None)
            if conv_id:
                conv_list_dicts.append({
                    'id': conv_id, 'name': conv_name,
                    'modified_at': mod_at.isoformat() if mod_at else datetime.utcnow().isoformat()
                })
        self.logger.debug(f"Worker emitting conversationListResult with {len(conv_list_dicts)} items.")
        self.conversationListResult.emit(conv_list_dicts)
        self.logger.info("<<< LoadConversationsWorker _run_task finished successfully.") # Change level to INFO

class LoadConversationWorker(BaseWorker):
    """Worker to fetch a specific conversation."""
    # Emits conversationResult from BaseWorker

    def _run_task(self):
        conv_id = self.args[0]
        self.logger.debug(f"LoadConversationWorker running for ID: {conv_id}")
        conversation = self.conv_service.get_conversation(conv_id) # Sync call
        self.conversationResult.emit(conversation) # Emit result directly
        self.logger.debug(f"LoadConversationWorker finished for ID: {conv_id}")

class LoadBranchWorker(BaseWorker):
    """Worker to fetch the message branch."""
    # Emits branchResult from BaseWorker

    def _run_task(self):
        msg_id = self.args[0]
        self.logger.debug(f"LoadBranchWorker running for message ID: {msg_id}")
        branch = self.conv_service.get_message_branch(msg_id) # Sync call
        self.branchResult.emit(branch) # Emit result directly
        self.logger.debug(f"LoadBranchWorker finished for message ID: {msg_id}")

class CreateConversationWorker(BaseWorker):
    """Worker to create a new conversation."""
    # Emits conversationResult from BaseWorker

    def _run_task(self):
        conv_name = self.args[0]
        self.logger.debug(f"CreateConversationWorker running for name: {conv_name}")
        system_message = self.view_model.settings_vm.get_setting("system_message", "You are a helpful assistant.") # Get from settings
        new_conv = self.conv_service.create_conversation(name=conv_name, system_message=system_message)
        self.conversationResult.emit(new_conv)
        # Trigger list reload *after* emitting the new conversation result
        # This uses another worker started from the ViewModel slot
        if new_conv:
            QTimer.singleShot(0, self.view_model.load_all_conversations_threaded)

class RenameConversationWorker(BaseWorker):
    """Worker to rename a conversation."""
    renameComplete = pyqtSignal(bool, str) # success, conversation_id

    def _run_task(self):
        conv_id, new_name = self.args
        self.logger.debug(f"RenameConversationWorker running for {conv_id} to '{new_name}'")
        success = self.conv_service.update_conversation(conv_id, name=new_name)
        self.renameComplete.emit(success, conv_id)
        # Trigger list reload if successful
        if success:
             QTimer.singleShot(0, self.view_model.load_all_conversations_threaded)

class DeleteConversationWorker(BaseWorker):
    """Worker to delete a conversation."""
    deleteComplete = pyqtSignal(bool, str) # success, deleted_id

    def _run_task(self):
        conv_id = self.args[0]
        self.logger.debug(f"DeleteConversationWorker running for {conv_id}")
        success = self.conv_service.delete_conversation(conv_id)
        self.deleteComplete.emit(success, conv_id)
         # Trigger list reload if successful
        if success:
             QTimer.singleShot(0, self.view_model.load_all_conversations_threaded)

class SendMessageWorker(BaseWorker):
    """Worker to send a message, call API, and save response."""
    # Specific signals for this process
    userMessageSaved = pyqtSignal(object)      # Emits the saved user Message object/dict
    assistantMessageSaved = pyqtSignal(object) # Emits the saved assistant Message object/dict
    streamChunkReady = pyqtSignal(str)         # Emits a text chunk from streaming API
    tokenUsageReady = pyqtSignal(dict)         # Emits token usage info
    reasoningStepsReady = pyqtSignal(list)     # Emits reasoning steps info (if any)
    messagingDone = pyqtSignal()               # Indicates the entire send/receive cycle is complete

    def _run_task(self):
        conversation_id, content, attachments = self.args
        api_settings_override = self.kwargs.get('api_settings_override', {})
        task_id = self.kwargs.get('task_id', 'send_message_task')

        user_message = None
        assistant_message = None
        stream_buffer = ""
        collected_metadata = {}

        self.logger.debug(f"SendMessageWorker running for conv {conversation_id}")

        # 1. Save User Message
        self.logger.debug("Saving user message...")
        # Determine parent ID based on ViewModel's current branch state *before* adding user msg
        parent_id = self.view_model._current_branch[-1].id if self.view_model._current_branch else None
        user_message = self.conv_service.add_user_message(conversation_id, content, parent_id=parent_id)
        if not user_message:
            raise Exception("Failed to save user message to database.")

        # TODO: Handle saving attachments synchronously if needed
        # for attachment_info in (attachments or []):
        #     # Need file processing logic here (read content, count tokens) - potentially another worker?
        #     # file_details = get_file_info(attachment_info['filePath']) # Synchronous version
        #     # if file_details:
        #     #     self.conv_service.add_file_attachment(user_message.id, file_details)
        #     pass

        self.userMessageSaved.emit(user_message) # Notify ViewModel immediately
        self.logger.debug(f"User message {user_message.id} saved.")

        # 2. Prepare for API Call
        # Get current branch *after* adding user message
        current_branch = self.conv_service.get_message_branch(user_message.id)
        if not current_branch:
             raise Exception("Failed to retrieve message branch after saving user message.")

        # Get API settings
        api_settings = self.api_service._api_settings.copy()
        api_settings.update(self.view_model.settings_vm.get_settings())
        api_settings.update(api_settings_override)

        use_streaming = api_settings.get("stream", True)
        api_type = api_settings.get("api_type", "responses")
        messages_payload = self.api_service._prepare_input(current_branch, api_type)


        # 3. Call API (Streaming or Non-Streaming)
        if use_streaming:
            self.logger.debug("Calling API (Streaming)...")
            stream_iterator = self.api_service.get_streaming_completion(current_branch, api_settings)
            for event in stream_iterator:
                # Process different event types (adapt based on ApiService output)
                if api_type == "responses":
                    event_type = event.get('type')
                    if event_type == 'response.output_text.delta' and 'delta' in event:
                        chunk = event['delta']
                        stream_buffer += chunk
                        self.streamChunkReady.emit(chunk)
                    elif event_type == 'response.completed' and 'response' in event:
                         if 'usage' in event['response']: collected_metadata['token_usage'] = self.api_service.last_token_usage
                         if 'model' in event['response']: collected_metadata['model'] = self.api_service.last_model
                    elif event_type == 'response.created' and 'response' in event:
                         if 'id' in event['response']: collected_metadata['response_id'] = self.api_service.last_response_id
                    elif event_type == 'response.thinking_step':
                         if 'thinking_step' in event:
                              if 'reasoning_steps' not in collected_metadata: collected_metadata['reasoning_steps'] = []
                              collected_metadata['reasoning_steps'].append(self.api_service.last_reasoning_steps[-1])
                else: # chat_completions
                    if 'choices' in event and event['choices']:
                         delta = event['choices'][0].get('delta', {})
                         if 'content' in delta and delta['content']:
                              chunk = delta['content']
                              stream_buffer += chunk
                              self.streamChunkReady.emit(chunk)
                    if 'usage' in event: collected_metadata['token_usage'] = self.api_service.last_token_usage
                    if 'model' in event: collected_metadata['model'] = self.api_service.last_model
                    if 'id' in event: collected_metadata['response_id'] = self.api_service.last_response_id

            self.logger.debug(f"Streaming finished. Collected content length: {len(stream_buffer)}")
            if collected_metadata.get('token_usage'): self.tokenUsageReady.emit(collected_metadata['token_usage'])
            if collected_metadata.get('reasoning_steps'): self.reasoningStepsReady.emit(collected_metadata['reasoning_steps'])

        else: # Non-streaming
            self.logger.debug("Calling API (Non-Streaming)...")
            response_data = self.api_service.get_completion(current_branch, api_settings)
            stream_buffer = response_data.get("content", "")
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
        if stream_buffer:
            assistant_message = self.conv_service.add_assistant_message(
                conversation_id,
                stream_buffer,
                parent_id=user_message.id, # Link to the user message we saved
                model_info=collected_metadata.get('model'),
                token_usage=collected_metadata.get('token_usage'),
                reasoning_steps=collected_metadata.get('reasoning_steps'),
                response_id=collected_metadata.get('response_id')
            )
            if not assistant_message:
                self.logger.error("Failed to save assistant message to database.")
                self.error.emit("Failed to save assistant response.") # Emit specific error
            else:
                self.assistantMessageSaved.emit(assistant_message)
                self.logger.debug(f"Assistant message {assistant_message.id} saved.")
        else:
             self.logger.warning("No content received from API to save for assistant message.")
             self.error.emit("No response content received from API.") # Emit specific error

        # 5. Signal completion
        self.messagingDone.emit() # Signal completion of the cycle


class SearchWorker(BaseWorker):
    """Worker to perform message searches in the database."""
    searchResult = pyqtSignal(list) # List of result dictionaries

    def _run_task(self):
        search_term, conversation_id = self.args
        self.logger.debug(f"SearchWorker running for term '{search_term}' (conv_id: {conversation_id})")
        results = self.conv_service.search_conversations(search_term, conversation_id)
        self.searchResult.emit(results)
        self.logger.debug(f"SearchWorker found {len(results)} results.")

class NavigateWorker(BaseWorker):
    """Worker to update the current message node in a conversation."""
    navigationComplete = pyqtSignal(bool, str, str) # success, conversation_id, target_message_id

    def _run_task(self):
        conversation_id, message_id = self.args
        self.logger.debug(f"NavigateWorker running for conv {conversation_id} to msg {message_id}")
        success = self.conv_service.navigate_to_message(conversation_id, message_id)
        self.navigationComplete.emit(success, conversation_id, message_id)
        self.logger.debug(f"NavigateWorker finished for conv {conversation_id}, msg {message_id}. Success: {success}")

class RetryWorker(BaseWorker):
    """Worker to retry the last assistant response."""
    # Re-use signals from SendMessageWorker
    assistantMessageSaved = pyqtSignal(object)
    streamChunkReady = pyqtSignal(str)
    tokenUsageReady = pyqtSignal(dict)
    reasoningStepsReady = pyqtSignal(list)
    messagingDone = pyqtSignal()

    def _run_task(self):
        current_branch = self.args[0]
        api_settings_override = self.kwargs.get('api_settings_override', {})
        task_id = self.kwargs.get('task_id', 'retry_task')

        assistant_message = None
        stream_buffer = ""
        collected_metadata = {}

        self.logger.debug(f"RetryWorker running for branch ending with {current_branch[-1].id if current_branch else 'None'}")

        # 1. Identify User Message
        if not current_branch or len(current_branch) < 2:
            raise ValueError("Cannot retry: Not enough messages in the current branch.")
        user_message = None
        retry_branch_payload = []
        for i in range(len(current_branch) - 2, -1, -1):
            if current_branch[i].role == 'user':
                user_message = current_branch[i]
                retry_branch_payload = current_branch[:i+1]
                break
        if not user_message:
            raise ValueError("Cannot retry: Could not find a preceding user message.")
        conversation_id = user_message.conversation_id
        self.logger.debug(f"Retrying from user message {user_message.id} in conversation {conversation_id}")

        # 2. Prepare API Call
        api_settings = self.api_service._api_settings.copy()
        api_settings.update(self.view_model.settings_vm.get_settings())
        api_settings.update(api_settings_override)
        use_streaming = api_settings.get("stream", True)
        api_type = api_settings.get("api_type", "responses")
        messages_payload = self.api_service._prepare_input(retry_branch_payload, api_type)

        # 3. Call API (Streaming or Non-Streaming) - Reuse logic
        if use_streaming:
            self.logger.debug("Calling API (Streaming) for retry...")
            stream_iterator = self.api_service.get_streaming_completion(retry_branch_payload, api_settings)
            for event in stream_iterator:
                 # Process stream events (same logic as SendMessageWorker)
                 if api_type == "responses":
                      event_type = event.get('type')
                      if event_type == 'response.output_text.delta' and 'delta' in event:
                          chunk = event['delta']; stream_buffer += chunk; self.streamChunkReady.emit(chunk)
                      elif event_type == 'response.completed' and 'response' in event:
                           if 'usage' in event['response']: collected_metadata['token_usage'] = self.api_service.last_token_usage
                           if 'model' in event['response']: collected_metadata['model'] = self.api_service.last_model
                      elif event_type == 'response.created' and 'response' in event:
                           if 'id' in event['response']: collected_metadata['response_id'] = self.api_service.last_response_id
                      elif event_type == 'response.thinking_step':
                           if 'thinking_step' in event:
                                if 'reasoning_steps' not in collected_metadata: collected_metadata['reasoning_steps'] = []
                                collected_metadata['reasoning_steps'].append(self.api_service.last_reasoning_steps[-1])
                 else: # chat_completions
                      if 'choices' in event and event['choices']:
                           delta = event['choices'][0].get('delta', {})
                           if 'content' in delta and delta['content']:
                                chunk = delta['content']; stream_buffer += chunk; self.streamChunkReady.emit(chunk)
                      if 'usage' in event: collected_metadata['token_usage'] = self.api_service.last_token_usage
                      if 'model' in event: collected_metadata['model'] = self.api_service.last_model
                      if 'id' in event: collected_metadata['response_id'] = self.api_service.last_response_id

            self.logger.debug(f"Streaming finished for retry. Content length: {len(stream_buffer)}")
            if collected_metadata.get('token_usage'): self.tokenUsageReady.emit(collected_metadata['token_usage'])
            if collected_metadata.get('reasoning_steps'): self.reasoningStepsReady.emit(collected_metadata['reasoning_steps'])
        else: # Non-streaming retry
            self.logger.debug("Calling API (Non-Streaming) for retry...")
            response_data = self.api_service.get_completion(retry_branch_payload, api_settings)
            stream_buffer = response_data.get("content", "")
            if response_data.get("token_usage"):
                 collected_metadata['token_usage'] = response_data['token_usage']; self.tokenUsageReady.emit(response_data['token_usage'])
            if response_data.get("reasoning_steps"):
                 collected_metadata['reasoning_steps'] = response_data['reasoning_steps']; self.reasoningStepsReady.emit(response_data['reasoning_steps'])
            if response_data.get("model"): collected_metadata['model'] = response_data['model']
            if response_data.get("response_id"): collected_metadata['response_id'] = response_data['response_id']
            self.logger.debug(f"Non-streaming retry response received. Content length: {len(stream_buffer)}")

        # 4. Save New Assistant Message
        self.logger.debug("Saving NEW assistant message for retry...")
        if stream_buffer:
            assistant_message = self.conv_service.add_assistant_message(
                conversation_id, stream_buffer, parent_id=user_message.id,
                model_info=collected_metadata.get('model'),
                token_usage=collected_metadata.get('token_usage'),
                reasoning_steps=collected_metadata.get('reasoning_steps'),
                response_id=collected_metadata.get('response_id')
            )
            if not assistant_message:
                self.logger.error("Failed to save new assistant message during retry."); self.error.emit("Failed to save retried response.")
            else:
                self.assistantMessageSaved.emit(assistant_message); self.logger.debug(f"New assistant message {assistant_message.id} saved.")
        else:
             self.logger.warning("No content received from API during retry."); self.error.emit("No response content received from API during retry.")

        # 5. Signal completion
        self.messagingDone.emit()

class DuplicateConversationWorker(BaseWorker):
    """Worker to duplicate a conversation."""
    duplicationComplete = pyqtSignal(object) # Emits new Conversation object or None

    def _run_task(self):
        original_conv_id, new_name = self.args
        self.logger.debug(f"DuplicateConversationWorker running for original ID: {original_conv_id}")
        new_conversation = self.conv_service.duplicate_conversation(original_conv_id, new_name)
        self.duplicationComplete.emit(new_conversation)
        self.logger.debug(f"DuplicateConversationWorker finished. New conv ID: {new_conversation.id if new_conversation else 'None'}")


# ==============================
# ConversationViewModel Class
# ==============================
class ConversationViewModel(QObject):
    """
    ViewModel for managing conversation interactions using QThread workers.
    """
    # --- Signals ---
    conversationLoaded = pyqtSignal(object)
    messageAdded = pyqtSignal(object)
    messageUpdated = pyqtSignal(object)
    messageBranchChanged = pyqtSignal(list)
    messageStreamChunk = pyqtSignal(str)
    messagingComplete = pyqtSignal()
    errorOccurred = pyqtSignal(str)
    loadingStateChanged = pyqtSignal(bool)
    tokenUsageUpdated = pyqtSignal(dict)
    reasoningStepsChanged = pyqtSignal(list)
    conversationListUpdated = pyqtSignal(list)
    searchResultsReady = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.logger = get_logger(__name__ + ".ConversationViewModel")

        # Services will be injected or created
        self.conversation_service: Optional[ConversationService] = None
        self.api_service: Optional[ApiService] = None
        self.settings_vm: Optional[SettingsViewModel] = None # Reference to settings VM

        # State variables
        self._current_conversation_id: Optional[str] = None
        self._current_branch: List[Message] = [] # Store actual Message objects if possible
        self._is_loading: bool = False # Tracks if *any* worker is running
        self._token_usage: Dict = {}
        self._stream_buffer: str = "" # May not be needed if QML handles accumulation
        self._model_info: Dict = {}
        self._reasoning_steps: List = []
        self._initialized: bool = False
        self._threads: Dict[str, QThread] = {} # {task_id: QThread}

        self.logger.info("ConversationViewModel constructor completed")
        # Initialization called externally after services are set

    # Call this after setting services
    def initialize_viewmodel(self):
        """Initialize services synchronously."""
        if self._initialized: return
        self.logger.debug("Starting synchronous initialization of ConversationViewModel")
        if not self.conversation_service or not self.api_service or not self.settings_vm:
             self.logger.error("Cannot initialize ViewModel: Services or Settings VM not set.")
             self.errorOccurred.emit("Internal setup error. ViewModel cannot function.")
             return

        self._initialized = self.conversation_service.ensure_initialized()
        if self._initialized:
            self.logger.info("ViewModel initialization completed successfully")
        else:
            self.logger.error("ViewModel initialization failed: DB Service could not initialize.")
            self.errorOccurred.emit("Database initialization failed. Cannot load conversations.")

    # --- Worker Management ---
    def _start_worker(self, task_id: str, worker_class: type, *args, **kwargs):
        # <<< ADD LOGGING >>>
        self.logger.info(f">>> _start_worker entered for task: {task_id}, worker: {worker_class.__name__}")

        if task_id in self._threads and self._threads[task_id].isRunning():
            self.logger.warning(f"Task '{task_id}' is already running. Ignoring request.")
            return

        if task_id in self._threads:
            self.logger.warning(f"Cleaning up previous non-running thread for task: {task_id}")
            try:
                # Attempt graceful cleanup if possible, though shouldn't be necessary if finished signal worked
                if not self._threads[task_id].isFinished():
                    self._threads[task_id].quit()
                    self._threads[task_id].wait(50) # Short wait
                del self._threads[task_id]
            except Exception as e:
                 self.logger.error(f"Error cleaning up previous thread for {task_id}: {e}")


        self.logger.debug(f"Creating QThread for task: {task_id}")
        thread = QThread(self)
        kwargs['conversation_service'] = self.conversation_service
        kwargs['api_service'] = self.api_service
        kwargs['view_model'] = self
        kwargs['task_id'] = task_id

        self.logger.debug(f"Instantiating worker {worker_class.__name__} for task: {task_id}")
        worker = worker_class(*args, **kwargs)
        worker.moveToThread(thread)
        self.logger.debug(f"Worker moved to thread for task: {task_id}")

        # --- Connect signals from Worker to ViewModel Slots ---
        self.logger.debug(f"Connecting worker signals for task: {task_id}...")
        worker.error.connect(self._handle_worker_error)
        self.logger.debug(f"Connected worker.error for task: {task_id}")
        worker.finished.connect(thread.quit)
        self.logger.debug(f"Connected worker.finished -> thread.quit for task: {task_id}")

        # Connect common result signals
        if hasattr(worker, 'conversationResult'): worker.conversationResult.connect(self._handle_conversation_loaded); self.logger.debug(f"Connected worker.conversationResult for task: {task_id}")
        if hasattr(worker, 'conversationListResult'): worker.conversationListResult.connect(self._handle_conversation_list_loaded); self.logger.debug(f"Connected worker.conversationListResult for task: {task_id}")
        if hasattr(worker, 'messageResult'): worker.messageResult.connect(self._handle_message_added); self.logger.debug(f"Connected worker.messageResult for task: {task_id}")
        if hasattr(worker, 'branchResult'): worker.branchResult.connect(self._handle_branch_changed); self.logger.debug(f"Connected worker.branchResult for task: {task_id}")


        # Connect specific worker signals
        if isinstance(worker, SendMessageWorker):
            worker.userMessageSaved.connect(self._handle_user_message_saved)
            worker.assistantMessageSaved.connect(self._handle_assistant_message_saved)
            worker.streamChunkReady.connect(self._handle_stream_chunk)
            worker.tokenUsageReady.connect(self._handle_api_metadata)
            worker.reasoningStepsReady.connect(self._handle_api_metadata)
            worker.messagingDone.connect(self._handle_messaging_done)
        elif isinstance(worker, SearchWorker):
            worker.searchResult.connect(self._handle_search_results)
        elif isinstance(worker, NavigateWorker):
            worker.navigationComplete.connect(self._handle_navigation_complete)
        elif isinstance(worker, RenameConversationWorker):
            worker.renameComplete.connect(self._handle_rename_complete)
        elif isinstance(worker, DeleteConversationWorker):
            worker.deleteComplete.connect(self._handle_delete_complete)
        elif isinstance(worker, RetryWorker):
            worker.assistantMessageSaved.connect(self._handle_assistant_message_saved)
            worker.streamChunkReady.connect(self._handle_stream_chunk)
            worker.tokenUsageReady.connect(self._handle_api_metadata)
            worker.reasoningStepsReady.connect(self._handle_api_metadata)
            worker.messagingDone.connect(self._handle_messaging_done)
        elif isinstance(worker, DuplicateConversationWorker):
            worker.duplicationComplete.connect(self._handle_duplication_complete)
        self.logger.debug(f"Finished connecting worker signals for task: {task_id}.")

        # --- Thread lifecycle ---
        # <<< ADD LOGGING >>>
        self.logger.debug(f"Connecting thread signals for task: {task_id}...")
        thread.finished.connect(worker.deleteLater)
        self.logger.debug(f"Connected thread.finished -> worker.deleteLater for task: {task_id}")
        thread.finished.connect(thread.deleteLater)
        self.logger.debug(f"Connected thread.finished -> thread.deleteLater for task: {task_id}")
        thread.started.connect(worker.run)
        self.logger.debug(f"Connected thread.started -> worker.run for task: {task_id}")
        thread.finished.connect(lambda tid=task_id: self._cleanup_thread(tid))
        self.logger.debug(f"Connected thread.finished -> _cleanup_thread for task: {task_id}")
        self.logger.debug(f"Finished connecting thread signals for task: {task_id}.")

        self._threads[task_id] = thread
        # Update loading state only if this is the *first* thread starting
        if not self._is_loading:
            self._is_loading = True
            self.loadingStateChanged.emit(True)
            self.logger.debug(f"Set loading state to True (task: {task_id}).")

        # <<< ADD LOGGING >>>
        self.logger.info(f"Starting thread for task: {task_id}...")
        thread.start()
        self.logger.info(f"<<< Exiting _start_worker for task: {task_id}")

    def _cleanup_thread(self, task_id: str):
        self.logger.debug(f"Cleaning up finished thread for task: {task_id}")
        if task_id in self._threads:
            del self._threads[task_id]
        # Only set loading to false if NO threads are running
        if not self._threads and self._is_loading:
             self._is_loading = False
             self.loadingStateChanged.emit(False)
             self.logger.debug("All worker threads finished, setting loading state to False.")
        elif self._threads:
             self.logger.debug(f"{len(self._threads)} worker threads still running.")

    # --- Slots for Worker Results/Errors ---

    @pyqtSlot(str)
    def _handle_worker_error(self, error_message: str):
        self.logger.error(f"Worker thread reported error: {error_message}")
        self.errorOccurred.emit(error_message)
        # Don't automatically turn off loading here, wait for _cleanup_thread

    @pyqtSlot(list)
    def _handle_conversation_list_loaded(self, conversations_list: list):
        self.logger.info(f">>> SLOT _handle_conversation_list_loaded called with {len(conversations_list)} items.")
        self.conversationListUpdated.emit(conversations_list)
        if conversations_list:
            first_id = conversations_list[0].get('id')
            if first_id:
                load_task_id = f"load_conv_{first_id}"
                if first_id != self._current_conversation_id and load_task_id not in self._threads:
                    self.logger.debug(f"Slot loading first conversation: {first_id}")
                    self.load_conversation(first_id)
                elif first_id == self._current_conversation_id:
                    self.logger.debug(f"First conversation {first_id} is already current.")
                    # Ensure branch is loaded if not already loading
                    branch_target_id = self._current_branch[-1].id if self._current_branch else None
                    conv = self.conversation_service._conversation_cache.get(self._current_conversation_id) # Check cache
                    if not branch_target_id and conv: branch_target_id = conv.current_node_id

                    if branch_target_id and f"load_branch_{branch_target_id}" not in self._threads:
                         self.load_message_branch(branch_target_id)

                else: self.logger.debug(f"Already loading conversation {first_id}.")
            else: self.logger.warning("First conversation in list has no ID.")
        elif not self._threads: # Only create new if no other threads (like load_all) are running
            self.logger.info("No conversations found, creating a new one.")
            if "create_conv" not in self._threads:
                self.create_new_conversation("New Conversation")

    @pyqtSlot(object)
    def _handle_conversation_loaded(self, conversation: Optional[Conversation]):
        if conversation:
             task_id = f"load_conv_{conversation.id}"
             self.logger.info(f"Handling loaded conversation: {conversation.id} from task {task_id}")
             if conversation.id == self._current_conversation_id:
                 self.conversationLoaded.emit(conversation)
                 if conversation.current_node_id:
                     self.load_message_branch(conversation.current_node_id)
                 else:
                     self.logger.warning(f"Loaded conversation {conversation.id} has no current node_id.")
                     self._current_branch = []
                     self.messageBranchChanged.emit([])
             else:
                  self.logger.warning(f"Received loaded conversation {conversation.id}, but current selection is now {self._current_conversation_id}. Discarding.")
        else:
             self.logger.error(f"Handling loaded conversation: Received None for ID {self._current_conversation_id}")
             # Clear UI for the failed load?
             if self._current_conversation_id: # Check if it matches the intended load
                  self._current_conversation_id = None
                  self._current_branch = []
                  self.conversationLoaded.emit(None) # Signal failure
                  self.messageBranchChanged.emit([])

    @pyqtSlot(list)
    def _handle_branch_changed(self, branch: List[Message]):
         self.logger.info(f"Handling branch change for conv {self._current_conversation_id}, {len(branch)} messages.")
         self._current_branch = branch
         self.messageBranchChanged.emit(branch)

    @pyqtSlot(object)
    def _handle_message_added(self, message: Optional[Message]):
         if message:
             self.logger.info(f"Handling added message: {message.id} (Role: {message.role})")
             self.messageAdded.emit(message)
             # If assistant message added, load its branch (handled by specific handlers now)
             # if message.role == 'assistant': self.load_message_branch(message.id)
         else:
             self.logger.error("Handling added message: Received None")

    @pyqtSlot(list)
    def _handle_search_results(self, results: list):
        self.logger.info(f"Received {len(results)} search results from worker.")
        self.searchResultsReady.emit(results)

    @pyqtSlot(bool, str, str)
    def _handle_navigation_complete(self, success: bool, conversation_id: str, target_message_id: str):
        if success:
            self.logger.info(f"Navigation DB update successful for conv {conversation_id} to msg {target_message_id}.")
            if conversation_id == self._current_conversation_id:
                 self.load_message_branch(target_message_id)
            else:
                 self.logger.warning(f"Navigation complete for {conversation_id}, but current conv is now {self._current_conversation_id}. Not loading branch.")
        else:
            self.logger.error(f"Navigation DB update failed for conv {conversation_id} to msg {target_message_id}.")

    @pyqtSlot(bool, str)
    def _handle_rename_complete(self, success: bool, conversation_id: str):
        if success: self.logger.info(f"Conversation {conversation_id} renamed successfully.")
        else: self.logger.error(f"Failed to rename conversation {conversation_id}.")

    @pyqtSlot(bool, str)
    def _handle_delete_complete(self, success: bool, deleted_id: str):
        if success:
             self.logger.info(f"Conversation {deleted_id} deleted successfully.")
             if self._current_conversation_id == deleted_id:
                  self._current_conversation_id = None
                  self._current_branch = []
                  # Wait for list reload to load next conversation
        else:
             self.logger.error(f"Failed to delete conversation {deleted_id}.")

    @pyqtSlot(object)
    def _handle_duplication_complete(self, new_conversation: Optional[Conversation]):
        if new_conversation:
            self.logger.info(f"Duplication successful. New conversation ID: {new_conversation.id}")
            self.load_all_conversations_threaded() # Reload list
        else:
            self.logger.error("Duplication failed.")

    # --- Slots for Send/Retry Worker Specific Signals ---
    @pyqtSlot()
    def _handle_messaging_done(self):
        self.logger.debug("Slot received messaging cycle complete.")
        self.messagingComplete.emit()

    @pyqtSlot(object)
    def _handle_user_message_saved(self, user_message: Message):
        self.logger.debug(f"Slot received saved user message: {user_message.id}")
        self.messageAdded.emit(user_message)
        # Don't update branch here, wait for assistant response

    @pyqtSlot(str)
    def _handle_stream_chunk(self, chunk: str):
        # self.logger.debug(f"Slot received stream chunk (len {len(chunk)})") # Too noisy
        self.messageStreamChunk.emit(chunk)

    @pyqtSlot(dict)
    def _handle_api_metadata(self, metadata: dict):
        # This handles both tokenUsageReady and reasoningStepsReady
        self.logger.debug(f"Slot received API metadata: {metadata.keys()}")
        is_token_update = "prompt_tokens" in metadata # Check if it's token usage
        if is_token_update:
            self._token_usage = metadata
            self.tokenUsageUpdated.emit(self._token_usage)
        else: # Assume it's reasoning steps
            self._reasoning_steps = metadata
            self.reasoningStepsChanged.emit(self._reasoning_steps)

    @pyqtSlot(object)
    def _handle_assistant_message_saved(self, assistant_message: Message):
        self.logger.debug(f"Slot received saved assistant message: {assistant_message.id}")
        self.messageAdded.emit(assistant_message) # Emit final message
        # Trigger final branch update to ensure UI consistency
        self.load_message_branch(assistant_message.id)


    # --- Public Slots for QML Interaction ---

    @pyqtSlot()
    def load_all_conversations_threaded(self):
        """Loads all conversations using a background thread."""
        # <<< ADD LOGGING >>>
        self.logger.info(">>> load_all_conversations_threaded called")
        if not self._initialized:
            self.logger.warning("Cannot load conversations: Service not initialized.")
            self.conversationListUpdated.emit([])
            return
        self.logger.debug("Initiating background load for all conversations.")
        self._start_worker("load_all_convs", LoadConversationsWorker)
        # <<< ADD LOGGING >>>
        self.logger.debug("<<< Exiting load_all_conversations_threaded")

    @pyqtSlot(str)
    def load_conversation(self, conversation_id: str):
        """Load a conversation by ID using a background thread."""
        if not conversation_id:
             self.logger.error("load_conversation called with empty ID.")
             return
        task_id = f"load_conv_{conversation_id}"
        if conversation_id == self._current_conversation_id and task_id not in self._threads:
             self.logger.debug(f"Conversation {conversation_id} already current and not loading.")
             # Ensure branch is loaded if needed
             branch_target_id = self._current_branch[-1].id if self._current_branch else None
             conv = self.conversation_service._conversation_cache.get(self._current_conversation_id) # Check cache
             if not branch_target_id and conv: branch_target_id = conv.current_node_id
             if branch_target_id and f"load_branch_{branch_target_id}" not in self._threads:
                  self.load_message_branch(branch_target_id)
             return

        self.logger.debug(f"Initiating background load for conversation: {conversation_id}")
        self._current_conversation_id = conversation_id # Update target ID immediately
        self._start_worker(task_id, LoadConversationWorker, conversation_id)

    # Keep the load_message_branch method mostly the same, just uses the worker class above
    def load_message_branch(self, message_id: str):
        """Loads message branch up to message_id using a background thread."""
        if not message_id:
             self.logger.warning("load_message_branch called with no message_id.")
             self._current_branch = []
             self.messageBranchChanged.emit([])
             # If this was the last step in loading, ensure loading indicator stops
             if not self._threads and self._is_loading:
                  self._is_loading = False; self.loadingStateChanged.emit(False)
             return

        self.logger.debug(f"Initiating background load for message branch ending at: {message_id}")
        task_id = f"load_branch_{message_id}"
        self._start_worker(task_id, LoadBranchWorker, message_id)

    @pyqtSlot(str)
    def create_new_conversation(self, name="New Conversation"):
        """Create a new conversation using a background thread."""
        self.logger.debug(f"Initiating background creation for new conversation: {name}")
        self._start_worker("create_conv", CreateConversationWorker, name)

    @pyqtSlot(str, str)
    def rename_conversation(self, conversation_id, new_name):
        """Rename a conversation using a background thread."""
        self.logger.debug(f"Initiating background rename for conv {conversation_id} to '{new_name}'")
        task_id = f"rename_conv_{conversation_id}"
        self._start_worker(task_id, RenameConversationWorker, conversation_id, new_name)

    @pyqtSlot(str)
    def delete_conversation(self, conversation_id):
        """Delete a conversation using a background thread."""
        self.logger.debug(f"Initiating background delete for conversation: {conversation_id}")
        task_id = f"delete_conv_{conversation_id}"
        self._start_worker(task_id, DeleteConversationWorker, conversation_id)

    @pyqtSlot(str, str, "QVariant")
    def send_message(self, conversation_id, content, attachments=None):
        """Send a user message and get response using SendMessageWorker."""
        if not conversation_id:
            self.logger.error("send_message called with no conversation ID."); self.errorOccurred.emit("Cannot send message: No conversation selected."); return
        if not content.strip():
            self.logger.warning("send_message called with empty content."); return

        self.logger.debug(f"Initiating SendMessageWorker for conversation {conversation_id}")
        task_id = f"send_msg_{conversation_id}_{uuid.uuid4().hex[:6]}"

        processed_attachments = []
        if attachments:
            for attach in attachments:
                processed_attachments.append({
                    'fileName': getattr(attach, 'fileName', attach.get('fileName', 'unknown')),
                    'filePath': getattr(attach, 'filePath', attach.get('filePath', None)),
                })

        self._start_worker(task_id, SendMessageWorker, conversation_id, content, processed_attachments)

    @pyqtSlot(str)
    def navigate_to_message(self, message_id: str):
        """Starts the process to navigate to a specific message."""
        if not self._current_conversation_id:
            self.logger.error("Cannot navigate: No current conversation ID set."); self.errorOccurred.emit("Cannot navigate: No conversation selected."); return
        if not message_id:
             self.logger.error("Cannot navigate: No message ID provided."); self.errorOccurred.emit("Cannot navigate: Invalid message selected."); return
        if self._current_branch and self._current_branch[-1].id == message_id:
             self.logger.debug(f"Already at target message {message_id}. No navigation needed."); return

        self.logger.info(f"Navigation requested to message: {message_id} in conversation {self._current_conversation_id}")
        task_id = f"navigate_{self._current_conversation_id}_{message_id}"
        self._start_worker(task_id, NavigateWorker, self._current_conversation_id, message_id)

    @pyqtSlot()
    def retry_last_response(self):
        """Initiates a retry of the last assistant response."""
        if not self._current_conversation_id:
            self.logger.error("Cannot retry: No current conversation."); self.errorOccurred.emit("Cannot retry: No conversation selected."); return
        if not self._current_branch or len(self._current_branch) < 2:
             self.logger.error("Cannot retry: Not enough messages."); self.errorOccurred.emit("Cannot retry: No previous message."); return
        if self._current_branch[-1].role != 'assistant':
             self.logger.error("Cannot retry: Last message not from assistant."); self.errorOccurred.emit("Cannot retry: Last message not assistant response."); return

        self.logger.info(f"Retry requested for conversation {self._current_conversation_id}")
        task_id = f"retry_{self._current_conversation_id}_{uuid.uuid4().hex[:6]}"
        branch_copy = list(self._current_branch)
        self._start_worker(task_id, RetryWorker, branch_copy)

    @pyqtSlot(str, str)
    def duplicate_conversation(self, original_conversation_id: str, new_name: Optional[str] = None):
        """Starts the process to duplicate a conversation."""
        if not original_conversation_id:
            self.logger.error("Cannot duplicate: No original ID."); self.errorOccurred.emit("Cannot duplicate: Invalid conversation."); return

        self.logger.info(f"Duplication requested for conversation: {original_conversation_id}")
        task_id = f"duplicate_{original_conversation_id}"
        self._start_worker(task_id, DuplicateConversationWorker, original_conversation_id, new_name)


    # --- Synchronous Methods (If Any) ---
    # Search can remain synchronous if performance is acceptable for expected data size
    @pyqtSlot(str, str, result="QVariant")
    def search_conversations(self, search_term, conversation_id=None):
        """Search conversations (synchronous - consider worker if slow)."""
        self.logger.debug(f"Searching conversations (sync) for '{search_term}'")
        if not self.ensure_initialized(): return []
        try:
            # Note: Direct service call - blocks caller until DB search completes.
            results = self.conversation_service.search_conversations(search_term, conversation_id)
            return results
        except Exception as e:
            self.logger.error(f"Error during synchronous search: {e}", exc_info=True)
            self.errorOccurred.emit(f"Search failed: {e}")
            return []

    # Helper for sync initialization check
    def ensure_initialized(self) -> bool:
        """Ensure the service is initialized."""
        if not self._initialized:
            # Try initializing again? Or just return false?
            self.logger.warning("Service accessed before initialization complete.")
            return self._initialized # Return current state
        return True

    # --- Cleanup ---
    def cleanup(self):
        """Cleanup resources, including stopping threads."""
        self.logger.info("Cleaning up ConversationViewModel resources")
        active_thread_ids = list(self._threads.keys())
        if active_thread_ids:
             self.logger.warning(f"Waiting for {len(active_thread_ids)} worker threads to finish...")
             for thread_id in active_thread_ids:
                  thread = self._threads.get(thread_id)
                  if thread and thread.isRunning():
                      thread.quit()
                      if not thread.wait(3000):
                           self.logger.error(f"Thread {thread_id} did not finish gracefully, terminating.")
                           thread.terminate()
        self._threads.clear()
        self._is_loading = False # Ensure loading state is off

        # Close services (if VM owns them)
        if hasattr(self.api_service, 'close'): self.api_service.close()
        if hasattr(self.conversation_service, 'close'): self.conversation_service.close()

        self.logger.info("ConversationViewModel cleanup completed")