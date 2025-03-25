
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer
import asyncio
import threading

from src.services.database import AsyncConversationService
from src.services.api import AsyncApiService
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
        """Initialize the ViewModel with async services - fixed version"""
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
        QTimer.singleShot(300, self._initialize_in_thread)

    def _initialize_in_thread(self):
        """Initialize services in a background thread to avoid blocking the UI"""
        self.logger.debug("Starting initialization in background thread")

        def init_thread():
            try:
                # Create and set event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Run the initialization
                result = loop.run_until_complete(self._initialize_async())

                # Update state on main thread
                QTimer.singleShot(0, lambda: self._handle_init_complete(result))
            except Exception as e:
                self.logger.error(f"Error in initialization thread: {str(e)}")
                # Report error on main thread
                QTimer.singleShot(0, lambda: self.errorOccurred.emit(f"Initialization error: {str(e)}"))

        # Start thread
        thread = threading.Thread(target=init_thread)
        thread.daemon = True
        thread.start()

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
        """Load a conversation by ID with improved error handling"""
        if conversation_id == self._current_conversation_id:
            return  # Already loaded

        self._current_conversation_id = conversation_id
        self.logger.debug(f"Loading conversation: {conversation_id}")

        # Schedule the operation to run asynchronously
        self._run_in_thread(self._load_conversation_impl, conversation_id)

    def _run_in_thread(self, func, *args):
        """Run an async function in a background thread"""
        def thread_target():
            try:
                # Set up a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Run the function
                result = loop.run_until_complete(func(*args))

                # Clean up
                loop.close()
                return result
            except Exception as e:
                self.logger.error(f"Error in thread: {str(e)}")
                # Report error on main thread
                QTimer.singleShot(0, lambda: self.errorOccurred.emit(f"Error: {str(e)}"))

        # Start the thread
        thread = threading.Thread(target=thread_target)
        thread.daemon = True
        thread.start()
        return thread

    async def _load_conversation_impl(self, conversation_id):
        """Implementation of load_conversation that runs in a thread"""
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

            # Use QTimer to safely emit signals from the main thread
            QTimer.singleShot(0, lambda: self.conversationLoaded.emit(conversation))

            # Load message branch
            if conversation.current_node_id:
                branch = await self.conversation_service.get_message_branch(conversation.current_node_id)
                # Update UI on main thread
                QTimer.singleShot(0, lambda: self._update_branch(branch))

            return conversation
        except Exception as e:
            self.logger.error(f"Error loading conversation: {str(e)}")
            QTimer.singleShot(0, lambda: self.errorOccurred.emit(f"Error loading conversation: {str(e)}"))
            return None

    def _update_branch(self, branch):
        """Update the current branch and notify UI (called on main thread)"""
        self._current_branch = branch
        self.messageBranchChanged.emit(branch)

    @pyqtSlot(str)
    def create_new_conversation(self, name="New Conversation"):
        """Create a new conversation with improved thread safety"""
        self.logger.debug(f"Creating new conversation with name: {name}")

        # Run in background thread
        self._run_in_thread(self._create_conversation_impl, name)

    async def _create_conversation_impl(self, name):
        """Implementation of create_new_conversation that runs in a thread"""
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

            # Schedule loading the new conversation on the main thread
            QTimer.singleShot(0, lambda: self.load_conversation(conversation.id))

            return conversation
        except Exception as e:
            self.logger.error(f"Error creating conversation: {str(e)}")
            QTimer.singleShot(0, lambda: self.errorOccurred.emit(f"Error creating conversation: {str(e)}"))
            return None