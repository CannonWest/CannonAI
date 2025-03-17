"""
Main window UI for the OpenAI Chat application.
"""
import json
import time
from typing import Optional, Dict, Any
from functools import partial

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QMessageBox, QFileDialog, QMenu
)
from PyQt6.QtCore import Qt, QSettings, QUuid
from PyQt6.QtGui import QFont, QIcon, QColor, QPalette, QAction, QTextCursor

from src.utils import DARK_MODE
from src.models import DBConversationManager, DBMessageNode
from src.services import OpenAIAPIWorker, OpenAIThreadManager, SettingsManager
from src.ui.conversation import ConversationBranchTab
from src.ui.components import SettingsDialog, SearchDialog
from src.models.db_manager import DatabaseManager
from src.utils.logging_utils import get_logger

# Get a logger for this module
logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenAI Chat Interface")
        self.setMinimumSize(900, 700)
        self.logger = get_logger(f"{__name__}.MainWindow")

        # Initialize settings and conversation managers
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.get_settings()

        # PyQt6 thread manager
        self.thread_manager = OpenAIThreadManager()

        # Initialize UI components first - this ensures the UI is responsive
        # even if database operations take time
        self.setup_ui()

        # Set up styling
        self.setup_style()

        try:
            # Use the new database-backed conversation manager
            self.conversation_manager = DBConversationManager()

            # Initialize database manager for direct database operations
            # This will use the singleton instance
            self.db_manager = DatabaseManager()

            # Debug: Print all conversations in database - with error handling
            try:
                self.db_manager.debug_print_conversations()
            except Exception as db_error:
                self.logger.error(f"Error printing conversations: {str(db_error)}")
                # Continue anyway - this is just diagnostic

            # Load saved conversations with error handling
            try:
                self.load_conversations()
            except Exception as load_error:
                self.logger.error(f"Error loading conversations: {str(load_error)}")
                QMessageBox.warning(
                    self,
                    "Database Error",
                    f"Error loading conversations: {str(load_error)}\n\nA new conversation will be created."
                )

            # Create a default conversation if none exists
            if not self.conversation_manager.active_conversation:
                self.create_new_conversation()

        except Exception as e:
            self.logger.error(f"Error initializing database components: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())

            # Show error to user
            QMessageBox.critical(
                self,
                "Database Error",
                f"Error initializing the application database: {str(e)}\n\n"
                "The application may not function correctly."
            )

            # Create a minimal conversation manager to prevent crashes
            from src.models.db_conversation_manager import DBConversationManager
            self.conversation_manager = DBConversationManager()

            # Create a default conversation
            self.create_new_conversation()

    def setup_ui(self):
        """Set up the main UI components"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # App header
        self.header = QWidget()
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(10, 5, 10, 5)

        self.app_title = QLabel("OpenAI Chat")
        self.app_title.setFont(QFont("Arial", 16, QFont.Weight.Bold))

        self.settings_button = QPushButton("⚙️ Settings")
        self.settings_button.clicked.connect(self.open_settings)

        self.header_layout.addWidget(self.app_title, 5)
        self.header_layout.addWidget(self.settings_button, 1)

        # Conversation tabs
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)

        # Enable context menu for tabs
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_tab_context_menu)

        # Add a "+" button to create new tabs
        self.tabs.setCornerWidget(self.create_add_tab_button())

        # Add components to main layout
        self.main_layout.addWidget(self.header)
        self.main_layout.addWidget(self.tabs)

        # Create menu bar
        self.create_menu_bar()

    def create_menu_bar(self):
        """Create the application menu bar"""
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("File")

        new_action = QAction("New Conversation", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.create_new_conversation)
        file_menu.addAction(new_action)

        save_action = QAction("Save Conversations", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_conversations)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menu_bar.addMenu("Edit")

        rename_action = QAction("Rename Conversation", self)
        rename_action.triggered.connect(self.rename_current_conversation)
        edit_menu.addAction(rename_action)
        rename_action.setShortcut("F2")

        # Add duplicate action
        duplicate_action = QAction("Duplicate Conversation", self)
        duplicate_action.setShortcut("Ctrl+D")
        duplicate_action.triggered.connect(self.duplicate_current_conversation)
        edit_menu.addAction(duplicate_action)

        # Add search action
        search_action = QAction("Search Conversations", self)
        search_action.setShortcut("Ctrl+F")
        search_action.triggered.connect(self.search_conversations)
        edit_menu.addAction(search_action)

        # Help menu
        help_menu = menu_bar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    # Add the search_conversations method to the MainWindow class
    def search_conversations(self):
        """Open the search dialog to search through conversations"""
        dialog = SearchDialog(self.conversation_manager, self)

        # Connect the message_selected signal to navigate to the message
        dialog.message_selected.connect(self.navigate_to_message)

        dialog.exec()

    def navigate_to_message(self, message_data):
        """Navigate to a specific message from search results"""
        # Parse the message data (format: "conversation_id:node_id")
        conversation_id, node_id = message_data.split(":")

        # Find the conversation tab
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if tab.conversation_tree.id == conversation_id:
                # Switch to this tab
                self.tabs.setCurrentIndex(i)

                # Navigate to the node
                tab.navigate_to_node(node_id)
                break
        else:
            # If the conversation isn't currently open, open it
            if conversation_id in self.conversation_manager.conversations:
                conversation = self.conversation_manager.conversations[conversation_id]
                self.add_conversation_tab(conversation)

                # Get the newly added tab
                tab = self.tabs.widget(self.tabs.count() - 1)

                # Navigate to the node
                tab.navigate_to_node(node_id)
            else:
                QMessageBox.warning(self, "Navigation Error",
                                    "Could not find the conversation for this message.")

    def create_add_tab_button(self) -> QWidget:
        """Create a button to add new conversation tabs"""
        button = QPushButton("+")
        button.setToolTip("New Conversation")

        # Create a local function to avoid reference issues
        def create_new_tab():
            self.create_new_conversation()

        button.clicked.connect(create_new_tab)
        return button

    def show_tab_context_menu(self, position):
        """Show context menu for tabs"""
        # Get the tab index at the position
        tab_index = self.tabs.tabBar().tabAt(position)
        if tab_index >= 0:
            # Create context menu
            context_menu = QMenu(self)

            # Add actions
            rename_action = QAction("Rename", self)
            rename_action.triggered.connect(lambda: self.rename_conversation_at_index(tab_index))

            duplicate_action = QAction("Duplicate", self)
            duplicate_action.triggered.connect(lambda: self.duplicate_conversation_at_index(tab_index))

            close_action = QAction("Close", self)
            close_action.triggered.connect(lambda: self.close_tab(tab_index))

            # Add actions to menu
            context_menu.addAction(rename_action)
            context_menu.addAction(duplicate_action)
            context_menu.addSeparator()
            context_menu.addAction(close_action)

            # Show the menu
            context_menu.exec(self.tabs.mapToGlobal(position))

    def duplicate_current_conversation(self):
        """Duplicate the current conversation tab"""
        current_index = self.tabs.currentIndex()
        if current_index >= 0:
            self.duplicate_conversation_at_index(current_index)

    def duplicate_conversation_at_index(self, index):
        """Duplicate the conversation at the given tab index"""
        if index < 0 or index >= self.tabs.count():
            return

        # Get the source conversation
        source_tab = self.tabs.widget(index)
        source_conversation = source_tab.conversation_tree

        # Create a new conversation with the same name but with "Copy" appended
        new_name = f"{source_conversation.name} (Copy)"
        new_conversation = self.conversation_manager.create_conversation(name=new_name)

        # Copy the root system message
        new_conversation.root.content = source_conversation.root.content

        # Duplicate the conversation tree structure
        # We'll duplicate the most recent branch path for simplicity
        branch_path = source_conversation.get_current_branch()

        # Skip the root node (system message) as we've already set it
        current_parent = new_conversation.root

        for node in branch_path[1:]:  # Skip the first node (root/system message)
            if node.role == "user":
                # Add user message
                child = new_conversation.add_user_message(node.content)
            elif node.role == "assistant":
                # Add assistant response with the same metadata
                child = new_conversation.add_assistant_response(
                    node.content,
                    model_info=node.model_info.copy() if node.model_info else None,
                    parameters=node.parameters.copy() if node.parameters else None,
                    token_usage=node.token_usage.copy() if node.token_usage else None
                )
            else:
                # For any other role, create a generic node
                child = DBMessageNode(
                    id=str(QUuid.createUuid()),
                    role=node.role,
                    content=node.content,
                    parent=current_parent
                )
                current_parent.add_child(child)
                new_conversation.current_node = child

            current_parent = child

        # Create a tab for the new conversation
        self.add_conversation_tab(new_conversation)

        # Save the new conversation
        self.save_conversation(new_conversation.id)

        # Show success message
        QMessageBox.information(
            self,
            "Conversation Duplicated",
            f"Conversation has been duplicated as '{new_name}'."
        )

    def rename_conversation_at_index(self, index):
        """Rename the conversation at the given tab index"""
        if index < 0 or index >= self.tabs.count():
            return

        tab = self.tabs.widget(index)
        conversation = tab.conversation_tree

        # Ask for a new name using an input dialog instead of file dialog
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Conversation",
            "Enter new conversation name:",
            text=conversation.name
        )

        if ok and new_name:
            # Update the conversation name
            conversation.name = new_name

            # Update the tab title
            self.tabs.setTabText(index, new_name)

            # Update the name in the database - this ensures it's saved
            if hasattr(conversation, 'update_name'):
                conversation.update_name(new_name)
            else:
                # If update_name doesn't exist, update the database directly
                conn = self.db_manager.get_connection()
                if conn:
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            'UPDATE conversations SET name = ? WHERE id = ?',
                            (new_name, conversation.id)
                        )
                        conn.commit()
                    except Exception as e:
                        print(f"Error updating conversation name: {str(e)}")
                        conn.rollback()
                    finally:
                        conn.close()

            # Save the conversation
            self.save_conversation(conversation.id)

    def rename_current_conversation(self):
        """Rename the current conversation"""
        # Get the current tab
        index = self.tabs.currentIndex()
        if index < 0:
            return

        self.rename_conversation_at_index(index)

    def setup_style(self):
        """Set up the application styling"""
        # Set application-wide dark mode palette
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(DARK_MODE["background"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(DARK_MODE["foreground"]))
        palette.setColor(QPalette.ColorRole.Base, QColor(DARK_MODE["highlight"]))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(DARK_MODE["background"]))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(DARK_MODE["background"]))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(DARK_MODE["foreground"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(DARK_MODE["foreground"]))
        palette.setColor(QPalette.ColorRole.Button, QColor(DARK_MODE["highlight"]))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(DARK_MODE["foreground"]))
        palette.setColor(QPalette.ColorRole.Link, QColor(DARK_MODE["accent"]))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(DARK_MODE["accent"]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(DARK_MODE["foreground"]))

        self.setPalette(palette)

        # Additional styling
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {DARK_MODE["background"]}; }}
            QTabWidget::pane {{ 
                border: 1px solid {DARK_MODE["accent"]}; 
                background-color: {DARK_MODE["background"]};
            }}
            QTabBar::tab {{ 
                background-color: {DARK_MODE["highlight"]}; 
                color: {DARK_MODE["foreground"]}; 
                padding: 8px 12px; 
                border-top-left-radius: 4px; 
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{ 
                background-color: {DARK_MODE["accent"]}; 
                color: {DARK_MODE["foreground"]}; 
            }}
            QPushButton {{ 
                background-color: {DARK_MODE["highlight"]}; 
                color: {DARK_MODE["foreground"]}; 
                padding: 8px; 
                border-radius: 4px; 
                border: none;
            }}
            QPushButton:hover {{ 
                background-color: {DARK_MODE["accent"]}; 
            }}
            QTextEdit {{ 
                border-radius: 4px; 
                padding: 8px; 
                border: 1px solid {DARK_MODE["accent"]};
            }}
            QLabel {{ color: {DARK_MODE["foreground"]}; }}
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ 
                background-color: {DARK_MODE["highlight"]}; 
                color: {DARK_MODE["foreground"]}; 
                padding: 6px; 
                border-radius: 4px;
                border: 1px solid {DARK_MODE["accent"]};
            }}
            QGroupBox {{ 
                color: {DARK_MODE["foreground"]}; 
                font-weight: bold; 
                border: 1px solid {DARK_MODE["accent"]}; 
                border-radius: 4px; 
                margin-top: 1.5ex;
                padding: 10px;
            }}
            QGroupBox::title {{ 
                subcontrol-origin: margin; 
                subcontrol-position: top center;
                padding: 0 3px;
            }}
        """)

    def create_new_conversation(self):
        """Create a new conversation and add a tab for it"""
        # Create a new conversation
        conversation = self.conversation_manager.create_conversation()

        # Create a tab for the conversation
        self.add_conversation_tab(conversation)

    def add_conversation_tab(self, conversation):
        """Add a tab for a conversation"""
        # Create the tab widget
        tab = ConversationBranchTab(conversation)

        # Connect signals
        tab.send_message.connect(lambda message: self.send_message(tab, message))
        tab.retry_request.connect(lambda: self.retry_message(tab))
        tab.branch_changed.connect(lambda: self.on_branch_changed(tab))

        # Initialize model info
        current_model = self.settings.get("model", "")
        tab.update_model_info(current_model)

        # Add the tab
        index = self.tabs.addTab(tab, conversation.name)
        self.tabs.setCurrentIndex(index)

    def send_message(self, tab, message):
        """Send a user message and get a response with improved file handling"""
        try:
            # First, make sure we're not already processing a message
            if hasattr(tab, '_processing_message') and tab._processing_message:
                print("DEBUG: Already processing a message, canceling duplicate send request")
                return

            # Mark that we're starting to process a message
            tab._processing_message = True

            # Get the active conversation
            conversation = tab.conversation_tree

            # Check if there are file attachments to include
            attached_files = getattr(tab, '_pending_attachments', None)

            # Debugging
            print(f"DEBUG: Sending message: '{message[:30]}...' with {len(attached_files) if attached_files else 0} attachments")

            try:
                # Show file count in UI
                if attached_files and len(attached_files) > 0:
                    tab.start_loading_indicator()
                    tab.chat_display.insertHtml(f"<br><span style='color: #FFB86C;'>Processing {len(attached_files)} attachments...</span><br>")

                # Add the user message
                conversation.add_user_message(message, attached_files=attached_files)

                # Update the UI to show the new user message
                tab.update_ui()

                # Start message processing - this will handle the API call
                self._start_message_processing(tab, conversation.get_current_messages())
            except MemoryError:
                # Handle out of memory errors specifically
                self.logger.error("Memory error while processing attachments")
                self.handle_error("Out of memory error: Too many files or files too large. Try reducing the number or size of attachments.")

                # Make sure to reset processing flag on error
                tab._processing_message = False
            except Exception as e:
                self.logger.error(f"Error sending message: {str(e)}")
                self.handle_error(f"Error sending message: {str(e)}")

                # Make sure to reset processing flag on error
                tab._processing_message = False
        except Exception as e:
            self.logger.error(f"Critical error in send_message: {str(e)}")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Critical Error",
                f"An unexpected error occurred while processing your message. Details: {str(e)}"
            )

    def retry_message(self, tab):
        """Retry the current message with possibly different settings"""
        # Get the conversation
        conversation = tab.conversation_tree

        # If the current node is an assistant message, we need to navigate to its parent (user message)
        if conversation.current_node.role == "assistant":
            if not conversation.retry_current_response():
                return
            tab.update_ui()  # Update UI to reflect the navigation
        # Otherwise, verify we're on a user message
        elif conversation.current_node.role != "user":
            return  # Can't retry if not on user/assistant message

        # Start message processing - reuse the same logic as send_message
        self._start_message_processing(tab, conversation.get_current_messages())

    def _start_message_processing(self, tab, messages):
        """
        Start processing a message request with robust error handling.

        Args:
            tab: The tab containing the conversation
            messages: Messages to send to the API
        """
        # Safety check
        if not tab or not messages:
            print("ERROR: Invalid tab or messages in _start_message_processing")
            return

        # Check if tab is already processing a message
        if hasattr(tab, '_processing_message') and tab._processing_message:
            print("WARNING: Tab is already processing a message, cancelling previous request")
            try:
                if hasattr(tab, '_active_thread_id'):
                    thread_id = tab._active_thread_id
                    print(f"DEBUG: Cancelling previous worker thread: {thread_id}")
                    self.thread_manager.cancel_worker(thread_id)

                    # Force cleanup loading indicators
                    if hasattr(tab, 'stop_loading_indicator') and tab._loading_active:
                        print("DEBUG: Cleaning up previous loading indicator")
                        tab.stop_loading_indicator()

                    # Reset processing state to allow new processing
                    tab._processing_message = False
            except Exception as e:
                print(f"Error cancelling previous worker: {str(e)}")

        try:
            # Clear any existing chain of thought steps
            if hasattr(tab, 'clear_cot'):
                tab.clear_cot()

            # Start loading indicator
            if hasattr(tab, 'start_loading_indicator'):
                tab.start_loading_indicator()

            # Mark the tab as processing a message
            tab._processing_message = True

            # Make a copy of messages to prevent potential memory issues
            messages_copy = list(messages)

            # Create worker and thread using the manager
            try:
                thread_id, worker = self.thread_manager.create_worker(
                    messages_copy,
                    self.settings.copy()  # Use a copy of settings to avoid shared state issues
                )

                # Store thread_id with the tab for potential cancellation
                tab._active_thread_id = thread_id

                # Set a reference to the worker in the tab to prevent it from being garbage collected
                tab._current_worker = worker

                # Disconnect any existing connections to prevent signal conflicts
                try:
                    self._disconnect_worker_signals(tab)
                except Exception as e:
                    print(f"Error disconnecting signals: {str(e)}")
                    # Continue anyway

                # Connect signals using direct methods instead of lambdas to reduce memory usage
                streaming_mode = self.settings.get("stream", True)
                if streaming_mode:
                    worker.chunk_received.connect(self._create_chunk_handler(tab))
                    worker.message_received.connect(self._create_streaming_finalizer(tab))
                    worker.completion_id.connect(self._create_response_id_handler(tab))
                else:
                    worker.message_received.connect(self._create_message_handler(tab))
                    worker.completion_id.connect(self._create_completion_id_handler(tab))

                # Connect other signals using factory methods
                worker.thinking_step.connect(self._create_thinking_step_handler(tab))
                worker.reasoning_steps.connect(self._create_reasoning_steps_handler(tab))
                worker.error_occurred.connect(self.handle_error)
                worker.usage_info.connect(self._create_usage_info_handler(tab))
                worker.system_info.connect(self._create_system_info_handler(tab))
                worker.worker_finished.connect(self._create_worker_finished_handler(tab))

                # Start the worker thread
                self.thread_manager.start_worker(thread_id)

                print(f"Started message processing with thread ID: {thread_id}")
                return True
            except Exception as worker_error:
                print(f"ERROR creating worker: {str(worker_error)}")
                if hasattr(tab, 'stop_loading_indicator'):
                    tab.stop_loading_indicator()
                tab._processing_message = False
                return False
        except Exception as e:
            print(f"CRITICAL ERROR in _start_message_processing: {str(e)}")
            import traceback
            traceback.print_exc()

            # Clean up
            if hasattr(tab, 'stop_loading_indicator'):
                tab.stop_loading_indicator()
            tab._processing_message = False
            return False

    def handle_assistant_response(self, tab, content, response_id=None, role="assistant"):
        """Handle the complete response from the assistant with improved state management"""
        self.logger.debug(f"Handling complete assistant response with content length: {len(content)}")

        if not content:
            self.logger.warning("Empty content in assistant response")
            # Even with empty content, we need to cleanup
            if hasattr(tab, 'stop_loading_indicator'):
                tab.stop_loading_indicator()
            return

        try:
            # Stop loading indicator if it's active
            if hasattr(tab, 'stop_loading_indicator'):
                self.logger.debug("Stopping loading indicator")
                tab.stop_loading_indicator()

            # Clear any streaming flags to ensure proper state
            if hasattr(tab, '_is_streaming'):
                tab._is_streaming = False
            if hasattr(tab, '_streaming_started'):
                tab._streaming_started = False
            if hasattr(tab, '_has_loading_text'):
                tab._has_loading_text = False

            # Get the conversation
            conversation = tab.conversation_tree

            if role == "system":
                # Add system response as child of current node
                self.logger.debug("Skipping system response to conversation")
            else:
                # Add assistant response as child of current node
                self.logger.debug("Adding assistant response to conversation")
                conversation.add_assistant_response(  # THIS ONE FIRST
                    content,
                    model_info={},
                    token_usage={},
                    response_id=response_id  # Add Response ID if available
                )

            # Update the UI
            self.logger.debug("Updating UI after adding assistant response")
            tab.update_ui()

            # Save the conversation
            self.logger.debug(f"Saving conversation: {conversation.id}")
            self.save_conversation(conversation.id)

            # Ensure chat display cursor is at the end
            if hasattr(tab, 'chat_display'):
                self.logger.debug("Ensuring cursor at end of chat display")
                cursor = tab.chat_display.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                tab.chat_display.setTextCursor(cursor)
                tab.chat_display.ensureCursorVisible()
        except Exception as e:
            self.logger.error(f"Error in handle_assistant_response: {str(e)}")

    def handle_chunk(self, tab, chunk):
        """
        DEPRECATED: This method should not be called directly anymore.
        Use _handle_chunk_db_only for database operations or let
        _create_chunk_handler handle both UI and database updates.
        """
        self.logger.warning("Deprecated handle_chunk called directly - use _handle_chunk_db_only instead")
        self._handle_chunk_db_only(tab, chunk)

    def _manage_chunk_buffer(self, tab, chunk):
        """Initialize and update the chunk buffer for a tab"""
        try:
            # Initialize buffer if needed
            if not hasattr(tab, '_chunk_buffer') or tab._chunk_buffer is None:
                tab._chunk_buffer = ""
                tab._chunk_counter = 0
                tab._buffer_flush_threshold = 100  # Increased threshold to reduce DB writes
                tab._last_flush_time = time.time()
                self.logger.debug("Initialized chunk buffer for tab")

            # Add new chunk to buffer
            tab._chunk_buffer += chunk
            tab._chunk_counter += 1
        except Exception as e:
            self.logger.error(f"Error managing chunk buffer: {str(e)}")
            # Re-initialize buffer in case of corruption
            tab._chunk_buffer = chunk
            tab._chunk_counter = 1
            tab._buffer_flush_threshold = 100
            tab._last_flush_time = time.time()
            self.logger.debug("Re-initialized chunk buffer after error")

    def _should_flush_buffer(self, tab, is_first_chunk):
        """Determine if the buffer should be flushed to the database with better timing"""
        import time

        # Always flush on first chunk (new assistant message)
        if is_first_chunk:
            return True

        # Time-based flushing - only flush every 1 second at most
        current_time = time.time()
        if not hasattr(tab, '_last_flush_time'):
            tab._last_flush_time = current_time

        # Flush if more than 1 second has passed since last flush
        time_based_flush = (current_time - tab._last_flush_time) > 1.0

        # Flush if we've accumulated enough chunks (increased threshold)
        chunk_threshold_met = tab._chunk_counter >= tab._buffer_flush_threshold

        # Flush if buffer is getting large (to prevent memory issues)
        size_threshold_met = len(tab._chunk_buffer) > 2000  # Increased size threshold

        should_flush = time_based_flush or chunk_threshold_met or size_threshold_met

        # Update last flush time if we're going to flush
        if should_flush:
            tab._last_flush_time = current_time

        return should_flush

    def _flush_buffer_to_database(self, tab, conversation, is_first_chunk):
        """Write accumulated buffer to the database with improved reliability"""

        conn = None
        try:
            # Add debug logging
            self.logger.debug(f"Flushing buffer to database, size: {len(tab._chunk_buffer)}, first chunk: {is_first_chunk}")
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            if is_first_chunk:
                # First chunk - create a new assistant node with the buffer content
                self.logger.debug("Creating new assistant node for first chunk")
                new_node = conversation.add_assistant_response(tab._chunk_buffer)

                # Store an empty reasoning_steps list on the node
                if not hasattr(new_node, 'reasoning_steps'):
                    setattr(new_node, 'reasoning_steps', [])

                # Store reference to new node ID for tracking
                tab._current_assistant_node_id = new_node.id
                self.logger.debug(f"Created new assistant node: {new_node.id}")
            else:
                # Update existing node with accumulated buffer
                if not hasattr(conversation.current_node, 'id'):
                    self.logger.error("Current node has no ID - cannot update database")
                    return

                node_id = conversation.current_node.id
                self.logger.debug(f"Updating existing node: {node_id}")

                cursor.execute(
                    '''
                    UPDATE messages SET content = content || ? WHERE id = ?
                    ''',
                    (tab._chunk_buffer, node_id)
                )

                # Also update the in-memory version
                if hasattr(conversation.current_node, 'content'):
                    conversation.current_node.content += tab._chunk_buffer
                else:
                    self.logger.warning("Current node has no content attribute")

            # Commit the changes
            conn.commit()
            self.logger.debug("Database updated successfully")

            # Reset buffer after successful commit
            old_size = len(tab._chunk_buffer)
            tab._chunk_buffer = ""
            tab._chunk_counter = 0
            self.logger.debug(f"Buffer reset (cleared {old_size} characters)")

        except Exception as e:
            self.logger.error(f"Database error in _flush_buffer_to_database: {str(e)}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()


    def _update_ui_for_chunk(self, tab, conversation, chunk, is_first_chunk):
        """Update the UI based on the new chunk"""
        try:
            if is_first_chunk:
                # For first chunk, do a full UI update to ensure assistant prefix appears
                tab.update_ui()
            else:
                # For subsequent chunks, just update the streaming display with the chunk
                tab.update_chat_streaming(chunk)
        except Exception as e:
            print(f"DEBUG: UI error in _update_ui_for_chunk: {str(e)}")

    def _ensure_complete_content(self, tab, conversation, full_content, response_id=None):
        """Ensure the node has the complete content from the streamed response"""
        self.logger.info(f"Ensuring complete content (length: {len(full_content)})")

        node_id = None

        # Get the current node ID - might be different ways it's stored
        if hasattr(conversation, 'current_node') and conversation.current_node:
            if conversation.current_node.role == "assistant":
                node_id = conversation.current_node.id

        # Also check for stored assistant node ID from first chunk
        if not node_id and hasattr(tab, '_current_assistant_node_id'):
            node_id = tab._current_assistant_node_id

        if not node_id:
            self.logger.error("Could not determine assistant node ID for content update")
            return

        self.logger.debug(f"Updating content for node: {node_id}")

        # Compare with existing content if available
        existing_content = ""
        if hasattr(conversation.current_node, 'content'):
            existing_content = conversation.current_node.content

        if existing_content == full_content:
            self.logger.debug("Content already matches - no update needed")
            return

        # Content differs - update the database
        conn = None
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            # Update with complete content
            if response_id:
                cursor.execute(
                    '''
                    UPDATE messages SET content = ?, response_id = ? WHERE id = ?
                    ''',
                    (full_content, response_id, node_id)
                )
            else:
                cursor.execute(
                    '''
                    UPDATE messages SET content = ? WHERE id = ?
                    ''',
                    (full_content, node_id)
                )

            conn.commit()
            self.logger.info(f"Updated complete content for node {node_id}")

            # Also update in-memory
            if hasattr(conversation.current_node, 'content'):
                conversation.current_node.content = full_content
                if response_id and hasattr(conversation.current_node, 'response_id'):
                    conversation.current_node.response_id = response_id

        except Exception as e:
            self.logger.error(f"Error ensuring complete content: {str(e)}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def _append_final_buffer(self, tab, conversation):
        """Append any remaining buffer to the node content without overwriting"""
        if not hasattr(tab, '_chunk_buffer') or not tab._chunk_buffer:
            return

        conn = None
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            node_id = conversation.current_node.id

            # Just append the remaining buffer
            cursor.execute(
                '''
                UPDATE messages SET content = content || ? WHERE id = ?
                ''',
                (tab._chunk_buffer, node_id)
            )

            # Update in-memory as well
            if hasattr(conversation.current_node, 'content'):
                conversation.current_node.content += tab._chunk_buffer

            conn.commit()
            self.logger.debug(f"Appended final buffer (size: {len(tab._chunk_buffer)})")

            # Clear the buffer
            tab._chunk_buffer = ""
            tab._chunk_counter = 0

        except Exception as e:
            self.logger.error(f"Error appending final buffer: {str(e)}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()


    def _maybe_save_conversation(self, tab, conversation, chunk):
        """Save the conversation if appropriate conditions are met"""
        try:
            # Save after a buffer flush with substantial content
            if tab._chunk_counter == 0 and len(chunk) > 50:
                self.save_conversation(conversation.id)
        except Exception as e:
            print(f"DEBUG: Error saving conversation: {str(e)}")

        # Make sure we clean up buffer on completion
        # This would typically be called from message_received signal handle

    def finalize_streaming(self, tab, full_content):
        """Finalize the streaming process, ensuring all content is saved and UI is cleaned up"""
        try:
            self.logger.info(f"Finalizing streaming with content length: {len(full_content)}")
            conversation = tab.conversation_tree

            # Get the response ID if it was stored
            response_id = getattr(tab, '_response_id', None)
            self.logger.debug(f"Response ID: {response_id}")

            # ALWAYS ensure content is updated with the full content
            # This ensures we have the complete content even if some chunks were missed
            self._ensure_complete_content(tab, conversation, full_content, response_id)

            # Ensure any remaining buffer is flushed completely
            if hasattr(tab, '_chunk_buffer') and tab._chunk_buffer:
                self.logger.debug(f"Flushing final buffer (size: {len(tab._chunk_buffer)})")
                # Just append remaining buffer to ensure we don't lose anything
                self._append_final_buffer(tab, conversation)

            # Stop loading indicator if still active
            if hasattr(tab, '_loading_active') and tab._loading_active:
                self.logger.debug("Stopping loading indicator that's still active")
                tab.stop_loading_indicator()

            # Reset streaming state flags
            self._reset_streaming_state(tab)

            # Mark streaming as complete and trigger deferred UI updates
            if hasattr(tab, 'complete_streaming_update'):
                try:
                    self.logger.debug("Calling complete_streaming_update")
                    tab.complete_streaming_update()
                except Exception as ui_error:
                    self.logger.error(f"Error updating UI in finalize_streaming: {str(ui_error)}")
                    # Try to manually correct display issues
                    try:
                        tab._is_streaming = False
                        tab.update_ui()
                    except Exception:
                        pass

            # Always save the conversation at the end
            try:
                self.logger.debug(f"Saving conversation: {conversation.id}")
                self.save_conversation(conversation.id)
            except Exception as save_error:
                self.logger.error(f"Error saving conversation in finalize_streaming: {str(save_error)}")

            # Final UI cleanup to ensure everything is visible
            try:
                if hasattr(tab, 'chat_display'):
                    cursor = tab.chat_display.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    tab.chat_display.setTextCursor(cursor)
                    tab.chat_display.ensureCursorVisible()
                    self.logger.debug("Ensured cursor visibility at end of finalization")
            except Exception as cursor_error:
                self.logger.error(f"Error setting final cursor position: {str(cursor_error)}")

        except Exception as e:
            self.logger.error(f"Critical error in finalize_streaming: {str(e)}")
            import traceback
            traceback.print_exc()

    def _emergency_content_update(self, tab, conversation, full_content, response_id=None):
        """Last resort method to update content directly in the database when other methods fail"""
        self.logger.warning("Using emergency content update method")

        if not hasattr(conversation, 'current_node') or not conversation.current_node:
            self.logger.error("No current node available for emergency update")
            return

        node_id = conversation.current_node.id

        # Direct database connection
        conn = None
        try:
            from src.models.db_manager import DatabaseManager
            db_manager = DatabaseManager()
            conn = db_manager.get_connection()
            cursor = conn.cursor()

            # Simple update query
            if response_id:
                cursor.execute(
                    'UPDATE messages SET content = ?, response_id = ? WHERE id = ?',
                    (full_content, response_id, node_id)
                )
            else:
                cursor.execute(
                    'UPDATE messages SET content = ? WHERE id = ?',
                    (full_content, node_id)
                )

            conn.commit()
            self.logger.info(f"Emergency content update successful for node {node_id}")

            # Update in-memory content if possible
            if hasattr(conversation.current_node, 'content'):
                conversation.current_node.content = full_content
                if response_id:
                    conversation.current_node.response_id = response_id

        except Exception as e:
            self.logger.error(f"Emergency database update failed: {str(e)}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()


    def _flush_final_content(self, tab, conversation, full_content, response_id=None):
        """Flush any remaining buffer and ensure content is complete"""
        conn = None
        try:
            # Log before flush for debugging
            print(f"DEBUG: Final flush - buffer size: {len(tab._chunk_buffer) if hasattr(tab, '_chunk_buffer') else 0}")
            print(f"DEBUG: Full content length: {len(full_content)}")

            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            # Set the exact full content rather than appending and include response_id if available
            if response_id:
                cursor.execute(
                    '''
                    UPDATE messages SET content = ?, response_id = ? WHERE id = ?
                    ''',
                    (full_content, response_id, conversation.current_node.id)
                )
            else:
                cursor.execute(
                    '''
                    UPDATE messages SET content = ? WHERE id = ?
                    ''',
                    (full_content, conversation.current_node.id)
                )
            conn.commit()

            # Update in-memory content
            conversation.current_node.content = full_content
            if response_id:
                conversation.current_node.response_id = response_id
            print(f"DEBUG: Updated node content length: {len(conversation.current_node.content)}")

        except Exception as e:
            print(f"Error in _flush_final_content: {str(e)}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

            # Clear buffer state regardless of success
            tab._chunk_buffer = ""
            tab._chunk_counter = 0


    def _ensure_content_consistency(self, tab, conversation, full_content):
        """Ensure the node content matches the full content, even without a buffer"""
        # Only update if content doesn't match
        if conversation.current_node.content != full_content:
            conn = None
            try:
                conn = self.db_manager.get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    '''
                    UPDATE messages SET content = ? WHERE id = ?
                    ''',
                    (full_content, conversation.current_node.id)
                )
                conn.commit()

                # Update in-memory content
                conversation.current_node.content = full_content

            except Exception as e:
                print(f"Error in _ensure_content_consistency: {str(e)}")
                if conn:
                    conn.rollback()
            finally:
                if conn:
                    conn.close()


    def _reset_streaming_state(self, tab):
        """Reset all streaming-related state variables"""
        # Clear buffer
        if hasattr(tab, '_chunk_buffer'):
            tab._chunk_buffer = ""
        if hasattr(tab, '_chunk_counter'):
            tab._chunk_counter = 0

        # Reset streaming flags
        if hasattr(tab, '_is_streaming'):
            tab._is_streaming = False
        if hasattr(tab, '_extracting_reasoning'):
            tab._extracting_reasoning = False


    def handle_usage_info(self, tab, info):
        """Handle token usage information"""
        # Get the conversation
        conversation = tab.conversation_tree

        # Update the token usage for the current node
        if conversation.current_node.role == "assistant":
            # Get a database connection to update the metadata
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            try:
                # Delete existing token usage records for this node
                cursor.execute(
                    'DELETE FROM message_metadata WHERE message_id = ? AND metadata_type LIKE ?',
                    (conversation.current_node.id, 'token_usage.%')
                )

                # Insert new token usage records
                for key, value in info.items():
                    cursor.execute(
                        '''
                        INSERT INTO message_metadata (message_id, metadata_type, metadata_value)
                        VALUES (?, ?, ?)
                        ''',
                        (conversation.current_node.id, f"token_usage.{key}", json.dumps(value))
                    )

                # Commit the changes
                conn.commit()

                # Update the in-memory object
                conversation.current_node.token_usage = info

                # Update the UI
                tab.update_ui()

                # Save the conversation
                self.save_conversation(conversation.id)

            except Exception as e:
                self.logger.error(f"Error updating token usage: {e}")
                conn.rollback()
            finally:
                conn.close()


    def handle_system_info(self, tab, info):
        """Handle system information from the API"""
        # Get the conversation
        conversation = tab.conversation_tree

        # Update the model info for the current node
        if conversation.current_node.role == "assistant":
            # Get a database connection to update the metadata
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()

            try:
                # Delete existing model info records for this node
                cursor.execute(
                    'DELETE FROM message_metadata WHERE message_id = ? AND metadata_type LIKE ?',
                    (conversation.current_node.id, 'model_info.%')
                )

                # Insert new model info records
                for key, value in info.items():
                    cursor.execute(
                        '''
                        INSERT INTO message_metadata (message_id, metadata_type, metadata_value)
                        VALUES (?, ?, ?)
                        ''',
                        (conversation.current_node.id, f"model_info.{key}", json.dumps(value))
                    )

                # Commit the changes
                conn.commit()

                # Update the in-memory object
                conversation.current_node.model_info = info

                # Update the UI
                tab.update_ui()

                # Save the conversation
                self.save_conversation(conversation.id)

            except Exception as e:
                self.logger.error(f"Error updating model info: {e}")
                conn.rollback()
            finally:
                conn.close()


    def handle_error(self, error_message):
        """Handle API errors with more context"""
        # Get the current tab to stop its loading indicator
        tab = self.tabs.currentWidget()
        if tab and hasattr(tab, 'stop_loading_indicator'):
            tab.stop_loading_indicator()

        # Add error recovery options
        error_box = QMessageBox(self)
        error_box.setIcon(QMessageBox.Critical)
        error_box.setText("API Error")
        error_box.setInformativeText(f"Error communicating with OpenAI: {error_message}")
        error_box.setDetailedText(f"Full error: {error_message}\nModel: {tab.model_label.text() if tab else 'Unknown'}")
        retry_button = error_box.addButton("Retry", QMessageBox.AcceptRole)
        error_box.addButton("Dismiss", QMessageBox.RejectRole)
        error_box.exec()

        if error_box.clickedButton() == retry_button:
            self.retry_message(tab)


    def on_branch_changed(self, tab):
        """Handle branch navigation events"""
        # Save the conversation when the branch changes
        conversation = tab.conversation_tree
        self.save_conversation(conversation.id)


    def open_settings(self):
        """Open the settings dialog"""
        dialog = SettingsDialog(self.settings, self)

        # Show warning if API key is not set
        if not self.settings.get("api_key"):
            QMessageBox.warning(
                self,
                "API Key Required",
                "No OpenAI API key detected. Please enter your API key in the settings."
            )

        if dialog.exec():
            # Update settings
            self.settings = dialog.get_settings()
            self.settings_manager.update_settings(self.settings)

            # Update model info in all open tabs
            current_model = self.settings.get("model", "")
            for i in range(self.tabs.count()):
                tab = self.tabs.widget(i)
                if hasattr(tab, 'update_model_info'):
                    tab.update_model_info(current_model)


    def save_conversation(self, conversation_id):
        """Save a specific conversation"""
        self.conversation_manager.save_conversation(conversation_id)


    def save_conversations(self):
        """Save all conversations"""
        self.conversation_manager.save_all()
        QMessageBox.information(self, "Save Complete", "All conversations have been saved.")


    def load_conversations(self):
        """Load all saved conversations"""
        # Load the conversations
        self.conversation_manager.load_all()

        # Add tabs for each conversation
        for conversation_id, conversation in self.conversation_manager.conversations.items():
            self.add_conversation_tab(conversation)
            # Ensure the tab title is set to the conversation name
            index = self.tabs.count() - 1  # Get the index of the tab we just added
            if index >= 0:
                # Make sure we're using the actual name from the database
                self.tabs.setTabText(index, conversation.name)
                print(f"DEBUG: Set tab {index} title to '{conversation.name}'")


    def show_about(self):
        """Show the 'about' dialog"""
        QMessageBox.about(
            self, "About OpenAI Chat",
            "OpenAI Chat Interface\n\n"
            "A desktop application for interacting with OpenAI's language models.\n\n"
            "Features include:\n"
            "- Multiple conversations\n"
            "- Branching conversations with retries\n"
            "- Model customization\n"
            "- Conversation saving and loading"
        )


    def _on_worker_finished(self, tab):
        """Handle worker thread completion"""
        if hasattr(tab, '_processing_message'):
            tab._processing_message = False

        if hasattr(tab, '_active_thread_id'):
            del tab._active_thread_id

        # Update UI as needed
        if hasattr(tab, 'stop_loading_indicator') and tab._loading_active:
            tab.stop_loading_indicator()

        # Add a method to handle tab closing with active threads


    def close_tab(self, index):
        """Close a conversation tab with proper thread cleanup"""
        if self.tabs.count() > 1:
            # Get the tab object
            tab = self.tabs.widget(index)
            conversation_id = tab.conversation_tree.id

            # Cancel any active API calls
            if hasattr(tab, '_active_thread_id'):
                self.thread_manager.cancel_worker(tab._active_thread_id)

            # Remove the tab
            self.tabs.removeTab(index)
            tab.deleteLater()

            # Delete the conversation
            self.conversation_manager.delete_conversation(conversation_id)
        else:
            QMessageBox.warning(
                self, "Cannot Close Tab",
                "You must have at least one conversation open."
            )

    def closeEvent(self, event):
        """Handle application close event with proper cleanup"""
        # Log start of close process
        self.logger.info("Application close initiated")

        # Cancel all active API calls
        self.thread_manager.cancel_all()
        self.logger.debug("Cancelled all active API threads")

        # Save all conversations
        try:
            self.conversation_manager.save_all()
            self.logger.info("Saved all conversations")
        except Exception as e:
            self.logger.error(f"Error saving conversations during close: {e}")

        # Ensure all file attachments are cleaned up
        try:
            for i in range(self.tabs.count()):
                tab = self.tabs.widget(i)
                if hasattr(tab, 'clear_attachments'):
                    tab.clear_attachments()
            self.logger.debug("Cleared all file attachments")
        except Exception as e:
            self.logger.error(f"Error clearing attachments during close: {e}")

        # Final garbage collection to free memory before closing
        try:
            import gc
            gc.collect()
        except Exception as e:
            self.logger.error(f"Error during final garbage collection: {e}")

        # Accept the close event
        self.logger.info("Application close completed successfully")
        event.accept()

    def _disconnect_worker_signals(self, tab):
        """Disconnect all signals from the worker to prevent conflicts"""
        if hasattr(tab, '_current_worker'):
            worker = tab._current_worker
            try:
                # Attempt to disconnect all signals
                worker.chunk_received.disconnect()
                worker.message_received.disconnect()
                worker.completion_id.disconnect()
                worker.thinking_step.disconnect()
                worker.reasoning_steps.disconnect()
                worker.error_occurred.disconnect()
                worker.usage_info.disconnect()
                worker.system_info.disconnect()
                worker.worker_finished.disconnect()
            except:
                # Ignore exceptions as some signals might not be connected
                pass


    def _create_chunk_handler(self, tab):
        """Create a handler for chunks that doesn't use lambdas"""

        def handle_chunk(chunk):
            try:
                # Log the chunk for debugging
                print(f"DEBUG: Chunk handler received: {chunk[:20]}... (length: {len(chunk)})")

                # Ensure that streaming mode is set
                if hasattr(tab, '_is_streaming'):
                    tab._is_streaming = True

                # Directly update the chat display with the chunk
                if hasattr(tab, 'update_chat_streaming'):
                    tab.update_chat_streaming(chunk)
                else:
                    print("ERROR: Tab doesn't have update_chat_streaming method")

                # Handle database updates, but NOT UI updates
                self._handle_chunk_db_only(tab, chunk)
            except Exception as e:
                print(f"Error in chunk handler: {str(e)}")
                import traceback
                traceback.print_exc()

        return handle_chunk


    def _handle_chunk_db_only(self, tab, chunk):
        """Handle database updates for a chunk without updating UI"""
        if not chunk:
            return

        try:
            # Get the conversation
            conversation = tab.conversation_tree

            # Manage the chunk buffer
            self._manage_chunk_buffer(tab, chunk)

            # Determine if database update is needed
            try:
                is_first_chunk = conversation.current_node.role != "assistant"
            except Exception as e:
                self.logger.warning(f"Error determining chunk type: {str(e)}")
                is_first_chunk = False  # Default to not first chunk in case of error

            should_flush = self._should_flush_buffer(tab, is_first_chunk)

            if should_flush:
                try:
                    self._flush_buffer_to_database(tab, conversation, is_first_chunk)
                except Exception as db_error:
                    self.logger.error(f"Database error in handle_chunk: {str(db_error)}")

            # Skip UI update - this is the key change!

            # Save conversation if needed
            try:
                self._maybe_save_conversation(tab, conversation, chunk)
            except Exception as save_error:
                self.logger.error(f"Error saving conversation: {str(save_error)}")

        except Exception as e:
            self.logger.error(f"Critical error in _handle_chunk_db_only: {str(e)}")
            import traceback
            traceback.print_exc()


    def _create_streaming_finalizer(self, tab):
        """Create a handler for streaming finalization that doesn't use lambdas"""

        def finalize_streaming(content):
            try:
                self.finalize_streaming(tab, content)
            except Exception as e:
                print(f"Error in streaming finalizer: {str(e)}")

        return finalize_streaming


    def _create_response_id_handler(self, tab):
        """Create a handler for response ID that doesn't use lambdas"""

        def handle_response_id(response_id):
            try:
                tab._response_id = response_id
            except Exception as e:
                print(f"Error in response ID handler: {str(e)}")

        return handle_response_id


    def _create_message_handler(self, tab):
        """Create a handler for messages that doesn't use lambdas"""

        def handle_message(content):
            try:
                self.handle_assistant_response(tab, content)  # THIS ONE SECOND
            except Exception as e:
                print(f"Error in message handler: {str(e)}")

        return handle_message


    def _create_completion_id_handler(self, tab):
        """Create a handler for completion IDs that doesn't use lambdas"""

        def handle_completion_id(id):
            try:
                self.handle_assistant_response(tab, tab.chat_display.toPlainText(), id, 'system')  # THIS ONE FIRST
            except Exception as e:
                print(f"Error in completion ID handler: {str(e)}")

        return handle_completion_id


    def _create_thinking_step_handler(self, tab):
        """Create a handler for thinking steps that doesn't use lambdas"""

        def handle_thinking_step(step, content):
            try:
                tab.add_cot_step(step, content)
            except Exception as e:
                print(f"Error in thinking step handler: {str(e)}")

        return handle_thinking_step


    def _create_reasoning_steps_handler(self, tab):
        """Create a handler for reasoning steps that doesn't use lambdas"""

        def handle_reasoning_steps(steps):
            try:
                tab.set_reasoning_steps(steps)
            except Exception as e:
                print(f"Error in reasoning steps handler: {str(e)}")

        return handle_reasoning_steps


    def _create_usage_info_handler(self, tab):
        """Create a handler for usage info that doesn't use lambdas"""

        def handle_usage_info(info):
            try:
                self.handle_usage_info(tab, info)
            except Exception as e:
                print(f"Error in usage info handler: {str(e)}")

        return handle_usage_info


    def _create_system_info_handler(self, tab):
        """Create a handler for system info that doesn't use lambdas"""

        def handle_system_info(info):
            try:
                self.handle_system_info(tab, info)
            except Exception as e:
                print(f"Error in system info handler: {str(e)}")

        return handle_system_info


    def _create_worker_finished_handler(self, tab):
        """Create a handler for worker finished that doesn't use lambdas"""

        def handle_worker_finished():
            try:
                self._on_worker_finished(tab)
            except Exception as e:
                print(f"Error in worker finished handler: {str(e)}")

        return handle_worker_finished
