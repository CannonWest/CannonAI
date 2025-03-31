# src/services/database/db_manager.py
"""
Synchronous database manager for SQLAlchemy operations.
"""

import os
import traceback
import platform
import threading
import time

# Use standard synchronous SQLAlchemy components
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from contextlib import contextmanager
from typing import Generator, Optional

from src.utils.logging_utils import get_logger
from src.utils.constants import DATABASE_DIR

# Get a logger for this module
logger = get_logger(__name__)

# Base class for ORM models (can be imported from models if preferred)
Base = declarative_base()

# Set environment variable to enable SQLAlchemy engine debug
if os.environ.get('DEBUG_SQLALCHEMY', '').lower() in ('1', 'true', 'yes'):
    import logging
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.DEBUG)

class DatabaseManager:
    """
    Manages synchronous database connections, session creation, and schema initialization.
    Uses standard SQLAlchemy.
    """
    _GLOBAL_ENGINE = None
    _GLOBAL_SESSION_MAKER = None
    _INIT_LOCK = threading.Lock() # Keep lock for thread safety during init

    def __init__(self, connection_string=None):
        """
        Initialize the synchronous database manager.

        Args:
            connection_string: SQLAlchemy connection string for the database.
                               Must be compatible with synchronous drivers (e.g., sqlite:///, postgresql://, mysql+pymysql://).
        """
        db_path = os.path.join(DATABASE_DIR, 'conversations.db')
        try:
            os.makedirs(DATABASE_DIR, exist_ok=True)
            logger.debug(f"Database directory ensured: {DATABASE_DIR}")
        except Exception as e:
            logger.error(f"Failed to create database directory {DATABASE_DIR}: {str(e)}")
            raise

        # Set default connection string if None is provided (use sync driver)
        if connection_string is None:
            # Default to standard sqlite driver
            connection_string = f'sqlite:///{db_path}'
            logger.debug(f"Using default synchronous connection string: {connection_string}")
        else:
            # Remove async driver prefix if present from the async version
            connection_string = connection_string.replace('+aiosqlite', '').replace('+asyncpg','').replace('+aiomysql','')


        self.connection_string = connection_string
        self.engine = None
        self.SessionLocal = None # Renamed from async_session
        self._initialized = False # Instance initialization flag

        self.logger = get_logger(f"{__name__}.DatabaseManager")
        # Attempt to initialize engine/session maker immediately
        self._create_engine_sessionmaker()
        self.logger.info(f"Initialized DatabaseManager with connection string: {connection_string}")


    def _create_engine_sessionmaker(self):
         """Creates the synchronous engine and session factory."""
         # Use lock to prevent race conditions during global initialization
         with DatabaseManager._INIT_LOCK:
             # If global engine exists, reuse it
             if DatabaseManager._GLOBAL_ENGINE is not None:
                 self.engine = DatabaseManager._GLOBAL_ENGINE
                 self.SessionLocal = DatabaseManager._GLOBAL_SESSION_MAKER
                 self._initialized = True # Mark instance as initialized
                 self.logger.debug("Using existing global synchronous engine and session factory.")
                 return

             # Create engine if it doesn't exist globally
             self.logger.debug("Creating SQLAlchemy synchronous engine.")
             try:
                 self.engine = create_engine(
                     self.connection_string,
                     echo=False,
                     # Standard pool settings (adjust as needed)
                     pool_pre_ping=True,
                     pool_recycle=3600, # Recycle connections hourly
                     # SQLite specific args (needed if using threads with SQLite)
                     connect_args={"check_same_thread": False} if self.connection_string.startswith('sqlite') else {}
                 )
                 # Create session factory
                 self.SessionLocal = sessionmaker(
                     autocommit=False, autoflush=False, bind=self.engine, class_=Session
                 )
                 # Store globally
                 DatabaseManager._GLOBAL_ENGINE = self.engine
                 DatabaseManager._GLOBAL_SESSION_MAKER = self.SessionLocal
                 self._initialized = True # Mark instance as initialized
                 self.logger.info("Synchronous engine and session factory created.")

             except Exception as e:
                 self.logger.error(f"Failed to create SQLAlchemy synchronous engine: {str(e)}", exc_info=True)
                 self.engine = None
                 self.SessionLocal = None
                 raise RuntimeError(f"Failed to create database engine: {str(e)}") from e

    def create_tables(self, sync_base):
        """
        Create all tables defined in the models (synchronously).

        Args:
            sync_base: The declarative base instance from your models file.
        """
        if not self.engine:
            self.logger.error("Engine not initialized, cannot create tables.")
            return False
        self.logger.debug("Ensuring database tables exist (synchronously)...")
        try:
            # Use the engine directly to create tables
            # This is thread-safe if the engine is configured correctly (e.g., check_same_thread=False for SQLite)
            sync_base.metadata.create_all(self.engine)
            self.logger.info("Database tables created or verified successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error creating database tables: {str(e)}", exc_info=True)
            return False

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Provide a transactional scope around a series of operations (synchronous).

        Usage:
            with db_manager.get_session() as session:
                # Use session here
        """
        if not self.SessionLocal:
            self.logger.error("Session factory not initialized. Cannot get session.")
            raise RuntimeError("Database session factory not initialized.")

        session = self.SessionLocal()
        self.logger.debug(f"Sync Session {id(session)} acquired.")
        try:
            yield session
            session.commit()
            self.logger.debug(f"Sync Session {id(session)} committed.")
        except Exception as e:
            self.logger.error(f"Error in synchronous database session: {str(e)}", exc_info=True)
            session.rollback()
            self.logger.debug(f"Sync Session {id(session)} rolled back.")
            raise # Re-raise the exception after rollback
        finally:
            session.close()
            self.logger.debug(f"Sync Session {id(session)} closed.")

    def close(self):
        """Dispose of the engine and close connections."""
        # Note: Disposing the global engine affects all instances
        with DatabaseManager._INIT_LOCK:
            if DatabaseManager._GLOBAL_ENGINE is not None:
                self.logger.info("Disposing synchronous database engine.")
                try:
                    DatabaseManager._GLOBAL_ENGINE.dispose()
                    DatabaseManager._GLOBAL_ENGINE = None
                    DatabaseManager._GLOBAL_SESSION_MAKER = None
                    self._initialized = False # Reset instance state
                except Exception as e:
                    self.logger.error(f"Error disposing synchronous engine: {str(e)}", exc_info=True)
            else:
                 self.logger.debug("Synchronous engine already disposed or never created.")

    def ping(self) -> bool:
        """Test if the database connection is working (synchronously)."""
        if not self.engine:
            self.logger.error("Cannot ping: Engine not initialized.")
            return False
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            self.logger.debug("Database ping successful.")
            return True
        except Exception as e:
            self.logger.error(f"Database ping failed: {str(e)}")
            return False

# --- End of Code ---