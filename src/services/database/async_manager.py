"""
Asynchronous database manager for SQLAlchemy 2.0 async operations.
Ensures consistent event loop usage with qasync.
"""

import os
import asyncio
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
        os.makedirs(DATABASE_DIR, exist_ok=True)

        # Set default connection string if None is provided
        if connection_string is None:
            connection_string = f'sqlite+aiosqlite:///{db_path}'

        self.connection_string = connection_string

        # Store the current event loop - IMPORTANT: delay engine creation
        self.loop = asyncio.get_event_loop()
        self.engine = None
        self.async_session = None

        self.logger = get_logger(f"{__name__}.AsyncDatabaseManager")
        self.logger.info(f"Initialized AsyncDatabaseManager with connection string: {connection_string}")

    def _create_engine(self):
        """Create SQLAlchemy engine using the current event loop"""
        if self.engine is None:
            self.logger.debug("Creating SQLAlchemy async engine")

            # Get the current event loop for this thread
            current_loop = asyncio.get_event_loop()

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

    async def create_tables(self):
        """Create all tables defined in the models if they don't exist"""
        self.logger.debug("Ensuring database tables exist")

        try:
            # Make sure engine is created with current event loop
            self._create_engine()

            # Log the current event loop for debugging
            current_loop = asyncio.get_event_loop()
            self.logger.debug(f"Creating tables with event loop: {id(current_loop)}")

            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self.logger.info("Database tables created or verified")
        except Exception as e:
            self.logger.error(f"Error creating database tables: {str(e)}")
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

        async with self.async_session() as session:
            try:
                yield session
            except Exception as e:
                self.logger.error(f"Error in database session: {str(e)}")
                await session.rollback()
                raise

    async def close(self):
        """Close the database engine and all connections"""
        self.logger.debug("Closing AsyncDatabaseManager")
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.async_session = None
        self.logger.info("AsyncDatabaseManager closed")