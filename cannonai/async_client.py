#!/usr/bin/env python3
"""
CannonAI Asynchronous Client - Provider-agnostic AI interaction client.

This module provides the asynchronous implementation of the CannonAI client,
building on conversation management logic from BaseClientFeatures and
delegating AI operations to a provider.
"""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, AsyncIterator, AsyncGenerator

from tabulate import tabulate

from base_client import BaseClientFeatures, Colors
from providers.base_provider import BaseAIProvider, ProviderError
from config import Config


class AsyncClient(BaseClientFeatures):
    """
    Asynchronous, provider-agnostic client for CannonAI.
    Manages conversations and interacts with an AI provider for responses.
    System instructions are stored in conversation metadata and dynamically prepended.
    """
    VERSION = "2.3.0"  # Ensure this matches the version in base_client.py if they are related

    def __init__(self, provider: BaseAIProvider, conversations_dir: Optional[Path] = None, global_config: Optional[Config] = None):
        """
        Initialize the asynchronous AI client.

        Args:
            provider: An instance of a class that implements BaseAIProvider.
            conversations_dir: Directory to store conversations. Uses default if None.
            global_config: Optional global Config object to fetch default system instruction.
        """
        super().__init__(conversations_dir=conversations_dir)

        self.provider = provider
        # If global_config is not provided, create a default quiet one.
        self.global_config = global_config if global_config else Config(quiet=True)

        self.conversation_id: Optional[str] = None
        self.conversation_data: Dict[str, Any] = {}  # Stores the entire conversation structure
        self.conversation_name: str = "New Conversation"  # Display name for the current conversation

        # Default generation parameters, will be updated from provider and config
        self.params: Dict[str, Any] = self.provider.get_default_params().copy()
        self.use_streaming: bool = False  # Client's session default, can be overridden by conversation metadata

        # Default system instruction, can be overridden by conversation metadata
        self.system_instruction: str = self.global_config.get("default_system_instruction", Config.DEFAULT_SYSTEM_INSTRUCTION)

        self.current_user_message_id: Optional[str] = None  # Tracks the ID of the most recent user message added via add_user_message
        self.is_web_ui: bool = False  # Flag to indicate if the client is used by the web UI

        self.ensure_directories()  # Ensure the conversations directory exists

    @property
    def active_branch(self) -> str:
        """Gets the ID of the currently active branch in the conversation."""
        return self.conversation_data.get("metadata", {}).get("active_branch", "main")

    @active_branch.setter
    def active_branch(self, branch_id: str) -> None:
        """Sets the ID of the currently active branch."""
        self.conversation_data.setdefault("metadata", {})["active_branch"] = branch_id

    @property
    def current_model_name(self) -> str:
        """Gets the model name currently configured for the provider."""
        return self.provider.config.model

    async def initialize_client(self) -> bool:
        """
        Initializes the underlying AI provider.
        Returns True if successful, False otherwise.
        """
        print(f"{Colors.CYAN}Initializing provider: {self.provider.provider_name} with model {self.provider.config.model}...{Colors.ENDC}")
        try:
            success = await self.provider.initialize()
            if success:
                print(f"{Colors.GREEN}Successfully initialized {self.provider.provider_name} provider.{Colors.ENDC}")
                # Update client's default params from the now-initialized provider
                self.params = self.provider.get_default_params().copy()
            else:
                print(f"{Colors.FAIL}Failed to initialize {self.provider.provider_name} provider.{Colors.ENDC}")
            return success
        except Exception as e:
            print(f"{Colors.FAIL}Error during provider initialization for {self.provider.provider_name}: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            return False

    async def start_new_conversation(self, title: Optional[str] = None, is_web_ui: bool = False) -> None:
        """
        Starts a new conversation. Saves the current one if active.
        Args:
            title: Optional title for the new conversation.
            is_web_ui: Flag indicating if called from web UI (suppresses input prompts).
        """
        if self.conversation_id and self.conversation_data:
            await self.save_conversation(quiet=True)  # Save previous conversation

        print(f"{Colors.CYAN}Starting new conversation...{Colors.ENDC}")
        self.conversation_id = self.generate_conversation_id()
        self.is_web_ui = is_web_ui  # Store if this client instance is for web UI

        if title is None and not self.is_web_ui:  # Prompt for title only if not web UI and no title given
            title_prompt = "Enter a title for this conversation (or leave blank for timestamp): "
            title_input = input(title_prompt).strip()
            title = title_input if title_input else f"Conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        elif not title:  # Auto-generate if title is empty or None (e.g., from web UI with blank input)
            title = f"Conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.conversation_name = title
        # Use global default system instruction for new conversations
        current_system_instruction = self.global_config.get("default_system_instruction", Config.DEFAULT_SYSTEM_INSTRUCTION)
        self.system_instruction = current_system_instruction  # Update client's current system instruction

        # Create the basic conversation data structure
        self.conversation_data = self.create_metadata_structure(title, self.conversation_id, current_system_instruction)
        conv_meta = self.conversation_data["metadata"]  # Convenience alias
        conv_meta["provider"] = self.provider.provider_name
        conv_meta["model"] = self.current_model_name
        conv_meta["params"] = self.params.copy()  # Use client's current session params
        conv_meta["streaming_preference"] = self.use_streaming  # Use client's current session streaming pref
        self.active_branch = "main"  # New conversations start on the main branch

        print(f"{Colors.GREEN}Started new conversation: '{title}' (ID: {self.conversation_id[:8]}){Colors.ENDC}")
        print(f"{Colors.CYAN}System Instruction: '{current_system_instruction[:70]}{'...' if len(current_system_instruction) > 70 else ''}'{Colors.ENDC}")
        print(f"{Colors.CYAN}Provider: {self.provider.provider_name}, Model: {self.current_model_name}{Colors.ENDC}")
        await self.save_conversation()  # Initial save of the new conversation structure

    async def save_conversation(self, quiet: bool = False) -> None:
        """Saves the current conversation data to a file."""
        if not self.conversation_id or not self.conversation_data:
            if not quiet: print(f"{Colors.WARNING}No active conversation to save.{Colors.ENDC}")
            return

        # Ensure metadata reflects current client state before saving
        conv_meta = self.conversation_data.setdefault("metadata", {})
        conv_meta["provider"] = self.provider.provider_name
        conv_meta["model"] = self.current_model_name
        conv_meta["params"] = self.params.copy()  # Save current session params to conversation
        conv_meta["streaming_preference"] = self.use_streaming  # Save current session streaming pref
        conv_meta["system_instruction"] = self.system_instruction  # Save current system instruction

        await super().save_conversation_data(
            conversation_data=self.conversation_data,
            conversation_id=self.conversation_id,
            title=conv_meta.get("title", "Untitled"),  # Get title from metadata
            conversations_dir=self.base_directory,
            quiet=quiet
        )

    async def load_conversation(self, name_or_idx_or_id: Optional[str] = None) -> None:
        """Loads a conversation from a file, by name, index, or ID."""
        if self.conversation_id and self.conversation_data:  # Save current before loading another
            await self.save_conversation(quiet=True)

        all_convs_info = await self.list_conversations()  # Get list of available conversations
        if not all_convs_info:
            print(f"{Colors.WARNING}No saved conversations found in {self.base_directory}.{Colors.ENDC}")
            return

        selected_conv_info: Optional[Dict[str, Any]] = None
        if name_or_idx_or_id:  # If an identifier is provided
            name_or_idx_lower = name_or_idx_or_id.lower()
            # Try matching by conversation_id, then filename, then title
            selected_conv_info = next((c for c in all_convs_info if c.get("conversation_id") == name_or_idx_or_id), None)
            if not selected_conv_info:
                selected_conv_info = next((c for c in all_convs_info if c["filename"].lower() == name_or_idx_lower), None)
            if not selected_conv_info:
                selected_conv_info = next((c for c in all_convs_info if c["title"].lower() == name_or_idx_lower), None)
            if not selected_conv_info:  # Try matching by index (if it's a number)
                try:
                    idx = int(name_or_idx_or_id) - 1  # User input is 1-based
                    if 0 <= idx < len(all_convs_info):
                        selected_conv_info = all_convs_info[idx]
                except ValueError:
                    pass  # Not a number
            if not selected_conv_info:
                print(f"{Colors.FAIL}Conversation '{name_or_idx_or_id}' not found.{Colors.ENDC}")
                await self.display_conversations()  # Show list again for user
                return
        else:  # No identifier provided, prompt user interactively
            await self.display_conversations()
            try:
                selection_str = input("\nEnter conversation number to load (or press Enter to cancel): ").strip()
                if not selection_str: print(f"{Colors.CYAN}Load cancelled.{Colors.ENDC}"); return
                sel_num = int(selection_str) - 1  # User input is 1-based
                if 0 <= sel_num < len(all_convs_info):
                    selected_conv_info = all_convs_info[sel_num]
                else:
                    print(f"{Colors.FAIL}Invalid selection number.{Colors.ENDC}");
                    return
            except ValueError:
                print(f"{Colors.FAIL}Invalid input. Please enter a number.{Colors.ENDC}");
                return

        if not selected_conv_info or not selected_conv_info.get("path"):
            print(f"{Colors.FAIL}Could not identify conversation file to load.{Colors.ENDC}")
            return

        loaded_data = await super().load_conversation_data(Path(selected_conv_info["path"]))
        if not loaded_data: return  # Error message handled by superclass method

        self.conversation_data = loaded_data
        self.conversation_id = loaded_data.get("conversation_id")
        conv_meta = self.conversation_data.get("metadata", {})
        self.conversation_name = conv_meta.get("title", "Untitled")
        # Load system instruction from conversation metadata, fallback to client's current (which might be global default)
        self.system_instruction = conv_meta.get("system_instruction", self.global_config.get("default_system_instruction", Config.DEFAULT_SYSTEM_INSTRUCTION))

        # Sync client state with loaded conversation's metadata
        loaded_provider_name = conv_meta.get("provider")
        loaded_model_name = conv_meta.get("model")
        loaded_params = conv_meta.get("params")
        loaded_streaming_pref = conv_meta.get("streaming_preference")

        if loaded_provider_name and loaded_provider_name != self.provider.provider_name:
            print(f"{Colors.WARNING}Conversation was created with provider '{loaded_provider_name}'. Current is '{self.provider.provider_name}'. Provider not changed by load.{Colors.ENDC}")
            # Provider change requires re-initialization, not handled by simple load.
        if loaded_model_name:
            if self.provider.validate_model(loaded_model_name):
                if loaded_model_name != self.current_model_name:  # Only update if different
                    print(f"{Colors.CYAN}Conversation used model '{loaded_model_name}'. Updating session model.{Colors.ENDC}")
                    self.provider.config.model = loaded_model_name
            else:
                print(f"{Colors.WARNING}Model '{loaded_model_name}' from conversation not valid for current provider '{self.provider.provider_name}'. Using '{self.current_model_name}'.{Colors.ENDC}")
            # Ensure metadata reflects the actual model being used for this session
            self.conversation_data["metadata"]["model"] = self.current_model_name
            self.conversation_data["metadata"]["provider"] = self.provider.provider_name  # Ensure provider is also current
        if loaded_params:
            self.params = loaded_params.copy()  # Update client's session params
            self.conversation_data["metadata"]["params"] = self.params.copy()  # Ensure metadata is synced
            print(f"{Colors.CYAN}Loaded generation parameters from conversation.{Colors.ENDC}")
        else:  # If no params in loaded conv, ensure metadata gets current session params
            self.conversation_data.setdefault("metadata", {})["params"] = self.params.copy()
        if loaded_streaming_pref is not None:
            self.use_streaming = loaded_streaming_pref  # Update client's session streaming pref
            self.conversation_data["metadata"]["streaming_preference"] = self.use_streaming  # Sync metadata
            print(f"{Colors.CYAN}Loaded streaming preference: {'Enabled' if self.use_streaming else 'Disabled'}.{Colors.ENDC}")
        else:  # If no streaming pref in loaded conv, ensure metadata gets current session pref
            self.conversation_data.setdefault("metadata", {})["streaming_preference"] = self.use_streaming
        self.active_branch = conv_meta.get("active_branch", "main")  # Load active branch

        print(f"{Colors.GREEN}Conversation '{self.conversation_name}' loaded (ID: {self.conversation_id[:8] if self.conversation_id else 'N/A'}).{Colors.ENDC}")
        print(f"{Colors.CYAN}System Instruction: '{self.system_instruction[:70]}{'...' if len(self.system_instruction) > 70 else ''}'{Colors.ENDC}")
        print(f"{Colors.CYAN}Active Provider: {self.provider.provider_name}, Model: {self.current_model_name}, Branch: '{self.active_branch}'{Colors.ENDC}")
        await self.display_conversation_history()  # Show the history of the loaded conversation

    async def send_message(self, message: str, attachments: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        """
        Sends a message to the AI provider (CLI-focused version).
        Adds user message, gets AI response, adds AI message, and saves.
        Args:
            message: The text content of the user's message.
            attachments: Optional list of attachments for the message.
        Returns:
            The AI's response text, or None on failure.
        """
        if not message.strip() and not attachments: return None  # Must have text or attachment
        if not self.provider.is_initialized:
            print(f"{Colors.FAIL}Provider '{self.provider.provider_name}' is not initialized.{Colors.ENDC}")
            return None
        if not self.conversation_id or not self.conversation_data:  # If no active conversation, start one
            print(f"{Colors.CYAN}No active conversation. Starting a new one...{Colors.ENDC}")
            await self.start_new_conversation(is_web_ui=self.is_web_ui)
            if not self.conversation_id:  # Check if start_new_conversation failed
                print(f"{Colors.FAIL}Failed to start a new conversation. Cannot send message.{Colors.ENDC}")
                return None

        try:
            # Add user message to conversation data
            parent_id = self._get_last_message_id(self.conversation_data, self.active_branch)
            user_msg_obj = self.create_message_structure(role="user", text=message, parent_id=parent_id, branch_id=self.active_branch, attachments=attachments)
            self._add_message_to_conversation(self.conversation_data, user_msg_obj)
            user_msg_id = user_msg_obj["id"]  # Get the ID of the added user message

            # Prepare history and parameters for the provider
            history_for_provider = self._build_history_for_provider()
            current_params = self.conversation_data.get("metadata", {}).get("params", self.params).copy()
            current_streaming_pref = self.conversation_data.get("metadata", {}).get("streaming_preference", self.use_streaming)
            response_text = ""
            token_usage = {}

            if current_streaming_pref:  # Handle streaming response
                print(f"\r{Colors.CYAN}{self.provider.provider_name} is thinking... (streaming){Colors.ENDC}", end="", flush=True)
                print("\r" + " " * (len(self.provider.provider_name) + 30) + "\r", end="", flush=True)  # Clear thinking line
                print(f"{Colors.GREEN}AI: {Colors.ENDC}", end="", flush=True)  # AI prefix
                stream_generator: AsyncGenerator[Dict[str, Any], None] = await self.provider.generate_response(history_for_provider, current_params, stream=True)  # type: ignore
                async for chunk_data in stream_generator:
                    if chunk_data.get("error"):
                        response_text = f"Error from provider: {chunk_data['error']}"
                        print(f"\n{Colors.FAIL}{response_text}{Colors.ENDC}")  # Print error
                        break
                    if chunk_data.get("chunk"):
                        print(chunk_data["chunk"], end="", flush=True)  # Print chunk
                        response_text += chunk_data["chunk"]
                    if chunk_data.get("done"):  # Stream finished
                        token_usage = chunk_data.get("token_usage", {})
                        full_response_text_from_provider = chunk_data.get("full_response", response_text)
                        if full_response_text_from_provider: response_text = full_response_text_from_provider  # Ensure full text
                        break
                print()  # Newline after streaming
            else:  # Handle non-streaming response
                print(f"\r{Colors.CYAN}{self.provider.provider_name} is thinking...{Colors.ENDC}", end="", flush=True)
                raw_response_text, metadata = await self.provider.generate_response(history_for_provider, current_params, stream=False)  # type: ignore
                print("\r" + " " * (len(self.provider.provider_name) + 20) + "\r", end="", flush=True)  # Clear thinking line
                response_text = raw_response_text if raw_response_text is not None else ""
                token_usage = metadata.get("token_usage", {})
                print(f"\n{Colors.GREEN}AI: {Colors.ENDC}{response_text}")  # Print full response

            # Add AI's response to conversation data
            ai_msg_obj = self.create_message_structure(
                role="assistant", text=response_text, model=self.current_model_name,
                params=current_params, token_usage=token_usage,
                parent_id=user_msg_id, branch_id=self.active_branch
            )
            self._add_message_to_conversation(self.conversation_data, ai_msg_obj)
            await self.save_conversation(quiet=True)  # Auto-save
            return response_text
        except Exception as e:
            print(f"{Colors.FAIL}Error generating response via {self.provider.provider_name}: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            # Log error message as an AI response if possible
            err_parent_id = locals().get('user_msg_id', self._get_last_message_id(self.conversation_data, self.active_branch))
            err_msg_text = f"Error: Provider communication failed. {str(e)[:200]}"
            if self.conversation_data and self.conversation_id:  # Check if conversation is active
                error_message_obj = self.create_message_structure(
                    role="assistant", text=err_msg_text, model=self.current_model_name,
                    params=self.params, parent_id=err_parent_id, branch_id=self.active_branch
                )
                self._add_message_to_conversation(self.conversation_data, error_message_obj)
                await self.save_conversation(quiet=True)
            return None

    def _build_history_for_provider(self) -> List[Dict[str, Any]]:
        """
        Builds the message history for the AI provider, including system instruction.
        Returns a list of message dicts compatible with provider's normalize_messages.
        """
        provider_history: List[Dict[str, Any]] = []

        # Get system instruction from current conversation's metadata, or client's current, or global default
        current_system_instruction = self.conversation_data.get("metadata", {}).get("system_instruction", self.system_instruction)
        if not current_system_instruction or not current_system_instruction.strip():  # Fallback if empty
            current_system_instruction = self.global_config.get("default_system_instruction", Config.DEFAULT_SYSTEM_INSTRUCTION)

        # Prepend system instruction if it exists (as a user message, to be normalized by provider)
        if current_system_instruction and current_system_instruction.strip():
            provider_history.append({"role": "user", "content": current_system_instruction, "is_system_instruction": True})  # Mark for potential special handling
            provider_history.append({"role": "assistant", "content": "Understood. I will follow these instructions."})  # Standard AI ack for system prompt

        # Add actual stored messages from the active conversation branch
        actual_stored_messages = self.get_conversation_history()  # Gets messages from current active branch
        for msg_data in actual_stored_messages:
            provider_history.append({
                "role": msg_data["role"],
                "content": msg_data.get("content", ""),
                "attachments": msg_data.get("attachments")  # Pass attachments
            })
        # The provider's normalize_messages method is responsible for final formatting
        return self.provider.normalize_messages(provider_history)

    async def get_available_models(self) -> List[Dict[str, Any]]:
        """Gets list of available models from the current provider."""
        if not self.provider.is_initialized:
            print(f"{Colors.FAIL}Provider '{self.provider.provider_name}' is not initialized.{Colors.ENDC}")
            return []
        try:
            return await self.provider.list_models()
        except Exception as e:
            print(f"{Colors.FAIL}Error getting models from provider '{self.provider.provider_name}': {e}{Colors.ENDC}")
            return []

    async def display_models(self) -> None:
        """Displays available models in a formatted table."""
        models = await self.get_available_models()
        if not models:
            print(f"{Colors.WARNING}No models available for provider: {self.provider.provider_name}.{Colors.ENDC}")
            return
        headers = ["#", "Name", "Display Name", "Input Tokens", "Output Tokens"]
        table_data = [[i + 1, m.get("name", "N/A"), m.get("display_name", m.get("name", "N/A")), m.get("input_token_limit", "N/A"), m.get("output_token_limit", "N/A")] for i, m in enumerate(models)]
        print(f"\nAvailable models for provider: {Colors.BOLD}{self.provider.provider_name}{Colors.ENDC}")
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))

    async def select_model(self) -> None:
        """Allows user to select a model from available options for the current session."""
        models = await self.get_available_models()
        if not models:
            print(f"{Colors.WARNING}No models to select for provider: {self.provider.provider_name}.{Colors.ENDC}")
            return
        await self.display_models()
        try:
            selection_str = input(f"\nEnter model number for {self.provider.provider_name} (or press Enter to cancel): ").strip()
            if not selection_str: print(f"{Colors.CYAN}Model selection cancelled.{Colors.ENDC}"); return
            selection_idx = int(selection_str) - 1
            if 0 <= selection_idx < len(models):
                new_model_name = models[selection_idx]["name"]
                self.provider.config.model = new_model_name  # Update provider's active model
                # If a conversation is active, update its metadata and save
                if self.conversation_data and "metadata" in self.conversation_data:
                    self.conversation_data["metadata"]["model"] = new_model_name
                    self.conversation_data["metadata"]["provider"] = self.provider.provider_name  # Ensure provider is also current
                    print(f"{Colors.CYAN}Conversation model updated. Saving...{Colors.ENDC}")
                    await self.save_conversation(quiet=True)
                print(f"{Colors.GREEN}Selected model: {self.current_model_name} (Provider: {self.provider.provider_name}){Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}Invalid selection number.{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.FAIL}Invalid input. Please enter a number.{Colors.ENDC}")

    async def update_system_instruction(self, new_instruction: str) -> None:
        """Updates the system instruction for the current conversation and client session."""
        print(f"{Colors.CYAN}Updating system instruction...{Colors.ENDC}")
        self.system_instruction = new_instruction  # Update client's current system instruction
        if self.conversation_data and "metadata" in self.conversation_data:  # If a conversation is active
            self.conversation_data["metadata"]["system_instruction"] = new_instruction
            self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            print(f"{Colors.GREEN}System instruction updated in current conversation metadata.{Colors.ENDC}")
            await self.save_conversation(quiet=True)
        else:  # No active conversation
            print(f"{Colors.YELLOW}No active conversation. System instruction '{new_instruction[:50]}...' will apply to the next new conversation started in this session.{Colors.ENDC}")

    async def customize_params(self) -> None:
        """Allows user to customize generation parameters for the current session/conversation."""
        # Start with a copy of current effective params (conversation's if active, else client's session params)
        params_to_edit = self.params.copy()
        if self.conversation_data and self.conversation_data.get("metadata", {}).get("params"):
            params_to_edit.update(self.conversation_data["metadata"]["params"])

        print(f"\n{Colors.HEADER}Customizing Generation Parameters for Provider: {self.provider.provider_name} (Model: {self.current_model_name}){Colors.ENDC}")
        print(f"{Colors.CYAN}Current values are shown in [brackets]. Press Enter to keep current value.{Colors.ENDC}")

        # Get editable params from the provider's defaults (as a template for what's configurable)
        editable_params_from_provider = self.provider.get_default_params().copy()
        if 'system_instruction' in editable_params_from_provider:  # System instruction is handled separately
            del editable_params_from_provider['system_instruction']

        made_changes = False
        new_params_for_conv: Dict[str, Any] = {}  # Store changes here

        try:
            for key in editable_params_from_provider.keys():  # Iterate over known configurable params
                current_val_display = params_to_edit.get(key, "Not set")
                value_str = input(f"{key.replace('_', ' ').capitalize()} [{current_val_display}]: ").strip()
                if value_str:  # If user entered something
                    made_changes = True
                    try:  # Attempt to cast to float or int if appropriate
                        if '.' in value_str or 'e' in value_str.lower():  # Heuristic for float
                            new_params_for_conv[key] = float(value_str)
                        else:  # Assume int
                            new_params_for_conv[key] = int(value_str)
                    except ValueError:  # If casting fails, store as string (or handle bools)
                        if value_str.lower() in ['true', 'false']:
                            new_params_for_conv[key] = value_str.lower() == 'true'
                        else:
                            new_params_for_conv[key] = value_str  # Store as string if not number/bool
            if made_changes:
                self.params.update(new_params_for_conv)  # Update client's session params
                if self.conversation_data and "metadata" in self.conversation_data:  # If conversation active
                    self.conversation_data["metadata"].setdefault("params", {}).update(new_params_for_conv)
                    self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
                    print(f"{Colors.CYAN}Saving updated generation parameters to current conversation...{Colors.ENDC}")
                    await self.save_conversation(quiet=True)
                print(f"{Colors.GREEN}Generation parameters updated successfully.{Colors.ENDC}")
            else:
                print(f"{Colors.CYAN}No changes made to generation parameters.{Colors.ENDC}")
        except ValueError as e:
            print(f"{Colors.FAIL}Invalid input for parameter: {e}. Parameters not updated.{Colors.ENDC}")

    def add_user_message(self, message: str, attachments: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        Adds a user message to conversation data. For GUI to update state before AI call.
        Args:
            message: Text content of user's message.
            attachments: Optional list of attachments.
        """
        if not self.conversation_id or not self.conversation_data:
            print(f"{Colors.FAIL}[Client Error] add_user_message called without an active conversation. Please start or load one.{Colors.ENDC}")
            # Optionally, could auto-start a new conversation here if desired for GUI robustness
            # await self.start_new_conversation(is_web_ui=self.is_web_ui)
            # if not self.conversation_id: return # If still no conversation
            return

        parent_id = self._get_last_message_id(self.conversation_data, self.active_branch)
        user_msg = self.create_message_structure(role="user", text=message, parent_id=parent_id, branch_id=self.active_branch, attachments=attachments)
        self._add_message_to_conversation(self.conversation_data, user_msg)
        self.current_user_message_id = user_msg["id"]  # Track this for parenting the AI's response

    def add_assistant_message(self, message_text: str, token_usage: Optional[Dict[str, Any]] = None) -> None:
        """
        Adds an assistant message to conversation data. For GUI to update state after AI call.
        Args:
            message_text: Text content of AI's response.
            token_usage: Optional token usage metrics.
        """
        if not self.conversation_id or not self.conversation_data:
            print(f"{Colors.FAIL}[Client Error] add_assistant_message called without an active conversation.{Colors.ENDC}")
            return

        text_to_add = message_text if message_text is not None else ""  # Ensure text is string
        parent_id_for_ai = self.current_user_message_id  # Should be set by add_user_message
        if not parent_id_for_ai:  # Fallback if current_user_message_id wasn't set (e.g., direct call)
            parent_id_for_ai = self._get_last_message_id(self.conversation_data, self.active_branch)
            print(f"{Colors.WARNING}[Client for GUI] current_user_message_id not set for AI msg. Using last in branch: {parent_id_for_ai}{Colors.ENDC}")

        conv_meta = self.conversation_data.get("metadata", {})
        ai_model_name = conv_meta.get("model", self.current_model_name)  # Use conversation's model if set
        ai_params = conv_meta.get("params", self.params).copy()  # Use conversation's params if set

        ai_msg = self.create_message_structure(role="assistant", text=text_to_add, model=ai_model_name, params=ai_params, token_usage=token_usage, parent_id=parent_id_for_ai, branch_id=self.active_branch)
        self._add_message_to_conversation(self.conversation_data, ai_msg)
        self.current_user_message_id = None  # Clear after AI response is parented

    async def get_response(self) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Gets a non-streaming response from the AI provider. (Primarily for GUI non-streaming path)
        Assumes add_user_message was called prior to set self.current_user_message_id.
        Returns: Tuple of (response_text, token_usage_dict) or (error_message, None).
        """
        if not self.current_user_message_id:
            print(f"{Colors.FAIL}[Client Error] User message not processed before requesting AI response (get_response).{Colors.ENDC}")
            return "Error: User message not processed first.", None
        if not self.provider.is_initialized:
            print(f"{Colors.FAIL}[Client Error] Provider '{self.provider.provider_name}' not initialized.{Colors.ENDC}")
            return "Error: Provider not initialized.", None
        if not self.conversation_data or not self.conversation_id:
            print(f"{Colors.FAIL}[Client Error] Conversation data not initialized.{Colors.ENDC}")
            return "Error: Conversation data not initialized.", None

        history_for_provider = self._build_history_for_provider()
        current_params = self.conversation_data.get("metadata", {}).get("params", self.params).copy()
        try:
            response_tuple: Tuple[str, Dict[str, Any]] = await self.provider.generate_response(history_for_provider, current_params, stream=False)  # type: ignore
            response_text, metadata = response_tuple

            # *** FIX: Add assistant message to conversation data ***
            token_usage_data = metadata.get("token_usage", {})
            self.add_assistant_message(response_text, token_usage_data)
            # *** End FIX ***

            return response_text, token_usage_data  # Return the extracted token usage
        except Exception as e:
            print(f"{Colors.FAIL}[Client Error] Non-streaming provider error for '{self.provider.provider_name}': {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            # Optionally, add an error message to the conversation history here as well
            # self.add_assistant_message(f"Error from {self.provider.provider_name}: {str(e)}", None)
            return f"Error from {self.provider.provider_name}: {str(e)}", None

    async def get_streaming_response(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Gets a streaming response from the AI provider. (Primarily for GUI streaming path)
        Assumes add_user_message was called prior.
        Yields data chunks and a final 'done' event with full response and metadata.
        """
        if not self.current_user_message_id:
            yield {"error": "User message not processed before requesting AI stream."};
            return
        if not self.provider.is_initialized:
            yield {"error": f"Provider '{self.provider.provider_name}' not initialized."};
            return
        if not self.conversation_data or not self.conversation_id:
            yield {"error": "Conversation data not initialized."};
            return

        user_message_id_for_parenting = self.current_user_message_id  # Parent for the upcoming AI message
        history_for_provider = self._build_history_for_provider()
        current_params = self.conversation_data.get("metadata", {}).get("params", self.params).copy()
        current_model_for_stream = self.conversation_data.get("metadata", {}).get("model", self.current_model_name)
        full_response_text = ""
        final_token_usage = {}
        try:
            stream_generator: AsyncGenerator[Dict[str, Any], None] = await self.provider.generate_response(history_for_provider, current_params, stream=True)  # type: ignore
            async for chunk_data in stream_generator:
                if chunk_data.get("error"): yield chunk_data; return  # Propagate error
                if chunk_data.get("chunk"):
                    full_response_text += chunk_data["chunk"]
                    yield {"chunk": chunk_data["chunk"]}  # Yield text chunk
                if chunk_data.get("done"):  # Stream finished from provider
                    final_token_usage = chunk_data.get("token_usage", {})
                    # Ensure full_response_text is the complete one from the provider if available
                    full_response_text = chunk_data.get("full_response", full_response_text)
                    break  # Exit loop once provider signals done

            # After stream completion, add the full AI message and save
            self.add_assistant_message(full_response_text, final_token_usage)
            assistant_msg_id = self._get_last_message_id(self.conversation_data, self.active_branch)  # Get ID of the just-added AI message
            await self.save_conversation(quiet=True)  # Save conversation with new AI message

            # Yield final 'done' event to GUI with all details
            yield {
                "done": True, "full_response": full_response_text,
                "conversation_id": self.conversation_id, "message_id": assistant_msg_id,
                "parent_id": user_message_id_for_parenting, "model": current_model_for_stream,
                "token_usage": final_token_usage
            }
        except Exception as e:
            print(f"{Colors.FAIL}[Client Error] Streaming provider error for '{self.provider.provider_name}': {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            yield {"error": f"Streaming error with {self.provider.provider_name}: {str(e)}"}

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """
        Retrieves the actual stored user/assistant messages from the active conversation branch.
        Does not include the dynamically prepended system instruction.
        Returns: List of message dictionaries.
        """
        hist_list = []
        if not self.conversation_data or "messages" not in self.conversation_data: return hist_list

        active_branch_message_ids = self._build_message_chain(self.conversation_data, self.active_branch)
        messages_dict = self.conversation_data.get("messages", {})

        for mid in active_branch_message_ids:
            msg = messages_dict.get(mid)
            if msg and msg.get("type") in ["user", "assistant"]:  # Only include user/assistant messages
                hist_list.append({
                    'role': msg["type"],
                    'content': msg.get("content", ""),
                    'id': mid,
                    'model': msg.get("model"),  # Present for assistant messages
                    'timestamp': msg.get("timestamp"),
                    'parent_id': msg.get("parent_id"),
                    'token_usage': msg.get("token_usage"),  # Present for assistant messages
                    'attachments': msg.get("attachments")  # Include attachments if present
                })
        return hist_list

    async def retry_message(self, assistant_message_id_to_retry: str) -> Dict[str, Any]:
        """
        Retries generating an AI response for a previous user message, creating a new branch.
        Args:
            assistant_message_id_to_retry: The ID of the assistant message whose generation should be retried.
        Returns:
            A dictionary with details of the new AI message and its sibling context.
        """
        print(f"{Colors.CYAN}[Client] Retrying from assistant message: {assistant_message_id_to_retry}{Colors.ENDC}")
        if not self.conversation_data or "messages" not in self.conversation_data:
            raise ValueError("No active conversation or messages found to retry.")

        messages_dict = self.conversation_data["messages"]
        original_assistant_msg = messages_dict.get(assistant_message_id_to_retry)
        if not original_assistant_msg or original_assistant_msg.get("type") != "assistant":
            raise ValueError(f"Message ID '{assistant_message_id_to_retry}' is not a valid assistant message to retry.")

        parent_user_id = original_assistant_msg.get("parent_id")
        if not parent_user_id or parent_user_id not in messages_dict:
            raise ValueError("Original assistant message for retry has no valid parent user message.")

        # Store original state in case retry fails
        original_active_branch = self.active_branch
        original_active_leaf = self.conversation_data.get("metadata", {}).get("active_leaf")

        parent_user_message_obj = messages_dict[parent_user_id]
        branch_of_parent_user_message = parent_user_message_obj.get("branch_id", "main")

        # Build history up to (and including) the parent user message for the retry
        history_ids_for_retry = self._build_message_chain_up_to_id(parent_user_id, branch_of_parent_user_message)
        history_for_provider_raw_retry: List[Dict[str, Any]] = []
        for mid in history_ids_for_retry:
            msg = messages_dict[mid]
            history_for_provider_raw_retry.append({
                "role": msg["type"],
                "content": msg.get("content", ""),
                "attachments": msg.get("attachments")  # Include attachments for retry context
            })

        # Prepend current system instruction for the retry
        current_system_instruction = self.conversation_data.get("metadata", {}).get("system_instruction", self.system_instruction)
        history_with_system_prompt_for_retry: List[Dict[str, Any]] = []
        if current_system_instruction and current_system_instruction.strip():
            history_with_system_prompt_for_retry.append({"role": "user", "content": current_system_instruction, "is_system_instruction": True})
            history_with_system_prompt_for_retry.append({"role": "assistant", "content": "Understood."})
        history_with_system_prompt_for_retry.extend(history_for_provider_raw_retry)

        normalized_history_for_retry = self.provider.normalize_messages(history_with_system_prompt_for_retry)
        current_params_for_retry = self.conversation_data.get("metadata", {}).get("params", self.params).copy()
        current_model_for_retry = self.conversation_data.get("metadata", {}).get("model", self.current_model_name)

        try:
            # Generate new response (non-streaming for retry simplicity here)
            response_tuple: Tuple[str, Dict[str, Any]] = await self.provider.generate_response(normalized_history_for_retry, current_params_for_retry, stream=False)  # type: ignore
            new_response_text, metadata = response_tuple
            new_token_usage = metadata.get("token_usage", {})

            # Create new assistant message on a new branch
            new_branch_id = f"branch_{uuid.uuid4().hex[:8]}"  # Unique ID for the new branch
            new_assistant_msg_obj = self.create_message_structure(
                role="assistant", text=new_response_text or "", model=current_model_for_retry,
                params=current_params_for_retry, token_usage=new_token_usage,
                parent_id=parent_user_id, branch_id=new_branch_id  # Assign to new branch
            )
            self._add_message_to_conversation(self.conversation_data, new_assistant_msg_obj)

            # Update active branch and leaf to the new response
            self.active_branch = new_branch_id
            self.conversation_data["metadata"]["active_leaf"] = new_assistant_msg_obj["id"]
            self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            await self.save_conversation(quiet=True)

            # Get sibling info for the new message
            parent_user_msg_children = messages_dict[parent_user_id].get("children", [])
            new_msg_idx = parent_user_msg_children.index(new_assistant_msg_obj["id"]) if new_assistant_msg_obj["id"] in parent_user_msg_children else -1

            print(f"{Colors.GREEN}[Client] Retry successful. New assistant message ID: {new_assistant_msg_obj['id'][:8]} on new branch '{new_branch_id}'.{Colors.ENDC}")
            return {
                "message": new_assistant_msg_obj,  # The new AI message object
                "sibling_index": new_msg_idx,
                "total_siblings": len(parent_user_msg_children),
                "system_instruction": current_system_instruction  # Return the system instruction used
            }
        except Exception as e:
            # Revert active branch/leaf if retry failed
            self.active_branch = original_active_branch
            if original_active_leaf: self.conversation_data.setdefault("metadata", {})["active_leaf"] = original_active_leaf
            print(f"{Colors.FAIL}Error during retry message generation: {e}{Colors.ENDC}")
            import traceback;
            traceback.print_exc()
            raise  # Re-raise the exception to be handled by the caller

    def _build_message_chain_up_to_id(self, target_leaf_id: str, branch_id_context: Optional[str] = None) -> List[str]:
        """Helper to build a message chain up to a specific message ID within a branch context."""
        if not self.conversation_data or "messages" not in self.conversation_data: return []
        messages = self.conversation_data["messages"]
        if target_leaf_id not in messages: return []  # Target message must exist

        chain: List[str] = []
        current_id: Optional[str] = target_leaf_id
        visited_ids = set()  # Prevent infinite loops in malformed data

        while current_id and current_id not in visited_ids:
            visited_ids.add(current_id)
            msg_data = messages.get(current_id, {})
            # Add to chain if it's the target or an ancestor on the correct branch
            if branch_id_context is None or msg_data.get("branch_id") == branch_id_context:
                chain.append(current_id)
            current_id = msg_data.get("parent_id")  # Move to parent
        chain.reverse()  # Order from oldest to newest
        return chain

    async def switch_to_sibling(self, message_id: str, direction: str) -> Dict[str, Any]:
        """
        Switches the active conversation path to a sibling (alternative) AI response.
        Args:
            message_id: The ID of the current message (user or assistant) from which to navigate.
            direction: "prev", "next", or "none" (to just get info without switching).
        Returns:
            A dictionary with the new active AI message and its sibling context.
        """
        print(f"{Colors.CYAN}[Client] Switching {direction} from message: {message_id}{Colors.ENDC}")
        if not self.conversation_data or "messages" not in self.conversation_data:
            raise ValueError("No active conversation or messages found to switch sibling.")

        messages = self.conversation_data["messages"]
        current_message_obj = messages.get(message_id)
        if not current_message_obj: raise ValueError(f"Message {message_id} not found.")

        parent_id: Optional[str] = None
        siblings_ids: List[str] = []
        current_index_in_siblings: int = -1

        # Determine parent and siblings based on if current_message_obj is user or assistant
        if current_message_obj["type"] == "assistant":
            parent_id = current_message_obj.get("parent_id")
            if parent_id and parent_id in messages:
                parent_message_obj = messages[parent_id]
                siblings_ids = parent_message_obj.get("children", [])  # Children of user message are assistant responses
                if message_id in siblings_ids:
                    current_index_in_siblings = siblings_ids.index(message_id)
            else:  # Orphaned assistant message? Or first assistant message with no explicit parent in tree?
                siblings_ids = [message_id];
                current_index_in_siblings = 0  # Treat as only child
        elif current_message_obj["type"] == "user":  # If navigating from a user message, we are interested in its children
            parent_id = message_id  # The user message itself is the "parent" of its responses
            siblings_ids = current_message_obj.get("children", [])
            # Determine which child is currently active (if any)
            active_leaf_for_user_parent = self.conversation_data.get("metadata", {}).get("active_leaf")
            if active_leaf_for_user_parent and active_leaf_for_user_parent in siblings_ids:
                current_index_in_siblings = siblings_ids.index(active_leaf_for_user_parent)
            else:  # No active child, or active leaf is not a child of this user message
                current_index_in_siblings = -1  # Indicate no current active sibling
        else:  # Should not happen for valid messages
            raise ValueError(f"Cannot navigate siblings for message type: {current_message_obj['type']}")

        if not siblings_ids:  # No siblings to navigate
            print(f"{Colors.WARNING}No siblings found for message {message_id} (or its children if user message). No change made.{Colors.ENDC}")
            active_system_instruction = self.conversation_data.get("metadata", {}).get("system_instruction", self.system_instruction)
            return {"message": current_message_obj, "sibling_index": current_index_in_siblings, "total_siblings": len(siblings_ids), "system_instruction": active_system_instruction}

        new_active_message_obj = current_message_obj  # Default to current if no switch happens
        new_sibling_idx = current_index_in_siblings

        if direction == "prev":
            if current_index_in_siblings > 0: new_sibling_idx = current_index_in_siblings - 1
        elif direction == "next":
            if current_index_in_siblings < len(siblings_ids) - 1: new_sibling_idx = current_index_in_siblings + 1
        elif direction == "none":  # Just getting info
            pass  # No change in index
        else:  # Invalid direction
            print(f"{Colors.YELLOW}Invalid navigation direction '{direction}'. No change made.{Colors.ENDC}")

        if new_sibling_idx != -1 and new_sibling_idx < len(siblings_ids):
            new_active_message_id = siblings_ids[new_sibling_idx]
            new_active_message_obj = messages[new_active_message_id]

            # Update active branch and leaf to the selected sibling
            self.active_branch = new_active_message_obj.get("branch_id", self.active_branch)  # Switch to sibling's branch
            self.conversation_data.setdefault("metadata", {})["active_leaf"] = new_active_message_id
            self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            await self.save_conversation(quiet=True)
            print(f"{Colors.GREEN}[Client] Switched. New active AI message: {new_active_message_id[:8]}, Branch: {self.active_branch}, Index: {new_sibling_idx}{Colors.ENDC}")
        else:
            print(f"{Colors.YELLOW}Navigation '{direction}' from message {message_id} resulted in no change or invalid index.{Colors.ENDC}")

        active_system_instruction = self.conversation_data.get("metadata", {}).get("system_instruction", self.system_instruction)
        return {
            "message": new_active_message_obj,  # The new active message (or current if no switch)
            "sibling_index": new_sibling_idx,
            "total_siblings": len(siblings_ids),
            "system_instruction": active_system_instruction
        }

    async def get_message_siblings(self, message_id: str) -> Dict[str, Any]:
        """
        Gets information about a message and its siblings (alternative responses).
        Args:
            message_id: The ID of the message to get sibling info for.
        Returns:
            A dictionary with sibling details.
        """
        if not self.conversation_data or "messages" not in self.conversation_data:
            raise ValueError("No conversation data available.")
        messages = self.conversation_data["messages"]
        target_msg_obj = messages.get(message_id)
        if not target_msg_obj: raise ValueError(f"Message with ID '{message_id}' not found.")

        parent_id_for_siblings: Optional[str] = None
        sibling_ids: List[str] = []
        current_idx: int = -1

        if target_msg_obj["type"] == "assistant":  # If it's an AI response, siblings are other AI responses to the same user message
            parent_id_for_siblings = target_msg_obj.get("parent_id")
            if parent_id_for_siblings and parent_id_for_siblings in messages:
                parent_msg_obj = messages[parent_id_for_siblings]
                sibling_ids = parent_msg_obj.get("children", [])  # Children of user message are AI siblings
                if message_id in sibling_ids: current_idx = sibling_ids.index(message_id)
            else:  # Orphaned or first assistant message
                sibling_ids = [message_id];
                current_idx = 0
        elif target_msg_obj["type"] == "user":  # If it's a user message, "siblings" are its direct AI responses
            parent_id_for_siblings = message_id  # User message is the parent of its responses
            sibling_ids = target_msg_obj.get("children", [])
            # Determine which child is currently active (if any)
            active_leaf = self.conversation_data.get("metadata", {}).get("active_leaf")
            if active_leaf and active_leaf in sibling_ids:
                current_idx = sibling_ids.index(active_leaf)  # Index of the active AI response among its siblings
            else:
                current_idx = -1  # No active child, or active leaf is not a direct child
        else:  # Should not happen
            raise ValueError(f"Cannot determine siblings for message type: {target_msg_obj['type']}")

        return {
            "message_id": message_id,
            "parent_id": parent_id_for_siblings,  # ID of the user message if target_msg is AI, or target_msg ID if user
            "siblings": sibling_ids,  # List of AI response IDs
            "current_index": current_idx,  # Index of target_msg (if AI) or active_leaf (if target_msg is user) among siblings
            "total": len(sibling_ids)
        }

    async def get_conversation_tree(self) -> Dict[str, Any]:
        """
        Gets data for visualizing the conversation tree structure.
        Returns:
            A dictionary with nodes, edges, and metadata for tree visualization.
        """
        if not self.conversation_data or "messages" not in self.conversation_data:
            return {"nodes": [], "edges": [], "metadata": self.conversation_data.get("metadata", {})}

        messages = self.conversation_data["messages"]
        nodes = []
        edges = []
        active_leaf_id = self.conversation_data.get("metadata", {}).get("active_leaf")
        active_branch_path_ids = set(self._build_message_chain(self.conversation_data, self.active_branch))  # IDs of messages on the active branch

        for msg_id, msg_data in messages.items():
            content_preview = msg_data.get("content", "")
            content_preview = (content_preview[:75] + "...") if len(content_preview) > 75 else content_preview
            # Create a more detailed label for nodes
            node_label_lines = [f"{msg_data.get('type', 'N/A').capitalize()}: {content_preview.splitlines()[0] if content_preview else 'Empty'}"]
            if msg_data.get('type') == 'assistant' and msg_data.get('model'):
                node_label_lines.append(f"Model: {msg_data['model'].split('/')[-1]}")  # Short model name
            node_label_lines.append(f"Branch: {msg_data.get('branch_id', 'N/A')}")

            node_info = {
                "id": msg_id,
                "label": "\n".join(node_label_lines),
                "title": (f"ID: {msg_id}\nTimestamp: {msg_data.get('timestamp')}\n"
                          f"Branch: {msg_data.get('branch_id', 'N/A')}\nParent: {msg_data.get('parent_id', 'None')}\n"
                          f"Children: {len(msg_data.get('children', []))}\n"
                          f"Model: {msg_data.get('model', 'N/A') if msg_data.get('type') == 'assistant' else ''}\n"
                          f"Content:\n{msg_data.get('content', '')}"),  # Full content for tooltip
                "type": msg_data.get("type", "unknown"),
                "branch_id": msg_data.get("branch_id", "main"),
                "is_active_leaf": msg_id == active_leaf_id,  # Highlight the current end of active branch
                "is_on_active_branch": msg_id in active_branch_path_ids  # Highlight messages on active path
            }
            nodes.append(node_info)

            parent_id = msg_data.get("parent_id")
            if parent_id and parent_id in messages:  # If it has a parent that exists
                edges.append({"from": parent_id, "to": msg_id})
        return {"nodes": nodes, "edges": edges, "metadata": self.conversation_data.get("metadata", {})}

    async def list_conversations(self) -> List[Dict[str, Any]]:
        """Lists saved conversation files with their metadata."""
        return await super().list_conversation_files_info(self.base_directory)

    async def display_conversations(self) -> List[Dict[str, Any]]:
        """Displays saved conversations in a formatted table."""
        convs_info = await self.list_conversations()
        if not convs_info:
            print(f"{Colors.WARNING}No saved conversations found in {self.base_directory}{Colors.ENDC}")
            return []

        headers = ["#", "Title", "Provider", "Model", "Msgs", "Updated", "Sys.Instruct Preview", "File"]
        table_data = []
        for i, c_info in enumerate(convs_info, 1):
            updated_at_str = c_info.get("updated_at", "N/A")
            if updated_at_str != "N/A":  # Format date nicely
                try:
                    dt = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"));
                    updated_at_str = dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass  # Keep as is if parsing fails
            sys_instruct_prev = c_info.get("system_instruction_preview", "N/A")
            if sys_instruct_prev != "N/A" and len(sys_instruct_prev) > 30: sys_instruct_prev = sys_instruct_prev[:27] + "..."

            table_data.append([
                i, c_info.get("title", "Untitled")[:30], c_info.get("provider", "N/A"),
                c_info.get("model", "N/A").split('/')[-1][:20],  # Show short model name
                c_info.get("message_count", 0), updated_at_str, sys_instruct_prev,
                c_info.get("filename", "N/A")[:25]
            ])
        print(f"\n{Colors.HEADER}Saved Conversations ({self.base_directory}):{Colors.ENDC}")
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))
        return convs_info

    async def display_conversation_history(self) -> None:
        """Displays the history of the current active conversation branch."""
        if not self.conversation_data or "messages" not in self.conversation_data or not self.conversation_data["messages"]:
            print(f"{Colors.WARNING}No conversation history to display (no messages found).{Colors.ENDC}")
            return

        print(f"\n{Colors.HEADER}Conversation History:{Colors.ENDC}")
        conv_meta = self.conversation_data.get("metadata", {})
        title = conv_meta.get("title", "Untitled")
        provider_disp = conv_meta.get("provider", self.provider.provider_name if self.provider else "N/A")
        model_disp = conv_meta.get("model", self.current_model_name if self.provider else "N/A")
        system_instr_disp = conv_meta.get("system_instruction", self.system_instruction)  # Get from conv metadata or client

        print(f"{Colors.BOLD}Title: {title}{Colors.ENDC}")
        print(f"{Colors.BOLD}Provider: {provider_disp}{Colors.ENDC}, {Colors.BOLD}Model: {model_disp}{Colors.ENDC}")
        print(f"{Colors.BOLD}Active Branch: {self.active_branch}{Colors.ENDC}")
        print(f"{Colors.CYAN}System Instruction: {system_instr_disp[:100]}{'...' if len(system_instr_disp) > 100 else ''}{Colors.ENDC}\n")

        active_branch_stored_messages = self.get_conversation_history()  # Gets actual user/assistant messages
        if not active_branch_stored_messages:
            print(f"{Colors.YELLOW}No actual user/assistant messages in this conversation branch yet.{Colors.ENDC}")
            return

        for msg_data in active_branch_stored_messages:
            role = msg_data["role"]
            text_content = msg_data.get("content", "")
            timestamp_str = msg_data.get("timestamp", "")
            try:  # Format timestamp
                time_display = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).strftime("%H:%M:%S")
            except:
                time_display = "N/A"
            color_code = Colors.BLUE if role == "user" else Colors.GREEN
            print(f"{color_code}{role.capitalize()} ({time_display}): {Colors.ENDC}{text_content}\n")

    async def toggle_streaming(self) -> bool:
        """
        Toggles the client's session default streaming preference and updates global/conversation config.
        Returns the new streaming state.
        """
        self.use_streaming = not self.use_streaming  # Toggle client's session default
        print(f"{Colors.GREEN}Client session streaming mode is now {'enabled' if self.use_streaming else 'disabled'}.{Colors.ENDC}")

        # Update global config's default streaming preference
        if self.global_config:
            self.global_config.set("use_streaming", self.use_streaming)
            await asyncio.to_thread(self.global_config.save_config)  # Save config in a separate thread
            print(f"{Colors.CYAN}Global default streaming preference updated in config.{Colors.ENDC}")

        # Update current conversation's streaming preference if active
        if self.conversation_data and "metadata" in self.conversation_data:
            self.conversation_data["metadata"]["streaming_preference"] = self.use_streaming
            print(f"{Colors.CYAN}Streaming preference for current conversation '{self.conversation_name}' updated.{Colors.ENDC}")
            await self.save_conversation(quiet=True)  # Save change to conversation file
        return self.use_streaming