"""
Application initialization package.
This module initializes the application and its components.
"""

import logging
import os
import sys
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

# Add backend directory to Python path
BACKEND_DIR = Path(__file__).parent.parent.absolute()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Set up logging
logger = logging.getLogger(__name__)

# Check for required packages and provide helpful messages
try:
    # Check if pydantic-settings is installed
    pydantic_settings_version = version("pydantic-settings")
    logger.info(f"Found pydantic-settings version {pydantic_settings_version}")
except PackageNotFoundError:
    logger.warning(
        "pydantic-settings package not found. "
        "Please install it with: pip install pydantic-settings"
    )

# Import key modules to make them available directly from app package
try:
    from app import api
    from app import core
    from app import models
    from app import utils
    
    # This helps with direct imports like: from app.core.config import settings
    __all__ = ['api', 'core', 'models', 'utils']
    
except ImportError as e:
    logger.error(f"Error importing app modules: {e}")
