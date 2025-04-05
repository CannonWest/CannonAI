"""
Database manager for SQLAlchemy operations.
Adapted for web-based architecture with FastAPI.
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

# Import Base from models
from src.models.orm_models import Base

# Create logger for this module
logger = logging.getLogger(__name__)


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

    def __init__(self, connection_string: Optional[str] = None, db_dir: Optional[str] = None):
        """
        Initialize the database manager if not already initialized.

        Args:
            connection_string: SQLAlchemy connection string. If None, uses SQLite.
            db_dir: Directory for SQLite database file if using SQLite.
        """
        # Only initialize once due to singleton pattern
        if self._initialized:
            return

        self.logger = logging.getLogger(f"{__name__}.DatabaseManager")

        # Default database directory and path
        if db_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_dir = os.path.join(base_dir, 'data', 'database')

        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, 'conversations.db')

        # Set connection string if not provided
        if connection_string is None:
            connection_string = f'sqlite:///{db_path}'

        self.connection_string = connection_string
        self.logger.info(f"Initializing DatabaseManager with connection string: {connection_string}")

        # Create engine and session factory
        self._create_engine()
        self._initialized = True

    def _create_engine(self):
        """Create SQLAlchemy engine and session factory."""
        try:
            # Configure engine with appropriate settings
            engine_args = {
                'echo': False,  # Set to True for SQL query logging
                'pool_pre_ping': True,
                'pool_recycle': 3600,  # Recycle connections after 1 hour
            }

            # Add SQLite-specific connect args if using SQLite
            if self.connection_string.startswith('sqlite'):
                engine_args['connect_args'] = {
                    'check_same_thread': False  # Allow multi-threaded access for SQLite
                }

            # Create engine with connection pooling
            self._engine = create_engine(
                self.connection_string,
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

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Provide a transactional scope around a series of operations.

        Usage:
            with db_manager.get_session() as session:
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
            session.commit()
            self.logger.debug(f"Session {session_id} committed")
        except Exception as e:
            self.logger.error(f"Error in database session: {e}", exc_info=True)
            session.rollback()
            self.logger.debug(f"Session {session_id} rolled back")
            raise  # Re-raise the exception after rollback
        finally:
            session.close()
            self.logger.debug(f"Session {session_id} closed")

    def ping(self) -> bool:
        """Test if the database connection is working."""
        if not self._engine:
            self.logger.error("Cannot ping: Engine not initialized")
            return False

        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
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
        """
        Dependency to use in FastAPI endpoints.

        Usage:
            @app.get("/items/")
            def read_items(db: Session = Depends(db_manager.get_db)):
                # Use db session here

        Yields:
            SQLAlchemy Session
        """
        with self.get_session() as session:
            yield session


# Initialize default database manager (can be overridden in app setup)
default_db_manager = DatabaseManager()