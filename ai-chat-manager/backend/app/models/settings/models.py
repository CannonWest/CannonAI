"""
SQLAlchemy models for user and application settings.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON, Boolean, Float
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import relationship

from app.core.database import Base

class UserSettings(Base):
    """Model for user-level settings."""
    
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=True, index=True)  # Optional: for future user authentication
    settings_key = Column(String(100), index=True)  # e.g., "default_provider", "theme"
    settings_value = Column(JSON, nullable=True)  # Flexible JSON storage
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @classmethod
    def get_or_create(cls, db, settings_key, user_id=None):
        """
        Get an existing setting or create a new one if it doesn't exist.
        
        Args:
            db: Database session
            settings_key: The key for the setting
            user_id: Optional user ID (for future auth)
            
        Returns:
            The existing or newly created settings object
        """
        setting = db.query(cls).filter(
            cls.settings_key == settings_key,
            cls.user_id == user_id
        ).first()
        
        if not setting:
            setting = cls(
                settings_key=settings_key,
                user_id=user_id,
                settings_value={}
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
            
        return setting

class ProviderSettings(Base):
    """Model for provider-specific settings."""
    
    __tablename__ = "provider_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=True, index=True)  # Optional: for future user authentication
    provider_name = Column(String(50), index=True)  # e.g., "openai", "anthropic"
    default_model = Column(String(100))  # Default model for this provider
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2000)
    additional_settings = Column(JSON, default={})  # For provider-specific settings
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @classmethod
    def get_or_create(cls, db, provider_name, user_id=None):
        """
        Get an existing provider setting or create a new one if it doesn't exist.
        
        Args:
            db: Database session
            provider_name: The name of the provider
            user_id: Optional user ID (for future auth)
            
        Returns:
            The existing or newly created provider settings object
        """
        setting = db.query(cls).filter(
            cls.provider_name == provider_name,
            cls.user_id == user_id
        ).first()
        
        if not setting:
            # Get default model for this provider
            default_model = None
            if provider_name == "openai":
                from app.models.openai.model_config import get_default_model
                default_model = get_default_model().model_id
            elif provider_name == "anthropic":
                default_model = "claude-3.5-sonnet"
            
            setting = cls(
                provider_name=provider_name,
                user_id=user_id,
                default_model=default_model,
                temperature=0.7,
                max_tokens=2000
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
            
        return setting

class UISettings(Base):
    """Model for UI-specific settings."""
    
    __tablename__ = "ui_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=True, index=True)  # Optional: for future user authentication
    theme = Column(String(20), default="light")  # e.g., "light", "dark"
    sidebar_collapsed = Column(Boolean, default=False)
    show_token_count = Column(Boolean, default=True)
    additional_settings = Column(JSON, default={})  # For other UI settings
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @classmethod
    def get_or_create(cls, db, user_id=None):
        """
        Get existing UI settings or create new ones if they don't exist.
        
        Args:
            db: Database session
            user_id: Optional user ID (for future auth)
            
        Returns:
            The existing or newly created UI settings object
        """
        setting = db.query(cls).filter(cls.user_id == user_id).first()
        
        if not setting:
            setting = cls(
                user_id=user_id,
                theme="light",
                sidebar_collapsed=False,
                show_token_count=True
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
            
        return setting
