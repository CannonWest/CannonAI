# src/services/db_service.py

from src.models.orm_models import Conversation, Message, FileAttachment
from src.services.db_manager import DatabaseManager
from src.utils.logging_utils import get_logger
from datetime import datetime
import uuid

# Get a logger for this module
logger = get_logger(__name__)


class ConversationService:
    """
    Service class for managing conversations and messages.
    Provides methods for CRUD operations on conversations and messages.
    """

    def __init__(self, db_path='sqlite:///data/database/conversations.db'):
        """
        Initialize the conversation service with a database manager

        Args:
            db_path: SQLAlchemy connection string for the database
        """
        self.db_manager = DatabaseManager(db_path)
        self.logger = get_logger(f"{__name__}.ConversationService")

    def get_session(self):
        """Get a new database session from the manager"""
        return self.db_manager.get_session()

    def create_conversation(self, name="New Conversation", system_message="You are a helpful assistant."):
        """
        Create a new conversation with an initial system message

        Args:
            name: Name of the conversation
            system_message: System message content

        Returns:
            The created Conversation object or None if failed
        """
        self.logger.debug(f"Creating conversation: {name}")
        s = self.get_session()
        try:
            c = Conversation(id=str(uuid.uuid4()), name=name, system_message=system_message)
            s.add(c)
            m = Message(id=str(uuid.uuid4()), conversation_id=c.id, role="system", content=system_message)
            s.add(m)
            c.current_node_id = m.id
            s.commit()
            self.logger.info(f"Created conversation {c.id} with name '{name}'")
            return c
        except Exception as e:
            s.rollback()
            self.logger.error(f"Error creating conversation: {str(e)}")
            raise
        finally:
            s.close()

    def get_conversation(self, id):
        """
        Get a conversation by ID

        Args:
            id: Conversation ID

        Returns:
            The Conversation object or None if not found
        """
        self.logger.debug(f"Getting conversation: {id}")
        s = self.get_session()
        try:
            return s.query(Conversation).filter(Conversation.id == id).first()
        finally:
            s.close()

    def get_all_conversations(self):
        """
        Get all conversations ordered by last modified date

        Returns:
            List of Conversation objects
        """
        self.logger.debug("Getting all conversations")
        s = self.get_session()
        try:
            conversations = s.query(Conversation).order_by(Conversation.modified_at.desc()).all()
            self.logger.debug(f"Found {len(conversations)} conversations")
            return conversations
        finally:
            s.close()

    def update_conversation(self, id, **kwargs):
        """
        Update a conversation with new values

        Args:
            id: Conversation ID
            **kwargs: Fields to update

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Updating conversation {id} with {kwargs}")
        s = self.get_session()
        try:
            c = s.query(Conversation).filter(Conversation.id == id).first()
            if not c:
                self.logger.warning(f"Conversation {id} not found for update")
                return False

            for k, v in kwargs.items():
                if hasattr(c, k):
                    setattr(c, k, v)

            c.modified_at = datetime.utcnow()
            s.commit()
            self.logger.info(f"Updated conversation {id}")
            return True
        except Exception as e:
            s.rollback()
            self.logger.error(f"Error updating conversation {id}: {str(e)}")
            return False
        finally:
            s.close()

    def delete_conversation(self, id):
        """
        Delete a conversation

        Args:
            id: Conversation ID

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Deleting conversation: {id}")
        s = self.get_session()
        try:
            c = s.query(Conversation).filter(Conversation.id == id).first()
            if not c:
                self.logger.warning(f"Conversation {id} not found for deletion")
                return False

            s.delete(c)
            s.commit()
            self.logger.info(f"Deleted conversation {id}")
            return True
        except Exception as e:
            s.rollback()
            self.logger.error(f"Error deleting conversation {id}: {str(e)}")
            return False
        finally:
            s.close()

    def duplicate_conversation(self, conversation_id, new_name=None):
        """
        Duplicate a conversation, including all messages and file attachments

        Args:
            conversation_id: ID of the conversation to duplicate
            new_name: Name for the new conversation, defaults to "<original_name> (Copy)"

        Returns:
            The new conversation, or None if the source conversation is not found
        """
        self.logger.debug(f"Duplicating conversation: {conversation_id}")
        s = self.get_session()
        try:
            # Get the source conversation
            source_conv = s.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not source_conv:
                self.logger.warning(f"Source conversation {conversation_id} not found")
                return None

            # Set the new name
            if new_name is None:
                new_name = f"{source_conv.name} (Copy)"

            # Create a new conversation with the same system message
            new_conv = Conversation(
                id=str(uuid.uuid4()),
                name=new_name,
                system_message=source_conv.system_message
            )
            s.add(new_conv)
            s.flush()  # Flush to get the new conversation ID

            # Get all messages from the source conversation
            source_messages = s.query(Message).filter(Message.conversation_id == conversation_id).all()

            # Create a mapping of old message IDs to new message IDs
            id_mapping = {}

            # First pass: create all new messages without parent IDs
            for source_msg in source_messages:
                new_msg = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=new_conv.id,
                    role=source_msg.role,
                    content=source_msg.content,
                    timestamp=datetime.now,
                    response_id=source_msg.response_id,
                    model_info=source_msg.model_info,
                    parameters=source_msg.parameters,
                    token_usage=source_msg.token_usage,
                    reasoning_steps=source_msg.reasoning_steps
                )
                s.add(new_msg)

                # Remember the mapping
                id_mapping[source_msg.id] = new_msg.id

                # Set the current node for the system message
                if source_msg.role == "system":
                    new_conv.current_node_id = new_msg.id

            # Flush to get all new message IDs
            s.flush()

            # Second pass: set parent IDs using the mapping
            for source_msg in source_messages:
                if source_msg.parent_id:
                    new_msg_id = id_mapping.get(source_msg.id)
                    new_parent_id = id_mapping.get(source_msg.parent_id)

                    if new_msg_id and new_parent_id:
                        new_msg = s.query(Message).filter(Message.id == new_msg_id).first()
                        if new_msg:
                            new_msg.parent_id = new_parent_id

            # Third pass: copy file attachments for each message
            for source_msg in source_messages:
                # Get file attachments for this message
                attachments = s.query(FileAttachment).filter(FileAttachment.message_id == source_msg.id).all()

                if attachments:
                    new_msg_id = id_mapping.get(source_msg.id)

                    for attachment in attachments:
                        # Create a new file attachment
                        new_attachment = FileAttachment(
                            id=str(uuid.uuid4()),
                            message_id=new_msg_id,
                            file_name=attachment.file_name,
                            display_name=attachment.display_name,
                            mime_type=attachment.mime_type,
                            token_count=attachment.token_count,
                            file_size=attachment.file_size,
                            file_hash=attachment.file_hash,
                            storage_type=attachment.storage_type,
                            content_preview=attachment.content_preview,
                            storage_path=attachment.storage_path,
                            content=attachment.content
                        )
                        s.add(new_attachment)

            # If the source conversation has a current node, set the equivalent in the new conversation
            if source_conv.current_node_id and source_conv.current_node_id in id_mapping:
                new_conv.current_node_id = id_mapping[source_conv.current_node_id]

            # Commit the changes
            s.commit()
            self.logger.info(f"Successfully duplicated conversation {conversation_id} to {new_conv.id}")

            # Return the new conversation
            return new_conv
        except Exception as e:
            s.rollback()
            self.logger.error(f"Error duplicating conversation: {str(e)}")
            return None
        finally:
            s.close()

    def add_user_message(self, conversation_id, content, parent_id=None):
        """
        Add a user message to a conversation

        Args:
            conversation_id: Conversation ID
            content: Message content
            parent_id: Parent message ID

        Returns:
            The created Message object or None if failed
        """
        self.logger.debug(f"Adding user message to conversation {conversation_id}")
        s = self.get_session()
        try:
            c = s.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not c:
                self.logger.warning(f"Conversation {conversation_id} not found")
                return None

            if parent_id is None:
                parent_id = c.current_node_id

            m = Message(id=str(uuid.uuid4()), role="user", content=content, conversation_id=conversation_id, parent_id=parent_id)
            s.add(m)
            c.current_node_id = m.id
            c.modified_at = datetime.utcnow()
            s.commit()
            self.logger.info(f"Added user message {m.id} to conversation {conversation_id}")
            return m
        except Exception as e:
            s.rollback()
            self.logger.error(f"Error adding user message: {str(e)}")
            return None
        finally:
            s.close()

    def add_assistant_message(self, conversation_id, content, parent_id=None, model_info=None, token_usage=None,
                              reasoning_steps=None, response_id=None):
        """
        Add an assistant message to a conversation

        Args:
            conversation_id: Conversation ID
            content: Message content
            parent_id: Parent message ID
            model_info: Model information dict
            token_usage: Token usage dict
            reasoning_steps: Reasoning steps list
            response_id: Response ID from API

        Returns:
            The created Message object or None if failed
        """
        self.logger.debug(f"Adding assistant message to conversation {conversation_id}")
        s = self.get_session()
        try:
            c = s.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not c:
                self.logger.warning(f"Conversation {conversation_id} not found")
                return None

            if parent_id is None:
                parent_id = c.current_node_id

            m = Message(
                id=str(uuid.uuid4()),
                role="assistant",
                content=content,
                conversation_id=conversation_id,
                parent_id=parent_id,
                response_id=response_id,
                model_info=model_info or {},
                token_usage=token_usage or {},
                reasoning_steps=reasoning_steps or []
            )
            s.add(m)
            c.current_node_id = m.id
            c.modified_at = datetime.utcnow()
            s.commit()
            self.logger.info(f"Added assistant message {m.id} to conversation {conversation_id}")
            return m
        except Exception as e:
            s.rollback()
            self.logger.error(f"Error adding assistant message: {str(e)}")
            return None
        finally:
            s.close()

    def add_file_attachment(self, message_id, file_info):
        """
        Add a file attachment to a message

        Args:
            message_id: Message ID
            file_info: Dictionary with file information

        Returns:
            The created FileAttachment object or None if failed
        """
        self.logger.debug(f"Adding file attachment to message {message_id}")
        s = self.get_session()
        try:
            # Create new file attachment
            attachment = FileAttachment(
                message_id=message_id,
                file_name=file_info.get('fileName', file_info.get('file_name', 'unknown')),
                display_name=file_info.get('display_name'),
                mime_type=file_info.get('mime_type', 'text/plain'),
                token_count=file_info.get('token_count', 0),
                file_size=file_info.get('size', 0),
                file_hash=file_info.get('file_hash'),
                content_preview=file_info.get('content_preview'),
                content=file_info.get('content', '')
            )
            s.add(attachment)
            s.commit()
            self.logger.info(f"Added file attachment {attachment.id} to message {message_id}")
            return attachment
        except Exception as e:
            s.rollback()
            self.logger.error(f"Error adding file attachment: {str(e)}")
            return None
        finally:
            s.close()

    def get_message(self, id):
        """
        Get a message by ID

        Args:
            id: Message ID

        Returns:
            The Message object or None if not found
        """
        self.logger.debug(f"Getting message {id}")
        s = self.get_session()
        try:
            return s.query(Message).filter(Message.id == id).first()
        finally:
            s.close()

    def get_message_branch(self, message_id):
        """
        Get the branch of messages from root to the specified message

        Args:
            message_id: ID of the leaf message

        Returns:
            List of messages from root to leaf
        """
        self.logger.debug(f"Getting message branch for {message_id}")
        s = self.get_session()
        try:
            branch = []
            current_id = message_id
            while current_id:
                m = s.query(Message).filter(Message.id == current_id).first()
                if not m:
                    break
                branch.insert(0, m)
                current_id = m.parent_id
            self.logger.debug(f"Found {len(branch)} messages in branch")
            return branch
        finally:
            s.close()

    def navigate_to_message(self, conversation_id, message_id):
        """
        Set the current node of a conversation to a specific message

        Args:
            conversation_id: Conversation ID
            message_id: Target message ID

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Navigating conversation {conversation_id} to message {message_id}")
        s = self.get_session()
        try:
            m = s.query(Message).filter(Message.id == message_id, Message.conversation_id == conversation_id).first()
            if not m:
                self.logger.warning(f"Message {message_id} not found in conversation {conversation_id}")
                return False

            c = s.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not c:
                self.logger.warning(f"Conversation {conversation_id} not found")
                return False

            c.current_node_id = message_id
            c.modified_at = datetime.utcnow()
            s.commit()
            self.logger.info(f"Navigated conversation {conversation_id} to message {message_id}")
            return True
        except Exception as e:
            s.rollback()
            self.logger.error(f"Error navigating to message: {str(e)}")
            return False
        finally:
            s.close()

    def search_conversations(self, search_term, conversation_id=None):
        """
        Search for messages containing the search term

        Args:
            search_term: Text to search for
            conversation_id: Optional conversation ID to limit search

        Returns:
            List of matching message dictionaries
        """
        self.logger.debug(f"Searching for '{search_term}' in conversations")
        s = self.get_session()
        try:
            q = s.query(Message, Conversation.name).join(Conversation).filter(Message.content.like(f'%{search_term}%'))
            if conversation_id:
                q = q.filter(Message.conversation_id == conversation_id)

            results = [
                {
                    'id': m.id,
                    'conversation_id': m.conversation_id,
                    'conversation_name': name,
                    'role': m.role,
                    'content': m.content,
                    'timestamp': m.timestamp.isoformat()
                }
                for m, name in q.all()
            ]
            self.logger.debug(f"Found {len(results)} matching messages")
            return results
        finally:
            s.close()