"""
Handles redirection of stdout for logging in the UI
"""

import sys
from tkinter import END

class StdoutRedirector:
    """Redirects stdout to a tkinter text widget for logging"""
    
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = ""
        self.prev_stdout = sys.stdout
        
    def write(self, string):
        """Write to both the original stdout and the text widget"""
        self.buffer += string
        self.prev_stdout.write(string)
        
        # If we have a complete line, add it to the log
        if '\n' in self.buffer:
            lines = self.buffer.split('\n')
            for line in lines[:-1]:  # Process all complete lines
                try:
                    # Check if it's a ScrolledText (has a .text attribute)
                    if hasattr(self.text_widget, 'text'):
                        text = self.text_widget.text
                        text.configure(state="normal")
                    # Fall back to direct configuration if it's a regular Text widget
                    elif hasattr(self.text_widget, 'configure'):
                        self.text_widget.configure(state="normal")
                    elif hasattr(self.text_widget, 'config'):
                        self.text_widget.config(state="normal")
                    
                    # Apply color tags based on the message content
                    if "[ERROR]" in line or "Error:" in line or "Failed" in line or "error" in line.lower():
                        self.text_widget.insert(END, line + '\n', "error")
                    elif "Warning:" in line or "[WARNING]" in line or "warning" in line.lower():
                        self.text_widget.insert(END, line + '\n', "warning")
                    elif "Success" in line or "[INFO]" in line or "info" in line.lower():
                        self.text_widget.insert(END, line + '\n', "info")
                    else:
                        self.text_widget.insert(END, line + '\n', "default")
                        
                    # Check if it's a ScrolledText (has a .text attribute)
                    if hasattr(self.text_widget, 'text'):
                        text = self.text_widget.text
                        text.configure(state="disabled")
                    # Fall back to direct configuration if it's a regular Text widget
                    elif hasattr(self.text_widget, 'configure'):
                        self.text_widget.configure(state="disabled")
                    elif hasattr(self.text_widget, 'config'):
                        self.text_widget.config(state="disabled")
                    
                    self.text_widget.see(END)
                except Exception as e:
                    # Print to the original stdout to avoid recursion
                    self.prev_stdout.write(f"Error updating log display: {e}\n")
            
            # Keep any partial line for next time
            self.buffer = lines[-1]
    
    def flush(self):
        """Flush the buffer"""
        # If there's any remaining content in buffer, write it
        if self.buffer:
            try:
                # Check if it's a ScrolledText (has a .text attribute)
                if hasattr(self.text_widget, 'text'):
                    text = self.text_widget.text
                    text.configure(state="normal")
                # Fall back to direct configuration if it's a regular Text widget
                elif hasattr(self.text_widget, 'configure'):
                    self.text_widget.configure(state="normal")
                elif hasattr(self.text_widget, 'config'):
                    self.text_widget.config(state="normal")
                
                self.text_widget.insert(END, self.buffer, "default")
                
                # Check if it's a ScrolledText (has a .text attribute)
                if hasattr(self.text_widget, 'text'):
                    text = self.text_widget.text
                    text.configure(state="disabled")
                # Fall back to direct configuration if it's a regular Text widget
                elif hasattr(self.text_widget, 'configure'):
                    self.text_widget.configure(state="disabled")
                elif hasattr(self.text_widget, 'config'):
                    self.text_widget.config(state="disabled")
                    
                self.text_widget.see(END)
                self.buffer = ""
            except Exception as e:
                # Print to the original stdout to avoid recursion
                self.prev_stdout.write(f"Error flushing log display: {e}\n")
            
    def __enter__(self):
        """Context manager entry"""
        sys.stdout = self
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        sys.stdout = self.prev_stdout
