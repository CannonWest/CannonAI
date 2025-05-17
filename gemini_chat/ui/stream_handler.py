"""
Handles streaming of AI responses in the UI that uses message bubbles
"""

import queue
from tkinter import END
from .components.message_bubbles import BubbleStreamHandler

# This class is kept for backward compatibility
# New code should use BubbleStreamHandler from components.message_bubbles
class StreamHandler(BubbleStreamHandler):
    """Handles streaming of AI responses in the UI
    
    This is now a wrapper around BubbleStreamHandler for backwards compatibility
    """
    
    def __init__(self, chat_display, update_interval_ms=50):
        """Initialize the stream handler
        
        Args:
            chat_display: The chat display widget
            update_interval_ms: How often to check the queue for new chunks
        """
        super().__init__(chat_display, update_interval_ms)
