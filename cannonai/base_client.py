#!/usr/bin/env python3
"""
CannonAI Base Client Features - Core utilities for conversation management.

This module provides base classes and shared, provider-agnostic functionality
for file operations, conversation data structuring, and terminal colors.
"""

import json
import os
import platform
# import re # Was unused
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

import asyncio

# Use colorama for cross-platform terminal colors
try:
    from colorama import init, Fore, Back, Style

    init(autoreset=True)
    colorama_available = True
except ImportError:
    print("Warning: colorama package not installed. Terminal colors may not work correctly.")
    print("Please install with: pip install colorama")
    colorama_available = False


# Removed Gemini-specific imports:
# from google import genai
# from google.genai import types

class Colors:
    """
    Terminal colors for better user experience.
    Uses colorama for cross-platform compatibility.
    """
    HEADER = Fore.MAGENTA if colorama_available else '\033[95m'
    BLUE = Fore.BLUE if colorama_available else '\033[94m'
    CYAN = Fore.CYAN if colorama_available else '\033[96m'
    GREEN = Fore.GREEN if colorama_available else '\033[92m'
    WARNING = Fore.YELLOW if colorama_available else '\033[93m'
    FAIL = Fore.RED if colorama_available else '\033[91m'
    ENDC = Style.RESET_ALL if colorama_available else '\033[0m'
    BOLD = Style.BRIGHT if colorama_available else '\033[1m'
    UNDERLINE = '\033[4m'


