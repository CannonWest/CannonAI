"""
Unit tests for the DBConversationTree and DBMessageNode classes.
"""

import os
import sys
import pytest
import tempfile
import sqlite3
from unittest.mock import MagicMock, patch
from datetime import datetime

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.models.db_conversation import DBConversationTree, DBMessageNode
from src.models.db_manager import DatabaseManager


class TestDBMessageNode:
    """Tests for the DBMessageNode class that represents a message in a conversation."""
    
    def test_init(self):
        """Test message node initialization."""
        # Create a message node
        node = DBMessageNode(
            id="test_id",
            conversation_id="test_conv_id",
            role="user",
            content="Test message content",
            parent_id="parent_id",
            timestamp="2023-01-01T12:00:00",
            model_info={"model": "gpt-4o"},
            parameters={"temperature": 0.7},
            token_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            attached_files=[{"file_name": "test.txt", "content": "file content"}],
            response_id="resp_123456"
        )
        
        # Check node was initialized correctly
        assert node.id == "test_id"
        assert node.conversation_id == "test_conv_id"
        assert node.role == "user"
        assert node.content == "Test message content"
        assert node.parent_id == "parent_id"
        assert node.timestamp == "2023-01-01T12:00:00"
        assert node.model_info == {"model": "gpt-4o"}
        assert node.parameters == {"temperature": 0.7}
        assert node.token_usage == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        assert len(node.attached_files) == 1
        assert node.attached_files[0]["file_name"] == "test.txt"
        assert node.response_id == "resp_123456"
        assert node._reasoning_steps is None
        
        # Check default values
        assert isinstance(node.timestamp, str)  # timestamp is converted to ISO format string
        assert node._children is None  # Children are loaded on demand
        assert node._db_manager is None  # DB manager reference is set later
    
    def test_children_property(self):
        """Test the children property with lazy loading."""
        # Create a message node
        node = DBMessageNode(
            id="test_id",
            conversation_id="test_conv_id",
            role="user",
            content="Test message content"
        )
        
        # Create a mock database manager
        mock_db_manager = MagicMock()
        mock_child_nodes = [
            DBMessageNode(id="child1", conversation_id="test_conv_id", role="assistant", content="Child 1"),
            DBMessageNode(id="child2", conversation_id="test_conv_id", role="user", content="Child 2")
        ]
        mock_db_manager.get_node_children.return_value = mock_child_nodes
        
        # Set the DB manager reference
        node._db_manager = mock_db_manager
        
        # Access the children property to trigger lazy loading
        children = node.children
        
        # Check get_node_children was called with the correct ID
        mock_db_manager.get_node_children.assert_called_once_with("test_id")
        
        # Check children were loaded correctly
        assert len(children) == 2
        assert children[0].id == "child1"
        assert children[1].id == "child2"
        
        # Check children are cached (accessing again doesn't trigger another DB call)
        mock_db_manager.get_node_children.reset_mock()
        children = node.children
        mock_db_manager.get_node_children.assert_not_called()
    
    def test_parent_property(self):
        """Test the parent property with lazy loading."""
        # Create a message node
        node = DBMessageNode(
            id="test_id",
            conversation_id="test_conv_id",
            role="user",
            content="Test message content",
            parent_id="parent_id"
        )
        
        # Create a mock database manager
        mock_db_manager = MagicMock()
        mock_parent_node = DBMessageNode(
            id="parent_id",
            conversation_id="test_conv_id", 
            role="system",
            content="Parent content"
        )
        mock_db_manager.get_message.return_value = mock_parent_node
        
        # Set the DB manager reference
        node._db_manager = mock_db_manager
        
        # Access the parent property to trigger lazy loading
        parent = node.parent
        
        # Check get_message was called with the correct ID
        mock_db_manager.get_message.assert_called_once_with("parent_id")
        
        # Check parent was loaded correctly
        assert parent.id == "parent_id"
        assert parent.role == "system"
        assert parent.content == "Parent content"
    
    def test_reasoning_steps_property(self):
        """Test the reasoning_steps property."""
        # Create a message node
        node = DBMessageNode(
            id="test_id",
            conversation_id="test_conv_id",
            role="assistant",
            content="Test message content"
        )
        
        # Test getting steps when they're not set
        assert node.reasoning_steps == []
        
        # Test setting steps
        steps = [{"name": "Step 1", "content": "Step 1 content"}]
        node.reasoning_steps = steps
        assert node._reasoning_steps == steps
        assert node.reasoning_steps == steps
        
        # Test loading from database
        mock_db_manager = MagicMock()
        mock_db_manager.get_node_metadata.return_value = (
            {},  # model_info
            {},  # parameters
            {},  # token_usage
            [{"name": "DB Step", "content": "DB Step content"}]  # reasoning_steps
        )
        
        # Create a new node without steps
        node2 = DBMessageNode(
            id="test_id2",
            conversation_id="test_conv_id",
            role="assistant",
            content="Test message content"
        )
        
        # Set the DB manager reference
        node2._db_manager = mock_db_manager
        
        # Access the reasoning_steps property to trigger loading from DB
        steps2 = node2.reasoning_steps
        
        # Check get_node_metadata was called
        mock_db_manager.get_node_metadata.assert_called_once_with("test_id2")
        
        # Check steps were loaded correctly
        assert len(steps2) == 1
        assert steps2[0]["name"] == "DB Step"
        assert steps2[0]["content"] == "DB Step content"
    
    def test_add_child(self):
        """Test adding a child node."""
        # Create a parent node
        parent = DBMessageNode(
            id="parent_id",
            conversation_id="test_conv_id",
            role="user",
            content="Parent content"
        )
        
        # Create a child node
        child = DBMessageNode(
            id="child_id",
            conversation_id="test_conv_id",
            role="assistant",
            content="Child content",
            parent_id="parent_id"
        )
        
        # Add the child to the parent
        parent.add_child(child)
        
        # Check the child was added correctly
        assert parent._children is not None
        assert len(parent._children) == 1
        assert parent._children[0].id == "child_id"
        assert parent._children[0].parent_id == "parent_id"
    
    def test_get_path_to_root(self):
        """Test getting the path from a node to the root."""
        # Create a message node
        node = DBMessageNode(
            id="test_id",
            conversation_id="test_conv_id",
            role="user",
            content="Test message content"
        )
        
        # Create a mock database manager
        mock_db_manager = MagicMock()
        mock_path = [
            DBMessageNode(id="root", conversation_id="test_conv_id", role="system", content="Root"),
            DBMessageNode(id="parent", conversation_id="test_conv_id", role="user", content="Parent"),
            DBMessageNode(id="test_id", conversation_id="test_conv_id", role="assistant", content="Current")
        ]
        mock_db_manager.get_path_to_root.return_value = mock_path
        
        # Set the DB manager reference
        node._db_manager = mock_db_manager
        
        # Get path to root
        path = node.get_path_to_root()
        
        # Check get_path_to_root was called with the correct ID
        mock_db_manager.get_path_to_root.assert_called_once_with("test_id")
        
        # Check path was returned correctly
        assert len(path) == 3
        assert path[0].id == "root"
        assert path[1].id == "parent"
        assert path[2].id == "test_id"
    
    def test_get_messages_to_root(self):
        """Test getting a list of message dicts from root to this node."""
        # Create a message node
        node = DBMessageNode(
            id="test_id",
            conversation_id="test_conv_id",
            role="assistant",
            content="Test message content"
        )
        
        # Mock the get_path_to_root method
        node.get_path_to_root = MagicMock(return_value=[
            DBMessageNode(id="root", conversation_id="test_conv_id", role="system", content="System message"),
            DBMessageNode(id="user1", conversation_id="test_conv_id", role="user", content="User message"),
            DBMessageNode(id="asst1", conversation_id="test_conv_id", role="assistant", content="Assistant message")
        ])
        
        # Get messages to root
        messages = node.get_messages_to_root()
        
        # Check messages are in the correct format
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "System message"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "User message"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "Assistant message"
    
    def test_to_dict(self):
        """Test converting a node to a dictionary."""
        # Create a message node
        node = DBMessageNode(
            id="test_id",
            conversation_id="test_conv_id",
            role="user",
            content="Test message content",
            timestamp="2023-01-01T12:00:00",
            model_info={"model": "gpt-4o"},
            parameters={"temperature": 0.7},
            token_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            attached_files=[{"file_name": "test.txt", "content": "file content"}]
        )
        
        # Mock the children property
        child = DBMessageNode(
            id="child_id",
            conversation_id="test_conv_id",
            role="assistant",
            content="Child content",
            parent_id="test_id"
        )
        node._children = [child]
        
        # Convert to dictionary
        node_dict = node.to_dict()
        
        # Check dictionary has the correct structure
        assert node_dict["id"] == "test_id"
        assert node_dict["role"] == "user"
        assert node_dict["content"] == "Test message content"
        assert node_dict["timestamp"] == "2023-01-01T12:00:00"
        assert node_dict["model_info"] == {"model": "gpt-4o"}
        assert node_dict["parameters"] == {"temperature": 0.7}
        assert node_dict["token_usage"] == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        assert len(node_dict["attached_files"]) == 1
        assert node_dict["attached_files"][0]["file_name"] == "test.txt"
        assert len(node_dict["children"]) == 1
        assert node_dict["children"][0]["id"] == "child_id"
        assert node_dict["children"][0]["role"] == "assistant"


