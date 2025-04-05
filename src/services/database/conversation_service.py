"""
Service class for managing conversations and messages using SQLAlchemy.
Adapted for web-based architecture with FastAPI.
"""

import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple, Union

from sqlalchemy import select, delete, update, or_, func
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

from src.models.orm_models import Conversation, Message, FileAttachment
from src.services.database.db_manager import DatabaseManager

# Create logger for this module
logger = logging.getLogger(__name__)


class ConversationService:
    """
    Service class for managing conversations and messages.
    Uses SQLAlchemy ORM for database operations.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize the conversation service.

        Args:
            db_manager: Database manager instance. If None, uses the default instance.
        """
        self.logger = logging.getLogger(f"{__name__}.ConversationService")

        # Use provided db_manager or get the default one
        self.db_manager = db_manager or DatabaseManager()

        # Initialize database if needed
        self._initialized = self.initialize()

        # Local cache for performance (optional)
        self._conversation_cache = {}
        self._message_cache = {}

        self.logger.info("ConversationService initialized")

    def initialize(self) -> bool:
        """
        Initialize database tables.

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("Initializing ConversationService database tables")
        return self.db_manager.create_tables()

    # --- Conversation CRUD Operations ---

    def create_conversation(self, db: Session, name: str = "New Conversation",
                            system_message: str = "You are a helpful assistant.") -> Conversation:
        """
        Create a new conversation with an initial system message.

        Args:
            db: SQLAlchemy session
            name: Name of the conversation
            system_message: System message content

        Returns:
            The created Conversation object
        """
        self.logger.debug(f"Creating conversation: {name}")

        # Create conversation
        conv_id = str(uuid.uuid4())
        conversation = Conversation(
            id=conv_id,
            name=name,
            system_message=system_message
        )
        db.add(conversation)
        db.flush()  # Flush to get conversation ID if needed by message

        # Create system message
        msg_id = str(uuid.uuid4())
        message = Message(
            id=msg_id,
            conversation_id=conversation.id,
            role="system",
            content=system_message
        )
        db.add(message)
        db.flush()  # Flush to get message ID

        # Set current node
        conversation.current_node_id = message.id
        db.add(conversation)

        # Commit happens at the route level
        self.logger.info(f"Created conversation {conversation.id} with name '{name}'")

        # Update cache
        self._conversation_cache[conversation.id] = conversation

        return conversation

    def get_conversation(self, db: Session, id: str, use_cache: bool = True) -> Optional[Conversation]:
        """
        Get a conversation by ID.

        Args:
            db: SQLAlchemy session
            id: Conversation ID
            use_cache: Whether to check the cache first

        Returns:
            Conversation object or None if not found
        """
        self.logger.debug(f"Getting conversation: {id}")

        # Check cache first if enabled
        if use_cache and id in self._conversation_cache:
            self.logger.debug(f"Using cached conversation: {id}")
            return self._conversation_cache[id]

        # Query database
        query = select(Conversation).where(Conversation.id == id)
        conversation = db.execute(query).scalars().first()

        if conversation:
            # Update cache
            self._conversation_cache[id] = conversation
        else:
            self.logger.warning(f"Conversation {id} not found")

        return conversation

    def get_conversation_with_messages(self, db: Session, id: str) -> Optional[Conversation]:
        """
        Get a conversation by ID with all messages eager-loaded.

        Args:
            db: SQLAlchemy session
            id: Conversation ID

        Returns:
            Conversation object with messages or None if not found
        """
        self.logger.debug(f"Getting conversation with messages: {id}")

        query = select(Conversation).where(Conversation.id == id).options(
            selectinload(Conversation.messages).selectinload(Message.file_attachments)
        )
        conversation = db.execute(query).scalars().first()

        if not conversation:
            self.logger.warning(f"Conversation {id} not found")

        return conversation

    def get_all_conversations(self, db: Session, skip: int = 0, limit: int = 100) -> List[Conversation]:
        """
        Get all conversations with pagination.

        Args:
            db: SQLAlchemy session
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of conversations ordered by last modified time
        """
        self.logger.debug(f"Getting all conversations (skip={skip}, limit={limit})")

        query = select(Conversation).order_by(Conversation.modified_at.desc()).offset(skip).limit(limit)
        conversations = db.execute(query).scalars().all()

        self.logger.info(f"Found {len(conversations)} conversations")
        return conversations

    def update_conversation(self, db: Session, id: str, data: Dict[str, Any]) -> Optional[Conversation]:
        """
        Update a conversation.

        Args:
            db: SQLAlchemy session
            id: Conversation ID
            data: Dictionary of fields to update

        Returns:
            Updated conversation or None if not found
        """
        self.logger.debug(f"Updating conversation {id} with {list(data.keys())}")

        conversation = db.get(Conversation, id)
        if not conversation:
            self.logger.warning(f"Conversation {id} not found for update")
            return None

        # Update fields
        for key, value in data.items():
            if hasattr(conversation, key):
                setattr(conversation, key, value)

        # Always update the modified timestamp
        conversation.modified_at = datetime.utcnow()

        # Commit happens at the route level
        self.logger.info(f"Updated conversation {id}")

        # Update cache
        self._conversation_cache[id] = conversation

        return conversation

    def delete_conversation(self, db: Session, id: str) -> bool:
        """
        Delete a conversation and all its messages.

        Args:
            db: SQLAlchemy session
            id: Conversation ID

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Deleting conversation: {id}")

        # Find the conversation
        conversation = db.get(Conversation, id)
        if not conversation:
            self.logger.warning(f"Conversation {id} not found for deletion")
            return False

        # Clear current_node_id reference first
        conversation.current_node_id = None
        db.flush()

        # Delete conversation (cascade will handle messages)
        db.delete(conversation)

        # Remove from cache
        if id in self._conversation_cache:
            del self._conversation_cache[id]

        self.logger.info(f"Deleted conversation {id}")
        return True

    def duplicate_conversation(self, db: Session, original_id: str, new_name: Optional[str] = None) -> Optional[Conversation]:
        """
        Creates a deep copy of a conversation and its messages.

        Args:
            db: SQLAlchemy session
            original_id: The ID of the conversation to duplicate
            new_name: The name for the new conversation. If None, uses "Original Name (Copy)"

        Returns:
            The newly created Conversation object or None if failed
        """
        self.logger.info(f"Duplicating conversation: {original_id}")

        # Get the original conversation with all messages
        original_conv = self.get_conversation_with_messages(db, original_id)
        if not original_conv:
            self.logger.warning(f"Original conversation {original_id} not found for duplication")
            return None

        # Determine new name
        final_new_name = new_name if new_name else f"{original_conv.name} (Copy)"

        # Create the new conversation
        new_conv_id = str(uuid.uuid4())
        new_conv = Conversation(
            id=new_conv_id,
            name=final_new_name,
            system_message=original_conv.system_message
        )
        db.add(new_conv)

        # Get all messages from original conversation
        if not original_conv.messages:
            self.logger.warning(f"Conversation {original_id} has no messages to duplicate")
            return new_conv

        # Create mapping for message IDs
        message_id_map = {}  # original_id -> new_id
        new_messages_map = {}  # new_id -> new_message_object

        # First pass: create all messages without parent links
        for original_msg in original_conv.messages:
            new_msg_id = str(uuid.uuid4())
            message_id_map[original_msg.id] = new_msg_id

            new_msg = Message(
                id=new_msg_id,
                conversation_id=new_conv_id,
                role=original_msg.role,
                content=original_msg.content,
                timestamp=original_msg.timestamp,
                response_id=original_msg.response_id,
                model_info=original_msg.model_info,
                parameters=original_msg.parameters,
                token_usage=original_msg.token_usage,
                reasoning_steps=original_msg.reasoning_steps
            )

            db.add(new_msg)
            new_messages_map[new_msg_id] = new_msg

            # Copy attachments if any
            if original_msg.file_attachments:
                for orig_att in original_msg.file_attachments:
                    new_att_id = str(uuid.uuid4())
                    new_att = FileAttachment(
                        id=new_att_id,
                        message_id=new_msg_id,
                        file_name=orig_att.file_name,
                        display_name=orig_att.display_name,
                        mime_type=orig_att.mime_type,
                        token_count=orig_att.token_count,
                        file_size=orig_att.file_size,
                        file_hash=orig_att.file_hash,
                        storage_type=orig_att.storage_type,
                        content_preview=orig_att.content_preview,
                        storage_path=orig_att.storage_path,
                        content=orig_att.content
                    )
                    db.add(new_att)

        # Second pass: set parent_id links
        for original_id, new_id in message_id_map.items():
            # Find the original message to get its parent_id
            original_msg = next((m for m in original_conv.messages if m.id == original_id), None)
            if not original_msg:
                continue

            if original_msg.parent_id:
                # Find the corresponding new parent ID
                new_parent_id = message_id_map.get(original_msg.parent_id)
                if new_parent_id:
                    new_message = new_messages_map[new_id]
                    new_message.parent_id = new_parent_id

        # Set current_node_id for the new conversation
        if original_conv.current_node_id:
            new_current_node_id = message_id_map.get(original_conv.current_node_id)
            if new_current_node_id:
                new_conv.current_node_id = new_current_node_id

        db.flush()

        # Update cache
        self._conversation_cache[new_conv.id] = new_conv

        self.logger.info(f"Successfully duplicated conversation {original_id} to {new_conv.id}")
        return new_conv

    # --- Message Operations ---

    def add_user_message(self, db: Session, conversation_id: str, content: str,
                         parent_id: Optional[str] = None) -> Optional[Message]:
        """
        Add a user message to a conversation.

        Args:
            db: SQLAlchemy session
            conversation_id: Conversation ID
            content: Message content
            parent_id: Parent message ID. If None, uses conversation's current node

        Returns:
            The created Message object or None if failed
        """
        self.logger.debug(f"Adding user message to conversation: {conversation_id}")

        # Get conversation
        conversation = db.get(Conversation, conversation_id)
        if not conversation:
            self.logger.warning(f"Conversation {conversation_id} not found")
            return None

        # Determine parent ID
        actual_parent_id = parent_id if parent_id is not None else conversation.current_node_id

        # Create message
        msg_id = str(uuid.uuid4())
        message = Message(
            id=msg_id,
            role="user",
            content=content,
            conversation_id=conversation_id,
            parent_id=actual_parent_id
        )
        db.add(message)
        db.flush()

        # Update conversation's current node and modified time
        conversation.current_node_id = message.id
        conversation.modified_at = datetime.utcnow()
        db.add(conversation)

        # Update cache
        self._message_cache[message.id] = message
        self._conversation_cache[conversation_id] = conversation

        self.logger.info(f"Added user message {message.id} to conversation {conversation_id}")
        return message

    def add_assistant_message(self, db: Session, conversation_id: str, content: str,
                              parent_id: Optional[str] = None, model_info: Optional[Dict] = None,
                              token_usage: Optional[Dict] = None, reasoning_steps: Optional[List] = None,
                              response_id: Optional[str] = None) -> Optional[Message]:
        """
        Add an assistant message to a conversation.

        Args:
            db: SQLAlchemy session
            conversation_id: Conversation ID
            content: Message content
            parent_id: Parent message ID. If None, uses conversation's current node
            model_info: Model information dictionary
            token_usage: Token usage statistics
            reasoning_steps: List of reasoning steps
            response_id: Response ID from the API

        Returns:
            The created Message object or None if failed
        """
        self.logger.debug(f"Adding assistant message to conversation: {conversation_id}")

        # Get conversation
        conversation = db.get(Conversation, conversation_id)
        if not conversation:
            self.logger.warning(f"Conversation {conversation_id} not found")
            return None

        # Determine parent ID
        actual_parent_id = parent_id if parent_id is not None else conversation.current_node_id

        # Create message
        msg_id = str(uuid.uuid4())
        message = Message(
            id=msg_id,
            role="assistant",
            content=content,
            conversation_id=conversation_id,
            parent_id=actual_parent_id,
            model_info=model_info or {},
            token_usage=token_usage or {},
            reasoning_steps=reasoning_steps or [],
            response_id=response_id
        )
        db.add(message)
        db.flush()

        # Update conversation's current node and modified time
        conversation.current_node_id = message.id
        conversation.modified_at = datetime.utcnow()
        db.add(conversation)

        # Update cache
        self._message_cache[message.id] = message
        self._conversation_cache[conversation_id] = conversation

        self.logger.info(f"Added assistant message {message.id} to conversation {conversation_id}")
        return message

    def get_message(self, db: Session, id: str, use_cache: bool = True) -> Optional[Message]:
        """
        Get a message by ID.

        Args:
            db: SQLAlchemy session
            id: Message ID
            use_cache: Whether to check the cache first

        Returns:
            Message object or None if not found
        """
        self.logger.debug(f"Getting message: {id}")

        # Check cache first if enabled
        if use_cache and id in self._message_cache:
            self.logger.debug(f"Using cached message: {id}")
            return self._message_cache[id]

        # Query database
        query = select(Message).where(Message.id == id).options(
            selectinload(Message.file_attachments)
        )
        message = db.execute(query).scalars().first()

        if message:
            # Update cache
            self._message_cache[id] = message
        else:
            self.logger.warning(f"Message {id} not found")

        return message

    def get_message_branch(self, db: Session, message_id: str) -> List[Message]:
        """
        Get the branch of messages from root to the specified message.

        Args:
            db: SQLAlchemy session
            message_id: Message ID

        Returns:
            List of messages in order from root to specified message
        """
        self.logger.debug(f"Getting message branch for message: {message_id}")

        branch = []
        current_id = message_id
        processed_ids = set()  # Prevent infinite loops in case of data corruption

        while current_id and current_id not in processed_ids:
            processed_ids.add(current_id)

            # Check cache first
            cached_message = self._message_cache.get(current_id)
            if cached_message is not None:
                branch.insert(0, cached_message)
                current_id = cached_message.parent_id
                continue

            # Query database
            message = db.get(Message, current_id, options=[selectinload(Message.file_attachments)])

            if not message:
                self.logger.warning(f"Message {current_id} not found during branch traversal")
                break  # Stop if a message in the chain is missing

            # Update cache
            self._message_cache[current_id] = message

            # Add to branch and move to parent
            branch.insert(0, message)
            current_id = message.parent_id

        if current_id in processed_ids:
            self.logger.error(f"Circular reference detected in message chain near ID {current_id}")

        self.logger.debug(f"Found {len(branch)} messages in branch")
        return branch

    def navigate_to_message(self, db: Session, conversation_id: str, message_id: str) -> bool:
        """
        Set the current node of a conversation.

        Args:
            db: SQLAlchemy session
            conversation_id: Conversation ID
            message_id: Message ID to navigate to

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Navigating conversation {conversation_id} to message {message_id}")

        # Verify message exists and belongs to the conversation
        message = db.get(Message, message_id)
        if not message or message.conversation_id != conversation_id:
            self.logger.warning(f"Message {message_id} not found or not in conversation {conversation_id}")
            return False

        # Update conversation
        conversation = db.get(Conversation, conversation_id)
        if not conversation:
            self.logger.warning(f"Conversation {conversation_id} not found")
            return False

        conversation.current_node_id = message_id
        conversation.modified_at = datetime.utcnow()

        # Update cache
        self._conversation_cache[conversation_id] = conversation

        self.logger.info(f"Navigated conversation {conversation_id} to message {message_id}")
        return True

    # --- File Attachment Operations ---

    def add_file_attachment(self, db: Session, message_id: str, file_info: Dict) -> Optional[FileAttachment]:
        """
        Add a file attachment to a message.

        Args:
            db: SQLAlchemy session
            message_id: Message ID
            file_info: Dictionary with file information

        Returns:
            The created FileAttachment object or None if failed
        """
        self.logger.debug(f"Adding file attachment to message: {message_id}")

        # Verify message exists
        message_exists = db.query(Message.id).filter_by(id=message_id).first()
        if not message_exists:
            self.logger.warning(f"Message {message_id} not found for attachment")
            return None

        # Create attachment
        attachment_id = str(uuid.uuid4())
        attachment = FileAttachment(
            id=attachment_id,
            message_id=message_id,
            file_name=file_info.get('fileName', file_info.get('file_name', 'unknown')),
            display_name=file_info.get('display_name'),
            mime_type=file_info.get('mime_type', 'text/plain'),
            token_count=file_info.get('tokenCount', file_info.get('token_count', 0)),
            file_size=file_info.get('fileSize', file_info.get('size', 0)),
            file_hash=file_info.get('file_hash'),
            content_preview=file_info.get('content_preview'),
            content=file_info.get('content', '')
        )
        db.add(attachment)

        self.logger.info(f"Added file attachment {attachment.id} to message {message_id}")
        return attachment

    # --- Search Operations ---

    def search_conversations(self, db: Session, search_term: str,
                             conversation_id: Optional[str] = None,
                             skip: int = 0, limit: int = 50) -> List[Dict]:
        """
        Search for messages containing the search term.

        Args:
            db: SQLAlchemy session
            search_term: Text to search for
            conversation_id: Optional conversation ID to limit search
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of message dictionaries with conversation info
        """
        self.logger.debug(f"Searching for '{search_term}' in conversations")

        search_pattern = f"%{search_term}%"
        query = select(Message, Conversation.name).join(Conversation)

        # Use case-insensitive search
        query = query.where(func.lower(Message.content).like(func.lower(search_pattern)))

        if conversation_id:
            query = query.where(Message.conversation_id == conversation_id)

        query = query.order_by(Message.conversation_id, Message.timestamp.desc())
        query = query.offset(skip).limit(limit)

        rows = db.execute(query).all()

        results = [{
            'id': m.id,
            'conversation_id': m.conversation_id,
            'conversation_name': name,
            'role': m.role,
            'content': m.content,
            'timestamp': m.timestamp.isoformat() if m.timestamp else None
        } for m, name in rows]

        self.logger.debug(f"Found {len(results)} matching messages")
        return results

    # --- Clean up ---

    def clear_cache(self):
        """Clear the internal caches."""
        self._conversation_cache.clear()
        self._message_cache.clear()
        self.logger.debug("Internal caches cleared")