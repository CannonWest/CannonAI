"""
Main FastAPI application for CannonAI.
Provides API endpoints for conversations, messages, and AI interactions.
"""

import os
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any, Union
from pathlib import Path

# FastAPI imports
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, status
from fastapi import UploadFile, File, Form, Path as PathParam, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
import uvicorn

# Pydantic models for request/response validation
from pydantic import BaseModel, Field, validator

# Import models, services, and schemas
from src.models.orm_models import Conversation, Message, FileAttachment
from src.services.database.db_manager import DatabaseManager, default_db_manager
from src.services.database.conversation_service import ConversationService
from src.services.api.api_service import ApiService
from src.services.storage.settings_manager import SettingsManager

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

class ApiKeyValidation(BaseModel):
    api_key: str = Field(..., min_length=1)

class SearchParams(BaseModel):
    query: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    skip: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)

# --- Configuration ---

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log"),
    ],
)

logger = logging.getLogger(__name__)

# Define upload path
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

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

# Create FastAPI app
app = FastAPI(
    title="CannonAI API",
    description="API for CannonAI chat application",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Configure CORS
origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Exception Handlers ---

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )

# --- Dependencies ---

# Dependency for database sessions
def get_db():
    """Dependency for database sessions."""
    with db_manager.get_session() as session:
        yield session

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"WebSocket connected: {client_id}")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"WebSocket disconnected: {client_id}")

    async def send_message(self, client_id: str, message: Dict[str, Any]):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)

    async def broadcast(self, message: Dict[str, Any]):
        """Send a message to all connected clients."""
        for client_id in list(self.active_connections.keys()):
            try:
                await self.send_message(client_id, message)
            except Exception as e:
                logger.error(f"Error broadcasting to {client_id}: {e}")
                self.disconnect(client_id)

manager = ConnectionManager()

# Serve static files (React/Vue/Angular build)
STATIC_DIR = Path("static")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")
    logger.info(f"Serving static files from {STATIC_DIR}")

# --- Health Check ---

@app.get("/api/health")
async def health_check():
    """Check if the API is running."""
    db_status = "online" if db_manager.ping() else "offline"
    return {
        "status": "healthy",
        "version": "1.0.0",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat()
    }

# --- Conversation Routes ---

