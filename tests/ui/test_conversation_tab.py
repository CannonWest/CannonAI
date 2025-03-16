"""
Tests for the ConversationBranchTab UI component.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QCoreApplication, QTimer

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.ui.conversation import ConversationBranchTab
from src.models.db_conversation import DBConversationTree, DBMessageNode


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
    """Create a mock conversation tree for testing."""
    mock_tree = MagicMock(spec=DBConversationTree)
    
    # Create mock nodes for the conversation
    root_node = MagicMock(spec=DBMessageNode)
    root_node.id = "root_id"
    root_node.role = "system"
    root_node.content = "You are a helpful assistant."
    root_node.parent_id = None
    root_node.model_info = {}
    root_node.parameters = {}
    root_node.token_usage = {}
    root_node.attached_files = []
    
    user_node = MagicMock(spec=DBMessageNode)
    user_node.id = "user_id"
    user_node.role = "user"
    user_node.content = "Hello, this is a test message."
    user_node.parent_id = "root_id"
    user_node.model_info = {}
    user_node.parameters = {}
    user_node.token_usage = {}
    user_node.attached_files = []
    
    assistant_node = MagicMock(spec=DBMessageNode)
    assistant_node.id = "assistant_id"
    assistant_node.role = "assistant"
    assistant_node.content = "Hello! This is a test response."
    assistant_node.parent_id = "user_id"
    assistant_node.model_info = {"model": "gpt-4o"}
    assistant_node.parameters = {"temperature": 0.7}
    assistant_node.token_usage = {
        "prompt_tokens": 15,
        "completion_tokens": 25,
        "total_tokens": 40
    }
    assistant_node.attached_files = []
    
    # Configure the mock tree to return nodes and branches
    mock_tree.root = root_node
    mock_tree.current_node = assistant_node
    mock_tree.get_current_branch.return_value = [root_node, user_node, assistant_node]
    mock_tree.get_node.side_effect = lambda node_id: {
        "root_id": root_node,
        "user_id": user_node,
        "assistant_id": assistant_node
    }.get(node_id)
    
    return mock_tree


class TestConversationBranchTab:
    """Tests for the ConversationBranchTab UI component."""
    
    def test_init(self, qapp, mock_conversation_tree):
        """Test tab initialization with a conversation tree."""
        # Create the tab with the mock conversation
        tab = ConversationBranchTab(mock_conversation_tree)
        
        # Check the tab was initialized correctly
        assert tab.conversation_tree == mock_conversation_tree
        assert hasattr(tab, 'chat_display')
        assert hasattr(tab, 'graph_view')
        assert hasattr(tab, 'branch_nav')
        assert hasattr(tab, 'text_input')
        assert hasattr(tab, 'send_button')
        assert hasattr(tab, 'retry_button')
    
    def test_set_conversation_tree(self, qapp, mock_conversation_tree):
        """Test setting a new conversation tree."""
        # Create the tab without a conversation
        tab = ConversationBranchTab()
        
        # Create a spy on the update_ui method
        tab.update_ui = MagicMock()
        
        # Set the conversation tree
        tab.set_conversation_tree(mock_conversation_tree)
        
        # Check the conversation was set and UI updated
        assert tab.conversation_tree == mock_conversation_tree
        tab.update_ui.assert_called_once()
    
    def test_on_send(self, qapp, mock_conversation_tree):
        """Test sending a message."""
        # Create the tab with the mock conversation
        tab = ConversationBranchTab(mock_conversation_tree)
        
        # Create spy for the send_message signal
        spy = QSignalSpy(tab.send_message)
        
        # Set text in the input field
        tab.text_input.setPlainText("Test message")
        
        # Mock clear_attachments method
        tab.clear_attachments = MagicMock()
        
        # Call on_send method
        tab.on_send()
        
        # Check signal was emitted with correct text
        assert len(spy) == 1
        assert spy[0][0] == "Test message"
        
        # Check input was cleared
        assert tab.text_input.toPlainText() == ""
        
        # Check attachments were cleared
        tab.clear_attachments.assert_called_once()
    
    def test_on_retry(self, qapp, mock_conversation_tree):
        """Test retrying a message."""
        # Create the tab with the mock conversation
        tab = ConversationBranchTab(mock_conversation_tree)
        
        # Create spy for the retry_request signal
        spy = QSignalSpy(tab.retry_request)
        
        # Configure mock conversation to return True for retry
        mock_conversation_tree.retry_current_response.return_value = True
        
        # Mock update_ui method
        tab.update_ui = MagicMock()
        
        # Call on_retry method
        tab.on_retry()
        
        # Check retry_current_response was called
        mock_conversation_tree.retry_current_response.assert_called_once()
        
        # Check UI was updated
        tab.update_ui.assert_called_once()
        
        # Check signal was emitted
        assert len(spy) == 1
    
    def test_update_ui(self, qapp, mock_conversation_tree):
        """Test updating the UI with the current conversation state."""
        # Create the tab with the mock conversation
        tab = ConversationBranchTab(mock_conversation_tree)
        
        # Mock the constituent update methods
        tab.branch_nav.update_branch = MagicMock()
        tab.graph_view.update_tree = MagicMock()
        tab.update_chat_display = MagicMock()
        tab.update_retry_button = MagicMock()
        
        # Call update_ui
        tab.update_ui()
        
        # Check all update methods were called with correct arguments
        tab.branch_nav.update_branch.assert_called_once_with(mock_conversation_tree.get_current_branch())
        tab.graph_view.update_tree.assert_called_once_with(mock_conversation_tree)
        tab.update_chat_display.assert_called_once()
        tab.update_retry_button.assert_called_once()
    
    def test_update_chat_display(self, qapp, mock_conversation_tree):
        """Test updating the chat display with conversation messages."""
        # Create the tab with the mock conversation
        tab = ConversationBranchTab(mock_conversation_tree)
        
        # Mock clear and insertHtml methods
        tab.chat_display.clear = MagicMock()
        tab.chat_display.insertHtml = MagicMock()
        tab.chat_display.insertPlainText = MagicMock()
        
        # Call update_chat_display
        tab.update_chat_display()
        
        # Check chat display was updated
        tab.chat_display.clear.assert_called_once()
        
        # Should call insertHtml for each message in the branch
        branch = mock_conversation_tree.get_current_branch()
        assert tab.chat_display.insertHtml.call_count >= len(branch)
        
        # Should call insertPlainText for spacing between messages
        assert tab.chat_display.insertPlainText.call_count >= len(branch)
    
    def test_update_model_info(self, qapp):
        """Test updating the model information display."""
        # Create the tab without a conversation
        tab = ConversationBranchTab()
        
        # Call update_model_info with a model ID
        tab.update_model_info("gpt-4o")
        
        # Check model labels were updated
        assert "gpt-4o" in tab.model_name_label.text()
        assert "ctx" in tab.model_token_limit_label.text()  # Should show context limit
        assert "$" in tab.model_pricing_label.text()  # Should show pricing info
    
    def test_process_markdown(self, qapp):
        """Test markdown processing for display."""
        # Create the tab without a conversation
        tab = ConversationBranchTab()
        
        # Test various markdown features
        markdown_text = """
