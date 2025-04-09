"""
Application path configuration.
Defines standardized paths for data storage and other resources.
"""

import os
from pathlib import Path

# Define the project root directory (root of the git repository)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_DIR = DATA_DIR / "database"
UPLOADS_DIR = DATA_DIR / "uploads"
LOGS_DIR = DATA_DIR / "logs"

# Ensure important directories exist
def ensure_directories():
    """Create required application directories if they don't exist."""
    directories = [DATA_DIR, DATABASE_DIR, UPLOADS_DIR, LOGS_DIR]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

# Database file paths
DEFAULT_DB_PATH = DATABASE_DIR / "conversations.db"
DEFAULT_DB_URL = f"sqlite:///{DEFAULT_DB_PATH}"

# Run directory creation when the module is imported
ensure_directories()
