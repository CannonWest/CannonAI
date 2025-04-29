"""
SQLAlchemy models for conversations and messages.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON, Boolean, Float
from sqlalchemy.orm import relationship

from app.core.database import Base

class Conversation(Base):
    """Model for a conversation thread."""
    
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    model_provider = Column(String(50))  # e.g., "openai", "google"
    model_name = Column(String(50))  # e.g., "gpt-4", "gemini-pro"
    
    # Relationship with Message
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    
    # Relationship with Settings
    settings = relationship("ConversationSettings", back_populates="conversation", uselist=False, cascade="all, delete-orphan")

class Message(Base):
    """Model for individual messages in a conversation."""
    
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    role = Column(String(20))  # e.g., "user", "assistant", "system"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship with Conversation
    conversation = relationship("Conversation", back_populates="messages")

class ConversationSettings(Base):
    """Model for conversation-specific settings."""
    
    __tablename__ = "conversation_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), unique=True)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=1000)
    # Add other model-specific settings as needed
    settings_json = Column(JSON, default={})
    
    # Relationship with Conversation
    conversation = relationship("Conversation", back_populates="settings")

# TODO: Add User model if implementing authentication