# Heading 1
## Heading 2
**Bold text**
*Italic text*
```python
def test():
    return "Hello"
```
- List item 1
- List item 2
        """
        
        # Process the markdown
        html = tab.process_markdown(markdown_text)
        
        # Check markdown was converted to HTML
        assert "<h1>" in html
        assert "<h2>" in html
        assert "<b>" in html
        assert "<i>" in html
        assert "<pre" in html
        assert "python" in html
        assert "Hello" in html
        assert "•" in html  # Bullet points
    
    def test_navigate_to_node(self, qapp, mock_conversation_tree):
        """Test navigating to a specific node."""
        # Create the tab with the mock conversation
        tab = ConversationBranchTab(mock_conversation_tree)
        
        # Mock update_ui method
        tab.update_ui = MagicMock()
        
        # Create spy for the branch_changed signal
        spy = QSignalSpy(tab.branch_changed)
        
        # Configure mock conversation to return True for navigate_to_node
        mock_conversation_tree.navigate_to_node.return_value = True
        
        # Call navigate_to_node method
        tab.navigate_to_node("user_id")
        
        # Check navigate_to_node was called with correct ID
        mock_conversation_tree.navigate_to_node.assert_called_once_with("user_id")
        
        # Check UI was updated
        tab.update_ui.assert_called_once()
        
        # Check signal was emitted
        assert len(spy) == 1
    
    def test_start_and_stop_loading_indicator(self, qapp):
        """Test starting and stopping the loading indicator."""
        # Create the tab without a conversation
        tab = ConversationBranchTab()
        
        # Test starting loading indicator
        tab.start_loading_indicator()
        assert tab._loading_active is True
        assert tab._loading_timer.isActive()
        
        # Test stopping loading indicator
        tab.stop_loading_indicator()
        assert tab._loading_active is False
        assert not tab._loading_timer.isActive()
    
    def test_update_chat_streaming(self, qapp, mock_conversation_tree):
        """Test updating the chat display during streaming."""
        # Create the tab with the mock conversation
        tab = ConversationBranchTab(mock_conversation_tree)
        
        # Mock the text cursor
        mock_cursor = MagicMock()
        tab.chat_display.textCursor = MagicMock(return_value=mock_cursor)
        tab.chat_display.setTextCursor = MagicMock()
        tab.chat_display.insertPlainText = MagicMock()
        tab.chat_display.ensureCursorVisible = MagicMock()
        
        # Call update_chat_streaming with a chunk
        tab.update_chat_streaming("Test chunk")
        
        # Check streaming flags were set
        assert tab._is_streaming is True
        
        # Check text cursor was positioned at the end
        mock_cursor.movePosition.assert_called()
        tab.chat_display.setTextCursor.assert_called_with(mock_cursor)
        
        # Check the chunk was inserted
        tab.chat_display.insertPlainText.assert_called_with("Test chunk")
        
        # Check cursor was made visible
        tab.chat_display.ensureCursorVisible.assert_called_once()
    
    def test_complete_streaming_update(self, qapp, mock_conversation_tree):
        """Test completing a streaming update."""
        # Create the tab with the mock conversation
        tab = ConversationBranchTab(mock_conversation_tree)
        
        # Set streaming flags
        tab._is_streaming = True
        tab._streaming_started = True
        
        # Mock update_chat_display
        tab.update_chat_display = MagicMock()
        
        # Call complete_streaming_update
        tab.complete_streaming_update()
        
        # Check streaming flags were reset
        assert tab._is_streaming is False
        assert tab._streaming_started is False
        
        # Check chat display was updated
        tab.update_chat_display.assert_called_once()
    
    def test_add_cot_step(self, qapp, mock_conversation_tree):
        """Test adding a chain of thought step."""
        # Create the tab with the mock conversation
        tab = ConversationBranchTab(mock_conversation_tree)
        
        # Call add_cot_step
        tab.add_cot_step("Step 1", "This is the first step.")
        
        # Check reasoning steps were updated
        assert len(tab.reasoning_steps) == 1
        assert tab.reasoning_steps[0]["name"] == "Step 1"
        assert tab.reasoning_steps[0]["content"] == "This is the first step."
    
    @patch('src.ui.conversation.QFileDialog')
    def test_on_attach_file(self, mock_file_dialog, qapp):
        """Test attaching a file to a message."""
        # Create the tab without a conversation
        tab = ConversationBranchTab()
        
        # Mock the file dialog to return a file path
        mock_file_dialog.getOpenFileNames.return_value = (["test_file.txt"], "")
        
        # Mock the add_attachment method
        tab.add_attachment = MagicMock()
        
        # Call on_attach_file
        tab.on_attach_file()
        
        # Check dialog was shown with correct parameters
        mock_file_dialog.getOpenFileNames.assert_called_once()
        
        # Check add_attachment was called with the file path
        tab.add_attachment.assert_called_once_with("test_file.txt")
    
    @patch('src.ui.conversation.get_file_info')
    def test_add_attachment(self, mock_get_file_info, qapp):
        """Test adding a file attachment."""
        # Create the tab without a conversation
        tab = ConversationBranchTab()
        
        # Mock the get_file_info function to return file info
        mock_get_file_info.return_value = {
            "file_name": "test_file.txt",
            "mime_type": "text/plain",
            "content": "Test file content",
            "token_count": 10,
            "path": "/path/to/test_file.txt",
            "size": 1024
        }
        
        # Mock the update_attachments_ui method
        tab.update_attachments_ui = MagicMock()
        
        # Create spy for the file_attached signal
        spy = QSignalSpy(tab.file_attached)
        
        # Call add_attachment
        tab.add_attachment("/path/to/test_file.txt")
        
        # Check get_file_info was called with the file path
        mock_get_file_info.assert_called_once()
        
        # Check attachment was added to current_attachments
        assert len(tab.current_attachments) == 1
        assert tab.current_attachments[0]["file_name"] == "test_file.txt"
        
        # Check UI was updated
        tab.update_attachments_ui.assert_called_once()
        
        # Check signal was emitted
        assert len(spy) == 1
        assert spy[0][0] == "/path/to/test_file.txt"
    
    def test_clear_attachments(self, qapp):
        """Test clearing attachments."""
        # Create the tab without a conversation
        tab = ConversationBranchTab()
        
        # Add a test attachment
        tab.current_attachments = [{
            "file_name": "test_file.txt",
            "mime_type": "text/plain",
            "content": "Test file content",
            "token_count": 10
        }]
        
        # Mock update_attachments_ui
        tab.update_attachments_ui = MagicMock()
        
        # Call clear_attachments
        tab.clear_attachments()
        
        # Check attachments were cleared
        assert len(tab.current_attachments) == 0
        
        # Check UI was updated
        tab.update_attachments_ui.assert_called_once()


# Helper class for testing signals
class QSignalSpy:
    """Simple class to capture signal emissions."""
    
    def __init__(self, signal):
        self.signal = signal
        self.emissions = []
        self.signal.connect(self.capture)
    
    def capture(self, *args):
        self.emissions.append(args)
    
    def __getitem__(self, index):
        return self.emissions[index]
    
    def __len__(self):
        return len(self.emissions)
