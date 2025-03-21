"""
Database-backed conversation models for improved scalability and persistence.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional
from PyQt6.QtCore import QUuid

from src.utils.constants import DEFAULT_SYSTEM_MESSAGE
from src.utils.logging_utils import get_logger, log_exception
from src.models.db_types import DBMessageNode
from src.models.db_manager import DatabaseManager  # Lazy import to avoid circular dependency

# Get a logger for this module
logger = get_logger(__name__)


class DBConversationTree:
    """
    Represents a conversation tree with database-backed storage.
    """

    def __init__(
            self,
            db_manager: DatabaseManager,
            id: Optional[str] = None,
            name: str = "New Conversation",
            system_message: str = DEFAULT_SYSTEM_MESSAGE
    ):
        self._longest_branches: Dict[str, List[str]] = {}  # Store longest branch for each branch ID
        self.db_manager = db_manager
        self.id: str
        self.name: str
        self.created_at: str
        self.modified_at: str
        self.current_node_id: str
        self.root_id: str
        self.system_message: str

        # If ID is provided, load existing conversation
        if id and db_manager:
            self._load_conversation(id)
            if not hasattr(self, 'id'):
                raise ValueError(f"Conversation with ID {id} not found")
        # Note: We've removed the else clause as new conversations are now created in the database first

    def update_name(self, new_name):
        """Update the conversation name in the database"""
        with self.db_manager.get_connection() as conn:
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

    def _load_conversation(self, conversation_id):
        """Load conversation from database"""
        with self.db_manager.get_connection() as conn:
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
                self.system_message = conversation['system_message']

                print(f"DEBUG: Loaded conversation '{self.name}' with ID {self.id}")

                # Find root node
                cursor.execute(
                    'SELECT id FROM messages WHERE conversation_id = ? AND parent_id IS NULL',
                    (self.id,)
                )
                root_result = cursor.fetchone()

                if not root_result:
                    self._create_root_node(cursor, self.system_message)

                self.root_id = root_result['id']

            except Exception as e:
                logger.error(f"Error loading conversation {conversation_id}")
                log_exception(logger, e, f"Failed to load conversation {conversation_id}")
                raise

    def _create_root_node(self, cursor, system_message):
        """Create a root node for the conversation if it doesn't exist"""
        root_id = str(QUuid.createUuid())
        now = datetime.now().isoformat()

        cursor.execute(
            '''
            INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp)
            VALUES (?, ?, NULL, 'system', ?, ?)
            ''',
            (root_id, self.id, system_message, now)
        )

        cursor.execute(
            '''
            UPDATE conversations SET current_node_id = ? WHERE id = ?
            ''',
            (root_id, self.id)
        )

    def _create_new_conversation(self, name: str, system_message: str):
        """Create a new conversation in the database"""
        with self.db_manager.get_connection() as conn:
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
                    (self.id, name, now, now, root_id, system_message)
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

    @property
    def root(self):
        """Get the root node"""
        return self.get_node(self.root_id)

    @root.setter
    def root(self, value):
        """
        Setter for root (used in testing).
        This doesn't change the actual root_id but allows tests to mock the root property.
        """
        self._root_for_testing = value

    @property
    def current_node(self):
        """Get the current node"""
        return self.get_node(self.current_node_id) if self.current_node_id else None

    @current_node.setter
    def current_node(self, value):
        """
        Setter for current_node (used in testing).
        This doesn't change the actual current_node_id but allows tests to mock the current_node property.
        """
        self._current_node_for_testing = value

    def get_node(self, node_id):
        """Get a node by ID, with support for test mocks"""
        if not node_id:
            return None

        # For testing - return the mocked object if it exists and the IDs match
        if hasattr(self, '_root_for_testing') and self.root_id == node_id:
            return self._root_for_testing

        if hasattr(self, '_current_node_for_testing') and self.current_node_id == node_id:
            return self._current_node_for_testing

        with self.db_manager.get_connection() as conn:
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

                # Create the node with response_id from the database
                node = DBMessageNode(
                    id=str(message['id']),
                    conversation_id=message['conversation_id'],
                    role=message['role'],
                    content=message['content'],
                    parent_id=message['parent_id'],
                    timestamp=message['timestamp'],
                    model_info=model_info,
                    parameters=parameters,
                    token_usage=token_usage,
                    attached_files=attached_files,
                    response_id=message['response_id']
                )

                # Set database manager for lazy loading children
                node._db_manager = self.db_manager

                return node

            except Exception as e:
                logger.error(f"Error getting node {node_id}")
                log_exception(logger, e, f"Failed to get node {node_id}")
                raise

    def add_user_message(self, content, attached_files=None):
        """Add a user message as a child of the current node"""
        with self.db_manager.get_connection() as conn:
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

    def add_assistant_response(self, content, model_info=None, parameters=None, token_usage=None, response_id=None):
        """Add an assistant response as a child of the current node, with Response API support"""
        with self.db_manager.get_connection() as conn:
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

    def add_system_response(self, content, model_info=None, parameters=None, token_usage=None, response_id=None):
        """Add a system response as a child of the current node, with Response API support"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            try:
                node_id = str(QUuid.createUuid())
                now = datetime.now().isoformat()

                # Insert message
                cursor.execute(
                    '''
                    INSERT INTO messages (id, conversation_id, parent_id, role, content, timestamp, response_id)
                    VALUES (?, ?, ?, 'system', ?, ?, ?)
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
                logger.error(f"Error adding system response")
                log_exception(logger, e, "Failed to add system response")
                raise

    def navigate_to_node(self, node_id):
        """Change the current active node"""
        with self.db_manager.get_connection() as conn:
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

                # Store the old node ID (unused, consider removing)
                old_node_id = self.current_node_id

                # Update current node - needed before getting branch
                self.current_node_id = node_id

                # Get the current branch for this node
                current_branch = self.get_current_branch()
                if current_branch:
                    # Get the first node of this branch for tracking
                    # We use the first two nodes to identify a branch uniquely
                    # (The first node is usually system, but second node identifies the branch)
                    if len(current_branch) >= 2:
                        branch_id = current_branch[1].id  # Use the second node
                    else:
                        branch_id = current_branch[0].id  # Fallback to first node

                    # Get all node IDs in the current branch
                    current_node_ids = [node.id for node in current_branch if node is not None]

                    # Check if we've seen a longer version of this branch before
                    if branch_id in self._longest_branches:
                        longest_node_ids = self._longest_branches[branch_id]

                        # If the current branch is longer, update our record
                        if len(current_node_ids) > len(longest_node_ids):
                            logger.debug(f"Found longer version of branch {branch_id}, updating record from {len(longest_node_ids)} to {len(current_node_ids)} nodes")
                            self._longest_branches[branch_id] = current_node_ids
                    else:
                        # First time seeing this branch, record it
                        logger.debug(f"First time seeing branch {branch_id}, recording {len(current_node_ids)} nodes")
                        self._longest_branches[branch_id] = current_node_ids

                    # Debug log
                    logger.debug(f"Currently viewing branch {branch_id} which has {len(current_node_ids)} visible nodes")
                    if branch_id in self._longest_branches:
                        logger.debug(f"Longest version of this branch has {len(self._longest_branches[branch_id])} nodes")

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
                logger.error(f"Error in navigate_to_node: {str(e)}")
                if conn:
                    conn.rollback()
                return False

    def _update_active_branch(self, node_id, current_branch_node_ids):
        """
        Update the active branch based on node navigation.

        This identifies which branch we're on when navigating to a specific node,
        looking for the most specific branch that contains this node.
        """
        try:
            logger.debug(f"Updating active branch for node {node_id}")
            logger.debug(f"Current branch has {len(current_branch_node_ids)} nodes")
            logger.debug(f"We have {len(self._branch_paths)} branches tracked")

            # If this is a leaf node, set it as the active branch
            if current_branch_node_ids and current_branch_node_ids[-1] == node_id:
                self._active_branch_id = node_id
                logger.debug(f"Node is a leaf node, setting as active branch")
                return

            # Find the most specific branch containing this node
            best_branch_id = None
            best_position = -1

            for branch_id, branch_nodes in self._branch_paths.items():
                if node_id in branch_nodes:
                    # Calculate position from the *beginning* of the list (not the end)
                    # This gives us node depth, which is more important
                    position = branch_nodes.index(node_id)

                    logger.debug(f"Node found in branch {branch_id} at position {position}")

                    # If this branch has exactly the same path to the node (more specific),
                    # or if the node is deeper in this branch, use it
                    if best_branch_id is None or position > best_position:
                        best_position = position
                        best_branch_id = branch_id
                        logger.debug(f"New best branch: {branch_id} with position {position}")

            # Set the active branch
            if best_branch_id:
                self._active_branch_id = best_branch_id
                logger.debug(f"Selected branch {best_branch_id} as active (node at position {best_position})")
            else:
                # No existing branch contains this node, create a new branch record
                if current_branch_node_ids:
                    leaf_id = current_branch_node_ids[-1]
                    self._active_branch_id = leaf_id
                    logger.debug(f"Created new active branch {leaf_id} for node {node_id}")
                else:
                    logger.warning(f"No branch nodes available for node {node_id}")
                    self._active_branch_id = node_id  # Default to current node
        except Exception as e:
            logger.error(f"Error updating active branch: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def retry_current_response(self):
        """
        Switch focus to the parent (user message) of the current node
        to allow generating an alternative response.
        """
        current = self.current_node

        if current.role == "assistant" and current.parent_id:
            return self.navigate_to_node(current.parent_id)

        return False

    def get_current_branch(self):
        """Get the current active conversation branch."""
        return self.current_node.get_path_to_root()

    def get_current_branch_future(self):
        """
        Get the current branch including future nodes from our stored longest version.
        """
        # Get the current branch we're viewing
        current_branch = self.get_current_branch()
        if not current_branch:
            logger.warning("No current branch available")
            return current_branch

        # Get the current node ID
        current_id = str(self.current_node_id)
        logger.debug(f"get_current_branch_future called, current node: {current_id}")

        # Identify the branch we're on using the second message
        branch_id = None
        if len(current_branch) >= 2:
            branch_id = str(current_branch[1].id)
        else:
            branch_id = str(current_branch[0].id)

        logger.debug(f"Current branch identified as {branch_id}")

        # Check if we have a longer version of this branch stored
        if branch_id not in self._longest_branches:
            logger.debug(f"No longer version of this branch found")
            return current_branch

        # Get the longest version of this branch
        longest_node_ids = self._longest_branches[branch_id]
        logger.debug(f"Longest version of this branch has {len(longest_node_ids)} nodes")

        # Check if current node is in the longest branch
        if current_id not in longest_node_ids:
            logger.debug(f"Current node not found in longest branch - this should not happen!")
            return current_branch

        # Get the position of current node in the longest branch
        current_pos = longest_node_ids.index(current_id)
        logger.debug(f"Current node at position {current_pos} in longest branch of length {len(longest_node_ids)}")

        # If this is already the last node in the longest branch, no future to show
        if current_pos == len(longest_node_ids) - 1:
            logger.debug("Current node is last in longest branch, no future to show")
            return current_branch

        # Build the full branch with node objects (contains future nodes)
        full_branch = []
        for node_id in longest_node_ids:
            node = self.get_node(node_id)
            if node:
                full_branch.append(node)
            else:
                logger.warning(f"Could not fetch node {node_id} for branch")

        # Log how many future nodes we have
        future_count = len(longest_node_ids) - current_pos - 1
        logger.debug(f"Returning branch with {future_count} future nodes")

        return full_branch

    def get_current_messages(self):
        """Get message list for API calls based on current branch."""
        return self.current_node.get_messages_to_root()

    def to_dict(self):
        """Serialize tree to dictionary (for compatibility with old format)."""
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "current_node_id": self.current_node_id,
            "root": self.root.to_dict()
        }

    def delete(self):
        """Delete the conversation and all associated messages from the database."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Delete all messages associated with this conversation
                cursor.execute('DELETE FROM messages WHERE conversation_id = ?', (self.id,))

                # Delete all metadata associated with messages in this conversation
                cursor.execute('DELETE FROM message_metadata WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = ?)', (self.id,))

                # Delete all file attachments associated with messages in this conversation
                cursor.execute('DELETE FROM file_attachments WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = ?)', (self.id,))

                # Delete the conversation itself
                cursor.execute('DELETE FROM conversations WHERE id = ?', (self.id,))

                conn.commit()
                logger.info(f"Deleted conversation {self.id} and all associated data")
            except Exception as e:
                conn.rollback()
                logger.error(f"Error deleting conversation {self.id}")
                log_exception(logger, e, f"Failed to delete conversation {self.id}")
                raise
