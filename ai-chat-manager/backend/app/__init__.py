"""
Application initialization package.
This module initializes the application and its components.
"""

import logging
from importlib.metadata import version, PackageNotFoundError

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

# This can be expanded to include other package dependencies as needed
