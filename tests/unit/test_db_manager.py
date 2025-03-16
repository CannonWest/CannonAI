"""
Unit tests for the DatabaseManager class.
"""

import os
import sys
import json
import pytest
import sqlite3
import tempfile
import hashlib
from unittest.mock import MagicMock, patch, mock_open

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.models.db_manager import DatabaseManager
from src.models.db_conversation import DBMessageNode
from PyQt6.QtCore import QUuid


@pytest.fixture
def mock_uuid():
    """Mock QUuid for predictable test IDs."""
    with patch.object(QUuid, 'createUuid') as mock:
        mock.return_value = "test-uuid-1234"
        yield mock


class TestDatabaseManager:
    """Tests for the DatabaseManager class that handles SQLite database operations."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
            temp_db_path = temp_file.name

        yield temp_db_path

        # Cleanup after tests
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

    @pytest.fixture
    def temp_file_storage_dir(self):
        """Create a temporary directory for file storage."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir

        # Cleanup after tests (recursive)
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def db_manager(self, temp_db_path):
        """Create a database manager instance."""
        return DatabaseManager(db_path=temp_db_path)

    def test_init(self, temp_db_path):
        """Test database manager initialization."""
        db_manager = DatabaseManager(db_path=temp_db_path)

        # Check the manager has initialized correctly
        assert db_manager.db_path == temp_db_path
        assert hasattr(db_manager, 'logger')

        # Check the database file exists
        assert os.path.exists(temp_db_path)

    def test_get_connection(self, db_manager):
        """Test getting a database connection."""
        # Get a connection
        conn = db_manager.get_connection()

        # Check it's a valid SQLite connection
        assert isinstance(conn, sqlite3.Connection)

        # Check it has row factory set
        assert conn.row_factory == sqlite3.Row

        # Close the connection
        conn.close()

    def test_initialize_database(self, db_manager):
        """Test database initialization with required tables."""
        # Get a connection to check tables
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        # Query for list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in cursor.fetchall()]

        # Check required tables exist
        required_tables = [
            'conversations',
            'messages',
            'message_metadata',
            'file_attachments',
            'reasoning_steps',
            'file_contents'  # New table in updated schema
        ]

        for table in required_tables:
            assert table in tables

        # Check file_attachments has all expected columns
        cursor.execute("PRAGMA table_info(file_attachments)")
        columns = {row['name'] for row in cursor.fetchall()}

        expected_columns = {
            'id', 'message_id', 'file_name', 'display_name', 'mime_type',
            'content', 'token_count', 'file_size', 'file_hash',
            'storage_type', 'content_preview', 'storage_path'
        }

        # All expected columns should be present in the new schema
        assert expected_columns.issubset(columns)

        # Close the connection
        conn.close()

    def test_schema_migration(self, temp_db_path):
        """Test schema migration for existing databases."""
        # Create a database with old schema first
        conn = sqlite3.connect(temp_db_path)
        conn.executescript('''
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                modified_at TEXT NOT NULL,
                current_node_id TEXT NOT NULL,
                system_message TEXT NOT NULL
            );
            
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                parent_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES messages(id) ON DELETE CASCADE
            );
            
            -- Old schema for file_attachments without new columns
            CREATE TABLE file_attachments (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                content TEXT NOT NULL,
                token_count INTEGER NOT NULL,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            );
        ''')

        # Insert a test file attachment
        test_content = "This is test file content."
        conn.execute(
            '''
            INSERT INTO file_attachments (id, message_id, file_name, mime_type, content, token_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('test-file-1', 'test-message-1', 'test.txt', 'text/plain', test_content, 5)
        )
        conn.commit()
        conn.close()

        # Now create DatabaseManager which should migrate the schema
        db_manager = DatabaseManager(db_path=temp_db_path)

        # Verify schema was updated with new columns
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(file_attachments)")
        columns = {row['name'] for row in cursor.fetchall()}

        assert 'display_name' in columns
        assert 'file_size' in columns
        assert 'file_hash' in columns
        assert 'storage_type' in columns
        assert 'content_preview' in columns
        assert 'storage_path' in columns

        # Verify file_contents table was created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
        assert cursor.fetchone() is not None

        # Verify existing data was migrated properly
        cursor.execute("SELECT * FROM file_attachments WHERE id='test-file-1'")
        attachment = cursor.fetchone()

        assert attachment['file_name'] == 'test.txt'
        assert attachment['content'] == test_content
        assert attachment['file_hash'] != ""  # Should have generated a hash
        assert attachment['storage_type'] == 'database'  # Default value
        assert attachment['content_preview'] is not None
        assert len(attachment['content_preview']) <= 4096  # Preview should be limited to 4KB

        conn.close()

    def test_get_path_to_root(self, db_manager):
        """Test getting path from a node to the root node."""
        # Insert test conversation and messages
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        # Create test conversation
        cursor.execute(
            '''
            INSERT INTO conversations (id, name, created_at, modified_at, current_node_id, system_message)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('test_conv_id', 'Test Conversation', '2023-01-01', '2023-01-01', 'node3', 'System message')
        )

        # Create a chain of messages: root -> node1 -> node2 -> node3
        cursor.execute(
            '''
            INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('root', 'test_conv_id', None, 'system', 'System message', '2023-01-01')
        )

        cursor.execute(
            '''
            INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('node1', 'test_conv_id', 'root', 'user', 'User message 1', '2023-01-01')
        )

        cursor.execute(
            '''
            INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('node2', 'test_conv_id', 'node1', 'assistant', 'Assistant message', '2023-01-01')
        )

        cursor.execute(
            '''
            INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('node3', 'test_conv_id', 'node2', 'user', 'User message 2', '2023-01-01')
        )

        conn.commit()
        conn.close()

        # Get path from node3 to root
        path = db_manager.get_path_to_root('node3')

        # Check path is correct (root -> node1 -> node2 -> node3)
        assert len(path) == 4
        assert path[0].id == 'root'
        assert path[0].role == 'system'
        assert path[1].id == 'node1'
        assert path[1].role == 'user'
        assert path[2].id == 'node2'
        assert path[2].role == 'assistant'
        assert path[3].id == 'node3'
        assert path[3].role == 'user'

    def test_get_node_children(self, db_manager):
        """Test getting children of a node."""
        # Insert test conversation and messages
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        # Create test conversation
        cursor.execute(
            '''
            INSERT INTO conversations (id, name, created_at, modified_at, current_node_id, system_message)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('test_conv_id', 'Test Conversation', '2023-01-01', '2023-01-01', 'parent', 'System message')
        )

        # Create parent node
        cursor.execute(
            '''
            INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('parent', 'test_conv_id', None, 'user', 'Parent message', '2023-01-01')
        )

        # Create child nodes
        for i in range(3):
            cursor.execute(
                '''
                INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (f'child{i}', 'test_conv_id', 'parent', 'assistant', f'Child message {i}', '2023-01-01')
            )

        conn.commit()
        conn.close()

        # Get children of parent node
        children = db_manager.get_node_children('parent')

        # Check children are correct
        assert len(children) == 3
        child_ids = [child.id for child in children]
        assert 'child0' in child_ids
        assert 'child1' in child_ids
        assert 'child2' in child_ids

        # Verify child nodes are correct type and have correct properties
        for child in children:
            assert isinstance(child, DBMessageNode)
            assert child.parent_id == 'parent'
            assert child.conversation_id == 'test_conv_id'
            assert child.role == 'assistant'
            assert child.content.startswith('Child message')

    def test_get_node_metadata(self, db_manager):
        """Test getting metadata for a node."""
        # Insert test conversation, message, and metadata
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        # Create test conversation
        cursor.execute(
            '''
            INSERT INTO conversations (id, name, created_at, modified_at, current_node_id, system_message)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('test_conv_id', 'Test Conversation', '2023-01-01', '2023-01-01', 'node_id', 'System message')
        )

        # Create message
        cursor.execute(
            '''
            INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('node_id', 'test_conv_id', None, 'assistant', 'Assistant message', '2023-01-01')
        )

        # Add metadata
        metadata_pairs = [
            ('model_info.model', '"gpt-4o"'),
            ('model_info.version', '"2024-05-13"'),
            ('parameters.temperature', '0.7'),
            ('parameters.max_tokens', '1024'),
            ('token_usage.prompt_tokens', '50'),
            ('token_usage.completion_tokens', '100'),
            ('token_usage.total_tokens', '150')
        ]

        for key, value in metadata_pairs:
            cursor.execute(
                '''
                INSERT INTO message_metadata (message_id, metadata_type, metadata_value)
                VALUES (?, ?, ?)
                ''',
                ('node_id', key, value)
            )

        # Add reasoning steps
        cursor.execute(
            '''
            INSERT INTO message_metadata (message_id, metadata_type, metadata_value)
            VALUES (?, ?, ?)
            ''',
            ('node_id', 'reasoning_steps', '[{"name": "Step 1", "content": "First step content"}]')
        )

        conn.commit()
        conn.close()

        # Get metadata for node
        metadata = db_manager.get_node_metadata('node_id')

        # Unpack metadata tuple
        model_info, parameters, token_usage, reasoning_steps = metadata

        # Check metadata is correct
        assert model_info['model'] == 'gpt-4o'
        assert model_info['version'] == '2024-05-13'
        assert parameters['temperature'] == 0.7
        assert parameters['max_tokens'] == 1024
        assert token_usage['prompt_tokens'] == 50
        assert token_usage['completion_tokens'] == 100
        assert token_usage['total_tokens'] == 150
        assert len(reasoning_steps) == 1
        assert reasoning_steps[0]['name'] == 'Step 1'
        assert reasoning_steps[0]['content'] == 'First step content'

    def test_get_message(self, db_manager):
        """Test getting a message by ID."""
        # Insert test conversation and message
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        # Create test conversation
        cursor.execute(
            '''
            INSERT INTO conversations (id, name, created_at, modified_at, current_node_id, system_message)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('test_conv_id', 'Test Conversation', '2023-01-01', '2023-01-01', 'message_id', 'System message')
        )

        # Create message
        cursor.execute(
            '''
            INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('message_id', 'test_conv_id', None, 'user', 'Test message content', '2023-01-01')
        )

        conn.commit()
        conn.close()

        # Get message
        message = db_manager.get_message('message_id')

        # Check message is correct
        assert isinstance(message, DBMessageNode)
        assert message.id == 'message_id'
        assert message.conversation_id == 'test_conv_id'
        assert message.role == 'user'
        assert message.content == 'Test message content'
        assert message.timestamp == '2023-01-01'
        assert message.parent_id is None

    def test_create_node_from_db_row(self, db_manager):
        """Test creating a DBMessageNode from a database row."""
        # Create a mock row (as a dictionary that can be accessed like a sqlite3.Row)
        class MockRow(dict):
            def __getitem__(self, key):
                return super().__getitem__(key)

        row = MockRow({
            'id': 'test_id',
            'conversation_id': 'test_conv_id',
            'parent_id': 'parent_id',
            'role': 'assistant',
            'content': 'Test content',
            'timestamp': '2023-01-01',
            'response_id': 'resp_123456'
        })

        # Mock the get_node_metadata and get_node_attachments methods
        db_manager._get_node_metadata = MagicMock(return_value=(
            {'model': 'gpt-4o'},  # model_info
            {'temperature': 0.7},  # parameters
            {'prompt_tokens': 50, 'completion_tokens': 100, 'total_tokens': 150},  # token_usage
            [{'name': 'Step 1', 'content': 'Step content'}]  # reasoning_steps
        ))

        db_manager._get_node_attachments = MagicMock(return_value=[
            {
                'file_name': 'test.txt',
                'mime_type': 'text/plain',
                'content': 'Test file content',
                'token_count': 10
            }
        ])

        # Create node from row
        node = db_manager._create_node_from_db_row(row)

        # Check node was created correctly
        assert isinstance(node, DBMessageNode)
        assert node.id == 'test_id'
        assert node.conversation_id == 'test_conv_id'
        assert node.parent_id == 'parent_id'
        assert node.role == 'assistant'
        assert node.content == 'Test content'
        assert node.timestamp == '2023-01-01'
        assert node.model_info == {'model': 'gpt-4o'}
        assert node.parameters == {'temperature': 0.7}
        assert node.token_usage == {'prompt_tokens': 50, 'completion_tokens': 100, 'total_tokens': 150}
        assert len(node.attached_files) == 1
        assert node.attached_files[0]['file_name'] == 'test.txt'
        assert node._db_manager == db_manager  # DB manager reference is set
        assert hasattr(node, '_reasoning_steps')
        assert len(node._reasoning_steps) == 1

    def test_get_node_attachments(self, db_manager):
        """Test getting file attachments for a node."""
        # Insert test conversation, message, and attachment
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        # Create test conversation
        cursor.execute(
            '''
            INSERT INTO conversations (id, name, created_at, modified_at, current_node_id, system_message)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('test_conv_id', 'Test Conversation', '2023-01-01', '2023-01-01', 'message_id', 'System message')
        )

        # Create message
        cursor.execute(
            '''
            INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('message_id', 'test_conv_id', None, 'user', 'Test message content', '2023-01-01')
        )

        # Add file attachment
        file_content = "This is test file content."
        file_hash = hashlib.sha256(file_content.encode('utf-8')).hexdigest()

        cursor.execute(
            '''
            INSERT INTO file_attachments (
                id, message_id, file_name, display_name, mime_type, content, token_count,
                file_size, file_hash, storage_type, content_preview
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            ('file_id', 'message_id', 'test.txt', 'test.txt', 'text/plain', file_content,
             10, len(file_content), file_hash, 'database', file_content[:100])
        )

        conn.commit()
        conn.close()

        # Get attachments for the node
        attachments = db_manager._get_node_attachments('message_id')

        # Check attachments are correct
        assert len(attachments) == 1
        assert attachments[0]['file_name'] == 'test.txt'
        assert attachments[0]['mime_type'] == 'text/plain'
        assert attachments[0]['token_count'] == 10
        assert 'content' in attachments[0]  # Should have content or preview

    @pytest.mark.parametrize("storage_type", ["database", "disk", "hybrid", "auto"])
    def test_add_file_attachment(self, db_manager, temp_file_storage_dir, storage_type, mock_uuid):
        """Test adding a file attachment with different storage strategies."""
        # Setup file cache manager mock
        with patch('src.utils.file_utils.FileCacheManager') as MockFileCacheManager:
            mock_cache_manager = MagicMock()
            # When cache_file is called, return a path in the temp dir
            mock_cache_manager.cache_file.return_value = os.path.join(temp_file_storage_dir, "test_file.txt")
            MockFileCacheManager.return_value = mock_cache_manager

            # Insert test conversation and message
            conn = db_manager.get_connection()
            cursor = conn.cursor()

            # Create test conversation
            cursor.execute(
                '''
                INSERT INTO conversations (id, name, created_at, modified_at, current_node_id, system_message)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                ('test_conv_id', 'Test Conversation', '2023-01-01', '2023-01-01', 'message_id', 'System message')
            )

            # Create message
            cursor.execute(
                '''
                INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                ('message_id', 'test_conv_id', None, 'user', 'Test message content', '2023-01-01')
            )

            conn.commit()
            conn.close()

            # Prepare file info
            file_content = "This is a test file for attachment testing."
            file_hash = hashlib.sha256(file_content.encode('utf-8')).hexdigest()

            file_info = {
                'file_name': 'test.txt',
                'display_name': 'test_display.txt',
                'mime_type': 'text/plain',
                'content': file_content,
                'token_count': 12,
                'size': len(file_content),
                'file_hash': file_hash
            }

            # Add file attachment
            file_id = db_manager.add_file_attachment('message_id', file_info, storage_type)

            # Check attachment was added correctly
            conn = db_manager.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT * FROM file_attachments WHERE id = ?',
                (str(file_id),)
            )

            attachment = cursor.fetchone()
            assert attachment is not None
            assert attachment['file_name'] == 'test.txt'
            assert attachment['display_name'] == 'test_display.txt'
            assert attachment['token_count'] == 12

            # Check storage behavior based on type
            if storage_type == 'auto':
                # For small files, auto should choose database
                assert attachment['storage_type'] == 'database'

                # Verify content was stored
                if 'content' in attachment and attachment['content']:
                    assert attachment['content'] == file_content
                else:
                    # Check in file_contents table
                    cursor.execute(
                        'SELECT content FROM file_contents WHERE file_id = ?',
                        (str(file_id),)
                    )
                    content_row = cursor.fetchone()
                    if content_row:
                        assert content_row['content'] == file_content

            elif storage_type == 'database':
                assert attachment['storage_type'] == 'database'

                # Verify content was stored either in main table or content table
                if 'content' in attachment and attachment['content']:
                    assert attachment['content'] == file_content
                else:
                    # Check in file_contents table
                    cursor.execute(
                        'SELECT content FROM file_contents WHERE file_id = ?',
                        (str(file_id),)
                    )
                    content_row = cursor.fetchone()
                    if content_row:
                        assert content_row['content'] == file_content

            elif storage_type == 'disk':
                assert attachment['storage_type'] == 'disk'
                assert attachment['storage_path'] is not None

                # Content should be null or empty
                if 'content' in attachment:
                    assert attachment['content'] is None or attachment['content'] == ''

                # Verify FileCacheManager was called
                mock_cache_manager.cache_file.assert_called_once_with(file_content, file_hash)

            elif storage_type == 'hybrid':
                assert attachment['storage_type'] == 'hybrid'
                assert attachment['storage_path'] is not None

                # Verify content was stored (either in main table or content table)
                content_found = False

                if 'content' in attachment and attachment['content']:
                    assert attachment['content'] == file_content
                    content_found = True

                if not content_found:
                    # Check in file_contents table
                    cursor.execute(
                        'SELECT content FROM file_contents WHERE file_id = ?',
                        (str(file_id),)
                    )
                    content_row = cursor.fetchone()
                    if content_row:
                        assert content_row['content'] == file_content
                        content_found = True

                # Verify FileCacheManager was called
                mock_cache_manager.cache_file.assert_called_once_with(file_content, file_hash)

            conn.close()

    def test_get_file_attachment(self, db_manager, temp_file_storage_dir):
        """Test retrieving a file attachment with different storage types."""
        # Setup
        file_content = "This is test file content for retrieval testing."
        file_hash = hashlib.sha256(file_content.encode('utf-8')).hexdigest()
        file_size = len(file_content)

        # Setup test data for different storage types
        conn = db_manager.get_connection()
        cursor = conn.cursor()

        # Create message to attach files to
        cursor.execute(
            '''
            INSERT INTO conversations (id, name, created_at, modified_at, current_node_id, system_message)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('test_conv_id', 'Test Conversation', '2023-01-01', '2023-01-01', 'message_id', 'System message')
        )

        cursor.execute(
            '''
            INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ('message_id', 'test_conv_id', None, 'user', 'Test message content', '2023-01-01')
        )

        # 1. Create database-stored attachment
        cursor.execute(
            '''
            INSERT INTO file_attachments (
                id, message_id, file_name, display_name, mime_type, content, token_count,
                file_size, file_hash, storage_type, content_preview
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            ('file_db', 'message_id', 'db.txt', 'db.txt', 'text/plain', file_content,
             10, file_size, file_hash, 'database', file_content[:100])
        )

        # 2. Create database-stored attachment using file_contents table
        cursor.execute(
            '''
            INSERT INTO file_attachments (
                id, message_id, file_name, display_name, mime_type, token_count,
                file_size, file_hash, storage_type, content_preview
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            ('file_db_separate', 'message_id', 'db_separate.txt', 'db_separate.txt', 'text/plain',
             10, file_size, file_hash, 'database', file_content[:100])
        )

        cursor.execute(
            '''
            INSERT INTO file_contents (file_id, content)
            VALUES (?, ?)
            ''',
            ('file_db_separate', file_content)
        )

        # 3. Create disk-stored attachment
        disk_storage_path = os.path.join(temp_file_storage_dir, "disk.txt")
        with open(disk_storage_path, 'w', encoding='utf-8') as f:
            f.write(file_content)

        cursor.execute(
            '''
            INSERT INTO file_attachments (
                id, message_id, file_name, display_name, mime_type, token_count,
                file_size, file_hash, storage_type, content_preview, storage_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            ('file_disk', 'message_id', 'disk.txt', 'disk.txt', 'text/plain',
             10, file_size, file_hash, 'disk', file_content[:100], disk_storage_path)
        )

        # 4. Create hybrid-stored attachment
        hybrid_storage_path = os.path.join(temp_file_storage_dir, "hybrid.txt")
        with open(hybrid_storage_path, 'w', encoding='utf-8') as f:
            f.write(file_content)

        cursor.execute(
            '''
            INSERT INTO file_attachments (
                id, message_id, file_name, display_name, mime_type, token_count,
                file_size, file_hash, storage_type, content_preview, storage_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            ('file_hybrid', 'message_id', 'hybrid.txt', 'hybrid.txt', 'text/plain',
             10, file_size, file_hash, 'hybrid', file_content[:100], hybrid_storage_path)
        )

        cursor.execute(
            '''
            INSERT INTO file_contents (file_id, content)
            VALUES (?, ?)
            ''',
            ('file_hybrid', file_content)
        )

        conn.commit()
        conn.close()

        # Test retrieving each attachment
        # 1. Database storage
        db_attachment = db_manager.get_file_attachment('file_db')
        assert db_attachment is not None
        assert db_attachment['file_name'] == 'db.txt'
        assert db_attachment['content'] == file_content

        # 2. Database storage with separate content table
        db_separate_attachment = db_manager.get_file_attachment('file_db_separate')
        assert db_separate_attachment is not None
        assert db_separate_attachment['file_name'] == 'db_separate.txt'
        assert db_separate_attachment['content'] == file_content

        # 3. Disk storage
        disk_attachment = db_manager.get_file_attachment('file_disk')
        assert disk_attachment is not None
        assert disk_attachment['file_name'] == 'disk.txt'
        assert disk_attachment['content'] == file_content

        # 4. Hybrid storage
        hybrid_attachment = db_manager.get_file_attachment('file_hybrid')
        assert hybrid_attachment is not None
        assert hybrid_attachment['file_name'] == 'hybrid.txt'
        assert hybrid_attachment['content'] == file_content

    def test_load_attachment_content(self, db_manager):
        """Test the load_attachment_content method."""
        # Setup
        file_content = "This is content for the load_attachment_content test."

        # Create a mock file attachment
        with patch.object(db_manager, 'get_file_attachment') as mock_get_file:
            mock_get_file.return_value = {'content': file_content}

            # Call the method
            content = db_manager.load_attachment_content('some_file_id')

            # Verify
            assert content == file_content
            mock_get_file.assert_called_once_with('some_file_id')

    def test_error_handling_get_path_to_root(self, db_manager):
        """Test error handling in get_path_to_root."""
        # Test with None node_id
        result = db_manager.get_path_to_root(None)
        assert result == []

        # Test with non-existent node_id
        result = db_manager.get_path_to_root('non_existent_id')
        assert result == []

    def test_error_handling_get_node_children(self, db_manager):
        """Test error handling in get_node_children."""
        # Test with non-existent node_id
        result = db_manager.get_node_children('non_existent_id')
        assert result == []

    def test_error_handling_get_message(self, db_manager):
        """Test error handling in get_message."""
        # Test with non-existent message_id
        result = db_manager.get_message('non_existent_id')
        assert result is None

    def test_error_handling_create_node(self, db_manager):
        """Test error handling in _create_node_from_db_row."""
        # Create an invalid row
        invalid_row = {'id': 'test_id'}  # Missing required fields

        # Attempt to create node from invalid row
        result = db_manager._create_node_from_db_row(invalid_row)
        assert result is None

    def test_database_exception_handling(self, db_manager):
        """Test handling of database exceptions."""
        # Test with a corrupted connection
        with patch.object(db_manager, 'get_connection') as mock_get_conn:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()

            # Make execute throw an exception
            mock_cursor.execute.side_effect = sqlite3.Error("Test database error")
            mock_conn.cursor.return_value = mock_cursor
            mock_get_conn.return_value = mock_conn

            # Test various methods that should handle the exception gracefully
            assert db_manager.get_path_to_root('any_id') == []
            assert db_manager.get_node_children('any_id') == []
            assert db_manager.get_message('any_id') is None

            # Ensure the connection is properly closed
            mock_conn.close.assert_called()