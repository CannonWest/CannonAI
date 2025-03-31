# src/services/database/conversation_service.py
"""
Synchronous service class for managing conversations and messages using SQLAlchemy.
"""
# Standard library imports
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

# Third-party library imports
# Use standard synchronous SQLAlchemy components
from sqlalchemy import delete, or_, update, select, func, text
from sqlalchemy.orm import joinedload, selectinload, Session, attributes # Added Session, attributes
from sqlalchemy.exc import SQLAlchemyError, OperationalError

# Local application imports
from src.services.database.db_manager import DatabaseManager # Renamed import
from src.models import Base, Conversation, FileAttachment, Message
from src.utils.logging_utils import get_logger

# Get a logger for this module
logger = get_logger(__name__)


class ConversationService: # Renamed class
    """
    Synchronous service class for managing conversations and messages.
    """
    # Keep caches if useful, but be mindful of potential staleness without async updates
    _conversation_cache = {}
    _message_cache = {}

    def __init__(self, connection_string=None):
        """
        Initialize the synchronous conversation service.

        Args:
            connection_string: Optional SQLAlchemy connection string for the database.
        """
        # Use the synchronous DatabaseManager
        self.db_manager = DatabaseManager(connection_string)
        self.logger = get_logger(f"{__name__}.ConversationService")
        self._initialized = False
        self.logger.info("ConversationService (Sync) created")
        # Attempt initialization immediately
        self.initialize_sync()

    def initialize_sync(self) -> bool:
        """
        Initialize database tables synchronously.

        Returns:
            True if successful, False otherwise.
        """
        if self._initialized:
            return True
        self.logger.info("Initializing ConversationService synchronously...")
        # Pass the Base from models to the db_manager for table creation
        success = self.db_manager.create_tables(Base)
        if success:
            self._initialized = True
            self.logger.info("ConversationService initialized successfully.")
        else:
            self.logger.error("ConversationService initialization failed.")
        return success

    def ensure_initialized(self) -> bool:
        """Ensure the service is initialized."""
        if not self._initialized:
            return self.initialize_sync()
        return True

    # --- Synchronous CRUD Operations ---

    def create_conversation(self, name="New Conversation", system_message="You are a helpful assistant.") -> Optional[Conversation]:
        """
        Create a new conversation with an initial system message (synchronous).

        Args:
            name: Name of the conversation.
            system_message: System message content.

        Returns:
            The created Conversation object or None if failed.
        """
        self.logger.debug(f"Creating conversation (sync): {name}")
        if not self.ensure_initialized():
            self.logger.error("DB not initialized, cannot create conversation.")
            return None

        try:
            with self.db_manager.get_session() as session: # Use sync session context manager
                # Create conversation
                conv_id = str(uuid.uuid4())
                c = Conversation(id=conv_id, name=name, system_message=system_message)
                session.add(c)
                session.flush() # Flush to get conversation ID if needed by message

                # Create system message
                msg_id = str(uuid.uuid4())
                m = Message(id=msg_id, conversation_id=c.id, role="system", content=system_message)
                session.add(m)
                session.flush() # Flush to get message ID

                # Set current node (must be done after message has ID)
                c.current_node_id = m.id
                session.add(c) # Add again to mark as dirty for update

                # Commit happens automatically at end of 'with' block
                # Eager load messages relationship for return? Optional.
                # session.refresh(c, attribute_names=['messages']) # Refresh to load relationships if needed

                # Detach from session before returning
                session.expunge(c)
                session.expunge(m)

                self.logger.info(f"Created conversation {c.id} with name '{name}' (sync)")
                # Update cache if desired
                self._conversation_cache[c.id] = c
                return c
        except Exception as e:
            self.logger.error(f"Error creating conversation (sync): {str(e)}", exc_info=True)
            return None # Return None on error

    def get_conversation(self, id: str, use_cache=True) -> Optional[Conversation]:
        """Get a conversation by ID (synchronous)."""
        self.logger.debug(f"Getting conversation (sync): {id}")
        if use_cache and id in self._conversation_cache:
            # Return a detached copy from cache? Or assume read-only use?
            # For simplicity, return cached directly, but be aware of potential detached state issues if modified.
            self.logger.debug(f"Using cached conversation (sync): {id}")
            return self._conversation_cache[id]

        if not self.ensure_initialized(): return None

        try:
            with self.db_manager.get_session() as session:
                query = select(Conversation).where(Conversation.id == id).options(
                    selectinload(Conversation.messages) # Eager load messages
                )
                conversation = session.execute(query).scalars().first()

                if conversation:
                    session.expunge(conversation) # Detach before caching/returning
                    self._conversation_cache[id] = conversation # Update cache
                else:
                    self.logger.warning(f"Conversation {id} not found (sync)")
                return conversation
        except Exception as e:
             self.logger.error(f"Error getting conversation {id} (sync): {str(e)}", exc_info=True)
             return None

    def update_conversation(self, id: str, **kwargs) -> bool:
        """Update a conversation (synchronous)."""
        self.logger.debug(f"Updating conversation {id} with {kwargs} (sync)")
        if not self.ensure_initialized(): return False

        try:
            with self.db_manager.get_session() as session:
                c = session.get(Conversation, id) # Use session.get for primary key lookup
                if not c:
                    self.logger.warning(f"Conversation {id} not found for update (sync)")
                    return False

                # Update fields
                for k, v in kwargs.items():
                    if hasattr(c, k):
                        setattr(c, k, v)
                c.modified_at = datetime.utcnow() # Update timestamp

                # Commit happens automatically
                # Update cache after commit
                session.flush() # Ensure changes are flushed before expunge
                session.expunge(c) # Detach updated object
                self._conversation_cache[id] = c # Update cache
                self.logger.info(f"Updated conversation {id} (sync)")
                return True
        except Exception as e:
            self.logger.error(f"Error updating conversation {id} (sync): {str(e)}", exc_info=True)
            return False

    def delete_conversation(self, id: str) -> bool:
        """Delete a conversation (synchronous)."""
        self.logger.debug(f"Deleting conversation (sync): {id}")
        if not self.ensure_initialized(): return False

        try:
            with self.db_manager.get_session() as session:
                c = session.get(Conversation, id)
                if not c:
                    self.logger.warning(f"Conversation {id} not found for deletion (sync)")
                    return False

                # Clear current_node_id reference first (still good practice)
                c.current_node_id = None
                session.flush()

                # Delete associated messages (handled by cascade="all, delete-orphan" on relationship)
                # So just deleting the conversation should be enough if cascade is set correctly.
                # If cascade isn't reliable, delete messages explicitly:
                # session.execute(delete(Message).where(Message.conversation_id == id))

                session.delete(c)
                # Commit happens automatically

                # Remove from cache after successful commit
                if id in self._conversation_cache:
                    del self._conversation_cache[id]
                self.logger.info(f"Deleted conversation {id} (sync)")
                return True
        except Exception as e:
            self.logger.error(f"Error deleting conversation {id} (sync): {str(e)}", exc_info=True)
            return False

    # Note: Duplicating conversations synchronously can be complex due to relationships.
    # This might be a candidate for keeping as a longer operation handled by a worker thread,
    # even if the individual DB steps are sync. For now, let's comment it out.
    # def duplicate_conversation(self, conversation_id: str, new_name: Optional[str] = None) -> Optional[Conversation]:
    #     # ... Implementation would involve multiple sync session queries and object creation ...
    #     self.logger.warning("Synchronous duplicate_conversation not fully implemented yet.")
    #     return None

    def add_user_message(self, conversation_id: str, content: str, parent_id: Optional[str] = None) -> Optional[Message]:
        """Add a user message (synchronous)."""
        self.logger.debug(f"Adding user message to conv {conversation_id} (sync)")
        if not self.ensure_initialized(): return None

        try:
            with self.db_manager.get_session() as session:
                c = session.get(Conversation, conversation_id)
                if not c:
                    self.logger.warning(f"Conversation {conversation_id} not found (sync)")
                    return None

                # Determine parent ID
                actual_parent_id = parent_id if parent_id is not None else c.current_node_id

                # Create message
                msg_id = str(uuid.uuid4())
                m = Message(id=msg_id, role="user", content=content, conversation_id=conversation_id, parent_id=actual_parent_id)
                session.add(m)
                session.flush() # Flush to get message ID

                # Update conversation's current node and modified time
                c.current_node_id = m.id
                c.modified_at = datetime.utcnow()
                session.add(c) # Mark conversation as dirty

                # Commit happens automatically

                # Detach and cache
                session.expunge(m)
                self._message_cache[m.id] = m
                # Update conversation cache if needed (though it's detached)
                session.expunge(c)
                self._conversation_cache[conversation_id] = c

                self.logger.info(f"Added user message {m.id} to conv {conversation_id} (sync)")
                return m
        except Exception as e:
            self.logger.error(f"Error adding user message (sync): {str(e)}", exc_info=True)
            return None

    def add_assistant_message(self, conversation_id: str, content: str, parent_id: Optional[str] = None,
                                   model_info: Optional[Dict] = None, token_usage: Optional[Dict] = None,
                                   reasoning_steps: Optional[List] = None, response_id: Optional[str] = None) -> Optional[Message]:
        """Add an assistant message (synchronous)."""
        self.logger.debug(f"Adding assistant message to conv {conversation_id} (sync)")
        if not self.ensure_initialized(): return None

        try:
            with self.db_manager.get_session() as session:
                c = session.get(Conversation, conversation_id)
                if not c:
                    self.logger.warning(f"Conversation {conversation_id} not found (sync)")
                    return None

                actual_parent_id = parent_id if parent_id is not None else c.current_node_id

                msg_id = str(uuid.uuid4())
                m = Message(
                    id=msg_id, role="assistant", content=content, conversation_id=conversation_id,
                    parent_id=actual_parent_id, response_id=response_id,
                    model_info=model_info or {}, token_usage=token_usage or {},
                    reasoning_steps=reasoning_steps or []
                )
                session.add(m)
                session.flush()

                c.current_node_id = m.id
                c.modified_at = datetime.utcnow()
                session.add(c)

                # Commit happens automatically

                # Detach and cache
                session.expunge(m)
                self._message_cache[m.id] = m
                session.expunge(c)
                self._conversation_cache[conversation_id] = c

                self.logger.info(f"Added assistant message {m.id} to conv {conversation_id} (sync)")
                return m
        except Exception as e:
            self.logger.error(f"Error adding assistant message (sync): {str(e)}", exc_info=True)
            return None

    # File attachments might also need adjustment if they involve complex logic
    def add_file_attachment(self, message_id: str, file_info: Dict) -> Optional[FileAttachment]:
        """Add a file attachment (synchronous)."""
        self.logger.debug(f"Adding file attachment to message {message_id} (sync)")
        if not self.ensure_initialized(): return None

        try:
            with self.db_manager.get_session() as session:
                 # Verify message exists first
                 msg_exists = session.query(Message.id).filter_by(id=message_id).first()
                 if not msg_exists:
                     self.logger.warning(f"Message {message_id} not found for attachment (sync).")
                     return None

                 attachment_id = str(uuid.uuid4())
                 attachment = FileAttachment(
                     id=attachment_id, message_id=message_id,
                     file_name=file_info.get('fileName', file_info.get('file_name', 'unknown')),
                     display_name=file_info.get('display_name'),
                     mime_type=file_info.get('mime_type', 'text/plain'),
                     token_count=file_info.get('tokenCount', file_info.get('token_count', 0)),
                     file_size=file_info.get('fileSize', file_info.get('size', 0)),
                     file_hash=file_info.get('file_hash'),
                     content_preview=file_info.get('content_preview'),
                     content=file_info.get('content', '') # Storing content directly if provided
                 )
                 session.add(attachment)
                 # Commit happens automatically

                 session.expunge(attachment) # Detach before returning
                 self.logger.info(f"Added file attachment {attachment.id} to message {message_id} (sync)")
                 return attachment
        except Exception as e:
             self.logger.error(f"Error adding file attachment (sync): {str(e)}", exc_info=True)
             return None


    def get_message(self, id: str, use_cache=True) -> Optional[Message]:
        """Get a message by ID (synchronous)."""
        self.logger.debug(f"Getting message {id} (sync)")
        if use_cache and id in self._message_cache:
            self.logger.debug(f"Using cached message (sync): {id}")
            return self._message_cache[id]

        if not self.ensure_initialized(): return None

        try:
            with self.db_manager.get_session() as session:
                query = select(Message).where(Message.id == id).options(
                    selectinload(Message.file_attachments) # Eager load attachments
                )
                message = session.execute(query).scalars().first()
                if message:
                    session.expunge(message)
                    self._message_cache[id] = message # Update cache
                return message
        except Exception as e:
            self.logger.error(f"Error getting message {id} (sync): {str(e)}", exc_info=True)
            return None

    def get_message_branch(self, message_id: str) -> List[Message]:
        """Get the branch of messages from root to the specified message (synchronous)."""
        self.logger.debug(f"Getting message branch for {message_id} (sync)")
        if not self.ensure_initialized(): return []

        branch = []
        current_id = message_id
        try:
            # Use a single session for potentially multiple queries
            with self.db_manager.get_session() as session:
                processed_ids = set() # Prevent infinite loops in case of data corruption
                while current_id and current_id not in processed_ids:
                    processed_ids.add(current_id)
                    # Check cache first
                    cached_message = self._message_cache.get(current_id)
                    if cached_message is not None:
                        branch.insert(0, cached_message)
                        current_id = cached_message.parent_id
                        continue

                    # Not in cache, query database
                    # Use session.get for optimized primary key lookup
                    m = session.get(Message, current_id, options=[selectinload(Message.file_attachments)])

                    if not m:
                        self.logger.warning(f"Message {current_id} not found during branch traversal.")
                        break # Stop if a message in the chain is missing

                    session.expunge(m) # Detach before caching/adding to branch
                    self._message_cache[current_id] = m # Add to cache
                    branch.insert(0, m)
                    # Access parent_id from the detached object
                    current_id = m.parent_id # Use the ID from the object before it was expunged

                if current_id in processed_ids:
                     self.logger.error(f"Circular reference detected in message chain near ID {current_id}.")

            self.logger.debug(f"Found {len(branch)} messages in branch (sync)")
            return branch
        except Exception as e:
            self.logger.error(f"Error getting message branch for {message_id} (sync): {str(e)}", exc_info=True)
            return [] # Return empty list on error

    def navigate_to_message(self, conversation_id: str, message_id: str) -> bool:
        """Set the current node of a conversation (synchronous)."""
        self.logger.debug(f"Navigating conv {conversation_id} to message {message_id} (sync)")
        if not self.ensure_initialized(): return False

        try:
            with self.db_manager.get_session() as session:
                 # Verify message exists and belongs to the conversation
                 m = session.get(Message, message_id)
                 if not m or m.conversation_id != conversation_id:
                     self.logger.warning(f"Message {message_id} not found or not in conv {conversation_id} (sync)")
                     return False

                 c = session.get(Conversation, conversation_id)
                 if not c:
                     self.logger.warning(f"Conversation {conversation_id} not found (sync)")
                     return False

                 c.current_node_id = message_id
                 c.modified_at = datetime.utcnow()
                 # Commit happens automatically

                 # Update cache
                 session.flush()
                 session.expunge(c)
                 self._conversation_cache[conversation_id] = c

                 self.logger.info(f"Navigated conv {conversation_id} to message {message_id} (sync)")
                 return True
        except Exception as e:
             self.logger.error(f"Error navigating to message (sync): {str(e)}", exc_info=True)
             return False

    def search_conversations(self, search_term: str, conversation_id: Optional[str] = None) -> List[Dict]:
        """Search for messages (synchronous)."""
        self.logger.debug(f"Searching for '{search_term}' in conversations (sync)")
        if not self.ensure_initialized(): return []

        try:
            with self.db_manager.get_session() as session:
                search_pattern = f"%{search_term}%"
                query = select(Message, Conversation.name).join(Conversation)
                # Use case-insensitive LIKE if possible (depends on DB collation)
                # For standard SQLite, LIKE is case-sensitive by default unless PRAGMA case_sensitive_like=OFF;
                # Using lower() is more portable for case-insensitivity
                query = query.where(func.lower(Message.content).like(func.lower(search_pattern)))

                if conversation_id:
                    query = query.where(Message.conversation_id == conversation_id)

                query = query.order_by(Message.conversation_id, Message.timestamp.desc())

                rows = session.execute(query).all()

                results = [
                    {
                        'id': m.id, 'conversation_id': m.conversation_id,
                        'conversation_name': name, 'role': m.role,
                        'content': m.content, 'timestamp': m.timestamp.isoformat()
                    }
                    for m, name in rows
                ]
                self.logger.debug(f"Found {len(results)} matching messages (sync)")
                return results
        except Exception as e:
            self.logger.error(f"Error searching conversations (sync): {str(e)}", exc_info=True)
            return []

    def get_all_conversations(self) -> List[Conversation]:
        """Get all conversations (synchronous). Uses the helper."""
        # This now directly calls the synchronous helper method
        if not self.ensure_initialized(): return []
        return self._get_all_conversations_sync() # Call the sync helper

    def _get_all_conversations_sync(self) -> List[Conversation]:
        """Synchronous helper to fetch all conversations."""
        self.logger.debug(">>> Entering _get_all_conversations_sync")
        if not self.SyncSessionLocal:
             self.logger.error("_get_all_conversations_sync: SyncSessionLocal not configured.")
             return []

        with self.db_manager.get_session() as session: # Use sync session
            try:
                self.logger.debug("_get_all_conversations_sync: Querying database...")
                query = select(Conversation).order_by(Conversation.modified_at.desc())
                conversations = session.execute(query).scalars().all()
                self.logger.info(f"_get_all_conversations_sync: Found {len(conversations)} conversations.")
                # Detach objects from the session
                for conv in conversations:
                    session.expunge(conv)
                # Update cache (optional, with detached objects)
                # self._conversation_cache.clear() # Clear cache before updating
                # for conv in conversations:
                #     self._conversation_cache[conv.id] = conv
                return conversations
            except Exception as e:
                self.logger.error(f"_get_all_conversations_sync: Error during query: {e}", exc_info=True)
                return []
            finally:
                self.logger.debug("<<< Exiting _get_all_conversations_sync")


    def close(self):
        """Close the database connection manager."""
        self.logger.debug("Closing ConversationService (Sync)")
        self.db_manager.close() # Close the synchronous manager
        self.logger.info("ConversationService (Sync) closed")
