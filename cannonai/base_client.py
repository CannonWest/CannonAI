#!/usr/bin/env python3
"""
CannonAI Base Client Features - Core utilities for conversation management.

This module provides base classes and shared, provider-agnostic functionality
for file operations, conversation data structuring, and terminal colors.
"""

import json
import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import uuid  # Added for generate_conversation_id and create_message_structure

import asyncio

# Use colorama for cross-platform terminal colors
try:
    from colorama import init, Fore, Style  # Removed Back as it's not used

    init(autoreset=True)
    colorama_available = True
except ImportError:
    print("Warning: colorama package not installed. Terminal colors may not work correctly.")
    print("Please install with: pip install colorama")
    colorama_available = False


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
    UNDERLINE = '\033[4m'  # Retained as it was there, though not actively used in provided snippets


class BaseClientFeatures:
    """
    Base class providing features for CannonAI clients, focusing on
    conversation structure, file I/O, and general utilities.
    This class is provider-agnostic.
    """

    VERSION = "2.3.0"  # Version indicating system instruction refactor

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

        # Fallback default params are not strictly needed here anymore as providers handle their defaults.
        # AsyncClient will manage the layering of these.
        # self._fallback_default_params = { ... }

    def ensure_directories(self, base_dir: Optional[Path] = None) -> None:
        """Ensure necessary directories exist.

        Args:
            base_dir: The directory to ensure. Uses self.base_directory if None.
        """
        dir_to_ensure = base_dir or self.base_directory
        try:
            dir_to_ensure.mkdir(parents=True, exist_ok=True)
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
        """Generates a unique conversation ID using UUID v4."""
        return str(uuid.uuid4())

    def create_message_structure(self, role: str, text: str,
                                 model: Optional[str] = None,
                                 params: Optional[Dict[str, Any]] = None,
                                 token_usage: Optional[Dict[str, Any]] = None,
                                 message_id: Optional[str] = None,
                                 parent_id: Optional[str] = None,
                                 branch_id: str = "main") -> Dict[str, Any]:
        """Create a standard message structure for conversation history.
        This structure represents actual user/assistant messages to be stored.

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
        if message_id is None:
            message_id = str(uuid.uuid4())

        message_dict = {
            "id": message_id,
            "parent_id": parent_id,
            "branch_id": branch_id,  # Branch this message primarily belongs to
            "type": role,  # 'user' or 'assistant'
            "content": text,
            "timestamp": datetime.now().isoformat(),
            "children": []  # List of child message IDs
        }

        if role == "assistant":
            if model: message_dict["model"] = model
            if params: message_dict["params"] = params.copy()
            if token_usage: message_dict["token_usage"] = token_usage

        return message_dict

    def create_metadata_structure(self, title: str, conversation_id: str, system_instruction: str) -> Dict[str, Any]:
        """Create metadata structure for a new conversation.
        System instruction is now part of metadata.

        Args:
            title: Conversation title.
            conversation_id: Unique conversation identifier.
            system_instruction: The system instruction for this conversation.

        Returns:
            Metadata structure dictionary for a new conversation.
        """
        return {
            "conversation_id": conversation_id,
            "version": self.VERSION,  # Use class attribute for version
            "metadata": {
                "title": title,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "app_info": "CannonAI Application",
                "platform": platform.system(),
                "active_branch": "main",  # Default active branch
                "active_leaf": None,  # ID of the last message in the active branch
                "system_instruction": system_instruction,  # NEW: Stored in metadata
                # Provider, model, params will be filled by the specific client instance when saving
            },
            "messages": {},  # Dictionary to store all messages, keyed by message_id
            "branches": {  # Information about different conversation branches
                "main": {
                    "created_at": datetime.now().isoformat(),
                    "last_message": None,  # ID of the last message in this branch
                    "message_count": 0
                }
            }
        }

    def _build_message_chain(self, conversation_data: Dict[str, Any], branch_id: Optional[str] = None) -> List[str]:
        """
        Builds an ordered list of message IDs for a specific branch, from root to leaf.
        This chain represents the actual stored messages.
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
            # This can happen if a branch is created but has no messages yet, or if active_leaf points to a non-existent message
            return []

        chain = []
        current_id: Optional[str] = leaf_id  # Start from the leaf of the branch
        visited_ids_for_chain = set()  # To prevent infinite loops in malformed data

        while current_id and current_id not in visited_ids_for_chain:
            visited_ids_for_chain.add(current_id)
            current_msg_data = messages.get(current_id, {})

            # Ensure the message belongs to the target branch if we are strictly tracing one branch
            # This is important because a message's parent might be on a different branch if branching occurred.
            if current_msg_data.get("branch_id") == actual_branch_id:
                chain.append(current_id)
            else:
                # If the message is not on the current branch, but its parent_id might be,
                # we need to decide if we stop or if this message is an ancestor from a shared path.
                # For _build_message_chain, we expect messages to be on the specified branch.
                # If a message's branch_id doesn't match actual_branch_id, it means we've likely
                # hit the point where this branch diverged.
                # However, the parent_id link should still be followed to get the full ancestry.
                # The critical part is that `leaf_id` must be on `actual_branch_id`.
                # Let's assume the parent_id chain correctly defines ancestry.
                pass  # Continue tracing parent even if branch_id differs, for full history.

            current_id = current_msg_data.get("parent_id")

        chain.reverse()  # Reverse to get chronological order (root to leaf)
        return chain

    def _add_message_to_conversation(self, conversation_data: Dict[str, Any], message: Dict[str, Any]) -> None:
        """Adds a message to the provided conversation_data structure.
           Updates message counts and parent-child relationships.
        """
        if not conversation_data:
            print(f"{Colors.WARNING}Attempted to add message but conversation_data is not initialized/provided.{Colors.ENDC}")
            return

        msg_id = message["id"]
        parent_id = message.get("parent_id")
        branch_id = message.get("branch_id", "main")  # Default to main if not specified

        # Ensure main structures exist
        conversation_data.setdefault("messages", {})
        conversation_data.setdefault("branches", {})
        conversation_data.setdefault("metadata", {}).setdefault("active_branch", "main")

        # Add message to the global messages dictionary
        conversation_data["messages"][msg_id] = message

        # Link to parent if parent_id exists and is valid
        if parent_id and parent_id in conversation_data["messages"]:
            parent_message_data = conversation_data["messages"][parent_id]
            parent_message_data.setdefault("children", [])
            if msg_id not in parent_message_data["children"]:
                parent_message_data["children"].append(msg_id)

        # Update branch information
        if branch_id not in conversation_data["branches"]:
            conversation_data["branches"][branch_id] = {
                "created_at": message.get("timestamp", datetime.now().isoformat()),
                "last_message": None, "message_count": 0
            }
        branch_info = conversation_data["branches"][branch_id]
        branch_info["last_message"] = msg_id  # This message is now the latest on its branch

        # Recalculate message count for this specific branch
        # This counts messages whose primary branch_id matches.
        count = 0
        for m_data_content in conversation_data["messages"].values():
            if m_data_content.get("branch_id") == branch_id:
                count += 1
        branch_info["message_count"] = count

        # If this message is on the currently active branch, update the active_leaf in metadata
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

    async def save_conversation_data(self, conversation_data: Dict[str, Any],
                                     conversation_id: str, title: str,
                                     conversations_dir: Path, quiet: bool = False) -> None:
        """Saves the given conversation data to a JSON file. (Async wrapper for sync I/O)"""
        if not conversation_id or not conversation_data:
            if not quiet: print(f"{Colors.WARNING}No active conversation data to save.{Colors.ENDC}")
            return

        filename = self.format_filename(title, conversation_id)
        filepath = conversations_dir / filename

        if "metadata" in conversation_data:
            conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            conversation_data["metadata"]["total_message_count"] = len(conversation_data.get("messages", {}))
            # Provider, model, params should be updated by the client before calling this.
            # System instruction is already in metadata.

        if not quiet: print(f"{Colors.CYAN}Saving conversation (v{self.VERSION}) to {filepath}...{Colors.ENDC}")

        try:
            def save_json_sync():
                filepath.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(conversation_data, f, indent=2, ensure_ascii=False)

            await asyncio.to_thread(save_json_sync)

            if not quiet:
                msg_count = len(conversation_data.get("messages", {}))
                print(f"{Colors.GREEN}Conversation '{title}' saved to: {filepath}. Total messages: {msg_count}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}Error saving conversation '{title}' to {filepath}: {e}{Colors.ENDC}")

    async def load_conversation_data(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """Loads conversation data from a JSON file. (Async wrapper for sync I/O)"""
        if not filepath.exists():
            print(f"{Colors.FAIL}Conversation file not found: {filepath}{Colors.ENDC}")
            return None
        try:
            def load_json_sync():
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)

            loaded_data = await asyncio.to_thread(load_json_sync)

            if not isinstance(loaded_data, dict) or \
                    "conversation_id" not in loaded_data or \
                    "metadata" not in loaded_data:
                print(f"{Colors.WARNING}File {filepath} does not appear to be a valid CannonAI conversation file (missing key fields).{Colors.ENDC}")
                return None

            # Ensure system_instruction is present in metadata for backward compatibility (or add default)
            if "system_instruction" not in loaded_data.get("metadata", {}):
                print(f"{Colors.WARNING}System instruction not found in metadata of {filepath}. Attempting to derive or using default.{Colors.ENDC}")
                # For this refactor, we'll assume new conversations get it. Old ones might need migration or will use default.
                # If we wanted to derive from old format (first message), that logic would go here.
                # For now, if it's missing, AsyncClient.load_conversation will handle setting a default.
                pass

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
                if data.get("conversation_id") == conversation_id_or_filename:
                    return file_path
                # Consider also checking by title if needed, but ID is primary
                # if data.get("metadata", {}).get("title", "").lower() == conversation_id_or_filename.lower():
                #    return file_path
            except (json.JSONDecodeError, IOError, TypeError):  # Added TypeError for robustness
                # print(f"{Colors.WARNING}Skipping unreadable/corrupt file: {file_path.name}{Colors.ENDC}")
                continue
        return None

    async def list_conversation_files_info(self, conversations_dir: Path) -> List[Dict[str, Any]]:
        """Lists summary info for all conversation files in the directory (awaitable)."""

        def list_files_sync():
            convs_info = []
            if not conversations_dir.exists():  # Check if directory exists
                print(f"{Colors.WARNING}Conversations directory not found: {conversations_dir}{Colors.ENDC}")
                return convs_info

            for file_path in conversations_dir.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    metadata = data.get("metadata", {})
                    messages_dict = data.get("messages", {})
                    message_count = len(messages_dict)

                    # Fallback for old format message count if messages_dict is empty but history exists
                    if message_count == 0 and "history" in data and isinstance(data["history"], list):
                        message_count = sum(1 for item in data.get("history", []) if item.get("type") == "message")

                    convs_info.append({
                        "filename": file_path.name,
                        "path": str(file_path),
                        "title": metadata.get("title", "Untitled Conversation"),
                        "provider": metadata.get("provider", "N/A"),
                        "model": metadata.get("model", "N/A"),
                        "created_at": metadata.get("created_at", "N/A"),
                        "updated_at": metadata.get("updated_at", "N/A"),
                        "message_count": message_count,
                        "conversation_id": data.get("conversation_id"),  # Should always exist
                        "system_instruction_preview": metadata.get("system_instruction", "")[:50] + "..." if metadata.get("system_instruction") else "N/A"
                    })
                except Exception as e:
                    print(f"{Colors.WARNING}Error reading or parsing {file_path.name}: {e}{Colors.ENDC}")
            # Sort by most recently updated
            return sorted(convs_info, key=lambda x: x.get("updated_at", "0"), reverse=True)

        return await asyncio.to_thread(list_files_sync)
