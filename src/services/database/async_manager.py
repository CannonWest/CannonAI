"""
Asynchronous database manager for SQLAlchemy 2.0 async operations.
Enhanced implementation with improved Windows support and connection handling.
"""

import os
import traceback
import platform
import threading
import time

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import asyncio

from src.utils.logging_utils import get_logger
from src.utils.constants import DATABASE_DIR
from src.utils.qasync_bridge import ensure_qasync_loop

# Get a logger for this module
logger = get_logger(__name__)

# Base class for ORM models
Base = declarative_base()

# Set environment variable to enable SQLAlchemy engine debug
if os.environ.get('DEBUG_SQLALCHEMY', '').lower() in ('1', 'true', 'yes'):
    import logging
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.DEBUG)
    logging.getLogger('aiosqlite').setLevel(logging.DEBUG)


class AsyncDatabaseManager:
    """
    Manages async database connections, session creation, and schema initialization.
    Uses SQLAlchemy 2.0 with asyncio support with improved connection handling.
    """

    # Class variable to track initialization status across instances
    _GLOBAL_INITIALIZED = False
    _GLOBAL_ENGINE = None
    _GLOBAL_SESSION_MAKER = None
    _INIT_LOCK = threading.Lock()

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

        # Validate the connection string
        if not connection_string.startswith(('sqlite+aiosqlite://', 'mysql+aiomysql://', 'postgresql+asyncpg://')):
            logger.warning(f"Connection string may not be compatible with async SQLAlchemy: {connection_string}")

        self.connection_string = connection_string

        # Get the current event loop - use ensure_qasync_loop for reliability
        try:
            self.loop = ensure_qasync_loop()
            logger.debug(f"Using event loop: {id(self.loop)}")
        except RuntimeError as e:
            logger.warning(f"No event loop found in current thread: {str(e)}")
            self.loop = None

        # Initialize instance variables (but delay actual creation)
        self.engine = AsyncDatabaseManager._GLOBAL_ENGINE
        self.async_session = AsyncDatabaseManager._GLOBAL_SESSION_MAKER
        self._initialized = AsyncDatabaseManager._GLOBAL_INITIALIZED

        self.logger = get_logger(f"{__name__}.AsyncDatabaseManager")
        self.logger.info(f"Initialized AsyncDatabaseManager with connection string: {connection_string}")

    def _create_engine(self):
        """
        Create SQLAlchemy engine using the current event loop
        with global engine sharing for improved efficiency
        """
        # Use lock to prevent race conditions during initialization
        with AsyncDatabaseManager._INIT_LOCK:
            # If already globally initialized, use the shared resources
            if AsyncDatabaseManager._GLOBAL_INITIALIZED:
                self.engine = AsyncDatabaseManager._GLOBAL_ENGINE
                self.async_session = AsyncDatabaseManager._GLOBAL_SESSION_MAKER
                self._initialized = True
                self.logger.debug("Using existing global engine and session factory")
                return

            if self.engine is None:
                self.logger.debug("Creating SQLAlchemy async engine")

                try:
                    # Get the current event loop for this thread
                    current_loop = ensure_qasync_loop()
                    self.logger.debug(f"Creating engine with loop: {id(current_loop)}")

                    # IMPORTANT: Improved engine creation with better connection management
                    self.engine = create_async_engine(
                        self.connection_string,
                        echo=False,
                        future=True,  # Use SQLAlchemy 2.0 style
                        pool_pre_ping=True,  # Verify connections before using
                        pool_recycle=300,    # Recycle connections after 5 minutes
                        pool_size=5,         # Maintain 5 connections in the pool
                        max_overflow=10,     # Allow 10 connections beyond pool_size
                        pool_timeout=30,     # Connection timeout of 30 seconds
                        connect_args={       # SQLite-specific args
                            "check_same_thread": False,  # Allow cross-thread usage
                            "timeout": 30,              # SQLite connection timeout
                        } if self.connection_string.startswith('sqlite') else {}
                    )

                    # Use async_sessionmaker for proper session creation
                    self.async_session = async_sessionmaker(
                        self.engine,
                        expire_on_commit=False,
                        class_=AsyncSession
                    )

                    # Store in class variables for sharing
                    AsyncDatabaseManager._GLOBAL_ENGINE = self.engine
                    AsyncDatabaseManager._GLOBAL_SESSION_MAKER = self.async_session
                    AsyncDatabaseManager._GLOBAL_INITIALIZED = True

                    self._initialized = True
                    self.logger.debug(f"Engine and session factory created with loop: {id(current_loop)}")
                except Exception as e:
                    self.logger.error(f"Failed to create SQLAlchemy engine: {str(e)}")
                    self.logger.error(traceback.format_exc())
                    raise RuntimeError(f"Failed to create database engine: {str(e)}") from e

    async def create_tables(self):
        """Create all tables defined in the models if they don't exist with improved Windows handling"""
        self.logger.debug("Ensuring database tables exist")

        try:
            # Make sure engine is created with current event loop
            self._create_engine()

            # Log the current event loop for debugging
            try:
                from src.utils.qasync_bridge import ensure_qasync_loop
                current_loop = ensure_qasync_loop()
                self.logger.debug(f"Creating tables with event loop: {id(current_loop)}")
            except RuntimeError:
                self.logger.warning("No event loop in current thread")
                return False

            # CRITICAL FIX: Special handling for Windows platform
            # Windows has issues with async SQLite operations during table creation
            if platform.system() == "Windows":
                # Use a more reliable direct approach on Windows
                self.logger.debug("Using Windows-specific table creation approach")

                # Fall back to sync approach which is more reliable on Windows
                from sqlalchemy import create_engine
                sync_url = self.connection_string.replace('+aiosqlite', '')
                sync_engine = create_engine(sync_url)

                # Retry mechanism for Windows - sometimes SQLite has locking issues
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        with sync_engine.begin() as connection:
                            Base.metadata.create_all(connection)

                        sync_engine.dispose()
                        self.logger.debug("Tables created successfully with Windows-specific method")
                        return True
                    except Exception as e:
                        if attempt < max_retries - 1:
                            self.logger.warning(f"Table creation attempt {attempt+1} failed: {str(e)}, retrying...")
                            time.sleep(0.5)  # Short delay before retry
                        else:
                            raise
            else:
                # Standard approach for non-Windows platforms
                try:
                    # This approach is more reliable than run_sync
                    async with self.engine.begin() as conn:
                        # Create all tables
                        await conn.run_sync(Base.metadata.create_all)
                        self.logger.debug("Tables created successfully")
                except Exception as e:
                    self.logger.error(f"Error creating tables: {str(e)}")
                    raise

            self.logger.info("Database tables created or verified")
            return True
        except Exception as e:
            self.logger.error(f"Error creating database tables: {str(e)}")
            self.logger.error(traceback.format_exc())

            # Try a last resort method if the standard approach fails
            try:
                self.logger.warning("Attempting last resort table creation method")
                # Create a direct connection to the SQLite database
                import sqlite3
                db_path = self.connection_string.split('///')[-1]

                # Extract SQL from metadata
                from sqlalchemy.schema import CreateTable
                table_creation_sql = []
                for table in Base.metadata.sorted_tables:
                    sql = str(CreateTable(table).compile(dialect=self.engine.dialect))
                    table_creation_sql.append(sql)

                # Execute the SQL directly
                conn = sqlite3.connect(db_path)
                try:
                    for sql in table_creation_sql:
                        conn.execute(sql)
                    conn.commit()
                    self.logger.info("Tables created with last resort method")
                    return True
                finally:
                    conn.close()
            except Exception as fallback_error:
                self.logger.error(f"Last resort table creation also failed: {str(fallback_error)}")

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

        # Create session with proper timeout management
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
                    execution_time = time.time() - start_time

                    # Log slow queries
                    if execution_time > 1.0:  # Log queries taking more than 1 second
                        self.logger.warning(f"Slow database operation: {execution_time:.3f}s")

                    try:
                        await session.close()
                    except Exception as e:
                        self.logger.error(f"Error closing session: {str(e)}")
        except Exception as e:
            self.logger.error(f"Failed to create database session: {str(e)}")
            self.logger.error(traceback.format_exc())

            # Clean up if we couldn't create a session
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
                # Don't reset the global engine - other instances may still be using it
                # Just reset this instance's references
                self.engine = None
                self.async_session = None
                self._initialized = False
        self.logger.info("AsyncDatabaseManager closed")

    async def ping(self) -> bool:
        """
        Test if the database connection is working

        Returns:
            True if connection is working, False otherwise
        """
        if not self._initialized:
            self._create_engine()

        try:
            # Implement retry mechanism for more reliable connections
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with self.engine.connect() as conn:
                        await conn.execute("SELECT 1")
                        return True
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.logger.warning(f"Database ping attempt {attempt+1} failed: {str(e)}, retrying...")
                        await asyncio.sleep(0.5)  # Short delay before retry
                    else:
                        raise
        except Exception as e:
            self.logger.error(f"Database ping failed: {str(e)}")
            return False

    @staticmethod
    async def get_global_instance():
        """
        Get or create a global instance of AsyncDatabaseManager.
        Useful for singleton-like access to the database.

        Returns:
            An initialized AsyncDatabaseManager instance
        """
        manager = AsyncDatabaseManager()
        if not manager._initialized:
            manager._create_engine()
            await manager.create_tables()
        return manager