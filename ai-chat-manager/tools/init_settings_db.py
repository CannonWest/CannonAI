"""
Script to initialize the settings database tables.
"""
import sys
import os

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import inspect
from app.core.database import engine, Base, SessionLocal
from app.models.settings.models import UserSettings, ProviderSettings, UISettings
from app.services.settings_service import SettingsService

def init_settings_db():
    """Initialize settings tables and create default settings."""
    print("Initializing settings database tables...")
    
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    # Get inspector to check if tables were created
    inspector = inspect(engine)
    settings_tables = [
        "user_settings",
        "provider_settings",
        "ui_settings"
    ]
    
    existing_tables = inspector.get_table_names()
    
    print("Existing tables:", existing_tables)
    created_tables = [table for table in settings_tables if table in existing_tables]
    print(f"Settings tables created: {created_tables}")
    
    # Initialize default settings
    db = SessionLocal()
    try:
        # Create default provider settings
        openai_settings = ProviderSettings.get_or_create(db, "openai")
        anthropic_settings = ProviderSettings.get_or_create(db, "anthropic")
        
        # Create default UI settings
        ui_settings = UISettings.get_or_create(db)
        
        print("Default settings created:")
        print(f"OpenAI: {openai_settings.default_model}, temp={openai_settings.temperature}, max_tokens={openai_settings.max_tokens}")
        print(f"Anthropic: {anthropic_settings.default_model}, temp={anthropic_settings.temperature}, max_tokens={anthropic_settings.max_tokens}")
        print(f"UI: theme={ui_settings.theme}, sidebar_collapsed={ui_settings.sidebar_collapsed}, show_token_count={ui_settings.show_token_count}")
        
    finally:
        db.close()
    
    print("Settings database initialization complete.")

if __name__ == "__main__":
    init_settings_db()
