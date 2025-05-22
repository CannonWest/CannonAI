"""
WebSocket message handlers for Gemini Chat UI.

This module contains message handling functions for the WebSocket interface,
separating concerns for better maintainability.
"""

import logging
import json
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from starlette.websockets import WebSocket
from pathlib import Path

# Import client manager for consistent client access
from ui.client_manager import get_client

logger = logging.getLogger("gemini_chat.ui.message_handlers")

async def send_help_message(websocket: WebSocket):
    """Send help information to the client."""
    help_text = """
## Available Commands

- **/help** - Show this help message
- **/new [name]** - Start a new conversation
- **/save** - Save the current conversation
- **/list** - List saved conversations
- **/load <n>** - Load a saved conversation
- **/history** - Display conversation history
- **/model [name]** - Show or change the model
- **/params [param=value ...]** - Show or set generation parameters
- **/stream** - Toggle streaming mode
- **/ui_refresh** - Refresh the UI state
- **/rename <old> <new>** - Rename a conversation
- **/delete <n>** - Delete a conversation
"""
    await websocket.send_json({
        'type': 'help',
        'content': help_text
    })


async def refresh_ui_state(websocket: WebSocket):
    """Refresh the UI state with current settings."""
    chat_client = get_client()
    
    if not chat_client:
        logger.warning("Cannot refresh UI state - client not initialized")
        await websocket.send_json({
            'type': 'system',
            'content': "Error: Chat client not initialized"
        })
        return
    
    # Get current state
    state = {
        'type': 'state_update',
        'model': chat_client.model,
        'streaming': chat_client.use_streaming,
        'conversation_name': getattr(chat_client, 'conversation_name', 'New Conversation'),
        'params': getattr(chat_client, 'params', {}) or getattr(chat_client, 'generation_params', {})
    }
    
    # Send state update
    await websocket.send_json(state)
    
    # Also send conversation history
    await send_conversation_history(websocket)
    
    # Also send list of available conversations
    await send_available_conversations(websocket)


async def update_model_token_limits(websocket: WebSocket, model_name: str, chat_client):
    """Fetch actual token limits for the specified model and update parameters."""
    logger.info(f"Fetching token limits for model: {model_name}")
    print(f"Fetching token limits for model: {model_name}")
    
    try:
        # Get the specific model information
        if hasattr(chat_client, 'get_model_info'):
            model_info = await chat_client.get_model_info(model_name)
        elif hasattr(chat_client, 'client') and hasattr(chat_client.client, 'models'):
            # Try to get model info using the genai client
            try:
                model_info = await chat_client.client.aio.models.get(model=model_name)
                logger.info(f"Successfully fetched model info for {model_name}")
                print(f"Model info retrieved: {model_info}")
            except Exception as e:
                logger.warning(f"Could not fetch model info via client.aio.models.get: {e}")
                print(f"Could not fetch model info via client.aio.models.get: {e}")
                model_info = None
        else:
            logger.warning("No method available to fetch model info")
            print("No method available to fetch model info")
            model_info = None
        
        if model_info:
            # Extract output token limit
            output_limit = getattr(model_info, 'output_token_limit', None) or getattr(model_info, 'outputTokenLimit', 4096)
            input_limit = getattr(model_info, 'input_token_limit', None) or getattr(model_info, 'inputTokenLimit', 0)
            
            logger.info(f"Model {model_name} limits: input={input_limit}, output={output_limit}")
            print(f"Model {model_name} limits: input={input_limit}, output={output_limit}")
            
            # Update max tokens if needed
            current_max = chat_client.params.get("max_output_tokens", 0)
            if current_max > output_limit:
                logger.info(f"Adjusting max_output_tokens from {current_max} to {output_limit}")
                print(f"Adjusting max_output_tokens from {current_max} to {output_limit}")
                chat_client.params["max_output_tokens"] = output_limit
            
            # Send model info update to frontend with actual token limits
            await websocket.send_json({
                'type': 'model_token_limits',
                'model': model_name,
                'input_token_limit': input_limit,
                'output_token_limit': output_limit,
                'current_max_tokens': chat_client.params.get("max_output_tokens", output_limit)
            })
        else:
            logger.warning(f"Could not retrieve model info for {model_name}, using fallback limits")
            print(f"Could not retrieve model info for {model_name}, using fallback limits")
            
            # Fallback to reasonable defaults based on model name
            if "flash" in model_name.lower():
                fallback_limit = 4096
            elif "pro" in model_name.lower():
                fallback_limit = 8192
            else:
                fallback_limit = 4096
            
            # Send fallback limits
            await websocket.send_json({
                'type': 'model_token_limits',
                'model': model_name,
                'input_token_limit': 0,
                'output_token_limit': fallback_limit,
                'current_max_tokens': chat_client.params.get("max_output_tokens", fallback_limit)
            })
            
    except Exception as e:
        logger.error(f"Error fetching model token limits: {str(e)}")
        print(f"Error fetching model token limits: {str(e)}")
        # Send error message to client
        await websocket.send_json({
            'type': 'system',
            'content': f"Warning: Could not fetch token limits for {model_name}"
        })


