"""
Custom message bubble components for chat-like interfaces.
"""

import queue
import tkinter as tk
from tkinter import Frame, Label, Text, END
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from .bubble_styles import BubbleStyles

class MessageBubble(Frame):
    """A chat message bubble for displaying messages in a chat-like interface"""
    
    def __init__(self, parent, message, is_user=True, **kwargs):
        """Initialize a message bubble
        
        Args:
            parent: The parent widget
            message: The message text
            is_user: True if this is a user message, False for AI/other messages
            **kwargs: Additional keyword arguments to pass to Frame constructor
        """
        # Store whether this is a user message for later reference
        self.is_user = is_user
        
        # Get the appropriate style based on the current theme
        root = parent.winfo_toplevel()
        bubble_style = BubbleStyles.DARK_THEME  # Default to dark theme
        
        # Try to get the actual theme if possible
        if hasattr(root, 'style') and hasattr(root.style, 'theme') and hasattr(root.style.theme, 'name'):
            bubble_style = BubbleStyles.get_style_for_theme(root.style.theme.name)
        
        frame_style = bubble_style["user"] if is_user else bubble_style["ai"]
        
        # Calculate optimal width based on parent widget width
        try:
            parent_width = parent.winfo_width()
            # If parent widget hasn't been fully initialized yet
            if parent_width <= 1:
                parent_width = 800  # Default assumption
                
            # Calculate width in characters (roughly)
            # User messages can now span up to 50% of window width
            # AI messages can span up to 65% of window width
            chars_per_pixel = 0.12  # Approximate for standard font
            if is_user:
                max_width = int(parent_width * 0.50 * chars_per_pixel)
                max_width = max(60, max_width)  # At least 60 chars
            else:
                max_width = int(parent_width * 0.65 * chars_per_pixel)
                max_width = max(70, max_width)  # At least 70 chars
                
            # Override the style's width setting
            frame_style["width"] = max_width
        except Exception as e:
            # Fallback to default widths if calculation fails
            print(f"Width calculation error: {e}")
        
        # Create the frame with proper styling
        super().__init__(
            parent,
            **kwargs
        )
        
        # Configure the bubble container
        self.container = ttk.Frame(
            self, 
            bootstyle="secondary" if is_user else "secondary-border"
        )
        
        # Create the message display
        self.message_text = Text(
            self.container,
            wrap="word",
            width=frame_style["width"],
            height=1,  # Start with 1 line, will auto-expand
            font=("Arial", 10),
            bg=frame_style["bg"],
            fg=frame_style["fg"],
            padx=frame_style["padx"],
            pady=frame_style["pady"],
            relief="flat",
            highlightthickness=0,
            borderwidth=0
        )
        
        # Disable horizontal scrollbar completely
        self.message_text.config(xscrollcommand=None)
        
        # Insert the message and configure the message height based on content
        self.message_text.insert("1.0", message)
        self.message_text.configure(state="disabled")
        
        # Apply rounded corners with a custom style
        if is_user:
            # Right side bubble (user)
            self.message_text.configure(
                bd=0, 
                highlightthickness=0, 
                highlightbackground=frame_style["bg"]
            )
        else:
            # Left side bubble (AI)
            self.message_text.configure(
                bd=0, 
                highlightthickness=0,
                highlightbackground=frame_style["bg"]
            )
        
        # Calculate required height based on text content
        # This ensures the bubble is always tall enough for all text
        self.message_text.update_idletasks()  # Ensure layout is updated
        try:
            # Try to get the display line count which accounts for word wrapping
            content_height = self.message_text.count("1.0", END, "displaylines")[0]
            # No extra buffer needed - use exact height
            self.message_text.configure(height=content_height)
        except Exception:
            # Fallback: Simple line count if displaylines fails
            text_content = self.message_text.get("1.0", END)
            num_lines = text_content.count('\n') + 1
            self.message_text.configure(height=num_lines)
        
        # Pack the message
        self.message_text.pack(fill="both", expand=True)
        self.container.pack(
            side=RIGHT if is_user else LEFT, 
            anchor=frame_style["anchor"], 
            padx=(frame_style["margin"][1], frame_style["margin"][3]), 
            pady=(frame_style["margin"][0], frame_style["margin"][2])
        )

