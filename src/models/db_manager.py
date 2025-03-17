# src/models/db_manager.py
"""
Improved database management utilities with simplified connection handling
and robust transaction support.
"""

import os
import queue
import sqlite3
import threading
import time
from typing import Optional, Callable, Any, Dict, List, Tuple
from datetime import datetime

from PyQt6.QtCore import QUuid

from src.utils import DATABASE_DIR, DATABASE_FILE
from src.utils.logging_utils import get_logger, log_exception

# Get a logger for this module
logger = get_logger(__name__)


class DatabaseManager:
    """
    Handles SQLite database connections and operations with robust transaction support.
    Uses a simplified connection approach with proper cleanup and error handling.
    """

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

            # Main lock for database operations
            self._db_lock = threading.RLock()

            # Connection management with simpler approach
            self._connection = None
            self._connection_count = 0
            self._last_connection_time = 0

            # File processor for attachments
            self._file_queue = queue.Queue()
            self._file_processor_running = False
            self._file_processor_thread = None

            # Initialize database schema
            self._ensure_database_schema()

            # Start the file processor thread
            self._start_file_processor()

            self.logger.info(f"Database manager initialized with database at {self.db_path}")

    def _ensure_database_schema(self):
        """Initialize database schema with better error handling"""
        try:
            # Use a dedicated connection for schema initialization
            conn = sqlite3.connect(self.db_path, timeout=60.0)
            cursor = conn.cursor()

            # Enable foreign keys
            cursor.execute("PRAGMA foreign_keys = ON")

            # Create tables with schema version tracking
            cursor.executescript('''
                -- Schema version tracking
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

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

                -- File contents table for large files
                CREATE TABLE IF NOT EXISTS file_contents (
                    file_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    FOREIGN KEY (file_id) REFERENCES file_attachments(id) ON DELETE CASCADE
                );

                -- Indices for faster lookups
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_parent_id ON messages(parent_id);
                CREATE INDEX IF NOT EXISTS idx_message_metadata_message_id ON message_metadata(message_id);
                CREATE INDEX IF NOT EXISTS idx_file_attachments_message_id ON file_attachments(message_id);
                CREATE INDEX IF NOT EXISTS idx_file_attachments_file_hash ON file_attachments(file_hash);
                CREATE INDEX IF NOT EXISTS idx_reasoning_steps_message_id ON reasoning_steps(message_id);
                CREATE INDEX IF NOT EXISTS idx_file_contents_file_id ON file_contents(file_id);
            ''')

            # Insert schema version if not exists
            cursor.execute(
                "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (1, ?)",
                (datetime.now().isoformat(),)
            )

            conn.commit()
            conn.close()

            self.logger.info("Database schema initialized successfully")
        except Exception as e:
            self.logger.error(f"Error initializing database schema: {str(e)}")
            # Log but don't propagate the error to allow for recovery later

    def get_connection(self):
        """
        Get a database connection with simplified management.
        Always returns a valid connection or raises an exception.
        """
        with self._db_lock:
            # Check if we have a valid connection
            if self._connection and self._is_connection_valid(self._connection):
                self._connection_count += 1
                return self._connection

            # Close existing connection if it exists but is invalid
            if self._connection:
                try:
                    self._connection.close()
                except:
                    pass
                self._connection = None

            # Create a new connection
            try:
                conn = sqlite3.connect(self.db_path, timeout=60.0)
                conn.row_factory = sqlite3.Row

                # Enable WAL mode and foreign keys
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=30000")  # 30-second timeout

                # Verify the connection works
                cursor.execute("SELECT 1").fetchone()

                # Store the connection
                self._connection = conn
                self._connection_count = 1
                self._last_connection_time = time.time()

                return conn
            except Exception as e:
                self.logger.error(f"Error creating database connection: {str(e)}")
                raise

    def _is_connection_valid(self, conn):
        """Test if a connection is valid"""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return cursor.fetchone() is not None
        except:
            return False

    def release_connection(self, conn):
        """
        Release a connection. With this implementation, we don't actually
        close the connection, just decrement the usage count.
        """
        with self._db_lock:
            if conn is self._connection:
                self._connection_count -= 1

                # Only close if connection is old and not in use
                if self._connection_count <= 0:
                    # Check if connection is old (idle for more than 5 minutes)
                    idle_time = time.time() - self._last_connection_time
                    if idle_time > 300:  # 5 minutes
                        try:
                            conn.close()
                            self._connection = None
                            self.logger.debug("Closed idle database connection")
                        except:
                            pass

    def execute_transaction(self, callback, retry_count=3):
        """
        Execute a callback within a transaction with retry logic.

        Args:
            callback: Function that takes a database connection and performs operations
            retry_count: Number of retries on database lock errors

        Returns:
            The result of the callback function
        """
        conn = None
        attempts = 0
        delay = 0.1  # Initial delay in seconds

        while attempts < retry_count:
            try:
                conn = self.get_connection()

                # Start transaction
                try:
                    result = callback(conn)
                    conn.commit()
                    return result
                except sqlite3.OperationalError as e:
                    # Handle database lock errors
                    if "database is locked" in str(e) and attempts < retry_count - 1:
                        conn.rollback()
                        attempts += 1
                        self.logger.warning(f"Database locked, retry {attempts}/{retry_count}")
                        time.sleep(delay * (2 ** attempts))  # Exponential backoff
                    else:
                        conn.rollback()
                        raise
                except Exception as e:
                    conn.rollback()
                    raise
            except Exception as e:
                self.logger.error(f"Transaction error: {str(e)}")
                raise
            finally:
                if conn:
                    self.release_connection(conn)

        raise sqlite3.OperationalError(f"Database transaction failed after {retry_count} retries")

    def execute_query(self, query, params=(), fetch_mode='all'):
        """
        Execute a simple query with proper transaction handling.

        Args:
            query: SQL query to execute
            params: Parameters for the query
            fetch_mode: 'all', 'one', or 'none' for result fetching

        Returns:
            Query results based on fetch_mode
        """

        def _execute(conn):
            cursor = conn.cursor()
            cursor.execute(query, params)

            if fetch_mode == 'all':
                return cursor.fetchall()
            elif fetch_mode == 'one':
                return cursor.fetchone()
            else:  # 'none'
                return None

        return self.execute_transaction(_execute)

    def get_node_children(self, node_id):
        """Get children of a node with transaction safety"""
        try:
            def _get_children(conn):
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM messages WHERE parent_id = ?',
                    (node_id,)
                )
                return cursor.fetchall()

            rows = self.execute_transaction(_get_children)
            children = []

            for row in rows:
                try:
                    child = self._create_node_from_db_row(row)
                    if child:
                        children.append(child)
                except Exception as e:
                    self.logger.warning(f"Error creating child node: {str(e)}")

            return children
        except Exception as e:
            self.logger.error(f"Error getting children for node {node_id}: {str(e)}")
            return []

    def get_path_to_root(self, node_id):
        """Get path from node to root with transaction safety"""
        if not node_id:
            self.logger.error("Attempted to get path to root with None node_id")
            return []

        try:
            def _get_path(conn):
                cursor = conn.cursor()
                path = []
                current_id = node_id

                while current_id:
                    cursor.execute(
                        'SELECT * FROM messages WHERE id = ?',
                        (current_id,)
                    )
                    message = cursor.fetchone()

                    if not message:
                        break

                    # Create node object
                    node = self._create_node_from_db_row(message)
                    if node:
                        path.insert(0, node)

                    # Move to parent
                    current_id = message['parent_id']

                return path

            return self.execute_transaction(_get_path)
        except Exception as e:
            self.logger.error(f"Error getting path to root for node {node_id}: {str(e)}")
            return []

    def _create_node_from_db_row(self, row):
        """Create a node object from a database row"""
        from src.models.db_conversation import DBMessageNode

        try:
            # Get metadata
            model_info, parameters, token_usage, reasoning_steps = self._get_node_metadata(row['id'])

            # Get file attachments
            attached_files = self._get_node_attachments(row['id'])

            # Create the node
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
                response_id=row['response_id']
            )

            # Set database manager for lazy loading
            node._db_manager = self

            # Add reasoning steps if available
            if reasoning_steps:
                node._reasoning_steps = reasoning_steps

            return node
        except Exception as e:
            self.logger.error(f"Error creating node from row: {str(e)}")
            return None

    def _get_node_metadata(self, node_id):
        """Get metadata for a node with transaction safety"""
        if not node_id:
            return {}, {}, {}, []

        try:
            def _get_metadata(conn):
                cursor = conn.cursor()
                model_info = {}
                parameters = {}
                token_usage = {}
                reasoning_steps = []

                cursor.execute(
                    'SELECT metadata_type, metadata_value FROM message_metadata WHERE message_id = ?',
                    (node_id,)
                )

                import json
                for row in cursor.fetchall():
                    try:
                        metadata_type = row['metadata_type']
                        metadata_value = json.loads(row['metadata_value'])

                        if metadata_type == 'reasoning_steps':
                            reasoning_steps = metadata_value
                        elif metadata_type.startswith('model_info.'):
                            key = metadata_type.replace('model_info.', '')
                            model_info[key] = metadata_value
                        elif metadata_type.startswith('parameters.'):
                            key = metadata_type.replace('parameters.', '')
                            parameters[key] = metadata_value
                        elif metadata_type.startswith('token_usage.'):
                            key = metadata_type.replace('token_usage.', '')
                            token_usage[key] = metadata_value
                    except Exception as e:
                        self.logger.error(f"Error processing metadata: {str(e)}")

                return model_info, parameters, token_usage, reasoning_steps

            return self.execute_transaction(_get_metadata)
        except Exception as e:
            self.logger.error(f"Error getting metadata for node {node_id}: {str(e)}")
            return {}, {}, {}, []

    def _get_node_attachments(self, node_id):
        """Get file attachments with transaction safety"""
        try:
            def _get_attachments(conn):
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM file_attachments WHERE message_id = ?',
                    (node_id,)
                )

                attachments = []
                for row in cursor.fetchall():
                    attachments.append({
                        'file_name': row['file_name'],
                        'mime_type': row['mime_type'],
                        'content': row['content'],
                        'token_count': row['token_count']
                    })

                return attachments

            return self.execute_transaction(_get_attachments)
        except Exception as e:
            self.logger.error(f"Error getting attachments for node {node_id}: {str(e)}")
            return []

    def get_message(self, message_id):
        """Get a message by ID with transaction safety"""
        try:
            def _get_message(conn):
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM messages WHERE id = ?',
                    (message_id,)
                )
                return cursor.fetchone()

            row = self.execute_transaction(_get_message)
            if not row:
                return None

            return self._create_node_from_db_row(row)
        except Exception as e:
            self.logger.error(f"Error getting message {message_id}: {str(e)}")
            return None

    def add_file_attachment(self, message_id, file_info, storage_type='auto'):
        """Queue a file attachment for processing"""
        # Create a result queue
        result_queue = queue.Queue()

        # Create placeholder file ID
        file_id = str(QUuid.createUuid())

        # Add to processing queue
        self._file_queue.put((message_id, file_info, storage_type, result_queue))

        try:
            # Wait for result with timeout
            success, result = result_queue.get(timeout=30.0)

            if success:
                return result
            else:
                raise Exception(f"Failed to add file attachment: {result}")
        except queue.Empty:
            raise Exception("Timeout waiting for file attachment to be processed")

    def _start_file_processor(self):
        """Start the background thread for processing file attachments"""
        if self._file_processor_running:
            return

        self._file_processor_running = True

        def process_file_queue():
            self.logger.info("File attachment processor thread started")

            while self._file_processor_running:
                try:
                    # Get next task with timeout
                    try:
                        task = self._file_queue.get(timeout=5.0)
                    except queue.Empty:
                        continue

                    try:
                        message_id, file_info, storage_type, result_queue = task

                        # Process file attachment
                        file_id = self._process_file_attachment(message_id, file_info, storage_type)

                        # Return result
                        if result_queue:
                            result_queue.put((True, file_id))
                    except Exception as e:
                        self.logger.error(f"Error processing file attachment: {str(e)}")
                        if result_queue:
                            result_queue.put((False, str(e)))
                    finally:
                        self._file_queue.task_done()
                except Exception as e:
                    self.logger.error(f"Error in file processor thread: {str(e)}")
                    time.sleep(0.1)

        # Start processor thread
        self._file_processor_thread = threading.Thread(
            target=process_file_queue,
            name="FileAttachmentProcessor",
            daemon=True
        )
        self._file_processor_thread.start()

    def _process_file_attachment(self, message_id, file_info, storage_type='auto'):
        """Process a file attachment with its own transaction"""
        try:
            def _process_file(conn):
                import hashlib

                cursor = conn.cursor()
                file_id = str(QUuid.createUuid())
                file_name = file_info['file_name']
                display_name = file_info.get('display_name', file_name)
                mime_type = file_info.get('mime_type', 'text/plain')
                token_count = file_info.get('token_count', 0)
                file_size = file_info.get('size', 0)
                content = file_info.get('content', '')

                # Calculate file hash if not provided
                file_hash = file_info.get('file_hash', '')
                if not file_hash and content:
                    file_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

                # Determine storage strategy
                content_too_large = len(content) > 2 * 1024 * 1024  # 2MB

                if storage_type == 'auto':
                    if content_too_large or file_size > 1024 * 1024:  # > 1MB
                        storage_type = 'disk'
                    else:
                        storage_type = 'database'

                # Generate preview (first 4KB)
                content_preview = content[:4096] if content else ''

                storage_path = None

                # If disk storage, save to disk
                if storage_type in ('disk', 'hybrid'):
                    from src.utils.file_utils import FileCacheManager

                    # Get cache manager
                    cache_manager = FileCacheManager()

                    # Cache the file
                    storage_path = cache_manager.cache_file(content, file_hash)

                    # Free memory for disk-only storage
                    if storage_type == 'disk':
                        content = None

                # Insert into file_attachments
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

                # Store content in separate table if needed
                if storage_type in ('database', 'hybrid') and content:
                    # Check if file_contents table exists
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_contents'")
                    if cursor.fetchone():
                        cursor.execute(
                            '''
                            INSERT INTO file_contents (file_id, content)
                            VALUES (?, ?)
                            ''',
                            (file_id, content)
                        )
                    else:
                        # Fall back to main table
                        cursor.execute(
                            '''
                            UPDATE file_attachments SET content = ?
                            WHERE id = ?
                            ''',
                            (content, file_id)
                        )

                return file_id

            return self.execute_transaction(_process_file)
        except Exception as e:
            self.logger.error(f"Error processing file attachment: {str(e)}")
            raise

    def verify_database_health(self):
        """Perform a comprehensive health check on the database"""
        self.logger.info("Performing database health check")
        issues_found = 0

        try:
            # Check if database file exists
            import os
            if not os.path.exists(self.db_path):
                self.logger.error(f"Database file not found at {self.db_path}")
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
                issues_found += 1

            # Try a test connection
            conn = None
            try:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.row_factory = sqlite3.Row

                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

                if result and result[0] == 1:
                    self.logger.info("Database connection test passed")
                else:
                    self.logger.warning("Database connection test returned unexpected result")
                    issues_found += 1

                # Check schema
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

            except Exception as e:
                self.logger.error(f"Failed to establish test connection: {str(e)}")
                connection_ok = False
                issues_found += 1
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

            # Report results
            if issues_found <= 0:
                self.logger.info("Database health check completed successfully - no issues found")
                return True
            else:
                self.logger.warning(f"Database health check completed with {issues_found} unresolved issues")
                return False

        except Exception as e:
            self.logger.error(f"Database health check failed with error: {str(e)}")
            return False

    def debug_print_conversations(self):
        """Print all conversations for debugging"""
        try:
            def _get_conversations(conn):
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM conversations')
                conversations = cursor.fetchall()

                results = []
                for conv in conversations:
                    # Also count messages
                    cursor.execute('SELECT COUNT(*) FROM messages WHERE conversation_id = ?', (conv['id'],))
                    message_count = cursor.fetchone()[0]

                    results.append((conv, message_count))

                return results

            conversation_data = self.execute_transaction(_get_conversations)

            # Print results
            print(f"===== DEBUG: Found {len(conversation_data)} conversations in database =====")
            for conv, message_count in conversation_data:
                print(f"ID: {conv['id']}, Name: {conv['name']}, Modified: {conv['modified_at']}")
                print(f"  Messages: {message_count}")
            print("=====================================================")

        except Exception as e:
            print(f"DEBUG: Error querying conversations: {str(e)}")
            self.logger.error(f"Error in debug_print_conversations: {str(e)}")

    def shutdown(self):
        """Clean shutdown procedure"""
        self.logger.info("Starting database manager shutdown")

        # Stop the file processor
        self._file_processor_running = False

        # Wait for processor thread to finish
        if self._file_processor_thread and self._file_processor_thread.is_alive():
            self.logger.info("Waiting for file processor to finish...")
            self._file_processor_thread.join(timeout=5.0)

        # Close and clean up the connection
        with self._db_lock:
            if self._connection:
                try:
                    self._connection.close()
                    self._connection = None
                    self.logger.info("Database connection closed")
                except Exception as e:
                    self.logger.error(f"Error closing database connection: {str(e)}")

        self.logger.info("Database manager shutdown complete")