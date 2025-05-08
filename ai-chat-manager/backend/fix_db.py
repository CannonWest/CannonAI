"""
Database fixing script to ensure proper connection and initialization.
"""
import os
import sys
import sqlite3
from pathlib import Path

# Ensure we're in the right directory and can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import engine, Base
from app.models.conversation import Conversation, Message, ConversationSettings
from app.models.settings.models import UserSettings, ProviderSettings, UISettings

def fix_database():
    """Fix database issues by ensuring directory exists and DB is properly initialized."""
    # Ensure data directory exists
    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)
    
    print(f"Data directory: {data_dir.absolute()}")
    db_path = data_dir / "chat_manager.db"
    
    # Check if database exists
    exists = db_path.exists()
    print(f"Database exists: {exists}")
    
    if exists:
        # Check if we can connect
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print(f"Existing tables: {tables}")
            conn.close()
        except Exception as e:
            print(f"Error connecting to database: {e}")
            print("Creating a new database file...")
            if db_path.exists():
                db_path.unlink()  # Delete existing file if corrupted
    
    # Create tables using SQLAlchemy
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    
    # Log tables that were created
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Tables in database: {tables}")
    
    # Check if we have conversations
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        conversations = session.query(Conversation).all()
        print(f"Number of conversations in database: {len(conversations)}")
        
        if not conversations:
            # Create a default conversation if none exist
            print("Creating a default conversation...")
            default_conversation = Conversation(
                title="Default Conversation",
                model_provider="openai",
                model_name="gpt-3.5-turbo"
            )
            session.add(default_conversation)
            session.commit()
            
            # Add default settings
            default_settings = ConversationSettings(
                conversation_id=default_conversation.id,
                temperature=0.7,
                max_tokens=1000
            )
            session.add(default_settings)
            session.commit()
            print(f"Created default conversation with ID: {default_conversation.id}")
    except Exception as e:
        print(f"Error checking conversations: {e}")
    finally:
        session.close()
    
    print("Database fix complete!")

if __name__ == "__main__":
    fix_database()
