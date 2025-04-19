# File: src/main.py
# File: src/main.py

import os
import uuid
import logging
import asyncio
import time
import hashlib
import json
from collections import OrderedDict
from datetime import datetime
from typing import List, Dict, Optional, Any, Union, Annotated
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Body, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import httpx

# Import path configuration
from src.config.paths import PROJECT_ROOT, DATA_DIR, UPLOADS_DIR, ensure_directories

# Import models, services, and schemas
from src.models.orm_models import Conversation, Message, FileAttachment
from src.services.database.db_manager import DatabaseManager, default_db_manager
from src.services.database.conversation_service import ConversationService
from src.services.api.api_service import ApiService
from src.services.storage.settings_manager import SettingsManager
from src.utils import logging_utils

# Ensure all application directories exist
ensure_directories()

# --- Request/Response Models ---
class ConversationCreate(BaseModel):
    name: str = Field("New Conversation", min_length=1, max_length=100)
    system_message: str = Field("You are a helpful assistant.", min_length=1)

class ConversationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    system_message: Optional[str] = Field(None, min_length=1)

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    parent_id: Optional[str] = None

class MessageNavigate(BaseModel):
    message_id: str = Field(..., min_length=1)

class ApiKeyValidation(BaseModel):
    api_key: str = Field(..., min_length=1)

class SearchParams(BaseModel):
    query: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    skip: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)

# --- Configuration ---
import sys
# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.constants import DATA_DIR, DATABASE_PATH
from src.utils import logging_utils

# Configure logging first thing
logging_utils.configure_logging()
logger = logging_utils.get_logger(__name__)

# Define upload path
UPLOAD_DIR = UPLOADS_DIR
UPLOAD_DIR.mkdir(exist_ok=True)

# Define frontend path - looking at multiple possible locations
STATIC_DIR = PROJECT_ROOT / "static"
FRONTEND_DIR = PROJECT_ROOT / "src" / "frontend" / "dist"
ALTERNATIVE_FRONTEND_DIR = PROJECT_ROOT / "src" / "static"

# Check each location in order
if STATIC_DIR.exists():
    FRONTEND_DIR = STATIC_DIR
    logger.info(f"Using static files from: {FRONTEND_DIR}")
elif FRONTEND_DIR.exists():
    logger.info(f"Using frontend files from: {FRONTEND_DIR}")
elif ALTERNATIVE_FRONTEND_DIR.exists():
    FRONTEND_DIR = ALTERNATIVE_FRONTEND_DIR
    logger.info(f"Using alternative frontend files from: {FRONTEND_DIR}")
else:
    logger.warning(f"No frontend directory found. Static files will not be served.")
    FRONTEND_DIR = PROJECT_ROOT / "static"
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

# Initialize service managers
settings_manager = SettingsManager()  # Adjust constructor parameters if needed

# Dependency functions
def get_db_manager():
    return default_db_manager

def get_settings_manager():
    return settings_manager

# Create FastAPI app instance
app = FastAPI(title="CannonAI API", description="API for CannonAI Chat Application")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers in development
)

# Initialize services in a function rather than at module level
def initialize_services():
    """Initialize all application services. Only call this once when server starts."""
    global db_manager, conversation_service, api_service
    # Initialize services
    db_manager = default_db_manager
    conversation_service = ConversationService(db_manager)
    api_service = ApiService()
    # Set API key from settings
    api_key = settings_manager.get_setting("api_key")
    if api_key:
        api_service.set_api_key(api_key)
        logger.info("API key loaded from settings")
    # Return the initialized services
    return db_manager, conversation_service, api_service
    
# Declare services at module level but don't initialize them yet
db_manager = None
conversation_service = None  
api_service = None

# --- Dependencies ---
# Dependency for database sessions
def get_db():
    """Dependency for database sessions."""
    # Ensure services are initialized
    if db_manager is None:
        initialize_services()
    with db_manager.get_session() as session:
        yield session
        
