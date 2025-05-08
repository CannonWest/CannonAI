"""
WebSocket connection manager for real-time chat communication.
"""
from typing import Dict, List, Any
from fastapi import WebSocket, WebSocketDisconnect
import json
import logging
from app.logging import get_logger

logger = get_logger(__name__)

class ConnectionManager:
    """Manager for WebSocket connections."""
    
    def __init__(self):
        # Active connections: {conversation_id: [websocket1, websocket2, ...]}
        self.active_connections: Dict[int, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, conversation_id: int):
        """
        Accept a WebSocket connection and add it to active connections.
        
        Args:
            websocket: The WebSocket connection
            conversation_id: The ID of the conversation to connect to
        """
        try:
            client_host = websocket.client.host if websocket.client else "unknown"
            logger.info(f"WebSocket connection request from {client_host} for conversation {conversation_id}")
            
            await websocket.accept()
            logger.debug(f"WebSocket connection accepted for client {client_host}, conversation {conversation_id}")
            
            if conversation_id not in self.active_connections:
                self.active_connections[conversation_id] = []
            
            self.active_connections[conversation_id].append(websocket)
            logger.info(f"Client {client_host} connected to conversation {conversation_id}. Active connections: {len(self.active_connections[conversation_id])}")
            
            # Send a welcome message to confirm connection
            await websocket.send_json({
                "type": "connection_status",
                "status": "connected",
                "message": f"Connected to conversation {conversation_id}"
            })
        except Exception as e:
            logger.error(f"Error accepting WebSocket connection: {str(e)}")
            # Try to send an error message if possible
            try:
                await websocket.send_json({
                    "type": "error",
                    "error": f"Connection error: {str(e)}"
                })
            except Exception:
                # If we can't even send an error, just log it
                logger.error("Failed to send error message to client")
            raise  # Re-raise to propagate to caller
    
    def disconnect(self, websocket: WebSocket, conversation_id: int):
        """
        Remove WebSocket connection from active connections.
        
        Args:
            websocket: The WebSocket connection to remove
            conversation_id: The ID of the conversation
        """
        if conversation_id in self.active_connections:
            if websocket in self.active_connections[conversation_id]:
                self.active_connections[conversation_id].remove(websocket)
                
            # Clean up empty lists
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]
                
        logger.info(f"Client disconnected from conversation {conversation_id}")
    
    async def send_message(self, message: Any, conversation_id: int):
        """
        Send a message to all connected clients for a conversation.
        
        Args:
            message: The message to send (will be JSON serialized)
            conversation_id: The ID of the conversation to send to
        """
        if conversation_id in self.active_connections:
            disconnected = []
            
            for connection in self.active_connections[conversation_id]:
                try:
                    if isinstance(message, str):
                        await connection.send_text(message)
                    else:
                        await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message: {e}")
                    disconnected.append(connection)
            
            # Clean up any connections that failed
            for connection in disconnected:
                self.disconnect(connection, conversation_id)
    
    async def broadcast(self, message: Any):
        """
        Broadcast a message to all connected clients across all conversations.
        
        Args:
            message: The message to broadcast (will be JSON serialized)
        """
        for conversation_id in list(self.active_connections.keys()):
            await self.send_message(message, conversation_id)

# Create a singleton instance
manager = ConnectionManager()
