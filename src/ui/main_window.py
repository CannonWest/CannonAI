"""
Main window UI for the OpenAI Chat application.
"""

from typing import Optional, Dict, Any
from functools import partial

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QMessageBox, QFileDialog, QMenu
)
from PyQt6.QtCore import Qt, QSettings, QUuid
from PyQt6.QtGui import QFont, QIcon, QColor, QPalette, QAction

from src.utils import DARK_MODE
from src.models import ConversationManager, ConversationTree, MessageNode
from src.services import OpenAIChatWorker, SettingsManager
from src.ui.conversation import ConversationBranchTab
from src.ui.components import SettingsDialog, SearchDialog


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenAI Chat Interface")
        self.setMinimumSize(900, 700)

        # Initialize settings and conversation managers
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.get_settings()

        self.conversation_manager = ConversationManager()

        # Initialize UI components
        self.setup_ui()

        # Set up styling
        self.setup_style()

        # Load saved conversations
        self.load_conversations()

        # Create a default conversation if none exists
        if not self.conversation_manager.active_conversation:
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

    #########NEW CODE###########
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
                child = MessageNode(
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

            # Save the conversation
            self.save_conversation(conversation.id)


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

        # Add the tab
        index = self.tabs.addTab(tab, conversation.name)
        self.tabs.setCurrentIndex(index)

    def close_tab(self, index):
        """Close a conversation tab"""
        if self.tabs.count() > 1:
            # Get the conversation ID for this tab
            tab = self.tabs.widget(index)
            conversation_id = tab.conversation_tree.id

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

    def send_message(self, tab, message):
        """Send a user message and get a response"""
        # Get the active conversation
        conversation = tab.conversation_tree

        # Check if there are file attachments to include
        attached_files = getattr(tab, '_pending_attachments', None)

        # Add the user message
        conversation.add_user_message(message, attached_files=attached_files)

        # Update the UI
        tab.update_ui()

        # Create and start the worker thread to get the response
        self.worker = OpenAIChatWorker(conversation.get_current_messages(), self.settings)

        # Clear any existing chain of thought steps
        tab.clear_cot()

        # Connect signals
        if self.settings.get("stream", True):
            # For streaming mode, only handle chunks
            self.worker.chunk_received.connect(lambda chunk: self.handle_chunk(tab, chunk))
            self.worker.message_received.connect(lambda content: None)  # Ignore full message to avoid duplication
        else:
            # For non-streaming mode, handle the complete message
            self.worker.message_received.connect(lambda content: self.handle_assistant_response(tab, content))

        # Connect other signals
        self.worker.thinking_step.connect(lambda step, content: tab.add_cot_step(step, content))
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.usage_info.connect(lambda info: self.handle_usage_info(tab, info))
        self.worker.system_info.connect(lambda info: self.handle_system_info(tab, info))

        # Start the worker
        self.worker.start()

    def retry_message(self, tab):
        """Retry the current message with possibly different settings"""
        # Get the conversation
        conversation = tab.conversation_tree

        # Verify the current node is a user message (parent of assistant message)
        if conversation.current_node.role != "user":
            return

        # Clear any existing chain of thought steps
        tab.clear_cot()

        # Create and start the worker thread to get the response
        self.worker = OpenAIChatWorker(conversation.get_current_messages(), self.settings)

        # Connect signals
        if self.settings.get("stream", True):
            # For streaming mode, only handle chunks
            self.worker.chunk_received.connect(lambda chunk: self.handle_chunk(tab, chunk))
            self.worker.message_received.connect(lambda content: None)  # Ignore full message to avoid duplication
        else:
            # For non-streaming mode, handle the complete message
            self.worker.message_received.connect(lambda content: self.handle_assistant_response(tab, content))

        # Connect other signals
        self.worker.thinking_step.connect(lambda step, content: tab.add_cot_step(step, content))
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.usage_info.connect(lambda info: self.handle_usage_info(tab, info))
        self.worker.system_info.connect(lambda info: self.handle_system_info(tab, info))

        # Start the worker
        self.worker.start()

    def handle_assistant_response(self, tab, content):
        """Handle the complete response from the assistant"""
        if not content:
            return

        # Get the conversation
        conversation = tab.conversation_tree

        # Add the assistant response
        conversation.add_assistant_response(content)

        # Update the UI
        tab.update_ui()

        # Save the conversation
        self.save_conversation(conversation.id)

    def handle_chunk(self, tab, chunk):
        """Handle a streaming chunk from the API"""
        if not chunk:
            return

        # Get the conversation
        conversation = tab.conversation_tree

        # Check if we already have an assistant node
        if conversation.current_node.role == "assistant":
            # Update the existing node
            conversation.current_node.content += chunk
        else:
            # Create a new assistant node
            conversation.add_assistant_response(chunk)

        # Update the UI
        tab.update_ui()

        # Save the conversation periodically (can optimize to save less frequently)
        self.save_conversation(conversation.id)

    def handle_usage_info(self, tab, info):
        """Handle token usage information"""
        # Get the conversation
        conversation = tab.conversation_tree

        # Update the token usage for the current node
        if conversation.current_node.role == "assistant":
            conversation.current_node.token_usage = info

            # Update the UI
            tab.update_ui()

    def handle_system_info(self, tab, info):
        """Handle system information from the API"""
        # Get the conversation
        conversation = tab.conversation_tree

        # Update the model info for the current node
        if conversation.current_node.role == "assistant":
            conversation.current_node.model_info = info

            # Update the UI
            tab.update_ui()

    def handle_error(self, error_message):
        """Handle API errors"""
        QMessageBox.critical(self, "API Error", f"Error communicating with OpenAI: {error_message}")

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

    def rename_current_conversation(self):
        """Rename the current conversation"""
        # Get the current tab
        index = self.tabs.currentIndex()
        if index < 0:
            return

        self.rename_conversation_at_index(index)

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

    def show_about(self):
        """Show the about dialog"""
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

    def closeEvent(self, event):
        """Handle application close event"""
        # Save all conversations
        self.conversation_manager.save_all()

        # Accept the close event
        event.accept()
