"""
UI Client for Gemini Chat

This module provides compatibility functions for different UI modes:
1. TTK Bootstrap GUI (legacy)
2. Web-based React UI (new)

It re-exports the necessary functions to maintain compatibility with the main entry point.
"""

import asyncio
import logging
from typing import Optional, Any, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def launch_ui(client, config):
    """
    Launch the ttkbootstrap-based UI (legacy)
    
    This function is maintained for backward compatibility with the original UI.
    It imports the old UI components if available.
    
    Args:
        client: The client instance
        config: The config instance
        
    Returns:
        The result of the UI launch
    """
    try:
        # Import the legacy UI (will raise ImportError if files were deleted)
        from ui import launch_ui as launch_legacy_ui
        return await launch_legacy_ui(client, config)
    except ImportError:
        logger.warning("Legacy UI components not found. If you need the ttkbootstrap UI, please restore the original UI files.")
        logger.info("Consider using the new web-based UI with the --web flag instead.")
        raise ImportError("Legacy UI components not found. Please use the web interface with --web flag instead.")

async def launch_web_ui(host: str = "127.0.0.1", port: int = 8000, static_dir: Optional[str] = None):
    """
    Launch the web-based UI
    
    This function launches the FastAPI server for the web-based UI.
    
    Args:
        host: The host to bind the server to
        port: The port to bind the server to
        static_dir: The directory containing static files for the web UI
        
    Returns:
        The result of the web UI launch
    """
    try:
        # Import the web UI components
        from ui.server import create_app, start_server
        from ui.routes import setup_routes
        from ui.websocket import setup_websocket
        
        # Create the FastAPI app
        app = create_app()
        
        # Set up routes and websocket
        setup_routes(app)
        setup_websocket(app)
        
        # Start the server
        await start_server(app, host=host, port=port, static_dir=static_dir)
        return True
    except ImportError:
        logger.error("Web UI components not found. Make sure the ui directory contains the necessary files.")
        raise ImportError("Web UI components not found. Please install the required dependencies.")
    except Exception as e:
        logger.error(f"Error launching web UI: {e}")
        raise
