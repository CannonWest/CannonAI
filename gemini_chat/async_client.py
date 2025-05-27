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
        # self.active_branch: str = "main" # Track active branch - managed by conversation_data.metadata.active_branch

        # The base directory is already set by the parent constructor
        self.conversations_dir = self.base_directory
        self.ensure_directories(self.conversations_dir)

    @property
    def active_branch(self) -> str:
        """Get the current active branch from conversation_data."""
        return self.conversation_data.get("metadata", {}).get("active_branch", "main")

    @active_branch.setter
    def active_branch(self, branch_id: str) -> None:
        """Set the current active branch in conversation_data."""
        if "metadata" not in self.conversation_data:
            self.conversation_data["metadata"] = {}
        self.conversation_data["metadata"]["active_branch"] = branch_id

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
        branch_id = message.get("branch_id", "main")  # Default to main if not specified

        # Ensure conversation_data and its nested structures exist
        if not self.conversation_data:
            print(f"{Colors.WARNING}_add_message_to_conversation called with no conversation_data.{Colors.ENDC}")
            # Potentially initialize it here if it's a valid scenario, or raise error
            return

        self.conversation_data.setdefault("messages", {})
        self.conversation_data.setdefault("branches", {})
        self.conversation_data.setdefault("metadata", {})
        self.conversation_data["metadata"].setdefault("active_branch", "main")

        print(f"{Colors.CYAN}Adding message {msg_id[:8]}... to branch '{branch_id}'{Colors.ENDC}")

        # Add message to messages dict
        self.conversation_data["messages"][msg_id] = message

        # Update parent's children list if parent exists
        if parent_id and parent_id in self.conversation_data["messages"]:
            parent = self.conversation_data["messages"][parent_id]
            if "children" not in parent:
                parent["children"] = []
            if msg_id not in parent["children"]:
                parent["children"].append(msg_id)
                print(f"{Colors.CYAN}Updated parent {parent_id[:8]}... children list: {parent['children']}{Colors.ENDC}")

        # Ensure branch exists before updating
        if branch_id not in self.conversation_data["branches"]:
            self.conversation_data["branches"][branch_id] = {
                "created_at": datetime.now().isoformat(),
                "last_message": None,
                "message_count": 0
            }
            print(f"{Colors.CYAN}Created new branch '{branch_id}' in conversation_data.{Colors.ENDC}")

        # Update branch information
        branch_info = self.conversation_data["branches"][branch_id]
        branch_info["last_message"] = msg_id

        # Recalculate message count for the branch
        count = 0
        for m_id, m_data in self.conversation_data["messages"].items():
            if m_data.get("branch_id") == branch_id:
                count += 1
        branch_info["message_count"] = count

        print(f"{Colors.CYAN}Updated branch '{branch_id}' - last_message: {msg_id[:8]}..., count: {branch_info['message_count']}{Colors.ENDC}")

        # Update active leaf in metadata if this message is on the active branch
        if branch_id == self.conversation_data["metadata"].get("active_branch", "main"):
            self.conversation_data["metadata"]["active_leaf"] = msg_id
            print(f"{Colors.CYAN}Updated active leaf to {msg_id[:8]}... on active branch '{branch_id}'{Colors.ENDC}")

    def _get_last_message_id(self, branch_id: Optional[str] = None) -> Optional[str]:
        """Get the ID of the last message in a branch.

        Args:
            branch_id: The branch to check (defaults to active branch)

        Returns:
            The ID of the last message or None
        """
        if not self.conversation_data: return None

        if branch_id is None:
            branch_id = self.conversation_data.get("metadata", {}).get("active_branch", "main")

        branch = self.conversation_data.get("branches", {}).get(branch_id, {})
        return branch.get("last_message")

    def _convert_old_to_new_format(self) -> None:
        """Convert old conversation_history format to new conversation_data format."""
        if not hasattr(self, 'conversation_history') or not self.conversation_history:
            return

        print(f"{Colors.CYAN}Converting old format to new format...{Colors.ENDC}")

        title = "Converted Conversation"
        conversation_id = self.conversation_id or self.generate_conversation_id()

        metadata_item = next((item for item in self.conversation_history if item.get("type") == "metadata"), None)
        if metadata_item:
            metadata_content = metadata_item.get("content", {})
            title = metadata_content.get("title", title)
            self.model = metadata_content.get("model", self.model)
            if "params" in metadata_content:  # Old format stored params in metadata
                self.params = metadata_content["params"]

        self.conversation_data = self.create_metadata_structure(title, conversation_id)
        # Ensure model and params from old metadata are set in the new structure's metadata
        self.conversation_data["metadata"]["model"] = self.model
        self.conversation_data["metadata"]["params"] = self.params.copy()

        prev_message_id = None
        for item in self.conversation_history:
            if item.get("type") == "message":
                content = item.get("content", {})
                role = content.get("role")
                text = content.get("text", "")

                if role in ["user", "assistant", "ai"]:
                    role = "assistant" if role == "ai" else role

                    message_params = self.params if role == "assistant" else {}
                    message_model = self.model if role == "assistant" else None

                    message = self.create_message_structure(
                        role=role,
                        text=text,
                        model=message_model,  # Pass model only for assistant
                        params=message_params,  # Pass params only for assistant
                        parent_id=prev_message_id,
                        branch_id="main"  # Old format only had a single branch
                    )
                    self._add_message_to_conversation(message)  # Use helper to add and update relationships
                    prev_message_id = message["id"]

        # Finalize active_leaf and branch counts after all messages are processed
        if prev_message_id:
            self.conversation_data["metadata"]["active_leaf"] = prev_message_id
            main_branch_messages = [msg for msg_id, msg in self.conversation_data["messages"].items() if msg.get("branch_id") == "main"]
            self.conversation_data["branches"]["main"]["message_count"] = len(main_branch_messages)

        print(f"{Colors.GREEN}Converted {len(self.conversation_data.get('messages', {}))} messages to new format{Colors.ENDC}")

    async def start_new_conversation(self, title: Optional[str] = None, is_web_ui: bool = False) -> None:
        """Start a new conversation asynchronously.

        Args:
            title: Optional title for the conversation. If None, will prompt or generate.
            is_web_ui: Whether this is being called from the web UI.
        """
        print(f"{Colors.CYAN}Starting new conversation...{Colors.ENDC}")
        self.conversation_id = self.generate_conversation_id()

        if title is None and not is_web_ui:
            title = input("Enter a title for this conversation (or leave blank for timestamp): ")

        if not title:
            title = f"Conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.conversation_name = title
        self.conversation_data = self.create_metadata_structure(title, self.conversation_id)
        # Set model and params in metadata for new conversations
        self.conversation_data["metadata"]["model"] = self.model
        self.conversation_data["metadata"]["params"] = self.params.copy()

        self.active_branch = "main"  # Explicitly set active_branch in metadata

        print(f"{Colors.GREEN}Started new conversation: {title}{Colors.ENDC}")
        print(f"{Colors.CYAN}Conversation ID: {self.conversation_id[:8]}...{Colors.ENDC}")
        print(f"{Colors.CYAN}Active branch: {self.active_branch}{Colors.ENDC}")

        await self.save_conversation()

    async def retry_message(self, message_id: str) -> Dict[str, Any]:
        """Retry generating a response for a specific message.
           This creates a new branch for the new response.
        Args:
            message_id: The ID of the assistant message whose parent (user message) will be used for retry.
        Returns:
            Dict with new message data and sibling info.
        """
        print(f"[DEBUG AsyncClient] Retrying based on assistant message: {message_id}")

        if not self.conversation_data or "messages" not in self.conversation_data:
            raise ValueError("No active conversation or messages found")

        messages = self.conversation_data["messages"]
        original_assistant_message = messages.get(message_id)

        if not original_assistant_message:
            raise ValueError(f"Message {message_id} not found")

        if original_assistant_message["type"] != "assistant":
            raise ValueError("Can only retry based on an assistant message to regenerate it.")

        parent_user_message_id = original_assistant_message.get("parent_id")
        if not parent_user_message_id:
            raise ValueError(f"Assistant message {message_id} has no parent to retry from.")

        parent_user_message = messages.get(parent_user_message_id)
        if not parent_user_message or parent_user_message["type"] != "user":
            raise ValueError(f"Parent message {parent_user_message_id} is not a user message.")

        print(f"[DEBUG AsyncClient] Found parent user message: {parent_user_message_id}")
        print(f"[DEBUG AsyncClient] Parent content: {parent_user_message['content'][:50]}...")

        # Build conversation history up to and including the parent user message
        # The history should be from the branch of the parent_user_message
        history_chain_ids = self._build_message_chain(self.conversation_data, parent_user_message.get("branch_id", "main"))

        # Ensure the chain goes up to the parent_user_message_id
        try:
            parent_index_in_chain = history_chain_ids.index(parent_user_message_id)
            api_history_ids = history_chain_ids[:parent_index_in_chain + 1]
        except ValueError:
            # This case should ideally not happen if _build_message_chain is correct and parent is on the branch
            print(f"{Colors.WARNING}Parent message {parent_user_message_id} not found in its own branch chain. Building history up to it manually.{Colors.ENDC}")
            # Fallback: trace back from parent_user_message_id
            temp_chain = []
            curr_id = parent_user_message_id
            while curr_id and curr_id in messages:
                temp_chain.append(curr_id)
                curr_id = messages[curr_id].get("parent_id")
            api_history_ids = temp_chain[::-1]

        chat_history_for_api = []
        for msg_id_in_hist in api_history_ids:
            msg_hist = messages[msg_id_in_hist]
            api_role = "user" if msg_hist["type"] == "user" else "model"
            chat_history_for_api.append(types.Content(
                role=api_role,
                parts=[types.Part.from_text(text=msg_hist["content"])]
            ))

        print(f"[DEBUG AsyncClient] Built API history with {len(chat_history_for_api)} messages for retry.")

        try:
            # Use current client model and params for retry
            current_model = self.conversation_data.get("metadata", {}).get("model", self.model)
            current_params = self.conversation_data.get("metadata", {}).get("params", self.params)

            api_response = await self.client.aio.models.generate_content(
                model=current_model,
                contents=chat_history_for_api,
                config=types.GenerateContentConfig(**current_params)
            )

            response_text = api_response.text or ""
            token_usage = self.extract_token_usage(api_response)
            print(f"[DEBUG AsyncClient] Got new response for retry: {response_text[:50]}...")

            # Create a new branch ID for this retried response
            new_branch_id = f"branch-{uuid.uuid4().hex[:8]}"
            print(f"[DEBUG AsyncClient] New response will be on branch: {new_branch_id}")

            new_assistant_message = self.create_message_structure(
                role="assistant",
                text=response_text,
                model=current_model,
                params=current_params,
                token_usage=token_usage,
                parent_id=parent_user_message_id,  # Child of the same user message
                branch_id=new_branch_id
            )

            self._add_message_to_conversation(new_assistant_message)  # This updates parent's children too

            # Update metadata
            self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            self.active_branch = new_branch_id  # Set the new branch as active
            self.conversation_data["metadata"]["active_leaf"] = new_assistant_message["id"]

            print(f"[DEBUG AsyncClient] Created new assistant message {new_assistant_message['id']} on branch {new_branch_id}")

            # Sibling info is relative to the parent_user_message
            siblings_ids = messages[parent_user_message_id].get("children", [])
            new_message_index = siblings_ids.index(new_assistant_message["id"]) if new_assistant_message["id"] in siblings_ids else -1

            return {
                "message": new_assistant_message,
                "sibling_index": new_message_index,
                "total_siblings": len(siblings_ids)
            }

        except Exception as e:
            print(f"{Colors.FAIL}Error during retry generation: {e}{Colors.ENDC}")
            raise

    async def get_message_siblings(self, message_id: str) -> Dict[str, Any]:
        """Get sibling messages (alternative responses to same parent user message).

        Args:
            message_id: The ID of an assistant message to find siblings for.
                        If a user message ID is passed, it will find its children.
        Returns:
            Dict with sibling information.
        """
        print(f"[DEBUG AsyncClient] Getting siblings for message: {message_id}")

        if not self.conversation_data or "messages" not in self.conversation_data:
            raise ValueError("No active conversation or messages found")

        messages = self.conversation_data["messages"]
        target_message = messages.get(message_id)

        if not target_message:
            raise ValueError(f"Message {message_id} not found")

        parent_id_for_siblings = None
        if target_message["type"] == "assistant":
            parent_id_for_siblings = target_message.get("parent_id")
        elif target_message["type"] == "user":  # If user asks for siblings of a user message, show its direct children
            parent_id_for_siblings = message_id

        if not parent_id_for_siblings:  # e.g. root user message if it was passed, or assistant message with no parent
            return {"siblings": [message_id] if target_message["type"] == "assistant" else messages.get(message_id, {}).get("children", []),
                    "current_index": 0,
                    "total": 1 if target_message["type"] == "assistant" else len(messages.get(message_id, {}).get("children", []))}

        parent_message = messages.get(parent_id_for_siblings)
        if not parent_message:
            raise ValueError(f"Parent message {parent_id_for_siblings} not found for sibling search")

        # Siblings are children of the parent_id_for_siblings
        sibling_ids = parent_message.get("children", [])

        current_message_is_sibling = message_id in sibling_ids
        current_index = sibling_ids.index(message_id) if current_message_is_sibling else -1

        # If the target_message was a user message, its "siblings" are its children.
        # In this case, there isn't a "current_index" in the same sense.
        # For now, let's assume message_id is an assistant message if we want a meaningful current_index among its peers.
        if target_message["type"] == "user":
            current_index = -1  # Or perhaps 0 if we always show the first child? This needs clarification.

        print(f"[DEBUG AsyncClient] Found {len(sibling_ids)} siblings for parent {parent_id_for_siblings}. Current message {message_id} index: {current_index}")

        return {
            "siblings": sibling_ids,
            "current_index": current_index,
            "total": len(sibling_ids),
            "parent_id": parent_id_for_siblings if target_message["type"] == "assistant" else None
        }

    async def switch_to_sibling(self, message_id: str, direction: str) -> Dict[str, Any]:
        """Switch the active_leaf to a sibling message.
           If direction is 'none', it activates the branch of message_id.
        Args:
            message_id: Current assistant message ID.
            direction: 'prev', 'next', or 'none'.
        Returns:
            Dict with new active message info.
        """
        print(f"[DEBUG AsyncClient] Switching {direction} from message: {message_id}")

        if not self.conversation_data or "messages" not in self.conversation_data:
            raise ValueError("No active conversation or messages found")

        messages = self.conversation_data["messages"]
        current_message = messages.get(message_id)

        if not current_message:
            raise ValueError(f"Message {message_id} not found")

        new_active_message_id = message_id
        new_active_message = current_message
        sibling_ids = []
        current_index_in_siblings = -1
        total_sibs = 1

        if direction == "none":
            # Activate the branch of the given message_id
            self.active_branch = current_message.get("branch_id", "main")
            self.conversation_data["metadata"]["active_leaf"] = message_id

            # Get sibling info for the response
            parent_id = current_message.get("parent_id")
            if parent_id and parent_id in messages:
                parent_message = messages[parent_id]
                sibling_ids = parent_message.get("children", [])
                if message_id in sibling_ids:
                    current_index_in_siblings = sibling_ids.index(message_id)
                total_sibs = len(sibling_ids)
            else:  # Root message or message with no parent in dict
                sibling_ids = [message_id]
                current_index_in_siblings = 0

            print(f"[DEBUG AsyncClient] Activated branch '{self.active_branch}' with leaf '{message_id}'")

        elif current_message["type"] == "assistant":
            parent_id = current_message.get("parent_id")
            if not parent_id or parent_id not in messages:
                raise ValueError("Cannot navigate siblings for a message with no parent or parent not found.")

            parent_message = messages[parent_id]
            sibling_ids = parent_message.get("children", [])
            total_sibs = len(sibling_ids)

            if not sibling_ids or message_id not in sibling_ids:
                raise ValueError("Message has no siblings or is not in its parent's children list.")

            current_index_in_siblings = sibling_ids.index(message_id)

            if direction == "prev":
                new_index = (current_index_in_siblings - 1 + total_sibs) % total_sibs
            elif direction == "next":
                new_index = (current_index_in_siblings + 1) % total_sibs
            else:  # Should not happen if direction is 'none' was handled
                new_index = current_index_in_siblings

            new_active_message_id = sibling_ids[new_index]
            new_active_message = messages[new_active_message_id]

            self.active_branch = new_active_message.get("branch_id", "main")
            self.conversation_data["metadata"]["active_leaf"] = new_active_message_id
            current_index_in_siblings = new_index
            print(f"[DEBUG AsyncClient] Switched to sibling {new_active_message_id} (index {new_index}) on branch '{self.active_branch}'")
        else:
            # Cannot navigate prev/next for a user message in this context
            print(f"{Colors.WARNING}Cannot perform prev/next navigation on a user message. Activating its branch instead.{Colors.ENDC}")
            self.active_branch = current_message.get("branch_id", "main")
            self.conversation_data["metadata"]["active_leaf"] = message_id
            # Sibling info for a user message might be its children
            sibling_ids = current_message.get("children", [])
            total_sibs = len(sibling_ids)
            current_index_in_siblings = -1  # No current index among children

        self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()

        return {
            "message": new_active_message,
            "sibling_index": current_index_in_siblings,
            "total_siblings": total_sibs
        }

    async def get_conversation_tree(self) -> Dict[str, Any]:
        """Get the full conversation tree structure.

        Returns:
            Dict representing the conversation tree
        """
        print("[DEBUG AsyncClient] Building conversation tree")

        if not self.conversation_data or "messages" not in self.conversation_data:
            return {"nodes": [], "edges": [], "metadata": self.conversation_data.get("metadata", {})}

        messages = self.conversation_data["messages"]
        nodes = []
        edges = []
        active_leaf_id = self.conversation_data.get("metadata", {}).get("active_leaf")

        for msg_id, msg_data in messages.items():
            node = {
                "id": msg_id,
                "type": msg_data["type"],
                "content_preview": (msg_data["content"][:50] + "...") if len(msg_data["content"]) > 50 else msg_data["content"],
                "timestamp": msg_data["timestamp"],
                "branch_id": msg_data.get("branch_id", "main"),
                "model": msg_data.get("model"),
                "is_active_leaf": msg_id == active_leaf_id
            }
            nodes.append(node)

            for child_id in msg_data.get("children", []):
                if child_id in messages:  # Ensure child exists
                    edges.append({"from": msg_id, "to": child_id})
                else:
                    print(f"{Colors.WARNING}Child ID {child_id} listed in parent {msg_id} but not found in messages dict.{Colors.ENDC}")

        print(f"[DEBUG AsyncClient] Built tree with {len(nodes)} nodes and {len(edges)} edges")

        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": self.conversation_data.get("metadata", {})
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

        title = self.conversation_data.get("metadata", {}).get("title", "Untitled")
        filename = self.format_filename(title, self.conversation_id)
        filepath = self.conversations_dir / filename

        if "metadata" in self.conversation_data:
            self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            self.conversation_data["metadata"]["model"] = self.model  # Ensure current model is saved
            self.conversation_data["metadata"]["params"] = self.params.copy()  # Ensure current params are saved

        if not quiet:
            print(f"{Colors.CYAN}Saving conversation structure v{self.VERSION}...{Colors.ENDC}")

        try:
            def save_json_sync():
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.conversation_data, f, indent=2, ensure_ascii=False)

            await asyncio.to_thread(save_json_sync)

            if not quiet:
                total_messages = len(self.conversation_data.get("messages", {}))
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

        # Ensure conversation is initialized
        if not self.conversation_data:
            await self.start_new_conversation(is_web_ui=self.is_web_ui)

        try:
            print(f"\n{Colors.CYAN}=== Processing Message ==={Colors.ENDC}")
            current_active_branch = self.active_branch
            print(f"{Colors.CYAN}Active branch: {current_active_branch}{Colors.ENDC}")

            response_text = ""
            token_usage = {}

            parent_id = self._get_last_message_id(current_active_branch)
            print(f"{Colors.CYAN}Parent message: {parent_id[:8] if parent_id else 'None (first message)'}...{Colors.ENDC}")

            user_msg_obj = self.create_message_structure(
                role="user", text=message, model=None, params={},  # User messages don't store model/params
                parent_id=parent_id, branch_id=current_active_branch
            )
            self._add_message_to_conversation(user_msg_obj)
            user_message_id = user_msg_obj["id"]
            print(f"{Colors.BLUE}User message ID: {user_message_id[:8]}...{Colors.ENDC}")

            # Use model and params from conversation metadata or client defaults
            current_model = self.conversation_data.get("metadata", {}).get("model", self.model)
            current_params = self.conversation_data.get("metadata", {}).get("params", self.params)

            config = types.GenerateContentConfig(
                temperature=current_params["temperature"],
                max_output_tokens=current_params["max_output_tokens"],
                top_p=current_params["top_p"],
                top_k=current_params["top_k"]
            )

            chat_history = self.build_chat_history(self.conversation_data, current_active_branch)
            print(f"{Colors.CYAN}Chat history length: {len(chat_history)} messages{Colors.ENDC}")

            if self.use_streaming:
                print(f"\r{Colors.CYAN}AI is thinking... (streaming mode){Colors.ENDC}", end="", flush=True)
                print("\r" + " " * 50 + "\r", end="", flush=True)
                print(f"{Colors.GREEN}AI: {Colors.ENDC}", end="", flush=True)

                stream_generator = await self.client.aio.models.generate_content_stream(
                    model=current_model, contents=chat_history, config=config
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
                    model=current_model, contents=chat_history, config=config
                )
                print("\r" + " " * 50 + "\r", end="", flush=True)
                response_text = api_response.text or ""
                print(f"\n{Colors.GREEN}AI: {Colors.ENDC}{response_text}")
                token_usage = self.extract_token_usage(api_response)

            ai_msg_obj = self.create_message_structure(
                role="assistant", text=response_text, model=current_model, params=current_params,
                token_usage=token_usage, parent_id=user_message_id, branch_id=current_active_branch
            )
            self._add_message_to_conversation(ai_msg_obj)
            print(f"{Colors.GREEN}AI message ID: {ai_msg_obj['id'][:8]}...{Colors.ENDC}")

            print(f"{Colors.CYAN}Auto-saving conversation...{Colors.ENDC}")
            await self.save_conversation(quiet=True)
            return response_text

        except Exception as e:
            print(f"{Colors.FAIL}Error generating response: {e}{Colors.ENDC}")
            # Attempt to get user_message_id if it was set
            error_parent_id = locals().get('user_message_id', self._get_last_message_id(self.active_branch))
            error_message = self.create_message_structure(
                role="assistant", text=f"Error: {e}", model=self.model, params=self.params,
                parent_id=error_parent_id, branch_id=self.active_branch
            )
            if self.conversation_data:  # Only add if conversation_data is initialized
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

        models_from_api = []
        try:
            print(f"Fetching available models from Google AI API...")
            model_list_response = await self.client.aio.models.list()

            if model_list_response:
                for model_obj_api in model_list_response:
                    if hasattr(model_obj_api, 'supported_actions') and "generateContent" in model_obj_api.supported_actions:
                        model_info_api = {
                            "name": model_obj_api.name,
                            "display_name": getattr(model_obj_api, 'display_name', model_obj_api.name),
                            "input_token_limit": getattr(model_obj_api, 'input_token_limit', "Unknown"),
                            "output_token_limit": getattr(model_obj_api, 'output_token_limit', "Unknown")
                        }
                        models_from_api.append(model_info_api)
                        print(f"Found model via API: {model_info_api['name']}")
        except Exception as e:
            print(f"{Colors.FAIL}Error retrieving models from API: {e}{Colors.ENDC}")
            print(f"{Colors.WARNING}Falling back to default model list.{Colors.ENDC}")

        # Default models list (always include these as a fallback or supplement)
        default_models_list = [
            {"name": "models/gemini-2.0-flash", "display_name": "Gemini 2.0 Flash", "input_token_limit": 32768, "output_token_limit": 8192},
            {"name": "models/gemini-2.0-pro", "display_name": "Gemini 2.0 Pro", "input_token_limit": 32768, "output_token_limit": 8192},
            {"name": "models/gemini-2.5-flash-preview-05-20", "display_name": "Gemini 2.5 Flash Preview (May 2025)", "input_token_limit": "Unknown", "output_token_limit": "Unknown"},  # Assuming unknown for previews
            {"name": "models/gemini-2.5-pro-preview-05-06", "display_name": "Gemini 2.5 Pro Preview (May 2025)", "input_token_limit": "Unknown", "output_token_limit": "Unknown"}
        ]

        # Combine API models with defaults, prioritizing API if names match
        final_models = {model_data["name"]: model_data for model_data in default_models_list}
        for api_model_data in models_from_api:
            final_models[api_model_data["name"]] = api_model_data  # API version overrides default if name matches

        return list(final_models.values())

    async def display_models(self) -> None:
        """Display available models in a formatted table asynchronously."""
        models_to_display = await self.get_available_models()

        if not models_to_display:
            print(f"{Colors.WARNING}No models available or error retrieving models.{Colors.ENDC}")
            return

        headers = ["#", "Name", "Display Name", "Input Tokens", "Output Tokens"]
        table_data = []

        for i, model_info_disp in enumerate(models_to_display, 1):
            row = [
                i,
                model_info_disp["name"],
                model_info_disp["display_name"],
                model_info_disp["input_token_limit"],
                model_info_disp["output_token_limit"]
            ]
            table_data.append(row)

        print(tabulate(table_data, headers=headers, tablefmt="pretty"))

    async def select_model(self) -> None:
        """Let user select a model from available options asynchronously."""
        models_for_selection = await self.get_available_models()

        if not models_for_selection:
            print(f"{Colors.WARNING}No models available to select.{Colors.ENDC}")
            return

        await self.display_models()

        try:
            selection_input = int(input("\nEnter model number to select: "))
            if 1 <= selection_input <= len(models_for_selection):
                selected_model_name = models_for_selection[selection_input - 1]["name"]
                self.model = selected_model_name
                if self.conversation_data and "metadata" in self.conversation_data:  # Update active conversation metadata
                    self.conversation_data["metadata"]["model"] = self.model
                print(f"{Colors.GREEN}Selected model: {self.model}{Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}Invalid selection.{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.FAIL}Please enter a valid number.{Colors.ENDC}")

    async def customize_params(self) -> None:
        """Allow user to customize generation parameters asynchronously."""
        current_params_to_show = self.params
        if self.conversation_data and "metadata" in self.conversation_data and "params" in self.conversation_data["metadata"]:
            current_params_to_show = self.conversation_data["metadata"]["params"]  # Show params of current conversation if available

        print(f"\n{Colors.HEADER}Current Parameters ({'Conversation' if current_params_to_show is not self.params else 'Default'}):{Colors.ENDC}")
        for key, value in current_params_to_show.items():
            print(f"  {key}: {value}")

        print("\nEnter new values (or leave blank to keep current values):")

        new_params = current_params_to_show.copy()  # Edit a copy

        try:
            temp_input = input(f"Temperature (0.0-2.0) [{new_params['temperature']}]: ")
            if temp_input: new_params["temperature"] = float(temp_input)

            max_tokens_input = input(f"Max output tokens [{new_params['max_output_tokens']}]: ")
            if max_tokens_input: new_params["max_output_tokens"] = int(max_tokens_input)

            top_p_input = input(f"Top-p (0.0-1.0) [{new_params['top_p']}]: ")
            if top_p_input: new_params["top_p"] = float(top_p_input)

            top_k_input = input(f"Top-k (positive integer) [{new_params['top_k']}]: ")
            if top_k_input: new_params["top_k"] = int(top_k_input)

            self.params = new_params  # Update client default params
            if self.conversation_data and "metadata" in self.conversation_data:  # Update active conversation metadata
                self.conversation_data["metadata"]["params"] = new_params

            print(f"{Colors.GREEN}Parameters updated successfully.{Colors.ENDC}")

        except ValueError as e:
            print(f"{Colors.FAIL}Invalid input: {e}. Parameters not updated.{Colors.ENDC}")

    async def list_conversations(self) -> List[Dict[str, Any]]:
        """List available conversation files asynchronously.

        Returns:
            List of conversation information dictionaries
        """

        def read_conversation_files_sync():
            conv_list = []
            for file_path_item in self.conversations_dir.glob("*.json"):
                try:
                    with open(file_path_item, 'r', encoding='utf-8') as f_item:
                        data_item = json.load(f_item)

                    metadata_content = data_item.get("metadata", {})  # New format
                    if not metadata_content and "history" in data_item:  # Old format fallback
                        for hist_item in data_item.get("history", []):
                            if hist_item.get("type") == "metadata":
                                metadata_content = hist_item.get("content", {})
                                break

                    message_count = len(data_item.get("messages", {}))  # New format
                    if message_count == 0 and "history" in data_item:  # Old format fallback
                        message_count = sum(1 for hist_item in data_item.get("history", []) if hist_item.get("type") == "message")

                    conv_list.append({
                        "filename": file_path_item.name,
                        "path": file_path_item,
                        "title": metadata_content.get("title", "Untitled"),
                        "model": metadata_content.get("model", "Unknown"),
                        "created_at": metadata_content.get("created_at", "Unknown"),
                        "message_count": message_count,
                        "conversation_id": data_item.get("conversation_id")
                    })
                except Exception as e_read:
                    print(f"{Colors.WARNING}Error reading {file_path_item.name}: {e_read}{Colors.ENDC}")
            return conv_list

        return await asyncio.to_thread(read_conversation_files_sync)

    async def display_conversations(self) -> List[Dict[str, Any]]:
        """Display available conversations in a formatted table asynchronously.

        Returns:
            List of conversation information dictionaries
        """
        conversations_to_disp = await self.list_conversations()

        if not conversations_to_disp:
            print(f"{Colors.WARNING}No saved conversations found.{Colors.ENDC}")
            return conversations_to_disp

        headers = ["#", "Title", "Model", "Messages", "Created", "Filepath"]
        table_data_disp = []

        for i, conv_item_disp in enumerate(conversations_to_disp, 1):
            created_at_val = conv_item_disp["created_at"]
            if created_at_val != "Unknown":
                try:
                    dt_obj = datetime.fromisoformat(created_at_val.replace("Z", "+00:00"))  # Handle Z for UTC
                    created_at_val = dt_obj.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    pass  # Keep original if parsing fails

            row_data = [
                i, conv_item_disp["title"], conv_item_disp["model"],
                conv_item_disp["message_count"], created_at_val, str(conv_item_disp["path"])
            ]
            table_data_disp.append(row_data)

        print(tabulate(table_data_disp, headers=headers, tablefmt="pretty"))
        return conversations_to_disp

    async def load_conversation(self, conversation_name_or_index: Optional[str] = None) -> None:
        """Load a saved conversation asynchronously.

        Args:
            conversation_name_or_index: Optional name or index of conversation to load directly.
        """
        all_conversations = await self.list_conversations()

        if not all_conversations:
            print(f"{Colors.WARNING}No saved conversations found.{Colors.ENDC}")
            return

        selected_conv_data = None
        if conversation_name_or_index:
            # Try matching by title (case-insensitive)
            selected_conv_data = next((c for c in all_conversations if c["title"].lower() == conversation_name_or_index.lower()), None)
            if not selected_conv_data:
                # Try matching by index
                try:
                    idx_select = int(conversation_name_or_index) - 1
                    if 0 <= idx_select < len(all_conversations):
                        selected_conv_data = all_conversations[idx_select]
                except ValueError:
                    pass  # Not a number

            if not selected_conv_data:
                print(f"{Colors.FAIL}Conversation '{conversation_name_or_index}' not found.{Colors.ENDC}")
                await self.display_conversations()  # Show list if direct load fails
                return
        else:  # Interactive selection
            await self.display_conversations()
            try:
                selection_num = int(input("\nEnter conversation number to load: "))
                if 1 <= selection_num <= len(all_conversations):
                    selected_conv_data = all_conversations[selection_num - 1]
                else:
                    print(f"{Colors.FAIL}Invalid selection.{Colors.ENDC}")
                    return
            except ValueError:
                print(f"{Colors.FAIL}Please enter a valid number.{Colors.ENDC}")
                return
            except Exception as e_select:
                print(f"{Colors.FAIL}Error during selection: {e_select}{Colors.ENDC}")
                return

        if not selected_conv_data: return  # Should be caught above, but as a safeguard

        try:
            def read_json_file_sync(path):
                with open(path, 'r', encoding='utf-8') as f_sync:
                    return json.load(f_sync)

            loaded_data = await asyncio.to_thread(read_json_file_sync, selected_conv_data["path"])

            self.conversation_id = loaded_data.get("conversation_id")

            if "messages" in loaded_data and "metadata" in loaded_data:  # New format
                self.conversation_data = loaded_data
                meta = self.conversation_data.get("metadata", {})
                self.model = meta.get("model", self.model)  # Update client's current model
                self.params = meta.get("params", self.params).copy()  # Update client's current params
                self.conversation_name = meta.get("title", "Untitled")
                self.active_branch = meta.get("active_branch", "main")
                print(f"{Colors.CYAN}Loaded new format conversation: {self.conversation_name}{Colors.ENDC}")
            else:  # Old format
                self.conversation_history = loaded_data.get("history", [])
                self._convert_old_to_new_format()  # This will populate self.conversation_data
                # model, params, and conversation_name are set within _convert_old_to_new_format
                print(f"{Colors.CYAN}Converted and loaded old format conversation: {self.conversation_name}{Colors.ENDC}")

            await self.display_conversation_history()
        except Exception as e_load_data:
            print(f"{Colors.FAIL}Error loading conversation data: {e_load_data}{Colors.ENDC}")
            import traceback
            traceback.print_exc()

    async def display_conversation_history(self) -> None:
        """Display the current conversation history asynchronously."""
        if not self.conversation_data or "messages" not in self.conversation_data or not self.conversation_data["messages"]:
            print(f"{Colors.WARNING}No conversation history to display.{Colors.ENDC}")
            return

        print(f"\n{Colors.HEADER}Conversation History:{Colors.ENDC}")
        metadata_disp = self.conversation_data.get("metadata", {})
        title_disp = metadata_disp.get("title", "Untitled")
        model_disp = metadata_disp.get("model", self.model)  # Use conversation's model

        print(f"{Colors.BOLD}Title: {title_disp}{Colors.ENDC}")
        print(f"{Colors.BOLD}Model: {model_disp}{Colors.ENDC}")
        print(f"{Colors.BOLD}Active Branch: {metadata_disp.get('active_branch', 'main')}{Colors.ENDC}\n")

        active_branch_id = metadata_disp.get("active_branch", "main")
        message_chain_ids = self._build_message_chain(self.conversation_data, active_branch_id)

        messages_dict = self.conversation_data["messages"]
        for msg_id_chain in message_chain_ids:
            msg_data_chain = messages_dict.get(msg_id_chain, {})
            if msg_data_chain.get("type") in ["user", "assistant"]:
                role_disp = msg_data_chain["type"]
                text_disp = msg_data_chain.get("content", "")
                timestamp_disp = msg_data_chain.get("timestamp", "")
                try:
                    dt_disp = datetime.fromisoformat(timestamp_disp.replace("Z", "+00:00"))
                    time_str_disp = dt_disp.strftime("%H:%M:%S")
                except:
                    time_str_disp = "Unknown Time"

                if role_disp == "user":
                    print(f"{Colors.BLUE}User ({time_str_disp}): {Colors.ENDC}{text_disp}")
                else:
                    print(f"{Colors.GREEN}AI ({time_str_disp}): {Colors.ENDC}{text_disp}")
                print("")

    async def toggle_streaming(self) -> bool:
        """Toggle streaming mode asynchronously.

        Returns:
            Current streaming mode state (True for enabled, False for disabled)
        """
        self.use_streaming = not self.use_streaming
        status_str = "enabled" if self.use_streaming else "disabled"
        print(f"{Colors.GREEN}Streaming mode {status_str}.{Colors.ENDC}")
        return self.use_streaming

    # --- Methods for UI interaction ---
    def add_user_message(self, message: str) -> None:
        """Add a user message to conversation (called by UI message handler)."""
        print(f"{Colors.CYAN}[UI] Adding user message to conversation{Colors.ENDC}")
        self.current_user_message = message

        if not self.conversation_data:  # Should be initialized by UI flow or load
            print(f"{Colors.WARNING}[UI] No active conversation_data, this might lead to issues.{Colors.ENDC}")
            # For safety, let's ensure it's an empty dict if not present
            self.conversation_id = self.generate_conversation_id()
            self.conversation_data = self.create_metadata_structure(f"UI_Conv_{self.conversation_id[:4]}", self.conversation_id)
            self.conversation_data["metadata"]["model"] = self.model
            self.conversation_data["metadata"]["params"] = self.params.copy()
            self.active_branch = "main"

        parent_id_ui = self._get_last_message_id(self.active_branch)

        user_msg_struct = self.create_message_structure(
            role="user", text=message, model=None, params={},
            parent_id=parent_id_ui, branch_id=self.active_branch
        )
        self._add_message_to_conversation(user_msg_struct)
        self.current_user_message_id = user_msg_struct["id"]
        print(f"{Colors.BLUE}[UI] User message added with ID: {user_msg_struct['id'][:8]}... on branch {self.active_branch}{Colors.ENDC}")

    def add_assistant_message(self, message: str, token_usage: Optional[Dict[str, Any]] = None) -> None:
        """Add an assistant message to conversation (called by UI message handler after response)."""
        print(f"{Colors.CYAN}[UI] Adding assistant message to conversation{Colors.ENDC}")

        text_to_add_ui = message if message is not None else ""
        parent_id_for_ai = self.current_user_message_id  # This should be the ID of the user message it's responding to

        if not parent_id_for_ai:  # Fallback if current_user_message_id wasn't set
            parent_id_for_ai = self._get_last_message_id(self.active_branch)
            print(f"{Colors.WARNING}[UI] current_user_message_id was not set, using last message in active branch as parent: {parent_id_for_ai}{Colors.ENDC}")

        # Use model and params from conversation metadata
        ai_model = self.conversation_data.get("metadata", {}).get("model", self.model)
        ai_params = self.conversation_data.get("metadata", {}).get("params", self.params)

        ai_msg_struct = self.create_message_structure(
            role="assistant", text=text_to_add_ui, model=ai_model, params=ai_params,
            token_usage=token_usage, parent_id=parent_id_for_ai, branch_id=self.active_branch
        )
        self._add_message_to_conversation(ai_msg_struct)
        print(f"{Colors.GREEN}[UI] Assistant message added with ID: {ai_msg_struct['id'][:8]}... on branch {self.active_branch}{Colors.ENDC}")
        self.current_user_message_id = None  # Clear after assistant responds

    async def get_response(self) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Get a non-streaming response for self.current_user_message (for UI).
           Returns response text and token usage.
        """
        print(f"{Colors.CYAN}[UI] Getting non-streaming response{Colors.ENDC}")

        if not self.current_user_message:
            return "Error: No current user message to process.", None
        if not self.client:
            return "Error: Gemini client not initialized.", None
        if not self.conversation_data:
            return "Error: Conversation data not initialized.", None

        # Use model and params from conversation metadata
        current_model_ui = self.conversation_data.get("metadata", {}).get("model", self.model)
        current_params_ui = self.conversation_data.get("metadata", {}).get("params", self.params)
        config_ui = types.GenerateContentConfig(**current_params_ui)

        chat_history_ui = self.build_chat_history(self.conversation_data, self.active_branch)
        print(f"{Colors.CYAN}[UI] Built chat history with {len(chat_history_ui)} messages for non-streaming response on branch {self.active_branch}{Colors.ENDC}")

        try:
            print(f"\r{Colors.CYAN}AI is thinking (non-streaming UI)...{Colors.ENDC}", end="", flush=True)
            api_response_obj = await self.client.aio.models.generate_content(
                model=current_model_ui, contents=chat_history_ui, config=config_ui)
            print("\r" + " " * 50 + "\r", end="", flush=True)

            response_text_ui = api_response_obj.text or ""
            token_usage_ui = self.extract_token_usage(api_response_obj)
            print(f"{Colors.CYAN}[UI] Got response of length {len(response_text_ui)}{Colors.ENDC}")

            # Caller (api_handlers) will call add_assistant_message and save_conversation
            # self.current_user_message = None # Clear after processing by caller
            return response_text_ui, token_usage_ui
        except Exception as e_resp:
            error_msg_resp = f"Error generating non-streaming response: {e_resp}"
            print(f"{Colors.FAIL}[UI] {error_msg_resp}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            # self.current_user_message = None # Clear after processing by caller
            return error_msg_resp, None

    async def get_streaming_response(self) -> AsyncIterator[Dict[str, Any]]:
        """Get a streaming response for self.current_user_message (for UI).
           Yields dictionaries: {'chunk': str} or {'error': str} or
                                {'done': True, 'full_response': str, 'token_usage': dict}
        """
        print(f"{Colors.CYAN}[UI] Getting streaming response{Colors.ENDC}")

        if not self.current_user_message:
            yield {"error": "No current user message to process."}
            return
        if not self.client:
            yield {"error": "Gemini client not initialized."}
            return
        if not self.conversation_data:
            yield {"error": "Conversation data not initialized."}
            return

        # Use model and params from conversation metadata
        stream_model = self.conversation_data.get("metadata", {}).get("model", self.model)
        stream_params = self.conversation_data.get("metadata", {}).get("params", self.params)
        stream_config = types.GenerateContentConfig(**stream_params)

        stream_chat_history = self.build_chat_history(self.conversation_data, self.active_branch)
        print(f"{Colors.CYAN}[UI] Built chat history with {len(stream_chat_history)} messages for streaming on branch {self.active_branch}{Colors.ENDC}")

        complete_response_text_stream = ""
        final_token_usage = {}
        try:
            print(f"\r{Colors.CYAN}AI is thinking (streaming UI)...{Colors.ENDC}", end="", flush=True)
            stream_gen_obj = await self.client.aio.models.generate_content_stream(
                model=stream_model, contents=stream_chat_history, config=stream_config)
            print("\r" + " " * 50 + "\r", end="", flush=True)

            async for chunk_item in stream_gen_obj:
                if hasattr(chunk_item, 'text') and chunk_item.text:
                    chunk_text_item = chunk_item.text
                    complete_response_text_stream += chunk_text_item
                    yield {"chunk": chunk_text_item}
                # Attempt to get usage metadata from the last chunk if available (may not always be)
                if hasattr(chunk_item, 'usage_metadata'):
                    final_token_usage = self.extract_token_usage(chunk_item)

            print(f"{Colors.CYAN}[UI] Streaming complete, total length: {len(complete_response_text_stream)}{Colors.ENDC}")
            yield {"done": True, "full_response": complete_response_text_stream, "token_usage": final_token_usage}
            # Caller (api_handlers) will call add_assistant_message and save_conversation
        except Exception as e_stream:
            error_msg_stream = f"Error generating streaming response: {e_stream}"
            print(f"{Colors.FAIL}[UI] {error_msg_stream}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            yield {"error": error_msg_stream}
        # finally:
        # self.current_user_message = None # Clear after processing by caller

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get history for UI (role, content, id, model, timestamp, parent_id).
           Returns messages from the active branch.
        """
        history_list = []
        if not self.conversation_data or "messages" not in self.conversation_data:
            return history_list

        current_active_branch = self.active_branch
        message_chain_ids_hist = self._build_message_chain(self.conversation_data, current_active_branch)

        messages_dict_hist = self.conversation_data["messages"]
        for msg_id_hist_chain in message_chain_ids_hist:
            msg_data_hist = messages_dict_hist.get(msg_id_hist_chain, {})
            if msg_data_hist.get("type") in ["user", "assistant"]:
                history_list.append({
                    'role': msg_data_hist["type"],
                    'content': msg_data_hist.get("content", ""),
                    'id': msg_id_hist_chain,
                    'model': msg_data_hist.get("model"),  # Will be None for user messages
                    'timestamp': msg_data_hist.get("timestamp"),
                    'parent_id': msg_data_hist.get("parent_id")
                })
        return history_list

