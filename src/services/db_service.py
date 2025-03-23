# src/services/db_service.py
from sqlalchemy import create_engine, Column, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import uuid

from src.models import FileAttachment

Base = declarative_base()


class Conversation(Base):
    __tablename__ = 'conversations'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    current_node_id = Column(String, ForeignKey('messages.id'))
    system_message = Column(Text, nullable=False, default="You are a helpful assistant.")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", foreign_keys="Message.conversation_id")
    current_node = relationship("Message", foreign_keys=[current_node_id])


class Message(Base):
    __tablename__ = 'messages'
    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey('conversations.id'), nullable=False)
    parent_id = Column(String, ForeignKey('messages.id'))
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    response_id = Column(String)
    conversation = relationship("Conversation", back_populates="messages", foreign_keys=[conversation_id])
    children = relationship("Message", backref="parent", remote_side=[id], cascade="all, delete-orphan")
    model_info = Column(JSON)
    parameters = Column(JSON)
    token_usage = Column(JSON)


class ConversationService:
    def __init__(self, db_path='sqlite:///data/database/conversations.db'):
        self.engine = create_engine(db_path)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def get_session(self):
        return self.Session()

    def create_conversation(self, name="New Conversation", system_message="You are a helpful assistant."):
        s = self.get_session()
        try:
            c = Conversation(id=str(uuid.uuid4()), name=name, system_message=system_message)
            s.add(c)
            m = Message(id=str(uuid.uuid4()), conversation_id=c.id, role="system", content=system_message)
            s.add(m)
            c.current_node_id = m.id
            s.commit()
            return c
        finally:
            s.close()

    def get_conversation(self, id):
        s = self.get_session()
        try:
            return s.query(Conversation).filter(Conversation.id == id).first()
        finally:
            s.close()

    def get_all_conversations(self):
        s = self.get_session()
        try:
            return s.query(Conversation).order_by(Conversation.modified_at.desc()).all()
        finally:
            s.close()

    def update_conversation(self, id, **kwargs):
        s = self.get_session()
        try:
            c = s.query(Conversation).filter(Conversation.id == id).first()
            if not c: return False
            for k, v in kwargs.items():
                if hasattr(c, k): setattr(c, k, v)
            c.modified_at = datetime.utcnow()
            s.commit()
            return True
        finally:
            s.close()

    def delete_conversation(self, id):
        s = self.get_session()
        try:
            c = s.query(Conversation).filter(Conversation.id == id).first()
            if not c: return False
            s.delete(c)
            s.commit()
            return True
        finally:
            s.close()

    def duplicate_conversation(self, conversation_id, new_name=None):
        """
        Duplicate a conversation, including all messages and file attachments

        Args:
            conversation_id: ID of the conversation to duplicate
            new_name: Name for the new conversation, defaults to "<original_name> (Copy)"

        Returns:
            The new conversation, or None if the source conversation is not found
        """
        s = self.get_session()
        try:
            # Get the source conversation
            source_conv = s.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not source_conv:
                return None

            # Set the new name
            if new_name is None:
                new_name = f"{source_conv.name} (Copy)"

            # Create a new conversation with the same system message
            new_conv = Conversation(
                id=str(uuid.uuid4()),
                name=new_name,
                system_message=source_conv.system_message
            )
            s.add(new_conv)
            s.flush()  # Flush to get the new conversation ID

            # Get all messages from the source conversation
            source_messages = s.query(Message).filter(Message.conversation_id == conversation_id).all()

            # Create a mapping of old message IDs to new message IDs
            id_mapping = {}

            # First pass: create all new messages without parent IDs
            for source_msg in source_messages:
                new_msg = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=new_conv.id,
                    role=source_msg.role,
                    content=source_msg.content,
                    timestamp=datetime.now,
                    response_id=source_msg.response_id,
                    model_info=source_msg.model_info,
                    parameters=source_msg.parameters,
                    token_usage=source_msg.token_usage
                )
                s.add(new_msg)

                # Remember the mapping
                id_mapping[source_msg.id] = new_msg.id

                # Set the current node for the system message
                if source_msg.role == "system":
                    new_conv.current_node_id = new_msg.id

            # Flush to get all new message IDs
            s.flush()

            # Second pass: set parent IDs using the mapping
            for source_msg in source_messages:
                if source_msg.parent_id:
                    new_msg_id = id_mapping.get(source_msg.id)
                    new_parent_id = id_mapping.get(source_msg.parent_id)

                    if new_msg_id and new_parent_id:
                        new_msg = s.query(Message).filter(Message.id == new_msg_id).first()
                        if new_msg:
                            new_msg.parent_id = new_parent_id

            # Third pass: copy file attachments for each message
            for source_msg in source_messages:
                # Get file attachments for this message
                attachments = s.query(FileAttachment).filter(FileAttachment.message_id == source_msg.id).all()

                if attachments:
                    new_msg_id = id_mapping.get(source_msg.id)

                    for attachment in attachments:
                        # Create a new file attachment
                        new_attachment = FileAttachment(
                            id=str(uuid.uuid4()),
                            message_id=new_msg_id,
                            file_name=attachment.file_name,
                            display_name=attachment.display_name,
                            mime_type=attachment.mime_type,
                            token_count=attachment.token_count,
                            file_size=attachment.file_size,
                            file_hash=attachment.file_hash,
                            storage_type=attachment.storage_type,
                            content_preview=attachment.content_preview,
                            storage_path=attachment.storage_path,
                            content=attachment.content
                        )
                        s.add(new_attachment)

            # If the source conversation has a current node, set the equivalent in the new conversation
            if source_conv.current_node_id and source_conv.current_node_id in id_mapping:
                new_conv.current_node_id = id_mapping[source_conv.current_node_id]

            # Commit the changes
            s.commit()

            # Return the new conversation
            return new_conv
        except Exception as e:
            s.rollback()
            print(f"Error duplicating conversation: {str(e)}")
            return None
        finally:
            s.close()

    def add_user_message(self, conversation_id, content, parent_id=None):
        s = self.get_session()
        try:
            c = s.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not c: return None
            if parent_id is None: parent_id = c.current_node_id
            m = Message(id=str(uuid.uuid4()), role="user", content=content, conversation_id=conversation_id, parent_id=parent_id)
            s.add(m)
            c.current_node_id = m.id
            c.modified_at = datetime.utcnow()
            s.commit()
            return m
        finally:
            s.close()

    def add_assistant_message(self, conversation_id, content, parent_id=None, model_info=None, token_usage=None, response_id=None):
        s = self.get_session()
        try:
            c = s.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not c: return None
            if parent_id is None: parent_id = c.current_node_id
            m = Message(id=str(uuid.uuid4()), role="assistant", content=content, conversation_id=conversation_id,
                        parent_id=parent_id, response_id=response_id, model_info=model_info or {}, token_usage=token_usage or {})
            s.add(m)
            c.current_node_id = m.id
            c.modified_at = datetime.utcnow()
            s.commit()
            return m
        finally:
            s.close()

    def get_message(self, id):
        s = self.get_session()
        try:
            return s.query(Message).filter(Message.id == id).first()
        finally:
            s.close()

    def get_message_branch(self, message_id):
        s = self.get_session()
        try:
            branch = []
            current_id = message_id
            while current_id:
                m = s.query(Message).filter(Message.id == current_id).first()
                if not m: break
                branch.insert(0, m)
                current_id = m.parent_id
            return branch
        finally:
            s.close()

    def navigate_to_message(self, conversation_id, message_id):
        s = self.get_session()
        try:
            m = s.query(Message).filter(Message.id == message_id, Message.conversation_id == conversation_id).first()
            if not m: return False
            c = s.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not c: return False
            c.current_node_id = message_id
            c.modified_at = datetime.utcnow()
            s.commit()
            return True
        finally:
            s.close()

    def search_conversations(self, search_term, conversation_id=None):
        s = self.get_session()
        try:
            q = s.query(Message, Conversation.name).join(Conversation).filter(Message.content.like(f'%{search_term}%'))
            if conversation_id: q = q.filter(Message.conversation_id == conversation_id)
            return [{'id': m.id, 'conversation_id': m.conversation_id, 'conversation_name': name,
                     'role': m.role, 'content': m.content, 'timestamp': m.timestamp.isoformat()}
                    for m, name in q.all()]
        finally:
            s.close()