async def handle_stream_toggle(websocket: WebSocket):
    """Specifically handle the streaming toggle command."""
    chat_client = get_client()
    
    if not chat_client:
        logger.error("Cannot toggle streaming - client not initialized")
        await websocket.send_json({
            'type': 'system',
            'content': "Error: Chat client not initialized"
        })
        return
    
    # Toggle the streaming mode
    chat_client.use_streaming = not chat_client.use_streaming
    new_state = chat_client.use_streaming
    
    # Log the change
    logger.info(f"Streaming mode toggled to: {new_state}")
    print(f"Streaming mode toggled to: {new_state}")
    
    # Send immediate UI update with new streaming state
    await websocket.send_json({
        'type': 'state_update',
        'model': chat_client.model,
        'streaming': new_state,
        'conversation_name': getattr(chat_client, 'conversation_name', 'New Conversation'),
        'params': getattr(chat_client, 'params', {}) or getattr(chat_client, 'generation_params', {})
    })
    
    # Also send confirmation message
    await websocket.send_json({
        'type': 'system',
        'content': f"Streaming mode {'enabled' if new_state else 'disabled'}"
    })


async def send_conversation_history(websocket: WebSocket):
    """Send the current conversation history to the client."""
    chat_client = get_client()
    
    if not chat_client:
        logger.warning("Cannot send conversation history - client not initialized")
        return
    
    # Get history from the client
    # First check if the client has the specific function
    if hasattr(chat_client, 'get_conversation_history'):
        logger.debug("Using get_conversation_history() method")
        history = chat_client.get_conversation_history()
    else:
        # Try to access the history directly from the message_history attribute
        logger.debug("Falling back to message_history attribute")
        history = []
        if hasattr(chat_client, 'message_history'):
            for msg in chat_client.message_history:
                if msg['type'] == 'message':
                    history.append({
                        'role': msg['content']['role'],
                        'content': msg['content']['text']
                    })
    
    # Format for the UI
    formatted_history = []
    for msg in history:
        if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
            formatted_history.append({
                'role': msg['role'],
                'content': msg['content']
            })
    
    logger.debug(f"Sending {len(formatted_history)} messages in history to client")
    
    # Send history
    await websocket.send_json({
        'type': 'history',
        'content': formatted_history
    })


async def send_available_conversations(websocket: WebSocket):
    """Send the list of available conversations to the client."""
    chat_client = get_client()
    
    if not chat_client:
        logger.warning("Cannot send conversations list - client not initialized")
        return
    
    # Check if client has list_conversations method
    if not hasattr(chat_client, 'list_conversations'):
        logger.warning("Client does not have list_conversations method")
        return
        
    try:
        # Get the list of conversations
        logger.debug("Retrieving conversation list")
        conversations = await chat_client.list_conversations()
        
        if not conversations:
            logger.debug("No conversations found")
            await websocket.send_json({
                'type': 'conversation_list',
                'content': "No saved conversations found.",
                'conversations': []
            })
            return
            
        # Log what we found
        logger.debug(f"Found {len(conversations)} conversations")
        for i, conv in enumerate(conversations):
            logger.debug(f"  {i+1}. {conv.get('title', 'Untitled')}")
        
        # Format for display
        formatted = "Available conversations:\n" + "\n".join(
            f"- {conv['title']}" for conv in conversations
        ) + "\n\nClick on a conversation name to load it or use /load <n>"
        
        # Convert Path objects to strings for JSON serialization
        serializable_conversations = []
        for conv in conversations:
            serialized_conv = {}
            for key, value in conv.items():
                # Convert Path objects to strings
                if key == 'path':
                    serialized_conv[key] = str(value)
                else:
                    serialized_conv[key] = value
            serializable_conversations.append(serialized_conv)
        
        # Send to client
        await websocket.send_json({
            'type': 'conversation_list',
            'content': formatted,
            'conversations': [conv['title'] for conv in serializable_conversations]  # Send only titles for simplicity
        })
        
    except Exception as e:
        logger.error(f"Error getting conversation list: {str(e)}")
        await websocket.send_json({
            'type': 'system',
            'content': f"Error loading conversations: {str(e)}"
        })


