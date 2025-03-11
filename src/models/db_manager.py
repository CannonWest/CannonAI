# src/models/db_manager.py
"""
Database management utilities for the OpenAI Chat application.
"""

import os
import sqlite3
from typing import Dict, List, Any, Optional
from datetime import datetime

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

    def initialize_database(self):
        """Create database tables if they don't exist"""
        self.logger.debug(f"Initializing database at {self.db_path}")

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Create tables
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

                -- File attachments table
                CREATE TABLE IF NOT EXISTS file_attachments (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                );

                -- Indices for faster lookups
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_parent_id ON messages(parent_id);
                CREATE INDEX IF NOT EXISTS idx_message_metadata_message_id ON message_metadata(message_id);
                CREATE INDEX IF NOT EXISTS idx_file_attachments_message_id ON file_attachments(message_id);
            ''')

            conn.commit()
            conn.close()
            self.logger.info("Database schema initialized successfully")

        except Exception as e:
            self.logger.error("Error initializing database")
            log_exception(self.logger, e, "Database initialization failed")
            raise

    def get_path_to_root(self, node_id):
        """Get the path from a node to the root"""
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
                    break

                # Create node object
                node = self._create_node_from_db_row(message)

                # Add to path (at beginning to maintain root-to-node order)
                path.insert(0, node)

                # Move to parent
                current_id = message['parent_id']

            return path

        except Exception as e:
            self.logger.error(f"Error getting path to root for node {node_id}")
            log_exception(self.logger, e, f"Failed to get path to root")
            return []
        finally:
            conn.close()

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

        # Get metadata
        model_info, parameters, token_usage = self._get_node_metadata(row['id'])

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

        return node

    def _get_node_metadata(self, node_id):
        """Get metadata for a node"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            model_info = {}
            parameters = {}
            token_usage = {}

            cursor.execute(
                'SELECT metadata_type, metadata_value FROM message_metadata WHERE message_id = ?',
                (node_id,)
            )

            import json
            for row in cursor.fetchall():
                metadata_type = row['metadata_type']
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

            return model_info, parameters, token_usage

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
