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


@router.websocket("/{conversation_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        conversation_id: int,
        db: Session = Depends(get_db)
):
    await manager.connect(websocket, conversation_id)
    conversation_service = ConversationService(db)
    try:
        client_host = websocket.client.host if websocket.client else "unknown"
        logger.info(f"WebSocket connection established for conversation {conversation_id} from {client_host}")

        # Send connection confirmation (optional, but good for debugging)
        await websocket.send_json({
            "type": "status",
            "status": "connected",
            "message": f"WebSocket connection established for conversation {conversation_id}"
        })

        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                message_type = message_data.get("type", "message")
                content = message_data.get("content", "")

                logger.debug(f"Received {message_type} message from client {client_host} for conversation {conversation_id}: {content[:100]}")  # Log content

                if message_type == "message":
                    await websocket.send_json({
                        "type": "status",
                        "status": "processing"
                    })

                    # Add user message to database
                    logger.info(f"Adding user message to DB for conversation {conversation_id}")
                    conversation_service.add_message(
                        conversation_id=conversation_id,
                        role="user",
                        content=content
                    )

                    try:
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

                        await websocket.send_json({
                            "type": "done",
                            "content": full_response
                        })

                        # --- ADD THIS SECTION TO SAVE AI RESPONSE ---
                        if full_response:  # Ensure there's something to save
                            logger.info(f"Adding AI assistant message to DB for conversation {conversation_id}")
                            conversation_service.add_message(
                                conversation_id=conversation_id,
                                role="assistant",
                                content=full_response
                            )
                        # --- END OF SECTION TO SAVE AI RESPONSE ---

                    except ProviderError as e:
                        logger.error(f"Provider error with {provider_name}/{model_name} for conversation {conversation_id}: {str(e)}")
                        await websocket.send_json({"type": "error", "error": f"API Provider Error: {str(e)}"})
                    except Exception as e:
                        logger.error(f"Unexpected error in WebSocket streaming for conversation {conversation_id}: {str(e)}", exc_info=True)
                        await websocket.send_json({"type": "error", "error": f"Server error: {str(e)}"})

                elif message_type == "ping":
                    await websocket.send_json({"type": "pong"})

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received on WebSocket for conversation {conversation_id}: {data}")
                await websocket.send_json({"type": "error", "error": "Invalid message format"})
            except Exception as e:
                logger.error(f"Error processing client message on WebSocket for conversation {conversation_id}: {str(e)}", exc_info=True)
                await websocket.send_json({"type": "error", "error": str(e)})

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected from conversation {conversation_id}")
    except Exception as e:
        logger.error(f"Unexpected error in WebSocket connection for conversation {conversation_id}: {str(e)}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "error": "An unexpected server error occurred"})
        except Exception:
            pass  # Connection likely already closed
    finally:
        # Ensure disconnect is always called
        manager.disconnect(websocket, conversation_id)