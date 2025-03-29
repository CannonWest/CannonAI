"""
Enhanced async conversation service with improved error handling and recovery mechanisms.
Handles Windows-specific edge cases and prevents context switching issues.
"""
# Standard library imports
import asyncio
import platform
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union, AsyncGenerator

# Third-party library imports
from sqlalchemy import delete, or_, update, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError, OperationalError

# Local application imports
from src.services.database.async_manager import AsyncDatabaseManager
from src.services.database.models import Conversation, FileAttachment, Message
from src.utils.logging_utils import get_logger
from src.utils.qasync_bridge import ensure_qasync_loop

# Get a logger for this module
logger = get_logger(__name__)


class AsyncConversationService:
    """
    Fully asynchronous service class for managing conversations and messages.
    Enhanced with better error handling and recovery strategies.
    """

    # Cache for conversations to reduce database load
    _conversation_cache = {}
    _message_cache = {}

    def __init__(self, connection_string=None):
        """
        Initialize the async conversation service

        Args:
            connection_string: Optional SQLAlchemy connection string for the database
        """
        self.db_manager = AsyncDatabaseManager(connection_string)
        self.logger = get_logger(f"{__name__}.AsyncConversationService")
        self._initialized = False
        self._initialization_in_progress = False
        self.logger.info("AsyncConversationService created")

    async def initialize(self) -> bool:
        """
        Initialize database tables with improved error handling

        Returns:
            True if successful, False if an error occurred
        """
        if self._initialized:
            return True

        if self._initialization_in_progress:
            # Wait for existing initialization to complete
            for _ in range(20):  # Try 20 times with 100ms intervals (2 sec total)
                await asyncio.sleep(0.1)
                if self._initialized:
                    return True
            # If still not initialized after waiting
            self.logger.warning("Initialization timed out while waiting for concurrent init")

        self._initialization_in_progress = True

        try:
            # Log the current event loop
            try:
                loop = asyncio.get_event_loop()
                self.logger.debug(f"Initializing with event loop: {id(loop)}")
            except RuntimeError:
                # No running loop
                loop = ensure_qasync_loop()
                self.logger.debug(f"Created new loop for initialization: {id(loop)}")

            # Try multiple times for Windows reliability
            for attempt in range(3):
                try:
                    await self.db_manager.create_tables()
                    self._initialized = True
                    self.logger.info("AsyncConversationService initialized")
                    return True
                except Exception as e:
                    if attempt < 2:  # Try 3 times total
                        self.logger.warning(f"Database init attempt {attempt+1} failed: {str(e)}. Retrying...")
                        await asyncio.sleep(0.5)  # Wait briefly before retry
                    else:
                        raise

        except Exception as e:
            self.logger.error(f"Failed to initialize database: {str(e)}")
            # Don't re-raise, allow reduced functionality
            return False
        finally:
            self._initialization_in_progress = False

        return self._initialized

    async def ensure_initialized(self) -> bool:
        """
        Ensure the service is initialized before performing operations

        Returns:
            True if already initialized or initialization was successful,
            False if initialization failed
        """
        if not self._initialized:
            return await self.initialize()
        return True

    async def create_conversation(self, name="New Conversation", system_message="You are a helpful assistant.", attempts=3):
        """
        Create a new conversation with an initial system message
        with improved error handling and retry logic

        Args:
            name: Name of the conversation
            system_message: System message content
            attempts: Number of retry attempts for resilience

        Returns:
            The created Conversation object or None if failed
        """
        self.logger.debug(f"Creating conversation: {name}")

        # Ensure the service is initialized
        if not self._initialized:
            success = await self.initialize()
            if not success:
                self.logger.error("Failed to initialize database for conversation creation")
                return self._create_emergency_conversation(name, system_message)

        # Use retry logic for reliable database operations
        for attempt in range(attempts):
            try:
                async with self._get_session_with_timeout(15.0) as session:
                    # Create conversation
                    conv_id = str(uuid.uuid4())
                    c = Conversation(id=conv_id, name=name, system_message=system_message)
                    session.add(c)

                    # Create system message
                    msg_id = str(uuid.uuid4())
                    m = Message(id=msg_id, conversation_id=c.id, role="system", content=system_message)
                    session.add(m)

                    # Set current node
                    c.current_node_id = m.id

                    # Commit transaction
                    await session.commit()

                    # Refresh to get the complete object with relationships
                    await session.refresh(c)

                    # Add to cache for faster future access
                    self._conversation_cache[c.id] = c

                    self.logger.info(f"Created conversation {c.id} with name '{name}'")
                    return c
            except SQLAlchemyError as e:
                # Handle database errors
                if attempt < attempts - 1:
                    error_type = type(e).__name__
                    self.logger.warning(f"Error creating conversation (attempt {attempt+1}/{attempts}): {error_type} - {str(e)}")
                    await asyncio.sleep(0.5 * (attempt + 1))  # Increasing backoff
                else:
                    # Last attempt failed
                    await session.rollback()
                    self.logger.error(f"All attempts to create conversation failed: {str(e)}")
                    # Try emergency fallback
                    return self._create_emergency_conversation(name, system_message)
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error creating conversation: {str(e)}")
                # Try emergency fallback
                return self._create_emergency_conversation(name, system_message)

    def _create_emergency_conversation(self, name, system_message):
        """
        Create an in-memory conversation when database operations fail

        Args:
            name: Name of the conversation
            system_message: System message content

        Returns:
            A Conversation object not backed by the database
        """
        try:
            self.logger.warning("Creating emergency in-memory conversation")
            # Create objects manually without database
            conv_id = str(uuid.uuid4())
            msg_id = str(uuid.uuid4())

            # Create conversation
            c = Conversation(id=conv_id, name=name, system_message=system_message)

            # Create message
            m = Message(id=msg_id, conversation_id=c.id, role="system", content=system_message)

            # Link them
            c.current_node_id = m.id
            c.messages = [m]

            # Set timestamps
            now = datetime.utcnow()
            c.created_at = now
            c.modified_at = now
            m.timestamp = now

            # Store in cache
            self._conversation_cache[c.id] = c
            self._message_cache[m.id] = m

            self.logger.info(f"Created emergency conversation {c.id}")
            return c
        except Exception as e:
            self.logger.error(f"Failed to create emergency conversation: {str(e)}")
            return None

    async def get_conversation(self, id: str, use_cache=True) -> Optional[Conversation]:
        """
        Get a conversation by ID with improved caching and error recovery

        Args:
            id: Conversation ID
            use_cache: Whether to check the cache first

        Returns:
            The Conversation object or None if not found
        """
        self.logger.debug(f"Getting conversation: {id}")

        # Check cache first if enabled
        if use_cache and id in self._conversation_cache:
            self.logger.debug(f"Using cached conversation: {id}")
            return self._conversation_cache[id]

        # Ensure the service is initialized
        if not self._initialized:
            success = await self.initialize()
            if not success:
                self.logger.error("Database not initialized for conversation retrieval")
                return None

        # Implement retry logic for resilience
        for attempt in range(3):
            try:
                async with self._get_session_with_timeout(10.0) as session:
                    # Query with relationships loaded efficiently
                    query = select(Conversation).where(Conversation.id == id).options(
                        selectinload(Conversation.messages)
                    )
                    result = await session.execute(query)
                    conversation = result.scalars().first()

                    if conversation:
                        # Add to cache
                        self._conversation_cache[id] = conversation
                    else:
                        self.logger.warning(f"Conversation {id} not found")

                    return conversation
            except Exception as e:
                if attempt < 2:  # Try 3 times total
                    self.logger.warning(f"Error getting conversation (attempt {attempt+1}): {str(e)}")
                    await asyncio.sleep(0.3)  # Short delay before retry
                else:
                    self.logger.error(f"Failed to get conversation after retries: {str(e)}")
                    return None

    async def update_conversation(self, id: str, **kwargs) -> bool:
        """
        Update a conversation with new values

        Args:
            id: Conversation ID
            **kwargs: Fields to update

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Updating conversation {id} with {kwargs}")

        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()

        # Try a few times for resilience
        for attempt in range(3):
            try:
                async with self.db_manager.get_session() as session:
                    # Get the conversation
                    query = select(Conversation).where(Conversation.id == id)
                    result = await session.execute(query)
                    c = result.scalars().first()

                    if not c:
                        self.logger.warning(f"Conversation {id} not found for update")
                        return False

                    # Update fields
                    for k, v in kwargs.items():
                        if hasattr(c, k):
                            setattr(c, k, v)

                    # Update modification timestamp
                    c.modified_at = datetime.utcnow()

                    # Commit changes
                    await session.commit()

                    # Update cache if we're using it
                    if id in self._conversation_cache:
                        self._conversation_cache[id] = c

                    self.logger.info(f"Updated conversation {id}")
                    return True
            except Exception as e:
                if attempt < 2:
                    self.logger.warning(f"Error updating conversation (attempt {attempt+1}): {str(e)}")
                    await asyncio.sleep(0.3)
                else:
                    await session.rollback()
                    self.logger.error(f"Error updating conversation {id}: {str(e)}")
                    return False

    async def delete_conversation(self, id: str) -> bool:
        """
        Delete a conversation with improved handling for circular dependencies

        Args:
            id: Conversation ID

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Deleting conversation: {id}")

        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()

        for attempt in range(3):
            async with self.db_manager.get_session() as session:
                try:
                    # First, clear the current_node_id reference to break circular dependency
                    query = select(Conversation).where(Conversation.id == id)
                    result = await session.execute(query)
                    conversation = result.scalars().first()

                    if not conversation:
                        self.logger.warning(f"Conversation {id} not found for deletion")
                        return False

                    # Important: Clear the current_node_id reference first
                    conversation.current_node_id = None
                    await session.flush()

                    # Now delete associated messages first
                    delete_messages = delete(Message).where(Message.conversation_id == id)
                    await session.execute(delete_messages)

                    # Then delete the conversation
                    await session.delete(conversation)

                    # Commit changes
                    await session.commit()

                    # Remove from cache
                    if id in self._conversation_cache:
                        del self._conversation_cache[id]

                    self.logger.info(f"Deleted conversation {id}")
                    return True
                except Exception as e:
                    await session.rollback()
                    if attempt < 2:
                        self.logger.warning(f"Error deleting conversation (attempt {attempt+1}): {str(e)}")
                        await asyncio.sleep(0.5)
                    else:
                        self.logger.error(f"Error deleting conversation {id}: {str(e)}")
                        self.logger.error(f"Exception details: {e.__class__.__name__}")
                        self.logger.error(traceback.format_exc())
                        return False

    async def duplicate_conversation(self, conversation_id: str, new_name: Optional[str] = None) -> Optional[Conversation]:
        """
        Duplicate a conversation, including all messages and file attachments

        Args:
            conversation_id: ID of the conversation to duplicate
            new_name: Name for the new conversation, defaults to "<original_name> (Copy)"

        Returns:
            The new conversation, or None if the source conversation is not found
        """
        self.logger.debug(f"Duplicating conversation: {conversation_id}")

        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()

        # Get the source conversation first
        source_conv = await self.get_conversation(conversation_id)
        if not source_conv:
            self.logger.warning(f"Source conversation {conversation_id} not found")
            return None

        # Create new conversation with same system message
        if new_name is None:
            new_name = f"{source_conv.name} (Copy)"

        # Create the new conversation
        new_conv = await self.create_conversation(name=new_name, system_message=source_conv.system_message)
        if not new_conv:
            self.logger.error("Failed to create new conversation for duplication")
            return None

        try:
            async with self.db_manager.get_session() as session:
                # Get all messages from the source conversation
                query = select(Message).where(Message.conversation_id == conversation_id)
                result = await session.execute(query)
                source_messages = result.scalars().all()

                if not source_messages:
                    self.logger.warning(f"No messages found in source conversation {conversation_id}")
                    return new_conv

                # Create a mapping of old message IDs to new message IDs
                id_mapping = {}

                # First pass: create all new messages without parent IDs
                for source_msg in source_messages:
                    # Skip system messages as we already created one
                    if source_msg.role == "system":
                        # Just map the ID to our new system message ID
                        system_msg_id = new_conv.current_node_id
                        id_mapping[source_msg.id] = system_msg_id
                        continue

                    new_msg = Message(
                        id=str(uuid.uuid4()),
                        conversation_id=new_conv.id,
                        role=source_msg.role,
                        content=source_msg.content,
                        timestamp=datetime.utcnow(),
                        response_id=source_msg.response_id,
                        model_info=source_msg.model_info,
                        parameters=source_msg.parameters,
                        token_usage=source_msg.token_usage,
                        reasoning_steps=source_msg.reasoning_steps
                    )
                    session.add(new_msg)

                    # Remember the mapping
                    id_mapping[source_msg.id] = new_msg.id

                # Flush to get all new message IDs
                await session.flush()

                # Second pass: set parent IDs using the mapping
                for source_msg in source_messages:
                    if source_msg.parent_id:
                        new_msg_id = id_mapping.get(source_msg.id)
                        new_parent_id = id_mapping.get(source_msg.parent_id)

                        if new_msg_id and new_parent_id:
                            query = select(Message).where(Message.id == new_msg_id)
                            result = await session.execute(query)
                            new_msg = result.scalars().first()

                            if new_msg:
                                new_msg.parent_id = new_parent_id

                # Third pass: copy file attachments for each message
                for source_msg in source_messages:
                    # Get file attachments for this message
                    query = select(FileAttachment).where(FileAttachment.message_id == source_msg.id)
                    result = await session.execute(query)
                    attachments = result.scalars().all()

                    if attachments:
                        new_msg_id = id_mapping.get(source_msg.id)

                        for attachment in attachments:
                            # Create a new file attachment
                            new_attachment = FileAttachment(
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
                            session.add(new_attachment)

                # Determine the latest message ID to use as current node
                latest_msg_id = None
                latest_timestamp = None
                for source_msg in source_messages:
                    if latest_timestamp is None or source_msg.timestamp > latest_timestamp:
                        latest_timestamp = source_msg.timestamp
                        latest_msg_id = source_msg.id

                # If we found the latest, set it as current node
                if latest_msg_id and latest_msg_id in id_mapping:
                    new_conv.current_node_id = id_mapping[latest_msg_id]

                # Commit the changes
                await session.commit()

                # Refresh the new conversation
                await session.refresh(new_conv)

                # Update the cache
                self._conversation_cache[new_conv.id] = new_conv

                self.logger.info(f"Successfully duplicated conversation {conversation_id} to {new_conv.id}")

                # Return the new conversation
                return new_conv
        except Exception as e:
            await session.rollback()
            self.logger.error(f"Error duplicating conversation: {str(e)}")
            return None

    async def add_user_message(self, conversation_id: str, content: str, parent_id: Optional[str] = None) -> Optional[Message]:
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

        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()

        for attempt in range(3):
            try:
                async with self.db_manager.get_session() as session:
                    # Get the conversation
                    query = select(Conversation).where(Conversation.id == conversation_id)
                    result = await session.execute(query)
                    c = result.scalars().first()

                    if not c:
                        self.logger.warning(f"Conversation {conversation_id} not found")
                        return None

                    if parent_id is None:
                        parent_id = c.current_node_id

                    # Create the message
                    msg_id = str(uuid.uuid4())
                    m = Message(id=msg_id, role="user", content=content, conversation_id=conversation_id, parent_id=parent_id)
                    session.add(m)

                    # Update conversation
                    c.current_node_id = m.id
                    c.modified_at = datetime.utcnow()

                    # Commit transaction
                    await session.commit()

                    # Refresh the message
                    await session.refresh(m)

                    # Add to cache
                    self._message_cache[m.id] = m

                    # Update conversation in cache
                    if conversation_id in self._conversation_cache:
                        self._conversation_cache[conversation_id] = c

                    self.logger.info(f"Added user message {m.id} to conversation {conversation_id}")
                    return m
            except Exception as e:
                if attempt < 2:
                    self.logger.warning(f"Error adding user message (attempt {attempt+1}): {str(e)}")
                    await asyncio.sleep(0.3)
                else:
                    await session.rollback()
                    self.logger.error(f"Error adding user message: {str(e)}")
                    return None

    async def add_assistant_message(self, conversation_id: str, content: str, parent_id: Optional[str] = None,
                                   model_info: Optional[Dict] = None, token_usage: Optional[Dict] = None,
                                   reasoning_steps: Optional[List] = None, response_id: Optional[str] = None) -> Optional[Message]:
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

        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()

        for attempt in range(3):
            try:
                async with self.db_manager.get_session() as session:
                    # Get the conversation
                    query = select(Conversation).where(Conversation.id == conversation_id)
                    result = await session.execute(query)
                    c = result.scalars().first()

                    if not c:
                        self.logger.warning(f"Conversation {conversation_id} not found")
                        return None

                    if parent_id is None:
                        parent_id = c.current_node_id

                    # Create the message
                    msg_id = str(uuid.uuid4())
                    m = Message(
                        id=msg_id,
                        role="assistant",
                        content=content,
                        conversation_id=conversation_id,
                        parent_id=parent_id,
                        response_id=response_id,
                        model_info=model_info or {},
                        token_usage=token_usage or {},
                        reasoning_steps=reasoning_steps or []
                    )
                    session.add(m)

                    # Update conversation
                    c.current_node_id = m.id
                    c.modified_at = datetime.utcnow()

                    # Commit transaction
                    await session.commit()

                    # Refresh the message
                    await session.refresh(m)

                    # Add to cache
                    self._message_cache[m.id] = m

                    # Update conversation in cache
                    if conversation_id in self._conversation_cache:
                        self._conversation_cache[conversation_id] = c

                    self.logger.info(f"Added assistant message {m.id} to conversation {conversation_id}")
                    return m
            except Exception as e:
                if attempt < 2:
                    self.logger.warning(f"Error adding assistant message (attempt {attempt+1}): {str(e)}")
                    await asyncio.sleep(0.3)
                else:
                    await session.rollback()
                    self.logger.error(f"Error adding assistant message: {str(e)}")
                    return None

    async def add_file_attachment(self, message_id: str, file_info: Dict) -> Optional[FileAttachment]:
        """
        Add a file attachment to a message

        Args:
            message_id: Message ID
            file_info: Dictionary with file information

        Returns:
            The created FileAttachment object or None if failed
        """
        self.logger.debug(f"Adding file attachment to message {message_id}")

        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()

        try:
            async with self.db_manager.get_session() as session:
                # Create new file attachment
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
                session.add(attachment)

                # Commit transaction
                await session.commit()

                # Refresh the attachment
                await session.refresh(attachment)

                self.logger.info(f"Added file attachment {attachment.id} to message {message_id}")
                return attachment
        except Exception as e:
            await session.rollback()
            self.logger.error(f"Error adding file attachment: {str(e)}")
            return None

    async def get_message(self, id: str, use_cache=True) -> Optional[Message]:
        """
        Get a message by ID with caching support

        Args:
            id: Message ID
            use_cache: Whether to check the cache first

        Returns:
            The Message object or None if not found
        """
        self.logger.debug(f"Getting message {id}")

        # Check cache first if enabled
        if use_cache and id in self._message_cache:
            self.logger.debug(f"Using cached message: {id}")
            return self._message_cache[id]

        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()

        try:
            async with self.db_manager.get_session() as session:
                query = select(Message).where(Message.id == id).options(
                    selectinload(Message.file_attachments)
                )
                result = await session.execute(query)
                message = result.scalars().first()

                if message:
                    # Add to cache
                    self._message_cache[id] = message

                return message
        except Exception as e:
            self.logger.error(f"Error getting message {id}: {str(e)}")
            return None

    async def get_message_branch(self, message_id: str) -> List[Message]:
        """
        Get the branch of messages from root to the specified message
        with improved caching and error handling.

        Args:
            message_id: ID of the leaf message

        Returns:
            List of messages from root to leaf
        """
        self.logger.debug(f"Getting message branch for {message_id}")

        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()

        try:
            async with self.db_manager.get_session() as session:
                branch = []
                current_id = message_id

                while current_id:
                    # Check cache first
                    cached_message = self._message_cache.get(current_id)
                    if cached_message is not None:
                        branch.insert(0, cached_message)
                        current_id = cached_message.parent_id
                        continue

                    # Not in cache, query database
                    query = select(Message).where(Message.id == current_id).options(
                        selectinload(Message.file_attachments)
                    )
                    result = await session.execute(query)
                    m = result.scalars().first()

                    if not m:
                        break

                    # Add to cache for future use
                    self._message_cache[current_id] = m

                    branch.insert(0, m)
                    current_id = m.parent_id

                self.logger.debug(f"Found {len(branch)} messages in branch")
                return branch
        except Exception as e:
            self.logger.error(f"Error getting message branch: {str(e)}")
            return []

    async def navigate_to_message(self, conversation_id: str, message_id: str) -> bool:
        """
        Set the current node of a conversation to a specific message

        Args:
            conversation_id: Conversation ID
            message_id: Target message ID

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Navigating conversation {conversation_id} to message {message_id}")

        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()

        try:
            async with self.db_manager.get_session() as session:
                # Verify message exists and belongs to the conversation
                query = select(Message).where(
                    Message.id == message_id,
                    Message.conversation_id == conversation_id
                )
                result = await session.execute(query)
                m = result.scalars().first()

                if not m:
                    self.logger.warning(f"Message {message_id} not found in conversation {conversation_id}")
                    return False

                # Get the conversation
                query = select(Conversation).where(Conversation.id == conversation_id)
                result = await session.execute(query)
                c = result.scalars().first()

                if not c:
                    self.logger.warning(f"Conversation {conversation_id} not found")
                    return False

                # Update conversation
                c.current_node_id = message_id
                c.modified_at = datetime.utcnow()

                # Commit transaction
                await session.commit()

                # Update cache
                if conversation_id in self._conversation_cache:
                    self._conversation_cache[conversation_id] = c

                self.logger.info(f"Navigated conversation {conversation_id} to message {message_id}")
                return True
        except Exception as e:
            await session.rollback()
            self.logger.error(f"Error navigating to message: {str(e)}")
            return False

    async def search_conversations(self, search_term: str, conversation_id: Optional[str] = None) -> List[Dict]:
        """
        Search for messages containing the search term

        Args:
            search_term: Text to search for
            conversation_id: Optional conversation ID to limit search

        Returns:
            List of matching message dictionaries
        """
        self.logger.debug(f"Searching for '{search_term}' in conversations")

        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()

        try:
            async with self._get_session_with_timeout(15.0) as session:
                # Build the query with proper error handling for special characters
                # Use LIKE for SQLite compatibility, more complex DBs could use full-text search
                search_pattern = f"%{search_term}%"

                # Build the query with join to get conversation name
                query = select(Message, Conversation.name).join(Conversation)

                # Add search condition - case insensitive if possible
                query = query.where(Message.content.ilike(search_pattern))

                # Add conversation filter if provided
                if conversation_id:
                    query = query.where(Message.conversation_id == conversation_id)

                # Add ordering by conversation and timestamp
                query = query.order_by(Message.conversation_id, Message.timestamp.desc())

                # Execute the query with timeout protection
                try:
                    result = await session.execute(query)
                    rows = result.all()

                    # Format results
                    results = [
                        {
                            'id': m.id,
                            'conversation_id': m.conversation_id,
                            'conversation_name': name,
                            'role': m.role,
                            'content': m.content,
                            'timestamp': m.timestamp.isoformat()
                        }
                        for m, name in rows
                    ]

                    self.logger.debug(f"Found {len(results)} matching messages")
                    return results
                except OperationalError as e:
                    # Handle database timeout or lock errors
                    self.logger.error(f"Database error during search: {str(e)}")
                    return []
        except Exception as e:
            self.logger.error(f"Error searching conversations: {str(e)}")
            return []

    async def close(self):
        """Close the database connection"""
        self.logger.debug("Closing AsyncConversationService")
        # Clear caches before closing
        self._conversation_cache.clear()
        self._message_cache.clear()
        await self.db_manager.close()
        self.logger.info("AsyncConversationService closed")

    # Add/modify this method in src/services/database/async_conversation_service.py
    async def get_all_conversations(self) -> List[Conversation]:
        """
        Get all conversations ordered by last modified date with improved timeout handling
        and better error recovery strategies.

        Returns:
            List of Conversation objects
        """
        self.logger.debug("Getting all conversations")

        # Ensure the service is initialized
        if not self._initialized:
            success = await self.initialize()
            if not success:
                self.logger.error("Failed to initialize database service")
                return []

        # Use our improved session context manager with timeout
        async with self._get_session_with_timeout(10.0) as session:
            try:
                # Set a timeout of 5 seconds for this query using the session context manager
                # If the above didn't time out, execute the query
                query = select(Conversation).order_by(Conversation.modified_at.desc())
                result = await session.execute(query)
                conversations = result.scalars().all()

                # Update cache with fetched conversations
                for conv in conversations:
                    self._conversation_cache[conv.id] = conv

                self.logger.debug(f"Found {len(conversations)} conversations")
                return conversations
            except asyncio.TimeoutError:
                self.logger.error("Timeout while getting conversations")
                return self._get_fallback_conversations()
            except SQLAlchemyError as e:
                self.logger.error(f"Database error getting conversations: {str(e)}")
                return self._get_fallback_conversations()
            except Exception as e:
                self.logger.error(f"Error getting all conversations: {str(e)}")
                # Return empty list instead of raising
                return self._get_fallback_conversations()

    def _get_fallback_conversations(self) -> List[Conversation]:
        """
        Get conversations from cache as fallback when database fails.
        If cache is empty, create an emergency conversation.

        Returns:
            List of available conversations from cache or a new emergency one
        """
        # First try to use cache
        if self._conversation_cache:
            self.logger.warning(f"Using {len(self._conversation_cache)} cached conversations as fallback")
            return list(self._conversation_cache.values())

        # If cache is empty, create a new emergency conversation
        self.logger.warning("Creating emergency conversation as fallback")
        emergency_conv = Conversation(
            id=str(uuid.uuid4()),
            name="Emergency Conversation",
            system_message="You are a helpful assistant."
        )
        emergency_conv.created_at = datetime.utcnow()
        emergency_conv.modified_at = datetime.utcnow()

        # Add to cache
        self._conversation_cache[emergency_conv.id] = emergency_conv

        return [emergency_conv]

    @asynccontextmanager
    async def _get_session_with_timeout(self, timeout: float = 10.0) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session with timeout protection

        Args:
            timeout: Timeout in seconds

        Yields:
            An AsyncSession
        """
        try:
            # Use asyncio.wait_for to enforce timeout
            session_ctx = self.db_manager.get_session()
            async with session_ctx as session:
                yield session
        except asyncio.TimeoutError:
            self.logger.error(f"Session operation timed out after {timeout} seconds")
            raise
        except Exception as e:
            self.logger.error(f"Error in database session: {str(e)}")
            raise

    async def _execute_get_all_conversations(self, session):
        """Helper method for testing database connectivity"""
        # Simple query to test connection
        query = select(1)
        await session.execute(query)
        return True