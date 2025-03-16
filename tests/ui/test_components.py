"""
Tests for UI components like ConversationTreeWidget, BranchNavBar, and SettingsDialog.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from PyQt6.QtWidgets import QApplication, QTreeWidgetItem
from PyQt6.QtCore import Qt, QSize, pyqtSignal

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.ui.components import ConversationTreeWidget, BranchNavBar, SettingsDialog, SearchDialog
from src.models.db_conversation import DBMessageNode, DBConversationTree


@pytest.fixture
def qapp():
    """Fixture to create a QApplication instance for each test."""
    # Only create a QApplication if it doesn't already exist
    if not QApplication.instance():
        app = QApplication([])
        yield app
        app.quit()
    else:
        yield QApplication.instance()


@pytest.fixture
def mock_conversation_tree():
    """Create a mock conversation tree with nodes."""
    # Create mock nodes
    system_node = MagicMock(spec=DBMessageNode)
    system_node.id = "node-sys"
    system_node.role = "system"
    system_node.content = "You are a helpful assistant."
    system_node.parent_id = None
    system_node.children = []
    
    user_node = MagicMock(spec=DBMessageNode)
    user_node.id = "node-user"
    user_node.role = "user"
    user_node.content = "Hello, this is a test message."
    user_node.parent_id = "node-sys"
    user_node.children = []
    
    assistant_node = MagicMock(spec=DBMessageNode)
    assistant_node.id = "node-assistant"
    assistant_node.role = "assistant"
    assistant_node.content = "Hello! How can I help you today?"
    assistant_node.parent_id = "node-user"
    assistant_node.children = []
    assistant_node.model_info = {"model": "gpt-4o"}
    
    # Link nodes
    system_node.children = [user_node]
    user_node.children = [assistant_node]
    
    # Create mock conversation tree
    mock_tree = MagicMock(spec=DBConversationTree)
    mock_tree.id = "conv-id"
    mock_tree.name = "Test Conversation"
    mock_tree.root = system_node
    mock_tree.current_node = assistant_node
    mock_tree.current_node_id = "node-assistant"
    
    # Mock get_current_branch to return nodes in order
    mock_tree.get_current_branch.return_value = [system_node, user_node, assistant_node]
    
    return mock_tree


class TestConversationTreeWidget:
    """Tests for the ConversationTreeWidget component."""
    
    def test_init(self, qapp):
        """Test widget initialization."""
        # Create widget
        widget = ConversationTreeWidget()
        
        # Check it has initialized correctly
        assert widget.columnCount() == 1
        assert widget.headerItem().text(0) == "Conversation"
        assert widget.selectionMode() == widget.SelectionMode.SingleSelection
    
    def test_update_tree(self, qapp, mock_conversation_tree):
        """Test updating the tree with a conversation structure."""
        # Create widget
        widget = ConversationTreeWidget()
        
        # Mock the create_items_recursive method
        root_item = QTreeWidgetItem(["System"])
        widget.create_items_recursive = MagicMock(return_value=root_item)
        
        # Update tree
        widget.update_tree(mock_conversation_tree)
        
        # Check create_items_recursive was called with the root node
        widget.create_items_recursive.assert_called_once_with(
            mock_conversation_tree.root, 
            {node.id for node in mock_conversation_tree.get_current_branch()}
        )
        
        # Check root item was added to the tree
        assert widget.topLevelItemCount() == 1
        assert widget.topLevelItem(0) == root_item
    
    def test_create_items_recursive(self, qapp, mock_conversation_tree):
        """Test creating tree items recursively."""
        # Create widget
        widget = ConversationTreeWidget()
        
        # Get current branch node IDs
        current_ids = {node.id for node in mock_conversation_tree.get_current_branch()}
        
        # Create root item
        root_item = widget.create_items_recursive(mock_conversation_tree.root, current_ids)
        
        # Check item was created correctly
        assert root_item.text(0) == "🔧 System"
        assert root_item.data(0, Qt.ItemDataRole.UserRole) == "node-sys"
        
        # Check it has one child (user message)
        assert root_item.childCount() == 1
        user_item = root_item.child(0)
        assert user_item.text(0) == "👤 User"
        assert user_item.data(0, Qt.ItemDataRole.UserRole) == "node-user"
        
        # Check user item has one child (assistant message)
        assert user_item.childCount() == 1
        assistant_item = user_item.child(0)
        assert "🤖 Assistant" in assistant_item.text(0)
        assert assistant_item.data(0, Qt.ItemDataRole.UserRole) == "node-assistant"
    
    def test_on_item_clicked(self, qapp, mock_conversation_tree):
        """Test handling item clicked events."""
        # Create widget
        widget = ConversationTreeWidget()
        
        # Connect to signal
        mock_handler = MagicMock()
        widget.node_selected.connect(mock_handler)
        
        # Create a mock item with node ID
        item = QTreeWidgetItem(["Test Item"])
        item.setData(0, Qt.ItemDataRole.UserRole, "test-node-id")
        
        # Trigger item clicked
        widget.on_item_clicked(item, 0)
        
        # Check signal was emitted with node ID
        mock_handler.assert_called_once_with("test-node-id")


class TestBranchNavBar:
    """Tests for the BranchNavBar component."""
    
    def test_init(self, qapp):
        """Test widget initialization."""
        # Create widget
        widget = BranchNavBar()
        
        # Check it has initialized correctly
        assert widget.layout.contentsMargins() == (5, 2, 5, 2)
        assert widget.layout.spacing() == 5
        assert widget.nodes == []
    
    def test_update_branch(self, qapp, mock_conversation_tree):
        """Test updating the navigation bar with branch nodes."""
        # Create widget
        widget = BranchNavBar()
        
        # Set up mock for extract_display_text
        with patch('src.ui.components.extract_display_text', return_value="Test Display"):
            # Update branch
            widget.update_branch(mock_conversation_tree.get_current_branch())
        
            # Check buttons were created
            assert len(widget.nodes) == 3
            
            # Check button texts
            assert "🔧" in widget.nodes[0][1].text()  # System
            assert "👤" in widget.nodes[1][1].text()  # User
            assert "🤖" in widget.nodes[2][1].text()  # Assistant
            
            # Check separator labels
            separators = [child for child in widget.layout.children() if hasattr(child, 'text') and child.text() == "→"]
            assert len(separators) == 2  # Should be 2 separators between 3 nodes
    
    def test_clear(self, qapp):
        """Test clearing the navigation bar."""
        # Create widget
        widget = BranchNavBar()
        
        # Add some mock buttons
        button1 = MagicMock()
        button2 = MagicMock()
        widget.layout.addWidget(button1)
        widget.layout.addWidget(button2)
        widget.nodes = [("id1", button1), ("id2", button2)]
        
        # Clear the bar
        widget.clear()
        
        # Check everything was cleared
        assert widget.nodes == []
        assert widget.layout.count() == 0
        button1.deleteLater.assert_called_once()
        button2.deleteLater.assert_called_once()
    
    def test_node_selected_signal(self, qapp):
        """Test node selection signal emission."""
        # Create widget
        widget = BranchNavBar()
        
        # Connect to signal
        mock_handler = MagicMock()
        widget.node_selected.connect(mock_handler)
        
        # Set up mock for extract_display_text
        with patch('src.ui.components.extract_display_text', return_value="Test Display"):
            # Create a mock branch
            system_node = MagicMock()
            system_node.id = "sys-id"
            system_node.role = "system"
            system_node.content = "System message"
            
            # Update branch with the mock node
            widget.update_branch([system_node])
            
            # Find the button and simulate a click
            button = widget.nodes[0][1]
            button.clicked.emit(False)  # Emit clicked signal
            
            # Check signal was emitted with node ID
            mock_handler.assert_called_once_with("sys-id")


class TestSettingsDialog:
    """Tests for the SettingsDialog component."""
    
    @pytest.fixture
    def default_settings(self):
        """Default settings for testing."""
        return {
            "api_key": "test_api_key",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "top_p": 1.0,
            "stream": True,
            "text": {"format": {"type": "text"}},
            "reasoning": {"effort": "medium"},
            "api_type": "responses",
            "metadata": {}
        }
    
    def test_init(self, qapp, default_settings):
        """Test dialog initialization."""
        # Create dialog
        dialog = SettingsDialog(default_settings)
        
        # Check it has initialized correctly
        assert hasattr(dialog, 'model_combo')
        assert hasattr(dialog, 'temperature')
        assert hasattr(dialog, 'max_tokens')
        assert hasattr(dialog, 'stream_checkbox')
        assert hasattr(dialog, 'api_key_input')
        
        # Check values were set from settings
        assert dialog.api_key_input.text() == "test_api_key"
        assert dialog.temperature.value() == 0.7
        assert dialog.max_tokens.value() == 1024
        assert dialog.stream_checkbox.isChecked() is True
    
    def test_update_ui_for_model(self, qapp, default_settings):
        """Test UI updates based on selected model."""
        # Create dialog
        dialog = SettingsDialog(default_settings)
        
        # Mock model info label
        dialog.model_info = MagicMock()
        
        # Set up mocks for model constants
        with patch('src.ui.components.MODEL_CONTEXT_SIZES', {'gpt-4o': 128000}), \
             patch('src.ui.components.MODEL_OUTPUT_LIMITS', {'gpt-4o': 16384}), \
             patch('src.ui.components.MODEL_PRICING', {'gpt-4o': {"input": 2.5, "output": 10.0}}), \
             patch('src.ui.components.REASONING_MODELS', []):
            
            # Test update for gpt-4o model
            dialog.model_tabs.currentIndex = MagicMock(return_value=0)
            dialog.model_combo.currentText = MagicMock(return_value="GPT-4o")
            dialog.update_ui_for_model()
            
            # Check max tokens was set
            assert dialog.max_tokens.maximum() == 16384
            
            # Check model info was updated
            dialog.model_info.setText.assert_called_once()
            model_info_text = dialog.model_info.setText.call_args[0][0]
            assert "128000" in model_info_text  # Context window
            assert "16384" in model_info_text   # Max output
            assert "$2.50" in model_info_text   # Input price
            assert "$10.00" in model_info_text  # Output price
    
    def test_update_metadata_fields_state(self, qapp, default_settings):
        """Test enabling/disabling metadata fields based on store checkbox."""
        # Create dialog
        dialog = SettingsDialog(default_settings)
        
        # Set up mock metadata fields
        dialog.metadata_keys = [MagicMock(), MagicMock()]
        dialog.metadata_values = [MagicMock(), MagicMock()]
        dialog.metadata_group = MagicMock()
        
        # Test with store enabled
        dialog.store_checkbox.setChecked(True)
        dialog.update_metadata_fields_state()
        
        # Check fields were enabled
        for key_input, value_input in zip(dialog.metadata_keys, dialog.metadata_values):
            key_input.setEnabled.assert_called_with(True)
            value_input.setEnabled.assert_called_with(True)
        
        # Check group title was updated
        dialog.metadata_group.setTitle.assert_called_with("Metadata")
        
        # Test with store disabled
        dialog.store_checkbox.setChecked(False)
        dialog.update_metadata_fields_state()
        
        # Check fields were disabled
        for key_input, value_input in zip(dialog.metadata_keys, dialog.metadata_values):
            key_input.setEnabled.assert_called_with(False)
            value_input.setEnabled.assert_called_with(False)
        
        # Check group title was updated
        dialog.metadata_group.setTitle.assert_called_with("Metadata (requires Store enabled)")
    
    def test_get_settings(self, qapp, default_settings):
        """Test getting settings from the dialog."""
        # Create dialog
        dialog = SettingsDialog(default_settings)
        
        # Set values
        # Mock tab index
        dialog.model_tabs.currentIndex = MagicMock(return_value=0)
        
        # Mock model name
        dialog.model_combo.currentText = MagicMock(return_value="GPT-4o")
        
        # Set some values
        dialog.temperature.setValue(0.5)
        dialog.max_tokens.setValue(2000)
        dialog.stream_checkbox.setChecked(False)
        dialog.api_key_input.setText("new_api_key")
        
        # Mock response format combo
        dialog.response_format_combo.currentText = MagicMock(return_value="json_object")
        
        # Set metadata fields
        dialog.metadata_keys = [MagicMock(), MagicMock()]
        dialog.metadata_values = [MagicMock(), MagicMock()]
        
        dialog.metadata_keys[0].text.return_value = "key1"
        dialog.metadata_values[0].text.return_value = "value1"
        dialog.metadata_keys[1].text.return_value = ""  # Empty key should be ignored
        dialog.metadata_values[1].text.return_value = "value2"
        
        # Mock models dictionary
        with patch('src.ui.components.MODELS', {"GPT-4o": "gpt-4o"}), \
             patch('src.ui.components.MODEL_SNAPSHOTS', {}):
            
            # Get settings
            settings = dialog.get_settings()
            
            # Check values
            assert settings["model"] == "gpt-4o"
            assert settings["temperature"] == 0.5
            assert settings["max_tokens"] == 2000
            assert settings["max_output_tokens"] == 2000
            assert settings["stream"] is False
            assert settings["api_key"] == "new_api_key"
            assert settings["text"]["format"]["type"] == "json_object"
            assert settings["metadata"] == {"key1": "value1"}


class TestSearchDialog:
    """Tests for the SearchDialog component."""
    
    def test_init(self, qapp):
        """Test dialog initialization."""
        # Create mock conversation manager
        mock_manager = MagicMock()
        
        # Create dialog
        dialog = SearchDialog(mock_manager)
        
        # Check it has initialized correctly
        assert dialog.conversation_manager == mock_manager
        assert hasattr(dialog, 'search_input')
        assert hasattr(dialog, 'results_list')
        assert hasattr(dialog, 'current_conversation_only')
        assert hasattr(dialog, 'filter_by_role')
    
    def test_perform_search(self, qapp):
        """Test searching through conversations."""
        # Create mock conversation manager
        mock_manager = MagicMock()
        
        # Configure mock search results
        mock_manager.search_conversations.return_value = [
            {
                "id": "msg1", 
                "conversation_id": "conv1", 
                "conversation_name": "Conversation 1",
                "role": "user", 
                "content": "test search term", 
                "timestamp": "2023-01-01"
            },
            {
                "id": "msg2", 
                "conversation_id": "conv2", 
                "conversation_name": "Conversation 2",
                "role": "assistant", 
                "content": "response with search term", 
                "timestamp": "2023-01-02"
            }
        ]
        
        # Create dialog
        dialog = SearchDialog(mock_manager)
        
        # Set search term
        dialog.search_input.setText("search term")
        
        # Perform search
        dialog.perform_search()
        
        # Check search was performed
        mock_manager.search_conversations.assert_called_once_with(
            "search term", 
            conversation_id=None, 
            role_filter=None
        )
        
        # Check results were added to the tree
        assert dialog.results_list.topLevelItemCount() > 0
        
        # Check status was updated
        assert "Found 2 results" in dialog.status_label.text()
    
    def test_perform_search_with_filters(self, qapp):
        """Test searching with filters."""
        # Create mock conversation manager
        mock_manager = MagicMock()
        mock_manager.active_conversation = MagicMock()
        mock_manager.active_conversation.id = "active-conv-id"
        
        # Configure mock search results
        mock_manager.search_conversations.return_value = [
            {
                "id": "msg1", 
                "conversation_id": "active-conv-id", 
                "conversation_name": "Active Conversation",
                "role": "user", 
                "content": "filtered search term", 
                "timestamp": "2023-01-01"
            }
        ]
        
        # Create dialog
        dialog = SearchDialog(mock_manager)
        
        # Set search term and filters
        dialog.search_input.setText("search term")
        dialog.current_conversation_only.setChecked(True)
        dialog.filter_by_role.setCurrentIndex(1)  # User messages
        
        # Perform search
        dialog.perform_search()
        
        # Check search was performed with filters
        mock_manager.search_conversations.assert_called_once_with(
            "search term", 
            conversation_id="active-conv-id", 
            role_filter="user"
        )
        
        # Check status was updated
        assert "Found 1 result" in dialog.status_label.text()
    
    def test_on_result_selected(self, qapp):
        """Test handling result selection."""
        # Create mock conversation manager
        mock_manager = MagicMock()
        
        # Create dialog
        dialog = SearchDialog(mock_manager)
        
        # Connect to signal
        mock_handler = MagicMock()
        dialog.message_selected.connect(mock_handler)
        
        # Create a mock item with node and conversation ID
        item = QTreeWidgetItem()
        item.setData(0, Qt.ItemDataRole.UserRole, "node-id")
        item.setData(1, Qt.ItemDataRole.UserRole, "conv-id")
        item.setData(2, Qt.ItemDataRole.UserRole, ["root-id", "parent-id", "node-id"])
        
        # Call on_result_selected
        dialog.on_result_selected(item, 0)
        
        # Check signal was emitted with combined ID
        mock_handler.assert_called_once_with("conv-id:node-id")
        
        # Check dialog was accepted
        assert dialog.result() == dialog.Accepted
