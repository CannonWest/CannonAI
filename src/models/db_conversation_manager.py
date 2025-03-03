# src/models/db_conversation_manager.py
"""
Database-backed conversation manager for improved scalability.
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from PyQt6.QtCore import QUuid

from src.utils import CONVERSATIONS_DIR
from src.utils.logging_utils import get_logger, log_exception
from src.models.db_manager import DatabaseManager
from src.models.db_conversation import DBConversationTree

# Get a logger for this module
logger = get_logger(__name__)


class DBConversationManager:
    """
    Database-backed conversation manager for improved scalability
    """

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.conversations = {}  # Cache for open conversations
        self.active_conversation_id = None
        self.logger = get_logger(f"{__name__}.DBConversationManager")

    @property
    def active_conversation(self):
        """Get the currently active conversation"""
        if self.active_conversation_id and self.active_conversation_id in self.conversations:
            return self.conversations[self.active_conversation_id]
        return None

    def set_active_conversation(self, conversation_id):
        """Set the active conversation"""
        if conversation_id in self.conversations:
            self.active_conversation_id = conversation_id
            return True

        # If not in cache, check if it exists in the database
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                'SELECT id FROM conversations WHERE id = ?',
                (conversation_id,)
            )

            if cursor.fetchone():
                # Load the conversation
                self.conversations[conversation_id] = DBConversationTree(
                    self.db_manager,
                    id=conversation_id
                )
                self.active_conversation_id = conversation_id
                return True
        except Exception as e:
            logger.error(f"Error setting active conversation {conversation_id}")
            log_exception(logger, e, f"Failed to set active conversation {conversation_id}")
        finally:
            conn.close()

        return False

    def create_conversation(self, name="New Conversation", system_message="You are a helpful assistant."):
        """Create a new conversation"""
        try:
            conversation = DBConversationTree(
                self.db_manager,
                name=name,
                system_message=system_message
            )

            self.conversations[conversation.id] = conversation
            self.active_conversation_id = conversation.id

            self.logger.info(f"Created new conversation: {name} (ID: {conversation.id})")
            return conversation
        except Exception as e:
            self.logger.error("Error creating new conversation")
            log_exception(self.logger, e, "Failed to create new conversation")
            raise

    def get_conversation_list(self):
        """Get a list of all conversations"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                '''
                SELECT id, name, created_at, modified_at
                FROM conversations
                ORDER BY modified_at DESC
                '''
            )

            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error("Error getting conversation list")
            log_exception(self.logger, e, "Failed to get conversation list")
            return []
        finally:
            conn.close()

    def load_conversation(self, conversation_id):
        """Load a conversation from the database"""
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        try:
            conversation = DBConversationTree(
                self.db_manager,
                id=conversation_id
            )

            self.conversations[conversation_id] = conversation

            # If this is our first conversation, make it active
            if not self.active_conversation_id:
                self.active_conversation_id = conversation_id

            self.logger.info(f"Loaded conversation: {conversation.name} (ID: {conversation_id})")
            return conversation
        except Exception as e:
            self.logger.error(f"Error loading conversation {conversation_id}")
            log_exception(self.logger, e, f"Failed to load conversation {conversation_id}")
            return None

    def load_all(self):
        """Load conversation list from database"""
        # We don't actually load all conversations into memory
        # Just get the list of available conversations
        conversation_list = self.get_conversation_list()

        if not conversation_list:
            self.logger.info("No conversations found in database")
            return

        # Set first conversation as active if none is active
        if not self.active_conversation_id and conversation_list:
            first_conversation_id = conversation_list[0]['id']
            self.load_conversation(first_conversation_id)
            self.logger.info(f"Set active conversation to: {first_conversation_id}")

    def delete_conversation(self, conversation_id):
        """Delete a conversation"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            # Due to CASCADE constraints, this will delete all related records
            cursor.execute(
                'DELETE FROM conversations WHERE id = ?',
                (conversation_id,)
            )

            # Remove from cache if present
            if conversation_id in self.conversations:
                del self.conversations[conversation_id]

            # If we deleted the active conversation, select a new one
            if conversation_id == self.active_conversation_id:
                self.active_conversation_id = None

                # Get first available conversation
                conversation_list = self.get_conversation_list()
                if conversation_list:
                    first_id = conversation_list[0]['id']
                    self.load_conversation(first_id)

            conn.commit()
            self.logger.info(f"Deleted conversation: {conversation_id}")
            return True
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Error deleting conversation {conversation_id}")
            log_exception(self.logger, e, f"Failed to delete conversation {conversation_id}")
            return False
        finally:
            conn.close()

    def save_conversation(self, conversation_id):
        """Save a conversation (no-op for database backend)"""
        # All changes are immediately saved to the database
        # This method exists for compatibility
        if conversation_id in self.conversations:
            self.logger.debug(f"Save operation called for conversation {conversation_id} (no-op in DB mode)")
            return True
        return False

    def save_all(self):
        """Save all conversations (no-op for database backend)"""
        # All changes are immediately saved to the database
        # This method exists for compatibility
        self.logger.debug("Save all operation called (no-op in DB mode)")
        return True

    def search_conversations(self, search_term, conversation_id=None, role_filter=None):
        """Search for messages containing the search term"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            query = '''
                SELECT m.id, m.conversation_id, m.role, m.content, m.timestamp,
                       c.name as conversation_name
                FROM messages m
                JOIN conversations c ON m.conversation_id = c.id
                WHERE m.content LIKE ?
            '''
            params = [f'%{search_term}%']

            # Add filters if provided
            if conversation_id:
                query += ' AND m.conversation_id = ?'
                params.append(conversation_id)

            if role_filter:
                query += ' AND m.role = ?'
                params.append(role_filter)

            cursor.execute(query, params)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row['id'],
                    'conversation_id': row['conversation_id'],
                    'conversation_name': row['conversation_name'],
                    'role': row['role'],
                    'content': row['content'],
                    'timestamp': row['timestamp']
                })

            return results
        except Exception as e:
            self.logger.error(f"Error searching conversations")
            log_exception(self.logger, e, "Failed to search conversations")
            return []
        finally:
            conn.close()

    def migrate_json_to_db(self):
        """Migrate existing JSON conversations to the database"""
        if not os.path.exists(CONVERSATIONS_DIR):
            self.logger.info("No conversations directory found, skipping migration")
            return

        # Get list of JSON files
        json_files = [f for f in os.listdir(CONVERSATIONS_DIR) if f.endswith('.json')]

        if not json_files:
            self.logger.info("No JSON conversation files found, skipping migration")
            return

        self.logger.info(f"Found {len(json_files)} JSON conversation files to migrate")

        # Check if we already have conversations in the database
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT COUNT(*) as count FROM conversations')
            count = cursor.fetchone()['count']

            if count > 0:
                self.logger.info(f"Database already contains {count} conversations, skipping migration")
                return
        finally:
            conn.close()

        # Migrate each file
        migrated_count = 0
        for filename in json_files:
            file_path = os.path.join(CONVERSATIONS_DIR, filename)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    conversation_data = json.load(f)

                # Create new conversation in the database
                self._import_conversation_from_json(conversation_data)
                migrated_count += 1

            except Exception as e:
                self.logger.error(f"Error migrating conversation from {filename}")
                log_exception(self.logger, e, f"Failed to migrate conversation from {filename}")

        self.logger.info(f"Successfully migrated {migrated_count} conversations to the database")

    def _import_conversation_from_json(self, data):
        """Import a conversation from JSON data"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            # Get conversation data
            conversation_id = data.get('id', str(QUuid.createUuid()))
            name = data.get('name', 'Imported Conversation')
            created_at = data.get('created_at', datetime.now().isoformat())
            modified_at = data.get('modified_at', created_at)
            current_node_id = data.get('current_node_id')

            # Process root node
            root_data = data.get('root')
            if not root_data:
                raise ValueError("Root node missing in conversation data")

            system_message = root_data.get('content', 'You are a helpful assistant.')

            # Start transaction
            cursor.execute('BEGIN TRANSACTION')

            # Insert conversation
            cursor.execute(
                '''
                INSERT INTO conversations 
                (id, name, created_at, modified_at, current_node_id, system_message)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (conversation_id, name, created_at, modified_at, current_node_id, system_message)
            )

            # Import nodes recursively
            id_mapping = {}  # Old ID -> New ID

            def import_node(node_data, parent_id=None):
                node_id = node_data.get('id', str(QUuid.createUuid()))
                id_mapping[node_id] = node_id  # In this case, we keep original IDs

                role = node_data.get('role', 'user')
                content = node_data.get('content', '')
                timestamp = node_data.get('timestamp', datetime.now().isoformat())

                # Insert message
                cursor.execute(
                    '''
                    INSERT INTO messages
                    (id, conversation_id, parent_id, role, content, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''',
                    (node_id, conversation_id, parent_id, role, content, timestamp)
                )

                # Insert metadata
                if 'model_info' in node_data and node_data['model_info']:
                    for key, value in node_data['model_info'].items():
                        cursor.execute(
                            '''
                            INSERT INTO message_metadata
                            (message_id, metadata_type, metadata_value)
                            VALUES (?, ?, ?)
                            ''',
                            (node_id, f"model_info.{key}", json.dumps(value))
                        )

                if 'parameters' in node_data and node_data['parameters']:
                    for key, value in node_data['parameters'].items():
                        cursor.execute(
                            '''
                            INSERT INTO message_metadata
                            (message_id, metadata_type, metadata_value)
                            VALUES (?, ?, ?)
                            ''',
                            (node_id, f"parameters.{key}", json.dumps(value))
                        )

                if 'token_usage' in node_data and node_data['token_usage']:
                    for key, value in node_data['token_usage'].items():
                        cursor.execute(
                            '''
                            INSERT INTO message_metadata
                            (message_id, metadata_type, metadata_value)
                            VALUES (?, ?, ?)
                            ''',
                            (node_id, f"token_usage.{key}", json.dumps(value))
                        )

                # Insert file attachments
                if 'attached_files' in node_data and node_data['attached_files']:
                    for file_info in node_data['attached_files']:
                        file_id = str(QUuid.createUuid())
                        cursor.execute(
                            '''
                            INSERT INTO file_attachments
                            (id, message_id, file_name, mime_type, content, token_count)
                            VALUES (?, ?, ?, ?, ?, ?)
                            ''',
                            (
                                file_id,
                                node_id,
                                file_info.get('file_name', 'unknown'),
                                file_info.get('mime_type', 'text/plain'),
                                file_info.get('content', ''),
                                file_info.get('token_count', 0)
                            )
                        )

                # Process children
                for child_data in node_data.get('children', []):
                    import_node(child_data, node_id)

                return node_id

            # Start with root node
            root_id = import_node(root_data)

            # Update current_node_id if it's in the mapping
            if current_node_id and current_node_id in id_mapping:
                mapped_current_id = id_mapping[current_node_id]
                cursor.execute(
                    'UPDATE conversations SET current_node_id = ? WHERE id = ?',
                    (mapped_current_id, conversation_id)
                )
            else:
                # Default to root if current_node_id not found
                cursor.execute(
                    'UPDATE conversations SET current_node_id = ? WHERE id = ?',
                    (root_id, conversation_id)
                )

            # Commit transaction
            cursor.execute('COMMIT')

            self.logger.info(f"Successfully imported conversation: {name} (ID: {conversation_id})")

        except Exception as e:
            cursor.execute('ROLLBACK')
            self.logger.error("Error importing conversation from JSON")
            log_exception(self.logger, e, "Failed to import conversation")
            raise
        finally:
            conn.close()