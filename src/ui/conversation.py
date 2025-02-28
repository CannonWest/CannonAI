"""
Conversation UI components for the OpenAI Chat application.
"""

from typing import Dict, List, Optional, Any, Callable
from functools import partial

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QSplitter, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QTextCursor

from src.utils import DARK_MODE
from src.models import ConversationTree, MessageNode
from src.ui.components import ConversationTreeWidget, BranchNavBar


class ConversationBranchTab(QWidget):
    """
    Widget representing a conversation branch tab with retry functionality
    """
    send_message = pyqtSignal(str)  # Signal to send a new message
    retry_request = pyqtSignal()  # Signal to retry the current response
    branch_changed = pyqtSignal()  # Signal that the active branch has changed

    def __init__(self, conversation_tree: Optional[ConversationTree] = None, parent=None):
        super().__init__(parent)
        self.conversation_tree = conversation_tree
        self.layout = QVBoxLayout(self)

        # Branch navigation bar
        self.branch_nav = BranchNavBar()
        self.branch_nav.node_selected.connect(self.navigate_to_node)

        # Chat display area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet(
            f"background-color: {DARK_MODE['background']}; color: {DARK_MODE['foreground']};"
        )

        # Token usage display
        self.usage_container = QWidget()
        self.usage_layout = QHBoxLayout(self.usage_container)
        self.usage_layout.setContentsMargins(5, 2, 5, 2)

        self.token_label = QLabel("Tokens: 0 / 0")
        self.token_label.setStyleSheet(f"color: {DARK_MODE['accent']};")
        self.model_label = QLabel("Model: -")
        self.model_label.setStyleSheet(f"color: {DARK_MODE['accent']};")

        self.usage_layout.addWidget(self.token_label)
        self.usage_layout.addStretch()
        self.usage_layout.addWidget(self.model_label)

        # Chain of thought section (collapsible)
        self.cot_container = QWidget()
        self.cot_layout = QVBoxLayout(self.cot_container)
        self.cot_header = QWidget()
        self.cot_header_layout = QHBoxLayout(self.cot_header)
        self.cot_label = QLabel("Chain of Thought")
        self.cot_toggle = QPushButton("▼")
        self.cot_toggle.setFixedWidth(30)
        self.cot_toggle.clicked.connect(self.toggle_cot)
        self.cot_header_layout.addWidget(self.cot_label)
        self.cot_header_layout.addWidget(self.cot_toggle)

        self.cot_content = QTreeWidget()
        self.cot_content.setHeaderLabels(["Step", "Content"])
        self.cot_content.setColumnWidth(0, 150)
        self.cot_content.setVisible(False)
        self.cot_content.setStyleSheet(
            f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
        )

        self.cot_layout.addWidget(self.cot_header)
        self.cot_layout.addWidget(self.cot_content)

        # Advanced info section (collapsible)
        self.info_container = QWidget()
        self.info_layout = QVBoxLayout(self.info_container)
        self.info_header = QWidget()
        self.info_header_layout = QHBoxLayout(self.info_header)
        self.info_label = QLabel("Response Details")
        self.info_toggle = QPushButton("▼")
        self.info_toggle.setFixedWidth(30)
        self.info_toggle.clicked.connect(self.toggle_info)
        self.info_header_layout.addWidget(self.info_label)
        self.info_header_layout.addWidget(self.info_toggle)

        self.info_content = QTextEdit()
        self.info_content.setReadOnly(True)
        self.info_content.setVisible(False)
        self.info_content.setStyleSheet(
            f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
        )
        self.info_content.setFixedHeight(120)

        self.info_layout.addWidget(self.info_header)
        self.info_layout.addWidget(self.info_content)

        # Input area with retry button
        self.input_container = QWidget()
        self.input_layout = QHBoxLayout(self.input_container)
        self.input_layout.setContentsMargins(0, 0, 0, 0)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Type your message here...")
        self.text_input.setFixedHeight(70)
        self.text_input.setStyleSheet(
            f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
        )

        self.button_container = QWidget()
        self.button_layout = QVBoxLayout(self.button_container)
        self.button_layout.setContentsMargins(0, 0, 0, 0)

        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet(
            f"background-color: {DARK_MODE['accent']}; color: {DARK_MODE['foreground']};"
        )
        self.send_button.clicked.connect(self.on_send)

        self.retry_button = QPushButton("Retry")
        self.retry_button.setStyleSheet(
            f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
        )
        self.retry_button.clicked.connect(self.on_retry)

        self.button_layout.addWidget(self.send_button)
        self.button_layout.addWidget(self.retry_button)

        self.input_layout.addWidget(self.text_input, 5)
        self.input_layout.addWidget(self.button_container, 1)

        # Tree view for branch navigation
        self.tree_container = QWidget()
        self.tree_layout = QVBoxLayout(self.tree_container)
        self.tree_layout.setContentsMargins(0, 0, 0, 0)

        self.tree_label = QLabel("Conversation Branches")
        self.tree_label.setStyleSheet(f"font-weight: bold; color: {DARK_MODE['foreground']};")

        self.tree_view = ConversationTreeWidget()
        self.tree_view.node_selected.connect(self.navigate_to_node)

        self.tree_layout.addWidget(self.tree_label)
        self.tree_layout.addWidget(self.tree_view)

        # Split view for conversation and branch tree
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Main conversation container
        self.conversation_container = QWidget()
        self.conversation_layout = QVBoxLayout(self.conversation_container)

        # Add components to conversation layout
        self.conversation_layout.addWidget(self.branch_nav)
        self.conversation_layout.addWidget(self.chat_display, 4)
        self.conversation_layout.addWidget(self.usage_container, 0)
        self.conversation_layout.addWidget(self.cot_container, 1)
        self.conversation_layout.addWidget(self.info_container, 1)
        self.conversation_layout.addWidget(self.input_container, 0)

        # Add widgets to splitter
        self.splitter.addWidget(self.conversation_container)
        self.splitter.addWidget(self.tree_container)

        # Set initial sizes (75% conversation, 25% tree)
        self.splitter.setSizes([750, 250])

        # Add splitter to main layout
        self.layout.addWidget(self.splitter)

        # Update the UI with the initial conversation
        if self.conversation_tree:
            self.update_ui()

    def set_conversation_tree(self, conversation_tree: ConversationTree):
        """Set the conversation tree and update the UI"""
        self.conversation_tree = conversation_tree
        self.update_ui()

    def update_ui(self):
        """Update the UI with the current conversation state"""
        if not self.conversation_tree:
            return

        # Update branch navigation
        current_branch = self.conversation_tree.get_current_branch()
        self.branch_nav.update_branch(current_branch)

        # Update tree view
        self.tree_view.update_tree(self.conversation_tree)

        # Update chat display
        self.update_chat_display()

        # Update retry button state
        self.update_retry_button()

    def update_chat_display(self):
        """Update the chat display with the current branch messages"""
        if not self.conversation_tree:
            return

        self.chat_display.clear()

        # Get the current branch messages
        branch = self.conversation_tree.get_current_branch()

        for node in branch:
            role = node.role
            content = node.content

            if role == "system":
                color = DARK_MODE["system_message"]
                prefix = "🔧 System: "
            elif role == "user":
                color = DARK_MODE["user_message"]
                prefix = "👤 You: "
            elif role == "assistant":
                color = DARK_MODE["assistant_message"]
                prefix = "🤖 Assistant: "
            elif role == "developer":
                color = DARK_MODE["system_message"]
                prefix = "👩‍💻 Developer: "
            else:
                color = DARK_MODE["foreground"]
                prefix = f"{role}: "

            self.chat_display.setTextColor(QColor(color))
            self.chat_display.append(f"{prefix}{content}\n")

        # Scroll to bottom
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)

        # Update token usage if available
        if branch and branch[-1].role == "assistant" and branch[-1].token_usage:
            usage = branch[-1].token_usage
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

            self.token_label.setText(f"Tokens: {completion_tokens} / {total_tokens}")

            # Update model info
            if branch[-1].model_info and "model" in branch[-1].model_info:
                self.model_label.setText(f"Model: {branch[-1].model_info['model']}")
            else:
                self.model_label.setText("Model: -")

            # Update response details
            details_text = f"Token Usage:\n"
            details_text += f"  • Prompt tokens: {prompt_tokens}\n"
            details_text += f"  • Completion tokens: {completion_tokens}\n"
            details_text += f"  • Total tokens: {total_tokens}\n\n"

            # Add completion tokens details if available
            if "completion_tokens_details" in usage:
                details = usage["completion_tokens_details"]
                details_text += "Completion Token Details:\n"
                details_text += f"  • Reasoning tokens: {details.get('reasoning_tokens', 0)}\n"
                details_text += f"  • Accepted prediction tokens: {details.get('accepted_prediction_tokens', 0)}\n"
                details_text += f"  • Rejected prediction tokens: {details.get('rejected_prediction_tokens', 0)}\n\n"

            # Add model info
            if branch[-1].model_info:
                details_text += "Model Information:\n"
                for key, value in branch[-1].model_info.items():
                    details_text += f"  • {key}: {value}\n"

            self.info_content.setText(details_text)

    def update_retry_button(self):
        """Enable/disable retry button based on current node"""
        if not self.conversation_tree:
            self.retry_button.setEnabled(False)
            return

        # Enable retry if current node is an assistant message
        current_node = self.conversation_tree.current_node
        can_retry = current_node.role == "assistant" and current_node.parent and current_node.parent.role == "user"
        self.retry_button.setEnabled(can_retry)

    def navigate_to_node(self, node_id):
        """Navigate to a specific node in the conversation"""
        if not self.conversation_tree or not node_id:
            return

        if self.conversation_tree.navigate_to_node(node_id):
            self.update_ui()
            self.branch_changed.emit()

    def on_send(self):
        """Handle sending a new message"""
        if not self.conversation_tree:
            return

        message = self.text_input.toPlainText().strip()
        if not message:
            return

        self.text_input.clear()
        self.send_message.emit(message)

    def on_retry(self):
        """Handle retry button click"""
        if not self.conversation_tree:
            return

        # Check if retry is possible
        if self.conversation_tree.retry_current_response():
            self.update_ui()
            self.retry_request.emit()

    def toggle_cot(self):
        """Toggle the visibility of the chain of thought content"""
        visible = not self.cot_content.isVisible()
        self.cot_content.setVisible(visible)
        self.cot_toggle.setText("▲" if visible else "▼")

    def toggle_info(self):
        """Toggle the visibility of the response details content"""
        visible = not self.info_content.isVisible()
        self.info_content.setVisible(visible)
        self.info_toggle.setText("▲" if visible else "▼")

    def add_cot_step(self, step_name, content):
        """Add a step to the chain of thought visualization"""
        item = QTreeWidgetItem([step_name, ""])
        item.setToolTip(1, content)

        # For long content, create a truncated version
        display_content = content
        if len(content) > 100:
            display_content = content[:97] + "..."

        child = QTreeWidgetItem(["", display_content])
        item.addChild(child)
        self.cot_content.addTopLevelItem(item)
        item.setExpanded(True)

        # Auto-show the COT panel when steps are added
        self.cot_content.setVisible(True)
        self.cot_toggle.setText("▲")

    def clear_cot(self):
        """Clear the chain of thought visualization"""
        self.cot_content.clear()