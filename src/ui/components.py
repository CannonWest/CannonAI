"""
Reusable UI components for the OpenAI Chat application.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Callable
from functools import partial

from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFormLayout, QComboBox, QScrollArea, QGroupBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QLineEdit, QGridLayout, QMessageBox, QDialog, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from src.utils import (
    DARK_MODE, MODEL_CONTEXT_SIZES, MODEL_OUTPUT_LIMITS,
    MODELS, MODEL_SNAPSHOTS, REASONING_MODELS, REASONING_EFFORT,
    RESPONSE_FORMATS, DEFAULT_PARAMS
)
from src.models import MessageNode, ConversationTree


class ConversationTreeWidget(QTreeWidget):
    """
    Widget to display and navigate conversation branches
    """
    node_selected = pyqtSignal(str)  # Signal emitted when a node is selected

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Conversation"])
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)

        # Connect signals
        self.itemClicked.connect(self.on_item_clicked)

        # Styling
        self.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {DARK_MODE['highlight']};
                color: {DARK_MODE['foreground']};
                border-radius: 4px;
                border: 1px solid {DARK_MODE['accent']};
            }}
            QTreeWidget::item:selected {{
                background-color: {DARK_MODE['accent']};
            }}
        """)

    def update_tree(self, conversation_tree: ConversationTree):
        """Update the tree view with the conversation structure"""
        self.clear()

        if not conversation_tree:
            return

        # Get the current branch for highlighting
        current_branch = conversation_tree.get_current_branch()
        current_ids = {node.id for node in current_branch}

        # Create items for the tree
        root_item = self.create_items_recursive(conversation_tree.root, current_ids)
        self.addTopLevelItem(root_item)

        # Expand all items
        self.expandAll()

    def create_items_recursive(self, node: MessageNode, current_ids: set) -> QTreeWidgetItem:
        """Recursively create QTreeWidgetItems for the conversation tree"""
        if node.role == "system":
            label = "System"
            icon = "🔧"
        elif node.role == "user":
            label = "User"
            icon = "👤"
        elif node.role == "assistant":
            label = "Assistant"
            icon = "🤖"
            # Add model info if available
            if node.model_info and "model" in node.model_info:
                label += f" ({node.model_info['model']})"
        else:
            label = node.role
            icon = "📝"

        # Create item for this node
        item = QTreeWidgetItem([f"{icon} {label}"])
        item.setData(0, Qt.ItemDataRole.UserRole, node.id)

        # Highlight if this node is in the current branch
        if node.id in current_ids:
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)

            # Set background color for the active node
            if node.id == current_ids and current_ids:
                item.setBackground(0, QColor(DARK_MODE['accent']))

        # Add tooltip with message content preview
        content_preview = node.content
        if len(content_preview) > 100:
            content_preview = content_preview[:97] + "..."
        item.setToolTip(0, content_preview)

        # Recursively add children
        for child in node.children:
            child_item = self.create_items_recursive(child, current_ids)
            item.addChild(child_item)

        return item

    def on_item_clicked(self, item, column):
        """Handle clicking on a node in the tree"""
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        if node_id:
            self.node_selected.emit(node_id)