async def handle_rename_conversation(websocket: WebSocket, old_name: str, new_name: str, command_handler):
    """Rename a conversation."""
    chat_client = get_client()
    
    if not chat_client:
        await websocket.send_json({
            'type': 'system',
            'content': "Error: Chat client not initialized"
        })
        return
    
    try:
        # Get the conversations list
        conversations = await chat_client.list_conversations()
        
        # Find the conversation to rename
        target_conv = None
        for conv in conversations:
            if conv["title"].lower() == old_name.lower():
                target_conv = conv
                break
        
        if not target_conv:
            await websocket.send_json({
                'type': 'system',
                'content': f"Error: Conversation '{old_name}' not found"
            })
            return
            
        # Get the file path
        file_path = target_conv["path"]
        
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Update the title in metadata
        for item in data.get("history", []):
            if item.get("type") == "metadata":
                item["content"]["title"] = new_name
                break
        
        # Create new filename with sanitized title
        old_filename = os.path.basename(file_path)
        conversation_id = old_filename.split('_')[-1]  # Extract UUID part
        
        # Use the same format as in the client
        new_filename = f"{new_name.lower().replace(' ', '_')}_{conversation_id}"
        new_path = os.path.join(os.path.dirname(file_path), new_filename)
        
        # Write updated data to new file
        with open(new_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Remove old file if the name changed
        if new_path != str(file_path):
            os.remove(file_path)
        
        # If the current conversation was renamed, update its title
        if chat_client.conversation_id == data.get("conversation_id"):
            chat_client.conversation_name = new_name
        
        await websocket.send_json({
            'type': 'system',
            'content': f"Renamed conversation '{old_name}' to '{new_name}'"
        })
        
        # Refresh conversation list
        await handle_command(websocket, "/list", command_handler)
        
    except Exception as e:
        logger.error(f"Error renaming conversation: {str(e)}")
        await websocket.send_json({
            'type': 'system',
            'content': f"Error renaming conversation: {str(e)}"
        })


async def handle_delete_conversation(websocket: WebSocket, name: str, command_handler):
    """Delete a conversation."""
    chat_client = get_client()
    
    if not chat_client:
        await websocket.send_json({
            'type': 'system',
            'content': "Error: Chat client not initialized"
        })
        return
    
    try:
        # Get the conversations list
        logger.debug(f"Getting conversation list to find '{name}' for deletion")
        conversations = await chat_client.list_conversations()
        
        # Find the conversation to delete
        target_conv = None
        for conv in conversations:
            if conv["title"].lower() == name.lower():
                target_conv = conv
                break
        
        if not target_conv:
            await websocket.send_json({
                'type': 'system',
                'content': f"Error: Conversation '{name}' not found"
            })
            return
            
        # Get the file path
        file_path = target_conv["path"]
        logger.debug(f"Deleting conversation file: {file_path}")
        
        # Check if this is the current conversation before deleting
        is_current = False
        current_conversation_id = getattr(chat_client, 'conversation_id', None)
        target_conversation_id = target_conv.get("conversation_id")
        
        if current_conversation_id and target_conversation_id and current_conversation_id == target_conversation_id:
            is_current = True
            logger.debug(f"The conversation being deleted is the current conversation (ID: {current_conversation_id})")
        
        # Delete the file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug("File deleted successfully")
            else:
                logger.warning(f"File not found for deletion: {file_path}")
        except OSError as e:
            logger.error(f"OS error when deleting file: {e}")
            await websocket.send_json({
                'type': 'system',
                'content': f"Error deleting file: {str(e)}"
            })
            return
        
        # Start a new conversation if we deleted the current one
        if is_current:
            try:
                logger.debug("Creating new conversation since current was deleted")
                await command_handler.cmd_new()
                logger.debug("New conversation created successfully")
            except Exception as e:
                logger.error(f"Error creating new conversation: {e}")
                # Continue even if this fails - we've already deleted the file
        
        # Send success message
        await websocket.send_json({
            'type': 'system',
            'content': f"Deleted conversation '{name}'"
        })
        
        # Refresh conversation list
        logger.debug("Refreshing conversation list after deletion")
        await handle_command(websocket, "/list", command_handler)
        
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        await websocket.send_json({
            'type': 'system',
            'content': f"Error deleting conversation: {str(e)}"
        })


async def handle_command(websocket: WebSocket, command_text: str, command_handler):
    """Handle a command from a client."""
    chat_client = get_client()
    
    if not chat_client or not command_handler:
        await websocket.send_json({
            'type': 'system',
            'content': "Error: Chat client not initialized"
        })
        return
        
    # Log the command being executed
    logger.debug(f"Executing command: {command_text}")
    
    # Extract command and arguments
    parts = command_text.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    # Set a flag indicating we're in web UI mode - this needs to be persistent
    # between commands, so we set it on the client itself
    chat_client.is_web_ui = True
    
    # Special handling for commands that need UI feedback
    if cmd == '/help':
        # Send help directly from the web UI
        await send_help_message(websocket)
        return
        
    # Web UI specific commands
    if cmd == '/ui_refresh':
        # Refresh the UI state
        await refresh_ui_state(websocket)
        return
    
    # Special handling for streaming toggle
    if cmd == '/stream':
        await handle_stream_toggle(websocket)
        return
    
    # New commands for the modern UI
    if cmd == '/rename' and args:
        # Split the args into old and new names
        rename_parts = args.split(maxsplit=1)
        if len(rename_parts) == 2:
            old_name, new_name = rename_parts
            await handle_rename_conversation(websocket, old_name, new_name, command_handler)
        else:
            await websocket.send_json({
                'type': 'system',
                'content': "Error: Rename command requires old and new names"
            })
        return
        
    if cmd == '/delete' and args:
        await handle_delete_conversation(websocket, args, command_handler)
        return
    
    # Process commands using the existing command handler
    # Store the original send_message function to restore it later
    original_send_message = chat_client.send_message
    
    # Override the send_message function to capture the output
    result_message = ""
    
    async def capture_message(message):
        nonlocal result_message
        result_message = message
        return await original_send_message(message)
    
    chat_client.send_message = capture_message
    
    # Handle specific commands with arguments
    if cmd == '/load' and args:
        # Direct loading with a conversation name
        should_exit = await command_handler.cmd_load(args)
    elif cmd == '/model' and args:
        # Direct model setting with a model name
        should_exit = await command_handler.cmd_model(args)
        
        # Get the actual token limits for the selected model
        logger.info(f"Model changed to {args}, fetching actual token limits from API")
        await update_model_token_limits(websocket, args, chat_client)
    elif cmd == '/new':
        # Handle new conversation with web UI mode
        # Extract title from args if provided
        title = args.strip() if args else f"Conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.debug(f"Creating new conversation with title: {title}")
        
        # Pass the title to cmd_new and set is_web_ui flag in the client
        chat_client.is_web_ui = True  # Set flag to indicate this is a web UI request
        should_exit = await command_handler.cmd_new(args)
        
        # After creating a new conversation, update all UI elements
        # First refresh the UI state to get current model, streaming mode, etc.
        await refresh_ui_state(websocket)
        
        # Then refresh the conversation list
        await send_available_conversations(websocket)
        
        # Finally, send the empty conversation history
        await send_conversation_history(websocket)
        
        # Log that we're updating the conversation list
        logger.debug("Explicitly refreshing conversation list after new conversation creation")
        # Explicitly refresh the conversation list again to ensure the UI is updated
        await send_available_conversations(websocket)
    else:
        # Execute the command using the normal handler
        should_exit = await command_handler.async_handle_command(cmd)
    
    # Restore the original send_message function
    chat_client.send_message = original_send_message
    
    # Send the result back to the client
    await websocket.send_json({
        'type': 'system',
        'content': result_message or f"Command '{cmd}' executed."
    })
    
    # Special post-command actions for UI
    if cmd in ['/load', '/new']:
        # After loading/creating conversation, show history
        await send_conversation_history(websocket)
        
        # Also refresh the conversation list
        await send_available_conversations(websocket)
        
        # Update UI state (model, streaming status, etc.)
        await refresh_ui_state(websocket)
    elif cmd in ['/save', '/list', '/delete', '/rename']:
        # For conversation management commands, refresh the conversation list
        logger.debug(f"Refreshing conversation list after {cmd} command")
        await send_available_conversations(websocket)
    elif cmd in ['/model', '/params']:
        # For other setting changes, update the UI state
        await refresh_ui_state(websocket)


async def handle_chat_message(websocket: WebSocket, message: str):
    """Handle a regular chat message."""
    chat_client = get_client() # Fetches the AsyncGeminiClient instance

    if not chat_client:
        logger.error("Chat client not initialized in handle_chat_message")
        await websocket.send_json({'type': 'system', 'content': "Error: Chat client not initialized"})
        return

    # 1. Add user's message to the client's conversation_history
    # This method also sets chat_client.current_user_message internally
    chat_client.add_user_message(message)

    # 2. Notify the UI to display the user's message
    await websocket.send_json({
        'type': 'user_message',
        'content': message
    })

    # 3. Get response from the AI
    if chat_client.use_streaming:
        await websocket.send_json({'type': 'assistant_start'})
        full_response_text = ""
        try:
            # get_streaming_response uses chat_client.conversation_history (which now includes the user's message)
            async for chunk in chat_client.get_streaming_response():
                full_response_text += chunk
                await websocket.send_json({'type': 'assistant_chunk', 'content': chunk})
        except Exception as e:
            logger.error(f"Error during streaming response: {e}", exc_info=True)
            error_chunk_message = f"\nError processing stream: {e}"
            await websocket.send_json({'type': 'assistant_chunk', 'content': error_chunk_message})
            full_response_text += error_chunk_message # Ensure error is part of the history
        finally:
            # Add the complete AI-streamed response to the client's history
            # Note: Token usage details might not be fully available from streaming in the current setup
            chat_client.add_assistant_message(full_response_text)
            await websocket.send_json({'type': 'assistant_end'})
    else: # Non-streaming
        # get_response uses chat_client.conversation_history (which now includes the user's message)
        response_text = await chat_client.get_response()

        # Add the AI's non-streamed response to the client's history
        # Note: Similar to streaming, detailed token_usage might need get_response to return it
        # if it's to be stored accurately per message via add_assistant_message.
        # For now, add_assistant_message will use defaults if token_usage isn't explicitly passed or handled within get_response.
        chat_client.add_assistant_message(response_text)

        # Send the complete AI message to the UI
        await websocket.send_json({
            'type': 'assistant_message',
            'content': response_text
        })

async def fetch_available_models(websocket: WebSocket):
    """Fetch and send the list of available models to the client."""
    chat_client = get_client()
    
    if not chat_client:
        logger.error("Cannot fetch models - client not initialized")
        await websocket.send_json({
            'type': 'system',
            'content': "Error: Chat client not initialized"
        })
        return
    
    # Check if client has get_available_models method
    if not hasattr(chat_client, 'get_available_models'):
        logger.error("Client does not have get_available_models method")
        await websocket.send_json({
            'type': 'system',
            'content': "Error: This client doesn't support retrieving available models"
        })
        return
    
    try:
        # Get the list of models
        logger.info("Fetching available models from the API...")
        models = await chat_client.get_available_models()
        
        if not models:
            logger.warning("No models found")
            await websocket.send_json({
                'type': 'available_models',
                'content': "No models available.",
                'models': []
            })
            return
        
        # Format the models for the UI
        formatted_models = []
        for model in models:
            # Extract the short name from the full resource path if needed
            name = model["name"]
            if '/' in name:
                name = name.split('/')[-1]
            
            # Get token limits with fallback values
            input_limit = model.get("input_token_limit", 0)
            output_limit = model.get("output_token_limit", 4096)  # Default fallback
            
            print(f"Model {name}: input_limit={input_limit}, output_limit={output_limit}")
            
            formatted_models.append({
                "name": name,
                "display_name": model["display_name"],
                "input_token_limit": input_limit,
                "output_token_limit": output_limit
            })
        
        logger.info(f"Found {len(formatted_models)} models from the API")
        for model in formatted_models:
            logger.info(f"  Model: {model['name']} - {model['display_name']}")
        
        # Send the models to the client
        await websocket.send_json({
            'type': 'available_models',
            'content': "Available models:",
            'models': formatted_models
        })
        
    except Exception as e:
        logger.error(f"Error retrieving models: {str(e)}")
        logger.debug("Detailed error trace:", exc_info=True)
        await websocket.send_json({
            'type': 'system',
            'content': f"Error retrieving models: {str(e)}"
        })

async def handle_client_message(websocket: WebSocket, message: str, command_handler):
    """Process a message from the client."""
    chat_client = get_client()
    
    logger.debug(f"Handling client message: {message[:50]}{'...' if len(message) > 50 else ''}")
    
    if not chat_client:
        logger.error("Chat client not initialized")
        await websocket.send_json({
            'type': 'system',
            'content': "Error: Chat client not initialized"
        })
        return
    
    # Check for special UI commands
    if message == "/fetch_models":
        logger.info("Received /fetch_models command from client")
        await fetch_available_models(websocket)
        return
    
    # Check if it's a command or regular message
    if message.startswith('/'):
        await handle_command(websocket, message, command_handler)
    else:
        await handle_chat_message(websocket, message)
