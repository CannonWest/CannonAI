"""
Conversation UI components for the OpenAI Chat application.
"""

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
        """Render reasoning steps for an assistant message with improved debugging"""
        # Check for reasoning tokens or reasoning steps
        reasoning_tokens = 0
        if node.token_usage and "completion_tokens_details" in node.token_usage:
            details = node.token_usage["completion_tokens_details"]
            reasoning_tokens = details.get("reasoning_tokens", 0)

        # Print debug info about this node and its reasoning data
        print(f"DEBUG: Rendering reasoning for node {node.id}, role: {node.role}")

        # Try to extract reasoning steps from different attributes
        node_reasoning = None

        # First try the standard attribute
        if hasattr(node, 'reasoning_steps'):
            node_reasoning = node.reasoning_steps
            print(f"DEBUG: Found reasoning_steps attribute with {len(node_reasoning) if node_reasoning else 0} steps")

        # If no reasoning after all attempts, return empty string
        if (not node_reasoning or len(node_reasoning) == 0) and reasoning_tokens <= 0:
            print("DEBUG: No reasoning steps found for this node")
            return ""

        html_parts = []
        html_parts.append(f'<div style="color: {DARK_MODE["accent"]}; margin-top: 10px;">💭 Chain of Thought:</div>')

        # Use stored reasoning steps if available
        if node_reasoning and isinstance(node_reasoning, list) and len(node_reasoning) > 0:
            html_parts.append('<ul style="margin-top: 5px; margin-bottom: 5px;">')
            for step in node_reasoning:
                if isinstance(step, dict):
                    step_name = step.get("name", "Reasoning Step")
                    step_content = step.get("content", "")
                    # Skip empty content
                    if not step_content or len(step_content.strip()) == 0:
                        continue
                    # Trim very long content for display
                    if len(step_content) > 500:
                        step_content = step_content[:497] + "..."
                    html_parts.append(f'<li><b>{step_name}:</b> {step_content}</li>')
            html_parts.append('</ul>')

        # If we have no steps but reasoning tokens were used, show that
        if (not node_reasoning or len(node_reasoning) == 0) and reasoning_tokens > 0:
            html_parts.append(f'<div>• Model performed reasoning ({reasoning_tokens} tokens)</div>')

            # Add extra info for o3-mini model (which might not expose steps)
            if 'model' in node.model_info and 'o3-mini' in node.model_info['model']:
                html_parts.append(f'<div>• Note: o3-mini model may not expose detailed reasoning steps</div>')

        return "".join(html_parts)

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
        """Update the chat display during streaming for efficiency"""
        try:
            # Safety check for extremely large chunks that could cause memory issues
            if len(chunk) > 10000:  # 10KB limit for a single chunk
                chunk = chunk[:10000] + "... [CHUNK TRUNCATED - TOO LARGE]"
                print("WARNING: Chunk size exceeded limits - truncated")

            # Set streaming mode flag
            self._is_streaming = True
            self._ui_update_pending = True

            # If this is the first chunk and we have a loading indicator active, remove it completely
            if not hasattr(self, '_streaming_started'):
                self._streaming_started = True

                # Remove any loading indicator text if present
                if hasattr(self, '_has_loading_text') and self._has_loading_text:
                    try:
                        cursor = self.chat_display.textCursor()
                        cursor.movePosition(QTextCursor.MoveOperation.End)
                        cursor.movePosition(QTextCursor.MoveOperation.Up, QTextCursor.MoveMode.KeepAnchor, 1)
                        cursor.removeSelectedText()
                        self._has_loading_text = False
                    except Exception as cursor_error:
                        print(f"Error removing loading text: {str(cursor_error)}")
                        # Just continue if cursor operations fail

            try:
                # Get cursor position at the end
                cursor = self.chat_display.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.chat_display.setTextCursor(cursor)

                # Insert the chunk as plain text
                self.chat_display.insertPlainText(chunk)
            except Exception as text_error:
                print(f"Error inserting text: {str(text_error)}")
                # Try an alternative method if the first fails
                try:
                    self.chat_display.append(chunk)
                except Exception:
                    pass  # Silently fail if both methods fail

            # Only process events every 20 chunks for better performance
            if not hasattr(self, '_chunk_counter'):
                self._chunk_counter = 0
            self._chunk_counter += 1

            # Reduce event processing frequency to prevent overload
            if self._chunk_counter % 50 == 0:  # Increased from 20 to 50
                try:
                    from PyQt6.QtCore import QCoreApplication
                    QCoreApplication.processEvents()
                except Exception as event_error:
                    print(f"Error processing events: {str(event_error)}")

        except Exception as e:
            print(f"Critical error in update_chat_streaming: {str(e)}")
            # Reset streaming state to avoid being stuck
            self._is_streaming = False

    def complete_streaming_update(self):
        """Perform a full UI update after streaming is complete"""
        # Reset streaming flag first
        self._is_streaming = False

        # Ensure any remaining buffer is flushed completely
        if hasattr(self, '_chunk_buffer') and self._chunk_buffer:
            try:
                # Force flush any remaining buffer
                if self.conversation_tree and self.conversation_tree.current_node:
                    current_node = self.conversation_tree.current_node
                    conn = None
                    try:
                        # Get database connection through db_manager
                        from src.models.db_manager import DatabaseManager
                        db_manager = DatabaseManager()
                        conn = db_manager.get_connection()
                        cursor = conn.cursor()

                        # Ensure the database content is complete
                        cursor.execute(
                            'SELECT content FROM messages WHERE id = ?',
                            (current_node.id,)
                        )
                        result = cursor.fetchone()
                        if result:
                            full_content = result['content']
                            # Update in-memory object
                            current_node.content = full_content
                        conn.commit()
                    except Exception as e:
                        print(f"Error in buffer flush during completion: {str(e)}")
                        if conn:
                            conn.rollback()
                    finally:
                        if conn:
                            conn.close()

                    # Clear buffer state
                    self._chunk_buffer = ""
                    self._chunk_counter = 0
            except Exception as e:
                print(f"Error finalizing streaming: {str(e)}")

        # Force a full chat display update to ensure content is complete
        self.update_chat_display()

        # Only update if we have pending updates
        if self._ui_update_pending:
            # Ensure we wait a short moment to allow any in-progress
            # operations to complete first (important for stability)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(200, self._do_complete_update)  # Increased delay

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

            # Start loading indicator
            try:
                self.start_loading_indicator()
            except Exception as indicator_error:
                print(f"Error starting loading indicator: {str(indicator_error)}")
                # Continue anyway

            # Emit signal to send message
            try:
                self.send_message.emit(message)
            except Exception as emit_error:
                print(f"Error emitting send message signal: {str(emit_error)}")
                # Try to recover from emission error
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
        """Update token usage and model info displays"""
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
            else:
                self.model_label.setText("Model: -")

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

    def _update_loading_indicator(self):
        """Update the loading indicator text"""
        if not self._loading_active:
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
            self.chat_display.append("")
            self.chat_display.append(loading_text)
            self._has_loading_text = True

        # Reset text color to normal
        self.chat_display.setTextColor(QColor(DARK_MODE["foreground"]))

        # Make sure the loading text is visible
        self.chat_display.ensureCursorVisible()

        # Debug output
        if self._loading_state == 0:  # Log only occasionally
            self.log_loading_state()

    def start_loading_indicator(self):
        """Start the loading indicator"""
        self._loading_state = 0
        self._loading_active = True
        self._has_loading_text = False
        self._streaming_started = False  # Reset streaming flag
        self._loading_timer.start()
        self._update_loading_indicator()  # Show initial state immediatel

    def stop_loading_indicator(self):
        """Stop the loading indicator and remove it from display"""
        if not self._loading_active:
            return

        self._loading_timer.stop()
        self._loading_active = False

        # Remove the loading text if it exists and streaming hasn't started yet
        if hasattr(self, '_has_loading_text') and self._has_loading_text and not getattr(self, '_streaming_started', False):
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.movePosition(QTextCursor.MoveOperation.Up, QTextCursor.MoveMode.KeepAnchor, 1)
            cursor.removeSelectedText()
            self._has_loading_text = False
