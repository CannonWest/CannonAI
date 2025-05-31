#!/usr/bin/env python3
"""
CannonAI GUI - API Handlers

This module contains the business logic for handling API requests,
separating concerns from the Flask routing layer.
It interacts with the AsyncGeminiClient for core AI and conversation management.
"""

import asyncio
import json
import logging
import os  # For file operations
import uuid  # For generating new IDs
from pathlib import Path
from typing import Dict, Any, Optional, AsyncGenerator, Tuple, List
from datetime import datetime

# Assuming these are in the parent directory or accessible via sys.path
from async_client import AsyncGeminiClient
from command_handler import CommandHandler
from base_client import Colors  # For logging if needed, though primarily for CLI

# Set up logging
logger = logging.getLogger("cannonai.gui.api_handlers")

class APIHandlers:
    """Handles API business logic for the GUI server"""

    def __init__(self, client: AsyncGeminiClient, command_handler: CommandHandler, event_loop: asyncio.AbstractEventLoop):
        self.client = client
        self.command_handler = command_handler
        self.event_loop = event_loop
        logger.info("APIHandlers initialized.")

    def run_async(self, coro, timeout=60):
        """Run an async coroutine in the event loop and return result.

        Args:
            coro: The coroutine to run.
            timeout: Timeout in seconds for the coroutine.

        Returns:
            The result of the coroutine.

        Raises:
            TimeoutError: If the coroutine exceeds the timeout.
            Exception: Any exception raised by the coroutine.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self.event_loop)
        try:
            return future.result(timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Async operation timed out after {timeout} seconds.")
            raise
        except Exception as e:
            logger.error(f"Exception in async operation: {e}", exc_info=True)
            raise

    # --- Status and Configuration ---

    def get_status(self) -> Dict[str, Any]:
        """Get current client status, including active conversation details."""
        # logger.debug("APIHandlers: Getting client status")
        if not self.client:
            return {'connected': False, 'error': 'Client not initialized'}

        conv_data = self.client.conversation_data if hasattr(self.client, 'conversation_data') else {}
        metadata = conv_data.get("metadata", {})
        active_branch_history = []
        current_messages_tree = {}

        if self.client.conversation_id and conv_data:
            # get_conversation_history() from client should return the active branch's linear history
            active_branch_history = self.run_async(asyncio.to_thread(self.client.get_conversation_history))
            current_messages_tree = conv_data.get("messages", {})  # The entire message graph

        status = {
            'connected': True,
            'model': metadata.get("model", self.client.model),
            'streaming': self.client.use_streaming,  # Server's default streaming preference
            'conversation_id': self.client.conversation_id,
            'conversation_name': metadata.get("title", getattr(self.client, 'conversation_name', 'New Conversation')),
            'params': metadata.get("params", self.client.params).copy(),
            'history': active_branch_history,  # For displaying the current chat view
            'full_message_tree': current_messages_tree  # For client-side understanding of the whole conversation structure
        }
        # logger.debug(f"Status: conv_id={status['conversation_id']}, history_len={len(status['history'])}, tree_size={len(status['full_message_tree'])}")
        return status

    def get_models(self) -> Dict[str, Any]:
        """Get available AI models."""
        logger.debug("APIHandlers: Fetching available models.")
        try:
            models = self.run_async(self.client.get_available_models())
            logger.debug(f"Found {len(models)} models.")
            return {'models': models}
        except Exception as e:
            logger.error(f"Failed to get models: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def update_settings(self, model: Optional[str] = None,
                        streaming: Optional[bool] = None,  # Server's default streaming preference
                        params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update client settings like model, streaming preference, or generation parameters."""
        logger.info(f"Updating settings - Model: {model}, Streaming: {streaming}, Params: {params}")
        try:
            if model is not None:
                self.client.model = model
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"]["model"] = model

            if streaming is not None:
                self.client.use_streaming = streaming  # Update server's default
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    # Store as a preference in conversation metadata too, if needed for persistence per conversation
                    self.client.conversation_data["metadata"]["streaming_preference"] = streaming
                logger.debug(f"Updated client master streaming preference to: {self.client.use_streaming}")

            if params is not None:
                self.client.params.update(params)  # Update client's default params
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"].setdefault("params", {}).update(params)
                logger.debug(f"Updated client params: {self.client.params}")

            if self.client.conversation_id:  # Save changes if they affect current conversation metadata
                self.run_async(self.client.save_conversation(quiet=True))

            return {
                'success': True,
                'model': self.client.model,
                'streaming': self.client.use_streaming,  # Return current server default
                'params': self.client.params.copy()
            }
        except Exception as e:
            logger.error(f"Failed to update settings: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    # --- Conversation Lifecycle and File Operations ---

    def _find_conversation_file_by_id_or_filename(self, conversation_id_or_filename: str) -> Optional[Path]:
        """
        Helper to find a conversation file path.
        It leverages the client's list_conversations which reads metadata from files.
        """
        logger.debug(f"Finding conversation file for: {conversation_id_or_filename}")
        all_convs_info: List[Dict[str, Any]] = self.run_async(self.client.list_conversations())

        found_conv_info = None
        # Try matching by conversation_id first
        found_conv_info = next((c for c in all_convs_info if c.get("conversation_id") == conversation_id_or_filename), None)

        if not found_conv_info:  # Fallback to filename matching
            found_conv_info = next((c for c in all_convs_info if c.get("filename") == conversation_id_or_filename), None)
            if not found_conv_info and not conversation_id_or_filename.endswith(".json"):
                # Try adding .json if it's a title-like name that might be a filename without extension
                found_conv_info = next((c for c in all_convs_info if c.get("filename") == f"{conversation_id_or_filename}.json"), None)

        if found_conv_info and found_conv_info.get("path"):
            logger.debug(f"Found conversation path: {found_conv_info['path']}")
            return Path(found_conv_info["path"])

        logger.warning(f"Conversation file not found for identifier: {conversation_id_or_filename}")
        return None

    def get_conversations(self) -> Dict[str, Any]:
        """Get list of saved conversations."""
        logger.debug("APIHandlers: Fetching conversations list.")
        try:
            conversations = self.run_async(self.client.list_conversations())
            logger.debug(f"Found {len(conversations)} conversations.")
            return {'conversations': conversations}
        except Exception as e:
            logger.error(f"Failed to get conversations: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def new_conversation(self, title: str = '') -> Dict[str, Any]:
        """Start a new conversation."""
        logger.info(f"Starting new conversation with title: '{title if title else '(auto-generated)'}'")
        try:
            if self.client.conversation_id:  # Save current before starting new
                self.run_async(self.client.save_conversation(quiet=True))

            # client.start_new_conversation handles ID generation, metadata creation, and initial save
            self.run_async(self.client.start_new_conversation(title=title, is_web_ui=True))

            metadata = self.client.conversation_data.get("metadata", {})
            result = {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': metadata.get("title", self.client.conversation_name),
                'history': [],  # Active branch history is empty for a new conversation
                'model': metadata.get("model", self.client.model),
                'params': metadata.get("params", self.client.params).copy(),
                'streaming': self.client.use_streaming,  # Current server default
                'full_message_tree': self.client.conversation_data.get("messages", {})  # Will be empty
            }
            logger.info(f"New conversation created: {result['conversation_name']} (ID: {result['conversation_id']})")
            return result
        except Exception as e:
            logger.error(f"Failed to create new conversation: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def load_conversation(self, conversation_identifier: str) -> Dict[str, Any]:
        """Load a saved conversation by its ID, filename, or title."""
        logger.info(f"Loading conversation: '{conversation_identifier}'")
        try:
            if self.client.conversation_id:  # Save current before loading another
                self.run_async(self.client.save_conversation(quiet=True))

            # client.load_conversation handles finding the file and loading data
            # It should be able to take an ID, filename, or title.
            self.run_async(self.client.load_conversation(conversation_identifier))

            active_history = self.run_async(asyncio.to_thread(self.client.get_conversation_history))
            metadata = self.client.conversation_data.get("metadata", {})
            full_tree = self.client.conversation_data.get("messages", {})

            result = {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': metadata.get("title", "Untitled"),
                'history': active_history,
                'model': metadata.get("model", self.client.model),
                'params': metadata.get("params", self.client.params).copy(),
                'streaming': metadata.get("streaming_preference", self.client.use_streaming),
                'full_message_tree': full_tree
            }
            logger.info(f"Conversation '{result['conversation_name']}' loaded. Active messages: {len(active_history)}, Total in tree: {len(full_tree)}.")
            return result
        except FileNotFoundError:
            logger.error(f"Conversation file for '{conversation_identifier}' not found during load.")
            return {'error': 'Conversation file not found', 'status_code': 404}
        except Exception as e:
            logger.error(f"Failed to load conversation '{conversation_identifier}': {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def save_conversation(self) -> Dict[str, Any]:
        """Save the current active conversation."""
        logger.info("Saving current conversation.")
        if not self.client.conversation_id:
            logger.warning("No active conversation to save.")
            return {'error': 'No active conversation to save', 'status_code': 400}
        try:
            self.run_async(self.client.save_conversation())  # Client handles file naming and saving
            logger.info(f"Conversation '{self.client.conversation_data.get('metadata', {}).get('title')}' saved.")
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def duplicate_conversation(self, conversation_id_to_duplicate: str, new_title: str) -> Dict[str, Any]:
        """Duplicate an existing conversation with a new title and ID."""
        logger.info(f"Duplicating conversation (ID/File): {conversation_id_to_duplicate} to new title: '{new_title}'")
        original_filepath = self._find_conversation_file_by_id_or_filename(conversation_id_to_duplicate)

        if not original_filepath or not original_filepath.exists():
            logger.error(f"Original conversation file not found for duplication: {conversation_id_to_duplicate}")
            return {'error': 'Original conversation file not found', 'status_code': 404}

        try:
            with open(original_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            new_conv_id_str = self.run_async(asyncio.to_thread(self.client.generate_conversation_id))

            data['conversation_id'] = new_conv_id_str  # Critical: New ID for the copy
            if 'metadata' not in data: data['metadata'] = {}  # Ensure metadata key exists

            data['metadata']['title'] = new_title
            now_iso = datetime.now().isoformat()
            data['metadata']['created_at'] = now_iso
            data['metadata']['updated_at'] = now_iso
            # Consider if active_branch and active_leaf should be reset or copied. For a true duplicate, copy.

            new_filename_str = self.run_async(asyncio.to_thread(self.client.format_filename, new_title, new_conv_id_str))
            new_filepath = self.client.conversations_dir / new_filename_str

            with open(new_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Conversation duplicated successfully to {new_filepath}")
            return {'success': True, 'new_conversation_id': new_conv_id_str, 'new_title': new_title, 'new_filename': new_filename_str}
        except Exception as e:
            logger.error(f"Error duplicating conversation: {e}", exc_info=True)
            return {'error': f'Server error: {str(e)}', 'status_code': 500}

    def rename_conversation(self, conversation_id_or_filename_to_rename: str, new_title: str) -> Dict[str, Any]:
        """Rename an existing conversation (updates title in metadata and filename)."""
        logger.info(f"Renaming conversation (ID/File): {conversation_id_or_filename_to_rename} to new title: '{new_title}'")
        original_filepath = self._find_conversation_file_by_id_or_filename(conversation_id_or_filename_to_rename)

        if not original_filepath or not original_filepath.exists():
            logger.error(f"Conversation file not found for renaming: {conversation_id_or_filename_to_rename}")
            return {'error': 'Conversation file not found', 'status_code': 404}

        try:
            with open(original_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            actual_conversation_id = data.get('conversation_id')
            if not actual_conversation_id:
                logger.error(f"Conversation ID missing in file content: {original_filepath}")
                return {'error': 'Internal server error: Conversation ID missing', 'status_code': 500}

            if 'metadata' not in data: data['metadata'] = {}
            data['metadata']['title'] = new_title
            data['metadata']['updated_at'] = datetime.now().isoformat()

            # Save updated content to the original file path first
            with open(original_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Determine new filename and rename if different
            new_filename_str = self.run_async(asyncio.to_thread(self.client.format_filename, new_title, actual_conversation_id))
            new_filepath = self.client.conversations_dir / new_filename_str

            if original_filepath != new_filepath:
                logger.info(f"Renaming file from {original_filepath.name} to {new_filepath.name}")

                def rename_sync(): os.rename(original_filepath, new_filepath)

                self.run_async(asyncio.to_thread(rename_sync))

            logger.info(f"Conversation renamed. New title: '{new_title}', Path: {new_filepath.name}")
            return {'success': True, 'conversation_id': actual_conversation_id, 'new_title': new_title, 'new_filename': new_filename_str}
        except Exception as e:
            logger.error(f"Error renaming conversation: {e}", exc_info=True)
            return {'error': f'Server error: {str(e)}', 'status_code': 500}

    def delete_conversation(self, conversation_id_or_filename_to_delete: str) -> Dict[str, Any]:
        """Delete a conversation file."""
        logger.info(f"Deleting conversation (ID/File): {conversation_id_or_filename_to_delete}")
        filepath_to_delete = self._find_conversation_file_by_id_or_filename(conversation_id_or_filename_to_delete)

        if not filepath_to_delete or not filepath_to_delete.exists():
            logger.error(f"Conversation file not found for deletion: {conversation_id_or_filename_to_delete}")
            return {'error': 'Conversation file not found', 'status_code': 404}

        try:
            # Try to read conversation_id from file before deleting for response accuracy
            actual_conversation_id = conversation_id_or_filename_to_delete  # Fallback
            try:
                with open(filepath_to_delete, 'r', encoding='utf-8') as f_read:
                    data_read = json.load(f_read)
                    actual_conversation_id = data_read.get('conversation_id', actual_conversation_id)
            except Exception as read_err:
                logger.warning(f"Could not read ID from {filepath_to_delete.name} before deletion: {read_err}")

            def delete_sync():
                os.remove(filepath_to_delete)

            self.run_async(asyncio.to_thread(delete_sync))

            logger.info(f"Conversation file {filepath_to_delete.name} deleted successfully.")
            return {'success': True, 'deleted_conversation_id': actual_conversation_id}
        except Exception as e:
            logger.error(f"Error deleting conversation file {filepath_to_delete.name if filepath_to_delete else 'N/A'}: {e}", exc_info=True)
            return {'error': f'Server error: {str(e)}', 'status_code': 500}

    # --- Message Interaction ---

    def send_message(self, message_content: str) -> Dict[str, Any]:
        """Send a message (non-streaming) and get AI response."""
        logger.debug(f"APIHandlers: Handling non-streaming send for message: '{message_content[:50]}...'")
        try:
            if not self.client.conversation_id:  # Ensure conversation exists
                logger.info("No active conversation for send_message, starting new one implicitly.")
                self.run_async(self.client.start_new_conversation(is_web_ui=True))

            # Client's add_user_message updates conversation_data and sets current_user_message_id
            self.run_async(asyncio.to_thread(self.client.add_user_message, message_content))
            user_message_id_for_parenting = self.client.current_user_message_id

            # Client's get_response gets AI reply (non-streaming)
            response_text, token_usage = self.run_async(self.client.get_response())

            if response_text is None:  # get_response might return (None, None) on error
                raise Exception("AI client failed to generate a valid response.")

            # Client's add_assistant_message updates conversation_data
            self.run_async(asyncio.to_thread(self.client.add_assistant_message, response_text, token_usage))
            assistant_message_id = self.run_async(asyncio.to_thread(self.client._get_last_message_id, self.client.active_branch))

            self.run_async(self.client.save_conversation(quiet=True))  # Auto-save

            logger.debug(f"Non-streaming response: '{response_text[:50]}...', UserMsgID: {user_message_id_for_parenting}, AsstMsgID: {assistant_message_id}")
            return {
                'response': response_text,
                'conversation_id': self.client.conversation_id,
                'message_id': assistant_message_id,  # ID of the new assistant message
                'parent_id': user_message_id_for_parenting,  # ID of the user message it's replying to
                'model': self.client.conversation_data.get("metadata", {}).get("model", self.client.model),
                'token_usage': token_usage or {}
            }
        except Exception as e:
            logger.error(f"Failed in send_message (non-streaming): {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    async def stream_message(self, message_content: str) -> AsyncGenerator[str, None]:
        """Stream AI response using Server-Sent Events format."""
        logger.debug(f"APIHandlers: Streaming message: '{message_content[:50]}...'")
        try:
            if not self.client.conversation_id:
                logger.info("No active conversation for stream_message, starting new one implicitly.")
                await self.client.start_new_conversation(is_web_ui=True)

            # Client's add_user_message is synchronous but called via to_thread if needed by client
            await asyncio.to_thread(self.client.add_user_message, message_content)

            # Client's get_streaming_response is an async generator
            # It yields dicts: {'chunk': str} or {'error': str} or final {'done': True, ...}
            async for data_event in self.client.get_streaming_response():
                yield f"data: {json.dumps(data_event)}\n\n"
                if data_event.get("error") or data_event.get("done"):
                    break
            logger.debug("Streaming finished.")
        except Exception as e:
            logger.error(f"Streaming error in API Handler: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Ensure conversation is saved after streaming, regardless of success/failure within stream
            try:
                if self.client.conversation_id:
                    await self.client.save_conversation(quiet=True)
            except Exception as save_e:
                logger.error(f"Error saving conversation during stream_message finally block: {save_e}")

    def retry_message(self, assistant_message_id_to_retry: str) -> Dict[str, Any]:
        """Retry generating a response for a specific assistant message."""
        logger.info(f"Retrying assistant message: {assistant_message_id_to_retry}")
        try:
            # client.retry_message handles creating new branch, getting response, updating active branch
            retry_result_dict = self.run_async(self.client.retry_message(assistant_message_id_to_retry))
            self.run_async(self.client.save_conversation(quiet=True))
            logger.debug(f"Retry successful. New assistant message ID: {retry_result_dict['message']['id']}")

            current_active_history = self.run_async(asyncio.to_thread(self.client.get_conversation_history))
            current_full_tree = self.client.conversation_data.get("messages", {})

            return {
                'success': True,
                'message': retry_result_dict['message'],  # The new assistant message object
                'sibling_index': retry_result_dict['sibling_index'],
                'total_siblings': retry_result_dict['total_siblings'],
                'history': current_active_history,  # Send history of the new active branch
                'conversation_id': self.client.conversation_id,
                'conversation_name': self.client.conversation_data.get("metadata", {}).get("title"),
                'full_message_tree': current_full_tree
            }
        except Exception as e:
            logger.error(f"Failed to retry message {assistant_message_id_to_retry}: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def navigate_sibling(self, message_id: str, direction: str) -> Dict[str, Any]:
        """Navigate to a sibling of an assistant message or activate a message's branch."""
        logger.info(f"Navigating {direction} from message: {message_id}")
        try:
            # client.switch_to_sibling handles changing active_branch and active_leaf
            nav_result_dict = self.run_async(self.client.switch_to_sibling(message_id, direction))
            self.run_async(self.client.save_conversation(quiet=True))
            logger.debug(f"Navigated. New active message: {nav_result_dict['message']['id']}, Sibling Index: {nav_result_dict['sibling_index']}")

            current_active_history = self.run_async(asyncio.to_thread(self.client.get_conversation_history))
            current_full_tree = self.client.conversation_data.get("messages", {})

            return {
                'success': True,
                'message': nav_result_dict['message'],  # The new active assistant message
                'sibling_index': nav_result_dict['sibling_index'],
                'total_siblings': nav_result_dict['total_siblings'],
                'history': current_active_history,
                'conversation_id': self.client.conversation_id,
                'conversation_name': self.client.conversation_data.get("metadata", {}).get("title"),
                'full_message_tree': current_full_tree
            }
        except Exception as e:
            logger.error(f"Failed to navigate sibling for {message_id} ({direction}): {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def get_message_info(self, message_id: str) -> Dict[str, Any]:
        """Get detailed information about a message, including its siblings."""
        logger.debug(f"Getting info for message: {message_id}")
        try:
            # client.get_message_siblings provides info about children of the message's parent
            sibling_info_dict = self.run_async(self.client.get_message_siblings(message_id))

            messages_dict = self.client.conversation_data.get("messages", {})
            message_data = messages_dict.get(message_id, {})
            if not message_data:
                return {'error': f"Message {message_id} not found in current conversation data", 'status_code': 404}

            logger.debug(f"Message {message_id} has {sibling_info_dict['total']} siblings.")
            return {
                'success': True,
                'message': message_data,  # The requested message itself
                'siblings': sibling_info_dict['siblings'],  # List of sibling IDs
                'current_index': sibling_info_dict['current_index'],  # Index of message_id among siblings
                'total_siblings': sibling_info_dict['total']
            }
        except Exception as e:
            logger.error(f"Failed to get message info for {message_id}: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def get_conversation_tree(self) -> Dict[str, Any]:
        """Get the full conversation tree structure (nodes and edges)."""
        logger.debug("APIHandlers: Getting full conversation tree.")
        try:
            # client.get_conversation_tree() returns the structured tree
            tree_data = self.run_async(self.client.get_conversation_tree())
            logger.debug(f"Tree has {len(tree_data.get('nodes', []))} nodes and {len(tree_data.get('edges', []))} edges.")
            return {'success': True, 'tree': tree_data}
        except Exception as e:
            logger.error(f"Failed to get conversation tree: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    # --- Command Execution ---

    def execute_command(self, command_str: str) -> Dict[str, Any]:
        """Execute a text-based command (e.g., /new, /load)."""
        logger.info(f"Executing command: '{command_str}'")
        try:
            # Parse command (simple split for now, CommandHandler might have more complex parsing)
            parts = command_str.lower().split(maxsplit=1)
            cmd_name = parts[0]
            cmd_args = parts[1] if len(parts) > 1 else ""

            # Handle commands that have specific API handler methods for richer responses
            if cmd_name == '/new':
                return self.new_conversation(title=cmd_args)
            if cmd_name == '/load':
                return self.load_conversation(cmd_args) if cmd_args else {'error': 'Specify conversation name/ID to load.', 'status_code': 400}
            if cmd_name == '/save':
                return self.save_conversation()
            if cmd_name == '/list':  # Refresh and return list
                convos = self.get_conversations()
                return {'success': True, 'message': 'Conversations list refreshed.', 'conversations': convos.get('conversations')}
            if cmd_name == '/model':
                return self.update_settings(model=cmd_args) if cmd_args else self.get_models()
            if cmd_name == '/stream':  # Toggle server's default streaming
                return self.update_settings(streaming=not self.client.use_streaming)
            if cmd_name == '/params':  # For GUI, this might just reflect current state or be handled by settings modal
                return {'success': True, 'params': self.client.params.copy(), 'message': 'Current generation parameters. Modify via Settings.'}

            # For other commands, or if CommandHandler is used for more complex logic:
            if hasattr(self.command_handler, 'async_handle_command'):
                # This is a more generic handler; its return might be simple text or boolean
                # The CommandHandler itself might call client methods.
                # This path is less ideal for GUI updates that need structured data.
                handler_result = self.run_async(self.command_handler.async_handle_command(command_str))

                # After a generic command, it's good to return the full current status
                # so the client can re-sync if anything changed.
                current_status = self.get_status()
                response_payload = {
                    'success': True,  # Assume success if no exception
                    'message': f"Command '{command_str}' processed.",
                    'handler_output': str(handler_result),  # Include raw output for debugging
                    **current_status  # Merge in the full current status
                }
                return response_payload
            else:
                logger.warning(f"Command '{cmd_name}' not directly handled by APIHandlers and no generic command_handler found.")
                return {'error': f"Unknown or unsupported command: {cmd_name}", 'status_code': 400}

        except Exception as e:
            logger.error(f"Failed to execute command '{command_str}': {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}
