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

        # Initialize state variables to prevent NoneType errors
        self._is_streaming = False
        self._chunk_counter = 0
        self._extracting_reasoning = False

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Initialize empty attachments list
        self.current_attachments = []

        # NEW: Store reasoning steps
        self.reasoning_steps = []

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

        self.attach_dir_button = QPushButton("📁")
        self.attach_dir_button.setToolTip("Attach directory")
        self.attach_dir_button.setStyleSheet(
            f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
        )
        self.attach_dir_button.clicked.connect(self.on_attach_directory)

        self.button_layout.addWidget(self.send_button)
        self.button_layout.addWidget(self.retry_button)
        self.button_layout.addWidget(self.attach_button)
        self.button_layout.addWidget(self.attach_dir_button)

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

        # Add flag to check if we're in streaming mode to avoid expensive operations
        is_streaming = hasattr(self, '_is_streaming') and self._is_streaming

        self.chat_display.clear()

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

                # Check for reasoning tokens or reasoning steps
                reasoning_tokens = 0
                if node.token_usage and "completion_tokens_details" in node.token_usage:
                    details = node.token_usage["completion_tokens_details"]
                    reasoning_tokens = details.get("reasoning_tokens", 0)

                # Get any stored reasoning steps for this node
                node_reasoning = getattr(node, 'reasoning_steps', [])

                # If we have stored reasoning steps or the model used reasoning tokens
                if node_reasoning or reasoning_tokens > 0:
                    self.chat_display.setTextColor(QColor(DARK_MODE["accent"]))
                    self.chat_display.insertPlainText("💭 Chain of Thought:\n")

                    print(f"DEBUG: node_reasoning={node_reasoning}, reasoning_tokens={reasoning_tokens}")

                    # First, try to use stored reasoning steps
                    if node_reasoning and isinstance(node_reasoning, list) and len(node_reasoning) > 0:
                        print(f"DEBUG: Using stored reasoning steps: {len(node_reasoning)}")
                        # Display the stored reasoning steps
                        for step in node_reasoning:
                            step_name = step.get("name", "Reasoning Step")
                            step_content = step.get("content", "")
                            self.chat_display.insertPlainText(f"• {step_name}: {step_content}\n")

                    # For o1/o3 models, attempt pattern extraction in non-streaming mode
                    elif "o1" in node.model_info.get("model", "") or "o3" in node.model_info.get("model", ""):
                        # Don't try to extract if we're still streaming
                        if getattr(self, '_is_streaming', False):
                            self.chat_display.insertPlainText(f"• Reasoning in progress (streaming)...\n")
                        else:
                            # When the full response is available, try to extract patterns
                            try:
                                # Skip recursion check for final extraction
                                if getattr(self, '_extracting_reasoning', False):
                                    self.chat_display.insertPlainText(f"• Extraction already in progress\n")
                                else:
                                    self._extracting_reasoning = True
                                    detected_steps = self._extract_reasoning_steps(content)
                                    self._extracting_reasoning = False

                                    if detected_steps and len(detected_steps) > 0:
                                        print(f"DEBUG: Found {len(detected_steps)} reasoning steps via extraction")
                                        for step in detected_steps:
                                            self.chat_display.insertPlainText(f"• {step['name']}: {step['content']}\n")

                                            # Save the extracted steps to the node for future use
                                            if not node_reasoning:
                                                setattr(node, 'reasoning_steps', detected_steps)
                                    else:
                                        # Just show token count if no steps found
                                        self.chat_display.insertPlainText(f"• Model performed reasoning ({reasoning_tokens} tokens)\n")
                            except Exception as e:
                                print(f"Error extracting reasoning steps: {str(e)}")
                                self.chat_display.insertPlainText(f"• Error displaying reasoning steps\n")
                    # Generic case - just mention reasoning token count
                    else:
                        self.chat_display.insertPlainText(f"• Model performed reasoning ({reasoning_tokens} tokens)\n")

                self.chat_display.insertPlainText("\n")  # Add spacing
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

                # Show reasoning tokens if available
                reasoning_tokens = 0
                if "completion_tokens_details" in usage:
                    details = usage["completion_tokens_details"]
                    reasoning_tokens = details.get("reasoning_tokens", 0)
                    if reasoning_tokens > 0:
                        self.token_label.setText(f"Tokens: {completion_tokens} / {total_tokens} ({reasoning_tokens} reasoning)")
                    else:
                        self.token_label.setText(f"Tokens: {completion_tokens} / {total_tokens}")
                else:
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
        try:
            # Initialize variables - must happen at the start
            # Mark that we're in streaming mode
            self._is_streaming = True

            # Initialize counter if it doesn't exist or is None
            if not hasattr(self, '_chunk_counter') or self._chunk_counter is None:
                self._chunk_counter = 0

            # Just append the chunk to the end of the display
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.chat_display.setTextCursor(cursor)

            # Insert the chunk
            self.chat_display.insertPlainText(chunk)
            self.chat_display.ensureCursorVisible()

            # Inrement counter safely
            try:
                self._chunk_counter += 1
            except TypeError:
                # Reset counter if it's somehow None
                self._chunk_counter = 1

            # Process events less frequently
            if self._chunk_counter % 20 == 0:
                from PyQt6.QtCore import QCoreApplication
                QCoreApplication.processEvents()
        except Exception as e:
            print(f"Error in update_chat_streaming: {str(e)}")

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
        """Add a step to the chain of thought"""
        try:
            # Add to our current reasoning steps
            if not hasattr(self, 'reasoning_steps') or self.reasoning_steps is None:
                self.reasoning_steps = []

            self.reasoning_steps.append({
                "name": step_name,
                "content": content
            })

            # Store the steps with the node but don't update UI during streaming
            if self.conversation_tree and self.conversation_tree.current_node:
                node = self.conversation_tree.current_node
                if node.role == "assistant":
                    # Store the steps
                    setattr(node, 'reasoning_steps', self.reasoning_steps)

                    # Just log the step - no UI update during streaming
                    print(f"Added CoT step: {step_name}")

                    # Skip UI update completely during streaming
                    if getattr(self, '_is_streaming', False):
                        return

        except Exception as e:
            print(f"Error in add_cot_step: {str(e)}")

    def clear_cot(self):
        """Clear the chain of thought steps"""
        self.reasoning_steps = []

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
        import os

        for url in event.mimeData().urls():
            file_path = url.toLocalFile()

            # Check if it's a directory
            if os.path.isdir(file_path):
                # Process directory recursively, similar to on_attach_directory
                for root, dirs, files in os.walk(file_path):
                    for file in files:
                        # Build the full file path
                        individual_file_path = os.path.join(root, file)

                        # Get the relative path from the dropped directory
                        relative_path = os.path.relpath(individual_file_path, file_path)

                        try:
                            # Add each file with its relative path
                            self.add_attachment(individual_file_path, relative_path)
                        except Exception as e:
                            print(f"Error attaching file {relative_path}: {str(e)}")
            else:
                # It's a regular file, handle normally
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

    def add_attachment(self, file_path: str, relative_path: str = None):
        """Add a file attachment to the current message"""
        try:
            # Use the current model from settings to count tokens accurately
            from src.services.storage import SettingsManager
            settings = SettingsManager().get_settings()
            model = settings.get("model", "gpt-4o")

            file_info = get_file_info(file_path, model)

            # Ensure the full path is stored
            file_info["path"] = file_path

            # If a relative path is provided, use it for display
            if relative_path:
                # Store original file name
                file_info["original_file_name"] = file_info["file_name"]
                # Use relative path for display
                file_info["file_name"] = relative_path

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

    def on_attach_directory(self):
        """Open directory dialog to attach all files in a directory"""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import os

        directory_path = QFileDialog.getExistingDirectory(
            self,
            "Select Directory to Attach",
            "",
            QFileDialog.Option.ShowDirsOnly
        )

        if not directory_path:
            return

        # Confirm with user if directory might contain many files
        file_count = sum([len(files) for _, _, files in os.walk(directory_path)])

        if file_count > 10:
            reply = QMessageBox.question(
                self,
                "Confirm Directory Attachment",
                f"The selected directory contains {file_count} files. Are you sure you want to attach all of them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        # Process the directory
        attached_count = 0
        error_count = 0

        # Walk through the directory recursively
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                # Build the full file path
                file_path = os.path.join(root, file)

                # Get the relative path from the selected directory
                relative_path = os.path.relpath(file_path, directory_path)

                try:
                    # Add the file with its relative path
                    self.add_attachment(file_path, relative_path)
                    attached_count += 1
                except Exception as e:
                    error_count += 1
                    print(f"Error attaching file {relative_path}: {str(e)}")

        # Show summary message
        if attached_count > 0:
            summary = f"Attached {attached_count} files from directory"
            if error_count > 0:
                summary += f" ({error_count} files skipped due to errors)"
            QMessageBox.information(self, "Directory Attachment", summary)
        elif error_count > 0:
            QMessageBox.warning(self, "Attachment Error", f"Could not attach any files. {error_count} files had errors.")

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
        display_name = file_info['file_name']
        original_name = file_info.get('original_file_name', display_name.split('/')[-1])
        full_path = file_info['path']

        info_label = QLabel(
            f"File: {display_name}\n"
            f"Original name: {original_name}\n"
            f"Path: {full_path}\n"
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

    def debug_streaming_test(self, chunk):
        """Test method to debug streaming issues"""
        # Get current text
        current_text = self.chat_display.toPlainText()

        # Find the last assistant message
        last_assistant_idx = current_text.rfind("🤖 Assistant")

        if last_assistant_idx >= 0:
            # Replace everything after the assistant prefix with updated content
            prefix_text = current_text[:last_assistant_idx + len("🤖 Assistant (gpt-4o-mini-2024-07-18): ")]
            assistant_content = self.conversation_tree.current_node.content

            # Set the complete text
            self.chat_display.setPlainText(prefix_text + assistant_content)

            # Move cursor to end
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.chat_display.setTextCursor(cursor)

        # Process events to update UI
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

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

    def set_reasoning_steps(self, steps):
        """Store reasoning steps for the current response"""
        try:
            # Ensure steps is a valid list
            if steps is None:
                steps = []

            print(f"Received {len(steps)} reasoning steps from worker")

            # Store the complete set of steps
            self.reasoning_steps = steps

            # If we have a current node that's an assistant, store the steps with it
            if self.conversation_tree and self.conversation_tree.current_node:
                node = self.conversation_tree.current_node
                if node.role == "assistant":
                    print(f"DEBUG: Storing {len(steps)} reasoning steps with node {node.id}")

                    try:
                        # Store the reasoning steps with the node
                        setattr(node, 'reasoning_steps', steps)
                    except Exception as e:
                        print(f"ERROR setting reasoning_steps on node: {str(e)}")

                    # Reset all state flags - VERY IMPORTANT for stability
                    self._is_streaming = False
                    self._chunk_counter = 0
                    self._extracting_reasoning = False

                    # Use extra safety - just update current node text
                    # and delay full UI update to avoid recursive crash
                    from PyQt6.QtCore import QTimer

                    # First update just the node content
                    try:
                        cursor = self.chat_display.textCursor()
                        self.chat_display.moveCursor(QTextCursor.MoveOperation.End)
                        self.chat_display.ensureCursorVisible()
                    except:
                        pass

                    # Schedule an update but first return control to main thread
                    # to avoid recursion issues
                    QTimer.singleShot(300, lambda: self.update_ui())
        except Exception as e:
            print(f"Error in set_reasoning_steps: {str(e)}")

    def _format_code_block(self, match):
        """Format code blocks with syntax highlighting"""
        language = match.group(1) or ""
        code = match.group(2)

        # Simple syntax highlighting could be implemented here
        # For now, we'll just wrap it in a pre tag with styling
        return f'<pre style="background-color:#2d2d2d; color:#f8f8f2; padding:10px; border-radius:5px; overflow:auto;">{code}</pre>'

    def _extract_reasoning_steps(self, content):
        """Extract reasoning steps from message content with improved pattern detection"""
        import re

        # If content is None or empty, return empty list
        if not content:
            print("Empty content for reasoning extraction")
            return []

        # Skip this entirely during streaming mode
        if getattr(self, '_is_streaming', False):
            print("Skipping reasoning extraction during streaming")
            return []

        # Set extraction flag
        self._extracting_reasoning = True

        try:
            # Debug: Print the first 100 chars of content to see what we're working with
            print(f"Extracting reasoning from content starting with: {content[:min(100, len(content))]}")

            # For some models, the reasoning structure uses markdown headers
            # This is a special case for o1/o3 models
            if "**Step" in content or "## Step" in content:
                print("Found markdown-style reasoning structure")

            # Patterns to identify reasoning steps (enhanced for more patterns)
            patterns = [
                # Classic step patterns
                (r"Step (\d+):(.*?)(?=Step \d+:|$)", "Step {}"),
                (r"Step (\d+)\.(.*?)(?=Step \d+\.|$)", "Step {}"),
                (r"Step (\d+)(.*?)(?=Step \d+|$)", "Step {}"),
                (r"(\d+)\. (.*?)(?=\d+\. |$)", "Step {}"),

                # Common reasoning frameworks
                (r"Let's think step by step:(.*?)(?=Therefore|So the answer|In conclusion|$)", "Reasoning"),
                (r"I'll solve this step by step:(.*?)(?=Therefore|So the answer|In conclusion|$)", "Problem Solving"),
                (r"Let me think through this:(.*?)(?=Therefore|So the answer|In conclusion|$)", "Analysis"),

                # For o1-mini specific patterns (based on your example)
                (r"Puzzle:(.*?)Solution:(.*?)(?=$)", "Puzzle & Solution"),
                (r"\*\*Solution:\*\*(.*?)(?=$)", "Solution"),
                (r"\*\*Puzzle:\*\*(.*?)\*\*Solution:\*\*(.*?)(?=$)", "Puzzle & Solution"),

                # Sequential reasoning patterns
                (r"First,(.*?)(?=Second,|Next,|Then,|Finally,|Therefore|$)", "Step 1"),
                (r"Second,(.*?)(?=Third,|Next,|Then,|Finally,|Therefore|$)", "Step 2"),
                (r"Third,(.*?)(?=Fourth,|Next,|Then,|Finally,|Therefore|$)", "Step 3"),

                # Numbered or bulleted lists that might be reasoning
                (r"\d+\)(.*?)(?=\d+\)|$)", "Point {}"),
                (r"•(.*?)(?=•|$)", "Point")
            ]

            steps = []

            # First, check if the content contains explicit section markers
            solution_match = re.search(r'\*\*Solution:\*\*(.*?)(?=$|Alternatively|Therefore|In conclusion)', content, re.DOTALL)
            if solution_match:
                solution_content = solution_match.group(1).strip()
                steps.append({
                    "name": "Solution Process",
                    "content": solution_content,
                    "match": solution_match.group(0)
                })
                print(f"Found explicit solution section: {solution_content[:50]}...")

            # Try to extract numbered steps within the content
            number_steps = re.finditer(r'\d+\.\s+\*\*([^*]+)\*\*:(.*?)(?=\d+\.\s+\*\*|$)', content, re.DOTALL)
            step_found = False
            for i, match in enumerate(number_steps):
                step_found = True
                step_name = match.group(1).strip() if match.group(1) else f"Step {i + 1}"
                step_content = match.group(2).strip()
                steps.append({
                    "name": step_name,
                    "content": step_content,
                    "match": match.group(0)
                })
                print(f"Found numbered step: {step_name} - {step_content[:50]}...")

            # If we didn't find any explicit steps yet, try the pattern matching approach
            if not steps:
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
                            print(f"Found pattern match: {step_name} - {step_content[:50]}...")

            # Last resort: if the content has reasoning tokens but we found no steps,
            # try to analyze the overall structure
            if not steps and "**" in content:
                # Look for bold text sections which might indicate steps
                bold_sections = re.finditer(r'\*\*([^*]+)\*\*:(.*?)(?=\*\*|$)', content, re.DOTALL)
                for i, match in enumerate(bold_sections):
                    section_name = match.group(1).strip()
                    section_content = match.group(2).strip()
                    steps.append({
                        "name": section_name,
                        "content": section_content,
                        "match": match.group(0)
                    })
                    print(f"Found bold section: {section_name} - {section_content[:50]}...")

            if steps:
                print(f"Total reasoning steps found: {len(steps)}")
            else:
                print("No reasoning steps detected in content")

            # Clear the recursion prevention flag
            self._extracting_reasoning = False
            return steps

        except Exception as e:
            print(f"Error in set_reasoning_steps: {str(e)}")

    def _remove_reasoning_steps(self, content, steps):
        """Remove reasoning steps from content for cleaner display"""
        # Make a copy of the content
        cleaned_content = content

        # Try different approaches to remove the reasoning sections

        # First, try to remove based on the exact match strings in the extracted steps
        for step in steps:
            if "match" in step:
                cleaned_content = cleaned_content.replace(step["match"], "", 1)  # Replace only first occurrence

        # If that didn't work well (content still has most of the steps), try to identify
        # the main solution or conclusion section
        if len(cleaned_content) > len(content) * 0.7:  # If we removed less than 30%
            # Look for standard conclusion markers
            conclusion_patterns = [
                r'Therefore,(.*?)$',
                r'In conclusion,(.*?)$',
                r'To summarize,(.*?)$',
                r'So the answer is(.*?)$',
                r'The solution is(.*?)$'
            ]

            for pattern in conclusion_patterns:
                import re
                conclusion_match = re.search(pattern, content, re.DOTALL)
                if conclusion_match:
                    # Just keep the conclusion part
                    cleaned_content = conclusion_match.group(0)
                    break

        # Clean up any double newlines
        import re
        cleaned_content = re.sub(r'\n\s*\n', '\n\n', cleaned_content)

        # If the content is empty or too short after cleanup, return the original
        if len(cleaned_content.strip()) < 20:
            return content

        return cleaned_content.strip()
