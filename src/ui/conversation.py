"""
Conversation UI components for the OpenAI Chat application.
"""

from typing import Dict, List, Optional, Any, Callable
from functools import partial

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QSplitter, QMessageBox, QDialogButtonBox, QFileDialog, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QTextCursor, QDragEnterEvent, QDropEvent

from src.utils import DARK_MODE, MODEL_CONTEXT_SIZES, MODEL_OUTPUT_LIMITS, MODEL_PRICING
from src.models import DBConversationTree, DBMessageNode
from src.ui.components import ConversationTreeWidget, BranchNavBar
from src.utils.file_utils import get_file_info, format_size


class ConversationBranchTab(QWidget):
    """
    Widget representing a conversation branch tab with retry functionality
    """
    send_message = pyqtSignal(str)  # Signal to send a new message
    retry_request = pyqtSignal()  # Signal to retry the current response
    branch_changed = pyqtSignal()  # Signal that the active branch has changed
    file_attached = pyqtSignal(str)  # Signal emitted when a file is attached

    def __init__(self, conversation_tree: Optional[DBConversationTree] = None, parent=None):
        super().__init__(parent)
        self.conversation_tree = conversation_tree
        self.layout = QVBoxLayout(self)

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Initialize empty attachments list
        self.current_attachments = []

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

        # Model information display
        self.model_info_container = QWidget()
        self.model_info_layout = QHBoxLayout(self.model_info_container)
        self.model_info_layout.setContentsMargins(5, 2, 5, 2)

        self.model_name_label = QLabel("Model: -")
        self.model_name_label.setStyleSheet(f"color: {DARK_MODE['accent']};")

        self.model_pricing_label = QLabel("Pricing: -")
        self.model_pricing_label.setStyleSheet(f"color: {DARK_MODE['accent']};")

        self.model_token_limit_label = QLabel("Limits: -")
        self.model_token_limit_label.setStyleSheet(f"color: {DARK_MODE['accent']};")

        self.model_info_layout.addWidget(self.model_name_label)
        self.model_info_layout.addStretch()
        self.model_info_layout.addWidget(self.model_pricing_label)
        self.model_info_layout.addStretch()
        self.model_info_layout.addWidget(self.model_token_limit_label)

        # File attachments display area
        self.attachments_container = QWidget()
        self.attachments_layout = QHBoxLayout(self.attachments_container)
        self.attachments_layout.setContentsMargins(5, 2, 5, 2)
        self.attachments_container.setVisible(False)  # Hidden by default

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

        self.attach_button = QPushButton("📎")
        self.attach_button.setToolTip("Attach file")
        self.attach_button.setStyleSheet(
            f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
        )
        self.attach_button.clicked.connect(self.on_attach_file)

        self.button_layout.addWidget(self.send_button)
        self.button_layout.addWidget(self.retry_button)
        self.button_layout.addWidget(self.attach_button)

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

        self.conversation_layout.addWidget(self.branch_nav)
        self.conversation_layout.addWidget(self.chat_display, 4)
        self.conversation_layout.addWidget(self.usage_container, 0)
        self.conversation_layout.addWidget(self.cot_container, 1)
        self.conversation_layout.addWidget(self.info_container, 1)
        self.conversation_layout.addWidget(self.attachments_container, 0)
        self.conversation_layout.addWidget(self.input_container, 0)
        self.conversation_layout.addWidget(self.model_info_container, 0)  # Add model info container

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

    def set_conversation_tree(self, conversation_tree: DBConversationTree):
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

    def update_model_info(self, model_id):
        """Update the model information display with the current model details"""
        if not model_id:
            # Reset labels if no model is specified
            self.model_name_label.setText("Model: -")
            self.model_pricing_label.setText("Pricing: -")
            self.model_token_limit_label.setText("Limits: -")
            return

        # Get model information
        context_size = MODEL_CONTEXT_SIZES.get(model_id, 0)
        output_limit = MODEL_OUTPUT_LIMITS.get(model_id, 0)

        # Get pricing information (display per 1K tokens)
        pricing_info = MODEL_PRICING.get(model_id, {"input": 0, "output": 0})
        input_price = pricing_info.get("input", 0) / 1000  # Convert from per 1M to per 1K
        output_price = pricing_info.get("output", 0) / 1000  # Convert from per 1M to per 1K

        # Update labels
        self.model_name_label.setText(f"Model: {model_id}")
        self.model_pricing_label.setText(f"Pricing: ${input_price:.4f}/1K in, ${output_price:.4f}/1K out")
        self.model_token_limit_label.setText(f"Limits: {context_size:,} ctx, {output_limit:,} out")


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

            # Add file attachment indicators if present
            if hasattr(node, 'attached_files') and node.attached_files:
                self.chat_display.setTextColor(QColor(DARK_MODE["accent"]))
                for file_info in node.attached_files:
                    file_text = f"📎 Attached: {file_info['file_name']} ({file_info['token_count']} tokens)"
                    self.chat_display.append(file_text)
                self.chat_display.append("")  # Add an empty line after attachments

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

        # Add file attachment references to the message if present
        attachments_copy = None
        if self.current_attachments:
            files_text = "\n\nAttached files:\n"
            for file_info in self.current_attachments:
                files_text += f"- {file_info['file_name']} ({file_info['token_count']} tokens)\n"

            if message:
                message += files_text
            else:
                message = files_text.strip()

            # Copy attachments before clearing
            attachments_copy = self.current_attachments.copy()

        if not message:
            return

        self.text_input.clear()

        # Store attachments for use in the main window's send_message method
        self._pending_attachments = attachments_copy

        self.send_message.emit(message)

        # Clear attachments after sending
        self.clear_attachments()

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

    # Drag and drop event handlers
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events for file drops"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragOverEvent(self, event):
        """Handle drag over events"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Handle file drop events"""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            self.add_attachment(file_path)
        event.acceptProposedAction()

    def on_attach_file(self):
        """Open file dialog to attach files"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Attach Files",
            "",
            "Text Files (*.txt *.py *.js *.c *.cpp *.h *.json *.md);;All Files (*)"
        )

        for file_path in file_paths:
            self.add_attachment(file_path)

    def add_attachment(self, file_path: str):
        """Add a file attachment to the current message"""
        try:
            # Use the current model from settings to count tokens accurately
            from src.services.storage import SettingsManager
            settings = SettingsManager().get_settings()
            model = settings.get("model", "gpt-4o")

            file_info = get_file_info(file_path, model)

            # Check if file is already attached
            for attachment in self.current_attachments:
                if attachment["file_name"] == file_info["file_name"]:
                    return  # Skip if already attached

            # Add to current attachments
            self.current_attachments.append(file_info)

            # Update UI
            self.update_attachments_ui()

            # Emit signal
            self.file_attached.emit(file_path)

        except Exception as e:
            QMessageBox.warning(
                self,
                "Attachment Error",
                f"Error attaching file: {str(e)}"
            )

    def update_attachments_ui(self):
        """Update the attachments UI with current files"""
        # Clear current widgets
        while self.attachments_layout.count():
            item = self.attachments_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.current_attachments:
            self.attachments_container.setVisible(False)
            return

        self.attachments_container.setVisible(True)

        # Add label
        label = QLabel("Attached Files:")
        label.setStyleSheet(f"color: {DARK_MODE['foreground']};")
        self.attachments_layout.addWidget(label)

        # Add file buttons
        for file_info in self.current_attachments:
            file_button = QPushButton(f"{file_info['file_name']} ({file_info['token_count']} tokens)")
            file_button.setStyleSheet(
                f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
            )
            file_button.setToolTip(f"Click to preview: {file_info['file_name']}")

            # Use lambda with default argument to capture the current file_info
            file_button.clicked.connect(lambda checked=False, fi=file_info: self.preview_file(fi))

            # Add delete button
            delete_button = QPushButton("×")
            delete_button.setFixedSize(20, 20)
            delete_button.setToolTip(f"Remove {file_info['file_name']}")
            delete_button.setStyleSheet(
                f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
            )

            # Use lambda with default argument
            delete_button.clicked.connect(lambda checked=False, fi=file_info: self.remove_attachment(fi))

            self.attachments_layout.addWidget(file_button)
            self.attachments_layout.addWidget(delete_button)

        # Add stretch to push everything to the left
        self.attachments_layout.addStretch()

    def preview_file(self, file_info):
        """Show a preview dialog for the file"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"File Preview: {file_info['file_name']}")
        dialog.setMinimumSize(700, 500)

        layout = QVBoxLayout(dialog)

        # File info label
        info_label = QLabel(
            f"File: {file_info['file_name']}\n"
            f"Size: {format_size(file_info['size'])}\n"
            f"Token count: {file_info['token_count']} tokens"
        )
        layout.addWidget(info_label)

        # Content display
        content_display = QTextEdit()
        content_display.setReadOnly(True)
        content_display.setPlainText(file_info["content"])
        content_display.setStyleSheet(
            f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
        )
        layout.addWidget(content_display)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.setStyleSheet(f"background-color: {DARK_MODE['background']}; color: {DARK_MODE['foreground']};")
        dialog.exec()

    def remove_attachment(self, file_info):
        """Remove a file attachment"""
        self.current_attachments = [
            attachment for attachment in self.current_attachments
            if attachment["file_name"] != file_info["file_name"]
        ]
        self.update_attachments_ui()

    def clear_attachments(self):
        """Clear all attachments"""
        self.current_attachments = []
        self.update_attachments_ui()
