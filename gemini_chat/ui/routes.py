"""
API route definitions for the Gemini Chat web interface.

This module provides the RESTful API endpoints for interacting with Gemini Chat.
"""

import asyncio
import json
import logging
import uuid
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Depends, Body, Query, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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

# ----- Pydantic Models for Request/Response -----

class Message(BaseModel):
    """Message model for requests and responses"""
    role: str
    text: str
    timestamp: Optional[str] = None

class NewConversationRequest(BaseModel):
    """Request model for creating a new conversation"""
    title: str = Field(..., description="Title for the new conversation")
    model: Optional[str] = Field(None, description="Model to use for this conversation")

class MessageRequest(BaseModel):
    """Request model for sending a message"""
    message: str = Field(..., description="Message to send")
    conversation_id: Optional[str] = Field(None, description="Conversation ID (if None, uses active conversation)")

class ConversationMetadata(BaseModel):
    """Model for conversation metadata"""
    conversation_id: str
    title: str
    model: str
    message_count: int
    created_at: str
    updated_at: str

class ModelInfo(BaseModel):
    """Model for information about available models"""
    name: str
    display_name: str
    input_token_limit: int
    output_token_limit: int

class ConfigInfo(BaseModel):
    """Model for configuration information"""
    api_key_set: bool
    conversations_dir: str
    default_model: str
    generation_params: Dict[str, Any]

class UpdateConfigRequest(BaseModel):
    """Request model for updating configuration"""
    api_key: Optional[str] = None
    conversations_dir: Optional[str] = None
    default_model: Optional[str] = None
    generation_params: Optional[Dict[str, Any]] = None

# ----- Helper Functions -----

def get_client_id(request_obj):
    """Get a unique client ID from cookies or create a new one
    
    Args:
        request_obj: Either a Request object or dict
        
    Returns:
        A client ID string
    """
    client_id = None
    
    # If request_obj is an actual Request object
    if hasattr(request_obj, 'cookies') and callable(getattr(request_obj, 'cookies', None)):
        client_id = request_obj.cookies.get("client_id")
    
    # If it's a dict or no client_id in cookies, generate a new one
    if not client_id:
        client_id = str(uuid.uuid4())
        logger.info(f"Generated new client ID: {client_id}")
        
    return client_id

async def get_or_create_client(app: FastAPI, client_id: str):
    """Get an existing client or create a new one"""
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

# ----- API Routes -----

