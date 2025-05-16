"""
Handles streaming of AI responses in the UI
"""

import queue
from tkinter import END

class StreamHandler:
    """Handles streaming of AI responses in the UI"""
    
    def __init__(self, chat_display, update_interval_ms=50):
        """Initialize the stream handler
        
        Args:
            chat_display: The ScrolledText widget to display chat messages
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
            
        self.chat_display.config(state="normal")
        self.chat_display.insert(END, text, "ai_text")
        self.chat_display.config(state="disabled")
        self.chat_display.see(END)
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
