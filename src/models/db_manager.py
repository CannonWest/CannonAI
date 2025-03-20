"""
Database management utilities for the OpenAI Chat application.
This module handles SQLite database connections and operations.
"""

import os
import sqlite3
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

from PyQt6.QtCore import QUuid

from src.utils.constants import DATABASE_DIR, DATABASE_FILE
from src.utils.logging_utils import get_logger, log_exception
from src.utils.file_utils import FileCacheManager
from src.models.db_types import DBMessageNode

logger = get_logger(__name__)

class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DATABASE_FILE
        self.logger = logger
        self.file_cache_manager = FileCacheManager()
        os.makedirs(DATABASE_DIR, exist_ok=True)
        self.initialize_database()

    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory for dictionary access"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_path_to_root(self, node_id: str) -> List['DBMessageNode']:
        """Get the path from a node to the root"""
        if not node_id:
            self.logger.error("Attempted to get path to root with None node_id")
            return []

        with self.get_connection() as conn:
            cursor = conn.cursor()
            path = []
            current_id = node_id

            while current_id:
                cursor.execute('SELECT * FROM messages WHERE id = ?', (current_id,))
                message = cursor.fetchone()

                if not message:
                    self.logger.warning(f"No message found for ID {current_id}")
                    break

                node = self._create_node_from_db_row(message)
                if node:
                    path.insert(0, node)
                else:
                    self.logger.error(f"Failed to create node from row for ID {current_id}")
                    break

                current_id = message['parent_id']

        return [node for node in path if node is not None]

    def get_node_children(self, node_id: str) -> List['DBMessageNode']:
        """Get children of a node"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM messages WHERE parent_id = ?', (node_id,))
            return [self._create_node_from_db_row(row) for row in cursor.fetchall()]

    def get_node_metadata(self, node_id: str) -> Tuple[Dict, Dict, Dict, List]:
        """Get metadata for a node"""
        return self._get_node_metadata(node_id)

    def get_message(self, message_id: str) -> Optional['DBMessageNode']:
        """Get a message by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM messages WHERE id = ?', (message_id,))
            message = cursor.fetchone()
            return self._create_node_from_db_row(message) if message else None

    def debug_print_conversations(self):
        """Print all conversations in the database for debugging"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM conversations')
            conversations = cursor.fetchall()

            print(f"===== DEBUG: Found {len(conversations)} conversations in database =====")
            for conv in conversations:
                print(f"ID: {conv['id']}, Name: {conv['name']}, Modified: {conv['modified_at']}")
                cursor.execute('SELECT COUNT(*) FROM messages WHERE conversation_id = ?', (conv['id'],))
                message_count = cursor.fetchone()[0]
                print(f"  Messages: {message_count}")
            print("=====================================================")

    def _create_node_from_db_row(self, row: sqlite3.Row) -> Optional['DBMessageNode']:
        """Create a DBMessageNode from a database row"""
        try:
            metadata_result = self._get_node_metadata(row['id'])
            model_info, parameters, token_usage, reasoning_steps = metadata_result

            attached_files = self._get_node_attachments(row['id'])

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
                attached_files=attached_files,
                response_id=row['response_id']
            )

            node._db_manager = self
            node._reasoning_steps = reasoning_steps

            return node
        except Exception as e:
            self.logger.error(f"Error creating node from row: {str(e)}")
            return None

    def _get_node_metadata(self, node_id: str) -> Tuple[Dict, Dict, Dict, List]:
        """Get metadata for a node with improved error handling"""
        if not node_id:
            self.logger.error("Attempted to get metadata with None node_id")
            return {}, {}, {}, []

        with self.get_connection() as conn:
            cursor = conn.cursor()
            model_info, parameters, token_usage = {}, {}, {}
            reasoning_steps = []

            cursor.execute(
                'SELECT metadata_type, metadata_value FROM message_metadata WHERE message_id = ?',
                (node_id,)
            )

            for row in cursor.fetchall():
                try:
                    metadata_type = row['metadata_type']
                    metadata_value = json.loads(row['metadata_value'])

                    if metadata_type == 'reasoning_steps':
                        reasoning_steps = metadata_value
                    elif metadata_type.startswith('model_info.'):
                        model_info[metadata_type.replace('model_info.', '')] = metadata_value
                    elif metadata_type.startswith('parameters.'):
                        parameters[metadata_type.replace('parameters.', '')] = metadata_value
                    elif metadata_type.startswith('token_usage.'):
                        token_usage[metadata_type.replace('token_usage.', '')] = metadata_value
                except json.JSONDecodeError:
                    self.logger.error(f"Error parsing metadata {metadata_type}")
                except Exception as e:
                    self.logger.error(f"Error processing metadata row: {e}")

        return model_info, parameters, token_usage, reasoning_steps

    def _get_node_attachments(self, node_id: str) -> List[Dict]:
        """Get file attachments for a node"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM file_attachments WHERE message_id = ?', (node_id,))
            return [dict(row) for row in cursor.fetchall()]

    def initialize_database(self):
        """Create database tables if they don't exist with safe migration for existing DBs"""
        self.logger.debug(f"Initializing database at {self.db_path}")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create base tables
            cursor.executescript('''
                -- Conversations table
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    modified_at TEXT NOT NULL,
                    current_node_id TEXT NOT NULL,
                    system_message TEXT NOT NULL
                );

                -- Messages table
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    parent_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    response_id TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_id) REFERENCES messages(id) ON DELETE CASCADE
                );

                -- Message metadata table
                CREATE TABLE IF NOT EXISTS message_metadata (
                    message_id TEXT NOT NULL,
                    metadata_type TEXT NOT NULL,
                    metadata_value TEXT NOT NULL,
                    PRIMARY KEY (message_id, metadata_type),
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                );

                -- Reasoning steps table
                CREATE TABLE IF NOT EXISTS reasoning_steps (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    step_content TEXT NOT NULL,
                    step_order INTEGER NOT NULL,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                );
            ''')

            # Check and create file_attachments table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_attachments'")
            if cursor.fetchone() is None:
                cursor.executescript('''
                    -- File attachments table
                    CREATE TABLE IF NOT EXISTS file_attachments (
                        id TEXT PRIMARY KEY,
                        message_id TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        display_name TEXT,
                        mime_type TEXT NOT NULL,
                        token_count INTEGER NOT NULL,
                        file_size INTEGER NOT NULL,
                        file_hash TEXT NOT NULL,
                        storage_type TEXT NOT NULL DEFAULT 'database',
                        content_preview TEXT,
                        storage_path TEXT,
                        content TEXT,
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    );
                ''')
            else:
                self._add_missing_columns(cursor)

            # Create indices
            cursor.executescript('''
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_parent_id ON messages(parent_id);
                CREATE INDEX IF NOT EXISTS idx_message_metadata_message_id ON message_metadata(message_id);
                CREATE INDEX IF NOT EXISTS idx_file_attachments_message_id ON file_attachments(message_id);
                CREATE INDEX IF NOT EXISTS idx_file_attachments_file_hash ON file_attachments(file_hash);
                CREATE INDEX IF NOT EXISTS idx_reasoning_steps_message_id ON reasoning_steps(message_id);
            ''')

            # Create file_contents table if needed
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

        self.logger.info("Database schema initialized/migrated successfully")

    def _add_missing_columns(self, cursor):
        """Add missing columns to file_attachments table"""
        required_columns = {
            'display_name': 'TEXT',
            'file_size': 'INTEGER NOT NULL DEFAULT 0',
            'file_hash': 'TEXT NOT NULL DEFAULT ""',
            'storage_type': "TEXT NOT NULL DEFAULT 'database'",
            'content_preview': 'TEXT',
            'storage_path': 'TEXT'
        }

        cursor.execute("PRAGMA table_info(file_attachments)")
        existing_columns = [row['name'] for row in cursor.fetchall()]

        for column, definition in required_columns.items():
            if column not in existing_columns:
                self.logger.info(f"Adding missing column: {column}")
                try:
                    cursor.execute(f"ALTER TABLE file_attachments ADD COLUMN {column} {definition}")
                except Exception as e:
                    self.logger.error(f"Error adding column {column}: {e}")

        self._update_existing_rows(cursor, existing_columns)

    def _update_existing_rows(self, cursor, existing_columns):
        """Update existing rows with new column data"""
        if 'file_hash' not in existing_columns:
            self._update_file_hash(cursor)

        if 'file_size' not in existing_columns:
            self._update_file_size(cursor)

        if 'content_preview' not in existing_columns:
            self._update_content_preview(cursor)

    def _update_file_hash(self, cursor):
        self.logger.info("Updating file_hash for existing attachments")
        cursor.execute("SELECT id, content FROM file_attachments")
        for row in cursor.fetchall():
            content_hash = hashlib.sha256(row['content'].encode('utf-8')).hexdigest()
            cursor.execute("UPDATE file_attachments SET file_hash = ? WHERE id = ?", (content_hash, row['id']))

    def _update_file_size(self, cursor):
        self.logger.info("Updating file_size for existing attachments")
        cursor.execute("SELECT id, content FROM file_attachments")
        for row in cursor.fetchall():
            content_size = len(row['content'].encode('utf-8'))
            cursor.execute("UPDATE file_attachments SET file_size = ? WHERE id = ?", (content_size, row['id']))

    def _update_content_preview(self, cursor):
        self.logger.info("Updating content_preview for existing attachments")
        cursor.execute("SELECT id, content FROM file_attachments")
        for row in cursor.fetchall():
            preview = row['content'][:4096] if row['content'] else ''
            cursor.execute("UPDATE file_attachments SET content_preview = ? WHERE id = ?", (preview, row['id']))

    def add_file_attachment(self, message_id: str, file_info: Dict, storage_type: str = 'auto') -> str:
        """Add a file attachment with optimized storage strategy"""
        file_id = str(QUuid.createUuid())
        file_name = file_info['file_name']
        display_name = file_info.get('display_name', file_name)
        mime_type = file_info.get('mime_type', 'text/plain')
        token_count = file_info.get('token_count', 0)
        file_size = file_info.get('size', 0)
        file_hash = file_info.get('file_hash', '')
        content = file_info.get('content', '')

        if not file_hash and content:
            file_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

        storage_type = self._determine_storage_type(storage_type, file_size)
        content_preview = content[:4096] if content else ''
        storage_path = None

        if storage_type in ('disk', 'hybrid'):
            cache_manager = FileCacheManager()
            storage_path = cache_manager.cache_file(content, file_hash)
            if storage_type == 'disk':
                content = None

        with self.get_connection() as conn:
            cursor = conn.cursor()
            self._insert_file_attachment(cursor, file_id, message_id, file_name, display_name, mime_type,
                                         token_count, file_size, file_hash, storage_type, content_preview,
                                         storage_path, content)

        return file_id

    def _determine_storage_type(self, storage_type: str, file_size: int) -> str:
        if storage_type == 'auto':
            return 'disk' if file_size > 1024 * 1024 else 'database'
        return storage_type

    def _insert_file_attachment(self, cursor, file_id, message_id, file_name, display_name, mime_type,
                                token_count, file_size, file_hash, storage_type, content_preview,
                                storage_path, content):
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

        if storage_type in ('database', 'hybrid') and content:
            self._insert_file_content(cursor, file_id, content)

    def _insert_file_content(self, cursor, file_id: str, content: str):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
        if cursor.fetchone():
            cursor.execute(
                '''
                INSERT INTO file_contents (file_id, content)
                VALUES (?, ?)
                ''',
                (file_id, content)
            )
        else:
            cursor.execute(
                '''
                UPDATE file_attachments SET content = ?
                WHERE id = ?
                ''',
                (content, file_id)
            )

    def get_file_attachment(self, file_id: str) -> Optional[Dict]:
        """Get a file attachment by ID with efficient content loading"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM file_attachments WHERE id = ?", (file_id,))
            attachment = cursor.fetchone()

            if not attachment:
                return None

            attachment_dict = dict(attachment)
            self._load_attachment_content(cursor, attachment_dict)

            return attachment_dict

    def _load_attachment_content(self, cursor, attachment_dict: Dict):
        storage_type = attachment_dict.get('storage_type', 'database')

        if storage_type == 'database':
            self._load_database_content(cursor, attachment_dict)
        elif storage_type == 'disk':
            self._load_disk_content(attachment_dict)
        elif storage_type == 'hybrid':
            self._load_hybrid_content(cursor, attachment_dict)

    def _load_database_content(self, cursor, attachment_dict: Dict):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
        if cursor.fetchone():
            cursor.execute("SELECT content FROM file_contents WHERE file_id = ?", (attachment_dict['id'],))
            result = cursor.fetchone()
            attachment_dict['content'] = result['content'] if result else ''
        elif 'content' not in attachment_dict or not attachment_dict['content']:
            attachment_dict['content'] = ''

    def _load_disk_content(self, attachment_dict: Dict):
        storage_path = attachment_dict.get('storage_path')
        if storage_path and os.path.exists(storage_path):
            with open(storage_path, 'r', encoding='utf-8') as f:
                attachment_dict['content'] = f.read()
        else:
            attachment_dict['content'] = ''

    def _load_hybrid_content(self, cursor, attachment_dict: Dict):
        self._load_database_content(cursor, attachment_dict)
        if not attachment_dict['content']:
            self._load_disk_content(attachment_dict)

    def get_node_attachments(self, node_id: str) -> List[Dict]:
        """Get file attachments for a node with optimized loading"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                SELECT id, file_name, display_name, mime_type, token_count, 
                       file_size, file_hash, storage_type, content_preview, storage_path
                FROM file_attachments WHERE message_id = ?
                ''',
                (node_id,)
            )
            attachments = [dict(row) for row in cursor.fetchall()]
            for attachment in attachments:
                attachment['content'] = attachment.get('content_preview', '')
            return attachments

    def load_attachment_content(self, attachment_id: str) -> str:
        """Load full attachment content on demand"""
        attachment = self.get_file_attachment(attachment_id)
        return attachment['content'] if attachment else ''
