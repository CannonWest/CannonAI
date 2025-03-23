# src/services/db_manager.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import json
import sqlite3
from datetime import datetime

from src.models.orm_models import Base, Conversation, Message, FileAttachment
from src.utils.logging_utils import get_logger

# Get a logger for this module
logger = get_logger(__name__)


class DatabaseManager:
    """
    Manages database connections, session creation, and schema initialization.
    This separates database infrastructure concerns from business logic in service classes.
    """

    def __init__(self, connection_string='sqlite:///data/database/conversations.db'):
        """
        Initialize the database manager

        Args:
            connection_string: SQLAlchemy connection string for the database
        """
        self.connection_string = connection_string
        self.engine = create_engine(connection_string)
        self.Session = sessionmaker(bind=self.engine)
        self.logger = get_logger(f"{__name__}.DatabaseManager")

        # Initialize tables if they don't exist
        self.create_tables()

    def create_tables(self):
        """Create all tables defined in the models if they don't exist"""
        self.logger.debug("Ensuring database tables exist")
        Base.metadata.create_all(self.engine)

    def get_session(self):
        """Get a new database session"""
        return self.Session()

    def migrate_from_old_db(self, old_db_path):
        """
        Migrate data from an older SQLite database to the new ORM structure

        Args:
            old_db_path: Path to the old SQLite database file

        Returns:
            bool: True if migration succeeded, False otherwise
        """
        self.logger.info(f"Starting migration from {old_db_path}")

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
            self.logger.info("Migration completed successfully")
            return True

        except Exception as e:
            session.rollback()
            self.logger.error(f"Migration error: {str(e)}")
            return False
        finally:
            session.close()
            old_conn.close()