# Replace the MessageCache with a more robust WebSocketMessageBuffer that prevents concurrent processing
class WebSocketMessageBuffer:
    """Prevents duplicate and concurrent processing of identical WebSocket messages"""
    
    def __init__(self):
        self.active_requests = {}  # Currently processing requests
        self.recent_requests = {}  # Recently completed requests (for deduplication)
        self.lock = asyncio.Lock()
        self.ttl_seconds = 5  # How long to remember completed requests
    
    async def start_processing(self, conversation_id, content, parent_id=None):
        """
        Attempt to start processing a message.
        Returns (True, None) if this is a new message we can process.
        Returns (False, message_id) if this message is a duplicate of a recently completed message.
        Returns (False, None) if this message is currently being processed.
        """
        # Create a unique identifier for the message
        request_id = self._create_request_id(conversation_id, content, parent_id)
        
        async with self.lock:
            # Check if we've recently completed this exact request
            if request_id in self.recent_requests:
                timestamp, message_id = self.recent_requests[request_id]
                if time.time() - timestamp < self.ttl_seconds:
                    logger.warning(f"Duplicate message detected, reusing previous result: {content[:30]}...")
                    return False, message_id
            
            # Check if we're already processing this request
            if request_id in self.active_requests:
                logger.warning(f"Concurrent message detected, ignoring: {content[:30]}...")
                return False, None
            
            # Mark this request as being processed
            self.active_requests[request_id] = time.time()
            return True, None
    
    async def complete_processing(self, conversation_id, content, parent_id=None, message_id=None):
        """Mark a request as completed and remember its result"""
        request_id = self._create_request_id(conversation_id, content, parent_id)
        
        async with self.lock:
            # Remove from active requests
            if request_id in self.active_requests:
                del self.active_requests[request_id]
            
            # Add to recent requests with result
            self.recent_requests[request_id] = (time.time(), message_id)
            
            # Clean up old entries
            self._clean_old_entries()
    
    def _create_request_id(self, conversation_id, content, parent_id=None):
        """Create a unique ID for this specific request"""
        combined = f"{conversation_id}:{content}:{parent_id or 'none'}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def _clean_old_entries(self):
        """Remove old entries from the recent requests cache"""
        now = time.time()
        to_remove = []
        
        for key, (timestamp, _) in self.recent_requests.items():
            if now - timestamp > self.ttl_seconds:
                to_remove.append(key)
        
        for key in to_remove:
            del self.recent_requests[key]

# Create a single buffer instance
ws_buffer = WebSocketMessageBuffer()

# --- Conversation Endpoints ---
@app.get("/api/conversations", response_model=List[Dict])
async def get_conversations(
    skip: int = 0,
    limit: int = 100,
    db_manager = Depends(get_db_manager)
):
    try:
        async with db_manager.get_session() as session:
            # Use the injected db_manager instance
            conversations = await db_manager.get_conversations(session, skip=skip, limit=limit)
            return conversations
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving conversations: {str(e)}")
    
@app.post("/api/conversations", response_model=Dict)
async def create_conversation(
    data: ConversationCreate
):
    """Create a new conversation."""
    async with db_manager.get_session() as session:
        conversation = await conversation_service.create_conversation(
            session,
            name=data.name,
            system_message=data.system_message
        )
        return conversation.to_dict()

