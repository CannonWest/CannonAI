# src/models/db_manager.py
"""
Database management utilities for the OpenAI Chat application.
"""

import os
import queue
import random
import sqlite3
import threading
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

from PyQt6.QtCore import QUuid

from src.utils import DATABASE_DIR, DATABASE_FILE
from src.utils.logging_utils import get_logger, log_exception

# Get a logger for this module
logger = get_logger(__name__)


class DatabaseManager:
    """Handles SQLite database connections and operations with improved concurrency support"""

    # Class variable for the singleton instance
    _instance = None
    _instance_lock = threading.RLock()

    def __new__(cls, db_path=None):
        """Singleton pattern to ensure only one database manager exists"""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                # Don't initialize here - just mark as not initialized
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path=None):
        """Initialize the database manager if not already initialized"""
        with self.__class__._instance_lock:
            if getattr(self, '_initialized', False):
                return

            self._initialized = True
            self.db_path = db_path or DATABASE_FILE
            self.logger = get_logger(f"{__name__}.DatabaseManager")

            # Create database directory if it doesn't exist
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

            # Thread-local storage for connections - ensure it exists
            self._local = threading.local()

            # Initialize the connection to None for this thread
            self._local.connection = None

            # Track open connections globally for shutdown
            self._all_connections = set()
            self._connections_lock = threading.RLock()

            # Dictionary to store connection metadata instead of adding attributes to connection objects
            self._connection_metadata = {}

            # Main lock for serializing critical database operations
            self._db_lock = threading.RLock()

            # Queue for file attachments to be processed in a serialized manner
            self._file_queue = queue.Queue()
            self._file_processor_running = False
            self._file_processor_thread = None

            # Initialize database schema with direct SQLite connection to avoid potential issues
            try:
                # Use a direct connection to initialize the database schema
                conn = sqlite3.connect(self.db_path, timeout=60.0)
                cursor = conn.cursor()

                # Create tables
                cursor.executescript('''
                    -- Conversations table to store conversation metadata
                    CREATE TABLE IF NOT EXISTS conversations (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        modified_at TEXT NOT NULL,
                        current_node_id TEXT NOT NULL,
                        system_message TEXT NOT NULL
                    );

                    -- Messages table to store individual messages
                    CREATE TABLE IF NOT EXISTS messages (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        parent_id TEXT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        response_id TEXT,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                        FOREIGN KEY (parent_id) REFERENCES messages(id) ON DELETE CASCADE
                    );

                    -- Message metadata table for model info, parameters, etc.
                    CREATE TABLE IF NOT EXISTS message_metadata (
                        message_id TEXT NOT NULL,
                        metadata_type TEXT NOT NULL,
                        metadata_value TEXT NOT NULL,
                        PRIMARY KEY (message_id, metadata_type),
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    );

                    -- Reasoning steps table for Response API reasoning
                    CREATE TABLE IF NOT EXISTS reasoning_steps (
                        id TEXT PRIMARY KEY,
                        message_id TEXT NOT NULL,
                        step_name TEXT NOT NULL,
                        step_content TEXT NOT NULL,
                        step_order INTEGER NOT NULL,
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    );

                    -- File attachments table with optimized storage
                    CREATE TABLE IF NOT EXISTS file_attachments (
                        id TEXT PRIMARY KEY,
                        message_id TEXT NOT NULL,
                        file_name TEXT NOT NULL, 
                        display_name TEXT,
                        mime_type TEXT NOT NULL,
                        token_count INTEGER NOT NULL,
                        file_size INTEGER NOT NULL DEFAULT 0,
                        file_hash TEXT NOT NULL DEFAULT "",
                        storage_type TEXT NOT NULL DEFAULT 'database',
                        content_preview TEXT,
                        storage_path TEXT,
                        content TEXT,
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    );

                    -- Indices for faster lookups
                    CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
                    CREATE INDEX IF NOT EXISTS idx_messages_parent_id ON messages(parent_id);
                    CREATE INDEX IF NOT EXISTS idx_message_metadata_message_id ON message_metadata(message_id);
                    CREATE INDEX IF NOT EXISTS idx_file_attachments_message_id ON file_attachments(message_id);
                    CREATE INDEX IF NOT EXISTS idx_file_attachments_file_hash ON file_attachments(file_hash);
                    CREATE INDEX IF NOT EXISTS idx_reasoning_steps_message_id ON reasoning_steps(message_id);
                ''')

                conn.commit()
                conn.close()

                self.logger.info("Database schema initialized successfully")
            except Exception as e:
                self.logger.error(f"Error initializing database schema: {str(e)}")
                # Log but don't propagate the error to allow for recovery later

            # Start the file processor thread - but only after initialization is complete
            self._start_file_processor()

            self.logger.info(f"Database manager initialized with database at {self.db_path}")

    def get_connection(self):
        """
        Get a database connection with advanced reliability, connection tracking,
        and proper error handling.

        This implementation uses a connection pooling approach with thread-local storage
        and ensures all connections are properly validated before use.
        """
        import time

        # Initialize connection metadata tracking if not already present
        if not hasattr(self, '_connection_metadata'):
            self._connection_metadata = {}

        # Track timing for performance logging
        start_time = time.time()

        # First try to get an existing connection from thread-local storage
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            try:
                # Test if the existing connection is valid with a simple query
                result = self._local.connection.execute("SELECT 1").fetchone()

                if result and result[0] == 1:
                    # Connection is valid
                    return self._local.connection

            except sqlite3.Error as e:
                # Connection is invalid - log and remove it
                conn_id = id(self._local.connection)
                self.logger.warning(f"Connection {conn_id} failed validation: {str(e)}")

                # Clean up the invalid connection
                try:
                    with self._connections_lock:
                        if self._local.connection in self._all_connections:
                            self._all_connections.remove(self._local.connection)

                        # Remove metadata if it exists
                        if conn_id in self._connection_metadata:
                            del self._connection_metadata[conn_id]

                    self._local.connection.close()
                except Exception as close_error:
                    self.logger.warning(f"Error closing invalid connection: {str(close_error)}")

                # Clear the thread-local reference
                self._local.connection = None

        # At this point we need a new connection
        # Use a lock to prevent multiple threads from creating connections simultaneously
        with self._db_lock:
            try:
                # Use the specialized method to create a stable connection
                conn = self._create_stable_connection()

                # Store in thread-local storage
                self._local.connection = conn

                # Log connection creation time for performance diagnostics
                creation_time = time.time() - start_time
                if creation_time > 0.1:  # Only log slow connection creations
                    conn_id = id(conn)
                    self.logger.info(f"Connection {conn_id} created in {creation_time:.3f}s")

                return conn

            except Exception as e:
                # Connection creation failed - critical error
                self.logger.error(f"Failed to create database connection: {str(e)}")

                # Try one last emergency fallback with minimal settings
                try:
                    # Basic connection with minimal settings - last resort
                    conn = sqlite3.connect(self.db_path, timeout=60.0)
                    conn.row_factory = sqlite3.Row

                    # Test that it works
                    if not conn.execute("SELECT 1").fetchone():
                        raise sqlite3.OperationalError("Emergency connection test failed")

                    self.logger.warning("Created emergency fallback database connection")

                    # Store in thread-local and tracking
                    self._local.connection = conn

                    # Track connection metadata
                    conn_id = id(conn)
                    self._connection_metadata[conn_id] = {
                        'created_at': time.time(),
                        'id': conn_id,
                        'emergency': True
                    }

                    with self._connections_lock:
                        self._all_connections.add(conn)

                    return conn

                except Exception as e2:
                    # All connection attempts have failed - critical error
                    self.logger.critical(f"All connection attempts failed: {str(e2)}")
                    raise sqlite3.OperationalError(f"Cannot create database connection: {str(e2)}")

    def _create_stable_connection(self):
        """
        Create a new stable database connection with special configuration.

        This function ensures connections are created with the most stable settings,
        handles connection validation, and provides detailed logging.
        """
        import time
        import random

        # Track attempts for diagnostics
        attempt = 0
        max_attempts = 3
        last_error = None

        # Initialize connection metadata tracking if not already present
        if not hasattr(self, '_connection_metadata'):
            self._connection_metadata = {}

        while attempt < max_attempts:
            try:
                # Add some randomized backoff between attempts
                if attempt > 0:
                    backoff = 0.1 * (2 ** attempt) * (0.5 + random.random())
                    time.sleep(backoff)
                    self.logger.debug(f"Retrying connection creation (attempt {attempt + 1}/{max_attempts})")

                # Create the connection with very conservative settings
                self.logger.debug(f"Creating fresh database connection to {self.db_path}")

                # Create a shared directory if needed
                import os
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

                # Use a more explicit connect with conservative timeouts
                conn = sqlite3.connect(
                    database=self.db_path,
                    timeout=60.0,  # Very generous timeout
                    isolation_level="DEFERRED",  # Standard isolation level
                    check_same_thread=False  # Allow cross-thread usage (we'll manage this ourselves)
                )

                # Set row factory
                conn.row_factory = sqlite3.Row

                # Configure connection with special retry logic
                cursor = conn.cursor()

                # First checkpoint the WAL to make it more stable
                try:
                    cursor.execute("PRAGMA wal_checkpoint(PASSIVE)")
                except sqlite3.OperationalError:
                    # This might fail if WAL mode is not enabled yet, which is fine
                    pass

                # Use WAL mode for improved concurrency
                cursor.execute("PRAGMA journal_mode=WAL")

                # Use normal synchronous mode for better performance while still being safe
                cursor.execute("PRAGMA synchronous=NORMAL")

                # Set a long busy timeout (30 seconds)
                cursor.execute("PRAGMA busy_timeout=30000")

                # Force these settings to take effect with a small transaction
                conn.commit()

                # Verify the connection works
                result = cursor.execute("SELECT 1").fetchone()
                if not result or result[0] != 1:
                    raise sqlite3.OperationalError("Connection verification query failed")

                # Generate a unique ID for this connection
                connection_id = id(conn)

                # Store metadata in our dictionary instead of on the connection object
                self._connection_metadata[connection_id] = {
                    'created_at': time.time(),
                    'id': connection_id
                }

                self.logger.debug(f"Connection {connection_id} created successfully")

                # Add this connection to the tracked set
                with self._connections_lock:
                    self._all_connections.add(conn)

                # Return the fully configured connection
                return conn

            except Exception as e:
                attempt += 1
                last_error = e
                self.logger.warning(f"Error creating database connection (attempt {attempt}/{max_attempts}): {str(e)}")

        # If we get here, all attempts failed
        self.logger.error(f"Failed to create stable connection after {max_attempts} attempts. Last error: {str(last_error)}")
        raise last_error or sqlite3.OperationalError("Failed to create database connection")

    def verify_database_health(self):
        """
        Perform a comprehensive health check on the database.

        This method validates the database file, schema integrity, and connection
        pool health. It attempts to fix any issues it finds.

        Returns:
            bool: True if database is healthy, False if there are critical issues
        """
        self.logger.info("Performing database health check")
        issues_found = 0

        try:
            # Step 1: Check if the database file exists
            import os
            if not os.path.exists(self.db_path):
                self.logger.error(f"Database file not found at {self.db_path}")
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
                issues_found += 1

            # Step 2: Try to get a fresh connection (don't use our connection pool methods)
            connection_ok = False
            test_conn = None
            try:
                # Create a standalone connection just for testing
                test_conn = sqlite3.connect(self.db_path, timeout=30.0)
                test_conn.row_factory = sqlite3.Row

                # Test a simple query
                cursor = test_conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

                if result and result[0] == 1:
                    connection_ok = True
                    self.logger.info("Database connection test passed")
                else:
                    self.logger.warning("Database connection test returned unexpected result")
                    issues_found += 1

                # Check schema integrity
                try:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = [row['name'] for row in cursor.fetchall()]

                    expected_tables = [
                        'conversations', 'messages', 'message_metadata',
                        'reasoning_steps', 'file_attachments'
                    ]

                    missing_tables = [t for t in expected_tables if t not in tables]
                    if missing_tables:
                        self.logger.warning(f"Missing tables in database: {', '.join(missing_tables)}")
                        issues_found += 1
                    else:
                        self.logger.info("Database schema integrity check passed")
                except Exception as schema_error:
                    self.logger.error(f"Schema integrity check failed: {str(schema_error)}")
                    issues_found += 1

            except Exception as conn_error:
                self.logger.error(f"Failed to establish test connection: {str(conn_error)}")
                connection_ok = False
                issues_found += 1
            finally:
                # Close the test connection
                if test_conn:
                    try:
                        test_conn.close()
                    except Exception as close_error:
                        self.logger.warning(f"Error closing test connection: {str(close_error)}")

            # Step 3: If connection failed, try to diagnose and fix the issue
            if not connection_ok:
                self.logger.warning("Attempting to diagnose connection issues...")

                # Check if database is locked by another process
                import subprocess
                import sys
                import platform

                if platform.system() == "Windows":
                    try:
                        # On Windows, try to check for locks using handle
                        db_dir = os.path.dirname(self.db_path)
                        self.logger.info(f"Testing database directory access permissions for {db_dir}")

                        # Test write permissions
                        test_file = os.path.join(db_dir, "_db_test_access.tmp")
                        try:
                            with open(test_file, 'w') as f:
                                f.write("test")
                            os.remove(test_file)
                            self.logger.info("Directory is writable")
                        except Exception as perm_error:
                            self.logger.error(f"Directory permission error: {str(perm_error)}")
                            issues_found += 1

                    except Exception as diag_error:
                        self.logger.error(f"Diagnostics error: {str(diag_error)}")

                # Try to reset connections
                self.logger.info("Resetting all database connections")
                self._close_connections()

            # Step 4: Check thread-local connection if it exists
            if hasattr(self._local, 'connection') and self._local.connection is not None:
                try:
                    # Test if thread-local connection is valid
                    self._local.connection.execute("SELECT 1").fetchone()
                    self.logger.info("Thread-local connection is valid")
                except Exception as local_error:
                    self.logger.warning(f"Thread-local connection is invalid: {str(local_error)}")
                    self._local.connection = None
                    issues_found += 1

            # Step 5: If needed, manually initialize database schema
            if issues_found > 0:
                self.logger.warning(f"Found {issues_found} database issues, attempting to fix by reinitializing schema")
                try:
                    # Create a direct connection without using our connection pooling
                    repair_conn = sqlite3.connect(self.db_path, timeout=60.0)

                    # Create the tables directly without using initialize_database
                    repair_conn.executescript('''
                        -- Conversations table to store conversation metadata
                        CREATE TABLE IF NOT EXISTS conversations (
                            id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            modified_at TEXT NOT NULL,
                            current_node_id TEXT NOT NULL,
                            system_message TEXT NOT NULL
                        );

                        -- Messages table to store individual messages
                        CREATE TABLE IF NOT EXISTS messages (
                            id TEXT PRIMARY KEY,
                            conversation_id TEXT NOT NULL,
                            parent_id TEXT,
                            role TEXT NOT NULL,
                            content TEXT NOT NULL,
                            timestamp TEXT NOT NULL,
                            response_id TEXT,
                            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                            FOREIGN KEY (parent_id) REFERENCES messages(id) ON DELETE CASCADE
                        );

                        -- Message metadata table for model info, parameters, etc.
                        CREATE TABLE IF NOT EXISTS message_metadata (
                            message_id TEXT NOT NULL,
                            metadata_type TEXT NOT NULL,
                            metadata_value TEXT NOT NULL,
                            PRIMARY KEY (message_id, metadata_type),
                            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                        );

                        -- Reasoning steps table for Response API reasoning
                        CREATE TABLE IF NOT EXISTS reasoning_steps (
                            id TEXT PRIMARY KEY,
                            message_id TEXT NOT NULL,
                            step_name TEXT NOT NULL,
                            step_content TEXT NOT NULL,
                            step_order INTEGER NOT NULL,
                            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                        );

                        -- File attachments table with optimized storage
                        CREATE TABLE IF NOT EXISTS file_attachments (
                            id TEXT PRIMARY KEY,
                            message_id TEXT NOT NULL,
                            file_name TEXT NOT NULL,
                            display_name TEXT,
                            mime_type TEXT NOT NULL,
                            token_count INTEGER NOT NULL,
                            file_size INTEGER NOT NULL DEFAULT 0,
                            file_hash TEXT NOT NULL DEFAULT "",
                            storage_type TEXT NOT NULL DEFAULT 'database',
                            content_preview TEXT,
                            storage_path TEXT,
                            content TEXT,
                            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                        );

                        -- Indices for faster lookups
                        CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
                        CREATE INDEX IF NOT EXISTS idx_messages_parent_id ON messages(parent_id);
                        CREATE INDEX IF NOT EXISTS idx_message_metadata_message_id ON message_metadata(message_id);
                        CREATE INDEX IF NOT EXISTS idx_file_attachments_message_id ON file_attachments(message_id);
                        CREATE INDEX IF NOT EXISTS idx_file_attachments_file_hash ON file_attachments(file_hash);
                        CREATE INDEX IF NOT EXISTS idx_reasoning_steps_message_id ON reasoning_steps(message_id);
                    ''')

                    repair_conn.commit()
                    repair_conn.close()

                    self.logger.info("Database schema repaired manually")
                    issues_found -= 1  # Reduce issue count if successful
                except Exception as init_error:
                    self.logger.error(f"Failed to manually repair database schema: {str(init_error)}")

            # Report health check results
            if issues_found <= 0:
                self.logger.info("Database health check completed successfully - no issues found")
                return True
            else:
                self.logger.warning(f"Database health check completed with {issues_found} unresolved issues")
                return False

        except Exception as e:
            self.logger.error(f"Database health check failed with error: {str(e)}")
            return False

    #########END BLOCK ALTER###########
    def debug_print_conversations(self):
        """Print all conversations in the database for debugging"""
        # Always get a fresh connection here
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM conversations')
            conversations = cursor.fetchall()

            print(f"===== DEBUG: Found {len(conversations)} conversations in database =====")
            for conv in conversations:
                print(f"ID: {conv['id']}, Name: {conv['name']}, Modified: {conv['modified_at']}")

                # Count messages in this conversation
                cursor.execute('SELECT COUNT(*) FROM messages WHERE conversation_id = ?', (conv['id'],))
                message_count = cursor.fetchone()[0]
                print(f"  Messages: {message_count}")

            print("=====================================================")

        except Exception as e:
            print(f"DEBUG: Error querying conversations: {str(e)}")
            self.logger.error(f"Error in debug_print_conversations: {str(e)}")
        # Don't close the connection in the finally block
        # This method should not be closing connections as it may be reused by thread-local storage


    def _start_file_processor(self):
        """Start the background thread for processing file attachments"""
        if self._file_processor_running:
            return

        self._file_processor_running = True

        def process_file_queue():
            self.logger.info("File attachment processor thread started")
            while self._file_processor_running:
                try:
                    # Get the next file task with a timeout
                    try:
                        task = self._file_queue.get(timeout=5.0)
                    except queue.Empty:
                        # No tasks, just continue the loop
                        continue

                    # Process the file attachment
                    try:
                        message_id, file_info, storage_type, result_queue = task

                        # Use a dedicated connection for file processing
                        # Create a new connection each time to avoid conflicts
                        conn = sqlite3.connect(self.db_path)
                        conn.row_factory = sqlite3.Row

                        # Set timeout for this connection
                        cursor = conn.cursor()
                        cursor.execute("PRAGMA busy_timeout=10000")  # 10-second timeout

                        try:
                            # Process the file attachment with a dedicated connection
                            file_id = self._process_file_attachment(conn, message_id, file_info, storage_type)

                            # Put the result in the result queue if provided
                            if result_queue:
                                result_queue.put((True, file_id))
                        except Exception as e:
                            self.logger.error(f"Error processing file attachment: {str(e)}")
                            # Put the error in the result queue if provided
                            if result_queue:
                                result_queue.put((False, str(e)))
                        finally:
                            # Always close the dedicated connection
                            conn.close()

                    finally:
                        # Mark the task as done
                        self._file_queue.task_done()

                except Exception as e:
                    self.logger.error(f"Error in file processor thread: {str(e)}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                    # Sleep briefly to avoid tight loop on errors
                    time.sleep(0.1)

        # Start the processor thread
        self._file_processor_thread = threading.Thread(
            target=process_file_queue,
            name="FileAttachmentProcessor",
            daemon=True
        )
        self._file_processor_thread.start()

    def get_path_to_root(self, node_id):
        """Get the path from a node to the root with retry logic and robust connection handling"""
        if not node_id:
            self.logger.error("Attempted to get path to root with None node_id")
            return []

        max_retries = 3
        retry_count = 0
        backoff_time = 0.1  # Start with 100ms

        while retry_count < max_retries:
            # Get a fresh connection each time - don't reuse or close the thread-local connection
            conn = None
            try:
                # Use the thread-safe connection getter that maintains connections properly
                conn = self.get_connection()

                # Set a longer timeout for this operation
                conn.execute("PRAGMA busy_timeout = 10000")  # 10 seconds

                cursor = conn.cursor()
                path = []
                current_id = node_id

                while current_id:
                    # Get the current node
                    cursor.execute(
                        'SELECT * FROM messages WHERE id = ?',
                        (current_id,)
                    )
                    message = cursor.fetchone()

                    if not message:
                        self.logger.warning(f"No message found for ID {current_id}")
                        break

                    # Create node object
                    try:
                        node = self._create_node_from_db_row(message)
                        if node:
                            # Add to path (at beginning to maintain root-to-node order)
                            path.insert(0, node)
                        else:
                            self.logger.error(f"Failed to create node from row for ID {current_id}")
                            break
                    except Exception as e:
                        self.logger.error(f"Error creating node from row for ID {current_id}: {str(e)}")
                        break

                    # Move to parent
                    current_id = message['parent_id']

                # Extra validation before returning
                valid_path = [node for node in path if node is not None]
                if len(valid_path) != len(path):
                    self.logger.warning(f"Filtered {len(path) - len(valid_path)} None nodes from path")

                return valid_path

            except sqlite3.OperationalError as e:
                # Handle database lock or busy errors with retries
                if "database is locked" in str(e) or "database is busy" in str(e) or "closed database" in str(e):
                    retry_count += 1
                    self.logger.warning(f"Database error in get_path_to_root, retry {retry_count}/{max_retries}: {str(e)}")

                    # Use exponential backoff with a bit of randomness
                    import time
                    import random
                    sleep_time = backoff_time * (1.0 + random.random() * 0.5)
                    time.sleep(sleep_time)
                    backoff_time *= 2  # Double the backoff time for next retry

                    # Clear the thread-local connection to force creating a new one
                    if hasattr(self._local, 'connection'):
                        self._local.connection = None
                else:
                    # Other operational errors should be logged and reported
                    self.logger.error(f"SQLite error in get_path_to_root: {str(e)}")
                    return []
            except Exception as e:
                self.logger.error(f"Error getting path to root for node {node_id}: {str(e)}")
                return []  # Return empty list instead of None on error

            # Don't close the connection - connection pooling is handled by get_connection

        # If we get here, we've exhausted retries
        self.logger.error(f"Failed to get path to root for node {node_id} after {max_retries} retries")
        return []

    def get_node_children(self, node_id):
        """Get children of a node with retry logic for database errors"""
        max_retries = 3
        retry_count = 0
        backoff_time = 0.1  # Start with 100ms

        while retry_count < max_retries:
            try:
                # Get a connection using the thread-safe method
                conn = self.get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    'SELECT * FROM messages WHERE parent_id = ?',
                    (node_id,)
                )

                children = []
                rows = cursor.fetchall()

                # Log count for debugging
                self.logger.debug(f"Found {len(rows)} children for node {node_id}")

                # Process each row
                for row in rows:
                    try:
                        child = self._create_node_from_db_row(row)
                        if child:
                            children.append(child)
                        else:
                            self.logger.warning(f"Failed to create child node for row {row['id']}")
                    except Exception as row_error:
                        self.logger.warning(f"Error creating child node: {str(row_error)}")
                        # Continue with next row instead of failing completely

                return children

            except sqlite3.OperationalError as e:
                # Handle database lock or busy errors with retries
                if "database is locked" in str(e) or "database is busy" in str(e) or "closed database" in str(e):
                    retry_count += 1
                    self.logger.warning(f"Database error in get_node_children, retry {retry_count}/{max_retries}: {str(e)}")

                    # Use exponential backoff with a bit of randomness
                    import time
                    import random
                    sleep_time = backoff_time * (1.0 + random.random() * 0.5)
                    time.sleep(sleep_time)
                    backoff_time *= 2  # Double the backoff time for next retry

                    # Clear the thread-local connection to force creating a new one
                    if hasattr(self._local, 'connection'):
                        self._local.connection = None
                else:
                    # Other operational errors should be logged and reported
                    self.logger.error(f"SQLite error in get_node_children: {str(e)}")
                    return []
            except Exception as e:
                self.logger.error(f"Error getting children for node {node_id}")
                log_exception(self.logger, e, f"Failed to get node children")
                return []

        # If we get here, we've exhausted retries
        self.logger.error(f"Failed to get children for node {node_id} after {max_retries} retries")
        return []

    def get_node_metadata(self, node_id):
        """Public method to get metadata for a node - forwards to _get_node_metadata"""
        return self._get_node_metadata(node_id)

    # Add this method to the DatabaseManager class
    def get_message(self, message_id):
        """Get a message by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                'SELECT * FROM messages WHERE id = ?',
                (message_id,)
            )
            message = cursor.fetchone()

            if not message:
                return None

            return self._create_node_from_db_row(message)

        except Exception as e:
            self.logger.error(f"Error getting message {message_id}")
            log_exception(self.logger, e, f"Failed to get message")
            return None
        finally:
            conn.close()

    def _create_node_from_db_row(self, row):
        """Create a DBMessageNode from a database row"""
        from src.models.db_conversation import DBMessageNode

        try:
            # Get metadata - handle both 3-tuple and 4-tuple returns for backward compatibility
            metadata_result = self._get_node_metadata(row['id'])

            # Handle different tuple lengths from _get_node_metadata
            if len(metadata_result) == 4:
                model_info, parameters, token_usage, reasoning_steps = metadata_result
            else:
                # Fall back to old 3-tuple format
                model_info, parameters, token_usage = metadata_result
                reasoning_steps = []

            # Get file attachments
            attached_files = self._get_node_attachments(row['id'])

            # Create the node - now passing response_id from the database row
            node = DBMessageNode(
                id=row['id'],
                conversation_id=row['conversation_id'],
                role=row['role'],
                content=row['content'],
                parent_id=row['parent_id'],
                timestamp=row['timestamp'],
                model_info=model_info,
                parameters=parameters,
                token_usage=token_usage,
                attached_files=attached_files,
                response_id=row['response_id']  # Add the response_id parameter
            )

            # Set database manager for lazy loading children
            node._db_manager = self

            # Add reasoning steps if available
            if reasoning_steps:
                node._reasoning_steps = reasoning_steps

            return node
        except Exception as e:
            self.logger.error(f"Error creating node from row: {str(e)}")
            return None  # Return None rather than crashing

    def _get_node_metadata(self, node_id):
        """Get metadata for a node with improved error handling"""
        if not node_id:
            self.logger.error("Attempted to get metadata with None node_id")
            return {}, {}, {}, []

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            model_info = {}
            parameters = {}
            token_usage = {}
            reasoning_steps = []

            try:
                cursor.execute(
                    'SELECT metadata_type, metadata_value FROM message_metadata WHERE message_id = ?',
                    (node_id,)
                )

                import json
                for row in cursor.fetchall():
                    try:
                        metadata_type = row['metadata_type']

                        # Special handling for reasoning steps
                        if metadata_type == 'reasoning_steps':
                            try:
                                reasoning_steps = json.loads(row['metadata_value'])
                                continue
                            except Exception as e:
                                self.logger.error(f"Error parsing reasoning steps: {e}")
                                continue

                        # Regular metadata handling
                        try:
                            metadata_value = json.loads(row['metadata_value'])

                            if metadata_type.startswith('model_info.'):
                                key = metadata_type.replace('model_info.', '')
                                model_info[key] = metadata_value
                            elif metadata_type.startswith('parameters.'):
                                key = metadata_type.replace('parameters.', '')
                                parameters[key] = metadata_value
                            elif metadata_type.startswith('token_usage.'):
                                key = metadata_type.replace('token_usage.', '')
                                token_usage[key] = metadata_value
                        except Exception as e:
                            self.logger.error(f"Error parsing metadata {metadata_type}: {e}")
                    except Exception as e:
                        self.logger.error(f"Error processing metadata row: {e}")
            except Exception as e:
                self.logger.error(f"Error querying metadata: {e}")

            # Return tuple including reasoning steps
            return model_info, parameters, token_usage, reasoning_steps

        finally:
            conn.close()

    def _get_node_attachments(self, node_id):
        """Get file attachments for a node"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            attached_files = []

            cursor.execute(
                'SELECT * FROM file_attachments WHERE message_id = ?',
                (node_id,)
            )

            for row in cursor.fetchall():
                attached_files.append({
                    'file_name': row['file_name'],
                    'mime_type': row['mime_type'],
                    'content': row['content'],
                    'token_count': row['token_count']
                })

            return attached_files

        finally:
            conn.close()

    """
    Database schema migration utility to safely upgrade existing databases.
    """

    def initialize_database(self):
        """Create database tables if they don't exist with safe migration for existing DBs"""
        self.logger.debug(f"Initializing database at {self.db_path}")

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Create base tables if they don't exist
            cursor.executescript('''
                -- Conversations table to store conversation metadata
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    modified_at TEXT NOT NULL,
                    current_node_id TEXT NOT NULL,
                    system_message TEXT NOT NULL
                );

                -- Messages table to store individual messages
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    parent_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    response_id TEXT,  -- Store OpenAI Response ID
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_id) REFERENCES messages(id) ON DELETE CASCADE
                );

                -- Message metadata table for model info, parameters, etc.
                CREATE TABLE IF NOT EXISTS message_metadata (
                    message_id TEXT NOT NULL,
                    metadata_type TEXT NOT NULL,
                    metadata_value TEXT NOT NULL,
                    PRIMARY KEY (message_id, metadata_type),
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                );

                -- Reasoning steps table for Response API reasoning
                CREATE TABLE IF NOT EXISTS reasoning_steps (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    step_content TEXT NOT NULL,
                    step_order INTEGER NOT NULL,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                );
            ''')

            # Check if file_attachments table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_attachments'")
            table_exists = cursor.fetchone() is not None

            if not table_exists:
                # Create new table with all columns if it doesn't exist
                cursor.executescript('''
                    -- File attachments table with optimized storage
                    CREATE TABLE IF NOT EXISTS file_attachments (
                        id TEXT PRIMARY KEY,
                        message_id TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        display_name TEXT, -- For relative paths in directory imports
                        mime_type TEXT NOT NULL,
                        token_count INTEGER NOT NULL,
                        file_size INTEGER NOT NULL,
                        file_hash TEXT NOT NULL, -- For identifying and caching files
                        storage_type TEXT NOT NULL DEFAULT 'database', -- 'database', 'disk', or 'hybrid'
                        content_preview TEXT, -- First 4KB for preview
                        storage_path TEXT, -- Path for disk storage
                        content TEXT, -- File content (will be moved to separate table in future)
                        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                    );
                ''')
            else:
                # Table exists - check columns and add missing ones
                self.logger.info("File attachments table exists, checking for missing columns")

                # Get existing columns
                cursor.execute("PRAGMA table_info(file_attachments)")
                existing_columns = [row['name'] for row in cursor.fetchall()]

                # Define required columns and their definitions
                required_columns = {
                    'display_name': 'TEXT',
                    'file_size': 'INTEGER NOT NULL DEFAULT 0',
                    'file_hash': 'TEXT NOT NULL DEFAULT ""',
                    'storage_type': "TEXT NOT NULL DEFAULT 'database'",
                    'content_preview': 'TEXT',
                    'storage_path': 'TEXT'
                }

                # Add missing columns
                for column, definition in required_columns.items():
                    if column not in existing_columns:
                        self.logger.info(f"Adding missing column: {column}")
                        try:
                            cursor.execute(f"ALTER TABLE file_attachments ADD COLUMN {column} {definition}")
                        except Exception as e:
                            self.logger.error(f"Error adding column {column}: {e}")

                # For existing rows, update file_hash based on content
                if 'file_hash' in required_columns and 'file_hash' not in existing_columns:
                    self.logger.info("Updating file_hash for existing attachments")
                    try:
                        # First check if content column exists
                        if 'content' in existing_columns:
                            cursor.execute("SELECT id, content FROM file_attachments")
                            for row in cursor.fetchall():
                                import hashlib
                                # Generate hash from content
                                content_hash = hashlib.sha256(row['content'].encode('utf-8')).hexdigest()
                                cursor.execute(
                                    "UPDATE file_attachments SET file_hash = ? WHERE id = ?",
                                    (content_hash, row['id'])
                                )
                    except Exception as e:
                        self.logger.error(f"Error updating file_hash values: {e}")

                # Update file_size for existing rows if needed
                if 'file_size' in required_columns and 'file_size' not in existing_columns:
                    self.logger.info("Updating file_size for existing attachments")
                    try:
                        if 'content' in existing_columns:
                            cursor.execute("SELECT id, content FROM file_attachments")
                            for row in cursor.fetchall():
                                content_size = len(row['content'].encode('utf-8'))
                                cursor.execute(
                                    "UPDATE file_attachments SET file_size = ? WHERE id = ?",
                                    (content_size, row['id'])
                                )
                    except Exception as e:
                        self.logger.error(f"Error updating file_size values: {e}")

                # Update content_preview for existing rows
                if 'content_preview' in required_columns and 'content_preview' not in existing_columns:
                    self.logger.info("Updating content_preview for existing attachments")
                    try:
                        if 'content' in existing_columns:
                            cursor.execute("SELECT id, content FROM file_attachments")
                            for row in cursor.fetchall():
                                # First 4KB for preview
                                preview = row['content'][:4096] if row['content'] else ''
                                cursor.execute(
                                    "UPDATE file_attachments SET content_preview = ? WHERE id = ?",
                                    (preview, row['id'])
                                )
                    except Exception as e:
                        self.logger.error(f"Error updating content_preview values: {e}")

            # Create indices if they don't exist
            cursor.executescript('''
                -- Indices for faster lookups
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_parent_id ON messages(parent_id);
                CREATE INDEX IF NOT EXISTS idx_message_metadata_message_id ON message_metadata(message_id);
                CREATE INDEX IF NOT EXISTS idx_file_attachments_message_id ON file_attachments(message_id);
                CREATE INDEX IF NOT EXISTS idx_file_attachments_file_hash ON file_attachments(file_hash);
                CREATE INDEX IF NOT EXISTS idx_reasoning_steps_message_id ON reasoning_steps(message_id);
            ''')

            # Check if the file_contents table needs to be created
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
            if cursor.fetchone() is None:
                cursor.executescript('''
                    -- Separate content table for large files
                    CREATE TABLE IF NOT EXISTS file_contents (
                        file_id TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        FOREIGN KEY (file_id) REFERENCES file_attachments(id) ON DELETE CASCADE
                    );

                    -- Index for faster lookups
                    CREATE INDEX IF NOT EXISTS idx_file_contents_file_id ON file_contents(file_id);
                ''')

            conn.commit()
            conn.close()
            self.logger.info("Database schema initialized/migrated successfully")

        except Exception as e:
            self.logger.error("Error initializing database")
            log_exception(self.logger, e, "Database initialization failed")
            raise

    def get_file_attachment(self, file_id):
        """
        Get a file attachment by ID with efficient content loading

        Args:
            file_id: ID of the attachment

        Returns:
            Dictionary with file information
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # First check if we have the new schema
            cursor.execute("PRAGMA table_info(file_attachments)")
            columns = [row['name'] for row in cursor.fetchall()]
            using_new_schema = all(col in columns for col in ['file_hash', 'storage_type', 'content_preview'])

            if using_new_schema:
                # Get attachment metadata
                cursor.execute(
                    '''
                    SELECT * FROM file_attachments
                    WHERE id = ?
                    ''',
                    (file_id,)
                )
            else:
                # Use original schema
                cursor.execute(
                    '''
                    SELECT id, message_id, file_name, mime_type, content, token_count
                    FROM file_attachments
                    WHERE id = ?
                    ''',
                    (file_id,)
                )

            attachment = cursor.fetchone()

            if not attachment:
                return None

            # Convert to dict
            attachment_dict = dict(attachment)

            # For new schema, load content based on storage type
            if using_new_schema and 'storage_type' in attachment_dict:
                storage_type = attachment_dict['storage_type']

                if storage_type == 'database':
                    # Check if separate content table exists
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
                    if cursor.fetchone():
                        # Get content from separate table
                        cursor.execute(
                            '''
                            SELECT content FROM file_contents
                            WHERE file_id = ?
                            ''',
                            (file_id,)
                        )

                        result = cursor.fetchone()
                        if result:
                            attachment_dict['content'] = result['content']
                        elif 'content' not in attachment_dict or not attachment_dict['content']:
                            attachment_dict['content'] = ''
                    # If content field exists but is null, set to empty string
                    elif 'content' not in attachment_dict or not attachment_dict['content']:
                        attachment_dict['content'] = ''

                elif storage_type == 'disk':
                    # Load from disk
                    storage_path = attachment_dict.get('storage_path')

                    if storage_path and os.path.exists(storage_path):
                        with open(storage_path, 'r', encoding='utf-8') as f:
                            attachment_dict['content'] = f.read()
                    else:
                        attachment_dict['content'] = ''

                elif storage_type == 'hybrid':
                    # Try database first - check both separate table and main table
                    content_found = False

                    # Check separate content table
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
                    if cursor.fetchone():
                        cursor.execute(
                            '''
                            SELECT content FROM file_contents
                            WHERE file_id = ?
                            ''',
                            (file_id,)
                        )

                        result = cursor.fetchone()
                        if result:
                            attachment_dict['content'] = result['content']
                            content_found = True

                    # If not found and content field is in main table
                    if not content_found and 'content' in attachment_dict and attachment_dict['content']:
                        content_found = True

                    # Fall back to disk if needed
                    if not content_found:
                        storage_path = attachment_dict.get('storage_path')

                        if storage_path and os.path.exists(storage_path):
                            with open(storage_path, 'r', encoding='utf-8') as f:
                                attachment_dict['content'] = f.read()
                        else:
                            attachment_dict['content'] = ''

            return attachment_dict

        except Exception as e:
            self.logger.error(f"Error getting file attachment: {e}")
            return None

        finally:
            conn.close()

    def get_node_attachments(self, node_id):
        """Get file attachments for a node with optimized loading"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            attached_files = []

            # Check schema version
            cursor.execute("PRAGMA table_info(file_attachments)")
            columns = [row['name'] for row in cursor.fetchall()]
            using_new_schema = all(col in columns for col in ['file_hash', 'storage_type', 'content_preview'])

            if using_new_schema:
                # Use new schema with preview
                cursor.execute(
                    '''
                    SELECT id, file_name, display_name, mime_type, token_count, 
                           file_size, file_hash, storage_type, content_preview, storage_path
                    FROM file_attachments WHERE message_id = ?
                    ''',
                    (node_id,)
                )
            else:
                # Use original schema
                cursor.execute(
                    '''
                    SELECT id, file_name, mime_type, content, token_count
                    FROM file_attachments WHERE message_id = ?
                    ''',
                    (node_id,)
                )

            for row in cursor.fetchall():
                # Convert row to dict
                attachment = dict(row)

                if using_new_schema:
                    # For normal UI display, we only need the preview
                    if 'content_preview' in attachment and attachment['content_preview']:
                        attachment['content'] = attachment['content_preview']

                attached_files.append(attachment)

            return attached_files

        finally:
            conn.close()

    def load_attachment_content(self, attachment_id):
        """Load full attachment content on demand"""
        return self.get_file_attachment(attachment_id)['content']

    def _execute_with_retry(self, operation_name, callback, retries=5, initial_delay=0.1):
        """
        Execute a database operation with retries on lock errors

        Args:
            operation_name: Name of operation for logging
            callback: Function that performs the actual operation
            retries: Maximum number of retries
            initial_delay: Initial delay before first retry in seconds

        Returns:
            Result of the callback function
        """
        conn = None
        attempt = 0
        delay = initial_delay

        while attempt <= retries:
            try:
                conn = self._get_connection()
                return callback(conn)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < retries:
                    # Log the lock and retry
                    attempt += 1
                    self.logger.warning(f"{operation_name}: Database locked, retry {attempt}/{retries} in {delay:.2f}s")
                    time.sleep(delay)
                    # Exponential backoff with jitter
                    delay = min(delay * 2, 5.0) * (0.5 + random.random())

                    # Close and clear the connection to force a new one
                    if conn:
                        try:
                            conn.close()
                        except:
                            pass
                    self._local.connection = None
                else:
                    # Other error or out of retries, propagate
                    self.logger.error(f"Error in {operation_name}: {str(e)}")
                    raise
            except Exception as e:
                self.logger.error(f"Error in {operation_name}: {str(e)}")
                if conn and conn.in_transaction:
                    conn.rollback()
                raise

    def execute_query(self, query, params=(), fetch_mode='all', retry_count=3):
        """
        Execute a database query with retry logic for database locks.

        Args:
            query: SQL query to execute
            params: Parameters for the query
            fetch_mode: 'all', 'one', or 'none' to determine what to return
            retry_count: Number of retries on database lock

        Returns:
            Query results based on fetch_mode
        """
        attempts = 0
        delay = 0.1
        last_error = None

        while attempts < retry_count:
            conn = None
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute(query, params)

                if fetch_mode == 'all':
                    return cursor.fetchall()
                elif fetch_mode == 'one':
                    return cursor.fetchone()
                else:  # 'none'
                    conn.commit()
                    return True

            except sqlite3.OperationalError as e:
                last_error = e
                if "database is locked" in str(e) and attempts < retry_count - 1:
                    # Retry with exponential backoff
                    attempts += 1
                    import time, random
                    retry_wait = delay * (2 ** attempts) * (0.5 + random.random())
                    time.sleep(retry_wait)
                    self.logger.warning(f"Database locked during query, retrying ({attempts}/{retry_count})...")

                    # Close connection to force a new one next time
                    if conn:
                        try:
                            conn.close()
                        except:
                            pass
                else:
                    # Other SQLite error or out of retries
                    if conn:
                        conn.rollback()
                    raise
            except Exception as e:
                # Other errors
                last_error = e
                if conn:
                    conn.rollback()
                raise

        # If we get here, we've exhausted retries
        raise last_error or sqlite3.OperationalError("Database operation failed after multiple retries")

    def add_file_attachment(self, message_id, file_info, storage_type='auto'):
        """
        Add a file attachment with queued processing to prevent database locks.

        Args:
            message_id: ID of the message to attach the file to
            file_info: Dictionary with file information
            storage_type: 'database', 'disk', 'hybrid', or 'auto'

        Returns:
            ID of the created attachment
        """
        # Create a result queue for this specific file
        result_queue = queue.Queue()

        # Create a placeholder file ID that will be replaced with the actual ID
        file_id = str(QUuid.createUuid())

        # Add the task to the queue - this will be processed by the background thread
        self._file_queue.put((message_id, file_info, storage_type, result_queue))

        try:
            # Wait for the result with a timeout
            success, result = result_queue.get(timeout=30.0)

            if success:
                # Return the actual file ID
                return result
            else:
                # Re-raise the error
                raise Exception(f"Failed to add file attachment: {result}")
        except queue.Empty:
            # Timeout waiting for the result
            raise Exception("Timeout waiting for file attachment to be processed")

    def _process_file_attachment(self, conn, message_id, file_info, storage_type='auto'):
        """
        Process a file attachment with a dedicated connection.
        This is called by the file processor thread.
        """
        cursor = conn.cursor()

        try:
            import hashlib
            from PyQt6.QtCore import QUuid

            file_id = str(QUuid.createUuid())
            file_name = file_info['file_name']
            display_name = file_info.get('display_name', file_name)
            mime_type = file_info.get('mime_type', 'text/plain')
            token_count = file_info.get('token_count', 0)
            file_size = file_info.get('size', 0)
            file_hash = file_info.get('file_hash', '')
            content = file_info.get('content', '')

            # If no file hash provided, calculate one
            if not file_hash and content:
                file_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

            # Determine storage strategy based on content size
            content_too_large = len(content) > 2 * 1024 * 1024  # 2MB threshold

            # Determine storage strategy if auto
            if storage_type == 'auto':
                if content_too_large or file_size > 1024 * 1024:  # > 1MB
                    storage_type = 'disk'
                else:
                    storage_type = 'database'

            # Generate a preview (first 4KB)
            content_preview = content[:4096] if content else ''

            storage_path = None

            # If disk storage, save to disk
            if storage_type in ('disk', 'hybrid'):
                # Import here to avoid circular imports
                from src.utils.file_utils import FileCacheManager

                # Get cache manager
                cache_manager = FileCacheManager()

                # Cache the file
                storage_path = cache_manager.cache_file(content, file_hash)

                # For hybrid, we keep content in the database
                # For disk, we just store the path and free the memory
                if storage_type == 'disk':
                    content = None  # Free memory

            # Check which version of the table we're working with
            cursor.execute("PRAGMA table_info(file_attachments)")
            columns = [row['name'] for row in cursor.fetchall()]

            # Determine if we should use the old or new schema
            using_new_schema = all(col in columns for col in ['file_hash', 'storage_type', 'content_preview'])

            if using_new_schema:
                # Use new optimized schema
                cursor.execute(
                    '''
                    INSERT INTO file_attachments
                    (id, message_id, file_name, display_name, mime_type, token_count,
                    file_size, file_hash, storage_type, content_preview, storage_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (file_id, message_id, file_name, display_name, mime_type, token_count,
                     file_size, file_hash, storage_type, content_preview, storage_path)
                )

                # If database or hybrid storage, save content to separate table
                if storage_type in ('database', 'hybrid') and content:
                    # Check if file_contents table exists
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
                    if cursor.fetchone():
                        # Use the separate content table
                        cursor.execute(
                            '''
                            INSERT INTO file_contents (file_id, content)
                            VALUES (?, ?)
                            ''',
                            (file_id, content)
                        )
                    else:
                        # Fall back to storing in main table
                        cursor.execute(
                            '''
                            UPDATE file_attachments SET content = ?
                            WHERE id = ?
                            ''',
                            (content, file_id)
                        )
            else:
                # Fall back to original schema
                cursor.execute(
                    '''
                    INSERT INTO file_attachments (id, message_id, file_name, mime_type, content, token_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''',
                    (file_id, message_id, file_name, mime_type, content, token_count)
                )

            conn.commit()
            return file_id

        except Exception as e:
            conn.rollback()
            self.logger.error(f"Error adding file attachment: {e}")
            raise

    def _close_connections(self):
        """Close all connections - called during shutdown"""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
                self._local.connection = None
            except:
                pass

    def shutdown(self):
        """Shutdown the database manager - stop background threads and close connections"""
        self.logger.info("Starting database manager shutdown")

        # Stop the file processor
        self._file_processor_running = False

        # Wait for the file processor to finish current tasks
        if self._file_processor_thread and self._file_processor_thread.is_alive():
            self.logger.info("Waiting for file processor to finish...")
            self._file_processor_thread.join(timeout=5.0)

            if self._file_processor_thread.is_alive():
                self.logger.warning("File processor thread did not exit gracefully after timeout")

        # Close all tracked connections
        try:
            with self._connections_lock:
                connection_count = len(self._all_connections)
                self.logger.info(f"Closing {connection_count} tracked database connections")

                for conn in list(self._all_connections):
                    try:
                        conn.close()
                        self._all_connections.remove(conn)
                    except Exception as e:
                        self.logger.warning(f"Error closing connection during shutdown: {str(e)}")

                # Clear the set
                self._all_connections.clear()
        except Exception as e:
            self.logger.error(f"Error closing tracked connections: {str(e)}")

        # Close the thread-local connection as well
        try:
            if hasattr(self._local, 'connection') and self._local.connection is not None:
                try:
                    self._local.connection.close()
                except Exception as e:
                    self.logger.warning(f"Error closing thread-local connection: {str(e)}")
                self._local.connection = None
        except Exception as e:
            self.logger.error(f"Error clearing thread-local connection: {str(e)}")

        self.logger.info("Database manager shutdown complete")


