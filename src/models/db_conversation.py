# src/models/db_conversation.py
"""
Database-backed conversation models for improved scalability.
"""

import os
import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from PyQt6.QtCore import QUuid

from src.utils.logging_utils import get_logger, log_exception
from src.models.db_manager import DatabaseManager

# Get a logger for this module
logger = get_logger(__name__)


class DBMessageNode:
    """
    Represents a single message in a conversation
    with database-backed storage
    """

    def __init__(
            self,
            id: str,
            conversation_id: str,
            role: str,
            content: str,
            parent_id: Optional[str] = None,
            timestamp: Optional[str] = None,
            model_info: Dict = None,
            parameters: Dict = None,
            token_usage: Dict = None,
            attached_files: List[Dict] = None,
            response_id: Optional[str] = None  # New: store OpenAI Response ID
    ):
        self._reasoning_steps = None
        self.id = id
        self.conversation_id = conversation_id
        self.role = role
        self.content = content
        self.parent_id = parent_id
        self.timestamp = timestamp or datetime.now().isoformat()

        # Store Response API data
        self.response_id = response_id

        # For assistant messages only
        self.model_info = model_info or {}
        self.parameters = parameters or {}
        self.token_usage = token_usage or {}

        # For attached files
        self.attached_files = attached_files or []

        # Children will be loaded on demand
        self._children = None
        self._db_manager = None

    @property
    def children(self):
        """Lazy-load children when requested"""
        if self._children is None and self._db_manager:
            self._children = self._db_manager.get_node_children(self.id)
        return self._children or []

    @property
    def parent(self):
        """Lazy-load parent when requested for compatibility with UI code"""
        if self.parent_id and self._db_manager:
            return self._db_manager.get_message(self.parent_id)
        return None

    @property
    def reasoning_steps(self):
        """Get reasoning steps if they exist"""
        # Note: Reasoning steps are currently not supported by the OpenAI API
        # This property is kept for future compatibility when reasoning becomes available
        if hasattr(self, '_reasoning_steps'):
            return self._reasoning_steps

        # Try to load from database if we have a manager
        if self._db_manager:
            try:
                # Get metadata info including reasoning steps
                _, _, _, steps = self._db_manager.get_node_metadata(self.id)
                if steps:
                    self._reasoning_steps = steps
                    return steps
            except Exception as e:
                print(f"Error retrieving reasoning steps: {str(e)}")

        return []

    @reasoning_steps.setter
    def reasoning_steps(self, steps):
        """Set reasoning steps and store in database"""
        self._reasoning_steps = steps

    def add_child(self, child_node):
        """Add a child node to this node (compatibility method)"""
        # This is just for in-memory operation during a session
        # Actual database changes should be done through the DBConversationTree
        if self._children is None:
            self._children = []
        self._children.append(child_node)
        return child_node

    def get_path_to_root(self):
        """Return list of nodes from root to this node"""
        if not self._db_manager:
            return [self]
        return self._db_manager.get_path_to_root(self.id)

    def get_messages_to_root(self):
        """Return list of message dicts from root to this node for API calls"""
        messages = []
        for node in self.get_path_to_root():
            if node.role in ['system', 'user', 'assistant', 'developer']:
                message = {
                    "role": node.role,
                    "content": node.content
                }

                # Include attached files if present
                if node.attached_files:
                    message["attached_files"] = node.attached_files

                messages.append(message)
        return messages

    def to_dict(self):
        """Serialize node to dictionary (for compatibility)"""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "model_info": self.model_info,
            "parameters": self.parameters,
            "token_usage": self.token_usage,
            "attached_files": self.attached_files,
            "children": [child.to_dict() for child in self.children]
        }


