"""
Asynchronous database manager for SQLAlchemy 2.0 async operations.
Improved implementation to ensure consistent event loop usage with qasync.
"""

import os
import asyncio
import traceback
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.asyncio import async_scoped_session
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import time

from src.utils.logging_utils import get_logger
from src.utils.constants import DATABASE_DIR
from src.utils.qasync_bridge import ensure_qasync_loop

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
    Uses SQLAlchemy 2.0 with asyncio support with improved connection handling.
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

        # Store the current event loop - IMPORTANT: Use ensure_qasync_loop() for a consistent loop
        try:
            self.loop = ensure_qasync_loop()
            logger.debug(f"Using event loop: {id(self.loop)}")
        except RuntimeError as e:
            logger.warning(f"No event loop found in current thread: {str(e)}")
            self.loop = None

        # Initialize instance variables (but delay actual creation)
        self.engine = None
        self.async_session = None
        self._initialized = False

        self.logger = get_logger(f"{__name__}.AsyncDatabaseManager")
        self.logger.info(f"Initialized AsyncDatabaseManager with connection string: {connection_string}")

    def _create_engine(self):
        """Create SQLAlchemy engine using the current event loop"""
        if self.engine is None:
            self.logger.debug("Creating SQLAlchemy async engine")

            try:
                # Get the current event loop for this thread
                current_loop = ensure_qasync_loop()
                self.logger.debug(f"Creating engine with loop: {id(current_loop)}")

                # IMPORTANT: Use create_async_engine with proper pooling settings for better connection management
                self.engine = create_async_engine(
                    self.connection_string,
                    echo=False,
                    connect_args={"check_same_thread": False},
                    # Add improved pool settings for better connection management
                    pool_pre_ping=True,  # Verify connections before using them
                    pool_recycle=3600,  # Recycle connections after 1 hour
                    pool_timeout=30,     # Connection timeout of 30 seconds
                    max_overflow=5       # Allow 5 connections beyond pool_size
                )

                # Create session factory
                self.async_session = async_sessionmaker(
                    self.engine,
                    expire_on_commit=False,
                    class_=AsyncSession
                )

                self._initialized = True
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
                current_loop = ensure_qasync_loop()
                self.logger.debug(f"Creating tables with event loop: {id(current_loop)}")
            except RuntimeError:
                self.logger.warning("No event loop in current thread, creating one")
                from src.utils.qasync_bridge import install
                current_loop = install()

            # IMPROVED APPROACH: Use a non-async run_sync method for table creation that avoids context managers
            # This is more reliable than using async context managers which can cause issues
            def _create_all_tables(conn):
                # This function runs in a thread and doesn't need asyncio
                self.logger.debug("Creating tables synchronously via run_sync")
                Base.metadata.create_all(conn)
                return True

            try:
                # Use run_sync which is more reliable for schema creation
                async with self.engine.begin() as conn:
                    await conn.run_sync(_create_all_tables)
                    self.logger.debug("Tables created successfully via run_sync")
            except RuntimeError as e:
                # If we get "no running event loop", fallback to alternative approach
                if "no running event loop" in str(e):
                    self.logger.warning(f"Using fallback method for table creation: {str(e)}")

                    # FALLBACK: Use SQLAlchemy directly in a with statement without async
                    from sqlalchemy import create_engine
                    sync_url = self.connection_string.replace('+aiosqlite', '')
                    sync_engine = create_engine(sync_url)
                    with sync_engine.begin() as connection:
                        Base.metadata.create_all(connection)
                    sync_engine.dispose()
                    self.logger.debug("Tables created successfully with fallback method")
                else:
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
        Get a new async database session as a context manager with improved error handling

        Usage:
            async with db_manager.get_session() as session:
                # Use session here
        """
        # Make sure engine is created with current event loop
        if not self._initialized:
            self._create_engine()

        # IMPROVED: Set up timeout management
        timeout = 10.0  # 10 seconds timeout
        start_time = time.time()

        session = None
        try:
            # Get the session from the factory
            session = self.async_session()

            # Yield the session to the caller
            try:
                yield session
            except Exception as e:
                self.logger.error(f"Error in database session: {str(e)}")
                if session and not session.is_active:
                    self.logger.debug("Session rollback needed")
                    await session.rollback()
                raise
            finally:
                # Always close the session when done
                if session:
                    if time.time() - start_time > timeout:
                        self.logger.warning(f"Session operation took longer than {timeout}s")

                    try:
                        await session.close()
                    except Exception as e:
                        self.logger.error(f"Error closing session: {str(e)}")
        except Exception as e:
            self.logger.error(f"Failed to create database session: {str(e)}")
            self.logger.error(traceback.format_exc())

            # If we couldn't create a session, try to clean up
            if session:
                try:
                    await session.close()
                except:
                    pass

            raise

    async def close(self):
        """Close the database engine and all connections"""
        self.logger.debug("Closing AsyncDatabaseManager")
        if self.engine is not None:
            try:
                # Properly dispose of the engine and all its connections
                await self.engine.dispose()
                self.logger.debug("Engine disposed successfully")
            except Exception as e:
                self.logger.error(f"Error disposing engine: {str(e)}")
                self.logger.error(traceback.format_exc())
            finally:
                self.engine = None
                self.async_session = None
                self._initialized = False
        self.logger.info("AsyncDatabaseManager closed")

    async def execute_query(self, query, params=None):
        """
        Execute a raw SQL query with improved connection management
        This provides a more direct way to run queries when needed

        Args:
            query: The SQL query to execute
            params: Optional parameters for the query

        Returns:
            The query result
        """
        if not self._initialized:
            self._create_engine()

        async with self.get_session() as session:
            try:
                result = await session.execute(query, params or {})
                await session.commit()
                return result
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error executing query: {str(e)}")
                raise

    async def ping(self) -> bool:
        """
        Test if the database connection is working

        Returns:
            True if connection is working, False otherwise
        """
        if not self._initialized:
            self._create_engine()

        try:
            async with self.engine.connect() as conn:
                await conn.execute("SELECT 1")
                return True
        except Exception as e:
            self.logger.error(f"Database ping failed: {str(e)}")
            return False