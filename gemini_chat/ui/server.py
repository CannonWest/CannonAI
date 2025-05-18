"""
FastAPI server implementation for Gemini Chat web interface.

This module provides the main server functionality for the web-based UI.
"""

import asyncio
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    """Create and configure the FastAPI application.
    
    Returns:
        The configured FastAPI application
    """
    logger.info("Creating FastAPI application")
    
    # Create FastAPI app
    app = FastAPI(
        title="Gemini Chat API",
        description="API for the Gemini Chat web interface",
        version="1.0.0",
    )
    
    # Configure CORS to allow requests from the React frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, restrict this to your frontend URL
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Application state to store client instances
    app.state.clients = {}
    app.state.active_conversations = {}
    
    # Return the configured app (routes will be added separately)
    return app

def mount_static_files(app: FastAPI, static_dir: Path) -> None:
    """Mount static files for the React frontend.
    
    Args:
        app: The FastAPI application
        static_dir: Path to the static files directory
    """
    logger.info(f"Mounting static files from {static_dir}")
    
    # Ensure directory exists
    if not static_dir.exists():
        logger.warning(f"Static directory {static_dir} does not exist!")
        return
    
    # Mount static files
    app.mount("/static", StaticFiles(directory=str(static_dir / "static")), name="static")
    
    # Serve index.html for all other routes
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # API routes are handled by other endpoints
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        
        # For all other routes, serve the React app
        return FileResponse(str(static_dir / "index.html"))

async def start_server(
    app: FastAPI, 
    host: str = "127.0.0.1", 
    port: int = 8000,
    static_dir: Optional[Path] = None
) -> None:
    """Start the FastAPI server.
    
    Args:
        app: The FastAPI application
        host: Host address to bind to
        port: Port to bind to
        static_dir: Path to static files (if None, API-only mode)
    """
    logger.info(f"Starting Gemini Chat server on {host}:{port}")
    
    # Mount static files if directory is provided
    if static_dir:
        mount_static_files(app, static_dir)
    
    # Start the server
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    except Exception as e:
        logger.error(f"Error starting server: {e}")
        raise
    finally:
        logger.info("Server shutdown complete")

def run_server(
    host: str = "127.0.0.1", 
    port: int = 8000,
    static_dir: Optional[str] = None
) -> None:
    """Run the server (blocking call for use from command line).
    
    Args:
        host: Host address to bind to
        port: Port to bind to
        static_dir: Path to static files (if None, API-only mode)
    """
    logger.info("Starting Gemini Chat server in blocking mode")
    
    # Create the app
    app = create_app()
    
    # Convert static_dir to Path if provided
    static_path = Path(static_dir) if static_dir else None
    
    # Set up routes and websocket
    from .routes import setup_routes
    from .websocket import setup_websocket
    
    setup_routes(app)
    setup_websocket(app)
    
    # Start the server
    if static_path:
        # Mount static files if directory is provided
        mount_static_files(app, static_path)
    
    # Use uvicorn directly for blocking operation
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )

if __name__ == "__main__":
    # Allow running the server directly
    import argparse
    
    parser = argparse.ArgumentParser(description="Run the Gemini Chat server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--static-dir", help="Path to static files")
    
    args = parser.parse_args()
    
    run_server(
        host=args.host,
        port=args.port,
        static_dir=args.static_dir,
    )