@app.get("/api/conversations")
async def get_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get all conversations with pagination."""
    conversations = conversation_service.get_all_conversations(db, skip, limit)
    return [conv.to_dict() for conv in conversations]

@app.post("/api/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db)
):
    """Create a new conversation."""
    conversation = conversation_service.create_conversation(db, data.name, data.system_message)
    return conversation.to_dict()

@app.get("/api/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str = PathParam(...),
    db: Session = Depends(get_db)
):
    """Get a specific conversation by ID."""
    conversation = conversation_service.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation.to_dict()

@app.put("/api/conversations/{conversation_id}")
async def update_conversation(
    data: ConversationUpdate,
    conversation_id: str = PathParam(...),
    db: Session = Depends(get_db)
):
    """Update a conversation."""
    # Filter out None values
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    if not update_data:
        return {"detail": "No updates provided"}

    conversation = conversation_service.update_conversation(db, conversation_id, update_data)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation.to_dict()

@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str = PathParam(...),
    db: Session = Depends(get_db)
):
    """Delete a conversation."""
    success = conversation_service.delete_conversation(db, conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}

@app.post("/api/conversations/{conversation_id}/duplicate")
async def duplicate_conversation(
    conversation_id: str = PathParam(...),
    new_name: Optional[str] = Body(None),
    db: Session = Depends(get_db)
):
    """Duplicate a conversation."""
    conversation = conversation_service.duplicate_conversation(db, conversation_id, new_name)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found or duplication failed")
    return conversation.to_dict()

# --- Message Routes ---

@app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str = PathParam(...),
    db: Session = Depends(get_db)
):
    """Get all messages for a conversation."""
    conversation = conversation_service.get_conversation_with_messages(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Sort messages to ensure they're in chronological order
    sorted_messages = sorted(conversation.messages, key=lambda msg: msg.timestamp)
    return [msg.to_dict() for msg in sorted_messages]

@app.get("/api/messages/{message_id}/branch")
async def get_message_branch(
    message_id: str = PathParam(...),
    db: Session = Depends(get_db)
):
    """Get the branch of messages from root to the specified message."""
    branch = conversation_service.get_message_branch(db, message_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Message not found")
    return [msg.to_dict() for msg in branch]

@app.post("/api/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def add_message(
    data: MessageCreate,
    conversation_id: str = PathParam(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """Add a user message and trigger assistant response."""
    # First add the user message
    user_message = conversation_service.add_user_message(db, conversation_id, data.content, data.parent_id)
    if not user_message:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Start background task to process assistant response
    if background_tasks:
        background_tasks.add_task(
            process_assistant_response,
            conversation_id=conversation_id,
            user_message_id=user_message.id
        )

    return user_message.to_dict()

async def process_assistant_response(conversation_id: str, user_message_id: str):
    """Process assistant response in the background."""
    with db_manager.get_session() as db:
        # Get the message branch
        branch = conversation_service.get_message_branch(db, user_message_id)
        if not branch:
            logger.error(f"Could not find message branch for {user_message_id}")
            return

        # Get settings
        settings = settings_manager.get_settings()

        try:
            # Stream response if WebSocket is active
            client_id = f"conversation_{conversation_id}"
            has_websocket = client_id in manager.active_connections

            if has_websocket and settings.get("stream", True):
                # Stream via WebSocket
                content_buffer = []

                async for chunk in api_service.get_streaming_completion_async(branch, settings):
                    # Process chunk based on API type
                    api_type = settings.get("api_type", "responses")

                    if api_type == "responses":
                        event_type = chunk.get('type')
                        if event_type == 'response.output_text.delta' and 'delta' in chunk:
                            text_chunk = chunk['delta']
                            content_buffer.append(text_chunk)
                            await manager.send_message(client_id, {
                                "type": "stream",
                                "content": text_chunk
                            })
                    else:  # chat_completions
                        if 'choices' in chunk and chunk['choices']:
                            delta = chunk['choices'][0].get('delta', {})
                            if 'content' in delta and delta['content']:
                                text_chunk = delta['content']
                                content_buffer.append(text_chunk)
                                await manager.send_message(client_id, {
                                    "type": "stream",
                                    "content": text_chunk
                                })

                # Save the complete response
                content = "".join(content_buffer)

                # Get metadata from api_service
                metadata = {
                    "model_info": api_service.last_model,
                    "token_usage": api_service.last_token_usage,
                    "reasoning_steps": api_service.last_reasoning_steps,
                    "response_id": api_service.last_response_id
                }

                # Add assistant message to database
                assistant_message = conversation_service.add_assistant_message(
                    db,
                    conversation_id,
                    content,
                    parent_id=user_message_id,
                    model_info=metadata.get("model_info"),
                    token_usage=metadata.get("token_usage"),
                    reasoning_steps=metadata.get("reasoning_steps"),
                    response_id=metadata.get("response_id")
                )

                # Notify completion
                if assistant_message:
                    await manager.send_message(client_id, {
                        "type": "complete",
                        "message": assistant_message.to_dict()
                    })
            else:
                # Non-streaming response
                response = await api_service.get_completion_async(branch, settings)

                # Add assistant message to database
                assistant_message = conversation_service.add_assistant_message(
                    db,
                    conversation_id,
                    response.get("content", ""),
                    parent_id=user_message_id,
                    model_info=response.get("model"),
                    token_usage=response.get("token_usage"),
                    reasoning_steps=response.get("reasoning_steps"),
                    response_id=response.get("response_id")
                )

                # Notify via WebSocket if available
                if has_websocket and assistant_message:
                    await manager.send_message(client_id, {
                        "type": "message",
                        "message": assistant_message.to_dict()
                    })

        except Exception as e:
            logger.error(f"Error processing assistant response: {e}", exc_info=True)
            # Notify error via WebSocket if available
            if client_id in manager.active_connections:
                await manager.send_message(client_id, {
                    "type": "error",
                    "message": str(e)
                })

@app.post("/api/conversations/{conversation_id}/retry")
async def retry_last_response(
    conversation_id: str = PathParam(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """Retry the last assistant response for this conversation."""
    # Get the conversation
    conversation = conversation_service.get_conversation(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get the current message
    current_message = db.get(Message, conversation.current_node_id)
    if not current_message:
        raise HTTPException(status_code=404, detail="Current message not found")

    # Find the parent user message
    if current_message.role == "assistant" and current_message.parent_id:
        user_message_id = current_message.parent_id
    else:
        # If current message is not an assistant message or has no parent
        raise HTTPException(status_code=400, detail="Cannot retry: current message is not an assistant response")

    # Start background task to process new assistant response
    if background_tasks:
        background_tasks.add_task(
            process_assistant_response,
            conversation_id=conversation_id,
            user_message_id=user_message_id
        )

    return {"status": "Retry in progress"}

@app.post("/api/conversations/{conversation_id}/navigate/{message_id}")
async def navigate_to_message(
    conversation_id: str = PathParam(...),
    message_id: str = PathParam(...),
    db: Session = Depends(get_db)
):
    """Navigate to a specific message in the conversation."""
    success = conversation_service.navigate_to_message(db, conversation_id, message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Navigation failed")
    return {"success": True}

# --- Settings Routes ---

@app.get("/api/settings")
async def get_settings():
    """Get application settings (for frontend)."""
    return settings_manager.get_frontend_settings()

@app.put("/api/settings")
async def update_settings(settings: Dict[str, Any] = Body(...)):
    """Update application settings."""
    updated = settings_manager.update_settings(settings)

    # Update API key in ApiService if present
    if "api_key" in settings and settings["api_key"]:
        api_service.set_api_key(settings["api_key"])

    return updated

@app.post("/api/settings/validate-api-key")
async def validate_api_key(data: ApiKeyValidation):
    """Validate an API key."""
    is_valid, message = await api_service.validate_api_key(data.api_key)
    return {"valid": is_valid, "message": message}

@app.post("/api/settings/reset-to-defaults")
async def reset_settings_to_defaults():
    """Reset settings to defaults (preserving API key)."""
    return settings_manager.reset_to_defaults()

# --- Search Routes ---

@app.get("/api/search")
async def search_messages(
    query: str = Query(..., min_length=1),
    conversation_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Search for messages containing the query text."""
    results = conversation_service.search_conversations(db, query, conversation_id, skip, limit)
    return results

