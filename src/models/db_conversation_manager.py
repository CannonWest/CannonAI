"""
Database-backed conversation manager for improved scalability and persistence.
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from PyQt6.QtCore import QUuid

from src.utils.logging_utils import get_logger
from src.models.db_manager import DatabaseManager
from src.models.db_conversation import DBConversationTree

# Configure logger for this module
logger = get_logger(__name__)


class DBConversationManager:
    """
    Database-backed conversation manager for improved scalability
    """

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.conversations: Dict[str, DBConversationTree] = {}  # Cache for open conversations
        self.active_conversation_id = None

    @property
    def active_conversation(self):
        """Get the currently active conversation"""
        if self.active_conversation_id and self.active_conversation_id in self.conversations:
            return self.conversations[self.active_conversation_id]
        return None

    def set_active_conversation(self, conversation_id):
        """Set the active conversation by ID"""
        if conversation_id in self.conversations:
            self.active_conversation_id = conversation_id
            return True

        # If not in cache, check if it exists in the database
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

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
        conn.close()
        logger.warning(f"Conversation {conversation_id} not found")
        return False

    def create_conversation(self, name="New Conversation", system_message="You are a helpful assistant."):
        """Create a new conversation"""
        try:
            max_attempts = 5
            for attempt in range(max_attempts):
                new_id = str(QUuid.createUuid())
                # Check if the conversation already exists
                if new_id in self.conversations:
                    logger.warning(f"Conversation with ID {new_id} already exists. Generating a new ID.")
                    continue

                try:
                    conversation = self._create_conversation_in_db(new_id, name, system_message)
                    if conversation and conversation.id:
                        self.conversations[conversation.id] = conversation
                        self.set_active_conversation(conversation.id)
                        logger.info(f"Created new conversation: {name} (ID: {str(conversation.id)})")
                        return conversation
                except ValueError as ve:
                    logger.warning(f"Attempt {attempt + 1}: Failed to create conversation - {str(ve)}")
                    continue

            logger.error(f"Failed to create conversation after {max_attempts} attempts")
            return None
        except Exception as e:
            logger.exception("Failed to create new conversation")
            return None

    def _create_conversation_in_db(self, new_id, name, system_message):
        """Create a new conversation in the database"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        try:
            # First, create the root system message
            root_id = str(QUuid.createUuid())
            now = datetime.now().isoformat()
            cursor.execute(
                '''
                INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
                VALUES (?, ?, NULL, 'system', ?, ?)
                ''',
                (root_id, new_id, system_message, now)
            )
            
            # Insert the new conversation into the database
            cursor.execute(
                '''
                INSERT INTO conversations (id, name, created_at, modified_at, current_node_id, system_message)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (new_id, name, now, now, root_id, system_message)
            )
            conn.commit()
            return DBConversationTree(self.db_manager, id=new_id)
        except Exception as e:
            if conn:
                conn.rollback()
            raise ValueError(f"Failed to create conversation in database: {str(e)}")
        finally:
            if conn:
                conn.close()

    def get_conversation_list(self):
        """Get a list of all conversations"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT id, name, created_at, modified_at
                FROM conversations
                ORDER BY modified_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.exception("Failed to get conversation list")
            return []
        finally:
            conn.close()

    def load_conversation(self, conversation_id):
        """Load a conversation from the database"""
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]

        conversation = DBConversationTree(self.db_manager, id=conversation_id)
        if conversation:
            self.conversations[conversation_id] = conversation
            if not self.active_conversation_id:
                self.active_conversation_id = str(conversation_id)
            logger.info(f"Loaded conversation: {conversation.name} (ID: {conversation_id})")
            return conversation
        logger.warning(f"Failed to load conversation {conversation_id}")
        return None

    def load_all(self):
        """Load conversation list from database"""
        conversation_list = self.get_conversation_list()

        if not conversation_list:
            logger.info("No conversations found in database")
            return

        logger.info(f"Found {len(conversation_list)} conversations in database")

        for conv_info in conversation_list:
            conv_id = conv_info['id']
            if conv_id not in self.conversations:
                self.load_conversation(conv_id)
                logger.debug(f"Loaded conversation: {conv_info['name']} (ID: {conv_id})")

        if not self.active_conversation_id and conversation_list:
            try:
                first_conversation_id = conversation_list[0]['id']
                if first_conversation_id not in self.conversations:
                    self.load_conversation(first_conversation_id)
                self.active_conversation_id = first_conversation_id
                logger.info(f"Set active conversation to: {first_conversation_id}")
            except (IndexError, KeyError) as e:
                logger.warning(f"Failed to set active conversation: {e}")

    def delete_conversation(self, conversation_id):
        """Delete a conversation"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('DELETE FROM conversations WHERE id = ?', (conversation_id,))

            if conversation_id in self.conversations:
                del self.conversations[conversation_id]

            if conversation_id == self.active_conversation_id:
                self.active_conversation_id = None
                conversation_list = self.get_conversation_list()
                if conversation_list:
                    first_id = conversation_list[0]['id']
                    self.load_conversation(first_id)

            conn.commit()
            logger.info(f"Deleted conversation: {conversation_id}")
            return True
        except Exception as e:
            conn.rollback()
            logger.exception(f"Failed to delete conversation {conversation_id}")
            return False
        finally:
            conn.close()

    def save_conversation(self, conversation_id):
        """Save a conversation (no-op for database backend)"""
        if conversation_id in self.conversations:
            logger.debug(f"Save operation called for conversation {conversation_id} (no-op in DB mode)")
            return True
        return False

    def save_all(self):
        """Save all conversations (no-op for database backend)"""
        logger.debug("Save all operation called (no-op in DB mode)")
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

            if conversation_id:
                query += ' AND m.conversation_id = ?'
                params.append(conversation_id)

            if role_filter:
                query += ' AND m.role = ?'
                params.append(role_filter)

            cursor.execute(query, params)

            return [{
                'id': row['id'],
                'conversation_id': row['conversation_id'],
                'conversation_name': row['conversation_name'],
                'role': row['role'],
                'content': row['content'],
                'timestamp': row['timestamp']
            } for row in cursor.fetchall()]
        except Exception as e:
            logger.exception("Failed to search conversations")
            return []
        finally:
            conn.close()
