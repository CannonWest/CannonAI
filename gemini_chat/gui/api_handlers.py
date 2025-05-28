#!/usr/bin/env python3
"""
Gemini Chat GUI - API Handlers

This module contains the business logic for handling API requests,
separating concerns from the Flask routing layer.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, AsyncGenerator, Tuple
from datetime import datetime

from async_client import AsyncGeminiClient
from command_handler import CommandHandler
from base_client import Colors

# Set up logging
logger = logging.getLogger("gemini_chat.gui.api_handlers")


class APIHandlers:
    """Handles API business logic for the GUI server"""

    def __init__(self, client: AsyncGeminiClient, command_handler: CommandHandler, event_loop: asyncio.AbstractEventLoop):
        """Initialize API handlers

        Args:
            client: The AsyncGeminiClient instance
            command_handler: The CommandHandler instance
            event_loop: The asyncio event loop running in a separate thread
        """
        self.client = client
        self.command_handler = command_handler
        self.event_loop = event_loop

        print("[DEBUG APIHandlers] Initialized with client and command handler")

    def _get_messages_dict(self) -> Dict[str, Any]:
        """Get messages dictionary, handling both old and new conversation formats.

        Returns:
            Dictionary mapping message IDs to message data
        """
        if hasattr(self.client, 'conversation_data') and self.client.conversation_data:
            messages = self.client.conversation_data.get('messages', {})
            if isinstance(messages, dict):
                return messages
            else:
                print(f"[DEBUG APIHandlers] Messages is not a dict: {type(messages)}")

        if hasattr(self.client, 'conversation_history') and self.client.conversation_history:
            messages_dict = {}
            for item in self.client.conversation_history:
                if item.get('type') == 'message' and 'id' in item:
                    messages_dict[item['id']] = item
            return messages_dict

        return {}

    def run_async(self, coro):
        """Run an async coroutine in the event loop and return result

        Args:
            coro: The coroutine to run

        Returns:
            The result of the coroutine
        """
        future = asyncio.run_coroutine_threadsafe(coro, self.event_loop)
        return future.result(timeout=60)  # Consider making timeout configurable

    def get_status(self) -> Dict[str, Any]:
        """Get current client status

        Returns:
            Dictionary with client status information
        """
        # print("[DEBUG APIHandlers] Getting client status")

        if not self.client:
            return {'connected': False, 'error': 'Client not initialized'}

        conv_data = self.client.conversation_data if hasattr(self.client, 'conversation_data') else {}
        metadata = conv_data.get("metadata", {})
        history_for_status = []
        if self.client.conversation_id and conv_data:
            history_for_status = self.client.get_conversation_history()

        status = {
            'connected': True,
            'model': metadata.get("model", self.client.model),
            'streaming': self.client.use_streaming,
            'conversation_id': self.client.conversation_id,
            'conversation_name': metadata.get("title", getattr(self.client, 'conversation_name', 'New Conversation')),
            'params': metadata.get("params", self.client.params).copy(),
            'history': history_for_status
        }

        # print(f"[DEBUG APIHandlers] Status: conversation_id={status['conversation_id']}, history_len={len(status['history'])}")
        return status

    def get_models(self) -> Dict[str, Any]:
        """Get available models

        Returns:
            Dictionary with models list or error
        """
        print("[DEBUG APIHandlers] Fetching available models")

        try:
            models = self.run_async(self.client.get_available_models())
            print(f"[DEBUG APIHandlers] Found {len(models)} models")
            return {'models': models}
        except Exception as e:
            logger.error(f"Failed to get models: {e}", exc_info=True)
            return {'error': str(e)}

    def retry_message(self, message_id: str) -> Dict[str, Any]:
        """Retry generating a response for a specific message

        Args:
            message_id: The ID of the assistant message to retry

        Returns:
            Dictionary with new message data or error
        """
        print(f"[DEBUG APIHandlers] Retrying message: {message_id}")

        try:
            retry_result = self.run_async(self.client.retry_message(message_id))
            self.run_async(self.client.save_conversation(quiet=True))

            print(f"[DEBUG APIHandlers] Retry successful, new message ID: {retry_result['message']['id']}")
            print(f"[DEBUG APIHandlers] Siblings: {retry_result['total_siblings']} total, current index: {retry_result['sibling_index']}")

            return {
                'success': True,
                'message': retry_result['message'],
                'sibling_index': retry_result['sibling_index'],
                'total_siblings': retry_result['total_siblings'],
                'conversation_name': self.client.conversation_data.get("metadata", {}).get("title"),
                'conversation_id': self.client.conversation_id,
            }
        except Exception as e:
            logger.error(f"Failed to retry message: {e}", exc_info=True)
            return {'error': str(e)}

    def get_message_info(self, message_id: str) -> Dict[str, Any]:
        """Get detailed information about a message including siblings

        Args:
            message_id: The message ID to get info for

        Returns:
            Dictionary with message info or error
        """
        print(f"[DEBUG APIHandlers] Getting info for message: {message_id}")

        try:
            sibling_info = self.run_async(self.client.get_message_siblings(message_id))
            messages = self._get_messages_dict()
            message_data = messages.get(message_id, {})

            print(f"[DEBUG APIHandlers] Message has {sibling_info['total']} siblings")

            return {
                'success': True,
                'message': message_data,
                'siblings': sibling_info['siblings'],
                'current_index': sibling_info['current_index'],
                'total_siblings': sibling_info['total']
            }
        except Exception as e:
            logger.error(f"Failed to get message info: {e}", exc_info=True)
            return {'error': str(e)}

    def navigate_sibling(self, message_id: str, direction: str) -> Dict[str, Any]:
        """Navigate to a sibling message (prev/next) or activate a message's branch ('none').

        Args:
            message_id: Current message ID
            direction: 'prev', 'next', or 'none' (to activate message_id's branch)

        Returns:
            Dictionary with new active message, history, and conversation info or error
        """
        print(f"[DEBUG APIHandlers] Navigating {direction} from message: {message_id}")

        try:
            nav_result = self.run_async(self.client.switch_to_sibling(message_id, direction))

            print(f"[DEBUG APIHandlers] Navigated to message: {nav_result['message']['id']}")
            print(f"[DEBUG APIHandlers] Now at sibling index {nav_result['sibling_index']} of {nav_result['total_siblings']}")

            current_history = self.client.get_conversation_history()
            self.run_async(self.client.save_conversation(quiet=True))

            return {
                'success': True,
                'message': nav_result['message'],
                'sibling_index': nav_result['sibling_index'],
                'total_siblings': nav_result['total_siblings'],
                'history': current_history,
                'conversation_id': self.client.conversation_id,
                'conversation_name': self.client.conversation_data.get("metadata", {}).get("title")
            }
        except Exception as e:
            logger.error(f"Failed to navigate sibling: {e}", exc_info=True)
            return {'error': str(e)}

    def get_conversation_tree(self) -> Dict[str, Any]:
        """Get the full conversation tree structure

        Returns:
            Dictionary with tree data or error
        """
        print("[DEBUG APIHandlers] Getting conversation tree")

        try:
            tree = self.run_async(self.client.get_conversation_tree())
            print(f"[DEBUG APIHandlers] Tree has {len(tree.get('nodes', []))} nodes and {len(tree.get('edges', []))} edges")
            return {'success': True, 'tree': tree}
        except Exception as e:
            logger.error(f"Failed to get conversation tree: {e}", exc_info=True)
            return {'error': str(e)}

    def get_conversations(self) -> Dict[str, Any]:
        """Get list of saved conversations

        Returns:
            Dictionary with conversations list or error
        """
        print("[DEBUG APIHandlers] Fetching conversations list")
        try:
            conversations = self.run_async(self.client.list_conversations())
            print(f"[DEBUG APIHandlers] Found {len(conversations)} conversations")
            return {'conversations': conversations}
        except Exception as e:
            logger.error(f"Failed to get conversations: {e}", exc_info=True)
            return {'error': str(e)}

    def new_conversation(self, title: str = '') -> Dict[str, Any]:
        """Start a new conversation

        Args:
            title: Optional title for the conversation

        Returns:
            Dictionary with success status or error
        """
        print(f"[DEBUG APIHandlers] Starting new conversation with title: '{title}'")
        try:
            if self.client.conversation_id:
                self.run_async(self.client.save_conversation(quiet=True))

            self.run_async(self.client.start_new_conversation(title=title, is_web_ui=True))
            metadata = self.client.conversation_data.get("metadata", {})
            result = {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': metadata.get("title", self.client.conversation_name),
                'history': [],
                'model': metadata.get("model", self.client.model),
                'params': metadata.get("params", self.client.params).copy(),
                'streaming': self.client.use_streaming  # Assuming this is a global client setting
            }
            print(f"[DEBUG APIHandlers] New conversation created: {result['conversation_name']}")
            return result
        except Exception as e:
            logger.error(f"Failed to create new conversation: {e}", exc_info=True)
            return {'error': str(e)}

    def load_conversation(self, conversation_name: str) -> Dict[str, Any]:
        """Load a saved conversation

        Args:
            conversation_name: Name or index of the conversation to load

        Returns:
            Dictionary with success status and conversation data or error
        """
        print(f"[DEBUG APIHandlers] Loading conversation: '{conversation_name}'")
        try:
            if self.client.conversation_id:
                self.run_async(self.client.save_conversation(quiet=True))

            self.run_async(self.client.load_conversation(conversation_name))
            history = self.client.get_conversation_history()
            metadata = self.client.conversation_data.get("metadata", {})

            result = {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': metadata.get("title", "Untitled"),
                'history': history,
                'model': metadata.get("model", self.client.model),
                'params': metadata.get("params", self.client.params).copy(),
                'streaming': metadata.get("streaming_preference", self.client.use_streaming)
            }
            print(f"[DEBUG APIHandlers] Conversation loaded with {len(history)} messages")
            return result
        except Exception as e:
            logger.error(f"Failed to load conversation: {e}", exc_info=True)
            return {'error': str(e)}

    def save_conversation(self) -> Dict[str, Any]:
        """Save the current conversation

        Returns:
            Dictionary with success status or error
        """
        print("[DEBUG APIHandlers] Saving current conversation")
        try:
            self.run_async(self.client.save_conversation())
            print("[DEBUG APIHandlers] Conversation saved successfully")
            return {'success': True}
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}", exc_info=True)
            return {'error': str(e)}

    def send_message(self, message: str) -> Dict[str, Any]:
        """Send a message and get response (non-streaming for /api/send)

        Args:
            message: The user's message

        Returns:
            Dictionary with response or error
        """
        print(f"[DEBUG APIHandlers] Handling /api/send for message: '{message[:50]}...'")

        try:
            if not self.client.conversation_id:
                print("[DEBUG APIHandlers] No active conversation, starting new one implicitly for /api/send")
                self.run_async(self.client.start_new_conversation(is_web_ui=True))

            # Add user message to client's internal state. This sets self.client.current_user_message_id.
            self.client.add_user_message(message)

            # Capture the user message ID BEFORE it's cleared by add_assistant_message (which is called within get_response or add_assistant_message)
            user_message_id_for_parenting = self.client.current_user_message_id

            response_text_content, token_usage_info = self.run_async(self.client.get_response())

            if response_text_content is None and token_usage_info is None:
                raise Exception("Client get_response failed to return valid data.")

            # Add assistant message to client's internal state.
            # This call will use the (now potentially cleared) self.client.current_user_message_id for its own parenting logic,
            # but we have already captured the correct one in user_message_id_for_parenting for the API response.
            self.client.add_assistant_message(response_text_content, token_usage_info)

            assistant_message_id = self.client._get_last_message_id(self.client.active_branch)

            print(f"[DEBUG APIHandlers] Response Text: '{response_text_content[:100] if response_text_content else ''}...', Token Usage: {token_usage_info}")
            print(f"[DEBUG APIHandlers] Message IDs - User (Parent): {user_message_id_for_parenting}, Assistant: {assistant_message_id}")

            self.run_async(self.client.save_conversation(quiet=True))

            return {
                'response': response_text_content,
                'conversation_id': self.client.conversation_id,
                'message_id': assistant_message_id,
                'parent_id': user_message_id_for_parenting,  # Use the captured ID
                'model': self.client.conversation_data.get("metadata", {}).get("model", self.client.model),
                'token_usage': token_usage_info
            }
        except Exception as e:
            logger.error(f"Failed to send message via /api/send: {e}", exc_info=True)
            return {'error': str(e)}

    async def stream_message(self, message: str) -> AsyncGenerator[str, None]:
        """Stream a message response using Server-Sent Events format

        Args:
            message: The user's message

        Yields:
            SSE-formatted response chunks
        """
        print(f"[DEBUG APIHandlers] Streaming message: '{message[:50]}...'")

        try:
            if not self.client.conversation_id:
                print("[DEBUG APIHandlers] No active conversation, starting new one implicitly for /api/stream")
                await self.client.start_new_conversation(is_web_ui=True)

            self.client.add_user_message(message)  # This sets self.client.current_user_message_id

            # Capture the user message ID for parenting BEFORE it's cleared
            user_message_id_for_parenting_stream = self.client.current_user_message_id

            full_response_text = ""
            final_token_usage = None  # Initialize

            # async_client.get_streaming_response() yields dicts:
            # {'chunk': str} OR {'error': str}
            # OR a final {'done': True, 'full_response': str, 'token_usage': dict, ...other_ids}
            async for data_chunk_obj in self.client.get_streaming_response():
                if "chunk" in data_chunk_obj:
                    full_response_text += data_chunk_obj["chunk"]
                    yield f"data: {json.dumps({'chunk': data_chunk_obj['chunk']})}\n\n"
                elif "error" in data_chunk_obj:
                    yield f"data: {json.dumps({'error': data_chunk_obj['error']})}\n\n"
                    return  # Stop on error
                elif "done" in data_chunk_obj and data_chunk_obj["done"]:
                    # This "done" event comes from async_client.get_streaming_response itself
                    # It already contains the necessary IDs and has handled saving.
                    # We just need to forward it.
                    # The parent_id in data_chunk_obj['parent_id'] should be the correct one (user_message_id_for_parenting_stream)
                    yield f"data: {json.dumps(data_chunk_obj)}\n\n"
                    print(f"[DEBUG APIHandlers] Streaming complete (via client's 'done' event), response length: {len(data_chunk_obj.get('full_response', ''))}")
                    return

            # Fallback: If the client's stream ends without its own 'done' event (legacy or unexpected)
            # This block might be redundant if async_client.get_streaming_response always yields a 'done' event.
            print(f"[DEBUG APIHandlers] Client stream ended. Synthesizing 'done' event if needed.")

            # Ensure assistant message is added if not already by a 'done' event from client
            # This check is tricky; ideally, client's get_streaming_response handles its own state.
            # For safety, if we reached here, it implies the client's stream ended without a 'done' event.

            # This part is now largely handled within async_client.get_streaming_response's "done" yield.
            # If we reach here, it means the client's stream finished without yielding its own "done" event.
            # This shouldn't happen with the latest async_client.py logic.
            # However, to be safe, we can construct a done event.

            # The call to self.client.add_assistant_message would have happened inside get_streaming_response
            # before it yielded its "done" event. So current_user_message_id would already be None.
            # We rely on user_message_id_for_parenting_stream captured earlier.

            assistant_message_id = self.client._get_last_message_id(self.client.active_branch)
            # final_token_usage would have been accumulated if client yielded it progressively, or from its "done" event.

            # await self.client.save_conversation(quiet=True) # Save is also done by client before its "done"

            final_done_event = {
                'done': True,
                'conversation_id': self.client.conversation_id,
                'message_id': assistant_message_id,  # ID of the assistant message
                'parent_id': user_message_id_for_parenting_stream,  # Captured user message ID
                'model': self.client.conversation_data.get('metadata', {}).get('model'),
                'token_usage': final_token_usage if final_token_usage else {}  # Ensure it's a dict
            }
            yield f"data: {json.dumps(final_done_event)}\n\n"
            print(f"[DEBUG APIHandlers] Streaming fallback 'done' event sent. Full response length: {len(full_response_text)}")


        except Exception as e:
            logger.error(f"Streaming error in API Handler: {e}", exc_info=True)
            try:
                await self.client.save_conversation(quiet=True)
            except Exception as save_e:
                logger.error(f"Error saving conversation during streaming error handling: {save_e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    def update_settings(self, model: Optional[str] = None,
                        streaming: Optional[bool] = None,
                        params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update client settings."""
        print(f"[DEBUG APIHandlers] Updating settings - Model: {model}, Streaming: {streaming}, Params: {params}")
        try:
            if model is not None:
                self.client.model = model
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"]["model"] = model
                print(f"[DEBUG APIHandlers] Updated client model to: {self.client.model}")

            if streaming is not None:
                self.client.use_streaming = streaming
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"]["streaming_preference"] = streaming  # Store as preference
                print(f"[DEBUG APIHandlers] Updated client streaming preference to: {self.client.use_streaming}")

            if params is not None:
                self.client.params.update(params)
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"].setdefault("params", {}).update(params)
                print(f"[DEBUG APIHandlers] Updated client params: {self.client.params}")

            if self.client.conversation_id:
                self.run_async(self.client.save_conversation(quiet=True))

            return {
                'success': True,
                'model': self.client.model,
                'streaming': self.client.use_streaming,
                'params': self.client.params.copy()
            }
        except Exception as e:
            logger.error(f"Failed to update settings: {e}", exc_info=True)
            return {'error': str(e)}

    def execute_command(self, command: str) -> Dict[str, Any]:
        """Execute a command."""
        print(f"[DEBUG APIHandlers] Executing command: '{command}'")

        try:
            parts = command.lower().split(maxsplit=1)
            cmd_name = parts[0]
            cmd_args = parts[1] if len(parts) > 1 else ""

            if cmd_name == '/new':
                return self.new_conversation(title=cmd_args)
            elif cmd_name == '/load':
                if cmd_args:
                    return self.load_conversation(cmd_args)
                else:
                    return {'error': 'Please specify a conversation name or number to load.'}
            # ... (other command handlers) ...
            else:
                # Fallback for commands not directly handled by specific API endpoints
                if hasattr(self.command_handler, 'async_handle_command'):
                    # This part might need refinement based on what CommandHandler is expected to do
                    # For simple status updates or messages, it's okay.
                    # For actions that change conversation state, it's better to have dedicated API endpoints.
                    result_from_handler = self.run_async(self.command_handler.async_handle_command(command))
                    # The result_from_handler might be a simple message or a boolean.
                    # We need to ensure the response to the client is structured correctly.

                    # After command execution, fetch the latest status to reflect any changes
                    current_status = self.get_status()

                    response_payload = {
                        'success': True,
                        'message': f"Command '{command}' processed.",
                        'result_from_handler': result_from_handler,  # Optional: include direct result
                        # Include updated state:
                        'conversation_id': current_status.get('conversation_id'),
                        'conversation_name': current_status.get('conversation_name'),
                        'model': current_status.get('model'),
                        'params': current_status.get('params'),
                        'streaming': current_status.get('streaming'),
                        'history': current_status.get('history')  # If command changed history
                    }
                    # If the command was to list conversations, add that to payload
                    if cmd_name == '/list':
                        convos = self.get_conversations()
                        response_payload['conversations'] = convos.get('conversations')
                        response_payload['message'] = "Conversations list refreshed."

                    return response_payload
                else:
                    return {'error': f"Command '{cmd_name}' not fully implemented for GUI or handler not found."}

        except Exception as e:
            logger.error(f"Failed to execute command '{command}': {e}", exc_info=True)
            return {'error': str(e)}
