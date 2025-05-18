"""
WebSocket handler for streaming Gemini AI responses in the web UI.

This module implements the WebSocket connection for streaming AI responses.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Import client functionality
import sys
import os
from pathlib import Path

# Add parent directory to sys.path if needed
parent_dir = Path(__file__).resolve().parent.parent
if str(parent_dir) not in sys.path:
    sys.path.append(str(parent_dir))

from client_manager import ClientManager
from config import Config

# ----- WebSocket Connection Manager -----

class ConnectionManager:
    """Manager for WebSocket connections"""
    
    def __init__(self):
        """Initialize the connection manager"""
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, client_id: str, websocket: WebSocket):
        """Connect a new client
        
        Args:
            client_id: Unique client identifier
            websocket: WebSocket connection
        """
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected")
    
    def disconnect(self, client_id: str):
        """Disconnect a client
        
        Args:
            client_id: Unique client identifier
        """
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected")
    
    async def send_message(self, client_id: str, message: Dict[str, Any]):
        """Send a message to a client
        
        Args:
            client_id: Unique client identifier
            message: Message to send (will be JSON-encoded)
        """
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)
    
    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connected clients
        
        Args:
            message: Message to broadcast (will be JSON-encoded)
        """
        for connection in self.active_connections.values():
            await connection.send_json(message)

# ----- WebSocket Handler -----

async def get_or_create_client(app: FastAPI, client_id: str):
    """Get an existing client or create a new one
    
    Args:
        app: FastAPI application instance
        client_id: Unique client identifier
        
    Returns:
        The client instance
    """
    # Make sure app.state has clients dictionary
    if not hasattr(app.state, 'clients'):
        app.state.clients = {}
        
    # Make sure app.state has active_conversations dictionary
    if not hasattr(app.state, 'active_conversations'):
        app.state.active_conversations = {}
    
    if client_id not in app.state.clients:
        logger.info(f"Creating new client for {client_id}")
        
        # Load config
        config = Config()
        
        # Create client using ClientManager static method
        client = ClientManager.create_client(
            async_mode=True,  # Always use async mode for web UI
            api_key=config.get_api_key(),
            model=config.get("default_model"),
            conversations_dir=Path(config.get("conversations_dir")) if config.get("conversations_dir") else None,
            params=config.get("generation_params", {}),
            use_streaming=config.get("use_streaming", True)
        )
        
        # Initialize the client
        await client.initialize_client()
        
        # Store client
        app.state.clients[client_id] = client
    
    return app.state.clients[client_id]

def setup_websocket(app: FastAPI) -> None:
    """Set up WebSocket endpoint for the application
    
    Args:
        app: The FastAPI application
    """
    # Create connection manager
    manager = ConnectionManager()
    
    @app.websocket("/ws/{client_id}")
    async def websocket_endpoint(websocket: WebSocket, client_id: str):
        """WebSocket endpoint for streaming AI responses"""
        await manager.connect(client_id, websocket)
        
        try:
            # Get or create client
            client = await get_or_create_client(app, client_id)
            
            # Process messages
            async for message in websocket.iter_json():
                # Expected message format:
                # {
                #   "action": "send_message",
                #   "data": {
                #     "conversation_id": "...",
                #     "message": "..."
                #   }
                # }
                
                try:
                    action = message.get("action")
                    data = message.get("data", {})
                    
                    if action == "send_message":
                        # Process message action
                        await process_message(
                            app, 
                            client, 
                            client_id, 
                            manager, 
                            data
                        )
                    elif action == "ping":
                        # Simple ping-pong for connection testing
                        await manager.send_message(
                            client_id, 
                            {"action": "pong", "timestamp": data.get("timestamp")}
                        )
                    else:
                        # Unknown action
                        await manager.send_message(
                            client_id,
                            {
                                "action": "error",
                                "error": f"Unknown action: {action}"
                            }
                        )
                
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {e}")
                    await manager.send_message(
                        client_id,
                        {
                            "action": "error",
                            "error": str(e)
                        }
                    )
        
        except WebSocketDisconnect:
            logger.info(f"Client {client_id} disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            manager.disconnect(client_id)

async def process_message(
    app: FastAPI,
    client,
    client_id: str,
    manager: ConnectionManager,
    data: Dict[str, Any]
) -> None:
    """Process a message from the client
    
    Args:
        app: FastAPI application instance
        client: The client instance
        client_id: Unique client identifier
        manager: Connection manager
        data: Message data
    """
    # Extract data
    conversation_id = data.get("conversation_id")
    message = data.get("message")
    
    # Validate data
    if not message:
        await manager.send_message(
            client_id,
            {
                "action": "error",
                "error": "Message is required"
            }
        )
        return
    
    # Get conversation ID
    if not conversation_id:
        conversation_id = app.state.active_conversations.get(client_id)
        
    # Validate conversation ID
    if not conversation_id:
        await manager.send_message(
            client_id,
            {
                "action": "error",
                "error": "No active conversation. Create or load a conversation first."
            }
        )
        return
    
    # Set conversation ID
    client.conversation_id = conversation_id
    
    # Ensure conversation is loaded
    if not client.conversation_history:
        await client.load_conversation(conversation_id)
    
    try:
        # Send start message
        await manager.send_message(
            client_id,
            {
                "action": "stream_start",
                "conversation_id": conversation_id
            }
        )
        
        # Add user message to history
        user_message = client.create_message_structure("user", message, client.model, client.params)
        client.conversation_history.append(user_message)
        
        # Send user message confirmation
        await manager.send_message(
            client_id,
            {
                "action": "message_sent",
                "message": {
                    "role": "user",
                    "text": message
                },
                "conversation_id": conversation_id
            }
        )
        
        # Build chat history for the API
        chat_history = client.build_chat_history(client.conversation_history)
        
        # Add the new message
        from google.genai import types
        chat_history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
        
        # Configure generation parameters
        config = types.GenerateContentConfig(
            temperature=client.params["temperature"],
            max_output_tokens=client.params["max_output_tokens"],
            top_p=client.params["top_p"],
            top_k=client.params["top_k"]
        )
        
        # Get stream generator
        stream_generator = await client.client.aio.models.generate_content_stream(
            model=client.model,
            contents=chat_history,
            config=config
        )
        
        # Process the stream
        response_text = ""
        async for chunk in stream_generator:
            if hasattr(chunk, 'text') and chunk.text:
                chunk_text = chunk.text
                response_text += chunk_text
                
                # Send chunk to client
                await manager.send_message(
                    client_id,
                    {
                        "action": "stream_chunk",
                        "chunk": chunk_text,
                        "conversation_id": conversation_id
                    }
                )
        
        # Add AI response to history
        token_usage = {}  # We don't have token usage for streaming responses
        ai_message = client.create_message_structure("ai", response_text, client.model, client.params, token_usage)
        client.conversation_history.append(ai_message)
        
        # Send complete message
        await manager.send_message(
            client_id,
            {
                "action": "stream_end",
                "message": {
                    "role": "ai",
                    "text": response_text
                },
                "conversation_id": conversation_id
            }
        )
        
        # Auto-save conversation
        await client.save_conversation(quiet=True)
        
    except Exception as e:
        logger.error(f"Error in streaming: {e}")
        import traceback
        traceback.print_exc()
        
        # Send error to client
        await manager.send_message(
            client_id,
            {
                "action": "error",
                "error": f"Error during streaming: {str(e)}"
            }
        )
