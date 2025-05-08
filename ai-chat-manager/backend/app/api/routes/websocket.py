""" 
WebSocket routes for real-time chat communication.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
import json
from typing import Dict, Any
import logging

from app.core.database import get_db
from app.services.conversation_service import ConversationService
from app.api.websocket_manager import manager
from app.services.provider_factory import ProviderError

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/chat/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time chat with AI models.
    
    Args:
        websocket: WebSocket connection
        conversation_id: ID of the conversation
        db: Database session
    """
    # Accept connection and register it
    await manager.connect(websocket, conversation_id)
    
    # Create conversation service
    conversation_service = ConversationService(db)
    
    try:
        while True:
            # Wait for messages from the client
            data = await websocket.receive_text()
            
            try:
                # Parse the message
                message_data = json.loads(data)
                message_type = message_data.get("type", "message")
                content = message_data.get("content", "")
                
                if message_type == "message":
                    # Send acknowledgment
                    await websocket.send_json({
                        "type": "status",
                        "status": "processing"
                    })
                    
                    # Add user message to database
                    conversation_service.add_message(
                        conversation_id=conversation_id,
                        role="user",
                        content=content
                    )
                    
                    # Stream AI response
                    try:
                        # Get conversation details for better error messages
                        conversation_details = conversation_service.get_conversation(conversation_id)
                        model_name = conversation_details.model_name if conversation_details else "unknown model"
                        provider_name = conversation_details.model_provider if conversation_details else "unknown provider"
                        
                        logger.debug(f"Starting streaming with {provider_name}/{model_name} for conversation {conversation_id}")
                        
                        full_response = ""
                        async for chunk in conversation_service.stream_message_to_ai(
                            conversation_id=conversation_id,
                            user_message=content
                        ):
                            full_response += chunk
                            await websocket.send_json({
                                "type": "chunk",
                                "content": chunk
                            })
                        
                        # Signal completion
                        await websocket.send_json({
                            "type": "done",
                            "content": full_response
                        })
                        
                    except ProviderError as e:
                        logger.error(f"Provider error with {provider_name}/{model_name}: {str(e)}")
                        await websocket.send_json({
                            "type": "error",
                            "error": f"API Provider Error with {provider_name}/{model_name}: {str(e)}"
                        })
                    except Exception as e:
                        logger.error(f"Unexpected error in WebSocket streaming with {provider_name}/{model_name}: {str(e)}")
                        await websocket.send_json({
                            "type": "error",
                            "error": f"Error processing request with {provider_name}/{model_name}: {str(e)}"
                        })
                    
                elif message_type == "ping":
                    # Respond to ping
                    await websocket.send_json({
                        "type": "pong"
                    })
                    
            except json.JSONDecodeError:
                # Handle invalid JSON
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid message format"
                })
                
            except Exception as e:
                # Handle other errors
                await websocket.send_json({
                    "type": "error",
                    "error": str(e)
                })
                
    except WebSocketDisconnect:
        # Handle client disconnection
        manager.disconnect(websocket, conversation_id)
