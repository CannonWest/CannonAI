#!/usr/bin/env python3
"""
Gemini Chat Base Client - Core functionality for Gemini API interactions.

This module provides the base classes and shared functionality for both
synchronous and asynchronous implementations of the Gemini Chat client.
"""

import json
import os
import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

# Use colorama for cross-platform terminal colors
try:
    from colorama import init, Fore, Back, Style
    # Initialize colorama
    init(autoreset=True)
except ImportError:
    print("Warning: colorama package not installed. Terminal colors may not work correctly.")
    print("Please install with: pip install colorama")

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai package not installed.")
    print("Please install with: pip install google-genai")
    exit(1)


class Colors:
    """
    Terminal colors for better user experience.
    Uses colorama for cross-platform compatibility.
    """
    # Basic colors
    HEADER = Fore.MAGENTA if 'colorama' in globals() else '\033[95m'
    BLUE = Fore.BLUE if 'colorama' in globals() else '\033[94m'
    CYAN = Fore.CYAN if 'colorama' in globals() else '\033[96m'
    GREEN = Fore.GREEN if 'colorama' in globals() else '\033[92m'
    WARNING = Fore.YELLOW if 'colorama' in globals() else '\033[93m'
    FAIL = Fore.RED if 'colorama' in globals() else '\033[91m'
    ENDC = Style.RESET_ALL if 'colorama' in globals() else '\033[0m'
    BOLD = Style.BRIGHT if 'colorama' in globals() else '\033[1m'
    UNDERLINE = '\033[4m'  # Not directly supported in colorama


