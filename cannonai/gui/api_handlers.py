#!/usr/bin/env python3
"""
CannonAI GUI - API Handlers

This module contains the business logic for handling API requests,
separating concerns from the Flask routing layer.
It interacts with the AsyncClient for core AI and conversation management.
System instructions are now managed via conversation metadata.
"""

import asyncio
import json
import logging
import os  # Retained for potential use, though not directly in this refactor
import uuid  # Retained for potential use
from pathlib import Path
from typing import Dict, Any, Optional, AsyncGenerator, Tuple, List  # Retained List, Tuple
from datetime import datetime

from async_client import AsyncClient
from command_handler import CommandHandler  # Retained
from base_client import Colors  # Retained
from config import Config  # For default system instruction if needed
from provider_manager import ProviderManager  # *** ADDED: For seamless provider switching ***

logger = logging.getLogger("cannonai.gui.api_handlers")

# This global variable can be set by server.py to provide access to the main app config.
# Useful for things like getting the global default system instruction.
main_config: Optional[Config] = None


class APIHandlers:
    """Handles API business logic for the GUI server."""

    def __init__(self, client: AsyncClient, command_handler: CommandHandler, event_loop: asyncio.AbstractEventLoop):
        self.client = client
        self.command_handler = command_handler  # Retained, though its use of system instruction might change
        self.event_loop = event_loop
        self.provider_manager: Optional[ProviderManager] = None  # *** ADDED: Will be set later ***

        if self.client and self.client.provider:
            logger.info(f"APIHandlers initialized with client for provider: {self.client.provider.provider_name}.")
        elif self.client:
            logger.warning("APIHandlers initialized with a client, but client has no provider set.")
        else:
            logger.error("APIHandlers initialized WITHOUT a client instance. GUI may not function.")
    
    def set_provider_manager(self, provider_manager: ProviderManager) -> None:
        """Set the provider manager for dynamic provider switching."""
        self.provider_manager = provider_manager
        logger.info("Provider manager set for API handlers")

    def run_async(self, coro, timeout: int = 60) -> Any:
        """
        Run an async coroutine in the event loop from a synchronous context
        and return its result. Handles common loop issues.
        """
        if not self.event_loop or self.event_loop.is_closed():
            logger.error("Event loop for APIHandlers is not running or closed.")
            try:  # Attempt to re-acquire the loop if it's the main thread's loop
                self.event_loop = asyncio.get_running_loop()
                if not self.event_loop.is_running():
                    raise RuntimeError("Acquired loop is not running.")
                logger.info("Re-acquired running event loop for APIHandlers.")
            except RuntimeError:
                logger.critical("No running asyncio event loop found for APIHandlers. Cannot execute async task.")
                raise RuntimeError("APIHandlers: Critical - Cannot execute async task without a running event loop.")

        if not self.event_loop.is_running():  # Final check
            logger.critical("APIHandlers: Event loop exists but is not running. Cannot schedule coroutine.")
            raise RuntimeError("APIHandlers: Critical - Event loop is not running.")

        future = asyncio.run_coroutine_threadsafe(coro, self.event_loop)
        try:
            return future.result(timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Async operation in APIHandlers timed out after {timeout} seconds.")
            raise  # Re-raise for Flask to handle as a server error
        except Exception as e:
            logger.error(f"Exception in APIHandlers async operation: {e}", exc_info=True)
            raise  # Re-raise

    def get_status(self) -> Dict[str, Any]:
        """Get current client status, including active conversation details and system instruction from metadata."""
        if not self.client or not self.client.provider:
            return {'connected': False, 'error': 'Client or provider not initialized'}

        conv_data = self.client.conversation_data if hasattr(self.client, 'conversation_data') else {}
        metadata = conv_data.get("metadata", {})

        # Get system instruction from conversation metadata, fallback to client's current (which might be global default)
        current_system_instruction = metadata.get("system_instruction", self.client.system_instruction)

        active_branch_history = []  # Actual stored messages
        current_messages_tree = {}

        if self.client.conversation_id and conv_data:
            try:
                # get_conversation_history() now returns only stored user/assistant messages
                active_branch_history = self.client.get_conversation_history()
                current_messages_tree = conv_data.get("messages", {})
            except Exception as e:
                logger.error(f"Error getting history/tree for status: {e}", exc_info=True)
                active_branch_history = [{"role": "system", "content": f"Error loading history: {e}"}]  # Error placeholder

        return {
            'connected': self.client.provider.is_initialized,
            'provider_name': self.client.provider.provider_name,
            'model': self.client.current_model_name,
            'streaming': metadata.get("streaming_preference", self.client.use_streaming),  # Use conv's pref, then client's
            'conversation_id': self.client.conversation_id,
            'conversation_name': metadata.get("title", getattr(self.client, 'conversation_name', 'New Conversation')),
            'params': metadata.get("params", self.client.params).copy(),  # Use conv's params, then client's
            'history': active_branch_history,  # Actual stored messages
            'full_message_tree': current_messages_tree,
            'system_instruction': current_system_instruction,  # From metadata
        }

    def get_models(self) -> Dict[str, Any]:
        """Gets available models from the current provider."""
        logger.debug("APIHandlers: Fetching available models.")
        if not self.client or not self.client.provider:
            return {'error': 'Client or provider not initialized', 'status_code': 503, 'models': [], 'current_provider': 'N/A'}
        try:
            models = self.run_async(self.client.get_available_models())
            logger.debug(f"API Handlers found {len(models)} models for provider {self.client.provider.provider_name}.")
            return {'models': models, 'current_provider': self.client.provider.provider_name}
        except Exception as e:
            logger.error(f"Failed to get models via APIHandlers: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500, 'models': [], 'current_provider': self.client.provider.provider_name if self.client and self.client.provider else 'N/A'}

    def update_settings(self, provider: Optional[str] = None,
                        model: Optional[str] = None,
                        streaming: Optional[bool] = None,  # This is client's session default streaming
                        params: Optional[Dict[str, Any]] = None
                        # system_instruction is now handled by update_conversation_system_instruction
                        ) -> Dict[str, Any]:
        """Updates client/conversation settings like model, params, session streaming preference."""
        global main_config  # Declare global at the beginning of the function scope

        logger.info(f"APIHandlers: Updating settings - Provider: {provider}, Model: {model}, Streaming: {streaming}, Params: {params}")
        if not self.client or not self.client.provider:
            return {'error': 'Client or provider not initialized', 'status_code': 503}

        try:
            # *** SEAMLESS PROVIDER SWITCHING ***
            if provider and provider != self.client.provider.provider_name:
                logger.info(f"Provider change to '{provider}' requested. Switching providers seamlessly...")
                
                if not self.provider_manager:
                    logger.error("Provider manager not available for dynamic switching")
                    return {'error': 'Provider switching not available', 'status_code': 503}
                
                try:
                    # Switch to the new provider
                    new_provider = self.run_async(self.provider_manager.switch_provider(provider, model))
                    
                    # Update the client's provider
                    self.client.provider = new_provider
                    
                    # Update conversation metadata if active
                    if self.client.conversation_data and "metadata" in self.client.conversation_data:
                        self.client.conversation_data["metadata"]["provider"] = provider
                        if model:
                            self.client.conversation_data["metadata"]["model"] = model
                    
                    # Update global config default
                    if main_config:
                        main_config.set("default_provider", provider)
                        if model:
                            main_config.set("provider_models", {**main_config.get("provider_models", {}), provider: model})
                        main_config.save_config()
                    
                    logger.info(f"Successfully switched to provider '{provider}' with model '{new_provider.config.model}'")
                    
                except Exception as e:
                    logger.error(f"Failed to switch provider: {e}", exc_info=True)
                    return {'error': f'Failed to switch provider: {str(e)}', 'status_code': 500}

            if model is not None and model != self.client.current_model_name:
                if self.client.provider.validate_model(model):
                    self.client.provider.config.model = model  # Update provider's active model
                    if self.client.conversation_data and "metadata" in self.client.conversation_data:
                        self.client.conversation_data["metadata"]["model"] = model
                    logger.debug(f"Client model updated to: {self.client.current_model_name}")
                else:
                    logger.warning(f"Model '{model}' is not valid for provider '{self.client.provider.provider_name}'. Model not changed.")
                    return {'error': f"Model '{model}' not valid for current provider.", 'status_code': 400}

            if streaming is not None:  # This updates the client's session default streaming preference
                self.client.use_streaming = streaming
                # If an active conversation exists, update its streaming_preference metadata too
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"]["streaming_preference"] = streaming
                logger.debug(f"Client session streaming preference updated to: {self.client.use_streaming}")
                # Also update global config's default streaming
                if main_config:
                    main_config.set("use_streaming", streaming)
                    main_config.save_config()

            if params is not None:
                self.client.params.update(params)  # Update client's session default params
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"].setdefault("params", {}).update(params)
                logger.debug(f"Client params updated: {self.client.params}")

            if self.client.conversation_id and self.client.conversation_data:  # Save if changes affected current conv
                self.run_async(self.client.save_conversation(quiet=True))

            # Return current effective state
            conv_meta = self.client.conversation_data.get("metadata", {}) if self.client.conversation_data else {}
            return {
                'success': True,
                'provider_name': self.client.provider.provider_name,
                'model': self.client.current_model_name,
                'streaming': conv_meta.get("streaming_preference", self.client.use_streaming),
                'params': conv_meta.get("params", self.client.params).copy(),
                'system_instruction': conv_meta.get("system_instruction", self.client.system_instruction),
            }
        except Exception as e:
            logger.error(f"Failed to update settings: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def update_conversation_system_instruction(self, conversation_id: str, new_instruction: str) -> Dict[str, Any]:
        """Updates the system instruction for a specific conversation (or current if IDs match)."""
        logger.info(f"APIHandlers: Updating system instruction for conversation ID '{conversation_id}' to: '{new_instruction[:50]}...'")
        if not self.client:
            return {'error': 'Client not initialized', 'status_code': 503}

        try:
            if self.client.conversation_id == conversation_id:
                # Update active conversation
                self.run_async(self.client.update_system_instruction(new_instruction))
                current_sys_instruct = self.client.system_instruction
            else:
                # Load the specified conversation, update its metadata, then save it.
                # This is a simplified approach. A more robust one might involve a dedicated client method.
                logger.info(f"Target conversation '{conversation_id}' is not active. Loading to update.")
                conv_file_path = self.run_async(asyncio.to_thread(self.client._find_conversation_file_by_id_or_filename, self.client.base_directory, conversation_id))
                if not conv_file_path:
                    return {'error': f"Conversation with ID '{conversation_id}' not found.", 'status_code': 404}

                loaded_conv_data = self.run_async(self.client.load_conversation_data(conv_file_path))
                if not loaded_conv_data:
                    return {'error': f"Failed to load conversation data for ID '{conversation_id}'.", 'status_code': 500}

                loaded_conv_data.setdefault("metadata", {})["system_instruction"] = new_instruction
                loaded_conv_data["metadata"]["updated_at"] = datetime.now().isoformat()

                # Save the modified non-active conversation
                title_for_save = loaded_conv_data.get("metadata", {}).get("title", "Untitled")
                self.run_async(self.client.save_conversation_data(loaded_conv_data, conversation_id, title_for_save, self.client.base_directory, quiet=False))
                current_sys_instruct = new_instruction  # The instruction that was set
                logger.info(f"System instruction for non-active conversation '{conversation_id}' updated and saved.")

            return {
                'success': True,
                'conversation_id': conversation_id,  # ID of the conversation that was updated
                'system_instruction': current_sys_instruct,
                'message': f"System instruction for conversation '{self.client.conversation_name if self.client.conversation_id == conversation_id else conversation_id}' updated."
            }
        except Exception as e:
            logger.error(f"Failed to update system instruction for conversation '{conversation_id}': {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def get_conversations(self) -> Dict[str, Any]:
        """Lists all saved conversations."""
        logger.debug("APIHandlers: Fetching conversations list.")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503, 'conversations': []}
        try:
            conversations = self.run_async(self.client.list_conversations())
            return {'conversations': conversations}
        except Exception as e:
            logger.error(f"Failed to get conversations: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500, 'conversations': []}

    def new_conversation(self, title: str = '') -> Dict[str, Any]:
        """Starts a new conversation."""
        logger.info(f"APIHandlers: Starting new conversation with title: '{title if title else '(auto-generated)'}'")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            self.run_async(self.client.start_new_conversation(title=title, is_web_ui=True))

            # After new conversation, get its state
            conv_meta = self.client.conversation_data.get("metadata", {})
            return {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': conv_meta.get("title", self.client.conversation_name),
                'history': [],  # New conversation has no stored messages yet
                'provider_name': conv_meta.get("provider", self.client.provider.provider_name if self.client.provider else 'N/A'),
                'model': conv_meta.get("model", self.client.current_model_name if self.client.provider else 'N/A'),
                'params': conv_meta.get("params", self.client.params).copy(),
                'streaming': conv_meta.get("streaming_preference", self.client.use_streaming),
                'full_message_tree': self.client.conversation_data.get("messages", {}),  # Should be empty
                'system_instruction': conv_meta.get("system_instruction", self.client.system_instruction),
            }
        except Exception as e:
            logger.error(f"Failed to create new conversation: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def load_conversation(self, conversation_identifier: str) -> Dict[str, Any]:
        """Loads an existing conversation."""
        logger.info(f"APIHandlers: Loading conversation: '{conversation_identifier}'")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            self.run_async(self.client.load_conversation(conversation_identifier))

            # After loading, get its state
            active_history = self.client.get_conversation_history()  # Actual stored messages
            conv_meta = self.client.conversation_data.get("metadata", {})
            full_tree = self.client.conversation_data.get("messages", {})

            return {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': conv_meta.get("title", "Untitled"),
                'history': active_history,
                'provider_name': conv_meta.get("provider", self.client.provider.provider_name if self.client.provider else 'N/A'),
                'model': conv_meta.get("model", self.client.current_model_name if self.client.provider else 'N/A'),
                'params': conv_meta.get("params", self.client.params).copy(),
                'streaming': conv_meta.get("streaming_preference", self.client.use_streaming),
                'full_message_tree': full_tree,
                'system_instruction': conv_meta.get("system_instruction", self.client.system_instruction),
            }
        except FileNotFoundError:  # More specific error
            logger.error(f"Conversation file for '{conversation_identifier}' not found by APIHandlers.")
            return {'error': 'Conversation file not found', 'status_code': 404}
        except Exception as e:
            logger.error(f"Failed to load conversation '{conversation_identifier}': {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def save_conversation(self) -> Dict[str, Any]:
        """Saves the currently active conversation."""
        logger.info("APIHandlers: Saving current conversation.")
        if not self.client or not self.client.conversation_id or not self.client.conversation_data:
            return {'error': 'No active conversation to save', 'status_code': 400}
        try:
            self.run_async(self.client.save_conversation())
            title = self.client.conversation_data.get("metadata", {}).get("title", "Untitled")
            return {'success': True, 'message': f"Conversation '{title}' saved."}
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def _find_conv_file(self, conv_id_or_name: str) -> Optional[Path]:
        """Helper to find conversation file path (synchronous part)."""
        if not self.client or not self.client.base_directory: return None
        # This is a synchronous call, run it in a thread from async context
        return self.client._find_conversation_file_by_id_or_filename(self.client.base_directory, conv_id_or_name)

    def duplicate_conversation(self, conversation_id_to_duplicate: str, new_title: str) -> Dict[str, Any]:
        """Duplicates an existing conversation with a new title and ID."""
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        logger.info(f"APIHandlers: Duplicating conversation ID/File: {conversation_id_to_duplicate} to new title: '{new_title}'")
        try:
            # _find_conv_file is sync, so run in thread
            original_filepath = self.run_async(asyncio.to_thread(self._find_conv_file, conversation_id_to_duplicate))
            if not original_filepath or not original_filepath.exists():
                return {'error': 'Original conversation file not found', 'status_code': 404}

            with open(original_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            new_conv_id_str = self.client.generate_conversation_id()  # New unique ID
            data['conversation_id'] = new_conv_id_str  # Update ID in duplicated data

            data.setdefault('metadata', {})
            data['metadata']['title'] = new_title
            now_iso = datetime.now().isoformat()
            data['metadata']['created_at'] = now_iso  # New creation time for duplicate
            data['metadata']['updated_at'] = now_iso
            # Keep original provider, model, params, system_instruction unless specified otherwise
            data['metadata']['provider'] = data['metadata'].get('provider', self.client.provider.provider_name if self.client.provider else "unknown")
            data['metadata']['model'] = data['metadata'].get('model', self.client.current_model_name if self.client.provider else "unknown")
            # System instruction is already in metadata if present, will be copied.

            new_filename_str = self.client.format_filename(new_title, new_conv_id_str)
            new_filepath = self.client.base_directory / new_filename_str

            with open(new_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            return {'success': True, 'new_conversation_id': new_conv_id_str, 'new_title': new_title, 'new_filename': new_filename_str}
        except Exception as e:
            logger.error(f"Error duplicating conversation: {e}", exc_info=True)
            return {'error': f'Server error during duplication: {str(e)}', 'status_code': 500}

    def rename_conversation(self, conversation_id_or_filename_to_rename: str, new_title: str) -> Dict[str, Any]:
        """Renames an existing conversation."""
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        logger.info(f"APIHandlers: Renaming conversation ID/File: {conversation_id_or_filename_to_rename} to new title: '{new_title}'")
        try:
            original_filepath = self.run_async(asyncio.to_thread(self._find_conv_file, conversation_id_or_filename_to_rename))
            if not original_filepath or not original_filepath.exists():
                return {'error': 'Conversation file not found for renaming', 'status_code': 404}

            with open(original_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            actual_conversation_id = data.get('conversation_id')
            if not actual_conversation_id:
                return {'error': 'Internal error: Conversation ID missing from file', 'status_code': 500}

            data.setdefault('metadata', {})
            data['metadata']['title'] = new_title
            data['metadata']['updated_at'] = datetime.now().isoformat()

            # Save changes back to the *original file path first* if filename doesn't change
            # Then, rename the file if the title change implies a filename change.
            with open(original_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            new_filename_str = self.client.format_filename(new_title, actual_conversation_id)
            new_filepath = self.client.base_directory / new_filename_str

            if original_filepath != new_filepath:
                try:
                    os.rename(original_filepath, new_filepath)
                    logger.info(f"Renamed file from {original_filepath.name} to {new_filepath.name}")
                except OSError as e_os:
                    logger.error(f"Error renaming file from {original_filepath} to {new_filepath}: {e_os}")
                    # If rename fails, the content is updated but filename might be old. This is a partial success.
                    return {'error': f'Content updated, but failed to rename file: {e_os}', 'status_code': 500, 'partial_success': True, 'conversation_id': actual_conversation_id, 'new_title': new_title}

            # If renaming the active conversation, update client's current name
            if self.client.conversation_id == actual_conversation_id:
                self.client.conversation_name = new_title
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"]["title"] = new_title

            return {'success': True, 'conversation_id': actual_conversation_id, 'new_title': new_title, 'new_filename': new_filename_str}
        except Exception as e:
            logger.error(f"Error renaming conversation: {e}", exc_info=True)
            return {'error': f'Server error during rename: {str(e)}', 'status_code': 500}

    def delete_conversation(self, conversation_id_or_filename_to_delete: str) -> Dict[str, Any]:
        """Deletes an existing conversation file."""
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        logger.info(f"APIHandlers: Deleting conversation ID/File: {conversation_id_or_filename_to_delete}")
        try:
            filepath_to_delete = self.run_async(asyncio.to_thread(self._find_conv_file, conversation_id_or_filename_to_delete))
            if not filepath_to_delete or not filepath_to_delete.exists():
                return {'error': 'Conversation file not found for deletion', 'status_code': 404}

            # Try to get the actual conversation_id from the file before deleting
            actual_conv_id_from_file = conversation_id_or_filename_to_delete  # Fallback
            try:
                with open(filepath_to_delete, 'r', encoding='utf-8') as f_read:
                    data_read = json.load(f_read)
                    actual_conv_id_from_file = data_read.get('conversation_id', actual_conv_id_from_file)
            except Exception:  # Ignore if can't read ID, proceed with deletion
                pass

            os.remove(filepath_to_delete)
            logger.info(f"Deleted conversation file: {filepath_to_delete.name}")

            return {'success': True, 'deleted_conversation_id': actual_conv_id_from_file}
        except Exception as e:
            logger.error(f"Error deleting conversation: {e}", exc_info=True)
            return {'error': f'Server error during deletion: {str(e)}', 'status_code': 500}

    def send_message(self, message_content: str) -> Dict[str, Any]:
        """Handles a non-streaming message send request."""
        logger.debug(f"APIHandlers: Handling non-streaming send for: '{message_content[:50]}...'")
        if not self.client or not self.client.provider:
            return {'error': 'Client or provider not initialized', 'status_code': 503}

        try:
            # GUI client should call client.add_user_message() before this to set current_user_message_id
            # This method assumes current_user_message_id is set.
            if not self.client.current_user_message_id:
                logger.warning("APIHandlers.send_message called but client.current_user_message_id is not set. User message might not be correctly parented.")
                # For robustness, add it now if it wasn't, though GUI flow should handle this.
                self.client.add_user_message(message_content)

            response_text, token_usage_dict = self.run_async(self.client.get_response())

            if response_text is None and token_usage_dict is None:  # Indicates provider error from client.get_response
                logger.error("AI client's get_response returned None for text and token_usage, likely provider error.")
                error_detail = "Provider returned no data or an error occurred during generation."
                return {'error': error_detail, 'status_code': 500}

            # client.get_response() internally calls add_assistant_message if successful
            # We need the ID of the assistant message that was just added by get_response
            # This assumes get_response updates the conversation_data and active_leaf correctly.

            assistant_message_id = self.client._get_last_message_id(
                self.client.conversation_data,
                self.client.active_branch
            )
            # The parent of this assistant message is the user message ID that was being processed
            user_message_id_for_parenting = self.client.conversation_data["messages"].get(assistant_message_id, {}).get("parent_id") if assistant_message_id else self.client.current_user_message_id

            # Save conversation after successful response
            self.run_async(self.client.save_conversation(quiet=True))

            return {
                'response': response_text,
                'conversation_id': self.client.conversation_id,
                'message_id': assistant_message_id,  # ID of the AI's response message
                'parent_id': user_message_id_for_parenting,  # ID of the user message it's responding to
                'provider_name': self.client.provider.provider_name,
                'model': self.client.current_model_name,
                'token_usage': token_usage_dict or {}
            }
        except Exception as e:
            logger.error(f"Failed in APIHandlers send_message (non-streaming): {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    async def stream_message(self, message_content: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Handles a streaming message send request."""
        logger.debug(f"APIHandlers: Initiating stream for message (content already added by client.add_user_message): '{message_content[:50]}...'")
        if not self.client or not self.client.provider:
            yield {"error": "Client or provider not initialized in APIHandlers."}
            return

        # Ensure current_user_message_id is set (GUI should call client.add_user_message first)
        if not self.client.current_user_message_id:
            logger.warning("APIHandlers.stream_message called but client.current_user_message_id is not set. Adding user message now.")
            # This is a fallback. Ideally, the route handler ensures add_user_message is called.
            self.client.add_user_message(message_content)  # This is a sync call, ensure it's safe in async context or refactor add_user_message
            if not self.client.current_user_message_id:  # If still not set
                yield {"error": "Failed to process user message before streaming."};
                return

        try:
            async for data_event in self.client.get_streaming_response():
                yield data_event  # Yield each event from the client's streaming method
                if data_event.get("error") or data_event.get("done"):
                    break  # Stop if error or done signal received
            logger.debug("APIHandlers: Streaming finished.")
        except Exception as e:
            logger.error(f"Streaming error in APIHandlers.stream_message: {e}", exc_info=True)
            yield {"error": f"API Handler streaming error: {str(e)}"}

    def retry_message(self, assistant_message_id_to_retry: str) -> Dict[str, Any]:
        """Retries generating an assistant message, creating a new branch."""
        logger.info(f"APIHandlers: Retrying assistant message: {assistant_message_id_to_retry}")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            retry_result_dict = self.run_async(self.client.retry_message(assistant_message_id_to_retry))

            # After retry, client's active branch/leaf and history are updated.
            current_active_history = self.client.get_conversation_history()  # Stored messages
            current_full_tree = self.client.conversation_data.get("messages", {})
            conv_meta = self.client.conversation_data.get("metadata", {})

            return {
                'success': True,
                'message': retry_result_dict.get('message', {}),  # The new AI message object
                'sibling_index': retry_result_dict.get('sibling_index', -1),
                'total_siblings': retry_result_dict.get('total_siblings', 0),
                'history': current_active_history,
                'conversation_id': self.client.conversation_id,
                'conversation_name': conv_meta.get("title"),
                'full_message_tree': current_full_tree,
                'system_instruction': conv_meta.get("system_instruction", self.client.system_instruction),
            }
        except Exception as e:
            logger.error(f"Failed to retry message {assistant_message_id_to_retry}: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def navigate_sibling(self, message_id: str, direction: str) -> Dict[str, Any]:
        """Navigates to a sibling (alternative) AI response."""
        logger.info(f"APIHandlers: Navigating {direction} from message: {message_id}")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            nav_result_dict = self.run_async(self.client.switch_to_sibling(message_id, direction))

            current_active_history = self.client.get_conversation_history()  # Stored messages
            current_full_tree = self.client.conversation_data.get("messages", {})
            conv_meta = self.client.conversation_data.get("metadata", {})

            return {
                'success': True,
                'message': nav_result_dict.get('message', {}),  # The new active AI message
                'sibling_index': nav_result_dict.get('sibling_index', -1),
                'total_siblings': nav_result_dict.get('total_siblings', 0),
                'history': current_active_history,
                'conversation_id': self.client.conversation_id,
                'conversation_name': conv_meta.get("title"),
                'full_message_tree': current_full_tree,
                'system_instruction': conv_meta.get("system_instruction", self.client.system_instruction),
            }
        except Exception as e:
            logger.error(f"Failed to navigate sibling for {message_id} ({direction}): {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def get_message_info(self, message_id: str) -> Dict[str, Any]:
        """Gets detailed information about a specific message and its siblings."""
        logger.debug(f"APIHandlers: Getting info for message: {message_id}")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            # get_message_siblings now returns more comprehensive info
            sibling_info_dict = self.run_async(self.client.get_message_siblings(message_id))

            messages_dict = self.client.conversation_data.get("messages", {}) if self.client.conversation_data else {}
            message_data = messages_dict.get(message_id, {})
            if not message_data:
                return {'error': f"Message {message_id} not found in conversation data", 'status_code': 404}

            return {
                'success': True,
                'message_data': message_data,  # The target message's own data
                'parent_id': sibling_info_dict.get('parent_id'),
                'sibling_ids': sibling_info_dict.get('siblings', []),  # IDs of all siblings (including self if assistant)
                'current_index_in_siblings': sibling_info_dict.get('current_index', -1),  # Index of target_msg among its siblings
                'total_siblings': sibling_info_dict.get('total', 0)
            }
        except Exception as e:
            logger.error(f"Failed to get message info for {message_id}: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def get_conversation_tree(self) -> Dict[str, Any]:
        """Gets the full message tree structure for the current conversation."""
        logger.debug("APIHandlers: Getting full conversation tree.")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            tree_data = self.run_async(self.client.get_conversation_tree())  # client method returns nodes, edges, metadata
            return {'success': True, **tree_data}  # Spread the dict from client
        except Exception as e:
            logger.error(f"Failed to get conversation tree: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def execute_command(self, command_str: str) -> Dict[str, Any]:
        """Executes a text command, primarily for CLI-like interactions if GUI uses it."""
        logger.info(f"APIHandlers: Executing command: '{command_str}'")
        if not self.client or not self.command_handler:
            return {'error': 'Client or command handler not initialized', 'status_code': 503}

        try:
            # Command handler logic needs to be async-aware if calling async client methods
            # For simplicity, assuming command_handler's methods are designed to be run via self.run_async if they are async

            # This part needs careful review based on CommandHandler implementation
            # For now, let's map common commands to their API handler methods for structured responses.
            parts = command_str.lower().split(maxsplit=1)
            cmd_name = parts[0]
            cmd_args = parts[1] if len(parts) > 1 else ""

            if cmd_name == '/new':
                return self.new_conversation(title=cmd_args)
            elif cmd_name == '/load':
                if not cmd_args: return {'error': 'Specify conversation name/ID/number to load', 'status_code': 400}
                return self.load_conversation(cmd_args)
            elif cmd_name == '/save':
                return self.save_conversation()
            elif cmd_name == '/list':
                convos = self.get_conversations()  # This already returns a dict with 'conversations'
                return {'success': True, 'message': 'Conversations list refreshed.', **convos}
            elif cmd_name == '/model':
                if cmd_args:
                    return self.update_settings(model=cmd_args)  # update_settings returns full state
                else:
                    return self.get_models()  # get_models returns models and current provider
            elif cmd_name == '/stream':  # Toggles client's session default streaming
                # update_settings handles the logic for toggling self.client.use_streaming
                # and saving to global config.
                current_streaming_pref = self.client.conversation_data.get("metadata", {}).get("streaming_preference", self.client.use_streaming)
                response = self.update_settings(streaming=not current_streaming_pref)
                new_streaming_status = self.client.conversation_data.get("metadata", {}).get("streaming_preference", self.client.use_streaming)
                response['message'] = f"Session and conversation streaming preference set to {'ON' if new_streaming_status else 'OFF'}."
                return response
            # Add other command mappings as needed.
            # The original CommandHandler might be more for CLI direct actions.
            # For GUI, it's better to have dedicated API handler methods.

            logger.warning(f"Command '{cmd_name}' not directly mapped in APIHandlers.execute_command for rich response. Falling back to CommandHandler (if implemented).")
            # Fallback to generic command handler if one exists and is appropriate
            # result = self.run_async(self.command_handler.handle_command_async(command_str)) # Example
            # return {'success': True, 'message': 'Command processed by generic handler.', 'details': result}
            return {'error': f"Command '{cmd_name}' not fully supported via this API route for structured GUI response.", 'status_code': 400}

        except Exception as e:
            logger.error(f"Failed to execute command '{command_str}': {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}
