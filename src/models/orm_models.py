# src/models/orm_models.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, JSON, Table, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import json
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


class Message(Base):
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
                            cascade="all, delete-orphan")

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


class FileAttachment(Base):
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


# Database management class
class DatabaseManager:
    def __init__(self, connection_string='sqlite:///data/conversations.db'):
        self.engine = create_engine(connection_string)
        self.Session = sessionmaker(bind=self.engine)

    def create_tables(self):
        Base.metadata.create_all(self.engine)

    def get_session(self):
        return self.Session()

    def migrate_from_old_db(self, old_db_path):
        """Migrate data from the old SQLite database to the new ORM structure"""
        import sqlite3

        session = self.get_session()
        old_conn = sqlite3.connect(old_db_path)
        old_conn.row_factory = sqlite3.Row

        try:
            # Migrate conversations
            old_cursor = old_conn.cursor()
            old_cursor.execute('SELECT * FROM conversations')
            conversations = {}

            for row in old_cursor.fetchall():
                conv = Conversation(
                    id=row['id'],
                    name=row['name'],
                    system_message=row['system_message'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    modified_at=datetime.fromisoformat(row['modified_at']),
                    current_node_id=row['current_node_id']
                )
                conversations[conv.id] = conv
                session.add(conv)

            # Migrate messages
            old_cursor.execute('SELECT * FROM messages')
            messages = {}

            for row in old_cursor.fetchall():
                msg = Message(
                    id=row['id'],
                    conversation_id=row['conversation_id'],
                    parent_id=row['parent_id'],
                    role=row['role'],
                    content=row['content'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    response_id=row['response_id']
                )
                messages[msg.id] = msg
                session.add(msg)

            # Migrate metadata
            old_cursor.execute('SELECT * FROM message_metadata')

            for row in old_cursor.fetchall():
                message_id = row['message_id']
                metadata_type = row['metadata_type']
                metadata_value = json.loads(row['metadata_value'])

                if message_id in messages:
                    msg = messages[message_id]

                    if metadata_type.startswith('model_info.'):
                        if not msg.model_info:
                            msg.model_info = {}
                        key = metadata_type.replace('model_info.', '')
                        msg.model_info[key] = metadata_value

                    elif metadata_type.startswith('parameters.'):
                        if not msg.parameters:
                            msg.parameters = {}
                        key = metadata_type.replace('parameters.', '')
                        msg.parameters[key] = metadata_value

                    elif metadata_type.startswith('token_usage.'):
                        if not msg.token_usage:
                            msg.token_usage = {}
                        key = metadata_type.replace('token_usage.', '')
                        msg.token_usage[key] = metadata_value

                    elif metadata_type == 'reasoning_steps':
                        msg.reasoning_steps = metadata_value

            # Migrate file attachments
            old_cursor.execute('SELECT * FROM file_attachments')

            for row in old_cursor.fetchall():
                # Convert the row to a dict
                file_data = dict(row)

                attachment = FileAttachment(
                    id=file_data['id'],
                    message_id=file_data['message_id'],
                    file_name=file_data['file_name'],
                    mime_type=file_data['mime_type'],
                    content=file_data['content'],
                    token_count=file_data['token_count']
                )

                # Handle additional fields that might exist in newer schema
                if 'display_name' in file_data:
                    attachment.display_name = file_data['display_name']
                if 'file_size' in file_data:
                    attachment.file_size = file_data['file_size']
                if 'file_hash' in file_data:
                    attachment.file_hash = file_data['file_hash']
                if 'storage_type' in file_data:
                    attachment.storage_type = file_data['storage_type']
                if 'content_preview' in file_data:
                    attachment.content_preview = file_data['content_preview']
                if 'storage_path' in file_data:
                    attachment.storage_path = file_data['storage_path']

                session.add(attachment)

            # Commit all changes
            session.commit()
            return True

        except Exception as e:
            session.rollback()
            print(f"Migration error: {str(e)}")
            return False
        finally:
            session.close()
            old_conn.close()