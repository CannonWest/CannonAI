"""
Database types for the OpenAI Chat application.
This module contains shared type definitions to avoid circular imports.
"""

from typing import Dict, List, Optional
from datetime import datetime


class DBMessageNode:
    """
    Represents a single message in a conversation with database-backed storage.
    """

    def __init__(
            self,
            id: str,
            conversation_id: str,
            role: str,
            content: str,
            parent_id: Optional[str] = None,
            timestamp: Optional[str] = None,
            model_info: Optional[Dict] = None,
            parameters: Optional[Dict] = None,
            token_usage: Optional[Dict] = None,
            attached_files: Optional[List[Dict]] = None,
            response_id: Optional[str] = None
    ):
        self._reasoning_steps: Optional[List[str]] = None
        self._children: Optional[List['DBMessageNode']] = None
        self._db_manager = None

        self.id = str(id)
        self.conversation_id = conversation_id
        self.role = role
        self.content = content
        self.parent_id = parent_id
        self.timestamp = timestamp or datetime.now().isoformat()

        # OpenAI Response API data
        self.response_id = response_id

        # Assistant message metadata
        self.model_info = model_info or {}
        self.parameters = parameters or {}
        self.token_usage = token_usage or {}
        self.attached_files = attached_files or []

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
            return self._db_manager.get_node(self.parent_id)
        return None

    @property
    def reasoning_steps(self):
        """Get reasoning steps if they exist"""
        # Note: Reasoning steps are currently not supported by the OpenAI API
        # This property is kept for future compatibility when reasoning becomes available
        if hasattr(self, '_reasoning_steps') and self._reasoning_steps is not None:
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

        # Always return an empty list as default instead of None
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
