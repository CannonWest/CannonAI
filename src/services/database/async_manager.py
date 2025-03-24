"""
Asynchronous database manager for SQLAlchemy 2.0 async operations.
"""

import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from src.utils.logging_utils import get_logger
from src.utils.constants import DATABASE_DIR

# Get a logger for this module
logger = get_logger(__name__)

# Base class for ORM models
Base = declarative_base()

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
        self.engine = create_async_engine(connection_string, echo=False)
        self.async_session = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        self.logger = get_logger(f"{__name__}.AsyncDatabaseManager")
        self.logger.info(f"Initialized AsyncDatabaseManager with connection string: {connection_string}")

    async def create_tables(self):
        """Create all tables defined in the models if they don't exist"""
        self.logger.debug("Ensuring database tables exist")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.logger.info("Database tables created or verified")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a new async database session as a context manager

        Usage:
            async with db_manager.get_session() as session:
                # Use session here
        """
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
        await self.engine.dispose()
        self.logger.info("AsyncDatabaseManager closed")