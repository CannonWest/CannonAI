"""
UI package initialization for CannonAI Gemini Chat

This module handles the web-based user interface implementation.
"""

from .server import create_app, start_server
from .routes import setup_routes
from .websocket import setup_websocket

__all__ = ['create_app', 'start_server', 'setup_routes', 'setup_websocket']