class BranchNavBar(QWidget):
    """
    Navigation bar showing the current branch path
    Allows jumping to any point in the current conversation branch
    """
    node_selected = pyqtSignal(str)  # Signal emitted when a node is selected

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 2, 5, 2)
        self.layout.setSpacing(5)

        self.nodes = []  # List of (node_id, button) tuples

        # Styling
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {DARK_MODE['highlight']};
                color: {DARK_MODE['foreground']};
                border-radius: 4px;
                padding: 4px 8px;
                border: 1px solid {DARK_MODE['accent']};
            }}
            QPushButton:hover {{
                background-color: {DARK_MODE['accent']};
            }}
        """)

    def update_branch(self, branch: List[MessageNode]):
        """Update the navigation bar with the current branch"""
        # Clear existing buttons
        self.clear()

        # Create new buttons for each node in the branch
        for i, node in enumerate(branch):
            if node.role == "system":
                continue  # Skip system message

            if node.role == "user":
                icon = "👤"
            elif node.role == "assistant":
                icon = "🤖"
            else:
                icon = "📝"

            # Create preview text from content
            content = node.content.strip()
            if len(content) > 20:
                content = content[:17] + "..."

            # Create button
            button = QPushButton(f"{icon} {content}")
            button.setToolTip(node.content)

            # Style the last (current) node differently
            if i == len(branch) - 1:
                button.setStyleSheet(f"""
                    background-color: {DARK_MODE['accent']};
                    font-weight: bold;
                """)

            # Connect signal using partial to capture node_id
            button.clicked.connect(lambda checked, node_id=node.id: self.node_selected.emit(node_id))

            # Add to layout
            self.layout.addWidget(button)
            self.nodes.append((node.id, button))

            # Add separator if not the last item
            if i < len(branch) - 1:
                separator = QLabel("→")
                separator.setStyleSheet(f"color: {DARK_MODE['foreground']};")
                self.layout.addWidget(separator)

        # Add stretch at the end
        self.layout.addStretch()

    def clear(self):
        """Clear all buttons from the navigation bar"""
        self.nodes = []

        # Remove all widgets from layout
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class SettingsDialog(QDialog):
    """Dialog for configuring OpenAI API settings"""

    def __init__(self, current_settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chat Settings")
        self.setMinimumWidth(600)
        self.setMinimumHeight(700)
        self.current_settings = current_settings.copy()

        # Main layout
        layout = QVBoxLayout(self)

        # Create a scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        # Create a widget for the scroll area
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll.setWidget(scroll_content)

        # Model selection
        model_group = QGroupBox("Model Selection")
        model_layout = QFormLayout()

        # Create tabs for model selection
        self.model_tabs = QTabWidget()

        # Main models tab
        main_models_widget = QWidget()
        main_models_layout = QVBoxLayout(main_models_widget)
        self.model_combo = QComboBox()

        # Add models from the MODELS dictionary
        for name in MODELS:
            self.model_combo.addItem(name)

        # Find current model in the list or default to first item
        current_model = current_settings.get("model", "gpt-4o")
        model_found = False

        for i, (name, model_id) in enumerate(MODELS.items()):
            if model_id == current_model:
                self.model_combo.setCurrentIndex(i)
                model_found = True
                break

        main_models_layout.addWidget(self.model_combo)
        self.model_tabs.addTab(main_models_widget, "Models")

        # Dated snapshots tab
        snapshot_widget = QWidget()
        snapshot_layout = QVBoxLayout(snapshot_widget)
        self.snapshot_combo = QComboBox()

        # Add models from the MODEL_SNAPSHOTS dictionary
        for name in MODEL_SNAPSHOTS:
            self.snapshot_combo.addItem(name)

        # If model wasn't found in main models, check snapshots
        if not model_found:
            for i, (name, model_id) in enumerate(MODEL_SNAPSHOTS.items()):
                if model_id == current_model:
                    self.snapshot_combo.setCurrentIndex(i)
                    self.model_tabs.setCurrentIndex(1)  # Switch to snapshots tab
                    break

        snapshot_layout.addWidget(self.snapshot_combo)
        self.model_tabs.addTab(snapshot_widget, "Dated Snapshots")

        # Connect model selection to update UI based on model
        self.model_combo.currentIndexChanged.connect(self.update_ui_for_model)
        self.snapshot_combo.currentIndexChanged.connect(self.update_ui_for_model)
        self.model_tabs.currentChanged.connect(self.update_ui_for_model)

        model_layout.addRow("Model:", self.model_tabs)

        # Model info display
        self.model_info = QLabel()
        self.model_info.setWordWrap(True)
        self.model_info.setStyleSheet("color: #8BE9FD; font-style: italic;")
        model_layout.addRow("", self.model_info)

        model_group.setLayout(model_layout)
        scroll_layout.addWidget(model_group)

        # Generation parameters
        self.gen_group = QGroupBox("Generation Parameters")
        gen_layout = QFormLayout()

        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(current_settings.get("temperature", 0.7))
        # Disable wheel events to prevent accidental changes while scrolling
        self.temperature.wheelEvent = lambda event: None
        gen_layout.addRow("Temperature:", self.temperature)

        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(1, 100000)  # Using a high max since o1 models support up to 100k tokens
        self.max_tokens.setValue(current_settings.get("max_completion_tokens", 1024))
        # Disable wheel events
        self.max_tokens.wheelEvent = lambda event: None
        gen_layout.addRow("Max Completion Tokens:", self.max_tokens)

        self.top_p = QDoubleSpinBox()
        self.top_p.setRange(0.0, 1.0)
        self.top_p.setSingleStep(0.05)
        self.top_p.setValue(current_settings.get("top_p", 1.0))
        # Disable wheel events
        self.top_p.wheelEvent = lambda event: None
        gen_layout.addRow("Top P:", self.top_p)

        self.freq_penalty = QDoubleSpinBox()
        self.freq_penalty.setRange(-2.0, 2.0)
        self.freq_penalty.setSingleStep(0.1)
        self.freq_penalty.setValue(current_settings.get("frequency_penalty", 0.0))
        # Disable wheel events
        self.freq_penalty.wheelEvent = lambda event: None
        gen_layout.addRow("Frequency Penalty:", self.freq_penalty)

        self.pres_penalty = QDoubleSpinBox()
        self.pres_penalty.setRange(-2.0, 2.0)
        self.pres_penalty.setSingleStep(0.1)
        self.pres_penalty.setValue(current_settings.get("presence_penalty", 0.0))
        # Disable wheel events
        self.pres_penalty.wheelEvent = lambda event: None
        gen_layout.addRow("Presence Penalty:", self.pres_penalty)

        # Response Format
        response_format_layout = QHBoxLayout()
        self.response_format_combo = QComboBox()
        for format_type in RESPONSE_FORMATS:
            self.response_format_combo.addItem(format_type)

        # Set current response format
        current_format = current_settings.get("response_format", {"type": "text"})
        if isinstance(current_format, dict) and "type" in current_format:
            format_type = current_format["type"]
            try:
                format_index = RESPONSE_FORMATS.index(format_type)
                self.response_format_combo.setCurrentIndex(format_index)
            except ValueError:
                self.response_format_combo.setCurrentIndex(0)

        response_format_layout.addWidget(self.response_format_combo)

        # Explanation for JSON mode
        json_mode_explanation = QPushButton("?")
        json_mode_explanation.setToolTip("JSON mode ensures the message the model generates is valid JSON.")
        json_mode_explanation.setFixedWidth(25)
        json_mode_explanation.clicked.connect(lambda: QMessageBox.information(
            self,
            "JSON Mode",
            "When set to 'json_object', the response will be formatted as valid JSON. "
            "This is useful when you need structured data from the model."
        ))
        response_format_layout.addWidget(json_mode_explanation)
        gen_layout.addRow("Response Format:", response_format_layout)

        # Seed for deterministic outputs
        seed_layout = QHBoxLayout()
        self.seed_input = QSpinBox()
        self.seed_input.setRange(-1, 2147483647)  # Maximum 32-bit integer
        self.seed_input.setSpecialValueText("None")  # Display "None" for -1
        self.seed_input.wheelEvent = lambda event: None  # Disable wheel events

        # Set current seed
        current_seed = current_settings.get("seed")
        if current_seed is None:
            self.seed_input.setValue(-1)
        else:
            self.seed_input.setValue(current_seed)

        seed_layout.addWidget(self.seed_input)

        # Explanation for seed
        seed_explanation = QPushButton("?")
        seed_explanation.setToolTip("Setting a seed helps generate deterministic responses.")
        seed_explanation.setFixedWidth(25)
        seed_explanation.clicked.connect(lambda: QMessageBox.information(
            self,
            "Seed",
            "Setting a specific seed value helps generate more deterministic responses. "
            "Using the same seed with the same parameters should return similar results."
        ))
        seed_layout.addWidget(seed_explanation)
        gen_layout.addRow("Seed (for deterministic output):", seed_layout)

        # Reasoning Effort (for o1 and o3 models)
        self.reasoning_effort_container = QWidget()
        reasoning_layout = QHBoxLayout(self.reasoning_effort_container)
        reasoning_layout.setContentsMargins(0, 0, 0, 0)

        self.reasoning_effort_combo = QComboBox()
        for effort in REASONING_EFFORT:
            self.reasoning_effort_combo.addItem(effort)

        current_effort = current_settings.get("reasoning_effort", "medium")
        try:
            effort_index = REASONING_EFFORT.index(current_effort)
            self.reasoning_effort_combo.setCurrentIndex(effort_index)
        except ValueError:
            self.reasoning_effort_combo.setCurrentIndex(1)  # Default to "medium"

        reasoning_layout.addWidget(self.reasoning_effort_combo)

        # Explanation for reasoning effort
        reason_explanation = QPushButton("?")
        reason_explanation.setToolTip("Only for o1 and o3-mini models. Controls how much effort the model spends on reasoning.")
        reason_explanation.setFixedWidth(25)
        reason_explanation.clicked.connect(lambda: QMessageBox.information(
            self,
            "Reasoning Effort",
            "Only applicable to reasoning models (o1, o1-mini, o3-mini). "
            "Constrains effort on reasoning. Lower values result in faster responses but less reasoning."
        ))
        reasoning_layout.addWidget(reason_explanation)

        gen_layout.addRow("Reasoning Effort:", self.reasoning_effort_container)

        # Streaming option
        self.stream_checkbox = QCheckBox()
        self.stream_checkbox.setChecked(current_settings.get("stream", True))
        gen_layout.addRow("Stream Responses:", self.stream_checkbox)

        # Store option
        store_layout = QHBoxLayout()
        self.store_checkbox = QCheckBox()
        self.store_checkbox.setChecked(current_settings.get("store", False))
        store_layout.addWidget(self.store_checkbox)

        # Explanation for store
        store_explanation = QPushButton("?")
        store_explanation.setToolTip("Store chat completions for later retrieval via API")
        store_explanation.setFixedWidth(25)
        store_explanation.clicked.connect(lambda: QMessageBox.information(
            self,
            "Store Completions",
            "When enabled, the chat completions will be stored on OpenAI's servers for 30 days "
            "and can be retrieved later via the API."
        ))
        store_layout.addWidget(store_explanation)
        gen_layout.addRow("Store Completions:", store_layout)

        # Service tier
        self.service_tier_combo = QComboBox()
        self.service_tier_combo.addItems(["auto", "default"])
        current_tier = current_settings.get("service_tier", "auto")
        self.service_tier_combo.setCurrentText(current_tier)
        gen_layout.addRow("Service Tier:", self.service_tier_combo)

        self.gen_group.setLayout(gen_layout)
        scroll_layout.addWidget(self.gen_group)

        # Advanced options
        adv_group = QGroupBox("Advanced Options")
        adv_layout = QFormLayout()

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setText(current_settings.get("api_key", ""))
        adv_layout.addRow("API Key:", self.api_key_input)

        self.api_base_input = QLineEdit()
        self.api_base_input.setText(current_settings.get("api_base", ""))
        adv_layout.addRow("API Base URL:", self.api_base_input)

        # Add metadata options
        self.metadata_layout = QGridLayout()
        self.metadata_keys = []
        self.metadata_values = []

        # Get existing metadata
        current_metadata = current_settings.get("metadata", {})

        # Add metadata fields
        for i in range(4):  # Allow 4 metadata key-value pairs in the UI
            key_input = QLineEdit()
            value_input = QLineEdit()

            # Set existing values if available
            if i < len(current_metadata):
                key, value = list(current_metadata.items())[i]
                key_input.setText(key)
                value_input.setText(value)

            self.metadata_keys.append(key_input)
            self.metadata_values.append(value_input)

            self.metadata_layout.addWidget(QLabel(f"Key {i + 1}:"), i, 0)
            self.metadata_layout.addWidget(key_input, i, 1)
            self.metadata_layout.addWidget(QLabel(f"Value {i + 1}:"), i, 2)
            self.metadata_layout.addWidget(value_input, i, 3)

        metadata_group = QGroupBox("Metadata")
        metadata_group.setLayout(self.metadata_layout)
        adv_layout.addRow(metadata_group)

        adv_group.setLayout(adv_layout)
        scroll_layout.addWidget(adv_group)

        # Buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(save_button)
        layout.addLayout(button_layout)

        # Initialize UI based on current model
        self.update_ui_for_model()

    def update_ui_for_model(self):
        """Update UI elements based on selected model"""
        # Determine which model is selected based on active tab
        model_id = ""
        if self.model_tabs.currentIndex() == 0:
            # Main models tab
            model_name = self.model_combo.currentText()
            model_id = MODELS.get(model_name, "")
        else:
            # Dated snapshots tab
            model_name = self.snapshot_combo.currentText()
            model_id = MODEL_SNAPSHOTS.get(model_name, "")

        # Update model info
        context_size = MODEL_CONTEXT_SIZES.get(model_id, 0)
        output_limit = MODEL_OUTPUT_LIMITS.get(model_id, 0)

        # Set max tokens based on model
        self.max_tokens.setMaximum(output_limit)

        model_info_text = f"Context window: {context_size:,} tokens | Max output: {output_limit:,} tokens"
        self.model_info.setText(model_info_text)

        # Enable/disable reasoning effort based on model
        is_reasoning_model = model_id in REASONING_MODELS
        self.reasoning_effort_container.setVisible(is_reasoning_model)

        # Set hint on max tokens spinbox
        self.max_tokens.setToolTip(f"Maximum value for this model: {output_limit:,}")

        # Update window title with model name for clarity
        self.setWindowTitle(f"Chat Settings - {model_name}")

    def get_settings(self) -> Dict[str, Any]:
        """Get the current settings from the dialog"""
        # Get model ID based on which tab is active
        model_id = ""
        if self.model_tabs.currentIndex() == 0:
            # Main models tab
            model_name = self.model_combo.currentText()
            model_id = MODELS.get(model_name, "")
        else:
            # Dated snapshots tab
            model_name = self.snapshot_combo.currentText()
            model_id = MODEL_SNAPSHOTS.get(model_name, "")

        # Get response format
        response_format_type = self.response_format_combo.currentText()
        response_format = {"type": response_format_type}

        # Handle seed value
        seed_value = self.seed_input.value()
        if seed_value == -1:
            seed_value = None

        # Get metadata
        metadata = {}
        for i in range(len(self.metadata_keys)):
            key = self.metadata_keys[i].text().strip()
            value = self.metadata_values[i].text().strip()
            if key and value:
                metadata[key] = value

        # Build settings dict with conditional parameters
        settings = {
            "model": model_id,
            "temperature": self.temperature.value(),
            "max_completion_tokens": self.max_tokens.value(),
            "top_p": self.top_p.value(),
            "frequency_penalty": self.freq_penalty.value(),
            "presence_penalty": self.pres_penalty.value(),
            "response_format": response_format,
            "stream": self.stream_checkbox.isChecked(),
            "store": self.store_checkbox.isChecked(),
            "seed": seed_value,
            "service_tier": self.service_tier_combo.currentText(),
            "metadata": metadata,
            "api_key": self.api_key_input.text(),
            "api_base": self.api_base_input.text()
        }

        # Only include reasoning_effort for appropriate models
        if model_id in REASONING_MODELS:
            settings["reasoning_effort"] = self.reasoning_effort_combo.currentText()

        return settings


# First, let's add a SearchDialog component to src/ui/components.py

class SearchDialog(QDialog):
    """Dialog for searching through conversations"""

    message_selected = pyqtSignal(str)  # Signal emitted when a message is selected from search results

    def __init__(self, conversation_manager, parent=None):
        super().__init__(parent)
        self.conversation_manager = conversation_manager
        self.setWindowTitle("Search Conversations")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        # Main layout
        layout = QVBoxLayout(self)

        # Search input
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term...")
        self.search_input.returnPressed.connect(self.perform_search)
        search_button = QPushButton("Search")
        search_button.clicked.connect(self.perform_search)

        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(search_button, 0)
        layout.addLayout(search_layout)

        # Filter options
        filter_layout = QHBoxLayout()

        self.current_conversation_only = QCheckBox("Current conversation only")
        filter_layout.addWidget(self.current_conversation_only)

        self.filter_by_role = QComboBox()
        self.filter_by_role.addItem("All messages")
        self.filter_by_role.addItem("User messages")
        self.filter_by_role.addItem("Assistant messages")
        self.filter_by_role.addItem("System messages")
        filter_layout.addWidget(QLabel("Filter by:"))
        filter_layout.addWidget(self.filter_by_role)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Results list
        self.results_list = QTreeWidget()
        self.results_list.setHeaderLabels(["Conversation", "Message", "Role", "Date"])
        self.results_list.setColumnWidth(0, 150)  # Conversation name
        self.results_list.setColumnWidth(1, 250)  # Message preview
        self.results_list.setColumnWidth(2, 80)  # Role
        self.results_list.setColumnWidth(3, 120)  # Date
        self.results_list.itemDoubleClicked.connect(self.on_result_selected)
        layout.addWidget(self.results_list, 1)

        # Status bar
        self.status_label = QLabel("Enter a search term to begin")
        layout.addWidget(self.status_label)

        # Buttons
        button_layout = QHBoxLayout()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

        # Apply dark mode styling
        self.apply_style()

    def apply_style(self):
        """Apply dark mode styling to the dialog"""
        self.setStyleSheet(f"""
            QDialog {{ background-color: {DARK_MODE["background"]}; color: {DARK_MODE["foreground"]}; }}
            QLineEdit {{ 
                background-color: {DARK_MODE["highlight"]}; 
                color: {DARK_MODE["foreground"]}; 
                padding: 6px; 
                border-radius: 4px;
                border: 1px solid {DARK_MODE["accent"]};
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
            QTreeWidget {{ 
                background-color: {DARK_MODE["highlight"]}; 
                color: {DARK_MODE["foreground"]}; 
                border-radius: 4px;
                border: 1px solid {DARK_MODE["accent"]};
            }}
            QLabel {{ color: {DARK_MODE["foreground"]}; }}
            QComboBox, QCheckBox {{ 
                background-color: {DARK_MODE["highlight"]}; 
                color: {DARK_MODE["foreground"]}; 
            }}
        """)

    def perform_search(self):
        """Search through conversations based on the input term"""
        search_term = self.search_input.text().strip().lower()
        if not search_term:
            self.status_label.setText("Please enter a search term")
            return

        self.results_list.clear()

        # Determine which conversations to search
        if self.current_conversation_only.isChecked():
            conversations = [self.conversation_manager.active_conversation]
        else:
            conversations = list(self.conversation_manager.conversations.values())

        # Determine role filter
        role_filter = None
        role_index = self.filter_by_role.currentIndex()
        if role_index == 1:
            role_filter = "user"
        elif role_index == 2:
            role_filter = "assistant"
        elif role_index == 3:
            role_filter = "system"

        # Search for matches
        total_results = 0
        for conversation in conversations:
            if conversation is None:
                continue

            matches = self.search_conversation(conversation, search_term, role_filter)
            total_results += len(matches)

            if matches:
                conversation_item = QTreeWidgetItem([conversation.name, "", "", ""])
                conversation_item.setExpanded(True)
                self.results_list.addTopLevelItem(conversation_item)

                for node, path_to_root in matches:
                    # Create preview text (truncated message content)
                    preview = node.content
                    if len(preview) > 50:
                        preview = preview[:47] + "..."

                    # Format the date
                    date_str = ""
                    if hasattr(node, 'timestamp') and node.timestamp:
                        try:
                            date_obj = datetime.fromisoformat(node.timestamp)
                            date_str = date_obj.strftime("%Y-%m-%d %H:%M")
                        except (ValueError, TypeError):
                            pass

                    # Create list item
                    item = QTreeWidgetItem([
                        "",  # Conversation name (already in parent)
                        preview,  # Message preview
                        node.role,  # Role
                        date_str  # Date
                    ])

                    # Store node ID and conversation ID as data
                    item.setData(0, Qt.ItemDataRole.UserRole, node.id)
                    item.setData(1, Qt.ItemDataRole.UserRole, conversation.id)

                    # Store full path to node for navigation
                    item.setData(2, Qt.ItemDataRole.UserRole, [n.id for n in path_to_root])

                    # Add to tree
                    conversation_item.addChild(item)

        # Update status
        if total_results == 0:
            self.status_label.setText(f"No results found for '{search_term}'")
        else:
            self.status_label.setText(f"Found {total_results} result{'s' if total_results != 1 else ''} for '{search_term}'")

    def search_conversation(self, conversation, search_term, role_filter=None):
        """
        Search a conversation tree for nodes containing the search term.
        Returns a list of (node, path_to_root) tuples for matches.
        """
        matches = []

        def search_node(node, path_so_far):
            # Check if this node matches the search criteria
            if (search_term in node.content.lower() and
                    (role_filter is None or node.role == role_filter)):
                matches.append((node, path_so_far + [node]))

            # Recursively search children
            for child in node.children:
                search_node(child, path_so_far + [node])

        # Start search from the root
        search_node(conversation.root, [])
        return matches

    def on_result_selected(self, item, column):
        """Handle double-click on a search result"""
        # Get the node ID and conversation ID
        node_id = item.data(0, Qt.ItemDataRole.UserRole)
        conversation_id = item.data(1, Qt.ItemDataRole.UserRole)

        if node_id and conversation_id:
            # Prepare data to signal which message was selected
            path_ids = item.data(2, Qt.ItemDataRole.UserRole)
            self.message_selected.emit(f"{conversation_id}:{node_id}")
            self.accept()