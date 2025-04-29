"""
Database initialization script.
"""
from sqlalchemy import inspect
from app.core.database import engine, Base
from app.models.conversation import Conversation, Message, ConversationSettings

def init_db():
    """Initialize the database by creating all tables."""
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    # Get inspector to check if tables were created
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    print(f"Database initialized with tables: {tables}")

if __name__ == "__main__":
    init_db()
