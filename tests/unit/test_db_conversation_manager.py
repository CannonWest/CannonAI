"""
Unit tests for the DBConversationManager class.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, Mock

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.models.db_conversation_manager import DBConversationManager
from src.models.db_conversation import DBConversationTree
from src.models.db_manager import DatabaseManager


class TestDBConversationManager:
    """Tests for the DatabaseConversationManager class."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager."""
        with patch('src.models.db_conversation_manager.DatabaseManager') as mock_class:
            mock_manager = mock_class.return_value
            
            # Configure mock connection
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_manager.get_connection.return_value = mock_conn
            
            yield mock_manager
    
    @pytest.fixture
    def mock_conversation_tree(self):
        """Create a mock conversation tree."""
        mock_tree = MagicMock(spec=DBConversationTree)
        mock_tree.id = "test-conv-id"
        mock_tree.name = "Test Conversation"
        mock_tree.created_at = "2023-01-01T12:00:00"
        mock_tree.modified_at = "2023-01-01T12:30:00"
        mock_tree.current_node_id = "node-id-1"
        
        return mock_tree
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_init(self, mock_tree_class, mock_db_manager):
        """Test initializing the conversation manager."""
        # Create the manager
        manager = DBConversationManager()
        
        # Check it has initialized correctly
        assert manager.db_manager is not None
        assert manager.conversations == {}
        assert manager.active_conversation_id is None
        assert hasattr(manager, 'logger')
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_active_conversation(self, mock_tree_class, mock_db_manager):
        """Test the active_conversation property."""
        # Create the manager
        manager = DBConversationManager()
        
        # Initially no active conversation
        assert manager.active_conversation is None
        
        # Add a conversation
        mock_conv = MagicMock()
        manager.conversations["test-id"] = mock_conv
        manager.active_conversation_id = "test-id"
        
        # Now we should get the active conversation
        assert manager.active_conversation == mock_conv
        
        # Test with unknown ID
        manager.active_conversation_id = "unknown-id"
        assert manager.active_conversation is None
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_set_active_conversation_existing(self, mock_tree_class, mock_db_manager):
        """Test setting an active conversation that's already in memory."""
        # Create the manager
        manager = DBConversationManager()
        
        # Add a conversation
        mock_conv = MagicMock()
        manager.conversations["test-id"] = mock_conv
        
        # Set it as active
        result = manager.set_active_conversation("test-id")
        
        # Check it was set correctly
        assert result is True
        assert manager.active_conversation_id == "test-id"
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_set_active_conversation_from_db(self, mock_tree_class, mock_db_manager):
        """Test setting an active conversation that needs to be loaded from DB."""
        # Configure mock cursor to find the conversation in DB
        mock_cursor = mock_db_manager.get_connection().cursor()
        mock_cursor.fetchone.return_value = {"id": "test-id"}
        
        # Create mock conversation tree
        mock_tree = MagicMock()
        mock_tree_class.return_value = mock_tree
        
        # Create the manager
        manager = DBConversationManager()
        
        # Set an active conversation that's not in memory
        result = manager.set_active_conversation("test-id")
        
        # Check it was loaded and set correctly
        assert result is True
        assert manager.active_conversation_id == "test-id"
        assert manager.conversations["test-id"] == mock_tree
        
        # Check DB query was executed
        mock_cursor.execute.assert_called_once()
        assert "SELECT id FROM conversations WHERE id = ?" in mock_cursor.execute.call_args[0][0]
        assert mock_cursor.execute.call_args[0][1] == ("test-id",)
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_set_active_conversation_not_found(self, mock_tree_class, mock_db_manager):
        """Test setting an active conversation that doesn't exist."""
        # Configure mock cursor to not find the conversation
        mock_cursor = mock_db_manager.get_connection().cursor()
        mock_cursor.fetchone.return_value = None
        
        # Create the manager
        manager = DBConversationManager()
        
        # Try to set a non-existent conversation
        result = manager.set_active_conversation("nonexistent-id")
        
        # Check it failed
        assert result is False
        assert manager.active_conversation_id is None
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_create_conversation(self, mock_tree_class, mock_db_manager):
        """Test creating a new conversation."""
        # Create mock conversation
        mock_conv = MagicMock()
        mock_conv.id = "new-conv-id"
        mock_tree_class.return_value = mock_conv
        
        # Create the manager
        manager = DBConversationManager()
        
        # Create a conversation
        result = manager.create_conversation(name="New Conversation")
        
        # Check it was created correctly
        assert result == mock_conv
        assert manager.conversations["new-conv-id"] == mock_conv
        assert manager.active_conversation_id == "new-conv-id"
        
        # Check constructor args
        mock_tree_class.assert_called_once()
        assert mock_tree_class.call_args[1]["name"] == "New Conversation"
        assert mock_tree_class.call_args[1]["system_message"] == "You are a helpful assistant."
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_get_conversation_list(self, mock_tree_class, mock_db_manager):
        """Test getting a list of all conversations."""
        # Configure mock cursor to return conversation list
        mock_cursor = mock_db_manager.get_connection().cursor()
        mock_cursor.fetchall.return_value = [
            {"id": "conv1", "name": "Conversation 1", "created_at": "2023-01-01", "modified_at": "2023-01-02"},
            {"id": "conv2", "name": "Conversation 2", "created_at": "2023-01-03", "modified_at": "2023-01-04"}
        ]
        
        # Create the manager
        manager = DBConversationManager()
        
        # Get conversation list
        result = manager.get_conversation_list()
        
        # Check it returned the expected data
        assert len(result) == 2
        assert result[0]["id"] == "conv1"
        assert result[1]["name"] == "Conversation 2"
        
        # Check DB query was executed
        mock_cursor.execute.assert_called_once()
        assert "SELECT id, name, created_at, modified_at" in mock_cursor.execute.call_args[0][0]
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_load_conversation(self, mock_tree_class, mock_db_manager, mock_conversation_tree):
        """Test loading a conversation by ID."""
        # Configure mock to return conversation
        mock_tree_class.return_value = mock_conversation_tree
        
        # Create the manager
        manager = DBConversationManager()
        
        # Load conversation
        result = manager.load_conversation("test-conv-id")
        
        # Check it returned the expected conversation
        assert result == mock_conversation_tree
        assert manager.conversations["test-conv-id"] == mock_conversation_tree
        
        # If this is the first conversation, it should be set as active
        assert manager.active_conversation_id == "test-conv-id"
        
        # Check constructor args
        mock_tree_class.assert_called_once()
        assert mock_tree_class.call_args[1]["id"] == "test-conv-id"
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_load_conversation_cached(self, mock_tree_class, mock_db_manager):
        """Test loading a conversation that's already cached."""
        # Add a conversation to cache
        mock_conv = MagicMock()
        
        # Create the manager
        manager = DBConversationManager()
        manager.conversations["cached-id"] = mock_conv
        
        # Load the cached conversation
        result = manager.load_conversation("cached-id")
        
        # Check it returned the cached one without creating a new one
        assert result == mock_conv
        mock_tree_class.assert_not_called()
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_load_all(self, mock_tree_class, mock_db_manager):
        """Test loading all conversations from the database."""
        # Configure mock to return conversation list
        mock_cursor = mock_db_manager.get_connection().cursor()
        mock_cursor.fetchall.return_value = [
            {"id": "conv1", "name": "Conversation 1", "created_at": "2023-01-01", "modified_at": "2023-01-02"},
            {"id": "conv2", "name": "Conversation 2", "created_at": "2023-01-03", "modified_at": "2023-01-04"}
        ]
        
        # Create mock conversation trees
        mock_conv1 = MagicMock()
        mock_conv1.id = "conv1"
        mock_conv1.name = "Conversation 1"
        
        mock_conv2 = MagicMock()
        mock_conv2.id = "conv2"
        mock_conv2.name = "Conversation 2"
        
        mock_tree_class.side_effect = [mock_conv1, mock_conv2]
        
        # Create the manager and patch load_conversation
        manager = DBConversationManager()
        manager.load_conversation = MagicMock(side_effect=[mock_conv1, mock_conv2])

        # Need to add an extra instance of mock_conv1 to handle the third call in load_all()
        manager.load_conversation = MagicMock(side_effect=[mock_conv1, mock_conv2, mock_conv1])

        # Load all conversations
        manager.load_all()
        
        # Check conversations were loaded
        assert manager.load_conversation.call_count >= 2
        manager.load_conversation.assert_any_call("conv1")
        manager.load_conversation.assert_any_call("conv2")

    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_delete_conversation(self, mock_tree_class, mock_db_manager):
        """Test deleting a conversation."""
        # Create the manager
        manager = DBConversationManager()
        
        # Add a conversation to cache
        mock_conv = MagicMock()
        manager.conversations["test-id"] = mock_conv
        manager.active_conversation_id = "test-id"
        
        # Configure mock cursor for get_conversation_list after deletion
        mock_cursor = mock_db_manager.get_connection().cursor()
        mock_cursor.fetchall.return_value = [
            {"id": "other-id", "name": "Other Conversation"}
        ]
        
        # Delete the conversation
        result = manager.delete_conversation("test-id")
        
        # Check it was deleted
        assert result is True
        assert "test-id" not in manager.conversations
        assert manager.active_conversation_id != "test-id"
        
        # Check DB query was executed
        mock_cursor.execute.assert_any_call(
            'DELETE FROM conversations WHERE id = ?',
            ("test-id",)
        )
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_search_conversations(self, mock_tree_class, mock_db_manager):
        """Test searching through conversations."""
        # Configure mock cursor to return search results
        mock_cursor = mock_db_manager.get_connection().cursor()
        mock_cursor.fetchall.return_value = [
            {
                "id": "msg1", 
                "conversation_id": "conv1", 
                "conversation_name": "Conversation 1",
                "role": "user", 
                "content": "search term here", 
                "timestamp": "2023-01-01"
            },
            {
                "id": "msg2", 
                "conversation_id": "conv2", 
                "conversation_name": "Conversation 2",
                "role": "assistant", 
                "content": "reply with search term", 
                "timestamp": "2023-01-02"
            }
        ]
        
        # Create the manager
        manager = DBConversationManager()
        
        # Search for a term
        results = manager.search_conversations("search term")
        
        # Check search returned expected results
        assert len(results) == 2
        assert results[0]["id"] == "msg1"
        assert results[0]["conversation_name"] == "Conversation 1"
        assert results[1]["role"] == "assistant"
        
        # Check DB query was executed
        mock_cursor.execute.assert_called_once()
        assert "SELECT m.id, m.conversation_id, m.role, m.content" in mock_cursor.execute.call_args[0][0]
        assert mock_cursor.execute.call_args[0][1] == ["%search term%"]
    
    @patch('src.models.db_conversation_manager.DBConversationTree')
    def test_search_conversations_with_filters(self, mock_tree_class, mock_db_manager):
        """Test searching with conversation and role filters."""
        # Configure mock cursor to return search results
        mock_cursor = mock_db_manager.get_connection().cursor()
        mock_cursor.fetchall.return_value = [
            {
                "id": "msg1", 
                "conversation_id": "conv1", 
                "conversation_name": "Conversation 1",
                "role": "user", 
                "content": "search term", 
                "timestamp": "2023-01-01"
            }
        ]
        
        # Create the manager
        manager = DBConversationManager()
        
        # Search with filters
        results = manager.search_conversations("search term", conversation_id="conv1", role_filter="user")
        
        # Check search returned expected results
        assert len(results) == 1
        assert results[0]["id"] == "msg1"
        
        # Check DB query was executed with filters
        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        
        assert "WHERE m.content LIKE ?" in query
        assert "AND m.conversation_id = ?" in query
        assert "AND m.role = ?" in query
        assert params == ["%search term%", "conv1", "user"]
