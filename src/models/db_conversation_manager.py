# src/models/db_conversation_manager.py
"""
Database-backed conversation manager for improved scalability.
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from PyQt6.QtCore import QUuid

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

