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
import datetime
import webbrowser
from pathlib import Path

# Add the parent directory to the Python path
# This is the most reliable way to import from parent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Now we can import from parent directory
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from starlette.websockets import WebSocketDisconnect, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Import from the project
from async_client import AsyncGeminiClient  
from command_handler import CommandHandler
from config import Config

# Import our WebSocket handlers and utilities
from ui.websocket_fix import WebSocketManager, create_websocket_route
from ui.message_handlers import handle_client_message, send_conversation_history
# Import our client manager for client reference sharing
from ui.client_manager import set_client, get_client

# Set up logging - use DEBUG level for more detailed logs
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("gemini_chat.ui.server")

# Get the current directory for resolving paths
current_dir = Path(__file__).parent
ui_dir = current_dir / "static"

# Create FastAPI app
app = FastAPI(title="Gemini Chat")

# Add CORS middleware for debugging
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for debugging
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")

# Global variables
chat_client = None
command_handler = None
ws_manager = WebSocketManager()

# Flag to determine if we should use the modern UI
USE_MODERN_UI = True  # Set to True to use the new modern UI


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
        conversations_dir=Path(conversations_dir) if conversations_dir else None
    )
    client.params = gen_params
    client.use_streaming = use_streaming
    
    # Initialize (same as CLI)
    success = await client.initialize_client()
    if not success:
        raise Exception("Failed to initialize Gemini client")
    
    # Initialize the command handler
    global command_handler
    command_handler = CommandHandler(client)
    
    return client


async def process_client_message(websocket, message):
    """Process a message from a client, delegates to the message_handlers module."""
    global chat_client, command_handler
    
    # Use our modularized message handler
    await handle_client_message(websocket, message, command_handler)


@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup."""
    logger.info("Starting Gemini Chat Web UI")
    
    # Register our custom WebSocket handler that bypasses middleware issues
    create_websocket_route(app, "/ws", handle_websocket_messages, ws_manager)
    logger.info("Custom WebSocket handler registered to fix 403 Forbidden errors")


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Serve the HTML frontend."""
    logger.debug("Serving main index.html page")
    if USE_MODERN_UI:
        logger.info("Using modern UI design")
        return FileResponse(ui_dir / "new_index.html")
    else:
        logger.info("Using classic UI design")
        return FileResponse(ui_dir / "index.html")


@app.get("/ws-test")
async def websocket_test():
    """Simple endpoint to test if the server can respond to WebSocket-related requests."""
    logger.debug("/ws-test endpoint called")
    return {
        "status": "ok",
        "message": "WebSocket test endpoint is working",
        "server_time": str(datetime.datetime.now()),
        "cors_enabled": True
    }


async def handle_websocket_messages(websocket: WebSocket, manager: WebSocketManager):
    """Custom WebSocket handler that processes messages after connection."""
    logger = logging.getLogger("gemini_chat.ui.server.websocket")
    # Get chat client from the client manager
    chat_client = get_client()
    
    client_info = f"{websocket.client.host}:{websocket.client.port}"
    logger.info(f"WebSocket connection established with {client_info}")
    
    # Send initial state immediately after connection
    try:
        if chat_client:
            # Send model and connection status right away
            state = {
                'type': 'state_update',
                'model': chat_client.model,
                'streaming': chat_client.use_streaming,
                'conversation_name': getattr(chat_client, 'conversation_name', 'New Conversation'),
                'params': getattr(chat_client, 'params', {}) or getattr(chat_client, 'generation_params', {})
            }
            logger.debug(f"Sending initial state update to {client_info}")
            await websocket.send_json(state)
            
            # Also send conversation history
            await send_conversation_history(websocket)
            
            # Also send list of available conversations on startup
            await handle_client_message(websocket, "/list", command_handler)
        else:
            logger.warning("Chat client not initialized when WebSocket connected")
            await websocket.send_json({
                'type': 'system',
                'content': "Warning: Chat client not fully initialized."
            })
        
        # Process messages in a loop
        while True:
            # Wait for messages
            message = await websocket.receive_text()
            if len(message) > 50:
                logger.debug(f"Received message from {client_info}: {message[:50]}...")
            else:
                logger.debug(f"Received message from {client_info}: {message}")
                
            # Process the message
            await process_client_message(websocket, message)
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected normally: {client_info}")
    except Exception as e:
        logger.error(f"Error in WebSocket connection with {client_info}: {str(e)}")
        logger.debug("Detailed error trace:", exc_info=True)
        
        # Try to notify client about the error if connection is still active
        try:
            await websocket.send_json({
                'type': 'system',
                'content': f"Server error: {str(e)}"
            })
        except:
            # Connection may already be closed, ignore additional errors
            pass


def start_web_ui(config, host="127.0.0.1", port=8000):
    """Start the web UI server with optimized WebSocket settings."""
    global chat_client
    
    print("\n" + "=" * 60)
    print("STARTING GEMINI CHAT WEB UI")
    print("=" * 60 + "\n")
    
    # Initialize client in a separate task
    async def init_client():
        global chat_client
        try:
            print("Initializing Gemini client...")
            chat_client = await initialize_client(config)
            # Set the client in the client manager for shared access
            set_client(chat_client)
            print(f"Successfully initialized Gemini client with model: {chat_client.model}")
        except Exception as e:
            print(f"ERROR: Failed to initialize client: {e}")
            import traceback
            print(traceback.format_exc())
    
    # Run initialization as a task
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_client())
    
    # Open browser
    webbrowser.open(f"http://{host}:{port}")
    
    # Enhanced uvicorn configuration for WebSocket support
    print(f"Starting web server at http://{host}:{port}")
    
    # Run with explicit WebSocket settings for reliability
    uvicorn.run(
        app, 
        host=host, 
        port=port,
        log_level="debug",     # Enable detailed logging
        ws="auto",             # Explicitly enable WebSockets
        ws_max_size=16777216,  # Increase max message size (16MB)
        ws_ping_interval=20,   # Send ping frames every 20 seconds
        ws_ping_timeout=20     # Wait 20 seconds for pong response
    )