# --- WebSocket Route ---

@app.websocket("/api/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for streaming responses."""
    await manager.connect(websocket, client_id)
    try:
        while True:
            # Keep connection alive and wait for messages
            data = await websocket.receive_json()
            # Here you could handle client-to-server messages if needed

            # Example of handling incoming messages:
            if "type" in data:
                if data["type"] == "ping":
                    await manager.send_message(client_id, {"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(client_id)

# --- File Routes ---

@app.post("/api/files")
async def upload_file(
    file: UploadFile = File(...),
):
    """Upload a file and return metadata."""
    # Create a unique ID for the file
    file_id = str(uuid.uuid4())

    # Get file content and metadata
    content = await file.read()
    file_size = len(content)

    # Sanitize filename to prevent path traversal attacks
    safe_filename = os.path.basename(file.filename)

    # Save file to disk
    file_path = UPLOAD_DIR / f"{file_id}_{safe_filename}"
    with open(file_path, "wb") as f:
        f.write(content)

    # Get MIME type
    mime_type = file.content_type or "application/octet-stream"

    # TODO: Count tokens if it's a text file
    token_count = 0
    if mime_type.startswith("text/") or mime_type in ("application/json", "application/xml"):
        # Implement token counting here
        pass

    return {
        "id": file_id,
        "file_name": safe_filename,
        "mime_type": mime_type,
        "file_size": file_size,
        "token_count": token_count,
        "file_path": str(file_path)
    }

@app.get("/api/files/{file_id}")
async def get_file(file_id: str = PathParam(...)):
    """Download a file by ID."""
    # Find the file in the uploads directory
    for filename in os.listdir(UPLOAD_DIR):
        if filename.startswith(file_id):
            file_path = UPLOAD_DIR / filename
            return FileResponse(
                path=file_path,
                filename=filename[len(file_id)+1:],  # Original filename without ID prefix
                media_type="application/octet-stream"
            )

    raise HTTPException(status_code=404, detail="File not found")

@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str = PathParam(...)):
    """Delete an uploaded file."""
    # Find the file in the uploads directory
    for filename in os.listdir(UPLOAD_DIR):
        if filename.startswith(file_id):
            file_path = UPLOAD_DIR / filename
            os.remove(file_path)
            return {"success": True}

    raise HTTPException(status_code=404, detail="File not found")

@app.post("/api/messages/{message_id}/attachments")
async def add_file_attachment(
    message_id: str = PathParam(...),
    file_info: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """Add a file attachment to a message."""
    attachment = conversation_service.add_file_attachment(db, message_id, file_info)
    if not attachment:
        raise HTTPException(status_code=404, detail="Message not found")
    return attachment.to_dict()

# --- Main Routes ---

@app.get("/")
async def root():
    """Serve the frontend application."""
    index_path = Path("static/index.html")
    if index_path.exists():
        return FileResponse(index_path)
    else:
        return {"message": "CannonAI API Server is running. Frontend not yet deployed."}

@app.get("/{path:path}")
async def catch_all(path: str):
    """Catch-all route to serve the frontend for client-side routing."""
    index_path = Path("static/index.html")
    if index_path.exists():
        return FileResponse(index_path)
    else:
        raise HTTPException(status_code=404, detail="Resource not found")

# Run the application (for development)
if __name__ == "__main__":
    # Ensure db is initialized
    if not db_manager.ping():
        logger.warning("Database connection failed. Attempting to create tables...")
        db_manager.create_tables()

    # Start the server
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting FastAPI server on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)