class DBConversationTree:
    """
    Represents a conversation tree with database-backed storage
    """

    def __init__(
            self,
            db_manager: DatabaseManager,
            id: str = None,
            name: str = "New Conversation",
            system_message: str = "You are a helpful assistant."
    ):
        self.db_manager = db_manager

        # If ID is provided, load existing conversation
        if id:
            self._load_conversation(id)
        else:
            # Create new conversation
            self.id = str(QUuid.createUuid())
            self.name = name
            self.created_at = datetime.now().isoformat()
            self.modified_at = self.created_at

            # Create root system message
            self._create_new_conversation(system_message)

    def update_name(self, new_name):
        """Update the conversation name in the database"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            # Update the name in the database
            cursor.execute(
                'UPDATE conversations SET name = ? WHERE id = ?',
                (new_name, self.id)
            )

            # Update the in-memory property
            self.name = new_name

            # Update modified timestamp
            now = datetime.now().isoformat()
            self.modified_at = now
            cursor.execute(
                'UPDATE conversations SET modified_at = ? WHERE id = ?',
                (now, self.id)
            )

            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            return False
        finally:
            conn.close()

    def _load_conversation(self, conversation_id):
        """Load conversation from database"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            # Get conversation metadata
            cursor.execute(
                'SELECT * FROM conversations WHERE id = ?',
                (conversation_id,)
            )
            conversation = cursor.fetchone()

            if not conversation:
                raise ValueError(f"Conversation with ID {conversation_id} not found")

            # Set properties
            self.id = conversation['id']
            self.name = conversation['name']
            self.created_at = conversation['created_at']
            self.modified_at = conversation['modified_at']
            self.current_node_id = conversation['current_node_id']

            print(f"DEBUG: Loaded conversation '{self.name}' with ID {self.id}")

            # Find root node
            cursor.execute(
                'SELECT id FROM messages WHERE conversation_id = ? AND parent_id IS NULL',
                (self.id,)
            )
            root_result = cursor.fetchone()

            if not root_result:
                raise ValueError(f"Root node for conversation {self.id} not found")

            self.root_id = root_result['id']

        except Exception as e:
            logger.error(f"Error loading conversation {conversation_id}")
            log_exception(logger, e, f"Failed to load conversation {conversation_id}")
            raise
        finally:
            conn.close()

    def _create_new_conversation(self, system_message):
        """Create a new conversation in the database"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            # Create root system message
            root_id = str(QUuid.createUuid())
            now = datetime.now().isoformat()

            # Insert system message
            cursor.execute(
                '''
                INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
                VALUES (?, ?, NULL, 'system', ?, ?)
                ''',
                (root_id, self.id, system_message, now)
            )

            # Insert conversation with root as current node
            cursor.execute(
                '''
                INSERT INTO conversations 
                (id, name, created_at, modified_at, current_node_id, system_message)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (self.id, self.name, self.created_at, self.modified_at, root_id, system_message)
            )

            conn.commit()

            # Set properties
            self.root_id = root_id
            self.current_node_id = root_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating new conversation")
            log_exception(logger, e, "Failed to create new conversation")
            raise
        finally:
            conn.close()

    @property
    def root(self):
        """Get the root node"""
        return self.get_node(self.root_id)

    @property
    def current_node(self):
        """Get the current node"""
        return self.get_node(self.current_node_id)

    def get_node(self, node_id):
        """Get a node by ID"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            # Get the message
            cursor.execute(
                'SELECT * FROM messages WHERE id = ?',
                (node_id,)
            )
            message = cursor.fetchone()

            if not message:
                raise ValueError(f"Message with ID {node_id} not found")

            # Get metadata
            model_info = {}
            parameters = {}
            token_usage = {}

            cursor.execute(
                'SELECT metadata_type, metadata_value FROM message_metadata WHERE message_id = ?',
                (node_id,)
            )

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

            # Get file attachments
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

            # Create the node
            node = DBMessageNode(
                id=message['id'],
                conversation_id=message['conversation_id'],
                role=message['role'],
                content=message['content'],
                parent_id=message['parent_id'],
                timestamp=message['timestamp'],
                model_info=model_info,
                parameters=parameters,
                token_usage=token_usage,
                attached_files=attached_files
            )

            # Set database manager for lazy loading children
            node._db_manager = self.db_manager

            return node

        except Exception as e:
            logger.error(f"Error getting node {node_id}")
            log_exception(logger, e, f"Failed to get node {node_id}")
            raise
        finally:
            conn.close()

    def add_user_message(self, content, attached_files=None):
        """Add a user message as child of current node"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            node_id = str(QUuid.createUuid())
            now = datetime.now().isoformat()

            # Insert message
            cursor.execute(
                '''
                INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
                VALUES (?, ?, ?, 'user', ?, ?)
                ''',
                (node_id, self.id, self.current_node_id, content, now)
            )

            # Add file attachments if present
            if attached_files:
                for file_info in attached_files:
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
                            file_info['file_name'],
                            file_info.get('mime_type', 'text/plain'),
                            file_info['content'],
                            file_info.get('token_count', 0)
                        )
                    )

            # Update current node
            self.current_node_id = node_id

            # Update conversation modified time
            self.modified_at = now
            cursor.execute(
                'UPDATE conversations SET current_node_id = ?, modified_at = ? WHERE id = ?',
                (node_id, now, self.id)
            )

            conn.commit()

            # Return the new node
            return self.get_node(node_id)

        except Exception as e:
            conn.rollback()
            logger.error(f"Error adding user message")
            log_exception(logger, e, "Failed to add user message")
            raise
        finally:
            conn.close()

    def add_assistant_response(self, content, model_info=None, parameters=None, token_usage=None, response_id=None):
        """Add an assistant response as child of current node, with Response API support"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            node_id = str(QUuid.createUuid())
            now = datetime.now().isoformat()

            # Insert message
            cursor.execute(
                '''
                INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp, response_id)
                VALUES (?, ?, ?, 'assistant', ?, ?, ?)
                ''',
                (node_id, self.id, self.current_node_id, content, now, response_id)
            )

            # Add metadata if provided
            if model_info:
                for key, value in model_info.items():
                    cursor.execute(
                        '''
                        INSERT INTO message_metadata (message_id, metadata_type, metadata_value)
                        VALUES (?, ?, ?)
                        ''',
                        (node_id, f"model_info.{key}", json.dumps(value))
                    )

            if parameters:
                for key, value in parameters.items():
                    cursor.execute(
                        '''
                        INSERT INTO message_metadata (message_id, metadata_type, metadata_value)
                        VALUES (?, ?, ?)
                        ''',
                        (node_id, f"parameters.{key}", json.dumps(value))
                    )

            if token_usage:
                for key, value in token_usage.items():
                    cursor.execute(
                        '''
                        INSERT INTO message_metadata (message_id, metadata_type, metadata_value)
                        VALUES (?, ?, ?)
                        ''',
                        (node_id, f"token_usage.{key}", json.dumps(value))
                    )

            # Update current node
            self.current_node_id = node_id

            # Update conversation modified time
            self.modified_at = now
            cursor.execute(
                'UPDATE conversations SET current_node_id = ?, modified_at = ? WHERE id = ?',
                (node_id, now, self.id)
            )

            conn.commit()

            # Return the new node
            return self.get_node(node_id)

        except Exception as e:
            conn.rollback()
            logger.error(f"Error adding assistant response")
            log_exception(logger, e, "Failed to add assistant response")
            raise
        finally:
            conn.close()

    def navigate_to_node(self, node_id):
        """Change the current active node"""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        try:
            # Verify the node exists and belongs to this conversation
            cursor.execute(
                'SELECT id FROM messages WHERE id = ? AND conversation_id = ?',
                (node_id, self.id)
            )

            if not cursor.fetchone():
                logger.warning(f"Node {node_id} not found in conversation {self.id}")
                return False

            # Update current node
            self.current_node_id = node_id

            # Update in database
            now = datetime.now().isoformat()
            self.modified_at = now

            cursor.execute(
                'UPDATE conversations SET current_node_id = ?, modified_at = ? WHERE id = ?',
                (node_id, now, self.id)
            )

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Error navigating to node {node_id}")
            log_exception(logger, e, f"Failed to navigate to node {node_id}")
            return False
        finally:
            conn.close()

    def retry_current_response(self):
        """
        Switch focus to the parent (user message) of the current node
        to allow generating an alternative response
        """
        current = self.current_node

        if current.role == "assistant" and current.parent_id:
            return self.navigate_to_node(current.parent_id)

        return False

    def get_current_branch(self):
        """Get the current active conversation branch"""
        return self.current_node.get_path_to_root()

    def get_current_messages(self):
        """Get message list for API calls based on current branch"""
        return self.current_node.get_messages_to_root()

    def to_dict(self):
        """Serialize tree to dictionary (for compatibility with old format)"""
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "current_node_id": self.current_node_id,
            "root": self.root.to_dict()
        }