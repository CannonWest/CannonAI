"""
Tests for the MainWindow UI component.
"""

import os
import sys
import pytest
import tempfile
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt, QCoreApplication

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.ui.main_window import MainWindow
from src.models.db_conversation_manager import DBConversationManager
from src.models.db_conversation import DBConversationTree
from src.ui.conversation import ConversationBranchTab


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
def mock_settings_manager():
    """Create a mock settings manager."""
    with patch('src.services.storage.SettingsManager') as mock_class:
        mock_manager = mock_class.return_value
        mock_manager.get_settings.return_value = {
            "api_key": "test_api_key",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": True
        }
        yield mock_manager


@pytest.fixture
def mock_conversation_manager():
    """Create a mock conversation manager."""
    with patch('src.models.db_conversation_manager.DBConversationManager') as mock_class:
        mock_manager = mock_class.return_value
        
        # Mock conversation creation
        mock_conversation = MagicMock(spec=DBConversationTree)
        mock_conversation.id = "test_conv_id"
        mock_conversation.name = "Test Conversation"
        mock_manager.create_conversation.return_value = mock_conversation
        
        # Mock active conversation getter
        mock_manager.active_conversation = mock_conversation
        
        # Mock get_conversation_list
        mock_manager.get_conversation_list.return_value = [
            {"id": "test_conv_id", "name": "Test Conversation"}
        ]
        
        yield mock_manager


@pytest.fixture
def mock_thread_manager():
    """Create a mock thread manager."""
    with patch('src.services.api.OpenAIThreadManager') as mock_class:
        mock_manager = mock_class.return_value
        mock_worker = MagicMock()
        mock_manager.create_worker.return_value = ("thread_123", mock_worker)
        yield mock_manager