class BaseGeminiClient:
    """Base class for Gemini Chat clients (both sync and async)."""
    
    DEFAULT_MODEL = "gemini-2.0-flash"
    VERSION = "2.0.0"  # Updated for new conversation structure
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, 
                 conversations_dir: Optional[Path] = None):
        """Initialize the base Gemini client.
        
        Args:
            api_key: The Gemini API key. If None, will attempt to get from environment.
            model: The model to use. Defaults to DEFAULT_MODEL.
            conversations_dir: Directory to store conversations. If None, uses default.
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or self.DEFAULT_MODEL
        
        # Set up the base directory if not provided
        if conversations_dir is None:
            # Get the current file path and determine the project structure
            current_file = Path(__file__).resolve()
            
            # First, find the parent directory containing "gemini_chat"
            current_dir = current_file.parent
            
            # Check if we're in the correct project structure
            if current_dir.name == "cannonai":
                # "gemini_chat" is the current directory
                # The parent should be "CannonAI" or the repository root
                parent_dir = current_dir.parent
                
                # Set conversations directory adjacent to gemini_chat
                self.base_directory = parent_dir / "gemini_chat_conversations"
                
                print(f"Debug: Found correct project structure")
                print(f"Debug: gemini_chat dir: {current_dir}")
                print(f"Debug: parent dir: {parent_dir}")
            else:
                # Fallback if the structure isn't as expected
                print(f"Debug: Unexpected directory structure. Current dir: {current_dir}")
                self.base_directory = Path(os.path.expanduser("~")) / "gemini_chat_conversations"
        else:
            self.base_directory = conversations_dir
            
        print(f"Debug: Setting conversations directory to: {self.base_directory}")
            
        self.client = None  # Will be initialized in concrete implementations
        
        # Common parameters for text generation
        self.default_params = {
            "temperature": 0.7,
            "max_output_tokens": 800,
            "top_p": 0.95,
            "top_k": 40
        }
    
    def ensure_directories(self, base_dir: Path) -> None:
        """Ensure necessary directories exist."""
        base_dir.mkdir(parents=True, exist_ok=True)
        print(f"Conversations will be saved to: {base_dir}")
    
    def format_filename(self, title: str, conversation_id: str) -> str:
        """Format a filename for a conversation.
        
        Args:
            title: The conversation title
            conversation_id: The unique ID for the conversation
            
        Returns:
            Formatted filename string
        """
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
        return f"{safe_title}_{conversation_id[:8]}.json"

    def create_message_structure(self, role: str, text: str, model: str, 
                                params: Dict[str, Any], token_usage: Dict[str, Any] = None,
                                message_id: Optional[str] = None, parent_id: Optional[str] = None,
                                branch_id: str = "main") -> Dict[str, Any]:
        """Create a standard message structure for conversation history.
        
        Args:
            role: The role of the message ("user" or "assistant")
            text: The message text content
            model: The model used (only stored for assistant messages)
            params: Generation parameters (only stored for assistant messages)
            token_usage: Optional token usage metrics
            message_id: Unique identifier for this message
            parent_id: ID of the parent message
            branch_id: ID of the branch this message belongs to
            
        Returns:
            Message structure dictionary
        """
        import uuid
        
        if message_id is None:
            message_id = str(uuid.uuid4())
            
        message = {
            "id": message_id,
            "parent_id": parent_id,
            "branch_id": branch_id,
            "type": role,  # "user" or "assistant"
            "content": text,
            "timestamp": datetime.now().isoformat(),
            "children": []  # Will be populated as new messages are added
        }
        
        # Only store model/params for assistant messages
        if role == "assistant" or role == "ai":
            message["model"] = model
            message["params"] = params.copy()
            if token_usage:
                message["token_usage"] = token_usage
            
        return message
        
    def create_metadata_structure(self, title: str, conversation_id: str) -> Dict[str, Any]:
        """Create metadata structure for conversation.
        
        Args:
            title: Conversation title
            conversation_id: Unique conversation identifier
            
        Returns:
            Metadata structure dictionary
        """
        return {
            "conversation_id": conversation_id,
            "version": self.VERSION,
            "metadata": {
                "title": title,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "app_info": "Gemini Chat CLI",
                "platform": platform.system(),
                "active_branch": "main",
                "active_leaf": None  # Will be updated as messages are added
            },
            "messages": {},  # Message ID -> Message dict
            "branches": {
                "main": {
                    "created_at": datetime.now().isoformat(),
                    "last_message": None,
                    "message_count": 0
                }
            }
        }

    def build_chat_history(self, conversation_data: Dict[str, Any], branch_id: str = None) -> List[types.Content]:
        """Build API-compatible chat history from conversation structure.
        
        Args:
            conversation_data: The full conversation data structure
            branch_id: Optional branch to follow (defaults to active_branch)
            
        Returns:
            List of Content objects for the API
        """
        if branch_id is None:
            branch_id = conversation_data.get("metadata", {}).get("active_branch", "main")
            
        # Build the message chain for the specified branch
        message_chain = self._build_message_chain(conversation_data, branch_id)
        
        # Convert to API-compatible format
        chat_history = []
        for msg_id in message_chain:
            msg = conversation_data["messages"][msg_id]
            if msg["type"] in ["user", "assistant", "ai"]:
                # Convert role to API format
                api_role = "user" if msg["type"] == "user" else "model"
                chat_history.append(types.Content(
                    role=api_role, 
                    parts=[types.Part.from_text(text=msg["content"])]
                ))
        
        return chat_history
    
    def _build_message_chain(self, conversation_data: Dict[str, Any], branch_id: str) -> List[str]:
        """Build ordered list of message IDs for a specific branch.
        
        Args:
            conversation_data: The full conversation data
            branch_id: The branch to follow
            
        Returns:
            Ordered list of message IDs from root to leaf
        """
        messages = conversation_data.get("messages", {})
        if not messages:
            return []
            
        # Find the leaf node for this branch
        branch_info = conversation_data.get("branches", {}).get(branch_id, {})
        leaf_id = branch_info.get("last_message")
        
        if not leaf_id or leaf_id not in messages:
            return []
            
        # Build chain from leaf to root
        chain = []
        current_id = leaf_id
        
        while current_id:
            chain.append(current_id)
            current_msg = messages.get(current_id, {})
            current_id = current_msg.get("parent_id")
            
        # Reverse to get root-to-leaf order
        chain.reverse()
        return chain
        
    def extract_token_usage(self, response) -> Dict[str, Any]:
        """Extract token usage metadata from response if available.
        
        Args:
            response: The API response object
            
        Returns:
            Dictionary of token usage metrics or empty dict if not available
        """
        token_usage = {}
        try:
            if hasattr(response, 'usage_metadata'):
                # Extract token counts from usage_metadata
                token_usage = {
                    "prompt_token_count": getattr(response.usage_metadata, 'prompt_token_count', None),
                    "candidates_token_count": getattr(response.usage_metadata, 'candidates_token_count', None),
                    "total_token_count": getattr(response.usage_metadata, 'total_token_count', None)
                }
                # Filter out None values
                token_usage = {k: v for k, v in token_usage.items() if v is not None}
        except Exception:
            # Silently handle errors in token extraction
            pass
            
        return token_usage

    def get_version(self) -> str:
        """Get the current version of the Gemini Chat CLI.
        
        Returns:
            The version string
        """
        return self.VERSION
