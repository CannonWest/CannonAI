#!/usr/bin/env python3
"""
Gemini Chat UI Server - FastAPI implementation for the web interface

This module provides the FastAPI server implementation for the Gemini Chat Web UI.
It handles WebSocket connections and serves static files.
"""

import os
import sys
import asyncio
import logging
import webbrowser
from pathlib import Path

# Add the parent directory to the Python path
# This is the most reliable way to import from parent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Now we can import from parent directory
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Import from the project
from async_client import AsyncGeminiClient  
from command_handler import CommandHandler
from config import Config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gemini_chat.ui.server")

# Get the current directory for resolving paths
current_dir = Path(__file__).parent
ui_dir = current_dir / "static"

# Create FastAPI app
app = FastAPI(title="Gemini Chat")

# Mount static files
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")

# Global variables
active_connections = []
chat_client = None
command_handler = None


async def initialize_client(config):
    """Initialize the Gemini chat client."""
    # Use the exact same initialization logic as the CLI
    api_key = config.get_api_key()
    model = config.get("default_model")
    conversations_dir = config.get("conversations_dir")
    gen_params = config.get("generation_params", {}).copy()
    use_streaming = config.get("use_streaming", False)
    
    # Create client - directly using AsyncGeminiClient
    client = AsyncGeminiClient(
        api_key=api_key,
        model=model,
        conversations_dir=Path(conversations_dir) if conversations_dir else None,
        generation_params=gen_params,
        use_streaming=use_streaming
    )
    
    # Initialize (same as CLI)
    success = await client.initialize_client()
    if not success:
        raise Exception("Failed to initialize Gemini client")
    
    # Initialize the command handler
    global command_handler
    command_handler = CommandHandler(client)
    
    return client


async def broadcast_message(message):
    """Broadcast a message to all connected WebSocket clients."""
    for connection in active_connections:
        try:
            await connection.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send message to client: {e}")


async def handle_client_message(websocket, message):
    """Handle a message from a client."""
    global chat_client
    
    if not chat_client:
        await websocket.send_json({
            'type': 'system',
            'content': "Error: Chat client not initialized"
        })
        return
    
    # Check if it's a command or regular message
    if message.startswith('/'):
        await handle_command(websocket, message)
    else:
        await handle_chat_message(websocket, message)


async def handle_command(websocket, command):
    """Handle a command from a client."""
    global chat_client, command_handler
    
    if not chat_client or not command_handler:
        await websocket.send_json({
            'type': 'system',
            'content': "Error: Chat client not initialized"
        })
        return
    
    # Extract command and arguments
    parts = command.split(maxsplit=1)
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
    
    # Execute the command
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
        # Format conversation list for better display
        conversations = await chat_client.list_conversations() if hasattr(chat_client, 'list_conversations') else []
        if conversations:
            formatted = "Available conversations:\n" + "\n".join(
                f"- {conv}" for conv in conversations
            )
            await websocket.send_json({
                'type': 'conversation_list',
                'content': formatted,
                'conversations': conversations
            })


async def handle_chat_message(websocket, message):
    """Handle a regular chat message."""
    global chat_client
    
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


async def send_help_message(websocket):
    """Send help information to the client."""
    help_text = """
## Available Commands

- **/help** - Show this help message
- **/new [name]** - Start a new conversation
- **/save** - Save the current conversation
- **/list** - List saved conversations
- **/load <name>** - Load a saved conversation
- **/history** - Display conversation history
- **/model [name]** - Show or change the model
- **/params [param=value ...]** - Show or set generation parameters
- **/stream** - Toggle streaming mode
- **/ui_refresh** - Refresh the UI state
"""
    await websocket.send_json({
        'type': 'help',
        'content': help_text
    })


async def refresh_ui_state(websocket):
    """Refresh the UI state with current settings."""
    global chat_client
    
    if not chat_client:
        return
    
    # Get current state
    state = {
        'type': 'state_update',
        'model': chat_client.model,
        'streaming': chat_client.use_streaming,
        'conversation_name': chat_client.conversation_name,
        'params': chat_client.generation_params
    }
    
    # Send state update
    await websocket.send_json(state)
    
    # Also send conversation history
    await send_conversation_history(websocket)


async def send_conversation_history(websocket):
    """Send the current conversation history to the client."""
    global chat_client
    
    if not chat_client:
        return
    
    # Get history from the client
    # First check if the client has the specific function
    if hasattr(chat_client, 'get_conversation_history'):
        history = chat_client.get_conversation_history()
    else:
        # Try to access the history directly from the message_history attribute
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
    
    # Send history
    await websocket.send_json({
        'type': 'history',
        'content': formatted_history
    })


@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup."""
    logger.info("Starting Gemini Chat Web UI")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the HTML frontend."""
    return FileResponse(ui_dir / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket):
    """Handle WebSocket connections."""
    global chat_client, active_connections
    
    # Accept the connection
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        # Send initial state
        if chat_client:
            await refresh_ui_state(websocket)
        
        # Handle messages
        while True:
            message = await websocket.receive_text()
            await handle_client_message(websocket, message)
            
    except WebSocketDisconnect:
        # Remove from active connections
        active_connections.remove(websocket)
        logger.info("Client disconnected")
        
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}")
        # Try to send error message
        try:
            await websocket.send_json({
                'type': 'system',
                'content': f"Error: {str(e)}"
            })
        except:
            pass
        
        # Remove from active connections if still there
        if websocket in active_connections:
            active_connections.remove(websocket)


def start_web_ui(config, host="127.0.0.1", port=8000):
    """Start the web UI server."""
    global chat_client
    
    # Initialize client in a separate task
    async def init_client():
        global chat_client
        try:
            chat_client = await initialize_client(config)
            logger.info(f"Initialized Gemini client with model: {chat_client.model}")
        except Exception as e:
            logger.error(f"Failed to initialize client: {e}")
    
    # Run initialization as a task
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_client())
    
    # Open browser
    webbrowser.open(f"http://{host}:{port}")
    
    # Start server
    logger.info(f"Starting web server at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
