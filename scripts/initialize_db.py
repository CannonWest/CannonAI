# scripts/initialize_db.py

# !/usr/bin/env python3
"""
Script to initialize the database and migrate existing conversations.
"""

import os
import sys
import logging

# Fix the path to properly include the src module
# Get the absolute path of the script directory
script_dir = os.path.dirname(os.path.abspath(__file__))
# Get the parent directory (root project directory)
project_dir = os.path.dirname(script_dir)
# Add the project directory to Python path
sys.path.insert(0, project_dir)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("db_init")


def main():
    """Initialize database and migrate conversations"""
    logger.info("Initializing database...")

    try:
        # Import after path setup
        from src.models.db_manager import DatabaseManager
        from src.models.db_conversation_manager import DBConversationManager

        # Initialize database
        db_manager = DatabaseManager()
        logger.info("Database schema created")

        # Migrate existing conversations
        conversation_manager = DBConversationManager()
        conversation_manager.migrate_json_to_db()

        logger.info("Database initialization complete")
        return 0
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())