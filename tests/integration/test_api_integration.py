"""
Integration tests for API to database flow.
"""

import os
import sys
import pytest
import tempfile
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import QCoreApplication

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.services.api import OpenAIAPIWorker, OpenAIThreadManager
from src.models.db_conversation import DBConversationTree, DBMessageNode
from src.models.db_manager import DatabaseManager


class TestAPIToDatabaseFlow:
    """Integration tests for API to database flow."""
    
    @pytest.fixture
    def setup_test_environment(self):
        """Set up test environment with mock API and real database."""
        # Create a temporary database
        temp_db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        temp_db_path = temp_db_file.name
        temp_db_file.close()
        
        # Create a real database manager with the temporary database
        db_manager = DatabaseManager(db_path=temp_db_path)
        
        # Create a test conversation
        conversation = DBConversationTree(
            db_manager,
            name="Test API Integration",
            system_message="You are a helpful assistant for testing API integration."
        )
        
        # Add a user message to the conversation
        user_message = conversation.add_user_message("Hello, this is a test message.")
        
        # Create OpenAI API mock
        with patch('openai.OpenAI') as mock_openai:
            # Mock response for non-streaming
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.output_text = "This is a test response."
            mock_response.model = "gpt-4o"
            mock_response.id = "resp_123456789"
            mock_response.usage = MagicMock()
            mock_response.usage.input_tokens = 10
            mock_response.usage.output_tokens = 20
            mock_response.usage.total_tokens = 30
            
            mock_client.responses.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            # Set up the thread manager
            thread_manager = OpenAIThreadManager()
            
            yield conversation, db_manager, thread_manager, mock_openai, mock_client
        
        # Clean up temporary database
        os.unlink(temp_db_path)

    def test_api_to_database_non_streaming(self, setup_test_environment):
        """Test API call and database storage with non-streaming response."""
        conversation, db_manager, thread_manager, mock_openai, mock_client = setup_test_environment

        # Set up test settings
        settings = {
            "api_key": "test_api_key",
            "api_type": "responses",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": False
        }

        # Get messages to send to the API
        messages = conversation.get_current_messages()

        # Create worker with the current conversation's messages
        thread_id, worker = thread_manager.create_worker(messages, settings)

        # Set up signal handlers to update the database
        def handle_message(content):
            # Add assistant response to the conversation
            conversation.add_assistant_response(
                content,
                model_info={"model": "gpt-4o"},
                token_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                response_id="resp_123456789"
            )

        def handle_usage_info(info):
            # Update token usage in the database
            if conversation.current_node.role == "assistant":
                # Updated token usage is stored in the current node
                conversation.current_node.token_usage = info

        def handle_system_info(info):
            # Update model info in the database
            if conversation.current_node.role == "assistant":
                # Updated model info is stored in the current node
                conversation.current_node.model_info = info

        def handle_completion_id(response_id):
            # Update response ID in the database
            conn = db_manager.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                '''
                UPDATE messages SET response_id = ? WHERE id = ?
                ''',
                (response_id, conversation.current_node.id)
            )

            # Update in-memory response ID
            conversation.current_node.response_id = response_id

            conn.commit()
            conn.close()

        # Connect signals
        worker.message_received.connect(handle_message)
        worker.usage_info.connect(handle_usage_info)
        worker.system_info.connect(handle_system_info)
        worker.completion_id.connect(handle_completion_id)  # Connect completion_id signal
    
    def test_api_to_database_streaming(self, setup_test_environment):
        """Test API call and database storage with streaming response."""
        conversation, db_manager, thread_manager, mock_openai, mock_client = setup_test_environment
        
        # Set up test settings
        settings = {
            "api_key": "test_api_key",
            "api_type": "responses",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_output_tokens": 1024,
            "stream": True
        }
        
        # Mock streaming response
        mock_stream = MagicMock()
        
        # Create a series of stream events
        stream_events = []
        
        # First event with delta = "This is "
        event1 = MagicMock()
        event1.type = "response.output_text.delta"
        event1.delta = "This is "
        stream_events.append(event1)
        
        # Second event with delta = "a test "
        event2 = MagicMock()
        event2.type = "response.output_text.delta"
        event2.delta = "a test "
        stream_events.append(event2)
        
        # Third event with delta = "streaming response."
        event3 = MagicMock()
        event3.type = "response.output_text.delta"
        event3.delta = "streaming response."
        stream_events.append(event3)
        
        # Final completion event
        event4 = MagicMock()
        event4.type = "response.completed"
        event4.response = MagicMock()
        event4.response.id = "resp_streaming_123"
        event4.response.model = "gpt-4o"
        event4.response.usage = MagicMock()
        event4.response.usage.input_tokens = 10
        event4.response.usage.output_tokens = 20
        event4.response.usage.total_tokens = 30
        stream_events.append(event4)
        
        # Configure mock to iterate through events
        mock_stream.__iter__.return_value = iter(stream_events)
        mock_client.responses.create.return_value = mock_stream
        
        # Get messages to send to the API
        messages = conversation.get_current_messages()
        
        # Create worker with the current conversation's messages
        thread_id, worker = thread_manager.create_worker(messages, settings)
        
        # Initialize state variables to simulate UI handling
        is_first_chunk = True
        accumulated_content = ""
        
        # Set up signal handlers to update the database
        def handle_chunk(chunk):
            nonlocal is_first_chunk, accumulated_content
            
            # Accumulate content
            accumulated_content += chunk
            
            # First chunk needs special handling
            if is_first_chunk:
                # Create a new assistant node for the first chunk
                conversation.add_assistant_response(chunk)
                is_first_chunk = False
            else:
                # Update the existing node with new content
                conn = db_manager.get_connection()
                cursor = conn.cursor()
                
                # Update with the full accumulated content to ensure consistency
                cursor.execute(
                    '''
                    UPDATE messages SET content = ? WHERE id = ?
                    ''',
                    (accumulated_content, conversation.current_node.id)
                )
                
                # Update in-memory content too
                conversation.current_node.content = accumulated_content
                
                conn.commit()
                conn.close()
        
        def handle_final_message(content):
            # Ensure the final content is stored correctly
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            
            # Update with the complete final content
            cursor.execute(
                '''
                UPDATE messages SET content = ? WHERE id = ?
                ''',
                (content, conversation.current_node.id)
            )
            
            # Update in-memory content
            conversation.current_node.content = content
            
            conn.commit()
            conn.close()
        
        def handle_usage_info(info):
            # Update token usage in the database
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            
            # Store token usage as metadata
            cursor.execute(
                'DELETE FROM message_metadata WHERE message_id = ? AND metadata_type LIKE ?',
                (conversation.current_node.id, 'token_usage.%')
            )
            
            for key, value in info.items():
                import json
                cursor.execute(
                    '''
                    INSERT INTO message_metadata (message_id, metadata_type, metadata_value)
                    VALUES (?, ?, ?)
                    ''',
                    (conversation.current_node.id, f"token_usage.{key}", json.dumps(value))
                )
            
            # Update in-memory token usage
            conversation.current_node.token_usage = info
            
            conn.commit()
            conn.close()
        
        def handle_system_info(info):
            # Update model info in the database
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            
            # Store model info as metadata
            cursor.execute(
                'DELETE FROM message_metadata WHERE message_id = ? AND metadata_type LIKE ?',
                (conversation.current_node.id, 'model_info.%')
            )
            
            for key, value in info.items():
                import json
                cursor.execute(
                    '''
                    INSERT INTO message_metadata (message_id, metadata_type, metadata_value)
                    VALUES (?, ?, ?)
                    ''',
                    (conversation.current_node.id, f"model_info.{key}", json.dumps(value))
                )
            
            # Update in-memory model info
            conversation.current_node.model_info = info
            
            conn.commit()
            conn.close()
        
        def handle_completion_id(response_id):
            # Update response ID in the database
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                '''
                UPDATE messages SET response_id = ? WHERE id = ?
                ''',
                (response_id, conversation.current_node.id)
            )
            
            # Update in-memory response ID
            conversation.current_node.response_id = response_id
            
            conn.commit()
            conn.close()
        
        # Connect signals
        worker.chunk_received.connect(handle_chunk)
        worker.message_received.connect(handle_final_message)
        worker.usage_info.connect(handle_usage_info)
        worker.system_info.connect(handle_system_info)
        worker.completion_id.connect(handle_completion_id)
        
        # Process the API call
        worker.process()
        
        # Check that the OpenAI client was called correctly
        mock_openai.assert_called_once()
        assert mock_openai.call_args[1]["api_key"] == "test_api_key"
        
        # Verify responses.create was called with the right parameters
        mock_client.responses.create.assert_called_once()
        call_args = mock_client.responses.create.call_args[1]
        assert call_args["model"] == "gpt-4o"
        assert call_args["temperature"] == 0.7
        assert call_args["max_output_tokens"] == 1024
        assert call_args["stream"] is True
        
        # Verify that the assistant response was added to the conversation
        current_node = conversation.current_node
        assert current_node.role == "assistant"
        assert current_node.content == "This is a test streaming response."
        assert current_node.model_info.get("model") == "gpt-4o"
        assert current_node.token_usage.get("prompt_tokens") == 10
        assert current_node.token_usage.get("completion_tokens") == 20
        assert current_node.token_usage.get("total_tokens") == 30
        assert current_node.response_id == "resp_streaming_123"
        
        # Verify that the response is stored in the database
        stored_node = conversation.get_node(current_node.id)
        assert stored_node.content == "This is a test streaming response."
        assert stored_node.model_info.get("model") == "gpt-4o"