class BubbleChatDisplay(ttk.Frame):
    """A chat display that uses message bubbles instead of plain text"""
    
    def __init__(self, parent, **kwargs):
        """Initialize the bubble chat display
        
        Args:
            parent: The parent widget
            **kwargs: Additional keyword arguments to pass to Frame constructor
        """
        super().__init__(parent, **kwargs)
        
        # Create a canvas with scrollbar for the messages
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Set canvas background to match parent
        self.canvas.configure(bg=self.winfo_toplevel().cget('bg'))
        
        # Create a frame to contain all the messages
        self.messages_frame = ttk.Frame(self.canvas)
        self.messages_frame_id = self.canvas.create_window(
            (0, 0), 
            window=self.messages_frame, 
            anchor="nw",
            width=self.canvas.winfo_width()
        )
        
        # Pack the widgets
        self.scrollbar.pack(side=RIGHT, fill=Y)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        
        # Bind events to handle scrolling and resizing
        self.messages_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # List to keep track of all messages
        self.messages = []
        
        # Stream state
        self.streaming = False
        self.current_stream_bubble = None
    
    def _on_frame_configure(self, event):
        """Update the scroll region when the frame changes size"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
    def _on_canvas_configure(self, event):
        """When the canvas resizes, resize the message frame to match the width"""
        self.canvas.itemconfig(self.messages_frame_id, width=event.width)
    
    def _on_mousewheel(self, event):
        """Handle mousewheel scrolling"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def add_message(self, message, is_user=True):
        """Add a new message to the chat
        
        Args:
            message: The message text
            is_user: True if this is a user message, False for AI messages
        """
        # Create a new message bubble
        bubble = MessageBubble(
            self.messages_frame,
            message,
            is_user=is_user
        )
        bubble.pack(fill=X, padx=5, pady=2)
        
        # Add to the list of messages
        self.messages.append(bubble)
        
        # Update the scroll region
        self.messages_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        # Scroll to the bottom
        self.canvas.yview_moveto(1.0)
        
        return bubble
    
    def add_system_message(self, message):
        """Add a system message to the chat
        
        Args:
            message: The system message text
        """
        # Get the appropriate style for system messages
        root = self.winfo_toplevel()
        style = BubbleStyles.DARK_THEME  # Default to dark theme
        
        # Try to get the actual theme if possible
        if hasattr(root, 'style') and hasattr(root.style, 'theme') and hasattr(root.style.theme, 'name'):
            style = BubbleStyles.get_style_for_theme(root.style.theme.name)
        
        system_style = style["system"]
        
        # Create a system message label
        label = ttk.Label(
            self.messages_frame,
            text=f"--- {message} ---",
            font=system_style["font"],
            foreground=system_style["fg"],
            justify=system_style["justify"]
        )
        label.pack(fill=X, padx=5, pady=system_style["pady"])
        
        # Update the scroll region
        self.messages_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
        # Scroll to the bottom
        self.canvas.yview_moveto(1.0)
    
    def clear(self):
        """Clear all messages"""
        for widget in self.messages_frame.winfo_children():
            widget.destroy()
        
        self.messages = []
        self.current_stream_bubble = None
        self.streaming = False
    
    def see_end(self):
        """Scroll to the bottom of the chat"""
        self.canvas.yview_moveto(1.0)
    
    def start_streaming(self):
        """Start a new streaming session for AI response"""
        self.streaming = True
        
        # Create a new bubble for the AI response
        self.current_stream_bubble = self.add_message("", is_user=False)
        
        # Configure the text widget for receiving stream
        self.current_stream_bubble.message_text.configure(state="normal")
        
        return self.current_stream_bubble
    
    def add_stream_chunk(self, chunk):
        """Add a chunk of text to the current streaming bubble
        
        Args:
            chunk: The text chunk to add
        """
        if not self.streaming or not self.current_stream_bubble:
            return
            
        # Add the chunk to the bubble
        self.current_stream_bubble.message_text.configure(state="normal")
        self.current_stream_bubble.message_text.insert(END, chunk)
        
        # Get the accurate display line count (accounts for word wrapping)
        text_widget = self.current_stream_bubble.message_text
        text_widget.update_idletasks()  # Force layout update
        
        try:
            # Try to get the display line count which accounts for word wrapping
            content_height = text_widget.count("1.0", END, "displaylines")[0]
            # No extra buffer needed - exact height
            text_widget.configure(height=content_height)
        except Exception:
            # Fallback to basic line count if displaylines fails
            text_content = text_widget.get("1.0", END)
            num_lines = text_content.count('\n') + 1
            text_widget.configure(height=num_lines)
        
        # Keep scroll at the bottom
        self.see_end()
        
        # Update the message frame layout
        self.messages_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def stop_streaming(self):
        """Stop the current streaming session"""
        if not self.streaming or not self.current_stream_bubble:
            return
            
        # Disable editing of the current bubble
        self.current_stream_bubble.message_text.configure(state="disabled")
        
        # Reset streaming state
        self.streaming = False
        self.current_stream_bubble = None
    
    def update_theme(self):
        """Update the theme for all message bubbles"""
        root = self.winfo_toplevel()
        BubbleStyles.apply_theme_to_bubbles(root, self)


class BubbleStreamHandler:
    """Handles streaming of AI responses in the chat bubble UI"""
    
    def __init__(self, chat_display, update_interval_ms=50):
        """Initialize the stream handler
        
        Args:
            chat_display: The BubbleChatDisplay widget
            update_interval_ms: How often to check the queue for new chunks
        """
        self.chat_display = chat_display
        self.response_queue = queue.Queue()
        self.update_interval_ms = update_interval_ms
        self.streaming = False
        self.current_response = ""
    
    def start_streaming(self):
        """Start a new streaming session"""
        print("Starting streaming session...")
        self.streaming = True
        self.current_response = ""
        self.chat_display.start_streaming()
        
    def add_chunk(self, chunk):
        """Add a chunk of text to the stream
        
        Args:
            chunk: The text chunk to add
        """
        # Debug output
        if not chunk:
            print(f"Warning: Empty chunk received")
        
        self.response_queue.put(chunk)
        
    def stop_streaming(self):
        """Stop the streaming session"""
        print(f"Stopping streaming session (collected {len(self.current_response)} chars)")
        self.streaming = False
        self.flush_queue()
        self.chat_display.stop_streaming()
        
    def flush_queue(self):
        """Process all chunks in the queue"""
        if not self.response_queue.empty():
            chunks = []
            try:
                while not self.response_queue.empty():
                    chunks.append(self.response_queue.get_nowait())
            except queue.Empty:
                pass
            
            if chunks:
                text = "".join(chunks)
                self.add_to_display(text)
    
    def add_to_display(self, text):
        """Add text to the chat display
        
        Args:
            text: The text to add
        """
        if not text:
            return
            
        self.chat_display.add_stream_chunk(text)
        self.current_response += text

    def check_queue(self):
        """Process any available chunks from the queue"""
        if self.streaming:
            self.flush_queue()
        # Reschedule this check
        self.chat_display.after(self.update_interval_ms, self.check_queue)
        
    def get_response(self):
        """Get the complete streamed response
        
        Returns:
            The complete response as a string
        """
        return self.current_response