def setup_routes(app: FastAPI) -> None:
    """Set up all API routes for the application
    
    Args:
        app: The FastAPI application
    """
    # Create API router
    api_router = APIRouter(prefix="/api")
    
    # ----- Conversation Management -----
    
    @api_router.post("/conversations", response_model=Dict[str, str])
    async def create_conversation(
        request: NewConversationRequest,
        request_obj: Request,
    ):
        """Create a new conversation"""
        client_id = get_client_id(request_obj)
        client = await get_or_create_client(app, client_id)
        
        try:
            # Create new conversation
            conversation_id = client.generate_conversation_id()
            title = request.title
            model = request.model or client.model
            
            # Create metadata
            metadata = client.create_metadata_structure(title, model, client.params)
            
            # Set as active conversation
            client.conversation_id = conversation_id
            client.conversation_history = [metadata]
            
            # Save conversation
            await client.save_conversation()
            
            # Track active conversation
            app.state.active_conversations[client_id] = conversation_id
            
            return {
                "conversation_id": conversation_id,
                "title": title,
            }
        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @api_router.get("/conversations", response_model=List[ConversationMetadata])
    async def list_conversations(
        request_obj: Request,
    ):
        """List all conversations"""
        client_id = get_client_id(request_obj)
        client = await get_or_create_client(app, client_id)
        
        try:
            conversations = await client.list_conversations()
            return conversations
        except Exception as e:
            logger.error(f"Error listing conversations: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @api_router.get("/conversations/{conversation_id}", response_model=Dict[str, Any])
    async def get_conversation(
        conversation_id: str,
        request_obj: Request,
    ):
        """Get a conversation by ID"""
        client_id = get_client_id(request_obj)
        client = await get_or_create_client(app, client_id)
        
        try:
            # Load the conversation
            result = await client.load_conversation(conversation_id)
            if not result:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            # Set as active conversation
            app.state.active_conversations[client_id] = conversation_id
            
            # Extract messages from history
            messages = []
            for item in client.conversation_history:
                if item.get("type") == "message":
                    content = item.get("content", {})
                    messages.append({
                        "role": content.get("role", ""),
                        "text": content.get("text", ""),
                        "timestamp": item.get("timestamp", "")
                    })
            
            # Extract metadata
            metadata = None
            for item in client.conversation_history:
                if item.get("type") == "metadata":
                    metadata = item.get("content", {})
                    break
            
            return {
                "conversation_id": conversation_id,
                "title": metadata.get("title", "Untitled") if metadata else "Untitled",
                "model": metadata.get("model", "") if metadata else "",
                "messages": messages
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting conversation: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @api_router.delete("/conversations/{conversation_id}", response_model=Dict[str, bool])
    async def delete_conversation(
        conversation_id: str,
        request_obj: Request,
    ):
        """Delete a conversation by ID"""
        client_id = get_client_id(request_obj)
        client = await get_or_create_client(app, client_id)
        
        try:
            # Get all conversations to find the path
            conversations = await client.list_conversations()
            target_path = None
            
            for conv in conversations:
                if conv.get("conversation_id") == conversation_id:
                    target_path = conv.get("path")
                    break
            
            if not target_path:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            # Delete the file
            import os
            os.remove(str(target_path))
            
            # If this was the active conversation, clear it
            if client_id in app.state.active_conversations and app.state.active_conversations[client_id] == conversation_id:
                client.conversation_id = None
                client.conversation_history = []
                app.state.active_conversations[client_id] = None
            
            return {"success": True}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting conversation: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @api_router.put("/conversations/{conversation_id}", response_model=Dict[str, str])
    async def rename_conversation(
        conversation_id: str,
        data: Dict[str, str] = Body(...),
        request_obj: Request = None,
    ):
        """Rename a conversation"""
        client_id = get_client_id(request_obj)
        client = await get_or_create_client(app, client_id)
        
        # Validate input
        if "title" not in data:
            raise HTTPException(status_code=400, detail="Title is required")
        
        new_title = data["title"]
        
        try:
            # Get current conversation data
            conversations = await client.list_conversations()
            target_conv = None
            target_path = None
            
            for conv in conversations:
                if conv.get("conversation_id") == conversation_id:
                    target_conv = conv
                    target_path = conv.get("path")
                    break
            
            if not target_conv or not target_path:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            # Read the conversation file
            with open(target_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Update the title in metadata
            history = data.get("history", [])
            for i, item in enumerate(history):
                if item.get("type") == "metadata":
                    if "content" in item and isinstance(item["content"], dict):
                        item["content"]["title"] = new_title
                        break
            
            # Save updated data
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            return {
                "conversation_id": conversation_id,
                "title": new_title
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error renaming conversation: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # ----- Messages -----
    
    @api_router.post("/messages", response_model=Dict[str, Any])
    async def send_message(
        request: MessageRequest,
        background_tasks: BackgroundTasks,
        request_obj: Request,
    ):
        """Send a message and get a response"""
        client_id = get_client_id(request_obj)
        client = await get_or_create_client(app, client_id)
        
        # Get conversation ID
        conversation_id = request.conversation_id
        if not conversation_id:
            conversation_id = app.state.active_conversations.get(client_id)
            
        # Validate conversation ID
        if not conversation_id:
            raise HTTPException(status_code=400, detail="No active conversation. Create or load a conversation first.")
        
        # Set conversation ID
        client.conversation_id = conversation_id
        
        # Ensure conversation is loaded
        if not client.conversation_history:
            await client.load_conversation(conversation_id)
        
        try:
            # Add user message to history
            user_message = client.create_message_structure("user", request.message, client.model, client.params)
            client.conversation_history.append(user_message)
            
            # Send message and get response (non-streaming)
            response = await client.send_message(request.message)
            
            # Add AI response to history
            ai_message = client.create_message_structure("ai", response, client.model, client.params)
            client.conversation_history.append(ai_message)
            
            # Save conversation in background
            background_tasks.add_task(client.save_conversation)
            
            return {
                "role": "ai",
                "text": response,
                "conversation_id": conversation_id
            }
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # ----- Models -----
    
    @api_router.get("/models", response_model=List[ModelInfo])
    async def list_models(
        request_obj: Request,
    ):
        """List available models"""
        client_id = get_client_id(request_obj)
        client = await get_or_create_client(app, client_id)
        
        try:
            models = await client.get_available_models()
            return models
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @api_router.post("/models/select", response_model=Dict[str, str])
    async def select_model(
        data: Dict[str, str] = Body(...),
        request_obj: Request = None,
    ):
        """Select a model to use"""
        client_id = get_client_id(request_obj)
        client = await get_or_create_client(app, client_id)
        
        # Validate input
        if "model" not in data:
            raise HTTPException(status_code=400, detail="Model name is required")
        
        model_name = data["model"]
        
        try:
            # Set model
            client.model = model_name
            
            # Update config
            client.config.set("model", model_name)
            client.config.save_config()
            
            return {"model": model_name}
        except Exception as e:
            logger.error(f"Error selecting model: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # ----- Configuration -----
    
    @api_router.get("/config", response_model=ConfigInfo)
    async def get_config(
        request_obj: Request,
    ):
        """Get current configuration"""
        client_id = get_client_id(request_obj)
        client = await get_or_create_client(app, client_id)
        
        try:
            return {
                "api_key_set": bool(client.api_key),
                "conversations_dir": str(client.conversations_dir),
                "default_model": client.model,
                "generation_params": client.params
            }
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @api_router.post("/config", response_model=Dict[str, bool])
    async def update_config(
        request: UpdateConfigRequest,
        request_obj: Request,
    ):
        """Update configuration"""
        client_id = get_client_id(request_obj)
        client = await get_or_create_client(app, client_id)
        
        try:
            # Update API key
            if request.api_key is not None:
                client.api_key = request.api_key
                client.config.set_api_key(request.api_key)
                
                # Reinitialize client if API key changed
                if request.api_key:
                    await client.initialize_client()
            
            # Update conversations directory
            if request.conversations_dir is not None:
                path = Path(request.conversations_dir)
                client.conversations_dir = path
                client.ensure_directories(path)
                client.config.set("conversations_dir", str(path))
            
            # Update default model
            if request.default_model is not None:
                client.model = request.default_model
                client.config.set("model", request.default_model)
            
            # Update generation parameters
            if request.generation_params is not None:
                client.params.update(request.generation_params)
                client.config.set("generation_params", client.params)
            
            # Save config
            client.config.save_config()
            
            return {"success": True}
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # ----- Health Check -----
    
    @api_router.get("/health", response_model=Dict[str, str])
    async def health_check():
        """Check if the API is healthy"""
        return {"status": "ok"}
    
    # Register all routes
    app.include_router(api_router)
