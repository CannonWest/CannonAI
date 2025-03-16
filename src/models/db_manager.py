# src/models/db_manager.py
"""
Database management utilities for the OpenAI Chat application.
"""

import os
import sqlite3
from typing import Dict, List, Any, Optional
from datetime import datetime

from PyQt6.QtCore import QUuid

from src.utils import DATABASE_DIR, DATABASE_FILE
from src.utils.logging_utils import get_logger, log_exception

# Get a logger for this module
logger = get_logger(__name__)


class DatabaseManager:
    """Handles SQLite database connections and operations"""

    def __init__(self, db_path=None):
        self.db_path = db_path or DATABASE_FILE
        self.logger = get_logger(f"{__name__}.DatabaseManager")

        # Create database directory if it doesn't exist
        os.makedirs(DATABASE_DIR, exist_ok=True)

        # Initialize database schema
        self.initialize_database()

    def get_connection(self):
        """Get a database connection with row factory for dictionary access"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_path_to_root(self, node_id):
        """Get the path from a node to the root"""
        if not node_id:
            self.logger.error("Attempted to get path to root with None node_id")
            return []

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            path = []
            current_id = node_id

            while current_id:
                # Get the current node
                cursor.execute(
                    'SELECT * FROM messages WHERE id = ?',
                    (current_id,)
                )
                message = cursor.fetchone()

                if not message:
                    self.logger.warning(f"No message found for ID {current_id}")
                    break

                # Create node object
                try:
                    node = self._create_node_from_db_row(message)
                    if node:
                        # Add to path (at beginning to maintain root-to-node order)
                        path.insert(0, node)
                    else:
                        self.logger.error(f"Failed to create node from row for ID {current_id}")
                        break
                except Exception as e:
                    self.logger.error(f"Error creating node from row for ID {current_id}: {str(e)}")
                    break

                # Move to parent
                current_id = message['parent_id']

            # Extra validation before returning
            valid_path = [node for node in path if node is not None]
            if len(valid_path) != len(path):
                self.logger.warning(f"Filtered {len(path) - len(valid_path)} None nodes from path")

            return valid_path

        except Exception as e:
            self.logger.error(f"Error creating node from row for ID {node_id}: {str(e)}")

    def get_node_children(self, node_id):
        """Get children of a node"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                'SELECT * FROM messages WHERE parent_id = ?',
                (node_id,)
            )

            children = []
            for row in cursor.fetchall():
                child = self._create_node_from_db_row(row)
                children.append(child)

            return children

        except Exception as e:
            self.logger.error(f"Error getting children for node {node_id}")
            log_exception(self.logger, e, f"Failed to get node children")
            return []
        finally:
            conn.close()

    def get_node_metadata(self, node_id):
        """Public method to get metadata for a node - forwards to _get_node_metadata"""
        return self._get_node_metadata(node_id)

    # Add this method to the DatabaseManager class
    def get_message(self, message_id):
        """Get a message by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                'SELECT * FROM messages WHERE id = ?',
                (message_id,)
            )
            message = cursor.fetchone()

            if not message:
                return None

            return self._create_node_from_db_row(message)

        except Exception as e:
            self.logger.error(f"Error getting message {message_id}")
            log_exception(self.logger, e, f"Failed to get message")
            return None
        finally:
            conn.close()

    def debug_print_conversations(self):
        """Print all conversations in the database for debugging"""
        # if not DEBUG_MODE:
        #     return
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT * FROM conversations')
            conversations = cursor.fetchall()

            print(f"===== DEBUG: Found {len(conversations)} conversations in database =====")
            for conv in conversations:
                print(f"ID: {conv['id']}, Name: {conv['name']}, Modified: {conv['modified_at']}")

                # Count messages in this conversation
                cursor.execute('SELECT COUNT(*) FROM messages WHERE conversation_id = ?', (conv['id'],))
                message_count = cursor.fetchone()[0]
                print(f"  Messages: {message_count}")

            print("=====================================================")

        except Exception as e:
            print(f"DEBUG: Error querying conversations: {str(e)}")
        finally:
            conn.close()

    def _create_node_from_db_row(self, row):
        """Create a DBMessageNode from a database row"""
        from src.models.db_conversation import DBMessageNode

        try:
            # Get metadata - handle both 3-tuple and 4-tuple returns for backward compatibility
            metadata_result = self._get_node_metadata(row['id'])

            # Handle different tuple lengths from _get_node_metadata
            if len(metadata_result) == 4:
                model_info, parameters, token_usage, reasoning_steps = metadata_result
            else:
                # Fall back to old 3-tuple format
                model_info, parameters, token_usage = metadata_result
                reasoning_steps = []

            # Get file attachments
            attached_files = self._get_node_attachments(row['id'])

            # Create the node
            node = DBMessageNode(
                id=row['id'],
                conversation_id=row['conversation_id'],
                role=row['role'],
                content=row['content'],
                parent_id=row['parent_id'],
                timestamp=row['timestamp'],
                model_info=model_info,
                parameters=parameters,
                token_usage=token_usage,
                attached_files=attached_files
            )

            # Set database manager for lazy loading children
            node._db_manager = self

            # Add reasoning steps if available
            if reasoning_steps:
                node._reasoning_steps = reasoning_steps

            return node
        except Exception as e:
            self.logger.error(f"Error creating node from row: {str(e)}")
            return None  # Return None rather than crashing

    def _get_node_metadata(self, node_id):
        """Get metadata for a node with improved error handling"""
        if not node_id:
            self.logger.error("Attempted to get metadata with None node_id")
            return {}, {}, {}, []

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            model_info = {}
            parameters = {}
            token_usage = {}
            reasoning_steps = []

            try:
                cursor.execute(
                    'SELECT metadata_type, metadata_value FROM message_metadata WHERE message_id = ?',
                    (node_id,)
                )

                import json
                for row in cursor.fetchall():
                    try:
                        metadata_type = row['metadata_type']

                        # Special handling for reasoning steps
                        if metadata_type == 'reasoning_steps':
                            try:
                                reasoning_steps = json.loads(row['metadata_value'])
                                continue
                            except Exception as e:
                                self.logger.error(f"Error parsing reasoning steps: {e}")
                                continue

                        # Regular metadata handling
                        try:
                            metadata_value = json.loads(row['metadata_value'])

                            if metadata_type.startswith('model_info.'):
                                key = metadata_type.replace('model_info.', '')
                                model_info[key] = metadata_value
                            elif metadata_type.startswith('parameters.'):
                                key = metadata_type.replace('parameters.', '')
                                parameters[key] = metadata_value
                            elif metadata_type.startswith('token_usage.'):
                                key = metadata_type.replace('token_usage.', '')
                                token_usage[key] = metadata_value
                        except Exception as e:
                            self.logger.error(f"Error parsing metadata {metadata_type}: {e}")
                    except Exception as e:
                        self.logger.error(f"Error processing metadata row: {e}")
            except Exception as e:
                self.logger.error(f"Error querying metadata: {e}")

            # Return tuple including reasoning steps
            return model_info, parameters, token_usage, reasoning_steps

        finally:
            conn.close()

    def _get_node_attachments(self, node_id):
        """Get file attachments for a node"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            attached_files = []

            cursor.execute(
                'SELECT * FROM file_attachments WHERE message_id = ?',
                (node_id,)
            )

            for row in cursor.fetchall():
                attached_files.append({
                    'file_name': row['file_name'],
                    'mime_type': row['mime_type'],
                    'content': row['content'],
                    'token_count': row['token_count']
                })

            return attached_files

        finally:
            conn.close()

    """
    Database schema migration utility to safely upgrade existing databases.
    """

    def initialize_database(self):
        """Create database tables if they don't exist with safe migration for existing DBs"""
        self.logger.debug(f"Initializing database at {self.db_path}")

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Create base tables if they don't exist
            cursor.executescript('''
                -- Conversations table to store conversation metadata
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    modified_at TEXT NOT NULL,
                    current_node_id TEXT NOT NULL,
                    system_message TEXT NOT NULL
                );

                -- Messages table to store individual messages
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    parent_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    response_id TEXT,  -- Store OpenAI Response ID
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_id) REFERENCES messages(id) ON DELETE CASCADE
                );

                -- Message metadata table for model info, parameters, etc.
                CREATE TABLE IF NOT EXISTS message_metadata (
                    message_id TEXT NOT NULL,
                    metadata_type TEXT NOT NULL,
                    metadata_value TEXT NOT NULL,
                    PRIMARY KEY (message_id, metadata_type),
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                );

                -- Reasoning steps table for Response API reasoning
                CREATE TABLE IF NOT EXISTS reasoning_steps (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    step_content TEXT NOT NULL,
                    step_order INTEGER NOT NULL,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                );
            ''')

            # Check if file_attachments table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_attachments'")
            table_exists = cursor.fetchone() is not None

            if not table_exists:
                # Create new table with all columns if it doesn't exist
                cursor.executescript('''
                    -- File attachments table with optimized storage
                    CREATE TABLE IF NOT EXISTS file_attachments (
                        id TEXT PRIMARY KEY,
                        message_id TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        display_name TEXT, -- For relative paths in directory imports
                        mime_type TEXT NOT NULL,
                        token_count INTEGER NOT NULL,
                        file_size INTEGER NOT NULL,
                        file_hash TEXT NOT NULL, -- For identifying and caching files
                        storage_type TEXT NOT NULL DEFAULT 'database', -- 'database', 'disk', or 'hybrid'
                        content_preview TEXT, -- First 4KB for preview
                        storage_path TEXT, -- Path for disk storage
                        content TEXT, -- File content (will be moved to separate table in future)
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    );
                ''')
            else:
                # Table exists - check columns and add missing ones
                self.logger.info("File attachments table exists, checking for missing columns")

                # Get existing columns
                cursor.execute("PRAGMA table_info(file_attachments)")
                existing_columns = [row['name'] for row in cursor.fetchall()]

                # Define required columns and their definitions
                required_columns = {
                    'display_name': 'TEXT',
                    'file_size': 'INTEGER NOT NULL DEFAULT 0',
                    'file_hash': 'TEXT NOT NULL DEFAULT ""',
                    'storage_type': "TEXT NOT NULL DEFAULT 'database'",
                    'content_preview': 'TEXT',
                    'storage_path': 'TEXT'
                }

                # Add missing columns
                for column, definition in required_columns.items():
                    if column not in existing_columns:
                        self.logger.info(f"Adding missing column: {column}")
                        try:
                            cursor.execute(f"ALTER TABLE file_attachments ADD COLUMN {column} {definition}")
                        except Exception as e:
                            self.logger.error(f"Error adding column {column}: {e}")

                # For existing rows, update file_hash based on content
                if 'file_hash' in required_columns and 'file_hash' not in existing_columns:
                    self.logger.info("Updating file_hash for existing attachments")
                    try:
                        # First check if content column exists
                        if 'content' in existing_columns:
                            cursor.execute("SELECT id, content FROM file_attachments")
                            for row in cursor.fetchall():
                                import hashlib
                                # Generate hash from content
                                content_hash = hashlib.sha256(row['content'].encode('utf-8')).hexdigest()
                                cursor.execute(
                                    "UPDATE file_attachments SET file_hash = ? WHERE id = ?",
                                    (content_hash, row['id'])
                                )
                    except Exception as e:
                        self.logger.error(f"Error updating file_hash values: {e}")

                # Update file_size for existing rows if needed
                if 'file_size' in required_columns and 'file_size' not in existing_columns:
                    self.logger.info("Updating file_size for existing attachments")
                    try:
                        if 'content' in existing_columns:
                            cursor.execute("SELECT id, content FROM file_attachments")
                            for row in cursor.fetchall():
                                content_size = len(row['content'].encode('utf-8'))
                                cursor.execute(
                                    "UPDATE file_attachments SET file_size = ? WHERE id = ?",
                                    (content_size, row['id'])
                                )
                    except Exception as e:
                        self.logger.error(f"Error updating file_size values: {e}")

                # Update content_preview for existing rows
                if 'content_preview' in required_columns and 'content_preview' not in existing_columns:
                    self.logger.info("Updating content_preview for existing attachments")
                    try:
                        if 'content' in existing_columns:
                            cursor.execute("SELECT id, content FROM file_attachments")
                            for row in cursor.fetchall():
                                # First 4KB for preview
                                preview = row['content'][:4096] if row['content'] else ''
                                cursor.execute(
                                    "UPDATE file_attachments SET content_preview = ? WHERE id = ?",
                                    (preview, row['id'])
                                )
                    except Exception as e:
                        self.logger.error(f"Error updating content_preview values: {e}")

            # Create indices if they don't exist
            cursor.executescript('''
                -- Indices for faster lookups
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_parent_id ON messages(parent_id);
                CREATE INDEX IF NOT EXISTS idx_message_metadata_message_id ON message_metadata(message_id);
                CREATE INDEX IF NOT EXISTS idx_file_attachments_message_id ON file_attachments(message_id);
                CREATE INDEX IF NOT EXISTS idx_file_attachments_file_hash ON file_attachments(file_hash);
                CREATE INDEX IF NOT EXISTS idx_reasoning_steps_message_id ON reasoning_steps(message_id);
            ''')

            # Check if the file_contents table needs to be created
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
            if cursor.fetchone() is None:
                cursor.executescript('''
                    -- Separate content table for large files
                    CREATE TABLE IF NOT EXISTS file_contents (
                        file_id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        FOREIGN KEY (file_id) REFERENCES file_attachments(id) ON DELETE CASCADE
                    );

                    -- Index for faster lookups
                    CREATE INDEX IF NOT EXISTS idx_file_contents_file_id ON file_contents(file_id);
                ''')

            conn.commit()
            conn.close()
            self.logger.info("Database schema initialized/migrated successfully")

        except Exception as e:
            self.logger.error("Error initializing database")
            log_exception(self.logger, e, "Database initialization failed")
            raise

    def add_file_attachment(self, message_id, file_info, storage_type='auto'):
        """
        Add a file attachment with optimized storage strategy

        Args:
            message_id: ID of the message to attach the file to
            file_info: Dictionary with file information
            storage_type: 'database', 'disk', 'hybrid', or 'auto'

        Returns:
            ID of the created attachment
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            from PyQt6.QtCore import QUuid

            file_id = str(QUuid.createUuid())
            file_name = file_info['file_name']
            display_name = file_info.get('display_name', file_name)
            mime_type = file_info.get('mime_type', 'text/plain')
            token_count = file_info.get('token_count', 0)
            file_size = file_info.get('size', 0)
            file_hash = file_info.get('file_hash', '')
            content = file_info.get('content', '')

            # If no file hash provided, calculate one
            if not file_hash and content:
                import hashlib
                file_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

            # Determine storage strategy if auto
            if storage_type == 'auto':
                if file_size > 1024 * 1024:  # > 1MB
                    storage_type = 'disk'
                else:
                    storage_type = 'database'

            # Generate a preview (first 4KB)
            content_preview = content[:4096] if content else ''

            storage_path = None

            # If disk storage, save to disk
            if storage_type in ('disk', 'hybrid'):
                # Import here to avoid circular imports
                from src.utils.file_utils import FileCacheManager

                # Get cache manager
                cache_manager = FileCacheManager()

                # Cache the file
                storage_path = cache_manager.cache_file(content, file_hash)

                # For hybrid, we keep content in the database
                # For disk, we just store the path and free the memory
                if storage_type == 'disk':
                    content = None  # Free memory

            # Check which version of the table we're working with
            cursor.execute("PRAGMA table_info(file_attachments)")
            columns = [row['name'] for row in cursor.fetchall()]

            # Determine if we should use the old or new schema
            using_new_schema = all(col in columns for col in ['file_hash', 'storage_type', 'content_preview'])

            if using_new_schema:
                # Use new optimized schema
                cursor.execute(
                    '''
                    INSERT INTO file_attachments
                    (id, message_id, file_name, display_name, mime_type, token_count,
                    file_size, file_hash, storage_type, content_preview, storage_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (file_id, message_id, file_name, display_name, mime_type, token_count,
                     file_size, file_hash, storage_type, content_preview, storage_path)
                )

                # If database or hybrid storage, save content to separate table
                if storage_type in ('database', 'hybrid') and content:
                    # Check if file_contents table exists
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
                    if cursor.fetchone():
                        # Use the separate content table
                        cursor.execute(
                            '''
                            INSERT INTO file_contents (file_id, content)
                            VALUES (?, ?)
                            ''',
                            (file_id, content)
                        )
                    else:
                        # Fall back to storing in main table
                        cursor.execute(
                            '''
                            UPDATE file_attachments SET content = ?
                            WHERE id = ?
                            ''',
                            (content, file_id)
                        )
            else:
                # Fall back to original schema
                cursor.execute(
                    '''
                    INSERT INTO file_attachments (id, message_id, file_name, mime_type, content, token_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''',
                    (file_id, message_id, file_name, mime_type, content, token_count)
                )

            conn.commit()
            return file_id

        except Exception as e:
            conn.rollback()
            self.logger.error(f"Error adding file attachment: {e}")
            raise

        finally:
            conn.close()

    def get_file_attachment(self, file_id):
        """
        Get a file attachment by ID with efficient content loading

        Args:
            file_id: ID of the attachment

        Returns:
            Dictionary with file information
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # First check if we have the new schema
            cursor.execute("PRAGMA table_info(file_attachments)")
            columns = [row['name'] for row in cursor.fetchall()]
            using_new_schema = all(col in columns for col in ['file_hash', 'storage_type', 'content_preview'])

            if using_new_schema:
                # Get attachment metadata
                cursor.execute(
                    '''
                    SELECT * FROM file_attachments
                    WHERE id = ?
                    ''',
                    (file_id,)
                )
            else:
                # Use original schema
                cursor.execute(
                    '''
                    SELECT id, message_id, file_name, mime_type, content, token_count
                    FROM file_attachments
                    WHERE id = ?
                    ''',
                    (file_id,)
                )

            attachment = cursor.fetchone()

            if not attachment:
                return None

            # Convert to dict
            attachment_dict = dict(attachment)

            # For new schema, load content based on storage type
            if using_new_schema and 'storage_type' in attachment_dict:
                storage_type = attachment_dict['storage_type']

                if storage_type == 'database':
                    # Check if separate content table exists
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
                    if cursor.fetchone():
                        # Get content from separate table
                        cursor.execute(
                            '''
                            SELECT content FROM file_contents
                            WHERE file_id = ?
                            ''',
                            (file_id,)
                        )

                        result = cursor.fetchone()
                        if result:
                            attachment_dict['content'] = result['content']
                        elif 'content' not in attachment_dict or not attachment_dict['content']:
                            attachment_dict['content'] = ''
                    # If content field exists but is null, set to empty string
                    elif 'content' not in attachment_dict or not attachment_dict['content']:
                        attachment_dict['content'] = ''

                elif storage_type == 'disk':
                    # Load from disk
                    storage_path = attachment_dict.get('storage_path')

                    if storage_path and os.path.exists(storage_path):
                        with open(storage_path, 'r', encoding='utf-8') as f:
                            attachment_dict['content'] = f.read()
                    else:
                        attachment_dict['content'] = ''

                elif storage_type == 'hybrid':
                    # Try database first - check both separate table and main table
                    content_found = False

                    # Check separate content table
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
                    if cursor.fetchone():
                        cursor.execute(
                            '''
                            SELECT content FROM file_contents
                            WHERE file_id = ?
                            ''',
                            (file_id,)
                        )

                        result = cursor.fetchone()
                        if result:
                            attachment_dict['content'] = result['content']
                            content_found = True

                    # If not found and content field is in main table
                    if not content_found and 'content' in attachment_dict and attachment_dict['content']:
                        content_found = True

                    # Fall back to disk if needed
                    if not content_found:
                        storage_path = attachment_dict.get('storage_path')

                        if storage_path and os.path.exists(storage_path):
                            with open(storage_path, 'r', encoding='utf-8') as f:
                                attachment_dict['content'] = f.read()
                        else:
                            attachment_dict['content'] = ''

            return attachment_dict

        except Exception as e:
            self.logger.error(f"Error getting file attachment: {e}")
            return None

        finally:
            conn.close()

    def get_node_attachments(self, node_id):
        """Get file attachments for a node with optimized loading"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            attached_files = []

            # Check schema version
            cursor.execute("PRAGMA table_info(file_attachments)")
            columns = [row['name'] for row in cursor.fetchall()]
            using_new_schema = all(col in columns for col in ['file_hash', 'storage_type', 'content_preview'])

            if using_new_schema:
                # Use new schema with preview
                cursor.execute(
                    '''
                    SELECT id, file_name, display_name, mime_type, token_count, 
                           file_size, file_hash, storage_type, content_preview, storage_path
                    FROM file_attachments WHERE message_id = ?
                    ''',
                    (node_id,)
                )
            else:
                # Use original schema
                cursor.execute(
                    '''
                    SELECT id, file_name, mime_type, content, token_count
                    FROM file_attachments WHERE message_id = ?
                    ''',
                    (node_id,)
                )

            for row in cursor.fetchall():
                # Convert row to dict
                attachment = dict(row)

                if using_new_schema:
                    # For normal UI display, we only need the preview
                    if 'content_preview' in attachment and attachment['content_preview']:
                        attachment['content'] = attachment['content_preview']

                attached_files.append(attachment)

            return attached_files

        finally:
            conn.close()

    def load_attachment_content(self, attachment_id):
        """Load full attachment content on demand"""
        return self.get_file_attachment(attachment_id)['content']