@app.get("/api/conversations/{conversation_id}", response_model=Dict)
async def get_conversation(
    conversation_id: str
):
    """Get a conversation by ID."""
    async with db_manager.get_session() as session:
        conversation = await conversation_service.get_conversation_with_messages(session, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation.to_dict()
        
@app.put("/api/conversations/{conversation_id}", response_model=Dict)
async def update_conversation(
    conversation_id: str,
    data: ConversationUpdate
):
    """Update a conversation."""
    # Convert model to dict, excluding None values
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    async with db_manager.get_session() as session:
        conversation = await conversation_service.update_conversation(session, conversation_id, update_data)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation.to_dict()

@app.delete("/api/conversations/{conversation_id}", response_model=Dict)
async def delete_conversation(
    conversation_id: str
):
    """Delete a conversation."""
    async with db_manager.get_session() as session:
        success = await conversation_service.delete_conversation(session, conversation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"success": True, "id": conversation_id}
    
@app.post("/api/conversations/{conversation_id}/duplicate", response_model=Dict)
async def duplicate_conversation(
    conversation_id: str,
    new_name: Optional[str] = None
):  
    """Duplicate a conversation."""
    async with db_manager.get_session() as session:
        new_conversation = await conversation_service.duplicate_conversation(session, conversation_id, new_name)
        if not new_conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return new_conversation.to_dict()
    
# --- Message Endpoints ---
@app.get("/api/conversations/{conversation_id}/messages", response_model=List[Dict])
async def get_messages(
    conversation_id: str
):
    """Get all messages for a conversation."""
    async with db_manager.get_session() as session:
        conversation = await conversation_service.get_conversation_with_messages(session, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return [message.to_dict() for message in conversation.messages]

@app.post("/api/conversations/{conversation_id}/messages", response_model=Dict)
async def add_user_message(
    conversation_id: str,
    data: MessageCreate
):
    """Add a user message to a conversation."""
    async with db_manager.get_session() as session:
        message = await conversation_service.add_user_message(
            session,
            conversation_id=conversation_id,
            content=data.content,
            parent_id=data.parent_id
        )
        if not message:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return message.to_dict()
         
@app.post("/api/conversations/{conversation_id}/navigate", response_model=Dict)
async def navigate_to_message(
    conversation_id: str,
    data: MessageNavigate
):
    """Navigate to a specific message in the conversation."""
    async with db_manager.get_session() as session:
        success = await conversation_service.navigate_to_message(
            session,
            conversation_id=conversation_id,
            message_id=data.message_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Conversation or message not found")
        return {"success": True, "conversation_id": conversation_id, "message_id": data.message_id}

# --- Settings Endpoints ---
@app.get("/api/settings", response_model=Dict)
async def get_settings(
    settings_manager = Depends(get_settings_manager)
):
    try:
        # Add a debug log to see what's happening
        print(f"Settings manager: {settings_manager}")
        settings = await settings_manager.get_settings()
        return settings
    except Exception as e:
        # Log the specific error
        import traceback
        print(f"Error retrieving settings: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving settings: {str(e)}")

@app.post("/api/settings", response_model=Dict)
async def save_settings(
    settings: Dict = Body(...)
):
    """Save application settings."""
    # Handle API key specially
    if "api_key" in settings and isinstance(settings["api_key"], str) and settings["api_key"]:
        api_key = settings["api_key"]
        # Set the API key in the API service
        api_service.set_api_key(api_key)
    updated_settings = settings_manager.update_settings(settings)
    return settings_manager.get_frontend_settings()

@app.post("/api/settings/reset", response_model=Dict)
async def reset_settings():
    """Reset settings to defaults."""
    settings_manager.reset_to_defaults()
    return settings_manager.get_frontend_settings()

# --- API Key Validation Endpoint ---
@app.post("/api/validate-api-key", response_model=Dict)
async def validate_api_key(data: ApiKeyValidation):
    """Validate an OpenAI API key."""
    is_valid, message = await api_service.validate_api_key(data.api_key)
    if is_valid:
        # Save valid API key to settings
        settings_manager.update_setting("api_key", data.api_key)
        # Set in API service for immediate use
        api_service.set_api_key(data.api_key)
    return {"valid": is_valid, "message": message}

# --- Chat Streaming Endpoint ---
@app.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(websocket: WebSocket, conversation_id: str):
    """WebSocket endpoint for chat with a specific conversation."""
    await websocket.accept()
    logger.info(f"WebSocket connection open for conversation {conversation_id}")

    # Get the initial conversation data
    try:
        async with db_manager.get_session() as session:
            conversation = await conversation_service.get_conversation(session, conversation_id)
            if not conversation:
                logger.warning(f"Conversation not found: {conversation_id}")
                await websocket.send_json({"error": "Conversation not found"})
                return
                
            # Store only the ID, not the entire object which would be detached
            conversation_id = conversation.id 
            initial_node_id = conversation.current_node_id
            
        while True:
            try:
                # Wait for a message from the client
                message_raw = await websocket.receive_text()
                
                # Parse the message
                try:
                    message_data = json.loads(message_raw)
                    message_type = message_data.get("type", "message")
                except Exception as e:
                    logger.error(f"Error receiving message: {e}", exc_info=True)
                    await websocket.send_json({"error": f"Message error: {str(e)}"})
                    continue
                
                # Process the user message
                if message_type == "message" and "content" in message_data:
                    content = message_data["content"]
                    
                    # Get the parent ID from the database within a fresh session
                    parent_id = None
                    try:
                        async with db_manager.get_session() as session:
                            conversation = await conversation_service.get_conversation(session, conversation_id)
                            parent_id = conversation.current_node_id
                    except Exception as db_error:
                        logger.error(f"Error retrieving parent message ID: {db_error}", exc_info=True)
                        await websocket.send_json({"error": f"Failed to process message: {str(db_error)}"})
                        continue
                    
                    # Add the message to the database
                    try:
                        async with db_manager.get_session() as session:
                            user_message = await conversation_service.add_message(
                                session,
                                conversation_id,
                                "user",
                                content,
                                parent_id=parent_id
                            )
                            await websocket.send_json({
                                "type": "user_message",
                                "message": user_message.to_dict(),
                                "status": "new"
                            })
                    except Exception as db_error:
                        logger.error(f"Error creating user message: {db_error}", exc_info=True)
                        await websocket.send_json({"error": f"Failed to create message: {str(db_error)}"})
                        continue
                        
            except Exception as processing_error:
                logger.error(f"Unexpected error processing message: {processing_error}", exc_info=True)
                # Send a specific error type that the frontend can recognize and handle
                await websocket.send_json({
                    "type": "error", 
                    "message": f"Server error: {str(processing_error)}",
                    "code": "processing_failed"  # Add an error code for the frontend to identify
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket connection closed for conversation {conversation_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass
    finally:
        logger.info(f"Closing WebSocket for conversation {conversation_id}")

# --- Serve Frontend Static Files ---
# Mount the frontend static files
if FRONTEND_DIR.exists():
    logger.info(f"Mounting frontend files from {FRONTEND_DIR}")
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    
    # Serve favicon and manifest from static directory
    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        favicon_path = FRONTEND_DIR / "favicon.ico"
        if favicon_path.exists():
            return FileResponse(str(favicon_path))
        return Response(status_code=404)
    
    @app.get("/manifest.json", include_in_schema=False)
    def manifest():
        manifest_path = FRONTEND_DIR / "manifest.json"
        if manifest_path.exists():
            return FileResponse(str(manifest_path))
        return Response(status_code=404)
    
    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        """Serve the frontend for any non-API routes."""
        logger.debug(f"Serving frontend path: {full_path}")
        # If the path exists, serve it directly
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # Otherwise, serve index.html (for SPAs to handle routing)
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        # If index.html doesn't exist, return a helpful error
        return Response(
            content=f"Frontend not found at {FRONTEND_DIR}. Please build the frontend or check paths.",
            status_code=404,
            media_type="text/plain"
        )

# --- Main Entry Point ---
def main():
    """Main entry point for the application."""
    import uvicorn
    
    # Set environment variable for development mode
    os.environ["ENVIRONMENT"] = "development"
    
    # Initialize services here, before starting the server
    global db_manager, conversation_service, api_service
    db_manager, conversation_service, api_service = initialize_services()
    
    # Ensure database is initialized
    if not db_manager.ping():
        logger.warning("Database connection failed. Attempting to create tables...")
        db_manager.create_tables()
    
    # Improve logging
    logger.info(f"Starting FastAPI server with frontend from: {FRONTEND_DIR}")
    logger.info(f"Database file location: {db_manager.db_url}")
    
    # Define explicitly which directories to watch (exclude data and logs)
    watch_dirs = [
        str(Path(__file__).parent),  # src directory
        str(Path(__file__).parent / "frontend" / "src"),  # frontend source
    ]
    
    # Start the server with explicit reload directories
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting FastAPI server on port {port}")
    logger.info(f"Logs will be written to: {logging_utils.LOGS_DIR}")
    uvicorn.run(
        "src.main:app", 
        host="0.0.0.0", 
        port=port, 
        reload=True, 
        log_level="info"
    )
    
    return 0

# Run the application (for development)
if __name__ == "__main__":
    main()