#!/usr/bin/env python3
"""
CannonAI Asynchronous Client - Provider-agnostic AI interaction client.

This module provides the asynchronous implementation of the CannonAI client,
building on conversation management logic from BaseClientFeatures and
delegating AI operations to a provider.
"""

import asyncio
import json  # For potential direct JSON ops if not fully handled by base
import uuid  # For potential direct ID generation if not fully handled by base
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, AsyncIterator

from tabulate import tabulate

from base_client import BaseClientFeatures, Colors  # Updated base class
from providers.base_provider import BaseAIProvider, ProviderError


class AsyncClient(BaseClientFeatures):  # Inherit from the new base
    """
    Asynchronous, provider-agnostic client for CannonAI.
    Manages conversations and interacts with an AI provider for responses.
    """
    VERSION = "2.2.0"  # Match BaseClientFeatures version or increment

    def __init__(self, provider: BaseAIProvider, conversations_dir: Optional[Path] = None):
        """
        Initialize the asynchronous AI client.

        Args:
            provider: An instance of a class that implements BaseAIProvider.
            conversations_dir: Directory to store conversations. Uses default if None.
        """
        # Initialize base class (handles conversations_dir)
        super().__init__(conversations_dir=conversations_dir)

        self.provider = provider

        # Conversation related state
        self.conversation_id: Optional[str] = None
        self.conversation_data: Dict[str, Any] = {}
        self.conversation_name: str = "New Conversation"

        # Client-level settings
        self.params: Dict[str, Any] = self.provider.get_default_params().copy()
        self.use_streaming: bool = False

        self.current_user_message_id: Optional[str] = None
        self.is_web_ui: bool = False

        self.ensure_directories()  # Call from base to ensure conv dir exists

    @property
    def active_branch(self) -> str:
        return self.conversation_data.get("metadata", {}).get("active_branch", "main")

    @active_branch.setter
    def active_branch(self, branch_id: str) -> None:
        if "metadata" not in self.conversation_data:
            self.conversation_data["metadata"] = {}
        self.conversation_data["metadata"]["active_branch"] = branch_id

    @property
    def current_model_name(self) -> str:
        return self.provider.config.model

    async def initialize_client(self) -> bool:
        """Initializes the configured AI provider."""
        print(f"Initializing provider: {self.provider.provider_name} with model {self.provider.config.model}")
        try:
            success = await self.provider.initialize()
            if success:
                print(f"{Colors.GREEN}Successfully initialized {self.provider.provider_name} provider.{Colors.ENDC}")
                self.params = self.provider.get_default_params().copy()
            else:
                print(f"{Colors.FAIL}Failed to initialize {self.provider.provider_name} provider.{Colors.ENDC}")
            return success
        except Exception as e:
            print(f"{Colors.FAIL}Error during provider initialization: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            return False

    async def start_new_conversation(self, title: Optional[str] = None, is_web_ui: bool = False) -> None:
        if self.conversation_id:
            await self.save_conversation(quiet=True)

        print(f"{Colors.CYAN}Starting new conversation...{Colors.ENDC}")
        self.conversation_id = self.generate_conversation_id()

        if title is None and not is_web_ui:
            title_prompt = "Enter a title for this conversation (or leave blank for timestamp): "
            title = input(title_prompt).strip()
        if not title:
            title = f"Conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.conversation_name = title
        self.conversation_data = self.create_metadata_structure(title, self.conversation_id)

        self.conversation_data["metadata"]["provider"] = self.provider.provider_name
        self.conversation_data["metadata"]["model"] = self.current_model_name
        self.conversation_data["metadata"]["params"] = self.params.copy()
        self.active_branch = "main"

        print(f"{Colors.GREEN}Started new conversation: {title} (Provider: {self.provider.provider_name}, Model: {self.current_model_name}), ID: {self.conversation_id[:8]}...{Colors.ENDC}")
        await self.save_conversation()

    async def save_conversation(self, quiet: bool = False) -> None:
        """Saves the current conversation data, ensuring provider/model metadata is current."""
        if not self.conversation_id or not self.conversation_data:
            if not quiet: print(f"{Colors.WARNING}No active conversation to save.{Colors.ENDC}")
            return

        if "metadata" in self.conversation_data:
            self.conversation_data["metadata"]["provider"] = self.provider.provider_name
            self.conversation_data["metadata"]["model"] = self.current_model_name
            self.conversation_data["metadata"]["params"] = self.params.copy()

        # Use the save_conversation_data from BaseClientFeatures
        await super().save_conversation_data(
            conversation_data=self.conversation_data,
            conversation_id=self.conversation_id,
            title=self.conversation_data.get("metadata", {}).get("title", "Untitled"),
            conversations_dir=self.conversations_dir,  # Ensure this is correct Path object
            quiet=quiet
        )

    async def load_conversation(self, name_or_idx: Optional[str] = None) -> None:
        """Loads a conversation, handling potential provider/model mismatches."""
        if self.conversation_id:
            await self.save_conversation(quiet=True)

        all_convs_info = await self.list_conversations()  # Uses new list_conversation_files_info
        if not all_convs_info:
            print(f"{Colors.WARNING}No saved conversations found in {self.conversations_dir}{Colors.ENDC}")
            return

        selected_conv_info: Optional[Dict[str, Any]] = None
        if name_or_idx:
            # Try matching by filename, then title, then ID, then index
            name_or_idx_lower = name_or_idx.lower()
            selected_conv_info = next((c for c in all_convs_info if c["filename"].lower() == name_or_idx_lower), None)
            if not selected_conv_info:
                selected_conv_info = next((c for c in all_convs_info if c["title"].lower() == name_or_idx_lower), None)
            if not selected_conv_info:
                selected_conv_info = next((c for c in all_convs_info if c.get("conversation_id") == name_or_idx), None)
            if not selected_conv_info:
                try:
                    idx = int(name_or_idx) - 1
                    if 0 <= idx < len(all_convs_info):
                        selected_conv_info = all_convs_info[idx]
                except ValueError:
                    pass  # Not a valid number

            if not selected_conv_info:
                print(f"{Colors.FAIL}Conversation '{name_or_idx}' not found.{Colors.ENDC}")
                await self.display_conversations()  # Show list again
                return
        else:  # Interactive selection
            await self.display_conversations()
            try:
                selection_str = input("\nEnter conversation number to load: ").strip()
                if not selection_str: print("Load cancelled."); return
                sel_num = int(selection_str) - 1
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
        if not loaded_data:
            return  # Error already printed by super method

        self.conversation_data = loaded_data
        self.conversation_id = loaded_data.get("conversation_id")

        metadata = self.conversation_data.get("metadata", {})
        loaded_provider = metadata.get("provider")
        loaded_model = metadata.get("model")
        loaded_params = metadata.get("params")

        self.conversation_name = metadata.get("title", "Untitled")
        self.active_branch = metadata.get("active_branch", "main")  # Set active branch from loaded data

        if loaded_provider and loaded_provider != self.provider.provider_name:
            print(f"{Colors.WARNING}Conversation was created with provider '{loaded_provider}'. "
                  f"Current active provider is '{self.provider.provider_name}'. "
                  f"Functionality may be affected. Consider switching providers if needed.{Colors.ENDC}")

        if loaded_model:
            if loaded_model != self.current_model_name:
                print(f"{Colors.CYAN}Conversation used model '{loaded_model}'. Updating current session to use this model.{Colors.ENDC}")
                self.provider.config.model = loaded_model
                # Ensure conversation metadata reflects the model being used
            self.conversation_data["metadata"]["model"] = self.provider.config.model

        if loaded_params:
            self.params = loaded_params.copy()
            self.conversation_data["metadata"]["params"] = self.params.copy()  # Also store in conv metadata
            print(f"{Colors.CYAN}Loaded generation parameters from conversation.{Colors.ENDC}")

        print(f"{Colors.GREEN}Conversation '{self.conversation_name}' loaded (ID: {self.conversation_id[:8]}...). Active branch: '{self.active_branch}'.{Colors.ENDC}")
        await self.display_conversation_history()

    async def send_message(self, message: str) -> Optional[str]:  # CLI Path
        if not message.strip(): return None
        if not self.provider.is_initialized:
            print(f"{Colors.FAIL}Provider '{self.provider.provider_name}' is not initialized.{Colors.ENDC}")
            return None
        if not self.conversation_id or not self.conversation_data:
            print(f"{Colors.CYAN}No active conversation. Starting a new one...{Colors.ENDC}")
            await self.start_new_conversation(is_web_ui=self.is_web_ui)
            if not self.conversation_id:
                print(f"{Colors.FAIL}Failed to start a new conversation. Cannot send message.{Colors.ENDC}")
                return None

        try:
            parent_id = self._get_last_message_id(self.conversation_data, self.active_branch)
            user_msg_obj = self.create_message_structure(role="user", text=message, parent_id=parent_id, branch_id=self.active_branch)
            self._add_message_to_conversation(self.conversation_data, user_msg_obj)
            user_msg_id = user_msg_obj["id"]

            history_for_provider = self._build_history_for_provider()
            current_params = self.conversation_data.get("metadata", {}).get("params", self.params).copy()
            response_text = ""
            token_usage = {}

            if self.use_streaming:
                print(f"\r{Colors.CYAN}{self.provider.provider_name} is thinking... (streaming){Colors.ENDC}", end="", flush=True)
                print("\r" + " " * (len(self.provider.provider_name) + 30) + "\r", end="", flush=True)
                print(f"{Colors.GREEN}AI: {Colors.ENDC}", end="", flush=True)

                stream_generator = await self.provider.generate_response(history_for_provider, current_params, stream=True)
                async for chunk_data in stream_generator:
                    if chunk_data.get("error"):
                        response_text = f"Error: {chunk_data['error']}"
                        print(f"\n{Colors.FAIL}{response_text}{Colors.ENDC}");
                        break
                    if chunk_data.get("chunk"):
                        print(chunk_data["chunk"], end="", flush=True)
                        response_text += chunk_data["chunk"]
                    if chunk_data.get("done"):
                        token_usage = chunk_data.get("token_usage", {})
                        break
                print()
            else:
                print(f"\r{Colors.CYAN}{self.provider.provider_name} is thinking...{Colors.ENDC}", end="", flush=True)
                raw_response_text, metadata = await self.provider.generate_response(history_for_provider, current_params, stream=False)
                print("\r" + " " * (len(self.provider.provider_name) + 20) + "\r", end="", flush=True)
                response_text = raw_response_text or ""
                token_usage = metadata.get("token_usage", {})
                print(f"\n{Colors.GREEN}AI: {Colors.ENDC}{response_text}")

            ai_msg_obj = self.create_message_structure(
                role="assistant", text=response_text, model=self.current_model_name,
                params=current_params, token_usage=token_usage,
                parent_id=user_msg_id, branch_id=self.active_branch
            )
            self._add_message_to_conversation(self.conversation_data, ai_msg_obj)
            await self.save_conversation(quiet=True)
            return response_text
        except Exception as e:
            print(f"{Colors.FAIL}Error generating response via {self.provider.provider_name}: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            err_parent_id = locals().get('user_msg_id', self._get_last_message_id(self.conversation_data, self.active_branch))
            err_msg_text = f"Error: Provider communication failed. {str(e)[:200]}"
            error_message_obj = self.create_message_structure(
                role="assistant", text=err_msg_text, model=self.current_model_name,
                params=self.params, parent_id=err_parent_id, branch_id=self.active_branch
            )
            if self.conversation_data and self.conversation_id:
                self._add_message_to_conversation(self.conversation_data, error_message_obj)
                await self.save_conversation(quiet=True)
            return None

    def _build_history_for_provider(self) -> List[Dict[str, str]]:
        if not self.conversation_data or "messages" not in self.conversation_data:
            return []
        message_chain_ids = self._build_message_chain(self.conversation_data, self.active_branch)
        provider_history = []
        messages_dict = self.conversation_data.get("messages", {})
        for msg_id in message_chain_ids:
            msg = messages_dict.get(msg_id, {})
            if msg.get("type") in ["user", "assistant"]:
                provider_history.append({"role": msg["type"], "content": msg.get("content", "")})
        return self.provider.normalize_messages(provider_history)

    async def get_available_models(self) -> List[Dict[str, Any]]:
        if not self.provider.is_initialized:
            print(f"{Colors.FAIL}Provider '{self.provider.provider_name}' is not initialized.{Colors.ENDC}");
            return []
        try:
            return await self.provider.list_models()
        except Exception as e:
            print(f"{Colors.FAIL}Error getting models from provider '{self.provider.provider_name}': {e}{Colors.ENDC}")
            return []

    async def display_models(self) -> None:  # For CLI
        models = await self.get_available_models()
        if not models:
            print(f"{Colors.WARNING}No models available for provider: {self.provider.provider_name}.{Colors.ENDC}")
            return
        headers = ["#", "Name", "Display Name", "Input Tokens", "Output Tokens"]
        table_data = [[i + 1, m.get("name", "N/A"), m.get("display_name", "N/A"), m.get("input_token_limit", "N/A"), m.get("output_token_limit", "N/A")] for i, m in enumerate(models)]
        print(f"\nAvailable models for provider: {Colors.BOLD}{self.provider.provider_name}{Colors.ENDC}")
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))

    async def select_model(self) -> None:  # For CLI
        models = await self.get_available_models()
        if not models:
            print(f"{Colors.WARNING}No models to select for provider: {self.provider.provider_name}.{Colors.ENDC}");
            return
        await self.display_models()
        try:
            selection_str = input(f"\nEnter model number for {self.provider.provider_name} (or press Enter to cancel): ").strip()
            if not selection_str: print("Model selection cancelled."); return
            selection_idx = int(selection_str) - 1
            if 0 <= selection_idx < len(models):
                new_model_name = models[selection_idx]["name"]
                self.provider.config.model = new_model_name
                if self.conversation_data and "metadata" in self.conversation_data:
                    self.conversation_data["metadata"]["model"] = new_model_name
                    self.conversation_data["metadata"]["provider"] = self.provider.provider_name
                    print(f"{Colors.CYAN}Conversation model updated. Saving...{Colors.ENDC}")
                    await self.save_conversation(quiet=True)
                print(f"{Colors.GREEN}Selected model: {self.current_model_name} (Provider: {self.provider.provider_name}){Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}Invalid selection number.{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.FAIL}Invalid input. Please enter a number.{Colors.ENDC}")

    async def customize_params(self) -> None:  # For CLI
        current_params_for_editing = self.params.copy()
        if self.conversation_data and "metadata" in self.conversation_data and "params" in self.conversation_data["metadata"]:
            current_params_for_editing.update(self.conversation_data["metadata"]["params"])
        print(f"\n{Colors.HEADER}Customizing Parameters for Provider: {self.provider.provider_name} (Model: {self.current_model_name}){Colors.ENDC}")
        provider_param_keys = self.provider.get_default_params().keys()
        print(f"{Colors.CYAN}Current values are shown in [brackets]. Press Enter to keep current value.{Colors.ENDC}")
        editable_params = {}
        try:
            for key in provider_param_keys:
                prompt_text = f"{key.replace('_', ' ').capitalize()} [{current_params_for_editing.get(key, 'Not set')}]: "
                value_str = input(prompt_text).strip()
                if value_str:
                    try:
                        if '.' in value_str:
                            editable_params[key] = float(value_str)
                        else:
                            editable_params[key] = int(value_str)
                    except ValueError:
                        if value_str.lower() in ['true', 'false']:
                            editable_params[key] = value_str.lower() == 'true'
                        else:
                            editable_params[key] = value_str
            if editable_params:
                self.params.update(editable_params)
                if self.conversation_data and "metadata" in self.conversation_data:
                    self.conversation_data["metadata"].setdefault("params", {}).update(editable_params)
                    print(f"{Colors.CYAN}Conversation parameters updated. Saving...{Colors.ENDC}")
                    await self.save_conversation(quiet=True)
                print(f"{Colors.GREEN}Generation parameters updated successfully.{Colors.ENDC}")
            else:
                print("No changes made to parameters.")
        except ValueError as e:
            print(f"{Colors.FAIL}Invalid input: {e}. Parameters not updated.{Colors.ENDC}")

    # --- GUI Specific Methods ---
    def add_user_message(self, message: str) -> None:  # For GUI path (SYNC)
        if not self.conversation_id or not self.conversation_data:
            print(f"{Colors.WARNING}[Client for GUI] No active conversation. Creating a default one for this session.{Colors.ENDC}")
            self.conversation_id = self.generate_conversation_id()
            self.conversation_data = self.create_metadata_structure(f"UI_Session_Conv_{self.conversation_id[:6]}", self.conversation_id)
            self.conversation_data["metadata"]["provider"] = self.provider.provider_name
            self.conversation_data["metadata"]["model"] = self.current_model_name
            self.conversation_data["metadata"]["params"] = self.params.copy()
            self.active_branch = "main"
        parent_id = self._get_last_message_id(self.conversation_data, self.active_branch)
        user_msg = self.create_message_structure(role="user", text=message, parent_id=parent_id, branch_id=self.active_branch)
        self._add_message_to_conversation(self.conversation_data, user_msg)
        self.current_user_message_id = user_msg["id"]

    def add_assistant_message(self, message_text: str, token_usage: Optional[Dict[str, Any]] = None) -> None:  # For GUI path (SYNC)
        text_to_add = message_text if message_text is not None else ""
        parent_id_for_ai = self.current_user_message_id
        if not parent_id_for_ai:
            parent_id_for_ai = self._get_last_message_id(self.conversation_data, self.active_branch)
            print(f"{Colors.WARNING}[Client for GUI] current_user_message_id not set for AI msg. Using last in branch: {parent_id_for_ai}{Colors.ENDC}")
        ai_model_name = self.conversation_data.get("metadata", {}).get("model", self.current_model_name)
        ai_params = self.conversation_data.get("metadata", {}).get("params", self.params).copy()
        ai_msg = self.create_message_structure(role="assistant", text=text_to_add, model=ai_model_name,
                                               params=ai_params, token_usage=token_usage,
                                               parent_id=parent_id_for_ai, branch_id=self.active_branch)
        self._add_message_to_conversation(self.conversation_data, ai_msg)
        self.current_user_message_id = None

    async def get_response(self) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:  # For non-streaming UI (ASYNC)
        if not self.current_user_message_id:
            print(f"{Colors.FAIL}[Client for GUI] User message not processed before requesting AI response.{Colors.ENDC}")
            return "Error: User message not processed first.", None
        if not self.provider.is_initialized:
            print(f"{Colors.FAIL}[Client for GUI] Provider not initialized.{Colors.ENDC}")
            return "Error: Provider not initialized.", None
        if not self.conversation_data or not self.conversation_id:
            print(f"{Colors.FAIL}[Client for GUI] Conversation data not initialized.{Colors.ENDC}")
            return "Error: Conversation data not initialized.", None

        history_for_provider = self._build_history_for_provider()
        current_params = self.conversation_data.get("metadata", {}).get("params", self.params).copy()
        try:
            response_text, metadata = await self.provider.generate_response(history_for_provider, current_params, stream=False)
            return response_text, metadata.get("token_usage", {})
        except Exception as e:
            print(f"{Colors.FAIL}[Client for GUI] Non-streaming provider error: {e}{Colors.ENDC}")
            import traceback;
            traceback.print_exc()
            return f"Error: {str(e)}", None

    async def get_streaming_response(self) -> AsyncIterator[Dict[str, Any]]:  # For streaming UI (ASYNC GEN)
        if not self.current_user_message_id:
            yield {"error": "User message not processed before requesting AI stream."};
            return
        if not self.provider.is_initialized:
            yield {"error": f"Provider '{self.provider.provider_name}' not initialized."};
            return
        if not self.conversation_data or not self.conversation_id:
            yield {"error": "Conversation data not initialized."};
            return

        user_message_id_for_parenting = self.current_user_message_id
        history_for_provider = self._build_history_for_provider()
        current_params = self.conversation_data.get("metadata", {}).get("params", self.params).copy()
        current_model_for_stream = self.conversation_data.get("metadata", {}).get("model", self.current_model_name)
        full_response_text = "";
        final_token_usage = {}
        try:
            stream_generator = await self.provider.generate_response(history_for_provider, current_params, stream=True)
            async for chunk_data in stream_generator:
                if chunk_data.get("error"): yield chunk_data; return
                if chunk_data.get("chunk"):
                    full_response_text += chunk_data["chunk"]
                    yield {"chunk": chunk_data["chunk"]}
                if chunk_data.get("done"):
                    final_token_usage = chunk_data.get("token_usage", {})
                    # If provider's "done" event also contains the full response, use it.
                    # Otherwise, we use our accumulated full_response_text.
                    full_response_text = chunk_data.get("full_response", full_response_text)
                    break

            self.add_assistant_message(full_response_text, final_token_usage)
            assistant_msg_id = self._get_last_message_id(self.conversation_data, self.active_branch)
            await self.save_conversation(quiet=True)
            yield {"done": True, "full_response": full_response_text,
                   "conversation_id": self.conversation_id, "message_id": assistant_msg_id,
                   "parent_id": user_message_id_for_parenting,
                   "model": current_model_for_stream, "token_usage": final_token_usage}
        except Exception as e:
            print(f"{Colors.FAIL}[Client for GUI] Streaming provider error: {e}{Colors.ENDC}")
            import traceback;
            traceback.print_exc()
            yield {"error": str(e)}

    def get_conversation_history(self) -> List[Dict[str, Any]]:  # For UI display (SYNC)
        """Gets the linear history of the active branch for display."""
        hist_list = []
        if not self.conversation_data or "messages" not in self.conversation_data: return hist_list

        active_branch_ids = self._build_message_chain(self.conversation_data, self.active_branch)
        messages_dict = self.conversation_data.get("messages", {})

        for mid in active_branch_ids:
            msg = messages_dict.get(mid, {})
            if msg.get("type") in ["user", "assistant"]:
                hist_list.append({
                    'role': msg["type"],
                    'content': msg.get("content", ""),
                    'id': mid,
                    'model': msg.get("model"),  # Will be None for user messages
                    'timestamp': msg.get("timestamp"),
                    'parent_id': msg.get("parent_id"),
                    'token_usage': msg.get("token_usage")  # Will be None for user messages
                })
        return hist_list

    async def retry_message(self, assistant_message_id_to_retry: str) -> Dict[str, Any]:
        print(f"[Client] Retrying assistant message: {assistant_message_id_to_retry}")
        if not self.conversation_data or "messages" not in self.conversation_data:
            raise ValueError("No active conversation or messages found to retry.")
        messages_dict = self.conversation_data["messages"]
        original_assistant_msg = messages_dict.get(assistant_message_id_to_retry)
        if not original_assistant_msg or original_assistant_msg.get("type") != "assistant":
            raise ValueError(f"Message ID '{assistant_message_id_to_retry}' is not a valid assistant message to retry.")
        parent_user_id = original_assistant_msg.get("parent_id")
        if not parent_user_id or parent_user_id not in messages_dict:
            raise ValueError("Original assistant message for retry has no valid parent user message.")

        original_branch_context = original_assistant_msg.get("branch_id", self.active_branch)
        history_ids_for_retry = self._build_message_chain_up_to_id(parent_user_id, original_branch_context)

        history_for_provider_retry = []
        for mid in history_ids_for_retry:
            msg = messages_dict[mid]
            history_for_provider_retry.append({"role": msg["type"], "content": msg["content"]})

        normalized_history_for_retry = self.provider.normalize_messages(history_for_provider_retry)
        current_model_for_retry = self.conversation_data.get("metadata", {}).get("model", self.current_model_name)
        current_params_for_retry = self.conversation_data.get("metadata", {}).get("params", self.params).copy()

        try:
            new_response_text, metadata = await self.provider.generate_response(
                normalized_history_for_retry, current_params_for_retry, stream=False)
            new_token_usage = metadata.get("token_usage", {})
            new_branch_id = f"branch_{uuid.uuid4().hex[:8]}"
            new_assistant_msg_obj = self.create_message_structure(
                role="assistant", text=new_response_text or "", model=current_model_for_retry,
                params=current_params_for_retry, token_usage=new_token_usage,
                parent_id=parent_user_id, branch_id=new_branch_id)
            self._add_message_to_conversation(self.conversation_data, new_assistant_msg_obj)

            self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            self.active_branch = new_branch_id
            self.conversation_data["metadata"]["active_leaf"] = new_assistant_msg_obj["id"]
            await self.save_conversation(quiet=True)

            parent_user_msg_obj = messages_dict[parent_user_id]
            sibling_ids = parent_user_msg_obj.get("children", [])
            new_msg_idx = sibling_ids.index(new_assistant_msg_obj["id"]) if new_assistant_msg_obj["id"] in sibling_ids else -1

            print(f"[Client] Retry successful. New assistant message ID: {new_assistant_msg_obj['id']} on new branch '{new_branch_id}'.")
            return {"message": new_assistant_msg_obj, "sibling_index": new_msg_idx, "total_siblings": len(sibling_ids)}
        except Exception as e:
            print(f"{Colors.FAIL}Error during retry message generation: {e}{Colors.ENDC}")
            import traceback;
            traceback.print_exc()
            raise

    def _build_message_chain_up_to_id(self, target_leaf_id: str, branch_id_context: Optional[str] = None) -> List[str]:
        """Helper to build message chain for a specific branch, ending at target_leaf_id."""
        # This version takes target_leaf_id directly from BaseClientFeatures.
        return super()._build_message_chain_up_to_id(self.conversation_data, target_leaf_id, branch_id_context)

    async def switch_to_sibling(self, message_id: str, direction: str) -> Dict[str, Any]:
        """Switches the active branch to a sibling of the given assistant message."""
        print(f"[Client] Switching {direction} from message: {message_id}")
        if not self.conversation_data or "messages" not in self.conversation_data:
            raise ValueError("No active conversation or messages found to switch sibling.")

        messages = self.conversation_data["messages"]
        current_message_obj = messages.get(message_id)
        if not current_message_obj:
            raise ValueError(f"Message {message_id} not found.")

        parent_id: Optional[str] = None
        siblings_ids: List[str] = []
        current_index_in_siblings: int = -1

        if current_message_obj["type"] == "assistant":
            parent_id = current_message_obj.get("parent_id")
            if parent_id and parent_id in messages:
                parent_message_obj = messages[parent_id]
                siblings_ids = parent_message_obj.get("children", [])
                if message_id in siblings_ids:
                    current_index_in_siblings = siblings_ids.index(message_id)
            else:  # Assistant message with no parent or parent not found (should not happen)
                siblings_ids = [message_id]
                current_index_in_siblings = 0
        elif current_message_obj["type"] == "user":  # If user message, "siblings" are its direct children
            parent_id = message_id  # User message is the parent for its children
            siblings_ids = current_message_obj.get("children", [])
            # current_index is not applicable in the same way, target one of children
            # For "none" direction, we just activate this user message's branch.
            # For prev/next, it means choosing a different child of this user message.
            # This logic needs refinement if navigating children of a user message.
            # For now, assume navigation is primarily for assistant message alternatives.
            print(f"{Colors.WARNING}Navigating from a user message; behavior might be to activate its branch or select a child.{Colors.ENDC}")

        if not siblings_ids:  # No siblings or children found
            print(f"{Colors.WARNING}No siblings found for message {message_id} to navigate {direction}. Staying on current branch.{Colors.ENDC}")
            # Ensure active_branch and active_leaf are correctly set to current state
            self.active_branch = current_message_obj.get("branch_id", self.active_branch)
            self.conversation_data["metadata"]["active_leaf"] = message_id
            return {"message": current_message_obj, "sibling_index": current_index_in_siblings, "total_siblings": len(siblings_ids)}

        new_active_message_obj = current_message_obj
        new_sibling_idx = current_index_in_siblings

        if direction == "prev" and current_index_in_siblings > 0:
            new_sibling_idx = current_index_in_siblings - 1
            new_active_message_obj = messages[siblings_ids[new_sibling_idx]]
        elif direction == "next" and current_index_in_siblings < len(siblings_ids) - 1:
            new_sibling_idx = current_index_in_siblings + 1
            new_active_message_obj = messages[siblings_ids[new_sibling_idx]]
        elif direction == "none":  # Activate the branch of the current message_id
            new_active_message_obj = current_message_obj  # Stays the same
            new_sibling_idx = current_index_in_siblings  # Stays the same
        else:
            print(f"{Colors.WARNING}Navigation '{direction}' from message {message_id} resulted in no change (edge or invalid direction).{Colors.ENDC}")
            # Still return info about current state

        self.active_branch = new_active_message_obj.get("branch_id", self.active_branch)
        self.conversation_data["metadata"]["active_leaf"] = new_active_message_obj["id"]
        self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()

        await self.save_conversation(quiet=True)

        print(f"[Client] Switched. New active message: {new_active_message_obj['id'][:8]}, Branch: {self.active_branch}, Index: {new_sibling_idx}")
        return {
            "message": new_active_message_obj,
            "sibling_index": new_sibling_idx,
            "total_siblings": len(siblings_ids)
        }

    async def get_message_siblings(self, message_id: str) -> Dict[str, Any]:
        """Gets sibling information for a given message ID."""
        if not self.conversation_data or "messages" not in self.conversation_data:
            raise ValueError("No conversation data available.")

        messages = self.conversation_data["messages"]
        target_msg_obj = messages.get(message_id)
        if not target_msg_obj:
            raise ValueError(f"Message with ID '{message_id}' not found.")

        parent_id_for_siblings: Optional[str] = None
        sibling_ids: List[str] = []
        current_idx: int = -1

        if target_msg_obj["type"] == "assistant":
            parent_id_for_siblings = target_msg_obj.get("parent_id")
            if parent_id_for_siblings and parent_id_for_siblings in messages:
                parent_msg_obj = messages[parent_id_for_siblings]
                sibling_ids = parent_msg_obj.get("children", [])
                if message_id in sibling_ids:
                    current_idx = sibling_ids.index(message_id)
            else:  # Assistant message with no parent, consider it its own sibling for consistency
                sibling_ids = [message_id]
                current_idx = 0
        elif target_msg_obj["type"] == "user":
            # For a user message, "siblings" in this context usually means its children (assistant responses)
            # However, the term "sibling" implies same parent. A user message doesn't have siblings in the same way.
            # Let's return its children as "potential next messages" rather than "siblings".
            # The UI might need to interpret this differently.
            # For now, let's stick to the definition of siblings having the same parent.
            # So, a user message has no siblings in this model unless we consider alternative user messages (not supported yet).
            # Or, this method is primarily for assistant messages.
            # Let's assume, for now, this is about assistant message alternatives.
            # If called with a user message, we can return its children.
            # parent_id_for_siblings = message_id # The user message itself is the "parent" of its responses
            # sibling_ids = target_msg_obj.get("children", [])
            # current_idx = -1 # Not applicable for user message itself among its children
            return {
                "message_id": message_id, "parent_id": target_msg_obj.get("parent_id"),
                "siblings": [], "current_index": -1, "total": 0,
                "note": "Sibling navigation is primarily for assistant message alternatives."
            }

        return {
            "message_id": message_id,
            "parent_id": parent_id_for_siblings,
            "siblings": sibling_ids,
            "current_index": current_idx,
            "total": len(sibling_ids)
        }

    async def get_conversation_tree(self) -> Dict[str, Any]:
        """Builds a graph structure (nodes and edges) of the current conversation."""
        if not self.conversation_data or "messages" not in self.conversation_data:
            return {"nodes": [], "edges": [], "metadata": self.conversation_data.get("metadata", {})}

        messages = self.conversation_data["messages"]
        nodes = []
        edges = []

        active_leaf_id = self.conversation_data.get("metadata", {}).get("active_leaf")
        active_branch_path_ids = set(self._build_message_chain(self.conversation_data, self.active_branch))

        for msg_id, msg_data in messages.items():
            content_preview = msg_data.get("content", "")
            content_preview = (content_preview[:75] + "...") if len(content_preview) > 75 else content_preview

            node_info = {
                "id": msg_id,
                "label": f"{msg_data.get('type', 'N/A').capitalize()}: {content_preview.splitlines()[0]}",  # Use first line for label
                "title": (f"ID: {msg_id}\nTimestamp: {msg_data.get('timestamp')}\n"
                          f"Branch: {msg_data.get('branch_id', 'N/A')}\n"
                          f"Model: {msg_data.get('model', 'N/A') if msg_data.get('type') == 'assistant' else ''}\n"
                          f"Content:\n{msg_data.get('content', '')}"),  # Full content for tooltip
                "type": msg_data.get("type", "unknown"),
                "branch_id": msg_data.get("branch_id", "main"),
                "is_active_leaf": msg_id == active_leaf_id,
                "is_on_active_branch": msg_id in active_branch_path_ids
            }
            nodes.append(node_info)

            # Edges from parent to this child
            parent_id = msg_data.get("parent_id")
            if parent_id and parent_id in messages:  # Ensure parent exists before creating edge
                edges.append({"from": parent_id, "to": msg_id})

        return {"nodes": nodes, "edges": edges, "metadata": self.conversation_data.get("metadata", {})}

    async def list_conversations(self) -> List[Dict[str, Any]]:  # CLI display support
        """Lists summary info for all conversation files. Uses method from base."""
        return await super().list_conversation_files_info(self.conversations_dir)

    async def display_conversations(self) -> List[Dict[str, Any]]:  # CLI display support
        """Displays saved conversations in a table. Returns the list of conv info."""
        convs_info = await self.list_conversations()
        if not convs_info:
            print(f"{Colors.WARNING}No saved conversations found in {self.conversations_dir}{Colors.ENDC}")
            return []

        headers = ["#", "Title", "Provider", "Model", "Msgs", "Updated", "File"]
        table_data = []
        for i, c_info in enumerate(convs_info, 1):
            updated_at_str = c_info.get("updated_at", "N/A")
            if updated_at_str != "N/A":
                try:
                    dt = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                    updated_at_str = dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass  # Keep original if parsing fails

            table_data.append([
                i,
                c_info.get("title", "Untitled")[:30],  # Truncate title for display
                c_info.get("provider", "N/A"),
                c_info.get("model", "N/A").split('/')[-1][:20],  # Shorten model name
                c_info.get("message_count", 0),
                updated_at_str,
                c_info.get("filename", "N/A")[:25]  # Truncate filename
            ])
        print(f"\n{Colors.HEADER}Saved Conversations ({self.conversations_dir}):{Colors.ENDC}")
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))
        return convs_info  # Return the full info list

    async def display_conversation_history(self) -> None:  # CLI display support
        """Displays the history of the active branch of the current conversation."""
        if not self.conversation_data or "messages" not in self.conversation_data or not self.conversation_data["messages"]:
            print(f"{Colors.WARNING}No conversation history to display.{Colors.ENDC}");
            return

        print(f"\n{Colors.HEADER}Conversation History:{Colors.ENDC}")
        metadata = self.conversation_data.get("metadata", {})
        title = metadata.get("title", "Untitled")
        provider_disp = metadata.get("provider", self.provider.provider_name if self.provider else "N/A")
        model_disp = metadata.get("model", self.current_model_name if self.provider else "N/A")

        print(f"{Colors.BOLD}Title: {title}{Colors.ENDC}")
        print(f"{Colors.BOLD}Provider: {provider_disp}{Colors.ENDC}")
        print(f"{Colors.BOLD}Model: {model_disp}{Colors.ENDC}")
        print(f"{Colors.BOLD}Active Branch: {self.active_branch}{Colors.ENDC}\n")

        active_branch_message_ids = self._build_message_chain(self.conversation_data, self.active_branch)
        messages_dict = self.conversation_data.get("messages", {})

        for msg_id in active_branch_message_ids:
            msg_data = messages_dict.get(msg_id, {})
            if msg_data.get("type") in ["user", "assistant"]:
                role = msg_data["type"]
                text_content = msg_data.get("content", "")
                timestamp_str = msg_data.get("timestamp", "")
                try:
                    time_display = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).strftime("%H:%M:%S")
                except:
                    time_display = "N/A"

                color_code = Colors.BLUE if role == "user" else Colors.GREEN
                print(f"{color_code}{role.capitalize()} ({time_display}): {Colors.ENDC}{text_content}\n")

    async def toggle_streaming(self) -> bool:  # For CLI
        """Toggles the client's default streaming preference for CLI interactions."""
        self.use_streaming = not self.use_streaming
        print(f"{Colors.GREEN}CLI streaming mode is now {'enabled' if self.use_streaming else 'disabled'}.{Colors.ENDC}")
        return self.use_streaming