class TestMainWindow:
    """Tests for the MainWindow UI component."""
    
    @patch('src.ui.main_window.SettingsManager')
    @patch('src.ui.main_window.DBConversationManager')
    @patch('src.ui.main_window.DatabaseManager')
    @patch('src.ui.main_window.OpenAIThreadManager')
    def test_init(self, mock_thread_manager_class, mock_db_manager_class,
                  mock_conversation_manager_class, mock_settings_manager_class,
                  qapp):
        """Test main window initialization."""
        # Configure mocks
        mock_settings_manager = mock_settings_manager_class.return_value
        mock_settings_manager.get_settings.return_value = {"api_key": "test_key"}
        
        mock_conversation_manager = mock_conversation_manager_class.return_value
        mock_conversation_manager.active_conversation = None
        
        # Create main window
        window = MainWindow()
        
        # Check the window was initialized correctly
        assert hasattr(window, 'settings_manager')
        assert hasattr(window, 'settings')
        assert hasattr(window, 'thread_manager')
        assert hasattr(window, 'conversation_manager')
        assert hasattr(window, 'db_manager')
        assert hasattr(window, 'tabs')
        
        # Check managers were initialized
        mock_settings_manager_class.assert_called_once()
        mock_conversation_manager_class.assert_called_once()
        mock_db_manager_class.assert_called_once()
        mock_thread_manager_class.assert_called_once()
        
        # Should have created a default conversation if none exists
        assert mock_conversation_manager.create_conversation.called
    
    @patch('src.ui.main_window.ConversationBranchTab')
    def test_create_new_conversation(self, mock_tab_class, qapp, mock_settings_manager, 
                                    mock_conversation_manager, mock_thread_manager):
        """Test creating a new conversation."""
        # Configure mocks
        mock_tab = mock_tab_class.return_value
        
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager):
            
            window = MainWindow()
            
            # Reset call counts from initialization
            mock_conversation_manager.create_conversation.reset_mock()
            mock_tab_class.reset_mock()
            
            # Call create_new_conversation
            window.create_new_conversation()
            
            # Check a new conversation was created
            mock_conversation_manager.create_conversation.assert_called_once()
            
            # Check a new tab was created with the conversation
            mock_tab_class.assert_called_once()
            
            # Check tab was added to tabs widget
            assert window.tabs.addTab.called
    
    def test_add_conversation_tab(self, qapp, mock_settings_manager, 
                                 mock_conversation_manager, mock_thread_manager):
        """Test adding a conversation tab."""
        # Create a mock conversation
        mock_conversation = MagicMock(spec=DBConversationTree)
        mock_conversation.id = "test_conv_id"
        mock_conversation.name = "Test Conversation"
        
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager), \
             patch('src.ui.main_window.ConversationBranchTab') as mock_tab_class:
            
            # Configure mock tab
            mock_tab = mock_tab_class.return_value
            
            window = MainWindow()
            
            # Reset call counts from initialization
            mock_tab_class.reset_mock()
            window.tabs.addTab.reset_mock()
            
            # Call add_conversation_tab
            window.add_conversation_tab(mock_conversation)
            
            # Check a new tab was created with the conversation
            mock_tab_class.assert_called_once_with(mock_conversation)
            
            # Check tab signals were connected
            assert mock_tab.send_message.connect.called
            assert mock_tab.retry_request.connect.called
            assert mock_tab.branch_changed.connect.called
            
            # Check tab was added to tabs widget
            assert window.tabs.addTab.called
    
    @patch('src.ui.main_window.SettingsDialog')
    def test_open_settings(self, mock_dialog_class, qapp, mock_settings_manager, 
                          mock_conversation_manager, mock_thread_manager):
        """Test opening the settings dialog."""
        # Configure mock dialog
        mock_dialog = mock_dialog_class.return_value
        mock_dialog.exec.return_value = True  # Dialog accepted
        mock_dialog.get_settings.return_value = {
            "api_key": "new_test_key",
            "model": "gpt-4o-mini"
        }
        
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager):
            
            window = MainWindow()
            
            # Call open_settings
            window.open_settings()
            
            # Check dialog was created with current settings
            mock_dialog_class.assert_called_once_with(window.settings, window)
            
            # Check dialog was executed
            mock_dialog.exec.assert_called_once()
            
            # Check settings were updated
            assert window.settings == mock_dialog.get_settings.return_value
            mock_settings_manager.update_settings.assert_called_once_with(mock_dialog.get_settings.return_value)
    
    def test_send_message(self, qapp, mock_settings_manager, 
                         mock_conversation_manager, mock_thread_manager):
        """Test sending a message."""
        # Create a mock tab
        mock_tab = MagicMock(spec=ConversationBranchTab)
        mock_tab.conversation_tree.get_current_messages.return_value = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Test message"}
        ]
        mock_tab._pending_attachments = None
        
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager):
            
            window = MainWindow()
            
            # Reset call counts from initialization
            mock_thread_manager.create_worker.reset_mock()
            mock_thread_manager.start_worker.reset_mock()
            
            # Call send_message
            window.send_message(mock_tab, "Test message")
            
            # Check an API worker was created
            mock_thread_manager.create_worker.assert_called_once()
            
            # Check work thread was started
            mock_thread_manager.start_worker.assert_called_once()
            
            # Check tab loading indicator was started
            mock_tab.start_loading_indicator.assert_called_once()
    
    def test_retry_message(self, qapp, mock_settings_manager, 
                          mock_conversation_manager, mock_thread_manager):
        """Test retrying a message."""
        # Create a mock tab
        mock_tab = MagicMock(spec=ConversationBranchTab)
        mock_tab.conversation_tree.get_current_messages.return_value = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Test message"}
        ]
        
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager):
            
            window = MainWindow()
            
            # Reset call counts from initialization
            mock_thread_manager.create_worker.reset_mock()
            mock_thread_manager.start_worker.reset_mock()
            
            # Call retry_message
            window.retry_message(mock_tab)
            
            # Check an API worker was created
            mock_thread_manager.create_worker.assert_called_once()
            
            # Check worker thread was started
            mock_thread_manager.start_worker.assert_called_once()
            
            # Check tab loading indicator was started
            mock_tab.start_loading_indicator.assert_called_once()
    
    def test_handle_assistant_response(self, qapp, mock_settings_manager, 
                                      mock_conversation_manager, mock_thread_manager):
        """Test handling an assistant response."""
        # Create a mock tab
        mock_tab = MagicMock(spec=ConversationBranchTab)
        mock_tab.conversation_tree.add_assistant_response.return_value = MagicMock()
        
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager):
            
            window = MainWindow()
            
            # Call handle_assistant_response
            window.handle_assistant_response(mock_tab, "Test response", "resp_123456")
            
            # Check loading indicator was stopped
            mock_tab.stop_loading_indicator.assert_called_once()
            
            # Check response was added to conversation
            mock_tab.conversation_tree.add_assistant_response.assert_called_once_with(
                "Test response",
                model_info={},
                token_usage={},
                response_id="resp_123456"
            )
            
            # Check UI was updated
            mock_tab.update_ui.assert_called_once()
            
            # Check conversation was saved
            assert window.save_conversation.called
    
    def test_handle_error(self, qapp, mock_settings_manager, 
                         mock_conversation_manager, mock_thread_manager):
        """Test handling an API error."""
        # Create a mock tab
        mock_tab = MagicMock(spec=ConversationBranchTab)
        
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager), \
             patch('src.ui.main_window.QMessageBox') as mock_message_box:
            
            window = MainWindow()
            
            # Set the current tab
            window.tabs.currentWidget = MagicMock(return_value=mock_tab)
            
            # Call handle_error
            window.handle_error("Test error message")
            
            # Check loading indicator was stopped
            mock_tab.stop_loading_indicator.assert_called_once()
            
            # Check error box was shown
            mock_message_box.Critical.assert_called_once()
    
    def test_save_conversation(self, qapp, mock_settings_manager, 
                              mock_conversation_manager, mock_thread_manager):
        """Test saving a conversation."""
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager):
            
            window = MainWindow()
            
            # Reset call counts from initialization
            mock_conversation_manager.save_conversation.reset_mock()
            
            # Call save_conversation
            window.save_conversation("test_conv_id")
            
            # Check save_conversation was called on the manager
            mock_conversation_manager.save_conversation.assert_called_once_with("test_conv_id")
    
    def test_save_conversations(self, qapp, mock_settings_manager, 
                               mock_conversation_manager, mock_thread_manager):
        """Test saving all conversations."""
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager), \
             patch('src.ui.main_window.QMessageBox') as mock_message_box:
            
            window = MainWindow()
            
            # Reset call counts from initialization
            mock_conversation_manager.save_all.reset_mock()
            
            # Call save_conversations
            window.save_conversations()
            
            # Check save_all was called on the manager
            mock_conversation_manager.save_all.assert_called_once()
            
            # Check success message was shown
            mock_message_box.information.assert_called_once()
    
    def test_close_tab(self, qapp, mock_settings_manager, 
                      mock_conversation_manager, mock_thread_manager):
        """Test closing a conversation tab."""
        # Create mock tabs
        mock_tab1 = MagicMock(spec=ConversationBranchTab)
        mock_tab1.conversation_tree.id = "test_conv_id1"
        
        mock_tab2 = MagicMock(spec=ConversationBranchTab)
        mock_tab2.conversation_tree.id = "test_conv_id2"
        
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager), \
             patch('src.ui.main_window.QMessageBox') as mock_message_box:
            
            window = MainWindow()
            
            # Mock tabs widget to have 2 tabs
            window.tabs.count = MagicMock(return_value=2)
            window.tabs.widget = MagicMock(side_effect=[mock_tab1, mock_tab2])
            
            # Reset call counts from initialization
            mock_conversation_manager.delete_conversation.reset_mock()
            
            # Call close_tab
            window.close_tab(0)  # Close first tab
            
            # Check removeTab was called
            window.tabs.removeTab.assert_called_once_with(0)
            
            # Check tab was deleted
            mock_tab1.deleteLater.assert_called_once()
            
            # Check conversation was deleted
            mock_conversation_manager.delete_conversation.assert_called_once_with("test_conv_id1")
    
    def test_close_tab_last_tab(self, qapp, mock_settings_manager, 
                               mock_conversation_manager, mock_thread_manager):
        """Test attempt to close the last tab."""
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager), \
             patch('src.ui.main_window.QMessageBox') as mock_message_box:
            
            window = MainWindow()
            
            # Mock tabs widget to have only 1 tab
            window.tabs.count = MagicMock(return_value=1)
            
            # Call close_tab
            window.close_tab(0)  # Try to close the only tab
            
            # Check warning was shown
            mock_message_box.warning.assert_called_once()
            
            # Check removeTab was not called
            window.tabs.removeTab.assert_not_called()
    
    @patch('src.ui.main_window.QInputDialog')
    def test_rename_conversation_at_index(self, mock_input_dialog, qapp, mock_settings_manager, 
                                         mock_conversation_manager, mock_thread_manager):
        """Test renaming a conversation."""
        # Create a mock tab
        mock_tab = MagicMock(spec=ConversationBranchTab)
        mock_tab.conversation_tree.name = "Old Name"
        
        # Configure input dialog to return a new name
        mock_input_dialog.getText.return_value = ("New Name", True)
        
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager):
            
            window = MainWindow()
            
            # Mock tabs widget to return our mock tab
            window.tabs.widget = MagicMock(return_value=mock_tab)
            
            # Call rename_conversation_at_index
            window.rename_conversation_at_index(0)
            
            # Check input dialog was shown with current name
            mock_input_dialog.getText.assert_called_once()
            assert mock_input_dialog.getText.call_args[1]["text"] == "Old Name"
            
            # Check conversation name was updated
            assert mock_tab.conversation_tree.update_name.called
            mock_tab.conversation_tree.update_name.assert_called_once_with("New Name")
            
            # Check tab text was updated
            window.tabs.setTabText.assert_called_once_with(0, "New Name")
            
            # Check conversation was saved
            assert window.save_conversation.called
    
    def test_closeEvent(self, qapp, mock_settings_manager, 
                        mock_conversation_manager, mock_thread_manager):
        """Test handling of application close event."""
        # Set up main window with mocked dependencies
        with patch('src.ui.main_window.SettingsManager', return_value=mock_settings_manager), \
             patch('src.ui.main_window.DBConversationManager', return_value=mock_conversation_manager), \
             patch('src.ui.main_window.DatabaseManager'), \
             patch('src.ui.main_window.OpenAIThreadManager', return_value=mock_thread_manager):
            
            window = MainWindow()
            
            # Reset call counts from initialization
            mock_thread_manager.cancel_all.reset_mock()
            mock_conversation_manager.save_all.reset_mock()
            
            # Create mock close event
            mock_event = MagicMock()
            
            # Call closeEvent
            window.closeEvent(mock_event)
            
            # Check all active API calls were cancelled
            mock_thread_manager.cancel_all.assert_called_once()
            
            # Check all conversations were saved
            mock_conversation_manager.save_all.assert_called_once()
            
            # Check event was accepted
            mock_event.accept.assert_called_once()
