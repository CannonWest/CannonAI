"""
Gemini Chat UI Module

This is the UI module for the Gemini Chat application.
It provides a web-based interface using FastAPI.
"""

# This makes the start_web_ui function directly importable from 'ui'
from .server import start_web_ui

# Define the version
__version__ = "1.0.0"
