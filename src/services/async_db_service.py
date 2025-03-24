"""
Asynchronous service for database operations.
Uses thread pool to avoid blocking the event loop on database operations.
"""

import asyncio
import concurrent.futures
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from src.models.orm_models import Conversation, Message, FileAttachment
from src.services.db_service import ConversationService
from src.utils.logging_utils import get_logger

# Get a logger for this module
logger = get_logger(__name__)


class AsyncConversationService:
    """
    Asynchronous service class for managing conversations and messages.
    Wraps synchronous database operations in a thread pool executor.
    """

    def __init__(self, thread_pool_size=4):
        """
        Initialize the async conversation service with a thread pool

        Args:
            thread_pool_size: Size of the thread pool for DB operations
        """
        self.sync_service = ConversationService()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=thread_pool_size)
        self.logger = get_logger(f"{__name__}.AsyncConversationService")
        self.logger.info(f"Initialized AsyncConversationService with {thread_pool_size} workers")

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
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.sync_service.create_conversation,
            name,
            system_message
        )

    async def get_conversation(self, id):
        """
        Get a conversation by ID

        Args:
            id: Conversation ID

        Returns:
            The Conversation object or None if not found
        """
        self.logger.debug(f"Getting conversation: {id}")
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.sync_service.get_conversation,
            id
        )

    async def get_all_conversations(self):
        """
        Get all conversations ordered by last modified date

        Returns:
            List of Conversation objects
        """
        self.logger.debug("Getting all conversations")
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.sync_service.get_all_conversations
        )

    async def update_conversation(self, id, **kwargs):
        """
        Update a conversation with new values

        Args:
            id: Conversation ID
            **kwargs: Fields to update

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Updating conversation {id} with {kwargs}")
        
        # Create a wrapper function to handle kwargs
        def update_wrapper():
            return self.sync_service.update_conversation(id, **kwargs)
            
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            update_wrapper
        )

    async def delete_conversation(self, id):
        """
        Delete a conversation

        Args:
            id: Conversation ID

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Deleting conversation: {id}")
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.sync_service.delete_conversation,
            id
        )

    async def duplicate_conversation(self, conversation_id, new_name=None):
        """
        Duplicate a conversation, including all messages and file attachments

        Args:
            conversation_id: ID of the conversation to duplicate
            new_name: Name for the new conversation, defaults to "<original_name> (Copy)"

        Returns:
            The new conversation, or None if the source conversation is not found
        """
        self.logger.debug(f"Duplicating conversation: {conversation_id}")
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.sync_service.duplicate_conversation,
            conversation_id,
            new_name
        )

    async def add_user_message(self, conversation_id, content, parent_id=None):
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
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.sync_service.add_user_message,
            conversation_id,
            content,
            parent_id
        )

    async def add_assistant_message(self, conversation_id, content, parent_id=None, model_info=None, token_usage=None,
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
        
        # Create a wrapper function to handle all the parameters
        def add_message_wrapper():
            return self.sync_service.add_assistant_message(
                conversation_id=conversation_id,
                content=content,
                parent_id=parent_id,
                model_info=model_info,
                token_usage=token_usage,
                reasoning_steps=reasoning_steps,
                response_id=response_id
            )
            
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            add_message_wrapper
        )

    async def add_file_attachment(self, message_id, file_info):
        """
        Add a file attachment to a message

        Args:
            message_id: Message ID
            file_info: Dictionary with file information

        Returns:
            The created FileAttachment object or None if failed
        """
        self.logger.debug(f"Adding file attachment to message {message_id}")
        
        # Create a wrapper function to pass the file_info dict
        def add_attachment_wrapper():
            return self.sync_service.add_file_attachment(message_id, file_info)
            
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            add_attachment_wrapper
        )

    async def get_message(self, id):
        """
        Get a message by ID

        Args:
            id: Message ID

        Returns:
            The Message object or None if not found
        """
        self.logger.debug(f"Getting message {id}")
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.sync_service.get_message,
            id
        )

    async def get_message_branch(self, message_id):
        """
        Get the branch of messages from root to the specified message

        Args:
            message_id: ID of the leaf message

        Returns:
            List of messages from root to leaf
        """
        self.logger.debug(f"Getting message branch for {message_id}")
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.sync_service.get_message_branch,
            message_id
        )

    async def navigate_to_message(self, conversation_id, message_id):
        """
        Set the current node of a conversation to a specific message

        Args:
            conversation_id: Conversation ID
            message_id: Target message ID

        Returns:
            True if successful, False otherwise
        """
        self.logger.debug(f"Navigating conversation {conversation_id} to message {message_id}")
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.sync_service.navigate_to_message,
            conversation_id,
            message_id
        )

    async def search_conversations(self, search_term, conversation_id=None):
        """
        Search for messages containing the search term

        Args:
            search_term: Text to search for
            conversation_id: Optional conversation ID to limit search

        Returns:
            List of matching message dictionaries
        """
        self.logger.debug(f"Searching for '{search_term}' in conversations")
        
        # Create wrapper function to handle optional parameter
        def search_wrapper():
            return self.sync_service.search_conversations(search_term, conversation_id)
            
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            search_wrapper
        )
        
    def close(self):
        """Close the thread pool executor"""
        self.executor.shutdown(wait=False)
        self.logger.info("AsyncConversationService executor shut down")
