# File: src/main.py

import os
import uuid
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Any, Union, Annotated
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Body, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

# Import path configuration
from src.config.paths import PROJECT_ROOT, DATA_DIR, UPLOADS_DIR, ensure_directories

# Import models, services, and schemas
from src.models.orm_models import Conversation, Message, FileAttachment
from src.services.database.db_manager import DatabaseManager, default_db_manager
from src.services.database.conversation_service import ConversationService
from src.services.api.api_service import ApiService
from src.services.storage.settings_manager import SettingsManager

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

# Initialize services
db_manager = default_db_manager
conversation_service = ConversationService(db_manager)
settings_manager = SettingsManager()
api_service = ApiService()

# Set API key from settings
api_key = settings_manager.get_setting("api_key")
if api_key:
    api_service.set_api_key(api_key)
    logger.info("API key loaded from settings")

# --- FastAPI App Configuration ---
app = FastAPI(title="CannonAI API", description="API for CannonAI Chat Application")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# --- Dependencies ---

# Dependency for database sessions
def get_db():
    """Dependency for database sessions."""
    with db_manager.get_session() as session:
        yield session

# --- Conversation Endpoints ---

@app.get("/api/conversations", response_model=List[Dict])
def get_conversations(
    skip: int = 0, 
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get all conversations with pagination."""
    conversations = conversation_service.get_all_conversations(db, skip, limit)
    return [conv.to_dict() for conv in conversations]

@app.post("/api/conversations", response_model=Dict)
def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db)
):
    """Create a new conversation."""
    conversation = conversation_service.create_conversation(
        db, 
        name=data.name,
        system_message=data.system_message
    )
    return conversation.to_dict()

@app.get("/api/conversations/{conversation_id}", response_model=Dict)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """Get a conversation by ID."""
    conversation = conversation_service.get_conversation_with_messages(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation.to_dict()

@app.put("/api/conversations/{conversation_id}", response_model=Dict)
def update_conversation(
    conversation_id: str,
    data: ConversationUpdate,
    db: Session = Depends(get_db)
):
    """Update a conversation."""
    # Convert model to dict, excluding None values
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    
    conversation = conversation_service.update_conversation(db, conversation_id, update_data)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return conversation.to_dict()

@app.delete("/api/conversations/{conversation_id}", response_model=Dict)
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """Delete a conversation."""
    success = conversation_service.delete_conversation(db, conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"success": True, "id": conversation_id}

@app.post("/api/conversations/{conversation_id}/duplicate", response_model=Dict)
def duplicate_conversation(
    conversation_id: str,
    new_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Duplicate a conversation."""
    new_conversation = conversation_service.duplicate_conversation(db, conversation_id, new_name)
    if not new_conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return new_conversation.to_dict()

# --- Message Endpoints ---

@app.get("/api/conversations/{conversation_id}/messages", response_model=List[Dict])
def get_messages(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """Get all messages for a conversation."""
    conversation = conversation_service.get_conversation_with_messages(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return [message.to_dict() for message in conversation.messages]

@app.post("/api/conversations/{conversation_id}/messages", response_model=Dict)
def add_user_message(
    conversation_id: str,
    data: MessageCreate,
    db: Session = Depends(get_db)
):
    """Add a user message to a conversation."""
    message = conversation_service.add_user_message(
        db, 
        conversation_id=conversation_id,
        content=data.content,
        parent_id=data.parent_id
    )
    
    if not message:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return message.to_dict()

@app.post("/api/conversations/{conversation_id}/navigate", response_model=Dict)
def navigate_to_message(
    conversation_id: str,
    data: MessageNavigate,
    db: Session = Depends(get_db)
):
    """Navigate to a specific message in the conversation."""
    success = conversation_service.navigate_to_message(
        db,
        conversation_id=conversation_id,
        message_id=data.message_id
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Conversation or message not found")
    
    return {"success": True, "conversation_id": conversation_id, "message_id": data.message_id}

# --- Settings Endpoints ---

@app.get("/api/settings", response_model=Dict)
def get_settings():
    """Get application settings."""
    return settings_manager.get_frontend_settings()

@app.post("/api/settings", response_model=Dict)
def save_settings(
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
def reset_settings():
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
    """WebSocket endpoint for streaming chat responses."""
    await websocket.accept()
    
    try:
        # Get the conversation
        with db_manager.get_session() as db:
            conversation = conversation_service.get_conversation(db, conversation_id)
            if not conversation:
                await websocket.send_json({"error": "Conversation not found"})
                await websocket.close()
                return
        
        while True:
            # Wait for the client to send a message
            data = await websocket.receive_json()
            
            # Extract message content and parent ID
            content = data.get("content")
            parent_id = data.get("parent_id")
            
            if not content:
                await websocket.send_json({"error": "Message content is required"})
                continue
            
            # Add user message to conversation
            with db_manager.get_session() as db:
                user_message = conversation_service.add_user_message(
                    db, 
                    conversation_id=conversation_id,
                    content=content,
                    parent_id=parent_id
                )
                
                if not user_message:
                    await websocket.send_json({"error": "Failed to add user message"})
                    continue
                
                # Send confirmation that user message was added
                await websocket.send_json({
                    "type": "user_message",
                    "message": user_message.to_dict()
                })
                
                # Get current settings for API call
                settings = settings_manager.get_settings()
                
                # Force streaming to be enabled
                settings["stream"] = True
                
                # Prepare message list for API
                messages = []
                
                # Get the conversation branch up to the current message
                message_branch = conversation_service.get_message_branch(db, user_message.id)
                
                # Add system message
                messages.append({
                    "role": "system",
                    "content": conversation.system_message
                })
                
                # Add conversation messages (excluding system message)
                for msg in message_branch:
                    if msg.role != "system":
                        messages.append({
                            "role": msg.role,
                            "content": msg.content
                        })
            
            # Call the API with streaming and send chunks to WebSocket
            try:
                # Initialize empty content
                streamed_content = ""
                
                # Create an async generator from streaming API
                async for chunk in api_service.get_streaming_completion_async(messages, settings):
                    # Extract and accumulate content
                    if chunk.get("type") == "content_block_delta":
                        delta = chunk.get("delta", {}).get("text", "")
                        streamed_content += delta
                        # Send the delta to the client
                        await websocket.send_json({
                            "type": "assistant_message_delta",
                            "delta": delta
                        })
                    elif chunk.get("type") == "response.thinking_step":
                        # Send reasoning step
                        await websocket.send_json({
                            "type": "reasoning_step",
                            "step": chunk.get("thinking_step", {})
                        })
                    elif chunk.get("type") == "response.completed":
                        # Final message with metadata
                        metadata = {
                            "token_usage": api_service.last_token_usage,
                            "model": api_service.last_model,
                            "response_id": api_service.last_response_id
                        }
                        await websocket.send_json({
                            "type": "assistant_message_complete",
                            "metadata": metadata
                        })
                
                # Save the complete message to the database
                with db_manager.get_session() as db:
                    assistant_message = conversation_service.add_assistant_message(
                        db,
                        conversation_id=conversation_id,
                        content=streamed_content,
                        parent_id=user_message.id,
                        model_info={"model": api_service.last_model},
                        token_usage=api_service.last_token_usage,
                        reasoning_steps=api_service.last_reasoning_steps,
                        response_id=api_service.last_response_id
                    )
                    
                    if assistant_message:
                        # Send the complete message object
                        await websocket.send_json({
                            "type": "assistant_message_saved",
                            "message": assistant_message.to_dict()
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Failed to save assistant message"
                        })
            
            except Exception as e:
                logger.error(f"Error in streaming chat: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for conversation {conversation_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass

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
    
    # Ensure database is initialized
    if not db_manager.ping():
        logger.warning("Database connection failed. Attempting to create tables...")
        db_manager.create_tables()
    
    # Improve logging
    logger.info(f"Starting FastAPI server with frontend from: {FRONTEND_DIR}")
    logger.info(f"Database file location: {db_manager.db_url}")
    
    # Start the server
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting FastAPI server on port {port}")
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, reload=True, log_level="info")
    
    return 0

# Run the application (for development)
if __name__ == "__main__":
    main()