class BaseClientFeatures:
    """
    Base class providing features for CannonAI clients, focusing on
    conversation structure, file I/O, and general utilities.
    This class is provider-agnostic.
    """

    VERSION = "2.2.0"  # Version indicating base client refactor

    def __init__(self, conversations_dir: Optional[Path] = None):
        """Initialize the base client features.

        Args:
            conversations_dir: Directory to store conversations. If None, uses default.
        """
        if conversations_dir is None:
            current_file_path = Path(__file__).resolve()
            project_root = current_file_path.parent.parent
            self.base_directory = project_root / "cannonai_conversations"
        else:
            self.base_directory = Path(conversations_dir)

        # Default params are now primarily handled by each provider and then layered by AsyncClient.
        # This can be a fallback or not used at all by inheriting clients.
        self._fallback_default_params = {
            "temperature": 0.7,
            "max_output_tokens": 800,
            "top_p": 0.95,
            "top_k": 40
        }
        # The actual client (AsyncClient) will have its own self.params,
        # initialized from its provider and config.

    def ensure_directories(self, base_dir: Optional[Path] = None) -> None:
        """Ensure necessary directories exist."""
        dir_to_ensure = base_dir or self.base_directory
        try:
            dir_to_ensure.mkdir(parents=True, exist_ok=True)
            # print(f"Debug: Ensured directory: {dir_to_ensure}")
        except Exception as e:
            print(f"{Colors.FAIL}Error creating directory {dir_to_ensure}: {e}{Colors.ENDC}")

    def format_filename(self, title: str, conversation_id: str) -> str:
        """Format a filename for a conversation.

        Args:
            title: The conversation title.
            conversation_id: The unique ID for the conversation.

        Returns:
            Formatted filename string.
        """
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
        safe_title = safe_title.replace(" ", "_")
        safe_title = safe_title[:50]  # Truncate long titles
        return f"{safe_title}_{conversation_id[:8]}.json"

    def generate_conversation_id(self) -> str:
        """Generates a unique conversation ID."""
        import uuid  # Local import for this utility method is fine
        return str(uuid.uuid4())

    def create_message_structure(self, role: str, text: str,
                                 model: Optional[str] = None,
                                 params: Optional[Dict[str, Any]] = None,
                                 token_usage: Optional[Dict[str, Any]] = None,
                                 message_id: Optional[str] = None,
                                 parent_id: Optional[str] = None,
                                 branch_id: str = "main") -> Dict[str, Any]:
        """Create a standard message structure for conversation history.

        Args:
            role: "user" or "assistant".
            text: Message content.
            model: Model name used for this message (typically for assistant messages).
            params: Generation parameters used (typically for assistant messages).
            token_usage: Token usage metrics.
            message_id: Unique ID for this message. Auto-generated if None.
            parent_id: ID of the parent message in the conversation tree.
            branch_id: ID of the branch this message belongs to.

        Returns:
            Message structure dictionary.
        """
        import uuid  # Local import

        if message_id is None:
            message_id = str(uuid.uuid4())

        message_dict = {
            "id": message_id,
            "parent_id": parent_id,
            "branch_id": branch_id,
            "type": role,
            "content": text,
            "timestamp": datetime.now().isoformat(),
            "children": []
        }

        if role == "assistant":
            # Store AI-specific metadata if provided
            if model: message_dict["model"] = model
            if params: message_dict["params"] = params.copy()
            if token_usage: message_dict["token_usage"] = token_usage

        return message_dict

    def create_metadata_structure(self, title: str, conversation_id: str) -> Dict[str, Any]:
        """Create metadata structure for a new conversation.

        Args:
            title: Conversation title.
            conversation_id: Unique conversation identifier.

        Returns:
            Metadata structure dictionary for a new conversation.
        """
        return {
            "conversation_id": conversation_id,
            "version": self.VERSION,
            "metadata": {
                "title": title,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "app_info": "CannonAI Application",
                "platform": platform.system(),
                "active_branch": "main",
                "active_leaf": None,
                # Provider, model, params will be filled by the specific client instance
            },
            "messages": {},
            "branches": {
                "main": {
                    "created_at": datetime.now().isoformat(),
                    "last_message": None,
                    "message_count": 0
                }
            }
        }

    def _build_message_chain(self, conversation_data: Dict[str, Any], branch_id: Optional[str] = None) -> List[str]:
        """
        Builds an ordered list of message IDs for a specific branch, from root to leaf.
        """
        if not conversation_data or "messages" not in conversation_data:
            return []

        messages = conversation_data.get("messages", {})
        if not messages:
            return []

        actual_branch_id = branch_id or conversation_data.get("metadata", {}).get("active_branch", "main")
        branch_info = conversation_data.get("branches", {}).get(actual_branch_id, {})
        leaf_id = branch_info.get("last_message")

        if not leaf_id or leaf_id not in messages:
            return []

        chain = []
        current_id = leaf_id

        visited_ids_for_chain = set()  # To prevent infinite loops in malformed data

        while current_id and current_id not in visited_ids_for_chain:
            visited_ids_for_chain.add(current_id)
            chain.append(current_id)
            current_msg_data = messages.get(current_id, {})
            current_id = current_msg_data.get("parent_id")
            # Basic check for branch consistency if needed, though current structure assumes
            # parent_id links define the branch structure correctly.
            # if current_id and messages.get(current_id, {}).get("branch_id") != actual_branch_id:
            #     break # Stop if parent is on a different branch (should not happen with current model)

        chain.reverse()
        return chain

    def _add_message_to_conversation(self, conversation_data: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Adds a message to the provided conversation_data structure."""
        if not conversation_data:
            print(f"{Colors.WARNING}Attempted to add message but conversation_data is not initialized/provided.{Colors.ENDC}")
            return

        msg_id = message["id"]
        parent_id = message.get("parent_id")
        branch_id = message.get("branch_id", "main")

        conversation_data.setdefault("messages", {})
        conversation_data.setdefault("branches", {})
        conversation_data.setdefault("metadata", {}).setdefault("active_branch", "main")

        conversation_data["messages"][msg_id] = message

        if parent_id and parent_id in conversation_data["messages"]:
            parent_message_data = conversation_data["messages"][parent_id]
            parent_message_data.setdefault("children", [])
            if msg_id not in parent_message_data["children"]:
                parent_message_data["children"].append(msg_id)

        if branch_id not in conversation_data["branches"]:
            conversation_data["branches"][branch_id] = {
                "created_at": message.get("timestamp", datetime.now().isoformat()),
                "last_message": None, "message_count": 0
            }
        branch_info = conversation_data["branches"][branch_id]
        branch_info["last_message"] = msg_id

        # Recalculate message count for the branch
        count = 0
        for m_data_id, m_data_content in conversation_data["messages"].items():
            if m_data_content.get("branch_id") == branch_id:
                count += 1
        branch_info["message_count"] = count
        # branch_info["message_count"] = sum(1 for m_data in conversation_data["messages"].values() if m_data.get("branch_id") == branch_id)

        # If this message is on the active branch, update the active_leaf in metadata
        if branch_id == conversation_data.get("metadata", {}).get("active_branch"):
            conversation_data["metadata"]["active_leaf"] = msg_id

    def _get_last_message_id(self, conversation_data: Dict[str, Any], branch_id: Optional[str] = None) -> Optional[str]:
        """Gets the ID of the last message in the specified or active branch."""
        if not conversation_data: return None

        actual_branch_id = branch_id or conversation_data.get("metadata", {}).get("active_branch", "main")
        return conversation_data.get("branches", {}).get(actual_branch_id, {}).get("last_message")

    def get_version(self) -> str:
        """Get the current version of the CannonAI application framework."""
        return self.VERSION

    # --- File Operations (can be called by concrete clients via super() or directly) ---
    async def save_conversation_data(self, conversation_data: Dict[str, Any],
                                     conversation_id: str, title: str,
                                     conversations_dir: Path, quiet: bool = False) -> None:
        """Saves the given conversation data to a JSON file."""
        if not conversation_id or not conversation_data:
            if not quiet: print(f"{Colors.WARNING}No active conversation data to save.{Colors.ENDC}")
            return

        filename = self.format_filename(title, conversation_id)
        filepath = conversations_dir / filename

        # Ensure metadata like updated_at is current before saving
        if "metadata" in conversation_data:
            conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            # Message count for the whole conversation (sum of messages in all branches or just count of messages dict)
            conversation_data["metadata"]["total_message_count"] = len(conversation_data.get("messages", {}))

        if not quiet: print(f"{Colors.CYAN}Saving conversation v{self.VERSION} to {filepath}...{Colors.ENDC}")
        try:
            def save_json_sync():
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(conversation_data, f, indent=2, ensure_ascii=False)

            # Run the synchronous file I/O in a separate thread from an async context
            # If called from a sync context, this would just be direct call.
            # This method is designed to be awaitable if needed.
            await asyncio.to_thread(save_json_sync)

            if not quiet:
                msg_count = len(conversation_data.get("messages", {}))
                print(f"{Colors.GREEN}Conversation '{title}' saved to: {filepath}. Total messages: {msg_count}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}Error saving conversation '{title}' to {filepath}: {e}{Colors.ENDC}")

    async def load_conversation_data(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """Loads conversation data from a JSON file."""
        if not filepath.exists():
            print(f"{Colors.FAIL}Conversation file not found: {filepath}{Colors.ENDC}")
            return None
        try:
            def load_json_sync():
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)

            loaded_data = await asyncio.to_thread(load_json_sync)

            # Basic validation
            if not isinstance(loaded_data, dict) or "conversation_id" not in loaded_data or "metadata" not in loaded_data:
                print(f"{Colors.WARNING}File {filepath} does not appear to be a valid CannonAI conversation file (missing key fields).{Colors.ENDC}")
                return None

            print(f"{Colors.GREEN}Conversation data loaded from: {filepath}{Colors.ENDC}")
            return loaded_data
        except json.JSONDecodeError as e:
            print(f"{Colors.FAIL}Error decoding JSON from {filepath}: {e}{Colors.ENDC}")
            return None
        except Exception as e:
            print(f"{Colors.FAIL}Error loading conversation from {filepath}: {e}{Colors.ENDC}")
            return None

    def _find_conversation_file_by_id_or_filename(self, conversations_dir: Path, conversation_id_or_filename: str) -> Optional[Path]:
        """
        Helper to find a conversation file path by ID or filename (synchronous).
        This can be called via asyncio.to_thread if needed from async context.
        """
        # Try direct filename match first (with and without .json)
        potential_path1 = conversations_dir / conversation_id_or_filename
        if potential_path1.exists() and potential_path1.is_file():
            return potential_path1

        potential_path2 = conversations_dir / f"{conversation_id_or_filename}.json"
        if potential_path2.exists() and potential_path2.is_file():
            return potential_path2

        # If not a direct filename, iterate and check metadata
        for file_path in conversations_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Check by conversation_id stored in the file
                if data.get("conversation_id") == conversation_id_or_filename:
                    return file_path
                # Check by title (less reliable but can be a fallback)
                # if data.get("metadata", {}).get("title") == conversation_id_or_filename:
                #    return file_path
            except (json.JSONDecodeError, IOError):
                continue  # Skip corrupted or unreadable files
        return None

    async def list_conversation_files_info(self, conversations_dir: Path) -> List[Dict[str, Any]]:
        """Lists summary info for all conversation files in the directory (awaitable)."""

        def list_files_sync():
            convs_info = []
            for file_path in conversations_dir.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    metadata = data.get("metadata", {})
                    # Fallback for very old format if metadata key is missing but history/type:metadata is present
                    if not metadata and "history" in data:
                        for history_item in data.get("history", []):
                            if history_item.get("type") == "metadata":
                                metadata = history_item.get("content", {})
                                break

                    messages_dict = data.get("messages", {})  # New format
                    message_count = len(messages_dict)
                    if message_count == 0 and "history" in data:  # Old format message count
                        message_count = sum(1 for item in data.get("history", []) if item.get("type") == "message")

                    convs_info.append({
                        "filename": file_path.name,
                        "path": str(file_path),  # Store as string for easier JSON serialization if needed
                        "title": metadata.get("title", "Untitled Conversation"),
                        "provider": metadata.get("provider", "N/A"),
                        "model": metadata.get("model", "N/A"),
                        "created_at": metadata.get("created_at", "N/A"),
                        "updated_at": metadata.get("updated_at", "N/A"),
                        "message_count": message_count,
                        "conversation_id": data.get("conversation_id", None)  # Essential field
                    })
                except Exception as e:
                    print(f"{Colors.WARNING}Error reading or parsing {file_path.name}: {e}{Colors.ENDC}")
            return sorted(convs_info, key=lambda x: x.get("updated_at", ""), reverse=True)  # Sort by most recently updated

        return await asyncio.to_thread(list_files_sync)

