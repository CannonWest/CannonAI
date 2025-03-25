"""
Asynchronous database manager for SQLAlchemy 2.0 async operations.
Ensures consistent event loop usage with qasync.
"""

import os
import asyncio
import traceback
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.asyncio import async_scoped_session
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from src.utils.logging_utils import get_logger
from src.utils.constants import DATABASE_DIR

# Get a logger for this module
logger = get_logger(__name__)

# Base class for ORM models
Base = declarative_base()

import logging

# Set environment variable to enable SQLAlchemy engine debug
if os.environ.get('DEBUG_SQLALCHEMY', '').lower() in ('1', 'true', 'yes'):
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.DEBUG)
    logging.getLogger('aiosqlite').setLevel(logging.DEBUG)

    # Create a formatted handler for SQLAlchemy logs
    import sys

    sql_handler = logging.StreamHandler(sys.stdout)
    sql_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logging.getLogger('sqlalchemy.engine').addHandler(sql_handler)
    logging.getLogger('sqlalchemy.pool').addHandler(sql_handler)
    logging.getLogger('aiosqlite').addHandler(sql_handler)


class AsyncDatabaseManager:
    """
    Manages async database connections, session creation, and schema initialization.
    Uses SQLAlchemy 2.0 with asyncio support.
    """

    def __init__(self, connection_string=None):
        """
        Initialize the async database manager

        Args:
            connection_string: SQLAlchemy connection string for the database
        """
        # Ensure the directory exists
        db_path = os.path.join(DATABASE_DIR, 'conversations.db')
        try:
            os.makedirs(DATABASE_DIR, exist_ok=True)
            logger.debug(f"Database directory ensured: {DATABASE_DIR}")
        except Exception as e:
            logger.error(f"Failed to create database directory {DATABASE_DIR}: {str(e)}")
            logger.error(traceback.format_exc())
            raise

        # Set default connection string if None is provided
        if connection_string is None:
            connection_string = f'sqlite+aiosqlite:///{db_path}'
            logger.debug(f"Using default connection string: {connection_string}")

        # Validate the connection string has the correct format
        if not connection_string.startswith(('sqlite+aiosqlite://', 'mysql+aiomysql://', 'postgresql+asyncpg://')):
            logger.warning(f"Connection string may not be compatible with async SQLAlchemy: {connection_string}")

        self.connection_string = connection_string

        # Store the current event loop - IMPORTANT: delay engine creation
        try:
            self.loop = asyncio.get_event_loop()
            logger.debug(f"Using event loop: {id(self.loop)}")
        except RuntimeError as e:
            logger.warning(f"No event loop found in current thread: {str(e)}")
            self.loop = None

        self.engine = None
        self.async_session = None

        self.logger = get_logger(f"{__name__}.AsyncDatabaseManager")
        self.logger.info(f"Initialized AsyncDatabaseManager with connection string: {connection_string}")

    def _create_engine(self):
        """Create SQLAlchemy engine using the current event loop"""
        if self.engine is None:
            self.logger.debug("Creating SQLAlchemy async engine")

            try:
                # Get the current event loop for this thread
                current_loop = asyncio.get_event_loop()
                self.logger.debug(f"Creating engine with loop: {id(current_loop)}")

                # Create engine with explicit connect_args and the current loop
                self.engine = create_async_engine(
                    self.connection_string,
                    echo=False,
                    connect_args={
                        "check_same_thread": False
                    }
                )

                # Create session factory
                self.async_session = async_sessionmaker(
                    self.engine,
                    expire_on_commit=False,
                    class_=AsyncSession
                )

                self.logger.debug(f"Engine and session factory created with loop: {id(current_loop)}")
            except Exception as e:
                self.logger.error(f"Failed to create SQLAlchemy engine: {str(e)}")
                self.logger.error(traceback.format_exc())
                raise RuntimeError(f"Failed to create database engine: {str(e)}") from e

    async def create_tables(self):
        """Create all tables defined in the models if they don't exist"""
        self.logger.debug("Ensuring database tables exist")

        try:
            # Make sure engine is created with current event loop
            self._create_engine()

            # Log the current event loop for debugging
            try:
                current_loop = asyncio.get_event_loop()
                self.logger.debug(f"Creating tables with event loop: {id(current_loop)}")
            except RuntimeError:
                self.logger.warning("No event loop in current thread, creating one")
                current_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(current_loop)

            # CRITICAL FIX: Use try-except instead of timeout
            try:
                async with self.engine.begin() as conn:
                    self.logger.debug("Beginning transaction to create tables")
                    await conn.run_sync(Base.metadata.create_all)
                    self.logger.debug("Tables created successfully")
            except Exception as e:
                self.logger.error(f"Error during table creation: {str(e)}")
                raise

            self.logger.info("Database tables created or verified")
            return True
        except Exception as e:
            self.logger.error(f"Error creating database tables: {str(e)}")
            self.logger.error(traceback.format_exc())
            # Re-raise the exception but with a clearer message
            raise RuntimeError(f"Failed to create database tables: {str(e)}") from e

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a new async database session as a context manager

        Usage:
            async with db_manager.get_session() as session:
                # Use session here
        """
        # Make sure engine is created with current event loop
        self._create_engine()

        try:
            async with self.async_session() as session:
                try:
                    yield session
                except Exception as e:
                    self.logger.error(f"Error in database session: {str(e)}")
                    self.logger.error(traceback.format_exc())
                    await session.rollback()
                    raise
        except Exception as e:
            self.logger.error(f"Failed to create database session: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    async def close(self):
        """Close the database engine and all connections"""
        self.logger.debug("Closing AsyncDatabaseManager")
        if self.engine is not None:
            try:
                await self.engine.dispose()
                self.logger.debug("Engine disposed successfully")
            except Exception as e:
                self.logger.error(f"Error disposing engine: {str(e)}")
                self.logger.error(traceback.format_exc())
            finally:
                self.engine = None
                self.async_session = None
        self.logger.info("AsyncDatabaseManager closed")