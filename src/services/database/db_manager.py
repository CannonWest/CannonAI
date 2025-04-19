#src/services/database/db_manager.py
"""
Database manager for SQLAlchemy operations.
Adapted for web-based architecture with FastAPI.
"""

import os
import logging
from contextlib import contextmanager, asynccontextmanager  # Add asynccontextmanager
from typing import Generator, Optional, Dict, Any
from pathlib import Path

# For async SQLAlchemy:
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# OR for sync SQLAlchemy:
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

# Import Base from models
from src.models.orm_models import Base
from src.config.paths import DATABASE_DIR, PROJECT_ROOT

# Create logger for this module
logger = logging.getLogger(__name__)

db_path = os.path.join(DATABASE_DIR, "conversations.db")

class DatabaseManager:
    """
    Manages database connections, session creation, and schema initialization.
    Singleton pattern to ensure only one database connection pool exists.
    """
    _instance = None
    _engine = None
    _session_factory = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern."""
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_url: str, echo: bool = False):
        """Initialize the database manager."""
        if self._initialized:
            return

        self.db_url = db_url
        self.echo = echo
        self.logger = logging.getLogger(f"{__name__}.DatabaseManager")

        # Log the database location for debugging
        if db_url.startswith('sqlite:///'):
            db_path = db_url[10:]  # Remove 'sqlite:///'
            self.logger.info(f"Using SQLite database at: {db_path}")

        # Create engine and session factory
        self._create_engine()
        self._initialized = True

    def _create_engine(self):
        """Create SQLAlchemy engine and session factory."""
        try:
            # Configure engine with appropriate settings
            engine_args = {
                'echo': self.echo,  # Set to True for SQL query logging
                'pool_pre_ping': True,
                'pool_recycle': 3600,  # Recycle connections after 1 hour
            }

            # Add SQLite-specific connect args if using SQLite
            if self.db_url.startswith('sqlite'):
                engine_args['connect_args'] = {
                    'check_same_thread': False  # Allow multi-threaded access for SQLite
                }

            # Create engine with connection pooling
            self._engine = create_engine(
                self.db_url,
                poolclass=QueuePool,
                **engine_args
            )

            # Create session factory
            self._session_factory = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self._engine
            )

            self.logger.info("SQLAlchemy engine and session factory created successfully")
        except Exception as e:
            self.logger.error(f"Error creating SQLAlchemy engine: {e}", exc_info=True)
            raise

    def create_tables(self):
        """Create all database tables defined in models."""
        if not self._engine:
            self.logger.error("Cannot create tables: Engine not initialized")
            return False

        try:
            Base.metadata.create_all(self._engine)
            self.logger.info("Database tables created or verified successfully")
            return True
        except Exception as e:
            self.logger.error(f"Error creating database tables: {e}", exc_info=True)
            return False

    @asynccontextmanager  # Change decorator
    async def get_session(self):  # Change to async def
        """
        Provide a transactional scope around a series of operations.

        Usage:
            async with db_manager.get_session() as session:
                # Use session here

        Yields:
            SQLAlchemy Session object
        """
        if not self._session_factory:
            self.logger.error("Session factory not initialized")
            raise RuntimeError("Database session factory not initialized")

        session = self._session_factory()
        session_id = id(session)
        self.logger.debug(f"Session {session_id} acquired")

        try:
            yield session
            await session.commit()
            self.logger.debug(f"Session {session_id} committed")
        except Exception as e:
            self.logger.error(f"Error in database session: {e}", exc_info=True)
            await session.rollback()
            self.logger.debug(f"Session {session_id} rolled back")
            raise  # Re-raise the exception after rollback
        finally:
            await session.close()
            self.logger.debug(f"Session {session_id} closed")

    async def get_conversations(self, session, skip=0, limit=100):
        """
        Retrieves a list of conversations with pagination.
        
        Args:
            session: The database session
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            
        Returns:
            List of conversation objects
        """
        try:
            # Adjust this query based on your actual database schema
            # This is an example assuming you have a Conversation model
            from sqlalchemy import select
            from src.models.orm_models import Conversation
            
            query = select(Conversation).offset(skip).limit(limit).order_by(Conversation.modified_at.desc())
            
            # Use synchronous execution instead of awaiting
            result = session.execute(query)  # Remove the await
            conversations = result.scalars().all()
            return conversations
            
        except Exception as e:
            self.logger.error(f"Error retrieving conversations: {str(e)}")
            raise

    def ping(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                self.logger.debug("Database ping successful")
            self.logger.debug("Database ping successful")
            return True
        except Exception as e:
            self.logger.error(f"Database ping failed: {e}")
            return False

    def close(self):
        """Dispose of the engine and close connections."""
        if self._engine:
            self.logger.info("Disposing database engine")
            try:
                self._engine.dispose()
                self._engine = None
                self._session_factory = None
                self._initialized = False
                self.logger.info("Database engine disposed successfully")
            except Exception as e:
                self.logger.error(f"Error disposing database engine: {e}", exc_info=True)
    # --- Dependency injection helper for FastAPI ---

    def get_db(self):
        """endpoints.
        Dependency to use in FastAPI endpoints.

        Usage:)
            @app.get("/items/") def read_items(db: Session = Depends(db_manager.get_db)):
            def read_items(db: Session = Depends(db_manager.get_db)):
                # Use db session here
        Yields:
        Yields:            SQLAlchemy Session
            SQLAlchemy Session
        """






default_db_manager = DatabaseManager(f"sqlite:///{db_path}")# Initialize default database manager with the correct database            yield session        with self.get_session() as session:            yield session


# Initialize default database manager with the correct database
default_db_manager = DatabaseManager(f"sqlite:///{db_path}")