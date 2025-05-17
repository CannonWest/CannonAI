"""
Styling utilities for the chat bubble UI components.
"""

import tkinter as tk
from tkinter import ttk

class BubbleStyles:
    """Styling options for message bubbles"""
    
    LIGHT_THEME = {
        "user": {
            "bg": "#007BFF",  # Medium blue
            "fg": "white",
            "padx": 15,
            "pady": 10,
            "anchor": "e",  # Right align
            "justify": "left",
            "width": 80,  # Maximum number of characters per line (approx)
            "corner_radius": 15,
            "margin": (10, 50, 5, 10),  # top, left, bottom, right
        },
        "ai": {
            "bg": "#E9ECEF",  # Light gray
            "fg": "#212529",  # Dark gray text
            "padx": 15,
            "pady": 10,
            "anchor": "w",  # Left align
            "justify": "left",
            "width": 100,  # AI messages can be wider
            "corner_radius": 15,
            "margin": (10, 10, 5, 50),  # top, left, bottom, right
        },
        "system": {
            "fg": "#6C757D",  # Medium gray
            "font": ("Arial", 9, "italic"),
            "justify": "center",
            "pady": 5,
        }
    }
    
    DARK_THEME = {
        "user": {
            "bg": "#0078D7",  # Blue for user messages
            "fg": "white",
            "padx": 10,
            "pady": 6,
            "anchor": "e",  # Right align
            "justify": "left",
            "width": 50,  # Maximum number of characters per line (approx)
            "corner_radius": 15,
            "margin": (4, 30, 4, 10),  # top, left, bottom, right
        },
        "ai": {
            "bg": "#383838",  # Dark gray for AI messages
            "fg": "#90EE90",  # Light green text
            "padx": 10,
            "pady": 6,
            "anchor": "w",  # Left align
            "justify": "left",
            "width": 60,  # AI messages can be wider
            "corner_radius": 15, 
            "margin": (4, 10, 4, 30),  # top, left, bottom, right
        },
        "system": {
            "fg": "#FFD700",  # Gold
            "font": ("Arial", 9, "italic"),
            "justify": "center",
            "pady": 5,
        }
    }
    
    @staticmethod
    def get_style_for_theme(theme_name):
        """Get appropriate bubble style for a given ttkbootstrap theme
        
        Args:
            theme_name: The name of the ttkbootstrap theme
            
        Returns:
            The appropriate bubble style dict
        """
        # Default to dark theme, then check if the theme name suggests a light theme
        style = BubbleStyles.DARK_THEME
        
        light_themes = [
            'litera', 'minty', 'lumen', 'journal', 'pulse', 'sandstone', 
            'flatly', 'morph', 'yeti', 'cosmo', 'simplex', 'cerculean'
        ]
        
        if any(lt in theme_name.lower() for lt in light_themes):
            style = BubbleStyles.LIGHT_THEME
            
        return style
    
    @staticmethod
    def apply_theme_to_bubbles(root, chat_display):
        """Apply appropriate style to bubble chat based on current theme
        
        Args:
            root: The root window
            chat_display: The BubbleChatDisplay instance
        """
        current_theme = root.style.theme.name
        style = BubbleStyles.get_style_for_theme(current_theme)
        
        # Update existing bubbles
        for message in chat_display.messages:
            if hasattr(message, 'message_text') and hasattr(message, 'is_user'):
                # It's a message bubble
                is_user = getattr(message, 'is_user', True)
                bubble_style = style["user"] if is_user else style["ai"]
                
                message.message_text.config(
                    bg=bubble_style["bg"],
                    fg=bubble_style["fg"]
                )
