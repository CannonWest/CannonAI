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
        self.chat_display.setAcceptRichText(True)
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

        self.cot_container = QWidget()
        self.cot_layout = QVBoxLayout(self.cot_container)
        self.cot_header = QWidget()
        self.cot_header_layout = QHBoxLayout(self.cot_header)
        self.cot_label = QLabel("Chain of Thought")
        self.show_in_chat_btn = QPushButton("Show in Chat")
        self.show_in_chat_btn.setCheckable(True)
        self.show_in_chat_btn.setChecked(True)  # Default to showing reasoning in chat
        self.show_in_chat_btn.clicked.connect(self.update_ui)
        self.cot_toggle = QPushButton("▼")
        self.cot_toggle.setFixedWidth(30)
        self.cot_toggle.clicked.connect(self.toggle_cot)
        self.cot_header_layout.addWidget(self.cot_label)
        self.cot_header_layout.addWidget(self.show_in_chat_btn)
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
        input_price = pricing_info.get("input", 0)
        output_price = pricing_info.get("output", 0)

        # Update labels
        self.model_name_label.setText(f"Model: {model_id}")
        self.model_pricing_label.setText(f"Pricing: ${input_price:.2f}/1M in, ${output_price:.2f}/1M out")
        self.model_token_limit_label.setText(f"Limits: {context_size:,} ctx, {output_limit:,} out")

    def update_chat_display(self):
        """Update the chat display with the current branch messages"""
        if not self.conversation_tree:
            return

        self.chat_display.clear()
        show_reasoning_in_chat = self.show_in_chat_btn.isChecked()

        # Get the current branch messages
        branch = self.conversation_tree.get_current_branch()
        current_node = self.conversation_tree.current_node

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
                # Add model info to the prefix if available
                if node.model_info and "model" in node.model_info:
                    prefix = f"🤖 Assistant ({node.model_info['model']}): "

                # Extract and display reasoning steps if enabled
                if show_reasoning_in_chat:
                    reasoning_steps = self._extract_reasoning_steps(content)
                    if reasoning_steps:
                        self.chat_display.setTextColor(QColor(DARK_MODE["accent"]))
                        self.chat_display.insertPlainText("💭 Reasoning:\n")

                        for step in reasoning_steps:
                            # Format and display the step
                            self.chat_display.insertPlainText(f"{step['name']}: {step['content']}\n")

                        self.chat_display.insertPlainText("\n")  # Add spacing

                        # Remove reasoning from content for cleaner display
                        content = self._remove_reasoning_steps(content, reasoning_steps)
            elif role == "developer":
                color = DARK_MODE["system_message"]
                prefix = "👩‍💻 Developer: "
            else:
                color = DARK_MODE["foreground"]
                prefix = f"{role}: "

            # Process markdown in content
            formatted_content = self.process_markdown(content)

            # Set text color for the prefix
            self.chat_display.setTextColor(QColor(color))

            # Insert prefix as plain text
            self.chat_display.insertPlainText(prefix)

            # Insert the formatted content as HTML
            cursor = self.chat_display.textCursor()
            cursor.insertHtml(formatted_content)
            cursor.insertBlock()  # Add a newline

            # Add file attachment indicators if present
            if hasattr(node, 'attached_files') and node.attached_files:
                self.chat_display.setTextColor(QColor(DARK_MODE["accent"]))
                file_count = len(node.attached_files)

                # Summary line for the attachments
                attachment_summary = f"📎 {file_count} file{'s' if file_count > 1 else ''} attached:"
                self.chat_display.append(attachment_summary)

                # Create a formatted list of files with more details
                for file_info in node.attached_files:
                    file_name = file_info['file_name']
                    file_type = file_info.get('mime_type', 'Unknown type')
                    file_size = file_info.get('size', 0)
                    token_count = file_info.get('token_count', 0)

                    # Format file size for display
                    if hasattr(self, 'format_size'):
                        size_str = self.format_size(file_size)
                    else:
                        # Simple format if the format_size method is not available
                        size_str = f"{file_size} bytes"

                    file_details = f"    • {file_name} ({size_str}, {token_count} tokens)"
                    self.chat_display.append(file_details)

                self.chat_display.append("")  # Add an empty line after attachments

        # Scroll to bottom
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)

        # Update token usage and model info based on the current node
        if current_node.role == "assistant":
            if current_node.token_usage:
                usage = current_node.token_usage
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)

                # For debugging
                print(f"Assistant node token usage: {usage}")

                self.token_label.setText(f"Tokens: {completion_tokens} / {total_tokens}")
            else:
                # No token usage data available
                self.token_label.setText("Tokens: - / -")
                print(f"No token usage for assistant node ID: {current_node.id}")

            # Update model info
            if current_node.model_info and "model" in current_node.model_info:
                model_name = current_node.model_info["model"]
                self.model_label.setText(f"Model: {model_name}")
                print(f"Model info: {current_node.model_info}")
            else:
                self.model_label.setText("Model: -")
                print(f"No model info for assistant node ID: {current_node.id}")

        elif current_node.role == "user":
            # For user messages, estimate token count from content and attachments
            token_estimate = 0

            # Approximate tokens as words/0.75 for English text (rough approximation)
            if current_node.content:
                token_estimate += len(current_node.content.split())

            # Add tokens from attachments if present
            if hasattr(current_node, 'attached_files') and current_node.attached_files:
                for file_info in current_node.attached_files:
                    token_estimate += file_info.get('token_count', 0)

            self.token_label.setText(f"Tokens: {token_estimate} / -")
            self.model_label.setText("Model: -")  # No model for user messages
        else:
            # For system or other messages
            self.token_label.setText("Tokens: - / -")
            self.model_label.setText("Model: -")

        # Update response details
        if current_node.role == "assistant" and current_node.token_usage:
            usage = current_node.token_usage
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

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
            if current_node.model_info:
                details_text += "Model Information:\n"
                for key, value in current_node.model_info.items():
                    details_text += f"  • {key}: {value}\n"

            self.info_content.setText(details_text)
        else:
            self.info_content.setText("")

    def update_retry_button(self):
        """Enable/disable retry button based on current node"""
        if not self.conversation_tree:
            self.retry_button.setEnabled(False)
            return

        # Enable retry if current node is an assistant message
        current_node = self.conversation_tree.current_node
        can_retry = current_node.role == "assistant" and current_node.parent and current_node.parent.role == "user"
        self.retry_button.setEnabled(can_retry)

    def update_chat_streaming(self, chunk):
        """Update the chat display during streaming for efficiency"""
        # Just append the chunk to the end of the display
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.insertPlainText(chunk)
        self.chat_display.ensureCursorVisible()

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

        # Prepare attachments if present but don't add them directly to the message text
        attachments_copy = None
        if self.current_attachments:
            # Just note that there are attachments in the UI message
            if message:
                # We no longer append file info to the message text
                # The API service will handle the file content formatting
                attachment_count = len(self.current_attachments)
                file_text = f"\n\n[{attachment_count} file{'s' if attachment_count > 1 else ''} attached]"
                message += file_text
            else:
                message = f"[Attached {len(self.current_attachments)} file{'s' if len(self.current_attachments) > 1 else ''}]"

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

            # Ensure the full path is stored
            file_info["path"] = file_path

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

    def format_size(self, size_bytes):
        """Format file size in a human-readable way."""
        from src.utils.file_utils import format_size as utils_format_size
        return utils_format_size(size_bytes)

    def process_markdown(self, text):
        """Convert markdown syntax to HTML for display"""
        import re

        # Process code blocks with syntax highlighting
        text = re.sub(r'```(\w+)?\n(.*?)\n```', self._format_code_block, text, flags=re.DOTALL)

        # Process inline code
        text = re.sub(r'`([^`]+)`', r'<code style="background-color:#2d2d2d; padding:2px 4px; border-radius:3px;">\1</code>', text)

        # Process bold text
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__([^_]+)__', r'<b>\1</b>', text)

        # Process italic text
        text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)
        text = re.sub(r'_([^_]+)_', r'<i>\1</i>', text)

        # Process headers
        text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)

        # Process bullet lists
        text = re.sub(r'^- (.+)$', r'• \1<br>', text, flags=re.MULTILINE)
        text = re.sub(r'^\* (.+)$', r'• \1<br>', text, flags=re.MULTILINE)

        # Process numbered lists
        text = re.sub(r'^(\d+)\. (.+)$', r'\1. \2<br>', text, flags=re.MULTILINE)

        # Replace newlines with <br> tags
        text = text.replace('\n', '<br>')

        return text

    def _format_code_block(self, match):
        """Format code blocks with syntax highlighting"""
        language = match.group(1) or ""
        code = match.group(2)

        # Simple syntax highlighting could be implemented here
        # For now, we'll just wrap it in a pre tag with styling
        return f'<pre style="background-color:#2d2d2d; color:#f8f8f2; padding:10px; border-radius:5px; overflow:auto;">{code}</pre>'

    def _extract_reasoning_steps(self, content):
        """Extract reasoning steps from message content"""
        import re

        # Patterns to identify reasoning steps
        patterns = [
            (r"Step (\d+):(.*?)(?=Step \d+:|$)", "Step {}"),
            (r"Let's think step by step:(.*?)(?=Therefore|So the answer|In conclusion|$)", "Reasoning"),
            (r"I'll solve this step by step:(.*?)(?=Therefore|So the answer|In conclusion|$)", "Problem Solving"),
            (r"Let me think through this:(.*?)(?=Therefore|So the answer|In conclusion|$)", "Analysis"),
            (r"First, (.*?)(?=Next,|Then,|Finally,|Therefore|So the answer|In conclusion|$)", "Step 1")
        ]

        steps = []
        for pattern, name_template in patterns:
            matches = re.finditer(pattern, content, re.DOTALL)
            for i, match in enumerate(matches):
                if len(match.groups()) > 1:
                    step_num = match.group(1)
                    step_content = match.group(2).strip()
                    step_name = name_template.format(step_num)
                else:
                    step_content = match.group(1).strip()
                    step_name = name_template.format(i + 1)

                if step_content:
                    steps.append({
                        "name": step_name,
                        "content": step_content,
                        "match": match.group(0)
                    })

        return steps

    def _remove_reasoning_steps(self, content, steps):
        """Remove reasoning steps from content for cleaner display"""
        cleaned_content = content
        for step in steps:
            if "match" in step:
                cleaned_content = cleaned_content.replace(step["match"], "")

        # Clean up any double newlines
        import re
        cleaned_content = re.sub(r'\n\s*\n', '\n\n', cleaned_content)
        return cleaned_content.strip()
