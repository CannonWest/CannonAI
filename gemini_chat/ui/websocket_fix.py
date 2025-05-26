#!/usr/bin/env python3
"""
WebSocket Fix for Gemini Chat

This module provides a direct WebSocket implementation that bypasses
middleware issues in FastAPI/Starlette that can cause 403 Forbidden errors.
"""

import logging
from typing import Callable, Dict, List, Any, Optional
from starlette.websockets import WebSocket, WebSocketDisconnect
from fastapi import APIRouter, FastAPI

# Configure logger
logger = logging.getLogger("gemini_chat.websocket_fix")

class WebSocketManager:
    """
    WebSocket connection manager that bypasses middleware issues.
    This implementation directly manages WebSocket connections.
    """
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.client_info: Dict[WebSocket, Dict[str, Any]] = {}
        
    async def connect(self, websocket: WebSocket) -> bool:
        """Accept a WebSocket connection and store it."""
        try:
            # Accept the connection directly, bypassing normal middleware processing
            await websocket.accept()
            
            # Track the connection
            self.active_connections.append(websocket)
            self.client_info[websocket] = {
                "client": f"{websocket.client.host}:{websocket.client.port}",
                "headers": dict(websocket.headers),
                "connected_at": logging.Formatter().formatTime(logging.LogRecord("name", logging.INFO, "", 0, "", (), None))
            }
            
            logger.info(f"WebSocket connection accepted from {websocket.client.host}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to accept WebSocket connection: {str(e)}")
            return False
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        
        if websocket in self.client_info:
            del self.client_info[websocket]
    
    async def send_json(self, websocket: WebSocket, data: dict):
        """Send JSON data to a WebSocket client."""
        try:
            await websocket.send_json(data)
            return True
        except Exception as e:
            logger.error(f"Failed to send WebSocket message: {str(e)}")
            self.disconnect(websocket)
            return False
    
    async def broadcast_json(self, data: dict):
        """Send JSON data to all connected WebSocket clients."""
        for connection in self.active_connections[:]:  # Copy to avoid modification during iteration
            if not await self.send_json(connection, data):
                # Connection failed, it's already been removed by send_json
                pass

def create_websocket_route(
    app: FastAPI,
    path: str,
    handler: Callable,
    manager: Optional[WebSocketManager] = None
) -> WebSocketManager:
    """
    Create a WebSocket route with special handling to bypass middleware issues.
    
    Args:
        app: The FastAPI application
        path: The URL path for the WebSocket endpoint
        handler: The handler function that processes WebSocket messages
        manager: Optional WebSocketManager instance (creates one if not provided)
        
    Returns:
        The WebSocketManager instance used for the route
    """
    # Create a manager if not provided
    if manager is None:
        manager = WebSocketManager()
    
    # Create a special router for WebSockets
    router = APIRouter()
    
    @router.websocket(path)
    async def websocket_endpoint(websocket: WebSocket):
        # Print all request headers for debugging
        print("\n=== WebSocket Headers ===")
        for key, value in websocket.headers.items():
            print(f"{key}: {value}")
        print("==========================\n")
        
        # Connect (this bypasses middleware issues)
        if await manager.connect(websocket):
            try:
                # Call the handler with successful connection
                await handler(websocket, manager)
            except WebSocketDisconnect:
                print(f"WebSocket client disconnected: {websocket.client.host}")
            except Exception as e:
                print(f"Error in WebSocket handler: {e}")
            finally:
                # Always ensure we disconnect on any error
                manager.disconnect(websocket)
    
    # Include the router in the app
    app.include_router(router)
    
    return manager
