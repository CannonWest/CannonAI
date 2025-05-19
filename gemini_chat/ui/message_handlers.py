"""
WebSocket message handlers for Gemini Chat UI.

This module contains message handling functions for the WebSocket interface,
separating concerns for better maintainability.
"""

import logging
import json
import os
import asyncio
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
            
        # Get the file path and delete the file
        file_path = target_conv["path"]
        os.remove(file_path)
        
        # If the current conversation was deleted, start a new one
        if chat_client.conversation_id == target_conv.get("conversation_id"):
            # Create a new conversation
            await command_handler.cmd_new("")
        
        await websocket.send_json({
            'type': 'system',
            'content': f"Deleted conversation '{name}'"
        })
        
        # Refresh conversation list
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
    elif cmd == '/list':
        # Get the list of conversations
        logger.debug("Getting list of conversations for /list command")
        conversations = await chat_client.list_conversations() if hasattr(chat_client, 'list_conversations') else []
        logger.debug(f"Found {len(conversations)} conversations in /list")
        
        # Format conversation list for better display
        if conversations:
            # Convert WindowsPath objects to strings before JSON serialization
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
                
            formatted = "Available conversations:\n" + "\n".join(
                f"- {conv['title']}" for conv in serializable_conversations
            ) + "\n\nClick on a conversation name to load it or use /load <n>"
            await websocket.send_json({
                'type': 'conversation_list',
                'content': formatted,
                'conversations': [conv['title'] for conv in serializable_conversations]  # Send only titles for simplicity
            })


async def handle_chat_message(websocket: WebSocket, message: str):
    """Handle a regular chat message."""
    chat_client = get_client()
    
    # Add the message to history (using existing client method)
    chat_client.add_user_message(message)
    
    # Notify the client that the message was received
    await websocket.send_json({
        'type': 'user_message',
        'content': message
    })
    
    # Determine if we're in streaming mode
    if chat_client.use_streaming:
        # Start streaming response
        await websocket.send_json({
            'type': 'assistant_start',
        })
        
        # Get streaming response (reusing existing method)
        full_response = ""
        async for chunk in chat_client.get_streaming_response():
            full_response += chunk
            # Send each chunk to the client
            await websocket.send_json({
                'type': 'assistant_chunk',
                'content': chunk
            })
        
        # Add the full response to history
        chat_client.add_assistant_message(full_response)
        
        # Signal end of response
        await websocket.send_json({
            'type': 'assistant_end',
        })
    else:
        # Get non-streaming response (reusing existing method)
        response = await chat_client.get_response()
        
        # Send the response
        await websocket.send_json({
            'type': 'assistant_message',
            'content': response
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
    
    # Check if it's a command or regular message
    if message.startswith('/'):
        await handle_command(websocket, message, command_handler)
    else:
        await handle_chat_message(websocket, message)
