"""
Fully asynchronous conversation service using SQLAlchemy 2.0 with asyncio support.
Replaces the previous AsyncConversationService that used thread pools.
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
from sqlalchemy import delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload

# Local application imports
from src.services.database.async_manager import AsyncDatabaseManager
from src.services.database.models import Conversation, FileAttachment, Message
from src.utils.logging_utils import get_logger

# Get a logger for this module
logger = get_logger(__name__)


class AsyncConversationService:
    """
    Fully asynchronous service class for managing conversations and messages.
    Uses SQLAlchemy 2.0 with asyncio support for all database operations.
    """

    def __init__(self, connection_string=None):
        """
        Initialize the async conversation service

        Args:
            connection_string: Optional SQLAlchemy connection string for the database
        """
        self.db_manager = AsyncDatabaseManager(connection_string)
        self.logger = get_logger(f"{__name__}.AsyncConversationService")
        self._initialized = False
        self.logger.info("AsyncConversationService created")

    async def initialize(self) -> bool:
        """
        Initialize database tables

        Returns:
            True if successful, False if an error occurred
        """
        if not self._initialized:
            try:
                # Log the current event loop
                loop = asyncio.get_event_loop()
                self.logger.debug(f"Initializing with event loop: {id(loop)}")

                await self.db_manager.create_tables()
                self._initialized = True
                self.logger.info("AsyncConversationService initialized")
                return True
            except Exception as e:
                self.logger.error(f"Failed to initialize database: {str(e)}")
                # Don't re-raise, allow reduced functionality
                return False
        return True

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

    async def create_conversation(self, name="New Conversation", system_message="You are a helpful assistant."):
        """
        Create a new conversation with an initial system message

        Args:
            name: Name of the conversation
            system_message: System message content

        Returns:
            The created Conversation object or None if failed
        """
        self.logger.debug(f"Creating conversation: {name}")
        
        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()
        
        async with self.db_manager.get_session() as session:
            try:
                # Create conversation
                c = Conversation(name=name, system_message=system_message)
                session.add(c)
                
                # Create system message
                msg_id = str(uuid.uuid4())
                m = Message(id=msg_id, conversation_id=c.id, role="system", content=system_message)
                session.add(m)
                
                # Set current node
                c.current_node_id = m.id
                
                # Commit transaction
                await session.commit()
                
                # Refresh to get the complete object
                await session.refresh(c)
                
                self.logger.info(f"Created conversation {c.id} with name '{name}'")
                return c
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error creating conversation: {str(e)}")
                raise

    async def get_conversation(self, id: str) -> Optional[Conversation]:
        """
        Get a conversation by ID

        Args:
            id: Conversation ID

        Returns:
            The Conversation object or None if not found
        """
        self.logger.debug(f"Getting conversation: {id}")
        
        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()
        
        async with self.db_manager.get_session() as session:
            # Query with relationships loaded
            query = select(Conversation).where(Conversation.id == id)
            result = await session.execute(query)
            return result.scalars().first()

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
        
        async with self.db_manager.get_session() as session:
            try:
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
                
                self.logger.info(f"Updated conversation {id}")
                return True
            except Exception as e:
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

                # Now delete the conversation (cascade will handle messages)
                await session.delete(conversation)

                # Commit changes
                await session.commit()

                self.logger.info(f"Deleted conversation {id}")
                return True
            except Exception as e:
                await session.rollback()
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
        
        async with self.db_manager.get_session() as session:
            try:
                # Get the source conversation
                query = select(Conversation).where(Conversation.id == conversation_id)
                result = await session.execute(query)
                source_conv = result.scalars().first()
                
                if not source_conv:
                    self.logger.warning(f"Source conversation {conversation_id} not found")
                    return None
                
                # Set the new name
                if new_name is None:
                    new_name = f"{source_conv.name} (Copy)"
                
                # Create a new conversation with the same system message
                new_conv = Conversation(
                    name=new_name,
                    system_message=source_conv.system_message
                )
                session.add(new_conv)
                await session.flush()  # Flush to get the new conversation ID
                
                # Get all messages from the source conversation
                query = select(Message).where(Message.conversation_id == conversation_id)
                result = await session.execute(query)
                source_messages = result.scalars().all()
                
                # Create a mapping of old message IDs to new message IDs
                id_mapping = {}
                
                # First pass: create all new messages without parent IDs
                for source_msg in source_messages:
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
                    
                    # Set the current node for the system message
                    if source_msg.role == "system":
                        new_conv.current_node_id = new_msg.id
                
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
                
                # If the source conversation has a current node, set the equivalent in the new conversation
                if source_conv.current_node_id and source_conv.current_node_id in id_mapping:
                    new_conv.current_node_id = id_mapping[source_conv.current_node_id]
                
                # Commit the changes
                await session.commit()
                
                # Refresh the new conversation
                await session.refresh(new_conv)
                
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
        
        async with self.db_manager.get_session() as session:
            try:
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
                m = Message(id=str(uuid.uuid4()), role="user", content=content, conversation_id=conversation_id, parent_id=parent_id)
                session.add(m)
                
                # Update conversation
                c.current_node_id = m.id
                c.modified_at = datetime.utcnow()
                
                # Commit transaction
                await session.commit()
                
                # Refresh the message
                await session.refresh(m)
                
                self.logger.info(f"Added user message {m.id} to conversation {conversation_id}")
                return m
            except Exception as e:
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
        
        async with self.db_manager.get_session() as session:
            try:
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
                session.add(m)
                
                # Update conversation
                c.current_node_id = m.id
                c.modified_at = datetime.utcnow()
                
                # Commit transaction
                await session.commit()
                
                # Refresh the message
                await session.refresh(m)
                
                self.logger.info(f"Added assistant message {m.id} to conversation {conversation_id}")
                return m
            except Exception as e:
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
        
        async with self.db_manager.get_session() as session:
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

    async def get_message(self, id: str) -> Optional[Message]:
        """
        Get a message by ID

        Args:
            id: Message ID

        Returns:
            The Message object or None if not found
        """
        self.logger.debug(f"Getting message {id}")
        
        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()
        
        async with self.db_manager.get_session() as session:
            query = select(Message).where(Message.id == id).options(
                selectinload(Message.file_attachments)
            )
            result = await session.execute(query)
            return result.scalars().first()

    async def get_message_branch(self, message_id: str) -> List[Message]:
        """
        Get the branch of messages from root to the specified message

        Args:
            message_id: ID of the leaf message

        Returns:
            List of messages from root to leaf
        """
        self.logger.debug(f"Getting message branch for {message_id}")
        
        # Ensure the service is initialized
        if not self._initialized:
            await self.initialize()
        
        async with self.db_manager.get_session() as session:
            branch = []
            current_id = message_id
            
            while current_id:
                query = select(Message).where(Message.id == current_id).options(
                    selectinload(Message.file_attachments)
                )
                result = await session.execute(query)
                m = result.scalars().first()
                
                if not m:
                    break
                    
                branch.insert(0, m)
                current_id = m.parent_id
            
            self.logger.debug(f"Found {len(branch)} messages in branch")
            return branch

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
        
        async with self.db_manager.get_session() as session:
            try:
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
        
        async with self.db_manager.get_session() as session:
            # Build the query
            query = select(Message, Conversation.name).join(Conversation)
            
            # Add search condition - case insensitive if possible
            query = query.where(Message.content.ilike(f'%{search_term}%'))
            
            # Add conversation filter if provided
            if conversation_id:
                query = query.where(Message.conversation_id == conversation_id)
            
            # Execute the query
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

    async def close(self):
        """Close the database connection"""
        self.logger.debug("Closing AsyncConversationService")
        await self.db_manager.close()
        self.logger.info("AsyncConversationService closed")

    # Add/modify this method in src/services/database/async_conversation_service.py

    async def get_all_conversations(self) -> List[Conversation]:
        """
        Get all conversations ordered by last modified date with improved timeout handling

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

        # Use a shorter timeout for the session
        async with self.db_manager.get_session() as session:
            try:
                # Set a timeout of 5 seconds for this query
                await asyncio.wait_for(self._execute_get_all_conversations(session), timeout=5.0)

                # If the above didn't time out, execute the query
                query = select(Conversation).order_by(Conversation.modified_at.desc())
                result = await session.execute(query)
                conversations = result.scalars().all()

                self.logger.debug(f"Found {len(conversations)} conversations")
                return conversations
            except asyncio.TimeoutError:
                self.logger.error("Timeout while getting conversations")
                return []
            except Exception as e:
                self.logger.error(f"Error getting all conversations: {str(e)}")
                # Return empty list instead of raising
                return []

    async def _execute_get_all_conversations(self, session):
        """Helper method for testing database connectivity"""
        # Simple query to test connection
        query = select(1)
        await session.execute(query)
        return True


    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a new async database session as a context manager with improved error handling
        and recovery mechanisms for Windows.

        Usage:
            async with db_manager.get_session() as session:
                # Use session here
        """
        # Make sure engine is created with current event loop
        if not self._initialized:
            self._create_engine()

        # Create session with proper timeout management
        timeout = 10.0  # 10 seconds timeout
        start_time = time.time()

        session = None
        attempt = 0
        max_attempts = 3

        while attempt < max_attempts:
            try:
                attempt += 1
                # Get the session from the factory
                session = self.async_session()

                # Test the connection with a simple query
                if platform.system() == "Windows":
                    try:
                        # For Windows, use a more reliable approach
                        await asyncio.wait_for(self._test_connection(session), timeout=5.0)
                    except (asyncio.TimeoutError, Exception) as e:
                        if attempt < max_attempts:
                            self.logger.warning(f"Connection test failed on attempt {attempt}: {str(e)}")
                            if session:
                                await session.close()
                            session = None
                            await asyncio.sleep(0.1)  # Brief pause before retry
                            continue
                        else:
                            raise

                # Yield the session to the caller
                try:
                    yield session
                except Exception as e:
                    self.logger.error(f"Error in database session: {str(e)}")
                    if session and not session.is_active:
                        self.logger.debug("Session rollback needed")
                        await session.rollback()
                    raise
                finally:
                    # Always close the session when done
                    if session:
                        execution_time = time.time() - start_time

                        # Log slow queries
                        if execution_time > 1.0:  # Log queries taking more than 1 second
                            self.logger.warning(f"Slow database operation: {execution_time:.3f}s")

                        try:
                            await session.close()
                        except Exception as e:
                            self.logger.error(f"Error closing session: {str(e)}")

                # If we got here, the session was successful
                break

            except Exception as e:
                self.logger.error(f"Failed to create database session (attempt {attempt}): {str(e)}")

                # Clean up if we couldn't create a session
                if session:
                    try:
                        await session.close()
                    except:
                        pass

                # If we've used all our attempts, raise the exception
                if attempt >= max_attempts:
                    raise

                # Otherwise wait briefly and try again
                await asyncio.sleep(0.2)

    async def _test_connection(self, session):
        """Test if the database connection is working"""
        query = select(1)
        await session.execute(query)
        return True