#!/usr/bin/env python3
"""
Gemini Chat Asynchronous Client - Asynchronous implementation of Gemini Chat client.

This module provides the asynchronous implementation of the Gemini Chat client,
building on the core functionality in base_client.py.
"""

import asyncio
import getpass
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, AsyncIterator

from tabulate import tabulate

from base_client import BaseGeminiClient, Colors

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai package not installed.")
    print("Please install with: pip install google-genai")
    exit(1)


class AsyncGeminiClient(BaseGeminiClient):
    """Asynchronous implementation of the Gemini Chat client."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 conversations_dir: Optional[Path] = None):
        """Initialize the asynchronous Gemini client.

        Args:
            api_key: The Gemini API key. If None, will attempt to get from environment.
            model: The model to use. Defaults to DEFAULT_MODEL.
            conversations_dir: Directory to store conversations. If None, uses default.
        """
        # Call parent constructor
        super().__init__(api_key, model, conversations_dir)

        # Async-specific initialization
        self.conversation_id: Optional[str] = None
        self.conversation_data: Dict[str, Any] = {}  # New structure replaces conversation_history
        self.params: Dict[str, Any] = self.default_params.copy()
        self.use_streaming: bool = False  # Default to non-streaming
        self.conversation_name: str = "New Conversation"  # Default conversation name
        self.current_user_message: Optional[str] = None  # Store the current user message for streaming
        self.current_user_message_id: Optional[str] = None  # Store the ID of current user message
        self.is_web_ui: bool = False  # Flag for web UI mode
        self.active_branch: str = "main"  # Track active branch

        # The base directory is already set by the parent constructor
        self.conversations_dir = self.base_directory
        self.ensure_directories(self.conversations_dir)

    async def initialize_client(self) -> bool:
        """Initialize the Gemini client with API key asynchronously.

        Returns:
            True if initialization was successful, False otherwise
        """
        if not self.api_key:
            print(f"{Colors.WARNING}No API key provided. Please set GEMINI_API_KEY environment variable "
                  f"or provide it when initializing the client.{Colors.ENDC}")
            return False

        try:
            print(f"Initializing client with API key: {self.api_key[:4]}...{self.api_key[-4:]}")
            # Initialize the client - note that genai.Client() is used for both sync and async
            # as the library handles the async operation internally
            self.client = genai.Client(api_key=self.api_key)
            print(f"{Colors.GREEN}Successfully connected to Gemini API.{Colors.ENDC}")
            return True
        except Exception as e:
            print(f"{Colors.FAIL}Failed to initialize Gemini client: {e}{Colors.ENDC}")
            return False

    def generate_conversation_id(self) -> str:
        """Generate a unique conversation ID.

        Returns:
            A UUID string
        """
        return str(uuid.uuid4())
    
    def _add_message_to_conversation(self, message: Dict[str, Any]) -> None:
        """Add a message to the conversation structure and update relationships.
        
        Args:
            message: The message dictionary to add
        """
        msg_id = message["id"]
        parent_id = message.get("parent_id")
        branch_id = message.get("branch_id", "main")
        
        print(f"{Colors.CYAN}Adding message {msg_id[:8]}... to branch '{branch_id}'{Colors.ENDC}")
        
        # Add message to messages dict
        self.conversation_data["messages"][msg_id] = message
        
        # Update parent's children list if parent exists
        if parent_id and parent_id in self.conversation_data["messages"]:
            parent = self.conversation_data["messages"][parent_id]
            if msg_id not in parent.get("children", []):
                parent.setdefault("children", []).append(msg_id)
                print(f"{Colors.CYAN}Updated parent {parent_id[:8]}... children list{Colors.ENDC}")
        
        # Update branch information
        if branch_id in self.conversation_data.get("branches", {}):
            branch = self.conversation_data["branches"][branch_id]
            branch["last_message"] = msg_id
            branch["message_count"] = branch.get("message_count", 0) + 1
            print(f"{Colors.CYAN}Updated branch '{branch_id}' - last_message: {msg_id[:8]}...{Colors.ENDC}")
        
        # Update active leaf in metadata
        if branch_id == self.conversation_data["metadata"].get("active_branch", "main"):
            self.conversation_data["metadata"]["active_leaf"] = msg_id
            print(f"{Colors.CYAN}Updated active leaf to {msg_id[:8]}...{Colors.ENDC}")
    
    def _get_last_message_id(self, branch_id: Optional[str] = None) -> Optional[str]:
        """Get the ID of the last message in a branch.
        
        Args:
            branch_id: The branch to check (defaults to active branch)
            
        Returns:
            The ID of the last message or None
        """
        if branch_id is None:
            branch_id = self.conversation_data["metadata"].get("active_branch", "main")
        
        branch = self.conversation_data.get("branches", {}).get(branch_id, {})
        return branch.get("last_message")
    
    def _convert_old_to_new_format(self) -> None:
        """Convert old conversation_history format to new conversation_data format."""
        if not hasattr(self, 'conversation_history') or not self.conversation_history:
            return
        
        print(f"{Colors.CYAN}Converting old format to new format...{Colors.ENDC}")
        
        # Initialize new conversation structure
        title = "Converted Conversation"
        conversation_id = self.conversation_id or self.generate_conversation_id()
        
        # Extract metadata first
        metadata_item = None
        for item in self.conversation_history:
            if item.get("type") == "metadata":
                metadata_item = item
                metadata = item.get("content", {})
                title = metadata.get("title", title)
                break
        
        # Create new format structure
        self.conversation_data = self.create_metadata_structure(title, conversation_id)
        
        # Convert messages
        messages = {}
        prev_message_id = None
        
        for item in self.conversation_history:
            if item.get("type") == "message":
                content = item.get("content", {})
                role = content.get("role")
                text = content.get("text", "")
                
                if role in ["user", "assistant", "ai"]:
                    # Convert ai role to assistant for consistency
                    if role == "ai":
                        role = "assistant"
                    
                    # Create new message structure
                    message = self.create_message_structure(
                        role=role,
                        text=text,
                        model=self.model,
                        params=self.params if role == "assistant" else {},
                        parent_id=prev_message_id,
                        branch_id="main"
                    )
                    
                    messages[message["id"]] = message
                    
                    # Update parent-child relationships
                    if prev_message_id and prev_message_id in messages:
                        messages[prev_message_id].setdefault("children", []).append(message["id"])
                    
                    prev_message_id = message["id"]
        
        # Add messages to conversation_data
        self.conversation_data["messages"] = messages
        
        # Update branch info
        if prev_message_id:
            self.conversation_data["branches"]["main"]["last_message"] = prev_message_id
            self.conversation_data["branches"]["main"]["message_count"] = len(messages)
            self.conversation_data["metadata"]["active_leaf"] = prev_message_id
        
        print(f"{Colors.GREEN}Converted {len(messages)} messages to new format{Colors.ENDC}")

    async def start_new_conversation(self, title: Optional[str] = None, is_web_ui: bool = False) -> None:
        """Start a new conversation asynchronously.

        Args:
            title: Optional title for the conversation. If None, will prompt or generate.
            is_web_ui: Whether this is being called from the web UI.
        """
        print(f"{Colors.CYAN}Starting new conversation...{Colors.ENDC}")
        self.conversation_id = self.generate_conversation_id()
        
        # Get title for the conversation
        if title is None and not is_web_ui:
            # Only prompt for input in CLI mode
            title = input("Enter a title for this conversation (or leave blank for timestamp): ")

        # Generate default title if none provided
        if not title:
            title = f"Conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Update the conversation name property
        self.conversation_name = title

        # Create initial conversation structure using new format
        self.conversation_data = self.create_metadata_structure(title, self.conversation_id)
        self.active_branch = "main"
        
        print(f"{Colors.GREEN}Started new conversation: {title}{Colors.ENDC}")
        print(f"{Colors.CYAN}Conversation ID: {self.conversation_id[:8]}...{Colors.ENDC}")
        print(f"{Colors.CYAN}Active branch: {self.active_branch}{Colors.ENDC}")

        # Initial save of the new conversation
        await self.save_conversation()

    async def retry_message(self, message_id: str) -> Dict[str, Any]:
        """Retry generating a response for a specific message.
        
        Args:
            message_id: The ID of the assistant message to retry
            
        Returns:
            Dict with new message data
        """
        print(f"[DEBUG] Retrying message: {message_id}")
        
        if not self.conversation_data:
            raise ValueError("No active conversation")
            
        messages = self.conversation_data.get("messages", {})
        target_message = messages.get(message_id)
        
        if not target_message:
            raise ValueError(f"Message {message_id} not found")
            
        if target_message["type"] != "assistant":
            raise ValueError("Can only retry assistant messages")
            
        # Get parent message (user's prompt)
        parent_id = target_message["parent_id"]
        parent_message = messages.get(parent_id)
        
        if not parent_message:
            raise ValueError("Parent message not found")
            
        print(f"[DEBUG] Found parent message: {parent_id}")
        print(f"[DEBUG] Parent content: {parent_message['content'][:50]}...")
        
        # Create new branch ID for this retry
        import uuid
        new_branch_id = f"branch-{uuid.uuid4().hex[:8]}"
        
        # Build conversation history up to parent message
        branch_id = parent_message.get("branch_id", "main")
        message_chain = self._build_message_chain(self.conversation_data, branch_id)
        
        # Find index of parent in chain and slice up to it
        parent_index = message_chain.index(parent_id) if parent_id in message_chain else -1
        if parent_index >= 0:
            message_chain = message_chain[:parent_index + 1]
        
        # Build chat history for API
        chat_history = []
        for msg_id in message_chain:
            msg = messages[msg_id]
            api_role = "user" if msg["type"] == "user" else "model"
            chat_history.append(types.Content(
                role=api_role,
                parts=[types.Part.from_text(text=msg["content"])]
            ))
        
        print(f"[DEBUG] Built history with {len(chat_history)} messages")
        
        # Generate new response
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=chat_history,
                config=types.GenerateContentConfig(**self.params)
            )
            
            response_text = response.text
            token_usage = self.extract_token_usage(response)
            
            print(f"[DEBUG] Got new response: {response_text[:50]}...")
            
            # Create new message
            new_message = self.create_message_structure(
                role="assistant",
                text=response_text,
                model=self.model,
                params=self.params,
                token_usage=token_usage,
                parent_id=parent_id,
                branch_id=new_branch_id
            )
            
            # Update parent's children list
            if parent_id not in messages[parent_id]["children"]:
                messages[parent_id]["children"].append(new_message["id"])
            
            # Add to messages
            messages[new_message["id"]] = new_message
            
            # Update branch info
            if new_branch_id not in self.conversation_data["branches"]:
                self.conversation_data["branches"][new_branch_id] = {
                    "created_at": datetime.now().isoformat(),
                    "last_message": new_message["id"],
                    "message_count": 1
                }
            
            # Update sibling information
            siblings = messages[parent_id]["children"]
            for idx, sibling_id in enumerate(siblings):
                sibling = messages.get(sibling_id)
                if sibling:
                    sibling["sibling_index"] = idx
                    sibling["total_siblings"] = len(siblings)
            
            # Update metadata
            self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            self.conversation_data["metadata"]["active_branch"] = new_branch_id
            self.conversation_data["metadata"]["active_leaf"] = new_message["id"]
            
            print(f"[DEBUG] Created new message {new_message['id']} on branch {new_branch_id}")
            print(f"[DEBUG] Parent now has {len(siblings)} children")
            
            return {
                "message": new_message,
                "siblings": siblings,
                "sibling_index": len(siblings) - 1,
                "total_siblings": len(siblings)
            }
            
        except Exception as e:
            print(f"[ERROR] Failed to retry message: {e}")
            raise
    
    async def get_message_siblings(self, message_id: str) -> Dict[str, Any]:
        """Get sibling messages (alternative responses to same prompt).
        
        Args:
            message_id: The message ID to find siblings for
            
        Returns:
            Dict with sibling information
        """
        print(f"[DEBUG] Getting siblings for message: {message_id}")
        
        if not self.conversation_data:
            raise ValueError("No active conversation")
            
        messages = self.conversation_data.get("messages", {})
        target_message = messages.get(message_id)
        
        if not target_message:
            raise ValueError(f"Message {message_id} not found")
            
        parent_id = target_message.get("parent_id")
        if not parent_id:
            # Root message has no siblings
            return {
                "siblings": [message_id],
                "current_index": 0,
                "total": 1
            }
            
        parent = messages.get(parent_id)
        if not parent:
            raise ValueError("Parent message not found")
            
        siblings = parent.get("children", [])
        current_index = siblings.index(message_id) if message_id in siblings else -1
        
        print(f"[DEBUG] Found {len(siblings)} siblings, current at index {current_index}")
        
        return {
            "siblings": siblings,
            "current_index": current_index,
            "total": len(siblings),
            "parent_id": parent_id
        }
    
    async def switch_to_sibling(self, message_id: str, direction: str) -> Dict[str, Any]:
        """Switch to a sibling message (prev/next alternative response).
        
        Args:
            message_id: Current message ID
            direction: 'prev' or 'next'
            
        Returns:
            Dict with new active message info
        """
        print(f"[DEBUG] Switching {direction} from message: {message_id}")
        
        sibling_info = await self.get_message_siblings(message_id)
        siblings = sibling_info["siblings"]
        current_index = sibling_info["current_index"]
        
        if current_index < 0:
            raise ValueError("Current message not found in siblings")
            
        # Calculate new index
        if direction == "prev":
            new_index = current_index - 1
            if new_index < 0:
                new_index = len(siblings) - 1  # Wrap around
        else:  # next
            new_index = current_index + 1
            if new_index >= len(siblings):
                new_index = 0  # Wrap around
                
        new_message_id = siblings[new_index]
        new_message = self.conversation_data["messages"].get(new_message_id)
        
        if not new_message:
            raise ValueError("New message not found")
            
        # Update active branch and leaf
        self.conversation_data["metadata"]["active_branch"] = new_message.get("branch_id", "main")
        self.conversation_data["metadata"]["active_leaf"] = new_message_id
        
        print(f"[DEBUG] Switched to message {new_message_id} (index {new_index} of {len(siblings)})")
        
        return {
            "message": new_message,
            "sibling_index": new_index,
            "total_siblings": len(siblings)
        }
    
    async def get_conversation_tree(self) -> Dict[str, Any]:
        """Get the full conversation tree structure.
        
        Returns:
            Dict representing the conversation tree
        """
        print("[DEBUG] Building conversation tree")
        
        if not self.conversation_data:
            return {"nodes": [], "edges": []}
            
        messages = self.conversation_data.get("messages", {})
        nodes = []
        edges = []
        
        for msg_id, msg in messages.items():
            # Create node
            node = {
                "id": msg_id,
                "type": msg["type"],
                "content_preview": msg["content"][:50] + "..." if len(msg["content"]) > 50 else msg["content"],
                "timestamp": msg["timestamp"],
                "branch_id": msg.get("branch_id", "main"),
                "model": msg.get("model"),
                "is_active": msg_id == self.conversation_data["metadata"].get("active_leaf")
            }
            nodes.append(node)
            
            # Create edges to children
            for child_id in msg.get("children", []):
                edges.append({
                    "from": msg_id,
                    "to": child_id
                })
                
        print(f"[DEBUG] Built tree with {len(nodes)} nodes and {len(edges)} edges")
        
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": self.conversation_data["metadata"]
        }

    async def save_conversation(self, quiet: bool = False) -> None:
        """Save the current conversation to a JSON file asynchronously.

        Args:
            quiet: If True, don't print success messages (for auto-save)
        """
        if not self.conversation_id or not self.conversation_data:
            if not quiet:
                print(f"{Colors.WARNING}No active conversation to save.{Colors.ENDC}")
            return

        # Get conversation title from metadata
        title = self.conversation_data.get("metadata", {}).get("title", "Untitled")
        
        # Create filename with sanitized title
        filename = self.format_filename(title, self.conversation_id)
        filepath = self.conversations_dir / filename

        # Update metadata timestamps and counts
        if "metadata" in self.conversation_data:
            self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            # Count total messages across all branches
            total_messages = len(self.conversation_data.get("messages", {}))
            # Update branch message counts
            for branch_id, branch_info in self.conversation_data.get("branches", {}).items():
                branch_messages = sum(1 for msg in self.conversation_data.get("messages", {}).values() 
                                    if msg.get("branch_id") == branch_id)
                branch_info["message_count"] = branch_messages
        
        if not quiet:
            print(f"{Colors.CYAN}Saving conversation structure v{self.VERSION}...{Colors.ENDC}")

        # Save to file using non-blocking io
        try:
            def save_json():
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.conversation_data, f, indent=2, ensure_ascii=False)

            # Use to_thread to make file I/O non-blocking
            await asyncio.to_thread(save_json)

            if not quiet:
                print(f"{Colors.GREEN}Conversation saved to: {filepath}{Colors.ENDC}")
                print(f"{Colors.CYAN}Total messages: {total_messages}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}Error saving conversation: {e}{Colors.ENDC}")

    async def send_message(self, message: str) -> Optional[str]:
        """Send a message to the model and get the response asynchronously (CLI path).

        Args:
            message: The message to send

        Returns:
            The model's response text, or None if there was an error
        """
        if not message.strip():
            return None

        if not self.client:
            print(f"{Colors.FAIL}Error: Gemini client not initialized.{Colors.ENDC}")
            return None

        try:
            print(f"\n{Colors.CYAN}=== Processing Message ==={Colors.ENDC}")
            print(f"{Colors.CYAN}Active branch: {self.active_branch}{Colors.ENDC}")
            
            response_text = ""
            token_usage = {}

            # Get the parent ID (last message in the active branch)
            parent_id = self._get_last_message_id(self.active_branch)
            print(f"{Colors.CYAN}Parent message: {parent_id[:8] if parent_id else 'None (first message)'}...{Colors.ENDC}")
            
            # Create and add user message to the conversation structure
            user_message = self.create_message_structure(
                role="user", 
                text=message, 
                model=self.model,  # Model not stored for user messages in new structure
                params=self.params,  # Params not stored for user messages
                parent_id=parent_id,
                branch_id=self.active_branch
            )
            self._add_message_to_conversation(user_message)
            user_message_id = user_message["id"]
            print(f"{Colors.BLUE}User message ID: {user_message_id[:8]}...{Colors.ENDC}")

            # Configure generation parameters
            config = types.GenerateContentConfig(
                temperature=self.params["temperature"],
                max_output_tokens=self.params["max_output_tokens"],
                top_p=self.params["top_p"],
                top_k=self.params["top_k"]
            )

            # Build chat history from the tree structure
            chat_history = self.build_chat_history(self.conversation_data, self.active_branch)
            print(f"{Colors.CYAN}Chat history length: {len(chat_history)} messages{Colors.ENDC}")

            if self.use_streaming:
                print(f"\r{Colors.CYAN}AI is thinking... (streaming mode){Colors.ENDC}", end="", flush=True)
                print("\r" + " " * 50 + "\r", end="", flush=True)
                print(f"{Colors.GREEN}AI: {Colors.ENDC}", end="", flush=True)

                stream_generator = await self.client.aio.models.generate_content_stream(
                    model=self.model,
                    contents=chat_history,
                    config=config
                )
                async for chunk in stream_generator:
                    if hasattr(chunk, 'text') and chunk.text:
                        chunk_text = chunk.text
                        print(f"{chunk_text}", end="", flush=True)
                        response_text += chunk_text
                print()
            else:
                print(f"\r{Colors.CYAN}AI is thinking...{Colors.ENDC}", end="", flush=True)
                api_response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=chat_history,
                    config=config
                )
                print("\r" + " " * 50 + "\r", end="", flush=True)
                response_text = api_response.text
                if response_text is None: # Ensure response_text is not None
                    response_text = ""
                print(f"\n{Colors.GREEN}AI: {Colors.ENDC}{response_text}")
                token_usage = self.extract_token_usage(api_response)

            # Create and add AI response to the conversation structure
            ai_message = self.create_message_structure(
                role="assistant",  # Using "assistant" instead of "ai" for new structure
                text=response_text, 
                model=self.model,  # Model IS stored for assistant messages
                params=self.params,  # Params ARE stored for assistant messages
                token_usage=token_usage,
                parent_id=user_message_id,  # AI response is child of user message
                branch_id=self.active_branch
            )
            self._add_message_to_conversation(ai_message)
            print(f"{Colors.GREEN}AI message ID: {ai_message['id'][:8]}...{Colors.ENDC}")

            print(f"{Colors.CYAN}Auto-saving conversation...{Colors.ENDC}")
            await self.save_conversation(quiet=True)
            return response_text

        except Exception as e:
            print(f"{Colors.FAIL}Error generating response: {e}{Colors.ENDC}")
            # Add a placeholder AI message in history to mark the error
            error_message = self.create_message_structure(
                role="assistant", 
                text=f"Error: {e}", 
                model=self.model, 
                params=self.params,
                parent_id=user_message_id if 'user_message_id' in locals() else self._get_last_message_id(),
                branch_id=self.active_branch
            )
            self._add_message_to_conversation(error_message)
            await self.save_conversation(quiet=True)
            return None

    async def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available models asynchronously.

        Returns:
            List of model information dictionaries
        """
        if not self.client:
            print(f"{Colors.FAIL}Error: Gemini client not initialized.{Colors.ENDC}")
            return []

        models = []
        try:
            print(f"Fetching available models from Google AI API...")
            # Try to get models from the API
            model_list = await self.client.aio.models.list()

            if model_list:
                for model_obj in model_list: # Renamed to model_obj to avoid conflict
                    # Only include models that support text generation
                    if hasattr(model_obj, 'supported_actions') and "generateContent" in model_obj.supported_actions:
                        # Extract model info
                        model_info = {
                            "name": model_obj.name,
                            "display_name": model_obj.display_name if hasattr(model_obj, 'display_name') else model_obj.name,
                            "input_token_limit": model_obj.input_token_limit if hasattr(model_obj, 'input_token_limit') else "Unknown",
                            "output_token_limit": model_obj.output_token_limit if hasattr(model_obj, 'output_token_limit') else "Unknown"
                        }
                        models.append(model_info)
                        print(f"Found model: {model_info['name']}")

            # If API doesn't return any usable models, add defaults
            if not models:
                print("No models returned from API, adding default models")
                # Add default models
                models = [
                    {
                        "name": "models/gemini-2.0-flash", # Using full path for consistency
                        "display_name": "Gemini 2.0 Flash",
                        "input_token_limit": 32768,
                        "output_token_limit": 8192
                    },
                    {
                        "name": "models/gemini-2.0-pro", # Using full path
                        "display_name": "Gemini 2.0 Pro",
                        "input_token_limit": 32768,
                        "output_token_limit": 8192
                    },
                    # Add other known models including preview ones
                    {
                        "name": "models/gemini-2.5-flash-preview-05-20",
                        "display_name": "Gemini 2.5 Flash Preview 05-20",
                        "input_token_limit": 32768, # Placeholder, update with actual
                        "output_token_limit": 8192  # Placeholder
                    },
                    {
                        "name": "models/gemini-2.5-pro-preview-05-06",
                        "display_name": "Gemini 2.5 Pro Preview 05-06",
                        "input_token_limit": 65536, # Placeholder
                        "output_token_limit": 65536 # Placeholder
                    }
                ]

        except Exception as e:
            print(f"{Colors.FAIL}Error retrieving models: {e}{Colors.ENDC}")
            print(f"Adding default models instead")
            # Add default models in case of error (same as above)
            models = [
                {
                    "name": "models/gemini-2.0-flash",
                    "display_name": "Gemini 2.0 Flash",
                    "input_token_limit": 32768,
                    "output_token_limit": 8192
                },
                {
                    "name": "models/gemini-2.0-pro",
                    "display_name": "Gemini 2.0 Pro",
                    "input_token_limit": 32768,
                    "output_token_limit": 8192
                },
                {
                    "name": "models/gemini-2.5-flash-preview-05-20",
                    "display_name": "Gemini 2.5 Flash Preview 05-20",
                    "input_token_limit": 32768,
                    "output_token_limit": 8192
                },
                {
                    "name": "models/gemini-2.5-pro-preview-05-06",
                    "display_name": "Gemini 2.5 Pro Preview 05-06",
                    "input_token_limit": 65536,
                    "output_token_limit": 65536
                }
            ]

        return models

    async def display_models(self) -> None:
        """Display available models in a formatted table asynchronously."""
        models = await self.get_available_models()

        if not models:
            print(f"{Colors.WARNING}No models available or error retrieving models.{Colors.ENDC}")
            return

        headers = ["#", "Name", "Display Name", "Input Tokens", "Output Tokens"]
        table_data = []

        for i, model_info in enumerate(models, 1): # Renamed to model_info
            name = model_info["name"]
            # No need to split here if get_available_models returns full paths
            # if '/' in name:  # Handle full resource paths
            #     name = name.split('/')[-1]

            row = [
                i,
                name, # Show full name/path for clarity
                model_info["display_name"],
                model_info["input_token_limit"],
                model_info["output_token_limit"]
            ]
            table_data.append(row)

        print(tabulate(table_data, headers=headers, tablefmt="pretty"))

    async def select_model(self) -> None:
        """Let user select a model from available options asynchronously."""
        models = await self.get_available_models()

        if not models:
            print(f"{Colors.WARNING}No models available to select.{Colors.ENDC}")
            return

        await self.display_models()

        try:
            selection = int(input("\nEnter model number to select: "))
            if 1 <= selection <= len(models):
                model_name = models[selection-1]["name"] # Use the full name from the list
                self.model = model_name # Set the full model name
                print(f"{Colors.GREEN}Selected model: {self.model}{Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}Invalid selection.{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.FAIL}Please enter a valid number.{Colors.ENDC}")

    async def customize_params(self) -> None:
        """Allow user to customize generation parameters asynchronously."""
        print(f"\n{Colors.HEADER}Current Parameters:{Colors.ENDC}")
        for key, value in self.params.items():
            print(f"  {key}: {value}")

        print("\nEnter new values (or leave blank to keep current values):")

        try:
            # Temperature (0.0 to 2.0)
            temp = input(f"Temperature (0.0-2.0) [{self.params['temperature']}]: ")
            if temp:
                self.params["temperature"] = float(temp)

            # Max output tokens
            max_tokens = input(f"Max output tokens [{self.params['max_output_tokens']}]: ")
            if max_tokens:
                self.params["max_output_tokens"] = int(max_tokens)

            # Top-p (0.0 to 1.0)
            top_p = input(f"Top-p (0.0-1.0) [{self.params['top_p']}]: ")
            if top_p:
                self.params["top_p"] = float(top_p)

            # Top-k (positive integer)
            top_k = input(f"Top-k (positive integer) [{self.params['top_k']}]: ")
            if top_k:
                self.params["top_k"] = int(top_k)

            print(f"{Colors.GREEN}Parameters updated successfully.{Colors.ENDC}")

        except ValueError as e:
            print(f"{Colors.FAIL}Invalid input: {e}. Parameters not updated.{Colors.ENDC}")

    async def list_conversations(self) -> List[Dict[str, Any]]:
        """List available conversation files asynchronously.

        Returns:
            List of conversation information dictionaries
        """
        # Define function for synchronous file operations
        def read_conversation_files():
            result = []
            for file_path in self.conversations_dir.glob("*.json"): # Renamed to file_path
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # Handle both old and new formats
                    if "metadata" in data and "messages" in data:
                        # New format
                        metadata = data.get("metadata", {})
                        message_count = len(data.get("messages", {}))
                    else:
                        # Old format
                        metadata = {}
                        for item in data.get("history", []):
                            if item.get("type") == "metadata":
                                metadata = item.get("content", {})
                                break
                        message_count = sum(1 for item in data.get("history", []) if item.get("type") == "message")

                    result.append({
                        "filename": file_path.name,
                        "path": file_path,
                        "title": metadata.get("title", "Untitled"),
                        "model": metadata.get("model", "Unknown"),
                        "created_at": metadata.get("created_at", "Unknown"),
                        "message_count": message_count,
                        "conversation_id": data.get("conversation_id")
                    })
                except Exception as e:
                    print(f"{Colors.WARNING}Error reading {file_path.name}: {e}{Colors.ENDC}")
            return result

        # Use to_thread to make file I/O non-blocking
        conversations = await asyncio.to_thread(read_conversation_files)
        return conversations

    async def display_conversations(self) -> List[Dict[str, Any]]:
        """Display available conversations in a formatted table asynchronously.

        Returns:
            List of conversation information dictionaries
        """
        conversations = await self.list_conversations()

        if not conversations:
            print(f"{Colors.WARNING}No saved conversations found.{Colors.ENDC}")
            return conversations

        headers = ["#", "Title", "Model", "Messages", "Created", "Filepath"]
        table_data = []

        for i, conv in enumerate(conversations, 1):
            # Format created_at date
            created_at_str = conv["created_at"] # Renamed to created_at_str
            if created_at_str != "Unknown":
                try:
                    dt = datetime.fromisoformat(created_at_str)
                    created_at_str = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    pass

            row = [
                i,
                conv["title"],
                conv["model"],
                conv["message_count"],
                created_at_str,
                str(conv["path"])
            ]
            table_data.append(row)

        print(tabulate(table_data, headers=headers, tablefmt="pretty"))
        return conversations

    async def load_conversation(self, conversation_name: Optional[str] = None) -> None:
        """Load a saved conversation asynchronously.

        Args:
            conversation_name: Optional name of conversation to load directly.
                              If provided, will attempt to load by name instead of prompting.
        """
        conversations = await self.list_conversations()  # Just list without displaying for programmatic access

        if not conversations:
            print(f"{Colors.WARNING}No saved conversations found.{Colors.ENDC}")
            return

        selected_conv = None # Renamed to selected_conv
        if conversation_name:
            print(f"Attempting to load conversation: {conversation_name}")
            for conv in conversations:
                if conv["title"].lower() == conversation_name.lower():
                    selected_conv = conv
                    break
            if not selected_conv:
                try:
                    idx = int(conversation_name) - 1
                    if 0 <= idx < len(conversations):
                        selected_conv = conversations[idx]
                except ValueError:
                    pass
            if not selected_conv:
                print(f"{Colors.FAIL}Conversation '{conversation_name}' not found.{Colors.ENDC}")
                return
        else:
            await self.display_conversations()
            try:
                selection = int(input("\nEnter conversation number to load: "))
                if 1 <= selection <= len(conversations):
                    selected_conv = conversations[selection-1]
                else:
                    print(f"{Colors.FAIL}Invalid selection.{Colors.ENDC}")
                    return
            except ValueError:
                print(f"{Colors.FAIL}Please enter a valid number.{Colors.ENDC}")
                return
            except Exception as e: # Catch generic exception
                print(f"{Colors.FAIL}Error during selection: {e}{Colors.ENDC}")
                return

        # Common loading code
        try:
            if selected_conv : # Check if selected_conv is not None
                def read_json_file():
                    with open(selected_conv["path"], 'r', encoding='utf-8') as f:
                        return json.load(f)
                data = await asyncio.to_thread(read_json_file)

                self.conversation_id = data.get("conversation_id")
                
                # Handle both old and new format conversations
                if "messages" in data and "metadata" in data:
                    # New format - direct assignment
                    self.conversation_data = data
                    metadata = data.get("metadata", {})
                    self.model = metadata.get("model", self.model)
                    self.conversation_name = metadata.get("title", "Untitled")
                    self.active_branch = metadata.get("active_branch", "main")
                    print(f"{Colors.CYAN}Loaded new format conversation{Colors.ENDC}")
                else:
                    # Old format - convert to new format
                    self.conversation_history = data.get("history", [])
                    self._convert_old_to_new_format()
                    print(f"{Colors.CYAN}Converted old format conversation to new format{Colors.ENDC}")
                    
                    for item in self.conversation_history:
                        if item.get("type") == "metadata":
                            metadata = item.get("content", {})
                            self.model = metadata.get("model", self.model)
                            self.conversation_name = metadata.get("title", "Untitled") # Update conversation_name
                            if "params" in metadata:
                                self.params = metadata["params"]
                            break
                    
                print(f"{Colors.GREEN}Loaded conversation: {selected_conv['title']}{Colors.ENDC}")
                await self.display_conversation_history()
        except Exception as e:
            print(f"{Colors.FAIL}Error loading conversation data: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()

    async def display_conversation_history(self) -> None:
        """Display the current conversation history asynchronously."""
        # Check if we have any conversation data to display
        if hasattr(self, 'conversation_data') and self.conversation_data:
            # New format - use conversation_data
            messages = self.conversation_data.get("messages", {})
            if not messages:
                print(f"{Colors.WARNING}No conversation history to display.{Colors.ENDC}")
                return

            print(f"\n{Colors.HEADER}Conversation History:{Colors.ENDC}")
            metadata = self.conversation_data.get("metadata", {})
            title = metadata.get("title", "Untitled")
            model_name = metadata.get("model", self.model)
            print(f"{Colors.BOLD}Title: {title}{Colors.ENDC}")
            print(f"{Colors.BOLD}Model: {model_name}{Colors.ENDC}\n")

            # Get the active branch message chain
            active_branch = metadata.get("active_branch", "main")
            message_chain = self._build_message_chain(self.conversation_data, active_branch)
            
            for msg_id in message_chain:
                msg = messages.get(msg_id, {})
                if msg.get("type") in ["user", "assistant"]:
                    role = msg["type"]
                    text = msg.get("content", "")
                    if role == "user":
                        print(f"{Colors.BLUE}User: {Colors.ENDC}{text}")
                    else:
                        print(f"{Colors.GREEN}AI: {Colors.ENDC}{text}")
                    print("")
        
        # Fallback to old format if it exists
        elif hasattr(self, 'conversation_history') and self.conversation_history:
            print(f"\n{Colors.HEADER}Conversation History:{Colors.ENDC}")
            title = "Untitled"
            current_model_display = self.model
            for item in self.conversation_history:
                if item["type"] == "metadata":
                    metadata = item["content"]
                    title = metadata.get("title", title)
                    current_model_display = metadata.get("model", current_model_display)
                    self.conversation_name = title
                    break
            print(f"{Colors.BOLD}Title: {title}{Colors.ENDC}")
            print(f"{Colors.BOLD}Model: {current_model_display}{Colors.ENDC}\n")

            for item in self.conversation_history:
                if item["type"] == "message":
                    role = item["content"]["role"]
                    text = item["content"]["text"]
                    if role == "user":
                        print(f"{Colors.BLUE}User: {Colors.ENDC}{text}")
                    else:
                        print(f"{Colors.GREEN}AI: {Colors.ENDC}{text}")
                    print("")
        else:
            print(f"{Colors.WARNING}No conversation history to display.{Colors.ENDC}")

    async def toggle_streaming(self) -> bool:
        """Toggle streaming mode asynchronously.

        Returns:
            Current streaming mode state (True for enabled, False for disabled)
        """
        self.use_streaming = not self.use_streaming
        status = "enabled" if self.use_streaming else "disabled"
        print(f"{Colors.GREEN}Streaming mode {status}.{Colors.ENDC}")
        return self.use_streaming

    # --- Methods for UI interaction ---
    def add_user_message(self, message: str) -> None:
        """Add a user message to conversation (called by UI message handler)."""
        print(f"{Colors.CYAN}[UI] Adding user message to conversation{Colors.ENDC}")
        self.current_user_message = message
        
        # Ensure we have a conversation structure
        if not self.conversation_data:
            print(f"{Colors.CYAN}[UI] No active conversation, starting new one{Colors.ENDC}")
            self.conversation_id = self.generate_conversation_id()
            self.conversation_data = self.create_metadata_structure("UI Conversation", self.conversation_id)
            self.active_branch = "main"
        
        # Get the parent ID (last message in the active branch)
        parent_id = self._get_last_message_id(self.active_branch)
        
        # Create and add user message to the conversation structure
        user_message = self.create_message_structure(
            role="user", 
            text=message, 
            model=self.model,
            params={},  # No params for user messages
            parent_id=parent_id,
            branch_id=self.active_branch
        )
        self._add_message_to_conversation(user_message)
        self.current_user_message_id = user_message["id"]
        print(f"{Colors.BLUE}[UI] User message added with ID: {user_message['id'][:8]}...{Colors.ENDC}")

    def add_assistant_message(self, message: str, token_usage: Optional[Dict[str, Any]] = None) -> None:
        """Add an assistant message to conversation (called by UI message handler after response)."""
        print(f"{Colors.CYAN}[UI] Adding assistant message to conversation{Colors.ENDC}")
        
        # Ensure message is not None before adding
        text_to_add = message if message is not None else ""
        
        # Use the current user message ID as parent
        parent_id = self.current_user_message_id if self.current_user_message_id else self._get_last_message_id(self.active_branch)
        
        # Create and add assistant message to the conversation structure
        ai_message = self.create_message_structure(
            role="assistant",  # Using "assistant" for consistency
            text=text_to_add, 
            model=self.model,
            params=self.params,
            token_usage=token_usage,
            parent_id=parent_id,
            branch_id=self.active_branch
        )
        self._add_message_to_conversation(ai_message)
        print(f"{Colors.GREEN}[UI] Assistant message added with ID: {ai_message['id'][:8]}...{Colors.ENDC}")

    async def get_response(self) -> str:
        """Get a non-streaming response for self.current_user_message (for UI)."""
        print(f"{Colors.CYAN}[UI] Getting non-streaming response{Colors.ENDC}")
        
        if not self.current_user_message:
            return "Error: No current user message to process."
        if not self.client:
            return "Error: Gemini client not initialized."

        # current_user_message is already added to conversation by add_user_message()
        # So, DO NOT add it again here.

        config = types.GenerateContentConfig(**self.params)
        
        # Build chat history from the new conversation_data structure
        chat_history = self.build_chat_history(self.conversation_data, self.active_branch)
        print(f"{Colors.CYAN}[UI] Built chat history with {len(chat_history)} messages{Colors.ENDC}")

        try:
            print(f"\r{Colors.CYAN}AI is thinking (non-streaming UI)...{Colors.ENDC}", end="", flush=True)
            api_response = await self.client.aio.models.generate_content(
                model=self.model, contents=chat_history, config=config)
            print("\r" + " " * 50 + "\r", end="", flush=True)

            response_text = api_response.text
            if response_text is None:
                response_text = ""

            token_usage = self.extract_token_usage(api_response)
            print(f"{Colors.CYAN}[UI] Got response of length {len(response_text)}{Colors.ENDC}")

            # Note: AI response will be added to conversation by caller via add_assistant_message()
            await self.save_conversation(quiet=True)
            self.current_user_message = None  # Clear after processing
            return response_text
        except Exception as e:
            error_msg = f"Error generating non-streaming response: {e}"
            print(f"{Colors.FAIL}[UI] {error_msg}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            self.current_user_message = None
            return error_msg

    async def get_streaming_response(self) -> AsyncIterator[str]:
        """Get a streaming response for self.current_user_message (for UI)."""
        print(f"{Colors.CYAN}[UI] Getting streaming response{Colors.ENDC}")
        
        if not self.current_user_message:
            yield "Error: No current user message to process."
            return
        if not self.client:
            yield "Error: Gemini client not initialized."
            return

        # current_user_message is already added to conversation by add_user_message()
        # So, DO NOT add it again here.

        config = types.GenerateContentConfig(**self.params)
        
        # Build chat history from the new conversation_data structure
        chat_history = self.build_chat_history(self.conversation_data, self.active_branch)
        print(f"{Colors.CYAN}[UI] Built chat history with {len(chat_history)} messages for streaming{Colors.ENDC}")

        complete_response_text = ""
        try:
            print(f"\r{Colors.CYAN}AI is thinking (streaming UI)...{Colors.ENDC}", end="", flush=True)
            stream_generator = await self.client.aio.models.generate_content_stream(
                model=self.model, contents=chat_history, config=config)
            print("\r" + " " * 50 + "\r", end="", flush=True)

            async for chunk in stream_generator:
                if hasattr(chunk, 'text') and chunk.text:
                    chunk_text = chunk.text
                    complete_response_text += chunk_text
                    yield chunk_text
                    
            print(f"{Colors.CYAN}[UI] Streaming complete, total length: {len(complete_response_text)}{Colors.ENDC}")
            
            # Note: Full AI response will be added to conversation by caller via add_assistant_message()
            await self.save_conversation(quiet=True)
        except Exception as e:
            error_msg = f"Error generating streaming response: {e}"
            print(f"{Colors.FAIL}[UI] {error_msg}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            yield error_msg
        finally:
            self.current_user_message = None  # Clear after processing

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get history for UI (role and content)."""
        history = []
        
        # Handle new format first
        if hasattr(self, 'conversation_data') and self.conversation_data:
            # Use the active branch to get the correct message chain
            active_branch = self.conversation_data.get("metadata", {}).get("active_branch", "main")
            message_chain = self._build_message_chain(self.conversation_data, active_branch)
            
            messages = self.conversation_data.get("messages", {})
            for msg_id in message_chain:
                msg = messages.get(msg_id, {})
                if msg.get("type") in ["user", "assistant"]:
                    history.append({
                        'role': msg["type"],
                        'content': msg.get("content", ""),
                        'id': msg_id,
                        'model': msg.get("model"),
                        'timestamp': msg.get("timestamp")
                    })
        
        # Fallback to old format
        elif hasattr(self, 'conversation_history') and self.conversation_history:
            for item in self.conversation_history:
                if item["type"] == "message":
                    history.append({
                        'role': item["content"]["role"],
                        'content': item["content"]["text"]
                    })
        
        return history