class TestDBConversationTree:
    """Tests for the DBConversationTree class that represents a conversation."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager."""
        mock_manager = MagicMock(spec=DatabaseManager)
        
        # Mock get_connection
        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        mock_manager.get_connection.return_value = mock_connection
        
        return mock_manager
    
    def test_init_new_conversation(self, mock_db_manager):
        """Test initializing a new conversation."""
        # Create a new conversation
        conversation = DBConversationTree(
            mock_db_manager,
            name="Test Conversation",
            system_message="You are a helpful assistant for testing."
        )
        
        # Check the conversation was initialized correctly
        assert conversation.db_manager == mock_db_manager
        assert conversation.name == "Test Conversation"
        assert conversation.created_at != ""
        assert conversation.modified_at != ""
        assert hasattr(conversation, 'id')
        assert hasattr(conversation, 'root_id')
        assert hasattr(conversation, 'current_node_id')
        
        # Check database operations were performed
        conn = mock_db_manager.get_connection.return_value
        cursor = conn.cursor.return_value
        
        # Should have inserted conversation and root system message
        cursor.execute.assert_called()
        assert cursor.execute.call_count >= 2
        conn.commit.assert_called_once()
    
    def test_init_existing_conversation(self, mock_db_manager):
        """Test initializing an existing conversation."""
        # Mock cursor.fetchone to return conversation data
        mock_cursor = mock_db_manager.get_connection.return_value.cursor.return_value
        mock_cursor.fetchone.side_effect = [
            # First call: return conversation data
            {
                'id': 'existing_conv_id',
                'name': 'Existing Conversation',
                'created_at': '2023-01-01T12:00:00',
                'modified_at': '2023-01-01T13:00:00',
                'current_node_id': 'current_node_id',
                'system_message': 'Existing system message'
            },
            # Second call: return root node ID
            {'id': 'root_node_id'}
        ]
        
        # Create conversation with existing ID
        conversation = DBConversationTree(
            mock_db_manager,
            id="existing_conv_id"
        )
        
        # Check the conversation was loaded correctly
        assert conversation.db_manager == mock_db_manager
        assert conversation.id == "existing_conv_id"
        assert conversation.name == "Existing Conversation"
        assert conversation.created_at == "2023-01-01T12:00:00"
        assert conversation.modified_at == "2023-01-01T13:00:00"
        assert conversation.current_node_id == "current_node_id"
        assert conversation.root_id == "root_node_id"
        
        # Check database queries were performed
        mock_cursor.execute.assert_called()
        assert mock_cursor.execute.call_count >= 2
    
    def test_update_name(self, mock_db_manager):
        """Test updating the conversation name."""
        # Initialize conversation with mock data
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id",
            name="Old Name",
            system_message="System message"
        )
        
        # Mock the query execution
        mock_cursor = mock_db_manager.get_connection.return_value.cursor.return_value
        
        # Update the name
        result = conversation.update_name("New Name")
        
        # Check the name was updated
        assert result is True
        assert conversation.name == "New Name"
        
        # Check database update was performed
        mock_cursor.execute.assert_called()
        mock_db_manager.get_connection.return_value.commit.assert_called_once()
    
    @patch('src.models.db_conversation.DBConversationTree._create_new_conversation')
    @patch('src.models.db_conversation.DBConversationTree._load_conversation')
    def test_init_delegation(self, mock_load, mock_create, mock_db_manager):
        """Test that init delegates to _load_conversation or _create_new_conversation."""
        # Test with existing ID
        DBConversationTree(mock_db_manager, id="existing_id")
        mock_load.assert_called_once_with("existing_id")
        mock_create.assert_not_called()
        
        # Reset mocks
        mock_load.reset_mock()
        mock_create.reset_mock()
        
        # Test without ID (new conversation)
        DBConversationTree(mock_db_manager, name="New Conversation", system_message="System message")
        mock_create.assert_called_once_with("System message")
        mock_load.assert_not_called()
    
    def test_root_property(self, mock_db_manager):
        """Test the root property."""
        # Initialize conversation
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id"
        )
        
        # Mock the root_id
        conversation.root_id = "root_id"
        
        # Mock the get_node method
        conversation.get_node = MagicMock(return_value="root_node")
        
        # Get the root
        root = conversation.root
        
        # Check get_node was called with root_id
        conversation.get_node.assert_called_once_with("root_id")
        
        # Check the root was returned
        assert root == "root_node"
    
    def test_current_node_property(self, mock_db_manager):
        """Test the current_node property."""
        # Initialize conversation
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id"
        )
        
        # Mock the current_node_id
        conversation.current_node_id = "current_id"
        
        # Mock the get_node method
        conversation.get_node = MagicMock(return_value="current_node")
        
        # Get the current node
        current = conversation.current_node
        
        # Check get_node was called with current_node_id
        conversation.get_node.assert_called_once_with("current_id")
        
        # Check the current node was returned
        assert current == "current_node"
    
    def test_get_node(self, mock_db_manager):
        """Test getting a node by ID."""
        # Initialize conversation
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id"
        )
        
        # Mock database queries
        mock_cursor = mock_db_manager.get_connection.return_value.cursor.return_value
        
        # Mock fetchone to return message data
        mock_cursor.fetchone.side_effect = [
            # First call: return message data
            {
                'id': 'node_id',
                'conversation_id': 'test_conv_id',
                'parent_id': None,
                'role': 'user',
                'content': 'Test content',
                'timestamp': '2023-01-01T12:00:00',
                'response_id': None
            },
            # Subsequent calls for metadata
            [], [], []
        ]
        
        # Get the node
        node = conversation.get_node("node_id")
        
        # Check the node was retrieved correctly
        assert node.id == "node_id"
        assert node.conversation_id == "test_conv_id"
        assert node.role == "user"
        assert node.content == "Test content"
        assert node._db_manager == mock_db_manager
        
        # Check database queries were performed
        mock_cursor.execute.assert_called()
    
    def test_add_user_message(self, mock_db_manager):
        """Test adding a user message."""
        # Initialize conversation
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id"
        )
        
        # Mock the current_node_id
        conversation.current_node_id = "previous_node_id"
        
        # Mock database operations
        mock_cursor = mock_db_manager.get_connection.return_value.cursor.return_value
        
        # Add a user message
        result = conversation.add_user_message("Test user message")
        
        # Check database operations were performed
        mock_cursor.execute.assert_called()
        mock_db_manager.get_connection.return_value.commit.assert_called_once()
        
        # Check current_node_id was updated
        assert conversation.current_node_id != "previous_node_id"
    
    def test_add_assistant_response(self, mock_db_manager):
        """Test adding an assistant response."""
        # Initialize conversation
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id"
        )
        
        # Mock the current_node_id
        conversation.current_node_id = "previous_node_id"
        
        # Mock database operations
        mock_cursor = mock_db_manager.get_connection.return_value.cursor.return_value
        
        # Add an assistant response
        result = conversation.add_assistant_response(
            "Test assistant response",
            model_info={"model": "gpt-4o"},
            parameters={"temperature": 0.7},
            token_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            response_id="resp_123456"
        )
        
        # Check database operations were performed
        mock_cursor.execute.assert_called()
        mock_db_manager.get_connection.return_value.commit.assert_called_once()
        
        # Check current_node_id was updated
        assert conversation.current_node_id != "previous_node_id"
    
    def test_navigate_to_node(self, mock_db_manager):
        """Test navigating to a specific node."""
        # Initialize conversation
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id"
        )
        
        # Mock the current_node_id
        conversation.current_node_id = "old_node_id"
        
        # Mock database queries
        mock_cursor = mock_db_manager.get_connection.return_value.cursor.return_value
        mock_cursor.fetchone.return_value = {'id': 'target_node_id'}
        
        # Navigate to node
        result = conversation.navigate_to_node("target_node_id")
        
        # Check navigation was successful
        assert result is True
        assert conversation.current_node_id == "target_node_id"
        
        # Check database operations were performed
        mock_cursor.execute.assert_called()
        mock_db_manager.get_connection.return_value.commit.assert_called_once()
    
    def test_retry_current_response(self, mock_db_manager):
        """Test retrying the current response."""
        # Initialize conversation
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id"
        )
        
        # Mock the current_node
        mock_node = MagicMock()
        mock_node.role = "assistant"
        mock_node.parent_id = "parent_id"
        conversation.current_node = mock_node
        
        # Mock the navigate_to_node method
        conversation.navigate_to_node = MagicMock(return_value=True)
        
        # Retry current response
        result = conversation.retry_current_response()
        
        # Check retry was successful
        assert result is True
        
        # Check navigate_to_node was called with parent_id
        conversation.navigate_to_node.assert_called_once_with("parent_id")
    
    def test_get_current_branch(self, mock_db_manager):
        """Test getting the current conversation branch."""
        # Initialize conversation
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id"
        )
        
        # Mock the current_node and its get_path_to_root method
        mock_node = MagicMock()
        mock_branch = ["root_node", "user_node", "assistant_node"]
        mock_node.get_path_to_root.return_value = mock_branch
        conversation.current_node = mock_node
        
        # Get current branch
        branch = conversation.get_current_branch()
        
        # Check branch was retrieved correctly
        assert branch == mock_branch
        mock_node.get_path_to_root.assert_called_once()
    
    def test_get_current_messages(self, mock_db_manager):
        """Test getting messages for the current branch."""
        # Initialize conversation
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id"
        )
        
        # Mock the current_node and its get_messages_to_root method
        mock_node = MagicMock()
        mock_messages = [
            {"role": "system", "content": "System message"},
            {"role": "user", "content": "User message"},
            {"role": "assistant", "content": "Assistant message"}
        ]
        mock_node.get_messages_to_root.return_value = mock_messages
        conversation.current_node = mock_node
        
        # Get current messages
        messages = conversation.get_current_messages()
        
        # Check messages were retrieved correctly
        assert messages == mock_messages
        mock_node.get_messages_to_root.assert_called_once()

    def test_to_dict(self, mock_db_manager):
        """Test converting a conversation to a dictionary."""
        # Initialize conversation
        conversation = DBConversationTree(
            mock_db_manager,
            id="test_conv_id",
            name="Test Conversation",
            system_message="System message"
        )

        # Explicitly set ID to override any mock behavior
        conversation.id = "test_conv_id"

        # Mock properties
        conversation.created_at = "2023-01-01T12:00:00"
        conversation.modified_at = "2023-01-01T13:00:00"
        conversation.current_node_id = "current_id"

        # Mock the root property
        mock_root = MagicMock()
        mock_root.to_dict.return_value = {"id": "root_id", "role": "system", "content": "System message"}
        conversation.root = mock_root

        # Override all properties that might be affected by mocking
        conversation.id = "test_conv_id"
        conversation.name = "Test Conversation"

        # Create a more robust setup that bypasses the _load_conversation method
        # This is a good approach when testing methods that rely on database state
        if hasattr(conversation, '_load_conversation'):
            # Replace the method with a mock that does nothing
            original_load = conversation._load_conversation
            conversation._load_conversation = lambda x: None

            # Re-initialize key properties
            conversation.id = "test_conv_id"
            conversation.name = "Test Conversation"
            conversation.created_at = "2023-01-01T12:00:00"
            conversation.modified_at = "2023-01-01T13:00:00"
            conversation.current_node_id = "current_id"

        # Convert to dictionary
        conv_dict = conversation.to_dict()

        # Check dictionary has the correct structure
        assert conv_dict["id"] == "test_conv_id"
        assert conv_dict["name"] == "Test Conversation"
        assert conv_dict["created_at"] == "2023-01-01T12:00:00"
        assert conv_dict["modified_at"] == "2023-01-01T13:00:00"
        assert conv_dict["current_node_id"] == "current_id"
        assert conv_dict["root"]["id"] == "root_id"
        assert conv_dict["root"]["role"] == "system"
