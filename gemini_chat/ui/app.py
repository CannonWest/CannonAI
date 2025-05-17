"""
Main application class for the Gemini Chat UI
"""

import os
import sys
import tkinter as tk
import asyncio
import json
import threading
from pathlib import Path
from tkinter import StringVar, BooleanVar, END
from typing import Dict, List, Optional, Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.dialogs import Messagebox, Querybox

from base_client import Colors
from .stdout_redirect import StdoutRedirector
from .stream_handler import StreamHandler
from .async_helper import AsyncHelper

class GeminiChatApp:
    """Main UI application for the Gemini Chat"""
    
    def __init__(self, client, config):
        """Initialize the application
        
        Args:
            client: The AsyncGeminiClient instance
            config: The Config instance
        """
        print("Initializing GeminiChatApp...")
        
        # Store references to client and config
        self.client = client
        self.config = config
        
        # Create the root window first
        print("Creating root window...")
        self.root = ttk.Window(
            title="CannonAI - Gemini Chat",
            themename="superhero",  # Dark theme by default
            size=(1200, 800),  # Increased height to show all elements
            position=(100, 100),
            minsize=(800, 650)  # Increased minimum height as well
        )
        
        # Create Tkinter variables
        print("Creating UI variables...")
        self.convo_var = StringVar(self.root, value="No conversation selected")
        self.status_var = StringVar(self.root, value="Initializing...")
        self.model_var = StringVar(self.root, value="Loading...")
        self.stream_var = BooleanVar(self.root, value=False)
        
        # UI components (will be set later)
        self.chat_display = None
        self.message_input = None
        self.convo_listbox = None
        self.log_text = None
        
        # Setup AsyncHelper for managing asyncio tasks
        print("Setting up AsyncHelper...")
        self.async_helper = AsyncHelper()
        self.async_helper.start_background_loop()
        
        # The stream handler will be created after UI widgets
        self.stream_handler = None
        self.redirector = None
        
        print("GeminiChatApp initialized")
        
    async def initialize(self):
        """Initialize the client and UI asynchronously"""
        print("Initializing client...")
        
        # Try to initialize the client, but don't fail if API key is missing
        client_initialized = await self.client.initialize_client()
        if not client_initialized:
            print("Notice: Gemini client not initialized. Set API key in Settings to use AI features.")
            # Schedule a non-blocking notification to be shown from the main thread
            self.root.after(1000, lambda: self.add_system_message(
                "Please set your API key in Settings to use AI features"
            ))
            # Still continue with the app initialization
        else:
            print("Client initialized successfully")
            
        print("Setting up UI...")
        
        # Set initial status
        if client_initialized:
            self.status_var.set("Ready")
            self.model_var.set(self.client.model or "Unknown model")
            self.stream_var.set(self.client.use_streaming)
        else:
            self.status_var.set("API key required")
            self.model_var.set("No API key set")
        
        # First, update the conversation list to load existing conversations
        print("Checking for existing conversations...")
        await self.update_conversation_list()
        
        # If no active conversation, create one - but only if we have conversations in the list
        if client_initialized and not self.client.conversation_id:
            # Check if we have any existing conversations
            if self.convo_listbox.get_children():
                # We have existing conversations, load the first one
                first_convo = self.convo_listbox.get_children()[0]
                print(f"Loading first conversation: {first_convo}")
                await self.load_conversation(first_convo)
            else:
                # No existing conversations, create a new one
                print("No existing conversations found, creating one...")
                await self.on_new_conversation()
        elif self.client.conversation_id:
            # Update the display with existing conversation
            self.convo_var.set(f"Current Conversation")
            await self.display_conversation_history()
        
        print("Initialization complete")
        return True
    
    def setup_ui(self):
        """Setup the UI components"""
        print("Setting up UI components...")
        
        # Setup menu
        self.setup_menu()
        
        # Main layout with paned window
        main_pane = ttk.PanedWindow(self.root, orient=HORIZONTAL)
        main_pane.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        
        # Left pane (conversations)
        left_frame = ttk.Frame(main_pane, width=250)
        main_pane.add(left_frame, weight=1)
        
        # Right pane (chat)
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=3)
        
        # Setup components
        self.setup_left_pane(left_frame)
        self.setup_right_pane(right_frame)
        self.setup_status_bar()
        
        # Create stream handler now that chat_display exists
        print("Creating stream handler...")
        self.stream_handler = StreamHandler(self.chat_display)
        self.stream_handler.check_queue()
        
        # Make sure the log_text is fully initialized first
        self.root.update_idletasks()
        
        # Redirect stdout to log
        print("Setting up stdout redirector...")
        try:
            self.redirector = StdoutRedirector(self.log_text)
            sys.stdout = self.redirector
            print("Stdout redirector set up successfully")
        except Exception as e:
            print(f"Error setting up stdout redirector: {e}")
            # Don't redirect if there was an error
        
        print("UI setup complete")
    
    def setup_menu(self):
        """Setup the application menu"""
        menu_bar = ttk.Menu(self.root)
        self.root.config(menu=menu_bar)
        
        # File menu
        file_menu = ttk.Menu(menu_bar, tearoff=NO)
        menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Conversation", command=self.on_new_conversation_click)
        file_menu.add_command(label="Save Conversation", command=self.on_save_conversation_click)
        file_menu.add_separator()
        file_menu.add_command(label="Settings", command=self.on_settings_click)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_exit_click)
        
        # Edit menu
        edit_menu = ttk.Menu(menu_bar, tearoff=NO)
        menu_bar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Clear Chat", command=self.on_clear_chat_click)
        edit_menu.add_command(label="Copy Selected Text", command=self.on_copy_text_click)
        
        # Model menu
        model_menu = ttk.Menu(menu_bar, tearoff=NO)
        menu_bar.add_cascade(label="Model", menu=model_menu)
        model_menu.add_command(label="Select Model", command=self.on_select_model_click)
        model_menu.add_command(label="Parameters", command=self.on_params_click)
        model_menu.add_separator()
        model_menu.add_checkbutton(label="Streaming Mode", 
                                  variable=self.stream_var, 
                                  command=self.on_toggle_streaming)
        
        # View menu
        view_menu = ttk.Menu(menu_bar, tearoff=NO)
        menu_bar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Show Log Window", command=self.on_show_log_click)
        
        # Help menu
        help_menu = ttk.Menu(menu_bar, tearoff=NO)
        menu_bar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.on_about_click)
        help_menu.add_command(label="Version Info", command=self.on_version_click)
    
    def setup_left_pane(self, parent):
        """Setup the left pane with conversation controls
        
        Args:
            parent: The parent frame
        """
        # New conversation button
        new_btn = ttk.Button(
            parent, 
            text="New Conversation", 
            bootstyle="success",
            command=self.on_new_conversation_click
        )
        new_btn.pack(fill=X, padx=5, pady=5)
        
        # Conversations list in a labelframe
        convo_frame = ttk.Labelframe(parent, text="Conversations", padding=5)
        convo_frame.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        
        # Treeview for conversations with scrollbar
        self.convo_listbox = ttk.Treeview(
            convo_frame, 
            show="tree", 
            selectmode="browse", 
            height=20
        )
        
        scrollbar = ttk.Scrollbar(
            convo_frame, 
            orient=VERTICAL, 
            command=self.convo_listbox.yview
        )
        
        # Link scrollbar to treeview
        self.convo_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Pack widgets
        self.convo_listbox.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # Bind selection event
        self.convo_listbox.bind("<<TreeviewSelect>>", self.on_conversation_select)
        
        # Bind right-click for context menu
        self.convo_listbox.bind("<Button-3>", self.show_conversation_context_menu)
        
        # Options frame at the bottom
        options_frame = ttk.Labelframe(parent, text="Options", padding=5)
        options_frame.pack(fill=X, padx=5, pady=5, side=BOTTOM)
        
        # Streaming mode toggle
        stream_check = ttk.Checkbutton(
            options_frame,
            text="Streaming Mode",
            variable=self.stream_var,
            bootstyle="success-round-toggle",
            command=self.on_toggle_streaming
        )
        stream_check.pack(fill=X, pady=2)
        
        # Model selection button
        model_btn = ttk.Button(
            options_frame,
            text="Select Model",
            bootstyle="info-outline",
            command=self.on_select_model_click
        )
        model_btn.pack(fill=X, pady=2)
        
        # Parameters button
        params_btn = ttk.Button(
            options_frame,
            text="Parameters",
            bootstyle="info-outline",
            command=self.on_params_click
        )
        params_btn.pack(fill=X, pady=2)
    
    def setup_right_pane(self, parent):
        """Setup the right pane with chat and log
        
        Args:
            parent: The parent frame
        """
        # Create notebook with chat and log tabs
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=BOTH, expand=YES)
        
        # Chat tab
        chat_tab = ttk.Frame(notebook)
        notebook.add(chat_tab, text="Chat")
        
        # Log tab
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="Log")
        
        # Setup chat display
        chat_frame = ttk.Frame(chat_tab)
        chat_frame.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        
        # Current conversation label
        ttk.Label(
            chat_frame, 
            textvariable=self.convo_var,
            font="-size 12 -weight bold"
        ).pack(fill=X, pady=(0, 5))
        
        # Chat display
        self.chat_display = ScrolledText(
            chat_frame,
            wrap="word",
            height=20,
            autohide=True,
            state="disabled"
        )
        self.chat_display.pack(fill=BOTH, expand=YES, pady=(0, 5))
        
        # Configure message tags
        self.setup_chat_tags()
        
        # Message input area
        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill=X, pady=5)
        
        self.message_input = ScrolledText(
            input_frame,
            height=3,
            width=60,
            wrap="word",
            autohide=True
        )
        self.message_input.pack(side=LEFT, fill=X, expand=YES, padx=(0, 5))
        self.message_input.focus()
        
        # Bind Enter key to send
        self.message_input.bind("<Return>", self.on_enter_pressed)
        # Allow Shift+Enter for newline
        self.message_input.bind("<Shift-Return>", lambda e: "break")
        
        # Send button
        send_btn = ttk.Button(
            input_frame,
            text="Send",
            command=self.on_send_message_click,
            bootstyle="success"
        )
        send_btn.pack(side=RIGHT, padx=5)
        
        # Setup log text widget
        log_frame = ttk.Frame(log_tab)
        log_frame.pack(fill=BOTH, expand=YES, padx=5, pady=5)
        
        self.log_text = ScrolledText(
            log_frame,
            wrap="word",
            height=20,
            autohide=True,
            state="disabled"
        )
        self.log_text.pack(fill=BOTH, expand=YES)
        
        # Configure log tags
        self.setup_log_tags()
    
    def setup_chat_tags(self):
        """Setup tags for the chat display"""
        # For user messages
        self.chat_display.tag_configure(
            "user_text",
            foreground="white",
            font=("-size 10 -weight bold"),
            spacing1=10,
            spacing3=5,
            lmargin1=10,
            lmargin2=25
        )
        
        # For AI responses
        self.chat_display.tag_configure(
            "ai_text",
            foreground="#90EE90",  # Light green
            font=("-size 10"),
            spacing1=10,
            spacing3=5,
            lmargin1=10,
            lmargin2=25
        )
        
        # For message labels
        self.chat_display.tag_configure(
            "user_label",
            foreground="#ADD8E6",  # Light blue
            font=("-size 10 -weight bold"),
            spacing1=10
        )
        
        self.chat_display.tag_configure(
            "ai_label",
            foreground="#90EE90",  # Light green
            font=("-size 10 -weight bold"),
            spacing1=10
        )
        
        # For system messages
        self.chat_display.tag_configure(
            "system_text",
            foreground="#FFD700",  # Gold
            font=("-size 9 -slant italic"),
            justify="center",
            spacing1=5,
            spacing3=5
        )
    
    def setup_log_tags(self):
        """Setup tags for the log display"""
        self.log_text.tag_configure(
            "error",
            foreground="#FF6347"  # Tomato red
        )
        
        self.log_text.tag_configure(
            "warning",
            foreground="#FFD700"  # Gold
        )
        
        self.log_text.tag_configure(
            "info",
            foreground="#90EE90"  # Light green
        )
        
        self.log_text.tag_configure(
            "default",
            foreground="white"
        )
    
    def setup_status_bar(self):
        """Setup the status bar at the bottom of the window"""
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=X, side=BOTTOM)
        
        # Status indicator
        ttk.Label(
            status_frame,
            text="Status:",
            padding=(5, 2)
        ).pack(side=LEFT)
        
        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            padding=(5, 2)
        ).pack(side=LEFT)
        
        # Separator
        ttk.Separator(
            status_frame,
            orient=VERTICAL
        ).pack(side=LEFT, fill=Y, padx=5, pady=2)
        
        # Model indicator
        ttk.Label(
            status_frame,
            text="Model:",
            padding=(5, 2)
        ).pack(side=LEFT)
        
        ttk.Label(
            status_frame,
            textvariable=self.model_var,
            padding=(5, 2)
        ).pack(side=LEFT)
        
        # Streaming indicator
        is_streaming = self.stream_var.get()
        
        ttk.Label(
            status_frame,
            text="•",
            foreground="green" if is_streaming else "red",
            font="-size 14",
            padding=(5, 0)
        ).pack(side=RIGHT)
        
        ttk.Label(
            status_frame,
            text="Streaming:",
            padding=(5, 2)
        ).pack(side=RIGHT)
    
    def update_streaming_indicator(self):
        """Update the streaming indicator in the status bar"""
        is_streaming = self.stream_var.get()
        
        # Find the indicator in the status bar
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Frame) and widget.winfo_y() > self.root.winfo_height() - 50:
                # We found the status bar
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Label) and child.cget("text") == "•":
                        # This is our indicator
                        color = "green" if is_streaming else "red"
                        child.configure(foreground=color)
                        break
    
    # ============= UI Event Handlers =============
    
    def on_new_conversation_click(self):
        """Handle click on New Conversation button"""
        print("New conversation button clicked")
        self.async_helper.run_coroutine(self.on_new_conversation())
    
    def on_save_conversation_click(self):
        """Handle click on Save Conversation menu item"""
        print("Save conversation menu item clicked")
        self.async_helper.run_coroutine(self.on_save_conversation())
    
    def on_settings_click(self):
        """Handle click on Settings menu item"""
        print("Settings menu item clicked")
        self.create_settings_dialog()
    
    def on_exit_click(self):
        """Handle click on Exit menu item"""
        print("Exit menu item clicked")
        self.async_helper.run_coroutine(self.on_exit())
    
    def on_clear_chat_click(self):
        """Handle click on Clear Chat menu item"""
        print("Clear chat menu item clicked")
        text_widget = self.chat_display.text
        text_widget.configure(state="normal")
        self.chat_display.delete("1.0", END)
        text_widget.configure(state="disabled")
    
    def on_copy_text_click(self):
        """Handle click on Copy Selected Text menu item"""
        print("Copy text menu item clicked")
        try:
            selected_text = self.chat_display.get("sel.first", "sel.last")
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
            print("Text copied to clipboard")
        except tk.TclError:
            print("No text selected")
    
    def on_select_model_click(self):
        """Handle click on Select Model menu item"""
        print("Select model menu item clicked")
        self.async_helper.run_coroutine(self.on_select_model())
    
    def on_params_click(self):
        """Handle click on Parameters menu item"""
        print("Parameters menu item clicked")
        self.async_helper.run_coroutine(self.on_customize_params())
    
    def on_toggle_streaming(self):
        """Handle toggling of streaming mode"""
        is_streaming = self.stream_var.get()
        print(f"Toggling streaming mode to: {is_streaming}")
        self.async_helper.run_coroutine(self.client.toggle_streaming())
        self.update_streaming_indicator()
    
    def on_show_log_click(self):
        """Handle click on Show Log Window menu item"""
        print("Show log menu item clicked")
        # Switch to log tab
        notebook = self.chat_display.master.master.master
        notebook.select(1)  # Log tab is at index 1
    
    def on_about_click(self):
        """Handle click on About menu item"""
        print("About menu item clicked")
        Messagebox.show_info(
            "CannonAI - Gemini Chat\n\n"
            "A powerful interface for Google's Gemini AI models\n"
            "with both CLI and GUI capabilities.\n\n"
            "See README.md for more information.",
            "About CannonAI"
        )
    
    def on_version_click(self):
        """Handle click on Version Info menu item"""
        print("Version info menu item clicked")
        version = self.client.get_version() if hasattr(self.client, 'get_version') else "Unknown"
        Messagebox.show_info(
            f"Gemini Chat v{version}\n\n"
            "Using ttkbootstrap for UI",
            "Version Information"
        )
    
    def on_conversation_select(self, event):
        """Handle selection of a conversation from the list"""
        print("Conversation selected from list")
        selected = self.convo_listbox.selection()
        if selected:
            convo_id = selected[0]
            print(f"Selected conversation ID: {convo_id}")
            self.async_helper.run_coroutine(self.load_conversation(convo_id))
            
    def show_conversation_context_menu(self, event):
        """Show context menu for right-clicked conversation"""
        # Identify the item that was right-clicked
        item = self.convo_listbox.identify_row(event.y)
        if not item:
            print("No item right-clicked")
            return
            
        print(f"Right-clicked on conversation: {item}")
        
        # Select the item first
        self.convo_listbox.selection_set(item)
        
        # Create context menu
        context_menu = ttk.Menu(self.root, tearoff=0)
        context_menu.add_command(label="Rename", command=lambda: self.rename_conversation(item))
        context_menu.add_command(label="Delete", command=lambda: self.delete_conversation(item))
        
        # Display context menu at the event location
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            # Make sure to release the grab or the app will hang
            context_menu.grab_release()
    
    def rename_conversation(self, conversation_id):
        """Rename a conversation
        
        Args:
            conversation_id: The conversation ID to rename
        """
        print(f"Renaming conversation: {conversation_id}")
        
        # Create an asyncio Future to wait for the result
        import asyncio
        future = asyncio.Future()
        
        # Function to show dialog on main thread
        def show_rename_dialog():
            # Get the current title
            current_title = ""
            for convo in self.convo_listbox.item(conversation_id, "text").split(" ("):
                current_title = convo
                break
                
            # Show dialog to get new title
            new_title = Querybox.get_string(
                "Enter new title for the conversation:",
                "Rename Conversation",
                initialvalue=current_title,
                parent=self.root
            )
            
            # Set future result
            future.set_result(new_title)
        
        # Show dialog on main thread
        self.root.after(0, show_rename_dialog)
        
        # Handle the result asynchronously
        def handle_rename_result(fut):
            try:
                new_title = fut.result()
                if new_title:
                    # Run the actual rename coroutine
                    rename_future = self.async_helper.run_coroutine(
                        self.do_rename_conversation(conversation_id, new_title)
                    )
                    rename_future.add_done_callback(lambda _: print(f"Rename completed for {conversation_id}"))
            except Exception as e:
                print(f"Error in rename dialog: {e}")
                self.add_system_message(f"Error renaming conversation: {str(e)}")
        
        # Add callback
        future.add_done_callback(handle_rename_result)
    
    async def do_rename_conversation(self, conversation_id, new_title):
        """Perform the actual conversation rename
        
        Args:
            conversation_id: The conversation ID to rename
            new_title: The new title for the conversation
        """
        print(f"Performing rename of {conversation_id} to '{new_title}'")
        
        try:
            # Get current conversation data
            conversations = await self.client.list_conversations()
            target_conv = None
            target_path = None
            
            for conv in conversations:
                if conv.get("conversation_id") == conversation_id:
                    target_conv = conv
                    target_path = conv.get("path")
                    break
            
            if not target_conv or not target_path:
                print(f"Error: Could not find conversation {conversation_id}")
                self.add_system_message("Error: Conversation not found")
                return False
            
            # Read the conversation file
            with open(target_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Update the title in metadata
            history = data.get("history", [])
            for i, item in enumerate(history):
                if item.get("type") == "metadata":
                    if "content" in item and isinstance(item["content"], dict):
                        item["content"]["title"] = new_title
                        break
            
            # Save updated data
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            # Update UI
            message_count = target_conv.get("message_count", 0)
            self.convo_listbox.item(
                conversation_id, 
                text=f"{new_title} ({message_count} msgs)"
            )
            
            # If this is the current conversation, update title
            if self.client.conversation_id == conversation_id:
                self.convo_var.set(f"Current Conversation: {new_title}")
            
            print(f"Successfully renamed conversation to '{new_title}'")
            self.add_system_message(f"Conversation renamed to '{new_title}'")
            return True
            
        except Exception as e:
            print(f"Error renaming conversation: {e}")
            import traceback
            traceback.print_exc()
            self.add_system_message(f"Error renaming conversation: {str(e)}")
            return False
    
    def delete_conversation(self, conversation_id):
        """Delete a conversation
        
        Args:
            conversation_id: The conversation ID to delete
        """
        print(f"Deleting conversation: {conversation_id}")
        
        # Get the conversation title
        convo_text = self.convo_listbox.item(conversation_id, "text")
        title = convo_text.split(" (")[0] if " (" in convo_text else convo_text
        
        # Confirm deletion
        if not Messagebox.show_question(
            f"Are you sure you want to delete the conversation '{title}'?",
            "Confirm Deletion",
            buttons=['Yes:success', 'No:secondary'],
            parent=self.root
        ):
            print("Deletion cancelled")
            return
        
        # Run the delete coroutine
        delete_future = self.async_helper.run_coroutine(
            self.do_delete_conversation(conversation_id)
        )
        delete_future.add_done_callback(lambda _: print(f"Delete completed for {conversation_id}"))
    
    async def do_delete_conversation(self, conversation_id):
        """Perform the actual conversation deletion
        
        Args:
            conversation_id: The conversation ID to delete
        """
        print(f"Performing deletion of {conversation_id}")
        
        try:
            # Get conversation path
            conversations = await self.client.list_conversations()
            target_path = None
            
            for conv in conversations:
                if conv.get("conversation_id") == conversation_id:
                    target_path = conv.get("path")
                    break
            
            if not target_path:
                print(f"Error: Could not find conversation {conversation_id}")
                self.add_system_message("Error: Conversation not found")
                return False
            
            # Check if this is the current conversation
            is_current = self.client.conversation_id == conversation_id
            
            # Delete the file
            import os
            os.remove(target_path)
            print(f"Deleted file: {target_path}")
            
            # Remove from UI
            self.convo_listbox.delete(conversation_id)
            
            # If current conversation was deleted, create a new one or load another
            if is_current:
                print("Current conversation was deleted")
                # Check if there are other conversations
                if self.convo_listbox.get_children():
                    # Load the first available conversation
                    first_convo = self.convo_listbox.get_children()[0]
                    await self.load_conversation(first_convo)
                else:
                    # Create a new conversation
                    await self.on_new_conversation()
            
            # Show message
            self.add_system_message("Conversation deleted successfully")
            return True
            
        except Exception as e:
            print(f"Error deleting conversation: {e}")
            import traceback
            traceback.print_exc()
            self.add_system_message(f"Error deleting conversation: {str(e)}")
            return False
    
    def on_send_message_click(self):
        """Handle click on Send button"""
        print("Send button clicked")
        message = self.message_input.get("1.0", END).strip()
        if message:
            print(f"Sending message: {message[:50]}{'...' if len(message) > 50 else ''}")
            self.message_input.delete("1.0", END)
            self.async_helper.run_coroutine(self.send_message(message))
            return True
        else:
            print("Empty message, not sending")
            return False
    
    def on_enter_pressed(self, event):
        """Handle Enter key in message input"""
        if self.on_send_message_click():
            # Prevent default behavior (newline)
            return "break"
        return None
    
    # ============= Async Methods =============
    
    async def on_new_conversation(self):
        """Start a new conversation"""
        print("Creating new conversation...")
        
        # Check if API key is set
        if not self.client.api_key:
            self.add_system_message("Please set your API key in Settings before creating a new conversation")
            self.root.after(0, self.on_settings_click)
            return
        
        # Save current conversation first if it exists
        if self.client.conversation_id:
            print(f"Saving current conversation: {self.client.conversation_id}")
            await self.client.save_conversation()
            
        # We need to get a title from the user via a dialog
        # But we can't call Tkinter dialogs from async functions, so we need to use a callback pattern
        # Create an asyncio Future to wait for the result
        import asyncio
        title_future = asyncio.Future()
        
        # Function to be called on the main thread
        def show_title_dialog():
            try:
                print("Showing conversation title dialog on main thread")
                default_title = f"Conversation_{self.client.get_timestamp()}"
                
                # Create the dialog on the main thread
                title = Querybox.get_string(
                    "Enter a title for this conversation:",
                    "New Conversation",
                    initialvalue=default_title,
                    parent=self.root
                )
                
                # Set result in the future
                title_future.set_result(title if title else default_title)
                print(f"Dialog result: {title if title else 'Using default title'}")
            except Exception as e:
                print(f"Error in title dialog: {e}")
                title_future.set_exception(e)
        
        # Schedule the dialog on the main thread
        self.root.after(0, show_title_dialog)
        
        # Wait for the dialog result
        try:
            print("Waiting for dialog result...")
            title = await title_future
            print(f"Received title: {title}")
            
            # Check if user cancelled
            if title is None:
                print("User cancelled new conversation")
                return
                
            # Update status
            self.status_var.set("Creating new conversation...")
            print(f"Creating new conversation with title: {title}")
            
            # Create new conversation
            self.client.conversation_id = self.client.generate_conversation_id()
            self.client.conversation_history = []
            
            # Create initial metadata
            metadata = self.client.create_metadata_structure(title, self.client.model, self.client.params)
            
            # Add to conversation history
            self.client.conversation_history.append(metadata)
            
            # Clear chat display
            text_widget = self.chat_display.text
            text_widget.configure(state="normal")
            self.chat_display.delete("1.0", END)
            text_widget.configure(state="disabled")
            
            # Update conversation title
            self.convo_var.set(f"Current Conversation: {title}")
            
            # Save the new conversation
            await self.client.save_conversation()
            print("New conversation saved successfully")
            
            # Force directory creation before updating list
            self.client.ensure_directories(self.client.conversations_dir)
            print(f"Ensured conversation directory exists at: {self.client.conversations_dir}")
            
            # Update conversation list
            await self.update_conversation_list()
            
            # Update status
            self.status_var.set("Ready")
            
            # Add system message to chat
            self.add_system_message(f"Started new conversation: {title}")
            print("New conversation created successfully")
        except Exception as e:
            print(f"Error creating new conversation: {e}")
            import traceback
            traceback.print_exc()
            self.add_system_message(f"Error creating new conversation: {str(e)}")
            self.status_var.set("Error creating conversation")
            return False
            
        return True
    
    async def on_save_conversation(self):
        """Save the current conversation"""
        print("Saving conversation...")
        self.status_var.set("Saving conversation...")
        await self.client.save_conversation()
        self.status_var.set("Conversation saved")
        print("Conversation saved successfully")
    
    async def on_exit(self):
        """Save and exit the application"""
        print("Exiting application...")
        self.status_var.set("Saving before exit...")
        await self.client.save_conversation()
        print("Conversation saved, calling quit")
        self.root.after(100, self.root.quit)
    
    async def update_conversation_list(self):
        """Update the conversation list"""
        print("Updating conversation list...")
        print(f"Looking for conversations in: {self.client.conversations_dir}")
        
        # Get list of conversations
        conversations = await self.client.list_conversations()
        
        if not conversations:
            print("No conversations found")
            return
            
        print(f"Found {len(conversations)} conversations")
        
        # Clear current list
        for item in self.convo_listbox.get_children():
            self.convo_listbox.delete(item)
        
        # Add conversations to list
        for convo in conversations:
            # Extract conversation info
            convo_id = convo.get("conversation_id", "")
            title = convo.get("title", "Untitled")
            message_count = convo.get("message_count", 0)
            
            # Debug
            print(f"Adding conversation: {title} ({convo_id}, {message_count} msgs)")
            
            # Insert into treeview
            self.convo_listbox.insert(
                "", 
                END, 
                iid=convo_id,
                text=f"{title} ({message_count} msgs)"
            )
            
            # Select current conversation
            if convo_id == self.client.conversation_id:
                self.convo_listbox.selection_set(convo_id)
                self.convo_listbox.see(convo_id)
                self.convo_var.set(f"Current Conversation: {title}")
    
    async def load_conversation(self, conversation_id):
        """Load a conversation by ID
        
        Args:
            conversation_id: The conversation ID to load
        """
        print(f"Loading conversation: {conversation_id}")
        self.status_var.set("Loading conversation...")
        
        # Save current conversation first
        if self.client.conversation_id:
            await self.client.save_conversation()
        
        # Get all conversations
        conversations = await self.client.list_conversations()
        
        # Find selected conversation
        selected_convo = None
        selected_path = None
        for convo in conversations:
            if convo.get("conversation_id") == conversation_id:
                selected_convo = convo
                selected_path = convo.get("path")
                break
        
        if not selected_convo or not selected_path:
            print(f"Error: Conversation not found: {conversation_id}")
            self.status_var.set("Error: Conversation not found")
            return
        
        print(f"Found conversation at: {selected_path}")
        
        # Load conversation data
        try:
            with open(selected_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Update client state
            self.client.conversation_id = data.get("conversation_id")
            self.client.conversation_history = data.get("history", [])
            
            # Update model and params from metadata
            title = "Untitled"
            for item in self.client.conversation_history:
                if item.get("type") == "metadata":
                    metadata = item.get("content", {})
                    self.client.model = metadata.get("model", self.client.model)
                    if "params" in metadata:
                        self.client.params = metadata["params"]
                    title = metadata.get("title", "Untitled")
                    self.convo_var.set(f"Current Conversation: {title}")
                    break
            
            # Update UI
            self.model_var.set(self.client.model)
            self.stream_var.set(self.client.use_streaming)
            self.update_streaming_indicator()
            
            # Display conversation history
            await self.display_conversation_history()
            
            self.status_var.set(f"Loaded conversation: {title}")
            print(f"Conversation loaded successfully: {title}")
            
        except Exception as e:
            print(f"Error loading conversation: {e}")
            self.status_var.set(f"Error loading conversation: {str(e)}")
            self.add_system_message(f"Error loading conversation: {str(e)}")
    
    async def display_conversation_history(self):
        """Display the current conversation history"""
        print("Displaying conversation history...")
        if not self.client.conversation_history:
            print("No conversation history to display")
            return
        
        # Clear chat display
        text_widget = self.chat_display.text
        text_widget.configure(state="normal")
        self.chat_display.delete("1.0", END)
        
        # Find title from metadata
        title = "Untitled"
        for item in self.client.conversation_history:
            if item.get("type") == "metadata":
                metadata = item.get("content", {})
                title = metadata.get("title", "Untitled")
                break
        
        print(f"Displaying conversation: {title}")
        self.add_system_message(f"Loaded conversation: {title}")
        
        # Add messages to display
        for item in self.client.conversation_history:
            if item.get("type") == "message":
                content = item.get("content", {})
                role = content.get("role", "")
                text = content.get("text", "")
                
                if role == "user":
                    self.add_user_message_to_display(text)
                elif role == "ai":
                    self.add_ai_message_to_display(text)
        
        text_widget.configure(state="disabled")
        self.chat_display.see(END)
        print("Conversation history displayed")
    
    async def send_message(self, message):
        """Send a message to the AI and display response
        
        Args:
            message: The message to send
        """
        if not message:
            print("Empty message, not sending")
            return
            
        print(f"Processing message: {message[:50]}{'...' if len(message) > 50 else ''}")
        
        # Check if API key is set
        if not self.client.api_key:
            self.add_system_message("Please set your API key in Settings before sending messages")
            self.root.after(0, self.on_settings_click)
            return
            
        # Check if we have an active conversation
        if not self.client.conversation_id:
            print("No active conversation, creating one...")
            await self.on_new_conversation()
            # If we still don't have a conversation ID, the user probably cancelled
            if not self.client.conversation_id:
                return
        
        # Display user message
        self.add_user_message_to_display(message)
        
        # Update status
        self.status_var.set("Waiting for AI response...")
        
        # Add user message to history
        user_message = self.client.create_message_structure("user", message, self.client.model, self.client.params)
        self.client.conversation_history.append(user_message)
        
        try:
            # Check if streaming mode is enabled
            if self.client.use_streaming:
                print("Using streaming mode for response")
                await self.send_streaming_message(message)
            else:
                # Non-streaming mode
                print("Using non-streaming mode for response")
                response = await self.client.send_message(message)
                if response:
                    print(f"Response received: {response[:50]}{'...' if len(response) > 50 else ''}")
                    self.add_ai_message_to_display(response)
                else:
                    print("No response received")
                    self.add_system_message("Error: No response received from AI")
        except Exception as e:
            print(f"Error sending message: {e}")
            self.add_system_message(f"Error: {str(e)}")
        
        # Update status
        self.status_var.set("Ready")
    
    async def send_streaming_message(self, message):
        """Send a message and stream the response
        
        Args:
            message: The message to send
        """
        print("Sending streaming message...")
        # Create a chat session
        try:
            # Add the AI label first to the text widget (not the ScrolledText container)
            self.chat_display.text.configure(state="normal")
            self.chat_display.insert(END, "AI: ", "ai_label")
            self.chat_display.text.configure(state="disabled")
            
            # Start stream handler
            self.stream_handler.start_streaming()
            
            # Build chat history for the API
            chat_history = self.client.build_chat_history(self.client.conversation_history)
            
            # Add the new message
            from google.genai import types
            chat_history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
            
            # Configure generation parameters
            config = types.GenerateContentConfig(
                temperature=self.client.params["temperature"],
                max_output_tokens=self.client.params["max_output_tokens"],
                top_p=self.client.params["top_p"],
                top_k=self.client.params["top_k"]
            )
            
            print("Getting stream generator...")
            # Get stream generator
            stream_generator = await self.client.client.aio.models.generate_content_stream(
                model=self.client.model,
                contents=chat_history,
                config=config
            )
            
            # Process the stream
            print("Processing stream...")
            response_text = ""
            async for chunk in stream_generator:
                if hasattr(chunk, 'text') and chunk.text:
                    chunk_text = chunk.text
                    self.stream_handler.add_chunk(chunk_text)
                    response_text += chunk_text
            
            # Stop streaming and get final response
            self.stream_handler.stop_streaming()
            
            # Add new line after response
            self.chat_display.text.configure(state="normal")
            self.chat_display.insert(END, "\n", "ai_text")
            self.chat_display.text.configure(state="disabled")
            
            # Add AI response to history with enhanced metadata
            ai_message = self.client.create_message_structure("ai", response_text, self.client.model, self.client.params)
            self.client.conversation_history.append(ai_message)
            
            # Auto-save after every message exchange
            print("Auto-saving conversation...")
            await self.client.save_conversation(quiet=True)
            
            print("Streaming message processed successfully")
            
        except Exception as e:
            print(f"Error in streaming: {e}")
            import traceback
            traceback.print_exc()
            self.add_system_message(f"Error during streaming: {str(e)}")
    
    async def on_select_model(self):
        """Select a different model"""
        print("Opening model selection dialog...")
        self.status_var.set("Loading available models...")
        
        # Get available models
        models = await self.client.get_available_models()
        
        if not models:
            print("No models available")
            self.status_var.set("Error: No models available")
            Messagebox.show_error("No models available or error retrieving models.", "Model Selection Error")
            return
        
        print(f"Found {len(models)} available models")
        
        # Create model selection dialog
        dialog = ttk.Toplevel(self.root)
        dialog.title("Select Model")
        dialog.minsize(400, 300)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Label
        ttk.Label(
            dialog,
            text="Select a model to use:",
            font="-size 12 -weight bold",
            padding=10
        ).pack(fill=X)
        
        # Model listbox frame
        model_frame = ttk.Frame(dialog, padding=10)
        model_frame.pack(fill=BOTH, expand=YES)
        
        # Create treeview with columns
        listbox = ttk.Treeview(
            model_frame,
            columns=("name", "display_name", "input", "output"),
            show="headings",
            height=10,
            selectmode="browse"
        )
        
        # Define columns
        listbox.heading("name", text="Name")
        listbox.heading("display_name", text="Display Name")
        listbox.heading("input", text="Input Tokens")
        listbox.heading("output", text="Output Tokens")
        
        listbox.column("name", width=150)
        listbox.column("display_name", width=200)
        listbox.column("input", width=80, anchor=CENTER)
        listbox.column("output", width=80, anchor=CENTER)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(model_frame, orient=VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        
        listbox.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # Add models to listbox
        for model in models:
            name = model["name"]
            if '/' in name:
                name = name.split('/')[-1]
                
            listbox.insert(
                "",
                END,
                values=(
                    name,
                    model["display_name"],
                    model["input_token_limit"],
                    model["output_token_limit"]
                )
            )
            
            # Select current model
            if name == self.client.model:
                for row in listbox.get_children():
                    values = listbox.item(row)["values"]
                    if values and values[0] == name:
                        listbox.selection_set(row)
                        listbox.see(row)
                        break
        
        # Buttons frame
        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill=X)
        
        def on_select():
            """Handle model selection"""
            selected = listbox.selection()
            if selected:
                selected_model = listbox.item(selected[0])["values"][0]
                print(f"Selected model: {selected_model}")
                self.client.model = selected_model
                self.model_var.set(selected_model)
                self.status_var.set(f"Selected model: {selected_model}")
                dialog.destroy()
        
        # Add button
        select_btn = ttk.Button(btn_frame, text="Select", command=on_select, bootstyle="success")
        select_btn.pack(side=LEFT, padx=5)
        
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, bootstyle="secondary")
        cancel_btn.pack(side=LEFT, padx=5)
        
        # Center dialog
        dialog.update_idletasks()  # Ensure dimensions are calculated
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (self.root.winfo_width() - width) // 2 + self.root.winfo_x()
        y = (self.root.winfo_height() - height) // 2 + self.root.winfo_y()
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        # Wait for dialog
        dialog.wait_window()
        
        self.status_var.set("Ready")
    
    async def on_customize_params(self):
        """Customize generation parameters"""
        print("Opening parameters dialog...")
        
        # Create dialog
        dialog = ttk.Toplevel(self.root)
        dialog.title("Model Parameters")
        dialog.minsize(300, 200)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Label
        ttk.Label(
            dialog,
            text="Customize Generation Parameters:",
            font="-size 12 -weight bold",
            padding=10
        ).pack(fill=X)
        
        # Parameters frame
        params_frame = ttk.Frame(dialog, padding=10)
        params_frame.pack(fill=BOTH, expand=YES)
        
        # Temperature
        temp_frame = ttk.Frame(params_frame)
        temp_frame.pack(fill=X, pady=5)
        
        ttk.Label(temp_frame, text="Temperature (0.0-2.0):").pack(side=LEFT)
        temp_var = ttk.DoubleVar(value=self.client.params["temperature"])
        temp_entry = ttk.Entry(temp_frame, textvariable=temp_var, width=10)
        temp_entry.pack(side=LEFT, padx=5)
        
        # Max output tokens
        tokens_frame = ttk.Frame(params_frame)
        tokens_frame.pack(fill=X, pady=5)
        
        ttk.Label(tokens_frame, text="Max output tokens:").pack(side=LEFT)
        tokens_var = ttk.IntVar(value=self.client.params["max_output_tokens"])
        tokens_entry = ttk.Entry(tokens_frame, textvariable=tokens_var, width=10)
        tokens_entry.pack(side=LEFT, padx=5)
        
        # Top-p
        top_p_frame = ttk.Frame(params_frame)
        top_p_frame.pack(fill=X, pady=5)
        
        ttk.Label(top_p_frame, text="Top-p (0.0-1.0):").pack(side=LEFT)
        top_p_var = ttk.DoubleVar(value=self.client.params["top_p"])
        top_p_entry = ttk.Entry(top_p_frame, textvariable=top_p_var, width=10)
        top_p_entry.pack(side=LEFT, padx=5)
        
        # Top-k
        top_k_frame = ttk.Frame(params_frame)
        top_k_frame.pack(fill=X, pady=5)
        
        ttk.Label(top_k_frame, text="Top-k (positive integer):").pack(side=LEFT)
        top_k_var = ttk.IntVar(value=self.client.params["top_k"])
        top_k_entry = ttk.Entry(top_k_frame, textvariable=top_k_var, width=10)
        top_k_entry.pack(side=LEFT, padx=5)
        
        # Buttons
        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill=X)
        
        def on_save():
            """Save parameters"""
            try:
                # Update parameters
                self.client.params["temperature"] = temp_var.get()
                self.client.params["max_output_tokens"] = tokens_var.get()
                self.client.params["top_p"] = top_p_var.get()
                self.client.params["top_k"] = top_k_var.get()
                
                print(f"Parameters updated: {self.client.params}")
                self.status_var.set("Parameters updated")
                dialog.destroy()
            except ValueError as e:
                print(f"Error updating parameters: {e}")
                Messagebox.show_error(f"Invalid input: {str(e)}", "Error", parent=dialog)
        
        save_btn = ttk.Button(btn_frame, text="Save", command=on_save, bootstyle="success")
        save_btn.pack(side=LEFT, padx=5)
        
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, bootstyle="secondary")
        cancel_btn.pack(side=LEFT, padx=5)
        
        # Center dialog
        dialog.update_idletasks()  # Ensure dimensions are calculated
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (self.root.winfo_width() - width) // 2 + self.root.winfo_x()
        y = (self.root.winfo_height() - height) // 2 + self.root.winfo_y()
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        # Wait for dialog
        dialog.wait_window()
    
    # ============= Helper Methods =============
    
    def create_settings_dialog(self):
        """Create and show the settings dialog"""
        print("Creating settings dialog...")
        dialog = ttk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.minsize(400, 200)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Label
        ttk.Label(
            dialog,
            text="Gemini Chat Settings",
            font="-size 12 -weight bold",
            padding=10
        ).pack(fill=X)
        
        # Settings frame
        settings_frame = ttk.Frame(dialog, padding=10)
        settings_frame.pack(fill=BOTH, expand=YES)
        
        # API Key
        api_frame = ttk.Frame(settings_frame)
        api_frame.pack(fill=X, pady=5)
        
        ttk.Label(api_frame, text="API Key:").pack(side=LEFT)
        api_var = ttk.StringVar(value=self.client.api_key)
        api_entry = ttk.Entry(api_frame, textvariable=api_var, show="*", width=40)
        api_entry.pack(side=LEFT, padx=5, fill=X, expand=YES)
        
        # API key status indicator
        api_status = ttk.Label(
            api_frame, 
            text="Not Set" if not self.client.api_key else "Set",
            foreground="red" if not self.client.api_key else "green",
            padding=(5, 0)
        )
        api_status.pack(side=RIGHT)
        
        # Conversations directory
        dir_frame = ttk.Frame(settings_frame)
        dir_frame.pack(fill=X, pady=5)
        
        ttk.Label(dir_frame, text="Conversations Directory:").pack(side=LEFT)
        dir_var = ttk.StringVar(value=str(self.client.conversations_dir))
        dir_entry = ttk.Entry(dir_frame, textvariable=dir_var, width=40)
        dir_entry.pack(side=LEFT, padx=5, fill=X, expand=YES)
        
        # Theme selection
        theme_frame = ttk.Frame(settings_frame)
        theme_frame.pack(fill=X, pady=5)
        
        ttk.Label(theme_frame, text="Theme:").pack(side=LEFT)
        theme_var = ttk.StringVar(value=self.root.style.theme.name)
        theme_combo = ttk.Combobox(
            theme_frame,
            textvariable=theme_var,
            values=self.root.style.theme_names(),
            state="readonly",
            width=20
        )
        theme_combo.pack(side=LEFT, padx=5)
        
        # Live theme change
        def on_theme_change(event):
            """Change theme immediately"""
            selected_theme = theme_var.get()
            print(f"Changing theme to: {selected_theme}")
            self.root.style.theme_use(selected_theme)
        
        theme_combo.bind("<<ComboboxSelected>>", on_theme_change)
        
        # API Key info
        if not self.client.api_key:
            info_frame = ttk.Frame(settings_frame)
            info_frame.pack(fill=X, pady=10)
            
            ttk.Label(
                info_frame,
                text="To use CannonAI's AI features, you need a Gemini API key.\n" \
                     "Sign up at https://ai.google.dev/ to get one.",
                justify="left",
                wraplength=350
            ).pack(fill=X)
        
        # Buttons
        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill=X)
        
        def on_save():
            """Save settings"""
            print("Saving settings...")
            # Update API key
            new_api_key = api_var.get()
            api_key_changed = new_api_key != self.client.api_key
            
            if api_key_changed:
                print(f"Updating API key: {new_api_key[:4] if new_api_key else 'None'}...{new_api_key[-4:] if new_api_key and len(new_api_key) > 4 else ''}")
                self.client.api_key = new_api_key
                self.config.set_api_key(new_api_key)
                
                # Need to reinitialize client if API key changed
                if new_api_key:  # Only reinitialize if a key was provided
                    self.async_helper.run_coroutine(self.client.initialize_client())
                    self.add_system_message("API key updated. You can now use AI features.")
                    self.status_var.set("Ready")
                else:
                    self.add_system_message("API key removed. AI features are now disabled.")
                    self.status_var.set("API key required")
            
            # Update conversations directory
            new_dir = dir_var.get()
            if new_dir != str(self.client.conversations_dir):
                print(f"Updating conversations directory: {new_dir}")
                path = Path(new_dir)
                self.client.conversations_dir = path
                self.client.ensure_directories(path)
                self.config.set("conversations_dir", new_dir)
            
            # Save theme
            selected_theme = theme_var.get()
            print(f"Saving theme preference: {selected_theme}")
            self.config.set("theme", selected_theme)
            
            # Save config
            self.config.save_config()
            
            self.status_var.set("Settings saved")
            dialog.destroy()
        
        save_btn = ttk.Button(btn_frame, text="Save", command=on_save, bootstyle="success")
        save_btn.pack(side=LEFT, padx=5)
        
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, bootstyle="secondary")
        cancel_btn.pack(side=LEFT, padx=5)
        
        # Center dialog
        dialog.update_idletasks()  # Ensure dimensions are calculated
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (self.root.winfo_width() - width) // 2 + self.root.winfo_x()
        y = (self.root.winfo_height() - height) // 2 + self.root.winfo_y()
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        print("Settings dialog created and displayed")
        # Wait for dialog
        dialog.wait_window()
    
    def add_user_message_to_display(self, message):
        """Add a user message to the chat display
        
        Args:
            message: The message to add
        """
        text_widget = self.chat_display.text
        text_widget.configure(state="normal")
        self.chat_display.insert(END, "You: ", "user_label")
        self.chat_display.insert(END, f"{message}\n", "user_text")
        text_widget.configure(state="disabled")
        self.chat_display.see(END)
    
    def add_ai_message_to_display(self, message):
        """Add an AI message to the chat display
        
        Args:
            message: The message to add
        """
        text_widget = self.chat_display.text
        text_widget.configure(state="normal")
        self.chat_display.insert(END, "AI: ", "ai_label")
        self.chat_display.insert(END, f"{message}\n", "ai_text")
        text_widget.configure(state="disabled")
        self.chat_display.see(END)
    
    def add_system_message(self, message):
        """Add a system message to the chat display
        
        Args:
            message: The message to add
        """
        # Access the internal Text widget of ScrolledText
        text_widget = self.chat_display.text
        text_widget.configure(state="normal")
        self.chat_display.insert(END, f"--- {message} ---\n", "system_text")
        text_widget.configure(state="disabled")
        self.chat_display.see(END)
    
    def start(self):
        """Start the application"""
        print("Starting application...")
        
        # Setup UI first before any async operations
        self.setup_ui()
        
        # Set window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Schedule the initialization to run after the main loop starts
        self.root.after(100, self.start_initialization)
        
        # Start the Tkinter main loop
        print("Starting main loop...")
        self.root.mainloop()
        
    def start_initialization(self):
        """Start the client initialization after the main loop is running"""
        print("Starting client initialization...")
        
        # Initialize the client
        future = self.async_helper.run_coroutine(self.initialize())
        
        # Add a callback for when initialization completes
        def on_initialization_done(fut):
            try:
                if fut.result():
                    print("Initialization successful")
                    self.status_var.set("Ready")
                else:
                    print("Initialization failed")
                    self.status_var.set("Failed to initialize")
            except Exception as e:
                print(f"Error during initialization: {e}")
                self.status_var.set("Error: Initialization failed")
                import traceback
                traceback.print_exc()
        
        # Add the callback to the future
        future.add_done_callback(on_initialization_done)
    
    def on_close(self):
        """Handle window close event"""
        print("Window close event triggered")
        try:
            # Save conversation
            future = self.async_helper.run_coroutine(self.client.save_conversation())
            future.result(timeout=5)
            print("Conversation saved")
            
            # Clean up
            self.cleanup()
            
            # Destroy the window
            self.root.destroy()
        except Exception as e:
            print(f"Error during close: {e}")
            self.root.destroy()
    
    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up resources...")
        
        # Reset stdout
        if hasattr(self, 'redirector') and self.redirector is not None:
            sys.stdout = self.redirector.prev_stdout
        
        # Stop the async helper
        if hasattr(self, 'async_helper') and self.async_helper is not None:
            self.async_helper.stop()
            
        print("Cleanup complete")
