"""
Data models for representing conversation trees with branches.
"""

import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from PyQt6.QtCore import QUuid

from src.utils import CONVERSATIONS_DIR


class MessageNode:
    """
    Represents a single message in a conversation tree
    Each node can have multiple children (responses/branches)
    """

    def __init__(
            self,
            id: str,
            role: str,
            content: str,
            parent=None,
            model_info: Dict = None,
            parameters: Dict = None,
            token_usage: Dict = None,
            attached_files: List[Dict] = None  # New parameter for attached files
    ):
        self.id = id  # Unique identifier for the node
        self.role = role  # 'system', 'user', 'assistant'
        self.content = content  # The message content
        self.parent = parent  # Reference to parent node
        self.children = []  # List of child nodes (responses/branches)
        self.timestamp = datetime.now().isoformat()  # When this message was created

        # For assistant messages only
        self.model_info = model_info or {}  # Model used, system fingerprint, etc.
        self.parameters = parameters or {}  # Temperature, top_p, etc.
        self.token_usage = token_usage or {}  # Token usage statistics

        # For attached files
        self.attached_files = attached_files or []  # List of dictionaries with file information

    def add_child(self, child_node):
        """Add a child node to this node"""
        child_node.parent = self
        self.children.append(child_node)
        return child_node

    def get_path_to_root(self):
        """Return list of nodes from root to this node"""
        path = []
        current = self
        while current:
            path.insert(0, current)
            current = current.parent
        return path

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
                if hasattr(node, 'attached_files') and node.attached_files:
                    message["attached_files"] = node.attached_files

                messages.append(message)
        return messages

    def to_dict(self):
        """Serialize node to dictionary (for saving)"""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "model_info": self.model_info,
            "parameters": self.parameters,
            "token_usage": self.token_usage,
            "attached_files": self.attached_files if hasattr(self, 'attached_files') else [],
            "children": [child.to_dict() for child in self.children]
        }

    @classmethod
    def from_dict(cls, data, parent=None):
        """Create node from dictionary (for loading)"""
        node = cls(
            id=data["id"],
            role=data["role"],
            content=data["content"],
            parent=parent,
            model_info=data.get("model_info"),
            parameters=data.get("parameters"),
            token_usage=data.get("token_usage"),
            attached_files=data.get("attached_files")
        )
        node.timestamp = data.get("timestamp")

        # Recursively create children
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data, parent=node)
            node.children.append(child)

        return node


class ConversationTree:
    """
    Represents a full conversation tree with multiple branches
    """

    def __init__(self, name="New Conversation", id=None):
        self.id = id or str(QUuid.createUuid())
        self.name = name
        self.created_at = datetime.now().isoformat()
        self.modified_at = self.created_at

        # Create root system message
        self.root = MessageNode(
            id=str(QUuid.createUuid()),
            role="system",
            content="You are a helpful assistant."
        )

        # Currently active node (for UI focus)
        self.current_node = self.root

    def add_user_message(self, content, attached_files=None):
        """Add a user message as child of current node"""
        node = MessageNode(
            id=str(QUuid.createUuid()),
            role="user",
            content=content,
            attached_files=attached_files
        )
        self.current_node.add_child(node)
        self.current_node = node
        self.modified_at = datetime.now().isoformat()
        return node



    def add_assistant_response(self, content, model_info=None, parameters=None, token_usage=None):
        """Add an assistant response as child of current node"""
        node = MessageNode(
            id=str(QUuid.createUuid()),
            role="assistant",
            content=content,
            model_info=model_info,
            parameters=parameters,
            token_usage=token_usage
        )
        self.current_node.add_child(node)
        self.current_node = node
        self.modified_at = datetime.now().isoformat()
        return node

    def retry_current_response(self):
        """
        Switch focus to the parent (user message) of the current node
        to allow generating an alternative response
        """
        if self.current_node.role == "assistant" and self.current_node.parent:
            self.current_node = self.current_node.parent
            self.modified_at = datetime.now().isoformat()
            return True
        return False

    def navigate_to_node(self, node_id):
        """Change the current active node"""

        def find_node(current, target_id):
            if current.id == target_id:
                return current

            for child in current.children:
                result = find_node(child, target_id)
                if result:
                    return result

            return None

        node = find_node(self.root, node_id)
        if node:
            self.current_node = node
            self.modified_at = datetime.now().isoformat()
            return True
        return False

    def get_current_branch(self):
        """Get the current active conversation branch"""
        return self.current_node.get_path_to_root()

    def get_current_messages(self):
        """Get message list for API calls based on current branch"""
        return self.current_node.get_messages_to_root()

    def to_dict(self):
        """Serialize tree to dictionary (for saving)"""
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "current_node_id": self.current_node.id,
            "root": self.root.to_dict()
        }

    @classmethod
    def from_dict(cls, data):
        """Create tree from dictionary (for loading)"""
        tree = cls(name=data["name"], id=data["id"])
        tree.created_at = data.get("created_at")
        tree.modified_at = data.get("modified_at")

        # Create tree structure
        tree.root = MessageNode.from_dict(data["root"])

        # Restore current node position
        current_node_id = data.get("current_node_id")
        if current_node_id:
            tree.navigate_to_node(current_node_id)

        return tree


class ConversationManager:
    """
    Manages multiple conversation trees, handles saving/loading
    """

    def __init__(self, save_dir=None):
        self.conversations = {}  # id -> ConversationTree
        self.active_conversation_id = None
        self.save_dir = save_dir or CONVERSATIONS_DIR

        # Create save directory if it doesn't exist
        os.makedirs(self.save_dir, exist_ok=True)

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
        return False

    def create_conversation(self, name="New Conversation"):
        """Create a new conversation"""
        conversation = ConversationTree(name=name)
        self.conversations[conversation.id] = conversation
        self.active_conversation_id = conversation.id
        return conversation

    def delete_conversation(self, conversation_id):
        """Delete a conversation"""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]

            # If we deleted the active conversation, select a new one
            if conversation_id == self.active_conversation_id:
                if self.conversations:
                    self.active_conversation_id = next(iter(self.conversations))
                else:
                    self.active_conversation_id = None

            # Delete saved file
            file_path = os.path.join(self.save_dir, f"{conversation_id}.json")
            if os.path.exists(file_path):
                os.remove(file_path)

            return True
        return False

    def save_conversation(self, conversation_id):
        """Save a single conversation to disk"""
        if conversation_id not in self.conversations:
            return False

        conversation = self.conversations[conversation_id]
        file_path = os.path.join(self.save_dir, f"{conversation_id}.json")

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(conversation.to_dict(), f, ensure_ascii=False, indent=2)

        return True

    def save_all(self):
        """Save all conversations to disk"""
        for conversation_id in self.conversations:
            self.save_conversation(conversation_id)

    def load_conversation(self, file_path):
        """Load a conversation from disk"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            conversation = ConversationTree.from_dict(data)
            self.conversations[conversation.id] = conversation

            # If this is our first conversation, make it active
            if not self.active_conversation_id:
                self.active_conversation_id = conversation.id

            return conversation
        except Exception as e:
            print(f"Error loading conversation: {e}")
            return None

    def load_all(self):
        """Load all conversations from disk"""
        if not os.path.exists(self.save_dir):
            return

        for filename in os.listdir(self.save_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(self.save_dir, filename)
                self.load_conversation(file_path)