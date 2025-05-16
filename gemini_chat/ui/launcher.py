"""
UI Launcher for Gemini Chat

This module handles launching the UI application and connecting it
with the backend client.
"""

import asyncio
from typing import Any, Dict, Optional

from .app import GeminiChatApp

async def start_app_main_thread(app):
    """Start the application on the main thread
    
    Args:
        app: The GeminiChatApp instance
    """
    # We need to return to the main thread to initialize UI
    # This is done by returning control to the event loop
    await asyncio.sleep(0.1)
    
    # Now we can set up the UI in the main thread
    app.setup_ui()
    
    # Start the initialization in the background
    app.start_initialization()
    
    # Start the mainloop
    app.root.mainloop()


async def launch_ui(client, config):
    """Launch the UI application
    
    Args:
        client: The AsyncGeminiClient instance
        config: The Config instance
    """
    print("Launching UI application from launcher module...")
    
    # Create the application instance
    app = GeminiChatApp(client, config)
    
    # Schedule the app to start on the main thread
    # All tkinter operations must run in the main thread
    asyncio.create_task(start_app_main_thread(app))
    
    # Wait for the app to be fully initialized
    while not hasattr(app, 'root') or not app.root.winfo_exists():
        await asyncio.sleep(0.1)
    
    # Keep the asyncio event loop running until the UI is closed
    # This prevents the launcher from returning immediately
    try:
        while app.root.winfo_exists():
            await asyncio.sleep(0.5)
    except Exception as e:
        print(f"Error monitoring UI: {e}")
    finally:
        print("UI closed, exiting launcher")
    
    return True
