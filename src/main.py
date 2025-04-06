# File: src/main.py

import os
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any, Union
from pathlib import Path

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