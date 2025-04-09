"""
Database connection and initialization.
"""

import os
import sqlite3
from typing import Optional

from src.utils.constants import DATABASE_PATH
from src.utils import logging_utils

logger = logging_utils.get_logger(__name__)

def get_db_connection() -> sqlite3.Connection:
    """
    Get a connection to the SQLite database.
    Returns:
        sqlite3.Connection: Database connection object
    """
    logger.debug(f"Opening database connection to {DATABASE_PATH}")
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    
    return conn