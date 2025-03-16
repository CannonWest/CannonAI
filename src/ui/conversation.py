"""
Conversation UI components for the OpenAI Chat application.
"""
import os
from typing import Dict, List, Optional, Any, Callable
from functools import partial

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QSplitter, QMessageBox, QDialogButtonBox, QFileDialog, QDialog, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QColor, QTextCursor, QDragEnterEvent, QDropEvent

from src.utils import DARK_MODE, MODEL_CONTEXT_SIZES, MODEL_OUTPUT_LIMITS, MODEL_PRICING
from src.models import DBConversationTree, DBMessageNode
from src.ui.components import ConversationTreeWidget, BranchNavBar
from src.utils.file_utils import get_file_info, format_size
from src.ui.graph_view import ConversationGraphView
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


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
        self.logger = get_logger(f"{__name__}.MainWindow")

        # Initialize state variables to prevent NoneType errors
        self._is_streaming = False
        self._chunk_counter = 0
        self._extracting_reasoning = False

        # Loading indicator variables
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._update_loading_indicator)
        self._loading_timer.setInterval(500)  # Update every 500ms
        self._loading_state = 0
        self._loading_active = False

        # Enable drag and drop
        self.setAcceptDrops(True)

        # Initialize empty attachments list
        self.current_attachments = []

        # NEW: Store reasoning steps
        self.reasoning_steps = []

        # Branch navigation bar
        self.branch_nav = BranchNavBar()
        self.branch_nav.node_selected.connect(self.navigate_to_node)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.branch_nav)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFixedHeight(60)  # Adjust as desired

        self.layout.addWidget(self.scroll_area)

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

        # Graphical view for branch navigation
        self.tree_container = QWidget()
        self.tree_layout = QVBoxLayout(self.tree_container)
        self.tree_layout.setContentsMargins(0, 0, 0, 0)

        self.tree_label = QLabel("Conversation Graph")
        self.tree_label.setStyleSheet(f"font-weight: bold; color: {DARK_MODE['foreground']};")

        # Replace tree view with graphical view
        self.graph_view = ConversationGraphView()
        self.graph_view.node_selected.connect(self.navigate_to_node)
        self.graph_view.setStyleSheet(f"background-color: {DARK_MODE['highlight']};")

        self.tree_layout.addWidget(self.tree_label)
        self.tree_layout.addWidget(self.graph_view)

        # Add zoom controls
        self.zoom_container = QWidget()
        self.zoom_layout = QHBoxLayout(self.zoom_container)
        self.zoom_layout.setContentsMargins(0, 5, 0, 5)

        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedWidth(30)
        self.zoom_in_btn.setToolTip("Zoom In")
        self.zoom_in_btn.clicked.connect(lambda: self.graph_view.scale(1.2, 1.2))

        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.setFixedWidth(30)
        self.zoom_out_btn.setToolTip("Zoom Out")
        self.zoom_out_btn.clicked.connect(lambda: self.graph_view.scale(0.8, 0.8))

        self.fit_btn = QPushButton("Fit")
        self.fit_btn.setToolTip("Fit View")
        self.fit_btn.clicked.connect(lambda: self.graph_view.fitInView(
            self.graph_view._scene.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio
        ))

        self.zoom_layout.addWidget(self.zoom_out_btn)
        self.zoom_layout.addWidget(self.fit_btn)
        self.zoom_layout.addWidget(self.zoom_in_btn)

        self.tree_layout.addWidget(self.zoom_container)

        # Split view for conversation and branch tree
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Main conversation container
        self.conversation_container = QWidget()
        self.conversation_layout = QVBoxLayout(self.conversation_container)

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

        # Add state tracking for deferred UI updates
        self._ui_update_pending = False
        self._is_streaming = False
        self._updating_ui = False
        self._streaming_started = False
        self._has_loading_text = False

        self._message_cache = {}  # node_id -> rendered html
        self._last_branch_ids = set()  # Track which messages were last displayed

        # Update the UI with the initial conversation
        if self.conversation_tree:
            self.update_ui()

    def set_conversation_tree(self, conversation_tree: DBConversationTree):
        """Set the conversation tree and update the UI"""
        self.conversation_tree = conversation_tree
        self.update_ui()

    def update_ui(self):
        """Update the UI with the current conversation state"""
        # Protect against recursion
        if hasattr(self, '_updating_ui') and self._updating_ui:
            print("WARNING: Prevented recursive UI update")
            return

        if not self.conversation_tree:
            return

        try:
            self._updating_ui = True

            # Don't do expensive UI updates during streaming
            if hasattr(self, '_is_streaming') and self._is_streaming:
                # Mark that we need a full update when streaming ends
                self._ui_update_pending = True
                # Only update the chat display during streaming
                self.update_chat_display()
                return

            # Normal full UI update when not streaming
            try:
                current_branch = self.conversation_tree.get_current_branch()
                self.branch_nav.update_branch(current_branch)
            except Exception as e:
                print(f"Error updating branch nav: {str(e)}")

            # Update tree view
            try:
                self.graph_view.update_tree(self.conversation_tree)
            except Exception as e:
                print(f"Error updating graph view: {str(e)}")

            # Update chat display
            try:
                self.update_chat_display()
            except Exception as e:
                print(f"Error updating chat display: {str(e)}")

            # Update retry button state
            try:
                self.update_retry_button()
            except Exception as e:
                print(f"Error updating retry button: {str(e)}")

            # Reset pending update flag since we just did a full update
            self._ui_update_pending = False
        finally:
            self._updating_ui = False

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
        """Update the chat display with the current branch messages more efficiently"""
        if not self.conversation_tree:
            return

        # Get the current branch messages
        branch = self.conversation_tree.get_current_branch()
        current_node = self.conversation_tree.current_node

        # Get the IDs in the current branch
        current_branch_ids = {node.id for node in branch}

        # Check if we just need to append new content
        append_only = False
        if self._last_branch_ids and current_branch_ids.issuperset(self._last_branch_ids):
            # All previous messages are still there, we might just need to append
            # Count messages to determine if we're just adding to the end
            if len(current_branch_ids) == len(self._last_branch_ids) + 1:
                # Added exactly one message
                append_only = True

        if append_only and hasattr(self, '_is_streaming') and self._is_streaming:
            # During streaming, we've already been updating incrementally
            # So we don't need to do anything here
            return

        # If the conversation structure has changed significantly, or this is
        # the first update, we need to redraw the entire conversation
        if not append_only or not self._last_branch_ids:
            self.chat_display.clear()
            self._render_full_conversation(branch)
        else:
            # We just need to append the new message(s)
            new_messages = [node for node in branch if node.id not in self._last_branch_ids]
            for node in new_messages:
                self._render_single_message(node)

        # Store the current branch IDs for next comparison
        self._last_branch_ids = current_branch_ids

        # Scroll to bottom
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)

        # Update token usage and model info based on the current node
        self._update_info_displays(current_node)

    def _render_full_conversation(self, branch):
        """Render the full conversation branch"""
        for node in branch:
            self._render_single_message(node)

    def _render_single_message(self, node):
        """Render a single message to the chat display"""
        # Check if we have this message cached and it hasn't changed
        cache_key = f"{node.id}:{node.content}"  # Include content in key to detect changes

        if cache_key in self._message_cache:
            # Use cached HTML
            html_content = self._message_cache[cache_key]
            self.chat_display.insertHtml(html_content)
            self.chat_display.insertPlainText("\n\n")  # Add spacing
            return

        # Determine message style based on role
        if node.role == "system":
            color = DARK_MODE["system_message"]
            prefix = "🔧 System: "
        elif node.role == "user":
            color = DARK_MODE["user_message"]
            prefix = "👤 You: "
        elif node.role == "assistant":
            color = DARK_MODE["assistant_message"]
            prefix = "🤖 Assistant: "
            # Add model info to the prefix if available
            if node.model_info and "model" in node.model_info:
                prefix = f"🤖 Assistant ({node.model_info['model']}): "
        elif node.role == "developer":
            color = DARK_MODE["system_message"]
            prefix = "👩‍💻 Developer: "
        else:
            color = DARK_MODE["foreground"]
            prefix = f"{node.role}: "

        # Start building HTML content
        html_parts = []

        # Add prefix with styling
        prefix_html = f'<span style="color: {color};">{prefix}</span>'
        html_parts.append(prefix_html)

        # Process content for markdown formatting
        content_html = self.process_markdown(node.content)
        html_parts.append(content_html)

        # Add reasoning steps if this is an assistant node
        if node.role == "assistant":
            reasoning_html = self._render_reasoning_steps(node)
            if reasoning_html:
                html_parts.append(reasoning_html)

        # Add file attachments if present
        if hasattr(node, 'attached_files') and node.attached_files:
            attachments_html = self._render_attachments(node.attached_files)
            html_parts.append(attachments_html)

        # Join all parts
        full_html = "".join(html_parts)

        # Cache the rendered HTML
        self._message_cache[cache_key] = full_html

        # Insert into display
        self.chat_display.insertHtml(full_html)
        self.chat_display.insertPlainText("\n\n")  # Add spacing

    def _render_reasoning_steps(self, node):
        """Render reasoning steps for an assistant message with comprehensive model support"""
        # Reasoning steps are currently disabled as OpenAI API doesn't support them
        # Return empty string to avoid displaying any reasoning
        print(f"DEBUG: Reasoning rendering disabled for node {node.id}, role: {node.role}")
        return ""
        """
        # Check for reasoning tokens or reasoning steps
        reasoning_tokens = 0
        if node.token_usage and "completion_tokens_details" in node.token_usage:
            details = node.token_usage["completion_tokens_details"]
            reasoning_tokens = details.get("reasoning_tokens", 0)

        # Print debug info about this node and its reasoning data
        print(f"DEBUG: Rendering reasoning for node {node.id}, role: {node.role}")
        print(f"DEBUG: Model info: {node.model_info}")
        print(f"DEBUG: Token usage: {node.token_usage}")
        print(f"DEBUG: Reasoning tokens: {reasoning_tokens}")

        # Determine if this is a reasoning-capable model
        is_reasoning_model = False
        model_name = ""
        if node.model_info and "model" in node.model_info:
            model_name = node.model_info["model"]
            from src.utils import REASONING_MODELS
            is_reasoning_model = (
                    model_name in REASONING_MODELS or
                    "o3" in model_name or
                    "o1" in model_name or
                    "deepseek-reasoner" in model_name
            )

        print(f"DEBUG: Model name: {model_name}, is_reasoning_model: {is_reasoning_model}")

        # Try to extract reasoning steps from all possible sources
        node_reasoning = None

        # First try the standard attribute
        if hasattr(node, 'reasoning_steps'):
            node_reasoning = node.reasoning_steps
            print(f"DEBUG: Found reasoning_steps attribute with {len(node_reasoning) if node_reasoning else 0} steps")

        # If no reasoning found but this is a reasoning model, we need to show something
        should_show_reasoning = (
                (node_reasoning and len(node_reasoning) > 0) or  # Has reasoning steps
                reasoning_tokens > 0 or  # Has reasoning tokens
                is_reasoning_model  # Is a reasoning-capable model
        )

        if not should_show_reasoning:
            print("DEBUG: No reasoning indicators found for this node")
            return ""
        """

    def _render_attachments(self, attachments):
        """Render file attachments HTML"""
        html_parts = []
        file_count = len(attachments)

        html_parts.append(f'<div style="color: {DARK_MODE["accent"]}; margin-top: 10px;">📎 {file_count} file{"s" if file_count > 1 else ""} attached:</div>')
        html_parts.append('<ul style="margin-top: 5px; margin-bottom: 5px;">')

        for file_info in attachments:
            file_name = file_info['file_name']
            file_type = file_info.get('mime_type', 'Unknown type')
            file_size = file_info.get('size', 0)
            token_count = file_info.get('token_count', 0)

            # Format file size
            if hasattr(self, 'format_size'):
                size_str = self.format_size(file_size)
            else:
                size_str = f"{file_size} bytes"

            html_parts.append(f'<li>{file_name} ({size_str}, {token_count} tokens)</li>')

        html_parts.append('</ul>')
        return "".join(html_parts)

    def update_chat_streaming(self, chunk):
        """Update the chat display during streaming with improved reliability and ordering"""
        try:
            # Add debug logging
            print(f"DEBUG: Received streaming chunk in update_chat_streaming: '{chunk[:20]}...' (length: {len(chunk)})")
            self.logger.debug(f"Processing chunk in update_chat_streaming: {chunk[:20]}...")

            # Safety check for extremely large chunks that could cause memory issues
            if len(chunk) > 10000:  # 10KB limit for a single chunk
                chunk = chunk[:10000] + "... [CHUNK TRUNCATED - TOO LARGE]"
                print("WARNING: Chunk size exceeded limits - truncated")
                self.logger.warning(f"Chunk size exceeded limits - truncated to 10KB")

            # Set streaming mode flag
            self._is_streaming = True
            self._ui_update_pending = True

            # Handle first chunk differently - remove loading indicator and add assistant prefix
            if not hasattr(self, '_streaming_started') or not self._streaming_started:
                self._streaming_started = True
                print("DEBUG: First chunk detected - initializing streaming display")

                # Clear any previous streaming content
                if hasattr(self, '_total_streamed_content'):
                    self._total_streamed_content = ""

                # Make sure we're not in the middle of a conflicting operation
                if hasattr(self, '_updating_display') and self._updating_display:
                    print("WARNING: Display update in progress - potential conflict")
                    self._updating_display = False

                # Remove any loading indicator text if present
                if hasattr(self, '_has_loading_text') and self._has_loading_text:
                    print("DEBUG: Removing loading indicator text")
                    try:
                        cursor = self.chat_display.textCursor()
                        cursor.movePosition(QTextCursor.MoveOperation.End)
                        cursor.movePosition(QTextCursor.MoveOperation.Up, QTextCursor.MoveMode.KeepAnchor, 1)
                        cursor.removeSelectedText()
                        self._has_loading_text = False
                    except Exception as cursor_error:
                        print(f"Error removing loading text: {str(cursor_error)}")
                        # Just continue if cursor operations fail

                    # Check for any remaining loading text that might not have been removed
                    current_text = self.chat_display.toPlainText()
                    if current_text.strip().endswith("Waiting for response.") or \
                            current_text.strip().endswith("Waiting for response..") or \
                            current_text.strip().endswith("Waiting for response..."):
                        try:
                            cursor = self.chat_display.textCursor()
                            cursor.movePosition(QTextCursor.MoveOperation.End)
                            # Select more text to ensure we get the whole loading indicator
                            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, 30)
                            selected_text = cursor.selectedText()
                            if "Waiting for response" in selected_text:
                                # Only remove the part that contains the loading indicator
                                indicator_pos = selected_text.find("Waiting for response")
                                if indicator_pos >= 0:
                                    cursor.movePosition(QTextCursor.MoveOperation.End)
                                    cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor,
                                                        len(selected_text) - indicator_pos)
                                    cursor.removeSelectedText()
                                    print("DEBUG: Removed additional loading indicator text")
                        except Exception as e:
                            print(f"Error removing additional loading text: {str(e)}")

                # Add assistant prefix for first message
                try:
                    # Get current model if available
                    model_name = ""
                    if self.conversation_tree and self.conversation_tree.current_node:
                        node = self.conversation_tree.current_node
                        if hasattr(node, 'model_info') and isinstance(node.model_info, dict) and 'model' in node.model_info:
                            model_name = node.model_info['model']

                    # Add assistant prefix with model if available
                    if model_name:
                        prefix = f"\n\n🤖 Assistant ({model_name}): "
                    else:
                        prefix = "\n\n🤖 Assistant: "

                    # Get cursor position at the end
                    cursor = self.chat_display.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    self.chat_display.setTextCursor(cursor)

                    # Insert the prefix
                    self.chat_display.insertHtml(f'<span style="color: {DARK_MODE["assistant_message"]};">{prefix}</span>')
                    print(f"DEBUG: Added assistant prefix: {prefix}")
                except Exception as prefix_error:
                    print(f"Error adding assistant prefix: {str(prefix_error)}")
                    # Continue even if prefix insertion fails

            # Initialize or update the accumulated streaming content
            if not hasattr(self, '_total_streamed_content'):
                self._total_streamed_content = chunk
            else:
                self._total_streamed_content += chunk

            # Set a flag to indicate we're updating the display
            self._updating_display = True

            # Insert the chunk text
            try:
                # Get cursor position at the end
                cursor = self.chat_display.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.chat_display.setTextCursor(cursor)

                # Insert the chunk as plain text
                self.chat_display.insertPlainText(chunk)

                # Ensure visible to keep scrolling with new content
                self.chat_display.ensureCursorVisible()
                print(f"DEBUG: Inserted chunk text (length: {len(chunk)})")
            except Exception as text_error:
                print(f"Error inserting text: {str(text_error)}")
                # Try an alternative method if the first fails
                try:
                    self.chat_display.append(chunk)
                    print("DEBUG: Used append fallback method")
                except Exception as append_error:
                    print(f"Error using append fallback: {str(append_error)}")
            finally:
                # Clear the updating flag
                self._updating_display = False
        except Exception as e:
            print(f"Error in update_chat_streaming: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def complete_streaming_update(self):
        """Perform a full UI update after streaming is complete with improved cleanup and ordering fixes"""
        print("DEBUG: Completing streaming update")

        # Reset streaming flag first
        self._is_streaming = False

        # Make sure we're not in the middle of an update
        if hasattr(self, '_updating_display') and self._updating_display:
            print("WARNING: Display update still in progress - waiting")
            import time
            time.sleep(0.1)  # Brief pause to allow any ongoing operations to complete
            self._updating_display = False

        # Force stop loading indicator if it's still active
        if hasattr(self, '_loading_active') and self._loading_active:
            print("DEBUG: Stopping any active loading indicator")
            self.stop_loading_indicator()
        else:
            print("DEBUG: Loading indicator not active during completion")

        # Double-check loading indicator timer is stopped
        if hasattr(self, '_loading_timer') and self._loading_timer.isActive():
            print("DEBUG: Forcibly stopping loading timer")
            self._loading_timer.stop()

        # Ensure any loading text is removed
        if hasattr(self, '_has_loading_text') and self._has_loading_text:
            print("DEBUG: Cleaning up loading text indicator")
            try:
                cursor = self.chat_display.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.movePosition(QTextCursor.MoveOperation.Up, QTextCursor.MoveMode.KeepAnchor, 1)
                cursor.removeSelectedText()
                self._has_loading_text = False
            except Exception as cursor_error:
                print(f"Error removing loading text: {str(cursor_error)}")

        # Double check message integrity using the accumulated content
        if hasattr(self, '_total_streamed_content') and self._total_streamed_content:
            # Get the conversation tree and current node
            if self.conversation_tree and self.conversation_tree.current_node:
                current_node = self.conversation_tree.current_node

                # Check if the content matches what we've accumulated
                try:
                    db_content = current_node.content
                    streamed_content = self._total_streamed_content

                    if db_content != streamed_content:
                        print(f"WARNING: Content mismatch - DB: {len(db_content)} chars, Streamed: {len(streamed_content)} chars")

                        # Update the database with the streamed content for consistency
                        from src.models.db_manager import DatabaseManager
                        conn = None
                        try:
                            db_manager = DatabaseManager()
                            conn = db_manager.get_connection()
                            cursor = conn.cursor()

                            cursor.execute(
                                'UPDATE messages SET content = ? WHERE id = ?',
                                (streamed_content, current_node.id)
                            )
                            # Also update in-memory content
                            current_node.content = streamed_content
                            conn.commit()
                            print("DEBUG: Updated node content from streamed content")
                        except Exception as db_error:
                            print(f"Error updating content from streamed content: {str(db_error)}")
                            if conn:
                                conn.rollback()
                        finally:
                            if conn:
                                conn.close()
                except Exception as e:
                    print(f"Error checking content integrity: {str(e)}")

        # Finalize and add extra newlines for clean separation between messages
        try:
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.chat_display.setTextCursor(cursor)
            self.chat_display.insertPlainText("\n\n")  # Add spacing after completed message
            print("DEBUG: Added final spacing after message")
        except Exception as e:
            print(f"Error adding final spacing: {str(e)}")

        # Force a full chat display update to ensure content is complete
        try:
            print("DEBUG: Forcing full chat display update")
            self.update_chat_display()
        except Exception as display_error:
            print(f"Error updating chat display: {str(display_error)}")

        # Reset streaming state variables
        if hasattr(self, '_streaming_started'):
            self._streaming_started = False

        # Clear accumulated content
        if hasattr(self, '_total_streamed_content'):
            self._total_streamed_content = ""

        # Only update if we have pending updates
        if hasattr(self, '_ui_update_pending') and self._ui_update_pending:
            print("DEBUG: Scheduling deferred complete update")
            # Ensure we wait a short moment to allow any in-progress
            # operations to complete first (important for stability)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(300, self._do_complete_update)  # Increased delay for stability

    def _do_complete_update(self):
        """Perform the actual delayed UI update"""
        try:
            # Ensure we have a valid conversation tree
            if not self.conversation_tree:
                return

            # Do a full UI update now
            current_branch = self.conversation_tree.get_current_branch()

            # Update branch navigation
            self.branch_nav.update_branch(current_branch)

            # Update graph view
            self.graph_view.update_tree(self.conversation_tree)

            # Update retry button
            self.update_retry_button()

            # Reset pending update flag
            self._ui_update_pending = False

            # Log that we completed a deferred update for debugging
            print("Completed deferred UI update after streaming")

        except Exception as e:
            print(f"Error in complete_streaming_update: {str(e)}")

    def clear_message_cache(self):
        """Clear the message rendering cache"""
        self._message_cache = {}

    def resizeEvent(self, event):
        """Handle widget resize events - invalidate cache on resize"""
        super().resizeEvent(event)
        # Clear cache as messages may need to reflow at new width
        self.clear_message_cache()

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
        """Handle sending a new message with improved error handling"""
        try:
            # First, check if we're already processing a message
            if hasattr(self, '_processing_message') and self._processing_message:
                from PyQt6.QtWidgets import QMessageBox

                # Show warning dialog
                reply = QMessageBox.question(
                    self,
                    "Message in Progress",
                    "A message is already being processed. Do you want to cancel it and send a new one?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )

                if reply != QMessageBox.StandardButton.Yes:
                    return

                # Cancel the current processing
                if hasattr(self, '_active_thread_id'):
                    from src.services.api import OpenAIThreadManager
                    thread_manager = OpenAIThreadManager()
                    thread_manager.cancel_worker(self._active_thread_id)
                    print(f"Cancelled thread: {self._active_thread_id}")

                    # Make sure to stop the loading indicator
                    if hasattr(self, '_loading_active') and self._loading_active:
                        print("DEBUG: Stopping loading indicator after cancellation")
                        self.stop_loading_indicator()

                    # Reset processing state
                    self._processing_message = False

            # Check if conversation tree is valid
            if not self.conversation_tree:
                print("ERROR: No conversation tree available")
                return

            # Get message text with safety checks
            try:
                message = self.text_input.toPlainText().strip()
            except Exception as text_error:
                print(f"Error getting message text: {str(text_error)}")
                message = ""

            # Check if message is too long (prevent memory issues)
            if len(message) > 100000:  # 100KB limit
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Message Too Long",
                    "Your message is too long. Please shorten it or split it into multiple messages."
                )
                return

            # Prepare attachments if present
            attachments_copy = None
            try:
                if hasattr(self, 'current_attachments') and self.current_attachments:
                    # Calculate total attachment size
                    total_size = sum(len(attachment.get('content', '')) for attachment in self.current_attachments)

                    # Check if total size is too large
                    if total_size > 10 * 1024 * 1024:  # 10MB limit
                        from PyQt6.QtWidgets import QMessageBox
                        QMessageBox.warning(
                            self,
                            "Attachments Too Large",
                            "Your attachments are too large. Please reduce their size or number."
                        )
                        return

                    # Just note that there are attachments in the UI message
                    if message:
                        attachment_count = len(self.current_attachments)
                        file_text = f"\n\n[{attachment_count} file{'s' if attachment_count > 1 else ''} attached]"
                        message += file_text
                    else:
                        message = f"[Attached {len(self.current_attachments)} file{'s' if len(self.current_attachments) > 1 else ''}]"

                    # Make a deep copy of attachments to prevent memory issues
                    attachments_copy = []
                    for attachment in self.current_attachments:
                        # Create a new dict with only the essential fields
                        clean_attachment = {
                            'file_name': attachment.get('file_name', 'unnamed_file'),
                            'mime_type': attachment.get('mime_type', 'text/plain'),
                            'content': attachment.get('content', ''),
                            'token_count': attachment.get('token_count', 0)
                        }
                        attachments_copy.append(clean_attachment)
            except Exception as attach_error:
                print(f"Error processing attachments: {str(attach_error)}")
                attachments_copy = None

            # Final check for empty message
            if not message:
                return

            # Clear the input field
            try:
                self.text_input.clear()
            except Exception as clear_error:
                print(f"Error clearing input field: {str(clear_error)}")
                # Continue anyway

            # Store attachments for use in the main window's send_message method
            self._pending_attachments = attachments_copy

            # Emit signal to send message
            try:
                print(f"DEBUG: Emitting send_message signal with: '{message[:30]}...'")
                self.send_message.emit(message)
            except Exception as emit_error:
                print(f"Error emitting send message signal: {str(emit_error)}")
                # Try to recover from emission error
                if hasattr(self, '_loading_active') and self._loading_active:
                    self.stop_loading_indicator()

                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self,
                    "Error Sending Message",
                    f"Failed to send message: {str(emit_error)}"
                )
                return

            # Clear attachments after sending
            try:
                self.clear_attachments()
            except Exception as clear_attach_error:
                print(f"Error clearing attachments: {str(clear_attach_error)}")
                # Continue anyway

        except Exception as e:
            print(f"Critical error in on_send: {str(e)}")
            import traceback
            traceback.print_exc()

            # Try to show error dialog
            try:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self,
                    "Error Sending Message",
                    f"An unexpected error occurred: {str(e)}"
                )
            except:
                pass  # Last resort, just ignore if even the error dialog fails

    def on_retry(self):
        """Handle retry button click"""
        if not self.conversation_tree:
            return

        # Check if retry is possible
        if self.conversation_tree.retry_current_response():
            self.update_ui()
            self.retry_request.emit()

    def toggle_info(self):
        """Toggle the visibility of the response details content"""
        visible = not self.info_content.isVisible()
        self.info_content.setVisible(visible)
        self.info_toggle.setText("▲" if visible else "▼")

    def add_cot_step(self, step_name, content):
        """Add a step to the chain of thought"""
        try:
            # Stop loading indicator when first thinking step is received
            if hasattr(self, '_loading_active') and self._loading_active:
                self.stop_loading_indicator()

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

    def set_reasoning_steps(self, steps):
        """Store reasoning steps for the current response with improved debugging and handling"""
        # Currently disabled as OpenAI API doesn't support reasoning steps
        # Method kept for future use when the API supports this feature
        print(f"Received reasoning steps (currently disabled): {len(steps) if steps else 0} steps")

        # Still reset streaming state for proper UI updates
        if hasattr(self, '_is_streaming'):
            self._is_streaming = False
        if hasattr(self, '_chunk_counter'):
            self._chunk_counter = 0
        if hasattr(self, '_extracting_reasoning'):
            self._extracting_reasoning = False

        # Update UI without processing reasoning steps
        from PyQt6.QtCore import QTimer
        self.update_chat_display()
        QTimer.singleShot(300, lambda: self.update_ui())

        """
        try:
            # Stop loading indicator if it's still active
            if hasattr(self, '_loading_active') and self._loading_active:
                self.stop_loading_indicator()

            # Log steps being set for debugging
            print(f"DEBUG: Setting reasoning steps. Steps type: {type(steps)}, o3-mini?: {'o3' in self.model_label.text() if hasattr(self, 'model_label') else 'unknown'}")

            # Ensure steps is a valid list
            if steps is None:
                steps = []

            print(f"Received {len(steps)} reasoning steps from worker")

            # Log details of the first few steps for debugging
            if steps and len(steps) > 0:
                print(f"First step info: {steps[0]}")

                # Check if steps have expected structure
                if not isinstance(steps[0], dict) or not all(key in steps[0] for key in ["name", "content"]):
                    print("WARNING: Reasoning steps don't have expected structure")

                    # Try to fix structure if possible
                    fixed_steps = []
                    for i, step in enumerate(steps):
                        if isinstance(step, str):
                            fixed_steps.append({
                                "name": f"Reasoning Step {i + 1}",
                                "content": step
                            })
                        elif isinstance(step, dict):
                            # Ensure it has required keys
                            fixed_step = {
                                "name": step.get("name", step.get("step", f"Reasoning Step {i + 1}")),
                                "content": step.get("content", str(step))
                            }
                            fixed_steps.append(fixed_step)

                    if fixed_steps:
                        print(f"Fixed {len(fixed_steps)} steps to correct structure")
                        steps = fixed_steps

            # Store the complete set of steps
            self.reasoning_steps = steps

            # If we have a current node that's an assistant, store the steps with it
            if self.conversation_tree and self.conversation_tree.current_node:
                node = self.conversation_tree.current_node
                if node.role == "assistant":
                    print(f"DEBUG: Storing {len(steps)} reasoning steps with node {node.id}")

                    # Create database-backed storage for reasoning steps
                    conn = None
                    try:
                        # Get a database connection
                        from src.models.db_manager import DatabaseManager
                        db_manager = DatabaseManager()
                        conn = db_manager.get_connection()
                        cursor = conn.cursor()

                        # Delete any existing reasoning steps metadata
                        cursor.execute(
                            'DELETE FROM message_metadata WHERE message_id = ? AND metadata_type = ?',
                            (node.id, 'reasoning_steps')
                        )

                        # Store reasoning steps as metadata
                        import json
                        cursor.execute(
                            '''
                            INSERT INTO message_metadata (message_id, metadata_type, metadata_value)
                            VALUES (?, ?, ?)
                            ''',
                            (node.id, 'reasoning_steps', json.dumps(steps))
                        )

                        conn.commit()
                        print(f"DEBUG: Saved reasoning steps to database for node {node.id}")
                    except Exception as e:
                        print(f"ERROR storing reasoning steps in database: {str(e)}")
                        if conn:
                            conn.rollback()
                    finally:
                        if conn:
                            conn.close()

                    try:
                        # Also store in-memory for immediate use
                        setattr(node, 'reasoning_steps', steps)
                    except Exception as e:
                        print(f"ERROR setting reasoning_steps on node: {str(e)}")

                    # Reset all state flags - VERY IMPORTANT for stability
                    self._is_streaming = False
                    self._chunk_counter = 0
                    self._extracting_reasoning = False

                    # Use extra safety - update UI with delay to avoid recursion
                    from PyQt6.QtCore import QTimer

                    # Immediate chat display update to show content
                    self.update_chat_display()

                    # Schedule a full UI update
                    QTimer.singleShot(300, lambda: self.update_ui())
        except Exception as e:
            print(f"Error in set_reasoning_steps: {str(e)}")
            import traceback
            traceback.print_exc()
        """

    def log_loading_state(self):
        """Log the current state of the loading indicator for debugging"""
        loading_active = getattr(self, '_loading_active', False)
        has_loading_text = getattr(self, '_has_loading_text', False)
        loading_state = getattr(self, '_loading_state', -1)
        is_streaming = getattr(self, '_is_streaming', False)

        print(f"LOADING DEBUG: active={loading_active}, has_text={has_loading_text}, " +
              f"state={loading_state}, streaming={is_streaming}")

    def _format_code_block(self, match):
        """Format code blocks with syntax highlighting"""
        language = match.group(1) or ""
        code = match.group(2)

        # Simple syntax highlighting could be implemented here
        # For now, we'll just wrap it in a pre tag with styling
        return f'<pre style="background-color:#2d2d2d; color:#f8f8f2; padding:10px; border-radius:5px; overflow:auto;">{code}</pre>'

    def _update_info_displays(self, current_node):
        """Update token usage and model info displays with comprehensive support"""
        if current_node.role == "assistant":
            # Extract model info first
            model_name = "unknown"
            if current_node.model_info and "model" in current_node.model_info:
                model_name = current_node.model_info["model"]

            # Determine if this is a reasoning-capable model
            from src.utils import REASONING_MODELS
            is_reasoning_model = (
                    model_name in REASONING_MODELS or
                    "o3" in model_name or
                    "o1" in model_name or
                    "deepseek-reasoner" in model_name
            )

            print(f"DEBUG: Updating info for model {model_name}, is_reasoning_model: {is_reasoning_model}")

            # Extract and display token usage with detailed logging
            if current_node.token_usage:
                usage = current_node.token_usage
                print(f"DEBUG: Token usage data: {usage}")

                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)

                # Show reasoning tokens if available or if this is a reasoning model
                reasoning_tokens = 0
                has_reasoning_details = False

                if "completion_tokens_details" in usage:
                    details = usage["completion_tokens_details"]
                    print(f"DEBUG: Completion token details: {details}")
                    reasoning_tokens = details.get("reasoning_tokens", 0)
                    has_reasoning_details = True

                # Build token display based on available information
                if has_reasoning_details and reasoning_tokens > 0:
                    self.token_label.setText(f"Tokens: {completion_tokens} / {total_tokens} ({reasoning_tokens} reasoning)")
                    print(f"DEBUG: Showing {reasoning_tokens} reasoning tokens")
                elif is_reasoning_model:
                    # For reasoning models that don't report reasoning tokens
                    self.token_label.setText(f"Tokens: {completion_tokens} / {total_tokens} (reasoning enabled)")
                    print(f"DEBUG: Showing reasoning-enabled label for model {model_name}")
                else:
                    self.token_label.setText(f"Tokens: {completion_tokens} / {total_tokens}")
            else:
                # No token usage data available
                if is_reasoning_model:
                    self.token_label.setText("Tokens: - / - (reasoning enabled)")
                else:
                    self.token_label.setText("Tokens: - / -")
                print(f"No token usage for assistant node ID: {current_node.id}")

    def start_loading_indicator(self):
        """Start the loading indicator with improved state tracking"""
        print("DEBUG: Starting loading indicator")
        self._loading_state = 0
        self._loading_active = True
        self._has_loading_text = False

        # Reset streaming related flags
        self._streaming_started = False
        self._is_streaming = False

        # Start the timer
        self._loading_timer.start()

        # Show initial state immediately
        self._update_loading_indicator()
        print("DEBUG: Loading indicator initialized")

    def stop_loading_indicator(self):
        """Stop the loading indicator and ensure it's removed from display"""
        print("DEBUG: Stopping loading indicator")

        # Check if already inactive
        if not hasattr(self, '_loading_active') or not self._loading_active:
            print("DEBUG: Loading indicator already inactive")
            # Regardless, make sure state is cleaned up
            self._loading_active = False

            # Still try to remove any loading text if present
            if hasattr(self, '_has_loading_text') and self._has_loading_text:
                print("DEBUG: Loading text still present despite inactive indicator")

        # Stop the timer first - do this unconditionally
        if hasattr(self, '_loading_timer'):
            if self._loading_timer.isActive():
                print("DEBUG: Stopping active loading timer")
                self._loading_timer.stop()
            else:
                print("DEBUG: Loading timer already stopped")

        # Always update state flags
        self._loading_active = False

        # Always attempt to remove the loading text for consistency
        if hasattr(self, '_has_loading_text') and self._has_loading_text:
            try:
                print("DEBUG: Removing loading indicator text")
                cursor = self.chat_display.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)

                # Save the current position
                end_position = cursor.position()

                # Move up to select the loading text line
                cursor.movePosition(QTextCursor.MoveOperation.Up, QTextCursor.MoveMode.KeepAnchor, 1)

                # Only remove if we actually moved (means there was a line to select)
                if cursor.position() < end_position:
                    cursor.removeSelectedText()
                    print("DEBUG: Loading text removed successfully")
                else:
                    print("DEBUG: No text to remove at cursor position")

                self._has_loading_text = False

                # Ensure cursor is at the end after removal
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.chat_display.setTextCursor(cursor)

                # Make sure any changes are visible
                self.chat_display.ensureCursorVisible()
            except Exception as e:
                print(f"ERROR: Failed to remove loading indicator text: {str(e)}")
                import traceback
                traceback.print_exc()
                # Even if we fail to remove it, mark it as gone to prevent duplicate attempts
                self._has_loading_text = False
        else:
            print("DEBUG: No loading text to remove")

    def _update_loading_indicator(self):
        """Update the loading indicator text with improved reliability"""
        # Check if the indicator should still be active
        if not hasattr(self, '_loading_active') or not self._loading_active:
            return

        # Don't update if streaming has started
        if hasattr(self, '_streaming_started') and self._streaming_started:
            print("DEBUG: Loading indicator update skipped - streaming has started")
            self._loading_timer.stop()
            return

        # Cycle through loading states
        states = [
            "⏳ Waiting for response.",
            "⏳ Waiting for response..",
            "⏳ Waiting for response..."
        ]

        # Get current loading text
        loading_text = states[self._loading_state]
        self._loading_state = (self._loading_state + 1) % len(states)

        # Log every third cycle
        if self._loading_state == 0:
            print(f"DEBUG: Updating loading indicator: {loading_text}")

        try:
            # Find the last message in the chat display
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.chat_display.setTextCursor(cursor)

            # Set color to make it more visible
            self.chat_display.setTextColor(QColor(DARK_MODE["accent"]))

            # Replace previous loading text or add new loading text
            if hasattr(self, '_has_loading_text') and self._has_loading_text:
                # Move up and delete previous loading text
                cursor.movePosition(QTextCursor.MoveOperation.Up, QTextCursor.MoveMode.KeepAnchor, 1)
                cursor.removeSelectedText()
                cursor.insertText("\n" + loading_text)
            else:
                # Add loading text for the first time
                self.chat_display.append("\n" + loading_text)  # Add extra newline before first loading indicator
                self._has_loading_text = True
                print("DEBUG: Added initial loading text")

            # Reset text color to normal
            self.chat_display.setTextColor(QColor(DARK_MODE["foreground"]))

            # Make sure the loading text is visible
            self.chat_display.ensureCursorVisible()
        except Exception as e:
            print(f"ERROR updating loading indicator: {str(e)}")
            # Try to recover by stopping the timer
            self._loading_timer.stop()
            self._loading_active = False

    """
    Changes to ConversationBranchTab for optimized file attachment handling.
    Only the relevant methods are shown - the rest of the file remains unchanged.
    """

    def on_attach_file(self):
        """Open file dialog to attach files with enhanced handling for large files"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Attach Files",
            "",
            "Text Files (*.txt *.py *.js *.c *.cpp *.h *.json *.md);;All Files (*)"
        )

        if not file_paths:
            return

        # Show progress dialog for multiple files
        if len(file_paths) > 1:
            from PyQt6.QtWidgets import QProgressDialog
            progress_dialog = QProgressDialog("Processing files...", "Cancel", 0, len(file_paths), self)
            progress_dialog.setWindowTitle("Attaching Files")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.show()
        else:
            progress_dialog = None

        # Process each file asynchronously
        self.pending_file_threads = []  # Keep reference to prevent garbage collection

        for i, file_path in enumerate(file_paths):
            # Update overall progress
            if progress_dialog:
                progress_dialog.setValue(i)
                if progress_dialog.wasCanceled():
                    break

            # Create progress handler to show file-specific progress
            def make_progress_handler(file_name):
                def update_progress(percentage):
                    if progress_dialog and not progress_dialog.wasCanceled():
                        progress_dialog.setLabelText(f"Processing {file_name}: {percentage}%")

                return update_progress

            file_name = os.path.basename(file_path)
            progress_handler = make_progress_handler(file_name)

            # Start asynchronous processing
            from src.utils.file_utils import get_file_info_async
            from src.services.storage import SettingsManager

            settings = SettingsManager().get_settings()
            model = settings.get("model", "gpt-4o")

            # Calculate combined size of existing attachments
            current_size = sum(attachment.get('size', 0) for attachment in self.current_attachments)

            # Cap individual file size (10MB minus current total)
            remaining_mb = max(1, 10 - (current_size / (1024 * 1024)))

            thread, worker = get_file_info_async(
                file_path,
                model,
                on_complete=self.add_processed_file,
                on_error=self.handle_file_error,
                on_progress=progress_handler,
                max_size_mb=remaining_mb
            )

            # Store reference to prevent garbage collection
            self.pending_file_threads.append((thread, worker))

        # Close progress dialog when done
        if progress_dialog:
            progress_dialog.setValue(len(file_paths))

    def add_processed_file(self, file_info):
        """Add a processed file to the attachments"""
        # Check token budget (prevent attaching if total exceeds reasonable limit)
        current_tokens = sum(attachment.get('token_count', 0) for attachment in self.current_attachments)
        new_tokens = file_info.get('token_count', 0)

        # Get current model context size
        from src.utils import MODEL_CONTEXT_SIZES
        from src.services.storage import SettingsManager
        settings = SettingsManager().get_settings()
        model = settings.get("model", "gpt-4o")
        context_size = MODEL_CONTEXT_SIZES.get(model, 8192)

        # Use 80% of context size as a reasonable limit for attachments
        max_tokens = int(context_size * 0.8)

        if current_tokens + new_tokens > max_tokens:
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                "Token Limit Warning",
                f"This file would add {new_tokens:,} tokens, bringing the total to {current_tokens + new_tokens:,} tokens. "
                f"This may exceed the model's capacity to process. Attach anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        # Check if file is already attached (by filename)
        for attachment in self.current_attachments:
            if attachment.get("file_name") == file_info.get("file_name"):
                # Ask to replace
                from PyQt6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self,
                    "Replace File",
                    f"A file named '{file_info.get('file_name')}' is already attached. Replace it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )

                if reply != QMessageBox.StandardButton.Yes:
                    return

                # Remove existing attachment
                self.current_attachments = [a for a in self.current_attachments if a.get("file_name") != file_info.get("file_name")]

        # Add to current attachments
        self.current_attachments.append(file_info)

        # Update UI
        self.update_attachments_ui()

        # Emit signal
        self.file_attached.emit(file_info.get('path', ''))

    def handle_file_error(self, error_message):
        """Handle file attachment errors"""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(
            self,
            "Attachment Error",
            error_message
        )

    """
    This fix replaces the QQueue reference with Python's collections.deque
    for the directory file processing queue.
    """

    def on_attach_directory(self):
        """Open directory dialog to attach all files in a directory with enhanced progress tracking"""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog
        import os
        from collections import deque  # Use Python's deque instead of QQueue

        directory_path = QFileDialog.getExistingDirectory(
            self,
            "Select Directory to Attach",
            "",
            QFileDialog.Option.ShowDirsOnly
        )

        if not directory_path:
            return

        # First, count files in the directory
        file_count = 0
        file_paths = []

        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)

                # Skip very large files immediately
                if os.path.getsize(file_path) > 20 * 1024 * 1024:  # 20MB
                    continue

                file_paths.append((file_path, os.path.relpath(file_path, directory_path)))
                file_count += 1

        # Confirm with user if directory contains many files
        if file_count > 10:
            reply = QMessageBox.question(
                self,
                "Confirm Directory Attachment",
                f"The selected directory contains {file_count} files under 20MB. Are you sure you want to attach all of them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

        # If no files found or too large
        if not file_paths:
            QMessageBox.warning(
                self,
                "No Files Found",
                "No suitable files were found in the directory (all files may be larger than 20MB)."
            )
            return

        # Show progress dialog
        progress_dialog = QProgressDialog("Processing files...", "Cancel", 0, file_count, self)
        progress_dialog.setWindowTitle("Attaching Directory")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.show()

        # Calculate token budget
        current_tokens = sum(attachment.get('token_count', 0) for attachment in self.current_attachments)

        # Get current model context size
        from src.utils import MODEL_CONTEXT_SIZES
        from src.services.storage import SettingsManager
        settings = SettingsManager().get_settings()
        model = settings.get("model", "gpt-4o")
        context_size = MODEL_CONTEXT_SIZES.get(model, 8192)

        # Use 80% of context size as a reasonable limit
        max_tokens = int(context_size * 0.8)

        # Create queue for processing - use deque instead of QQueue
        processing_queue = deque(file_paths)

        # Keep track of active threads
        self.directory_file_threads = []
        self.directory_files_processed = 0
        self.directory_files_total = file_count
        self.directory_progress_dialog = progress_dialog

        # Process files in batches (process 3 at a time)
        max_concurrent = 3

        # Function to start next file
        def process_next_file():
            if not processing_queue or progress_dialog.wasCanceled():
                # If we're done or canceled, check if we need to wait for threads
                if not self.directory_file_threads:
                    progress_dialog.setValue(self.directory_files_total)
                return

            # Get next file from queue - use popleft() for deque
            file_path, relative_path = processing_queue.popleft()

            # Start processing file
            from src.utils.file_utils import get_file_info_async
            thread, worker = get_file_info_async(
                file_path,
                model,
                on_complete=lambda file_info: handle_file_completed(file_info, relative_path),
                on_error=lambda error: handle_file_error(error, file_path),
                max_size_mb=10,
                relative_path=relative_path
            )

            # Store reference
            self.directory_file_threads.append((thread, worker))

            # Connect additional signals
            thread.finished.connect(lambda: handle_thread_finished(thread, worker))

        # Function to handle file completion
        def handle_file_completed(file_info, relative_path):
            nonlocal current_tokens

            # Update attachment name to use relative path
            file_info["file_name"] = relative_path

            # Check token budget
            new_tokens = file_info.get('token_count', 0)

            # Skip if would exceed token budget
            if current_tokens + new_tokens > max_tokens:
                return

            # Add file
            self.current_attachments.append(file_info)
            current_tokens += new_tokens

            # Update UI periodically (not on every file to avoid locking UI)
            self.directory_files_processed += 1
            if self.directory_files_processed % 5 == 0:
                self.update_attachments_ui()

        # Function to handle file error
        def handle_file_error(error, file_path):
            # Just log the error, don't show message box for each file
            print(f"Error processing {file_path}: {error}")

        # Function to handle thread completion
        def handle_thread_finished(thread, worker):
            # Remove from active threads
            if (thread, worker) in self.directory_file_threads:
                self.directory_file_threads.remove((thread, worker))

            # Update progress
            progress_dialog.setValue(self.directory_files_total - len(processing_queue))

            # Start next file
            process_next_file()

            # If all threads done and queue empty, finalize
            if not self.directory_file_threads and not processing_queue:
                # Final UI update
                self.update_attachments_ui()

                # Show summary
                QMessageBox.information(
                    self,
                    "Directory Attachment Complete",
                    f"Attached {self.directory_files_processed} files from directory with {current_tokens:,} total tokens."
                )

        # Start initial batch of files
        for _ in range(min(max_concurrent, len(processing_queue))):
            process_next_file()

    def update_attachments_ui(self):
        """Update the attachments UI with current files with improved token display"""
        # Clear current widgets
        while self.attachments_layout.count():
            item = self.attachments_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.current_attachments:
            self.attachments_container.setVisible(False)
            return

        self.attachments_container.setVisible(True)

        # Calculate total token count
        total_tokens = sum(attachment.get('token_count', 0) for attachment in self.current_attachments)

        # From context limit
        from src.utils import MODEL_CONTEXT_SIZES
        from src.services.storage import SettingsManager
        settings = SettingsManager().get_settings()
        model = settings.get("model", "gpt-4o")
        context_size = MODEL_CONTEXT_SIZES.get(model, 8192)

        # Add token usage summary
        token_percent = min(100, int((total_tokens / context_size) * 100))
        token_color = "#50FA7B"  # Green

        if token_percent > 80:
            token_color = "#FF5555"  # Red
        elif token_percent > 50:
            token_color = "#FFB86C"  # Orange

        label = QLabel(f"Attached Files: {len(self.current_attachments)} ({total_tokens:,} tokens, {token_percent}% of context)")
        label.setStyleSheet(f"color: {token_color};")
        self.attachments_layout.addWidget(label)

        # Add clear all button
        clear_btn = QPushButton("Clear All")
        clear_btn.setStyleSheet(
            f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
        )
        clear_btn.clicked.connect(self.clear_attachments)
        self.attachments_layout.addWidget(clear_btn)

        # Add spacer
        from PyQt6.QtWidgets import QSpacerItem, QSizePolicy
        spacer = QSpacerItem(20, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.attachments_layout.addItem(spacer)

        # Add file list label
        files_label = QLabel("Files:")
        files_label.setStyleSheet(f"color: {DARK_MODE['foreground']};")
        self.attachments_layout.addWidget(files_label)

        # Create scrolling area for files if many files
        if len(self.current_attachments) > 5:
            from PyQt6.QtWidgets import QScrollArea, QWidget, QVBoxLayout
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setMaximumHeight(150)

            scroll_content = QWidget()
            scroll_layout = QVBoxLayout(scroll_content)

            for file_info in self.current_attachments:
                file_widget = QWidget()
                file_layout = QHBoxLayout(file_widget)
                file_layout.setContentsMargins(0, 0, 0, 0)

                # Create file button with token count and size
                size_str = format_size(file_info.get('size', 0))
                token_str = f"{file_info.get('token_count', 0):,} tokens"
                file_button = QPushButton(f"{file_info['file_name']} ({size_str}, {token_str})")
                file_button.setStyleSheet(
                    f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
                )
                file_button.setToolTip(f"Click to preview: {file_info['file_name']}")
                file_button.clicked.connect(lambda checked=False, fi=file_info: self.preview_file(fi))

                # Add delete button
                delete_button = QPushButton("×")
                delete_button.setFixedSize(20, 20)
                delete_button.setToolTip(f"Remove {file_info['file_name']}")
                delete_button.setStyleSheet(
                    f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
                )
                delete_button.clicked.connect(lambda checked=False, fi=file_info: self.remove_attachment(fi))

                file_layout.addWidget(file_button)
                file_layout.addWidget(delete_button)

                scroll_layout.addWidget(file_widget)

            scroll_area.setWidget(scroll_content)
            self.attachments_layout.addWidget(scroll_area)
        else:
            # For small number of files, add them directly
            for file_info in self.current_attachments:
                from PyQt6.QtWidgets import QWidget
                file_widget = QWidget()
                file_layout = QHBoxLayout(file_widget)
                file_layout.setContentsMargins(0, 0, 0, 0)

                # Create file button with token count
                size_str = format_size(file_info.get('size', 0))
                token_str = f"{file_info.get('token_count', 0):,} tokens"
                file_button = QPushButton(f"{file_info['file_name']} ({size_str}, {token_str})")
                file_button.setStyleSheet(
                    f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
                )
                file_button.setToolTip(f"Click to preview: {file_info['file_name']}")
                file_button.clicked.connect(lambda checked=False, fi=file_info: self.preview_file(fi))

                # Add delete button
                delete_button = QPushButton("×")
                delete_button.setFixedSize(20, 20)
                delete_button.setToolTip(f"Remove {file_info['file_name']}")
                delete_button.setStyleSheet(
                    f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
                )
                delete_button.clicked.connect(lambda checked=False, fi=file_info: self.remove_attachment(fi))

                file_layout.addWidget(file_button)
                file_layout.addWidget(delete_button)

                self.attachments_layout.addWidget(file_widget)

        # Add stretch to push everything to the top
        self.attachments_layout.addStretch()

    def preview_file(self, file_info):
        """Show a preview dialog for the file with optimized display for large files"""
        # Content display
        from PyQt6.QtWidgets import QLabel, QTabWidget
        content_tab = QTabWidget()

        dialog = QDialog(self)
        dialog.setWindowTitle(f"File Preview: {file_info['file_name']}")
        dialog.setMinimumSize(700, 500)

        layout = QVBoxLayout(dialog)

        # File info label
        display_name = file_info.get('file_name', '')
        original_name = file_info.get('original_file_name', display_name.split('/')[-1])
        full_path = file_info.get('path', '')

        # Get token and character counts
        token_count = file_info.get('token_count', 0)
        char_count = len(file_info.get('content', ''))

        info_label = QLabel(
            f"File: {display_name}\n"
            f"Original name: {original_name}\n"
            f"Path: {full_path}\n"
            f"Size: {format_size(file_info.get('size', 0))}\n"
            f"Character count: {char_count:,}\n"
            f"Token count: {token_count:,} tokens"
        )
        layout.addWidget(info_label)

        # Get file extension for syntax highlighting
        file_ext = os.path.splitext(display_name)[1].lower() if '.' in display_name else ''

        # Create raw text view
        raw_text = QTextEdit()
        raw_text.setReadOnly(True)

        # For very large files, show a warning and truncated content
        content = file_info.get('content', '')
        content_length = len(content)
        max_display = 100_000  # Max chars to display

        if content_length > max_display:
            warning_label = QLabel(f"⚠️ This file is very large ({content_length:,} characters). Showing first {max_display:,} characters.")
            warning_label.setStyleSheet("color: #FFB86C;")  # Orange warning color
            layout.addWidget(warning_label)

            # Truncate content for display
            display_content = content[:max_display] + f"\n\n... [Truncated - {content_length - max_display:,} more characters] ..."
            raw_text.setPlainText(display_content)
        else:
            raw_text.setPlainText(content)

        # Style the text view
        raw_text.setStyleSheet(
            f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
        )

        # Add raw tab
        content_tab.addTab(raw_text, "Raw Text")

        # Add syntax highlighted tab for common code files
        code_extensions = ('.py', '.js', '.html', '.css', '.cpp', '.c', '.h', '.java', '.json', '.xml')
        if file_ext in code_extensions:
            try:
                from PyQt6.Qsci import QsciScintilla, QsciLexerPython, QsciLexerJavaScript, QsciLexerHTML, QsciLexerCSS, QsciLexerCPP, QsciLexerJava, QsciLexerJSON, QsciLexerXML

                # Create syntax highlighting editor
                editor = QsciScintilla()
                editor.setReadOnly(True)

                # Set up lexer based on file type
                lexer = None
                if file_ext == '.py':
                    lexer = QsciLexerPython()
                elif file_ext == '.js':
                    lexer = QsciLexerJavaScript()
                elif file_ext == '.html':
                    lexer = QsciLexerHTML()
                elif file_ext == '.css':
                    lexer = QsciLexerCSS()
                elif file_ext in ('.cpp', '.c', '.h'):
                    lexer = QsciLexerCPP()
                elif file_ext == '.java':
                    lexer = QsciLexerJava()
                elif file_ext == '.json':
                    lexer = QsciLexerJSON()
                elif file_ext == '.xml':
                    lexer = QsciLexerXML()

                if lexer:
                    # Configure lexer for dark mode
                    lexer.setDefaultPaper(QColor(DARK_MODE['background']))
                    lexer.setDefaultColor(QColor(DARK_MODE['foreground']))
                    editor.setLexer(lexer)

                    # Set the text with possible truncation
                    if content_length > max_display:
                        display_content = content[:max_display] + f"\n\n... [Truncated - {content_length - max_display:,} more characters] ..."
                        editor.setText(display_content)
                    else:
                        editor.setText(content)

                    # Add to tabs
                    content_tab.addTab(editor, "Highlighted")
            except ImportError:
                # QScintilla not available
                pass

        # Add token visualization tab
        try:
            token_view = QTextEdit()
            token_view.setReadOnly(True)

            # Get encoding for token counting
            try:
                from src.services.storage import SettingsManager
                settings = SettingsManager().get_settings()
                model = settings.get("model", "gpt-4o")

                import tiktoken
                try:
                    encoding = tiktoken.encoding_for_model(model)
                except KeyError:
                    encoding = tiktoken.get_encoding("cl100k_base")

                # Generate token visualization
                token_html = "<style>span.token{background:#44475A;border-radius:3px;margin:2px;padding:2px;}</style>"

                # Truncate content for token visualization
                token_max = 2000  # Maximum number of tokens to visualize
                if content_length > 10000:
                    # For very large files, just show token counts
                    tokens = encoding.encode(content[:50000])  # Sample first 50K chars
                    token_html += f"<p>This file contains {token_count:,} tokens.</p>"
                    token_html += f"<p>Sample token sizes:</p>"
                    token_html += f"<p>First 1000 chars: {len(encoding.encode(content[:1000])):,} tokens</p>"
                    token_html += f"<p>First 10000 chars: {len(encoding.encode(content[:10000])):,} tokens</p>"

                    # Show first 100 tokens
                    tokens = tokens[:100]
                    token_html += "<p>First 100 tokens:</p><p>"
                    for token in tokens:
                        decoded = encoding.decode([token])
                        # Replace special chars for HTML display
                        decoded = decoded.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "↵").replace(" ", "·")
                        token_html += f'<span class="token" title="Token ID: {token}">{decoded}</span>'
                    token_html += "</p>"
                else:
                    # For smaller files, show token visualization
                    tokens = encoding.encode(content)
                    if len(tokens) > token_max:
                        token_html += f"<p>Showing first {token_max:,} of {len(tokens):,} tokens:</p><p>"
                        tokens = tokens[:token_max]
                    else:
                        token_html += f"<p>Total tokens: {len(tokens):,}</p><p>"

                    for token in tokens:
                        decoded = encoding.decode([token])
                        # Replace special chars for HTML display
                        decoded = decoded.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "↵").replace(" ", "·")
                        token_html += f'<span class="token" title="Token ID: {token}">{decoded}</span>'
                    token_html += "</p>"

                token_view.setHtml(token_html)
                token_view.setStyleSheet(
                    f"background-color: {DARK_MODE['highlight']}; color: {DARK_MODE['foreground']};"
                )
                content_tab.addTab(token_view, "Token View")
            except Exception as e:
                print(f"Error creating token visualization: {e}")
        except Exception as e:
            print(f"Error creating token tab: {e}")

        layout.addWidget(content_tab)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.setStyleSheet(f"background-color: {DARK_MODE['background']}; color: {DARK_MODE['foreground']};")
        dialog.exec()