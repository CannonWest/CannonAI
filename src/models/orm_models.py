"""
Database ORM models for the CannonAI web application.
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, JSON, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()

# Association table for message metadata
message_metadata = Table(
    'message_metadata',
    Base.metadata,
    Column('message_id', String, ForeignKey('messages.id')),
    Column('key', String),
    Column('value', Text),
)


class Conversation(Base):
    """
    Represents a conversation containing messages.
    """
    __tablename__ = 'conversations'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    current_node_id = Column(String, ForeignKey('messages.id'))
    system_message = Column(Text, nullable=False, default="You are a helpful assistant.")

    messages = relationship("Message", back_populates="conversation",
                            cascade="all, delete-orphan",
                            foreign_keys="Message.conversation_id")
    current_node = relationship("Message", foreign_keys=[current_node_id])

    def __init__(self, name="New Conversation", system_message="You are a helpful assistant.", **kwargs):
        self.id = str(uuid.uuid4())
        self.name = name
        self.system_message = system_message
        self.created_at = datetime.utcnow()
        self.modified_at = self.created_at
        super().__init__(**kwargs)

    def to_dict(self):
        """Convert instance to dictionary for API responses"""
        return {
            "id": self.id,
            "name": self.name,
            "system_message": self.system_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "current_node_id": self.current_node_id
        }


class Message(Base):
    """
    Represents a message in a conversation.
    Messages can have parent-child relationships for branching conversations.
    """
    __tablename__ = 'messages'

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey('conversations.id'), nullable=False)
    parent_id = Column(String, ForeignKey('messages.id'))
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    response_id = Column(String)

    conversation = relationship("Conversation", back_populates="messages",
                                foreign_keys=[conversation_id])
    children = relationship("Message",
                            backref="parent",
                            remote_side=[id],
                            cascade="all, delete-orphan",
                            single_parent=True)

    # Store JSON-serializable metadata
    model_info = Column(JSON)
    parameters = Column(JSON)
    token_usage = Column(JSON)
    reasoning_steps = Column(JSON)

    file_attachments = relationship("FileAttachment", back_populates="message",
                                    cascade="all, delete-orphan")

    def __init__(self, role, content, conversation_id=None, parent_id=None, **kwargs):
        self.id = str(uuid.uuid4())
        self.role = role
        self.content = content
        self.conversation_id = conversation_id
        self.parent_id = parent_id
        self.timestamp = datetime.utcnow()
        super().__init__(**kwargs)

    def to_dict(self):
        """Convert instance to dictionary for API responses"""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "parent_id": self.parent_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "response_id": self.response_id,
            "model_info": self.model_info,
            "parameters": self.parameters,
            "token_usage": self.token_usage,
            "reasoning_steps": self.reasoning_steps,
            "file_attachments": [attachment.to_dict() for attachment in self.file_attachments] if self.file_attachments else []
        }


class FileAttachment(Base):
    """
    Represents a file attachment to a message.
    """
    __tablename__ = 'file_attachments'

    id = Column(String, primary_key=True)
    message_id = Column(String, ForeignKey('messages.id'), nullable=False)
    file_name = Column(String, nullable=False)
    display_name = Column(String)
    mime_type = Column(String, nullable=False, default='text/plain')
    token_count = Column(Integer, default=0)
    file_size = Column(Integer, default=0)
    file_hash = Column(String)
    storage_type = Column(String, default='database')
    content_preview = Column(Text)
    storage_path = Column(String)
    content = Column(Text)

    message = relationship("Message", back_populates="file_attachments")

    def __init__(self, message_id, file_name, mime_type='text/plain', **kwargs):
        self.id = str(uuid.uuid4())
        self.message_id = message_id
        self.file_name = file_name
        self.mime_type = mime_type
        super().__init__(**kwargs)

    def to_dict(self):
        """Convert instance to dictionary for API responses"""
        return {
            "id": self.id,
            "message_id": self.message_id,
            "file_name": self.file_name,
            "display_name": self.display_name,
            "mime_type": self.mime_type,
            "token_count": self.token_count,
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "storage_type": self.storage_type,
            "content_preview": self.content_preview,
            "storage_path": self.storage_path
            # Note: We don't include raw content in API responses for security/performance
        }