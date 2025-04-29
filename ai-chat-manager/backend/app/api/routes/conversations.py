"""
API routes for managing conversations.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.services.conversation_service import ConversationService
from app.models.conversation import Conversation as DBConversation
from app.models.conversation import Message as DBMessage

router = APIRouter()

# Pydantic models for API
class ConversationCreate(BaseModel):
    title: str
    model_provider: str
    model_name: str
    settings: Optional[Dict[str, Any]] = None

class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None

class MessageCreate(BaseModel):
    content: str

class ConversationResponse(BaseModel):
    id: int
    title: str
    model_provider: str
    model_name: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: str

    class Config:
        from_attributes = True

# Routes
@router.get("/default", response_model=ConversationResponse)
def get_default_conversation(db: Session = Depends(get_db)):
    """Get or create a default conversation."""
    service = ConversationService(db)
    return service.get_or_create_default_conversation()

@router.post("", response_model=ConversationResponse)
def create_conversation(
    conversation: ConversationCreate,
    db: Session = Depends(get_db)
):
    """Create a new conversation."""
    service = ConversationService(db)
    db_conversation = service.create_conversation(
        title=conversation.title,
        model_provider=conversation.model_provider,
        model_name=conversation.model_name,
        settings=conversation.settings
    )
    return db_conversation

@router.get("", response_model=List[ConversationResponse])
def get_conversations(db: Session = Depends(get_db)):
    """Get all conversations."""
    service = ConversationService(db)
    return service.get_all_conversations()

@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(conversation_id: int, db: Session = Depends(get_db)):
    """Get a specific conversation by ID."""
    service = ConversationService(db)
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation

@router.put("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: int,
    conversation_update: ConversationUpdate,
    db: Session = Depends(get_db)
):
    """Update a conversation."""
    service = ConversationService(db)
    updated_conversation = service.update_conversation(
        conversation_id=conversation_id,
        title=conversation_update.title,
        model_provider=conversation_update.model_provider,
        model_name=conversation_update.model_name
    )
    if not updated_conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return updated_conversation

@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    """Delete a conversation."""
    service = ConversationService(db)
    success = service.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "success"}

@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
def get_messages(conversation_id: int, db: Session = Depends(get_db)):
    """Get messages for a conversation."""
    service = ConversationService(db)
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = service.get_messages(conversation_id)
    return messages

@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def create_message(
    conversation_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db)
):
    """Create a new message and get AI response."""
    service = ConversationService(db)
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Send message to AI and get response
    ai_message = await service.send_message_to_ai(
        conversation_id=conversation_id,
        user_message=message.content
    )
    
    return ai_message

@router.websocket("/{conversation_id}/stream")
async def stream_chat(
    websocket: WebSocket,
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """Stream conversation with AI via WebSocket."""
    await websocket.accept()
    service = ConversationService(db)
    
    try:
        while True:
            # Receive user message
            user_message = await websocket.receive_text()
            
            # Send initial acknowledgment
            await websocket.send_json({"status": "processing"})
            
            # Add the user message to the conversation
            # Stream AI response
            async for chunk in service.stream_message_to_ai(
                conversation_id=conversation_id,
                user_message=user_message
            ):
                await websocket.send_json({
                    "type": "chunk",
                    "content": chunk
                })
            
            # Signal completion
            await websocket.send_json({"type": "done"})
            
    except WebSocketDisconnect:
        print(f"WebSocket for conversation {conversation_id} disconnected")
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "content": str(e)
        })
