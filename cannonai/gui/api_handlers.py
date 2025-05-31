#!/usr/bin/env python3
"""
CannonAI GUI - API Handlers

This module contains the business logic for handling API requests,
separating concerns from the Flask routing layer.
It interacts with the AsyncClient for core AI and conversation management.
"""

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, AsyncGenerator, Tuple, List
from datetime import datetime

# Assuming these are in the parent directory or accessible via sys.path
from async_client import AsyncClient  # Uses the refactored AsyncClient
from command_handler import CommandHandler
from base_client import Colors
from config import Config  # To potentially access global config if needed

# Set up logging
logger = logging.getLogger("cannonai.gui.api_handlers")

# Global reference to be set by server.py, allowing API handlers to access the main app config
# This is one way to provide config access; dependency injection or app context are others.
main_config: Optional[Config] = None


class APIHandlers:
    """Handles API business logic for the GUI server"""

    def __init__(self, client: AsyncClient, command_handler: CommandHandler, event_loop: asyncio.AbstractEventLoop):
        self.client = client
        self.command_handler = command_handler
        self.event_loop = event_loop
        # self.main_config can be set externally if needed, e.g. by server.py
        # For now, operations will try to use client's config or passed-in config.
        if self.client and self.client.provider:
            logger.info(f"APIHandlers initialized with client for provider: {self.client.provider.provider_name}.")
        elif self.client:
            logger.warning("APIHandlers initialized with a client, but client has no provider set.")
        else:
            logger.warning("APIHandlers initialized WITHOUT a client instance.")

    def run_async(self, coro, timeout=60):
        """
        Run an async coroutine in the event loop from a synchronous context
        and return its result.
        """
        if not self.event_loop or self.event_loop.is_closed():
            logger.error("Event loop for APIHandlers is not running or closed.")
            try:
                # Attempt to get the currently running loop in this thread context
                # This might be the Flask's default loop if not managed carefully
                running_loop = asyncio.get_running_loop()
                if running_loop.is_running():
                    self.event_loop = running_loop
                    logger.info("Re-acquired running event loop for APIHandlers.")
                else:  # Should not happen if get_running_loop() succeeded
                    raise RuntimeError("Acquired loop is not running.")
            except RuntimeError:  # No running loop in current context
                logger.error("No running asyncio event loop found for APIHandlers to run coroutine.")
                raise RuntimeError("APIHandlers: Cannot execute async task without a running event loop.")

        if not self.event_loop.is_running():
            # This case implies the loop exists but isn't active, which is problematic for run_coroutine_threadsafe
            logger.error("APIHandlers: Event loop exists but is not running. Cannot schedule coroutine.")
            raise RuntimeError("APIHandlers: Event loop is not running.")

        future = asyncio.run_coroutine_threadsafe(coro, self.event_loop)
        try:
            return future.result(timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Async operation in APIHandlers timed out after {timeout} seconds.")
            raise
        except Exception as e:
            logger.error(f"Exception in APIHandlers async operation: {e}", exc_info=True)
            raise

    # --- Status and Configuration ---

    def get_status(self) -> Dict[str, Any]:
        """Get current client status, including active conversation details."""
        if not self.client or not self.client.provider:
            return {'connected': False, 'error': 'Client or provider not initialized'}

        conv_data = self.client.conversation_data if hasattr(self.client, 'conversation_data') else {}
        metadata = conv_data.get("metadata", {})

        active_branch_history = []
        current_messages_tree = {}

        if self.client.conversation_id and conv_data:
            try:
                # get_conversation_history is synchronous on AsyncClient after refactor
                active_branch_history = self.client.get_conversation_history()
                current_messages_tree = conv_data.get("messages", {})
            except Exception as e:
                logger.error(f"Error getting history/tree for status: {e}", exc_info=True)
                active_branch_history = [{"role": "system", "content": f"Error loading history: {e}"}]

        return {
            'connected': self.client.provider.is_initialized,
            'provider_name': self.client.provider.provider_name,
            'model': self.client.current_model_name,
            'streaming': self.client.use_streaming,
            'conversation_id': self.client.conversation_id,
            'conversation_name': metadata.get("title", getattr(self.client, 'conversation_name', 'New Conversation')),
            'params': metadata.get("params", self.client.params).copy(),
            'history': active_branch_history,
            'full_message_tree': current_messages_tree
        }

    def get_models(self) -> Dict[str, Any]:
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
                        streaming: Optional[bool] = None,
                        params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info(f"APIHandlers: Updating settings - Provider: {provider}, Model: {model}, Streaming: {streaming}, Params: {params}")
        if not self.client or not self.client.provider:
            return {'error': 'Client or provider not initialized', 'status_code': 503}
        try:
            global main_config  # Access the global config from server.py

            if provider and provider != self.client.provider.provider_name:
                logger.warning(f"Provider change requested to '{provider}'. This requires client re-initialization by the server. Updating config default for next startup.")
                if main_config_for_gui:
                    main_config_for_gui.set("default_provider", provider)
                    # To change model for the new provider, we'd also need to set it in config.
                    # For now, just changing default provider. Model for new provider will be its default from config.
                    new_provider_default_model = main_config_for_gui.get_default_model_for_provider(provider)
                    if new_provider_default_model:
                        main_config_for_gui.set("provider_models", {**main_config_for_gui.get("provider_models", {}), provider: new_provider_default_model})

                    main_config_for_gui.save_config()
                    # The actual switch needs a server restart or a more dynamic client manager interaction.
                    # For now, return current state but acknowledge request.
                    return {
                        'success': False,  # Indicate switch didn't happen live
                        'message': f"Default provider changed to {provider}. Restart GUI for changes to take full effect.",
                        'provider_name': self.client.provider.provider_name,
                        'model': self.client.current_model_name,
                        # ... other current settings
                    }
                else:
                    logger.error("main_config_for_gui not available in APIHandlers to update default provider.")

            if model is not None and model != self.client.current_model_name:
                # Validate if model is compatible with current provider
                if self.client.provider.validate_model(model):
                    self.client.provider.config.model = model
                    if self.client.conversation_data and "metadata" in self.client.conversation_data:
                        self.client.conversation_data["metadata"]["model"] = model
                    logger.debug(f"Client model updated to: {self.client.current_model_name}")
                else:
                    logger.warning(f"Model '{model}' is not valid for provider '{self.client.provider.provider_name}'. Model not changed.")
                    return {'error': f"Model '{model}' not valid for current provider.", 'status_code': 400}

            if streaming is not None:
                self.client.use_streaming = streaming
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"]["streaming_preference"] = streaming
                logger.debug(f"Client streaming preference updated to: {self.client.use_streaming}")

            if params is not None:
                self.client.params.update(params)
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"].setdefault("params", {}).update(params)
                logger.debug(f"Client params updated: {self.client.params}")

            if self.client.conversation_id and self.client.conversation_data:
                self.run_async(self.client.save_conversation(quiet=True))

            return {
                'success': True,
                'provider_name': self.client.provider.provider_name,
                'model': self.client.current_model_name,
                'streaming': self.client.use_streaming,
                'params': self.client.params.copy()
            }
        except Exception as e:
            logger.error(f"Failed to update settings: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def get_conversations(self) -> Dict[str, Any]:
        logger.debug("APIHandlers: Fetching conversations list.")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            conversations = self.run_async(self.client.list_conversations())
            return {'conversations': conversations}
        except Exception as e:
            logger.error(f"Failed to get conversations: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def new_conversation(self, title: str = '') -> Dict[str, Any]:
        logger.info(f"APIHandlers: Starting new conversation with title: '{title if title else '(auto-generated)'}'")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            self.run_async(self.client.start_new_conversation(title=title, is_web_ui=True))
            metadata = self.client.conversation_data.get("metadata", {})
            return {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': metadata.get("title", self.client.conversation_name),
                'history': [],
                'provider_name': metadata.get("provider", self.client.provider.provider_name if self.client.provider else 'N/A'),
                'model': metadata.get("model", self.client.current_model_name if self.client.provider else 'N/A'),
                'params': metadata.get("params", self.client.params).copy(),
                'streaming': self.client.use_streaming,
                'full_message_tree': self.client.conversation_data.get("messages", {})
            }
        except Exception as e:
            logger.error(f"Failed to create new conversation: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def load_conversation(self, conversation_identifier: str) -> Dict[str, Any]:
        logger.info(f"APIHandlers: Loading conversation: '{conversation_identifier}'")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            self.run_async(self.client.load_conversation(conversation_identifier))
            # After loading, client's provider/model might have been updated by load_conversation logic
            active_history = self.client.get_conversation_history()  # This is sync
            metadata = self.client.conversation_data.get("metadata", {})
            full_tree = self.client.conversation_data.get("messages", {})
            return {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': metadata.get("title", "Untitled"),
                'history': active_history,
                'provider_name': metadata.get("provider", self.client.provider.provider_name if self.client.provider else 'N/A'),
                'model': metadata.get("model", self.client.current_model_name if self.client.provider else 'N/A'),
                'params': metadata.get("params", self.client.params).copy(),
                'streaming': metadata.get("streaming_preference", self.client.use_streaming),
                'full_message_tree': full_tree
            }
        except FileNotFoundError:
            logger.error(f"Conversation file for '{conversation_identifier}' not found.")
            return {'error': 'Conversation file not found', 'status_code': 404}
        except Exception as e:
            logger.error(f"Failed to load conversation '{conversation_identifier}': {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def save_conversation(self) -> Dict[str, Any]:
        logger.info("APIHandlers: Saving current conversation.")
        if not self.client or not self.client.conversation_id:
            return {'error': 'No active conversation to save', 'status_code': 400}
        try:
            self.run_async(self.client.save_conversation())
            title = self.client.conversation_data.get("metadata", {}).get("title", "Untitled")
            return {'success': True, 'message': f"Conversation '{title}' saved."}
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def _find_conv_file(self, conv_id_or_name: str) -> Optional[Path]:
        """Helper to find conversation file path. (Synchronous part)"""
        if not self.client or not self.client.conversations_dir: return None
        # This is a simplified version. AsyncClient has a more robust _find_conversation_file_by_id_or_filename
        # that reads metadata. For APIHandlers, we might need to call that via run_async if exact matching is needed.
        # For now, assume conv_id_or_name might be a direct filename or requires listing.
        # This is a placeholder, ideally use client's method.
        files = list(self.client.conversations_dir.glob("*.json"))
        for f_path in files:
            if conv_id_or_name in f_path.name:  # Simple check
                return f_path
            try:  # Try reading ID from file
                with open(f_path, 'r') as f_content:
                    data = json.load(f_content)
                    if data.get("conversation_id") == conv_id_or_name:
                        return f_path
            except:
                continue
        return None

    def duplicate_conversation(self, conversation_id_to_duplicate: str, new_title: str) -> Dict[str, Any]:
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        logger.info(f"APIHandlers: Duplicating conversation ID/File: {conversation_id_to_duplicate} to new title: '{new_title}'")
        try:
            original_filepath = self.run_async(asyncio.to_thread(self.client._find_conversation_file_by_id_or_filename, conversation_id_to_duplicate))
            if not original_filepath or not original_filepath.exists():
                return {'error': 'Original conversation file not found', 'status_code': 404}

            with open(original_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            new_conv_id_str = self.client.generate_conversation_id()  # Sync method from base
            data['conversation_id'] = new_conv_id_str
            if 'metadata' not in data: data['metadata'] = {}
            data['metadata']['title'] = new_title
            now_iso = datetime.now().isoformat()
            data['metadata']['created_at'] = now_iso
            data['metadata']['updated_at'] = now_iso
            data['metadata']['provider'] = data['metadata'].get('provider', self.client.provider.provider_name if self.client.provider else "unknown")
            data['metadata']['model'] = data['metadata'].get('model', self.client.current_model_name if self.client.provider else "unknown")

            new_filename_str = self.client.format_filename(new_title, new_conv_id_str)  # Sync method from base
            new_filepath = self.client.conversations_dir / new_filename_str
            with open(new_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            return {'success': True, 'new_conversation_id': new_conv_id_str, 'new_title': new_title, 'new_filename': new_filename_str}
        except Exception as e:
            logger.error(f"Error duplicating conversation: {e}", exc_info=True)
            return {'error': f'Server error: {str(e)}', 'status_code': 500}

    def rename_conversation(self, conversation_id_or_filename_to_rename: str, new_title: str) -> Dict[str, Any]:
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        logger.info(f"APIHandlers: Renaming conversation ID/File: {conversation_id_or_filename_to_rename} to new title: '{new_title}'")
        try:
            original_filepath = self.run_async(asyncio.to_thread(self.client._find_conversation_file_by_id_or_filename, conversation_id_or_filename_to_rename))
            if not original_filepath or not original_filepath.exists():
                return {'error': 'Conversation file not found for renaming', 'status_code': 404}

            with open(original_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            actual_conversation_id = data.get('conversation_id')
            if not actual_conversation_id: return {'error': 'Internal error: Conversation ID missing', 'status_code': 500}

            if 'metadata' not in data: data['metadata'] = {}
            data['metadata']['title'] = new_title
            data['metadata']['updated_at'] = datetime.now().isoformat()

            with open(original_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            new_filename_str = self.client.format_filename(new_title, actual_conversation_id)  # Sync
            new_filepath = self.client.conversations_dir / new_filename_str
            if original_filepath != new_filepath:
                os.rename(original_filepath, new_filepath)  # This is sync

            return {'success': True, 'conversation_id': actual_conversation_id, 'new_title': new_title, 'new_filename': new_filename_str}
        except Exception as e:
            logger.error(f"Error renaming conversation: {e}", exc_info=True)
            return {'error': f'Server error: {str(e)}', 'status_code': 500}

    def delete_conversation(self, conversation_id_or_filename_to_delete: str) -> Dict[str, Any]:
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        logger.info(f"APIHandlers: Deleting conversation ID/File: {conversation_id_or_filename_to_delete}")
        try:
            filepath_to_delete = self.run_async(asyncio.to_thread(self.client._find_conversation_file_by_id_or_filename, conversation_id_or_filename_to_delete))
            if not filepath_to_delete or not filepath_to_delete.exists():
                return {'error': 'Conversation file not found for deletion', 'status_code': 404}

            actual_conv_id = conversation_id_or_filename_to_delete
            try:
                with open(filepath_to_delete, 'r', encoding='utf-8') as f_read:
                    data_read = json.load(f_read)
                    actual_conv_id = data_read.get('conversation_id', actual_conv_id)
            except Exception:
                pass

            os.remove(filepath_to_delete)  # Sync

            return {'success': True, 'deleted_conversation_id': actual_conv_id}
        except Exception as e:
            logger.error(f"Error deleting conversation: {e}", exc_info=True)
            return {'error': f'Server error: {str(e)}', 'status_code': 500}

    # --- Message Interaction ---

    def send_message(self, message_content: str) -> Dict[str, Any]:
        logger.debug(f"APIHandlers: Handling non-streaming send for: '{message_content[:50]}...'")
        if not self.client or not self.client.provider: return {'error': 'Client or provider not initialized', 'status_code': 503}
        try:
            # client.add_user_message is sync, called by Flask route before this.
            # client.get_response is async.
            response_text, token_usage_dict = self.run_async(self.client.get_response())

            if response_text is None and token_usage_dict is None:
                raise Exception("AI client's get_response failed to return valid data.")

            # client.add_assistant_message is sync, called after getting response.
            self.client.add_assistant_message(response_text, token_usage_dict)

            assistant_message_id = self.client._get_last_message_id(self.client.active_branch)  # Sync
            user_message_id_for_parenting = self.client.conversation_data["messages"][assistant_message_id]["parent_id"]  # Sync

            self.run_async(self.client.save_conversation(quiet=True))

            return {
                'response': response_text,
                'conversation_id': self.client.conversation_id,
                'message_id': assistant_message_id,
                'parent_id': user_message_id_for_parenting,
                'provider_name': self.client.provider.provider_name,
                'model': self.client.current_model_name,
                'token_usage': token_usage_dict or {}
            }
        except Exception as e:
            logger.error(f"Failed in APIHandlers send_message (non-streaming): {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    async def stream_message(self, message_content: str) -> AsyncGenerator[Dict[str, Any], None]:
        # message_content is passed but client.add_user_message should have already been called by the Flask route
        logger.debug(f"APIHandlers: Initiating stream for message (content already added): '{message_content[:50]}...'")
        if not self.client or not self.client.provider:
            yield {"error": "Client or provider not initialized in APIHandlers."};
            return
        try:
            # AsyncClient.get_streaming_response is the actual async generator
            async for data_event in self.client.get_streaming_response():
                yield data_event  # No need to format as SSE here, just yield the dicts
                if data_event.get("error") or data_event.get("done"):
                    break  # Stop this generator if provider stream signals error or completion
            logger.debug("APIHandlers: Streaming finished.")
        except Exception as e:
            logger.error(f"Streaming error in APIHandlers.stream_message: {e}", exc_info=True)
            yield {"error": str(e)}

    def retry_message(self, assistant_message_id_to_retry: str) -> Dict[str, Any]:
        logger.info(f"APIHandlers: Retrying assistant message: {assistant_message_id_to_retry}")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            retry_result_dict = self.run_async(self.client.retry_message(assistant_message_id_to_retry))
            current_active_history = self.client.get_conversation_history()  # Sync
            current_full_tree = self.client.conversation_data.get("messages", {})
            return {
                'success': True, 'message': retry_result_dict['message'],
                'sibling_index': retry_result_dict['sibling_index'],
                'total_siblings': retry_result_dict['total_siblings'],
                'history': current_active_history, 'conversation_id': self.client.conversation_id,
                'conversation_name': self.client.conversation_data.get("metadata", {}).get("title"),
                'full_message_tree': current_full_tree
            }
        except Exception as e:
            logger.error(f"Failed to retry message {assistant_message_id_to_retry}: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def navigate_sibling(self, message_id: str, direction: str) -> Dict[str, Any]:
        logger.info(f"APIHandlers: Navigating {direction} from message: {message_id}")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            nav_result_dict = self.run_async(self.client.switch_to_sibling(message_id, direction))
            current_active_history = self.client.get_conversation_history()  # Sync
            current_full_tree = self.client.conversation_data.get("messages", {})
            return {
                'success': True, 'message': nav_result_dict['message'],
                'sibling_index': nav_result_dict['sibling_index'],
                'total_siblings': nav_result_dict['total_siblings'],
                'history': current_active_history, 'conversation_id': self.client.conversation_id,
                'conversation_name': self.client.conversation_data.get("metadata", {}).get("title"),
                'full_message_tree': current_full_tree
            }
        except Exception as e:
            logger.error(f"Failed to navigate sibling for {message_id} ({direction}): {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def get_message_info(self, message_id: str) -> Dict[str, Any]:
        logger.debug(f"APIHandlers: Getting info for message: {message_id}")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            sibling_info_dict = self.run_async(self.client.get_message_siblings(message_id))
            messages_dict = self.client.conversation_data.get("messages", {})
            message_data = messages_dict.get(message_id, {})
            if not message_data:
                return {'error': f"Message {message_id} not found", 'status_code': 404}
            return {
                'success': True, 'message': message_data,
                'siblings': sibling_info_dict['siblings'],
                'current_index': sibling_info_dict['current_index'],
                'total_siblings': sibling_info_dict['total']
            }
        except Exception as e:
            logger.error(f"Failed to get message info for {message_id}: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def get_conversation_tree(self) -> Dict[str, Any]:
        logger.debug("APIHandlers: Getting full conversation tree.")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            tree_data = self.run_async(self.client.get_conversation_tree())
            return {'success': True, 'tree': tree_data}
        except Exception as e:
            logger.error(f"Failed to get conversation tree: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def execute_command(self, command_str: str) -> Dict[str, Any]:
        logger.info(f"APIHandlers: Executing command: '{command_str}'")
        if not self.client or not self.command_handler:
            return {'error': 'Client or command handler not initialized', 'status_code': 503}

        try:
            parts = command_str.lower().split(maxsplit=1)
            cmd_name = parts[0]
            cmd_args = parts[1] if len(parts) > 1 else ""

            if cmd_name == '/new': return self.new_conversation(title=cmd_args)
            if cmd_name == '/load': return self.load_conversation(cmd_args) if cmd_args else {'error': 'Specify conversation name/ID', 'status_code': 400}
            if cmd_name == '/save': return self.save_conversation()
            if cmd_name == '/list':
                convos = self.get_conversations()
                return {'success': True, 'message': 'Conversations list refreshed.', 'conversations': convos.get('conversations')}
            if cmd_name == '/model':
                if cmd_args:  # Request to change model
                    return self.update_settings(model=cmd_args)
                else:  # Request to list models
                    return self.get_models()
            if cmd_name == '/stream':
                return self.update_settings(streaming=not self.client.use_streaming if self.client else False)

            # For other commands, could use command_handler if it's designed for structured output
            # For now, only specific mapped commands are fully supported for rich JSON response.
            # handler_result = self.run_async(self.command_handler.async_handle_command(command_str))
            # return {'success': True, 'message': f"Command '{command_str}' processed.", 'handler_output': str(handler_result), **self.get_status()}

            logger.warning(f"Command '{cmd_name}' not directly mapped in APIHandlers.execute_command for rich response.")
            return {'error': f"Command '{cmd_name}' not directly supported via this API endpoint for structured response.", 'status_code': 400}

        except Exception as e:
            logger.error(f"Failed to execute command '{command_str}': {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}
