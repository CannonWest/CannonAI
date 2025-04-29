"""
Service for managing conversations.
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import logging

# Get logger
logger = logging.getLogger(__name__)

from app.models.conversation import Conversation, Message as DBMessage, ConversationSettings
from app.services.ai_provider import Message, ModelSettings, ChatResponse
from app.services.provider_factory import get_provider
from app.utils.serialization import serialize_datetime

class ConversationService:
    """Service for managing conversations and messages."""
    
    def __init__(self, db: Session):
        self.db = db
        
    def _serialize_model(self, obj):
        """Serialize a model instance, converting datetime fields to strings."""
        if hasattr(obj, "created_at") and isinstance(obj.created_at, datetime):
            obj.created_at = serialize_datetime(obj.created_at)
            
        if hasattr(obj, "updated_at") and isinstance(obj.updated_at, datetime):
            obj.updated_at = serialize_datetime(obj.updated_at)
            
        return obj
    
    def create_conversation(
        self, 
        title: str, 
        model_provider: str, 
        model_name: str,
        settings: Dict[str, Any] = None
    ) -> Conversation:
        """
        Create a new conversation.
        
        Args:
            title: Title of the conversation
            model_provider: AI provider (e.g., "openai", "google")
            model_name: Model name (e.g., "gpt-4", "gemini-pro")
            settings: Optional model settings
            
        Returns:
            Created Conversation object
        """
        # Create conversation
        logger.info(f"Creating new conversation with title: {title}, provider: {model_provider}, model: {model_name}")
        db_conversation = Conversation(
            title=title,
            model_provider=model_provider,
            model_name=model_name
        )
        self.db.add(db_conversation)
        self.db.commit()
        self.db.refresh(db_conversation)
        
        # Create settings if provided
        if settings:
            temperature = settings.get("temperature", 0.7)
            max_tokens = settings.get("max_tokens", 1000)
            
            db_settings = ConversationSettings(
                conversation_id=db_conversation.id,
                temperature=temperature,
                max_tokens=max_tokens,
                settings_json=settings
            )
            self.db.add(db_settings)
            self.db.commit()
        
        return self._serialize_model(db_conversation)
    
    def get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        """Get a conversation by ID."""
        conversation = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conversation:
            logger.info(f"Conversation with ID {conversation_id} not found")
            return None
        return self._serialize_model(conversation)
        
    def get_or_create_default_conversation(self) -> Conversation:
        """
        Gets the default conversation or creates it if it doesn't exist.
        
        Returns:
            The default conversation (first one or newly created)
        """
        default_conversation = self.db.query(Conversation).first()
        
        if not default_conversation:
            logger.info("Creating default conversation")
            default_conversation = Conversation(
                title="New Conversation",
                model_provider="openai",  # Default provider
                model_name="gpt-3.5-turbo",  # Default model
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(default_conversation)
            self.db.commit()
            self.db.refresh(default_conversation)
            
            # Add default settings
            default_settings = ConversationSettings(
                conversation_id=default_conversation.id,
                temperature=0.7,
                max_tokens=1000
            )
            self.db.add(default_settings)
            self.db.commit()
        
        return self._serialize_model(default_conversation)
    
    def get_all_conversations(self) -> List[Conversation]:
        """Get all conversations."""
        conversations = self.db.query(Conversation).order_by(Conversation.updated_at.desc()).all()
        return [self._serialize_model(conv) for conv in conversations]
    
    def update_conversation(
        self, 
        conversation_id: int, 
        title: str = None,
        model_provider: str = None,
        model_name: str = None
    ) -> Optional[Conversation]:
        """Update a conversation."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            logger.error(f"Conversation with ID {conversation_id} not found")
            return None
        
        if title:
            conversation.title = title
        if model_provider:
            conversation.model_provider = model_provider
        if model_name:
            conversation.model_name = model_name
        
        conversation.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(conversation)
        return self._serialize_model(conversation)
    
    def delete_conversation(self, conversation_id: int) -> bool:
        """Delete a conversation."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return False
        
        self.db.delete(conversation)
        self.db.commit()
        return True
    
    def add_message(
        self, 
        conversation_id: int, 
        role: str, 
        content: str
    ) -> Optional[DBMessage]:
        """Add a message to a conversation."""
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return None
        
        message = DBMessage(
            conversation_id=conversation_id,
            role=role,
            content=content
        )
        
        self.db.add(message)
        
        # Update the conversation's updated_at timestamp
        conversation.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(message)
        return self._serialize_model(message)
    
    def get_messages(self, conversation_id: int) -> List[DBMessage]:
        """Get all messages for a conversation."""
        messages = self.db.query(DBMessage).filter(
            DBMessage.conversation_id == conversation_id
        ).order_by(DBMessage.created_at).all()
        return [self._serialize_model(msg) for msg in messages]
    
    async def send_message_to_ai(
        self, 
        conversation_id: int, 
        user_message: str
    ) -> Optional[DBMessage]:
        """
        Send a user message to the AI and store the response.
        
        Args:
            conversation_id: ID of the conversation
            user_message: User's message content
            
        Returns:
            The AI's response message
        """
        logger.info(f"Sending message to AI for conversation {conversation_id}")
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            logger.error(f"Conversation with ID {conversation_id} not found")
            return None
        
        # Get conversation settings
        settings_obj = self.db.query(ConversationSettings).filter(
            ConversationSettings.conversation_id == conversation_id
        ).first()
        
        # Add user message to the conversation
        self.add_message(conversation_id, "user", user_message)
        
        # Get all messages for context
        db_messages = self.get_messages(conversation_id)
        messages = [
            Message(role=msg.role, content=msg.content)
            for msg in db_messages
        ]
        
        # Create model settings
        model_settings = ModelSettings(
            model_name=conversation.model_name,
            temperature=settings_obj.temperature if settings_obj else 0.7,
            max_tokens=settings_obj.max_tokens if settings_obj else None
        )
        
        # Get the appropriate AI provider
        provider = get_provider(conversation.model_provider)
        
        # Get response from AI
        response = await provider.chat_completion(messages, model_settings)
        
        # Save AI response to database
        ai_message = self.add_message(
            conversation_id,
            "assistant",
            response.message.content
        )
        
        return ai_message  # Already serialized in add_message
    
    async def stream_message_to_ai(
        self, 
        conversation_id: int, 
        user_message: str
    ):
        """
        Stream a user message to the AI.
        
        Args:
            conversation_id: ID of the conversation
            user_message: User's message content
            
        Yields:
            Chunks of the AI's response as they become available
        """
        logger.info(f"Streaming message to AI for conversation {conversation_id}")
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            logger.error(f"Conversation with ID {conversation_id} not found")
            yield "Error: Conversation not found"
            return
        
        # Get conversation settings
        settings_obj = self.db.query(ConversationSettings).filter(
            ConversationSettings.conversation_id == conversation_id
        ).first()
        
        # Add user message to the conversation
        self.add_message(conversation_id, "user", user_message)
        
        # Get all messages for context
        db_messages = self.get_messages(conversation_id)
        messages = [
            Message(role=msg.role, content=msg.content)
            for msg in db_messages
        ]
        
        # Create model settings
        model_settings = ModelSettings(
            model_name=conversation.model_name,
            temperature=settings_obj.temperature if settings_obj else 0.7,
            max_tokens=settings_obj.max_tokens if settings_obj else None
        )
        
        # Get the appropriate AI provider
        provider = get_provider(conversation.model_provider)
        
        # Stream response from AI
        logger.debug(f"Starting streaming response for conversation {conversation_id}")
        full_response = ""
        async for chunk in provider.stream_chat_completion(messages, model_settings):
            full_response += chunk
            yield chunk
        
        logger.debug(f"Completed streaming response for conversation {conversation_id}")
        # Save the complete response to the database
        self.add_message(conversation_id, "assistant", full_response)
