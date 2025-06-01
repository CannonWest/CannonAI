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

        # Get current system instruction for the active conversation, or global default
        current_system_instruction = metadata.get(
            "system_instruction",
            main_config.get("default_system_instruction", Config.DEFAULT_SYSTEM_INSTRUCTION) if main_config else Config.DEFAULT_SYSTEM_INSTRUCTION
        )

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
            'full_message_tree': current_messages_tree,
            'system_instruction': current_system_instruction,
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
                        params: Optional[Dict[str, Any]] = None,
                        system_instruction: Optional[str] = None) -> Dict[str, Any]:
        logger.info(f"APIHandlers: Updating settings - Provider: {provider}, Model: {model}, Streaming: {streaming}, Params: {params}, SystemInstruction: {system_instruction is not None}")
        if not self.client or not self.client.provider:
            return {'error': 'Client or provider not initialized', 'status_code': 503}
        try:
            global main_config  # Access the global config from server.py
            # Accessing main_config_for_gui from server.py context for saving global defaults
            from gui.server import main_config_for_gui as server_main_config

            if provider and provider != self.client.provider.provider_name:
                logger.warning(f"Provider change requested to '{provider}'. This requires client re-initialization by the server. Updating config default for next startup.")
                if server_main_config:
                    server_main_config.set("default_provider", provider)
                    new_provider_default_model = server_main_config.get_default_model_for_provider(provider)
                    if new_provider_default_model:
                        server_main_config.set("provider_models", {**server_main_config.get("provider_models", {}), provider: new_provider_default_model})
                    server_main_config.save_config()  # Save global config change
                    return {
                        'success': False,
                        'message': f"Default provider changed to {provider}. Restart GUI for changes to take full effect.",
                        'provider_name': self.client.provider.provider_name,
                        'model': self.client.current_model_name,
                    }
                else:
                    logger.error("main_config_for_gui not available in APIHandlers to update default provider.")

            if model is not None and model != self.client.current_model_name:
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
                # Update global config for streaming if server_main_config is available
                if server_main_config:
                    server_main_config.set("use_streaming", streaming)
                    server_main_config.save_config()

            if params is not None:
                self.client.params.update(params)
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"].setdefault("params", {}).update(params)
                logger.debug(f"Client params updated: {self.client.params}")

            current_system_instruction_for_response = self.client.system_instruction  # Default to client's current
            if system_instruction is not None:
                self.client.system_instruction = system_instruction  # Update client's active system instruction
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"]["system_instruction"] = system_instruction
                logger.debug(f"Client system instruction updated to: '{system_instruction[:50]}...'")
                current_system_instruction_for_response = system_instruction
                # Optionally update the global default system instruction in config
                if server_main_config and server_main_config.get("default_system_instruction") != system_instruction:
                    # This could be a separate setting if global default vs conversation-specific is desired
                    # For now, let's assume changing it here means changing the default for new conversations too.
                    # server_main_config.set("default_system_instruction", system_instruction)
                    # server_main_config.save_config()
                    pass  # Decided not to update global default here, only conversation specific for now via sidebar. Wizard handles global.

            if self.client.conversation_id and self.client.conversation_data:
                self.run_async(self.client.save_conversation(quiet=True))

            return {
                'success': True,
                'provider_name': self.client.provider.provider_name,
                'model': self.client.current_model_name,
                'streaming': self.client.use_streaming,
                'params': self.client.params.copy(),
                'system_instruction': current_system_instruction_for_response,
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
            # The client's start_new_conversation will use its current system_instruction
            self.run_async(self.client.start_new_conversation(title=title, is_web_ui=True))
            metadata = self.client.conversation_data.get("metadata", {})
            return {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': metadata.get("title", self.client.conversation_name),
                'history': [],  # Initial history is empty, system prompt handled by client
                'provider_name': metadata.get("provider", self.client.provider.provider_name if self.client.provider else 'N/A'),
                'model': metadata.get("model", self.client.current_model_name if self.client.provider else 'N/A'),
                'params': metadata.get("params", self.client.params).copy(),
                'streaming': self.client.use_streaming,
                'full_message_tree': self.client.conversation_data.get("messages", {}),
                'system_instruction': metadata.get("system_instruction", self.client.system_instruction)
            }
        except Exception as e:
            logger.error(f"Failed to create new conversation: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def load_conversation(self, conversation_identifier: str) -> Dict[str, Any]:
        logger.info(f"APIHandlers: Loading conversation: '{conversation_identifier}'")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            self.run_async(self.client.load_conversation(conversation_identifier))
            active_history = self.client.get_conversation_history()  # This history does not include the prepended system prompt
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
                'full_message_tree': full_tree,
                'system_instruction': metadata.get("system_instruction", self.client.system_instruction)
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
            # Ensure current system instruction is in metadata before saving
            if self.client.conversation_data and "metadata" in self.client.conversation_data:
                self.client.conversation_data["metadata"]["system_instruction"] = self.client.system_instruction

            self.run_async(self.client.save_conversation())
            title = self.client.conversation_data.get("metadata", {}).get("title", "Untitled")
            return {'success': True, 'message': f"Conversation '{title}' saved."}
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def _find_conv_file(self, conv_id_or_name: str) -> Optional[Path]:
        if not self.client or not self.client.base_directory: return None  # Use base_directory
        return self.run_async(asyncio.to_thread(self.client._find_conversation_file_by_id_or_filename, self.client.base_directory, conv_id_or_name))

    def duplicate_conversation(self, conversation_id_to_duplicate: str, new_title: str) -> Dict[str, Any]:
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        logger.info(f"APIHandlers: Duplicating conversation ID/File: {conversation_id_to_duplicate} to new title: '{new_title}'")
        try:
            original_filepath = self._find_conv_file(conversation_id_to_duplicate)
            if not original_filepath or not original_filepath.exists():
                return {'error': 'Original conversation file not found', 'status_code': 404}

            with open(original_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            new_conv_id_str = self.client.generate_conversation_id()
            data['conversation_id'] = new_conv_id_str
            if 'metadata' not in data: data['metadata'] = {}
            data['metadata']['title'] = new_title
            now_iso = datetime.now().isoformat()
            data['metadata']['created_at'] = now_iso
            data['metadata']['updated_at'] = now_iso
            data['metadata']['provider'] = data['metadata'].get('provider', self.client.provider.provider_name if self.client.provider else "unknown")
            data['metadata']['model'] = data['metadata'].get('model', self.client.current_model_name if self.client.provider else "unknown")
            # Preserve system instruction from duplicated conversation
            data['metadata']['system_instruction'] = data['metadata'].get('system_instruction', self.client.system_instruction)

            new_filename_str = self.client.format_filename(new_title, new_conv_id_str)
            new_filepath = self.client.base_directory / new_filename_str
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
            original_filepath = self._find_conv_file(conversation_id_or_filename_to_rename)
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
            new_filename_str = self.client.format_filename(new_title, actual_conversation_id)
            new_filepath = self.client.base_directory / new_filename_str
            if original_filepath != new_filepath:
                os.rename(original_filepath, new_filepath)

            # If renaming the active conversation, update client's current name
            if self.client.conversation_id == actual_conversation_id:
                self.client.conversation_name = new_title

            return {'success': True, 'conversation_id': actual_conversation_id, 'new_title': new_title, 'new_filename': new_filename_str}
        except Exception as e:
            logger.error(f"Error renaming conversation: {e}", exc_info=True)
            return {'error': f'Server error: {str(e)}', 'status_code': 500}

    def delete_conversation(self, conversation_id_or_filename_to_delete: str) -> Dict[str, Any]:
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        logger.info(f"APIHandlers: Deleting conversation ID/File: {conversation_id_or_filename_to_delete}")
        try:
            filepath_to_delete = self._find_conv_file(conversation_id_or_filename_to_delete)
            if not filepath_to_delete or not filepath_to_delete.exists():
                return {'error': 'Conversation file not found for deletion', 'status_code': 404}

            actual_conv_id = conversation_id_or_filename_to_delete
            try:
                with open(filepath_to_delete, 'r', encoding='utf-8') as f_read:
                    data_read = json.load(f_read)
                    actual_conv_id = data_read.get('conversation_id', actual_conv_id)
            except Exception:
                pass

            os.remove(filepath_to_delete)

            return {'success': True, 'deleted_conversation_id': actual_conv_id}
        except Exception as e:
            logger.error(f"Error deleting conversation: {e}", exc_info=True)
            return {'error': f'Server error: {str(e)}', 'status_code': 500}

    # --- Message Interaction ---

    def send_message(self, message_content: str) -> Dict[str, Any]:
        logger.debug(f"APIHandlers: Handling non-streaming send for: '{message_content[:50]}...'")
        if not self.client or not self.client.provider: return {'error': 'Client or provider not initialized', 'status_code': 503}
        try:
            # add_user_message now happens in the Flask route before calling this
            # So, self.client.current_user_message_id should be set.
            response_text, token_usage_dict = self.run_async(self.client.get_response())  # get_response uses current_user_message_id

            if response_text is None and token_usage_dict is None:
                logger.error("AI client's get_response returned None for text and token_usage.")
                error_detail = "Provider returned no data or an error occurred during generation."
                return {'error': error_detail, 'status_code': 500}

            self.client.add_assistant_message(response_text, token_usage_dict)  # Adds to conversation_data

            assistant_message_id = self.client._get_last_message_id(
                self.client.conversation_data,
                self.client.active_branch
            )
            user_message_id_for_parenting = self.client.conversation_data["messages"][assistant_message_id]["parent_id"]

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
        logger.debug(f"APIHandlers: Initiating stream for message (content already added by client.add_user_message): '{message_content[:50]}...'")
        if not self.client or not self.client.provider:
            yield {"error": "Client or provider not initialized in APIHandlers."};
            return
        try:
            # client.add_user_message was called in the Flask route handler
            async for data_event in self.client.get_streaming_response():  # get_streaming_response uses current_user_message_id
                yield data_event
                if data_event.get("error") or data_event.get("done"):
                    break
            logger.debug("APIHandlers: Streaming finished.")
        except Exception as e:
            logger.error(f"Streaming error in APIHandlers.stream_message: {e}", exc_info=True)
            yield {"error": str(e)}

    def retry_message(self, assistant_message_id_to_retry: str) -> Dict[str, Any]:
        logger.info(f"APIHandlers: Retrying assistant message: {assistant_message_id_to_retry}")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            retry_result_dict = self.run_async(self.client.retry_message(assistant_message_id_to_retry))
            current_active_history = self.client.get_conversation_history()
            current_full_tree = self.client.conversation_data.get("messages", {})
            return {
                'success': True, 'message': retry_result_dict['message'],
                'sibling_index': retry_result_dict['sibling_index'],
                'total_siblings': retry_result_dict['total_siblings'],
                'history': current_active_history, 'conversation_id': self.client.conversation_id,
                'conversation_name': self.client.conversation_data.get("metadata", {}).get("title"),
                'full_message_tree': current_full_tree,
                'system_instruction': self.client.conversation_data.get("metadata", {}).get("system_instruction", self.client.system_instruction)
            }
        except Exception as e:
            logger.error(f"Failed to retry message {assistant_message_id_to_retry}: {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}

    def navigate_sibling(self, message_id: str, direction: str) -> Dict[str, Any]:
        logger.info(f"APIHandlers: Navigating {direction} from message: {message_id}")
        if not self.client: return {'error': 'Client not initialized', 'status_code': 503}
        try:
            nav_result_dict = self.run_async(self.client.switch_to_sibling(message_id, direction))
            current_active_history = self.client.get_conversation_history()
            current_full_tree = self.client.conversation_data.get("messages", {})
            return {
                'success': True, 'message': nav_result_dict['message'],
                'sibling_index': nav_result_dict['sibling_index'],
                'total_siblings': nav_result_dict['total_siblings'],
                'history': current_active_history, 'conversation_id': self.client.conversation_id,
                'conversation_name': self.client.conversation_data.get("metadata", {}).get("title"),
                'full_message_tree': current_full_tree,
                'system_instruction': self.client.conversation_data.get("metadata", {}).get("system_instruction", self.client.system_instruction)
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

            # For commands that modify state and should return full status
            if cmd_name == '/new':
                response = self.new_conversation(title=cmd_args)
                # Ensure system_instruction is part of the response for /new
                response['system_instruction'] = self.client.system_instruction
                return response
            if cmd_name == '/load':
                if not cmd_args: return {'error': 'Specify conversation name/ID', 'status_code': 400}
                response = self.load_conversation(cmd_args)
                # Ensure system_instruction is part of the response for /load
                response['system_instruction'] = self.client.system_instruction
                return response

            if cmd_name == '/save': return self.save_conversation()
            if cmd_name == '/list':
                convos = self.get_conversations()
                return {'success': True, 'message': 'Conversations list refreshed.', 'conversations': convos.get('conversations')}
            if cmd_name == '/model':
                if cmd_args:
                    return self.update_settings(model=cmd_args)
                else:
                    return self.get_models()
            if cmd_name == '/stream':  # Toggles global default streaming
                response = self.update_settings(streaming=not self.client.use_streaming if self.client else False)
                response['message'] = f"Default streaming mode set to {'ON' if self.client.use_streaming else 'OFF'}."
                return response

            logger.warning(f"Command '{cmd_name}' not directly mapped in APIHandlers.execute_command for rich response.")
            return {'error': f"Command '{cmd_name}' not directly supported via this API endpoint for structured response.", 'status_code': 400}

        except Exception as e:
            logger.error(f"Failed to execute command '{command_str}': {e}", exc_info=True)
            return {'error': str(e), 'status_code': 500}
