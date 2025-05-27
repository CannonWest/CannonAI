#!/usr/bin/env python3
"""
Gemini Chat GUI - API Handlers

This module contains the business logic for handling API requests,
separating concerns from the Flask routing layer.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, AsyncGenerator, Tuple  # Added Tuple
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
        return future.result(timeout=60)

    def get_status(self) -> Dict[str, Any]:
        """Get current client status

        Returns:
            Dictionary with client status information
        """
        print("[DEBUG APIHandlers] Getting client status")

        if not self.client:
            return {'connected': False, 'error': 'Client not initialized'}

        # Ensure conversation_data and metadata exist before accessing
        conv_data = self.client.conversation_data if hasattr(self.client, 'conversation_data') else {}
        metadata = conv_data.get("metadata", {})
        history_for_status = []
        if self.client.conversation_id and conv_data:  # Only send history if a conversation is active
            history_for_status = self.client.get_conversation_history()

        status = {
            'connected': True,
            'model': metadata.get("model", self.client.model),
            'streaming': self.client.use_streaming,  # This should reflect client's general setting
            'conversation_id': self.client.conversation_id,
            'conversation_name': metadata.get("title", getattr(self.client, 'conversation_name', 'New Conversation')),
            'params': metadata.get("params", self.client.params).copy(),
            'history': history_for_status if self.client.conversation_id else []  # Send history if active
        }

        print(f"[DEBUG APIHandlers] Status: conversation_id={status['conversation_id']}, history_len={len(status['history'])}")
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
            # retry_message in client now returns dict: {"message": new_msg_obj, "sibling_index": int, "total_siblings": int}
            retry_result = self.run_async(self.client.retry_message(message_id))

            self.run_async(self.client.save_conversation(quiet=True))

            print(f"[DEBUG APIHandlers] Retry successful, new message ID: {retry_result['message']['id']}")
            print(f"[DEBUG APIHandlers] Siblings: {retry_result['total_siblings']} total, current index: {retry_result['sibling_index']}")

            return {
                'success': True,
                'message': retry_result['message'],  # This is the new assistant message object
                'sibling_index': retry_result['sibling_index'],
                'total_siblings': retry_result['total_siblings'],
                # The client is now on the new branch, so get_conversation_history will reflect that
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
                'siblings': sibling_info['siblings'],  # List of sibling IDs
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
            # switch_to_sibling now returns: {"message": new_active_msg_obj, "sibling_index": int, "total_siblings": int}
            nav_result = self.run_async(self.client.switch_to_sibling(message_id, direction))

            print(f"[DEBUG APIHandlers] Navigated to message: {nav_result['message']['id']}")
            print(f"[DEBUG APIHandlers] Now at sibling index {nav_result['sibling_index']} of {nav_result['total_siblings']}")

            # Get the updated conversation history for the new active branch
            current_history = self.client.get_conversation_history()

            self.run_async(self.client.save_conversation(quiet=True))

            return {
                'success': True,
                'message': nav_result['message'],  # The new active message object
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
            return {'conversations': conversations}  # client.list_conversations already formats it
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
            if self.client.conversation_id:  # Save existing before starting new
                self.run_async(self.client.save_conversation(quiet=True))

            self.run_async(self.client.start_new_conversation(title=title, is_web_ui=True))

            result = {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': self.client.conversation_name,
                # For a new conversation, history is empty
                'history': [],
                'model': self.client.model,
                'params': self.client.params.copy(),
                'streaming': self.client.use_streaming
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
            if self.client.conversation_id:  # Save existing before loading another
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
                'streaming': metadata.get("streaming", self.client.use_streaming)  # Assuming streaming might be saved per convo
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
                # This will set self.client.conversation_data, .conversation_id, .active_branch
                self.run_async(self.client.start_new_conversation(is_web_ui=True))

                # Add user message to client's internal state. This sets current_user_message_id.
            self.client.add_user_message(message)

            # Get response from client (text and token usage)
            # get_response() uses self.current_user_message and then clears it.
            response_text_content, token_usage_info = self.run_async(self.client.get_response())

            if response_text_content is None and token_usage_info is None:  # Indicates error in get_response
                raise Exception("Client get_response failed to return valid data.")

            # Add assistant message to client's internal state
            # This uses response_text_content (string) and token_usage_info (dict)
            self.client.add_assistant_message(response_text_content, token_usage_info)

            # Retrieve IDs for the response
            assistant_message_id = self.client._get_last_message_id(self.client.active_branch)
            user_message_id = self.client.current_user_message_id  # This was set by add_user_message
            # Important: clear current_user_message_id *after* assistant message is processed and parented
            self.client.current_user_message_id = None

            print(f"[DEBUG APIHandlers] Response Text: '{response_text_content[:100] if response_text_content else ''}...', Token Usage: {token_usage_info}")
            print(f"[DEBUG APIHandlers] Message IDs - User: {user_message_id}, Assistant: {assistant_message_id}")

            # Save conversation asynchronously
            self.run_async(self.client.save_conversation(quiet=True))

            return {
                'response': response_text_content,  # This is now guaranteed to be a string
                'conversation_id': self.client.conversation_id,
                'message_id': assistant_message_id,
                'parent_id': user_message_id,
                'model': self.client.conversation_data.get("metadata", {}).get("model", self.client.model),
                'token_usage': token_usage_info  # Send separately
            }
        except Exception as e:
            logger.error(f"Failed to send message via /api/send: {e}", exc_info=True)
            return {'error': str(e)}

    async def stream_message(self, message: str) -> AsyncGenerator[str, None]:
        """Stream a message response using Server-Sent Events format

        Args:
            message: The user's message

        Yields:
            SSE-formatted response chunks: data: {"chunk": str} or data: {"error": str} or data: {"done": bool, ...}
        """
        print(f"[DEBUG APIHandlers] Streaming message: '{message[:50]}...'")

        try:
            if not self.client.conversation_id:
                print("[DEBUG APIHandlers] No active conversation, starting new one implicitly for /api/stream")
                await self.client.start_new_conversation(is_web_ui=True)

            self.client.add_user_message(message)  # Sets self.current_user_message and self.current_user_message_id

            full_response_text = ""
            final_token_usage = None

            # get_streaming_response is an async generator yielding dicts
            async for data_chunk in self.client.get_streaming_response():
                if "chunk" in data_chunk:
                    full_response_text += data_chunk["chunk"]
                    yield f"data: {json.dumps({'chunk': data_chunk['chunk']})}\n\n"
                elif "done" in data_chunk:
                    final_token_usage = data_chunk.get("token_usage")
                    # Add the complete assistant message to internal state
                    self.client.add_assistant_message(full_response_text, final_token_usage)

                    assistant_message_id = self.client._get_last_message_id(self.client.active_branch)
                    user_message_id = self.client.current_user_message_id
                    self.client.current_user_message_id = None  # Clear after use

                    await self.client.save_conversation(quiet=True)

                    yield f"data: {json.dumps({'done': True, 'conversation_id': self.client.conversation_id, 'message_id': assistant_message_id, 'parent_id': user_message_id, 'model': self.client.conversation_data.get('metadata', {}).get('model'), 'token_usage': final_token_usage})}\n\n"
                    print(f"[DEBUG APIHandlers] Streaming complete, response length: {len(full_response_text)}")
                    return  # Stop generation after "done"
                elif "error" in data_chunk:
                    yield f"data: {json.dumps({'error': data_chunk['error']})}\n\n"
                    return  # Stop on error

            # Fallback if stream ends without a "done" event (should not happen with current client impl)
            if not final_token_usage:  # If stream ended abruptly
                self.client.add_assistant_message(full_response_text, None)
                await self.client.save_conversation(quiet=True)
                assistant_message_id = self.client._get_last_message_id(self.client.active_branch)
                user_message_id = self.client.current_user_message_id
                self.client.current_user_message_id = None

                yield f"data: {json.dumps({'done': True, 'conversation_id': self.client.conversation_id, 'message_id': assistant_message_id, 'parent_id': user_message_id, 'model': self.client.conversation_data.get('metadata', {}).get('model')})}\n\n"


        except Exception as e:
            logger.error(f"Streaming error in API Handler: {e}", exc_info=True)
            try:
                await self.client.save_conversation(quiet=True)  # Attempt to save even on error
            except Exception as save_e:
                logger.error(f"Error saving conversation during streaming error handling: {save_e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    def update_settings(self, model: Optional[str] = None,
                        streaming: Optional[bool] = None,
                        params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update client settings (model, streaming preference, generation params).
           These settings apply to the current client instance and will be used for
           new messages in the active conversation or for new conversations.
        """
        print(f"[DEBUG APIHandlers] Updating settings - Model: {model}, Streaming: {streaming}, Params: {params}")
        try:
            if model is not None:
                self.client.model = model
                # Also update in current conversation's metadata if one is active
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"]["model"] = model
                print(f"[DEBUG APIHandlers] Updated client model to: {self.client.model}")

            if streaming is not None:
                self.client.use_streaming = streaming
                # Optionally, store this preference in conversation metadata too if desired
                # if self.client.conversation_data and "metadata" in self.client.conversation_data:
                # self.client.conversation_data["metadata"]["streaming_preference"] = streaming
                print(f"[DEBUG APIHandlers] Updated client streaming preference to: {self.client.use_streaming}")

            if params is not None:
                self.client.params.update(params)
                # Also update in current conversation's metadata
                if self.client.conversation_data and "metadata" in self.client.conversation_data:
                    self.client.conversation_data["metadata"].setdefault("params", {}).update(params)
                print(f"[DEBUG APIHandlers] Updated client params: {self.client.params}")

            # Save conversation if settings were tied to it
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
        """Execute a command through the command handler.
           Some commands are handled directly here if they primarily affect UI state
           or require specific data to be returned to the UI.
        """
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
            elif cmd_name == '/save':
                return self.save_conversation()
            elif cmd_name == '/list':  # For GUI, this might just trigger a refresh of the conversation list display
                convos = self.get_conversations()
                return {'success': True, 'message': 'Conversations list refreshed.', 'conversations': convos.get('conversations')}
            elif cmd_name == '/model':
                if cmd_args:
                    return self.update_settings(model=cmd_args)
                else:  # Return list of models for UI to display
                    return self.get_models()
            elif cmd_name == '/stream':  # Toggle streaming preference
                new_streaming_state = not self.client.use_streaming
                return self.update_settings(streaming=new_streaming_state)
            elif cmd_name == '/params':  # For GUI, this could open the settings modal or display current params
                # For now, just return current params
                return {'success': True, 'params': self.client.params.copy(), 'message': 'Current generation parameters.'}

            # For other commands, try to execute via CommandHandler (if it's set up for more complex logic)
            # This part might be less relevant if most UI interactions map to specific API endpoints
            if hasattr(self.command_handler, 'async_handle_command'):
                # This assumes command_handler can operate on the shared client state
                result = self.run_async(self.command_handler.async_handle_command(command))
                return {'success': True, 'message': f"Command '{command}' executed.", 'result': result}
            else:
                return {'error': f"Command '{cmd_name}' not fully implemented for GUI or handler not found."}

        except Exception as e:
            logger.error(f"Failed to execute command '{command}': {e}", exc_info=True)
            return {'error': str(e)}

