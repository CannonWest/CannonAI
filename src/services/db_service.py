# src/services/db_service.py
from sqlalchemy import create_engine, Column, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import uuid

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
    def __init__(self, db_path='sqlite:///data/conversations.db'):
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