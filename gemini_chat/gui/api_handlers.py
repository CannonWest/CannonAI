#!/usr/bin/env python3
"""
Gemini Chat GUI - API Handlers

This module contains the business logic for handling API requests,
separating concerns from the Flask routing layer.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, AsyncGenerator
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
    
    def run_async(self, coro):
        """Run an async coroutine in the event loop and return result
        
        Args:
            coro: The coroutine to run
            
        Returns:
            The result of the coroutine
        """
        future = asyncio.run_coroutine_threadsafe(coro, self.event_loop)
        return future.result(timeout=60)  # 60 second timeout
    
    def get_status(self) -> Dict[str, Any]:
        """Get current client status
        
        Returns:
            Dictionary with client status information
        """
        print("[DEBUG APIHandlers] Getting client status")
        
        if not self.client:
            return {
                'connected': False,
                'error': 'Client not initialized'
            }
        
        status = {
            'connected': True,
            'model': self.client.model,
            'streaming': self.client.use_streaming,
            'conversation_id': self.client.conversation_id,
            'conversation_name': getattr(self.client, 'conversation_name', 'New Conversation'),
            'params': self.client.params
        }
        
        print(f"[DEBUG APIHandlers] Status: {status}")
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
    
    def get_conversations(self) -> Dict[str, Any]:
        """Get list of saved conversations
        
        Returns:
            Dictionary with conversations list or error
        """
        print("[DEBUG APIHandlers] Fetching conversations list")
        
        try:
            conversations = self.run_async(self.client.list_conversations())
            print(f"[DEBUG APIHandlers] Found {len(conversations)} conversations")
            
            # Format for frontend
            formatted = []
            for conv in conversations:
                formatted.append({
                    'title': conv['title'],
                    'model': conv['model'],
                    'message_count': conv['message_count'],
                    'created_at': conv['created_at'],
                    'conversation_id': conv['conversation_id'],
                    'filename': conv['filename']
                })
            
            return {'conversations': formatted}
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
            # Save current conversation first
            self.run_async(self.client.save_conversation(quiet=True))
            
            # Start new conversation
            self.run_async(self.client.start_new_conversation(title=title, is_web_ui=True))
            
            result = {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': self.client.conversation_name
            }
            
            print(f"[DEBUG APIHandlers] New conversation created: {result}")
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
            # Save current conversation first
            self.run_async(self.client.save_conversation(quiet=True))
            
            # Load the requested conversation
            self.run_async(self.client.load_conversation(conversation_name))
            
            # Get the conversation history
            history = self.client.get_conversation_history()
            
            result = {
                'success': True,
                'conversation_id': self.client.conversation_id,
                'conversation_name': self.client.conversation_name,
                'history': history
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
        """Send a message and get response (non-streaming)
        
        Args:
            message: The user's message
            
        Returns:
            Dictionary with response or error
        """
        print(f"[DEBUG APIHandlers] Sending message: '{message[:50]}...'")
        
        try:
            # Check if there's an active conversation
            if not self.client.conversation_id:
                print("[DEBUG APIHandlers] No active conversation, starting new one")
                self.run_async(self.client.start_new_conversation(is_web_ui=True))
            
            # Add user message to history
            self.client.add_user_message(message)
            
            # Get response
            response = self.run_async(self.client.get_response())
            
            # Add assistant message to history
            self.client.add_assistant_message(response)
            
            print(f"[DEBUG APIHandlers] Got response: '{response[:50]}...'")
            
            return {
                'response': response,
                'conversation_id': self.client.conversation_id
            }
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
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
            # Check if there's an active conversation
            if not self.client.conversation_id:
                print("[DEBUG APIHandlers] No active conversation, starting new one")
                await self.client.start_new_conversation(is_web_ui=True)
            
            # Add user message to history
            self.client.add_user_message(message)
            
            # Get streaming response
            complete_response = ""
            async for chunk in self.client.get_streaming_response():
                if chunk:
                    complete_response += chunk
                    # Yield as SSE format
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            
            # Add complete response to history
            self.client.add_assistant_message(complete_response)
            
            # Send completion signal
            yield f"data: {json.dumps({'done': True, 'conversation_id': self.client.conversation_id})}\n\n"
            
            print(f"[DEBUG APIHandlers] Streaming complete, response length: {len(complete_response)}")
            
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    def update_settings(self, model: Optional[str] = None, 
                       streaming: Optional[bool] = None,
                       params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update client settings
        
        Args:
            model: New model name (optional)
            streaming: Enable/disable streaming (optional)
            params: Generation parameters to update (optional)
            
        Returns:
            Dictionary with updated settings or error
        """
        print("[DEBUG APIHandlers] Updating settings")
        print(f"[DEBUG APIHandlers] - Model: {model}")
        print(f"[DEBUG APIHandlers] - Streaming: {streaming}")
        print(f"[DEBUG APIHandlers] - Params: {params}")
        
        try:
            # Update model if provided
            if model is not None:
                self.client.model = model
                print(f"[DEBUG APIHandlers] Updated model to: {self.client.model}")
            
            # Update streaming mode if provided
            if streaming is not None:
                self.client.use_streaming = streaming
                print(f"[DEBUG APIHandlers] Updated streaming to: {self.client.use_streaming}")
            
            # Update parameters if provided
            if params is not None:
                self.client.params.update(params)
                print(f"[DEBUG APIHandlers] Updated params: {self.client.params}")
            
            return {
                'success': True,
                'model': self.client.model,
                'streaming': self.client.use_streaming,
                'params': self.client.params
            }
        except Exception as e:
            logger.error(f"Failed to update settings: {e}", exc_info=True)
            return {'error': str(e)}
    
    def execute_command(self, command: str) -> Dict[str, Any]:
        """Execute a command through the command handler
        
        Args:
            command: The command to execute
            
        Returns:
            Dictionary with execution result or error
        """
        print(f"[DEBUG APIHandlers] Executing command: '{command}'")
        
        try:
            # Handle specific commands that need special treatment
            if command.startswith('/new'):
                # Extract title if provided
                parts = command.split(maxsplit=1)
                title = parts[1] if len(parts) > 1 else ''
                return self.new_conversation(title)
            
            elif command.startswith('/load'):
                # Extract conversation name if provided
                parts = command.split(maxsplit=1)
                if len(parts) > 1:
                    return self.load_conversation(parts[1])
                else:
                    # For GUI, we can't prompt for input, so return an error
                    return {'error': 'Please specify a conversation to load'}
            
            elif command == '/save':
                return self.save_conversation()
            
            elif command == '/list':
                return self.get_conversations()
            
            elif command.startswith('/model'):
                # Extract model name if provided
                parts = command.split(maxsplit=1)
                if len(parts) > 1:
                    return self.update_settings(model=parts[1])
                else:
                    # Return available models for GUI to display
                    return self.get_models()
            
            elif command == '/stream':
                # Toggle streaming
                new_state = not self.client.use_streaming
                return self.update_settings(streaming=new_state)
            
            # For other commands, execute through command handler
            result = self.run_async(self.command_handler.async_handle_command(command))
            
            print(f"[DEBUG APIHandlers] Command result: should_exit={result}")
            
            return {
                'success': True,
                'should_exit': result
            }
        except Exception as e:
            logger.error(f"Failed to execute command: {e}", exc_info=True)
            return {'error': str(e)}
