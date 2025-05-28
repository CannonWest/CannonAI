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
        super().__init__(api_key, model, conversations_dir)
        self.conversation_id: Optional[str] = None
        self.conversation_data: Dict[str, Any] = {}
        self.params: Dict[str, Any] = self.default_params.copy()
        self.use_streaming: bool = False
        self.conversation_name: str = "New Conversation"
        self.current_user_message: Optional[str] = None
        self.current_user_message_id: Optional[str] = None
        self.is_web_ui: bool = False
        self.conversations_dir = self.base_directory
        self.ensure_directories(self.conversations_dir)

    @property
    def active_branch(self) -> str:
        return self.conversation_data.get("metadata", {}).get("active_branch", "main")

    @active_branch.setter
    def active_branch(self, branch_id: str) -> None:
        if "metadata" not in self.conversation_data:
            self.conversation_data["metadata"] = {}
        self.conversation_data["metadata"]["active_branch"] = branch_id

    async def initialize_client(self) -> bool:
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
        return str(uuid.uuid4())

    def _add_message_to_conversation(self, message: Dict[str, Any]) -> None:
        msg_id = message["id"]
        parent_id = message.get("parent_id")
        branch_id = message.get("branch_id", "main")
        if not self.conversation_data: return
        self.conversation_data.setdefault("messages", {})
        self.conversation_data.setdefault("branches", {})
        self.conversation_data.setdefault("metadata", {})
        self.conversation_data["metadata"].setdefault("active_branch", "main")
        self.conversation_data["messages"][msg_id] = message
        if parent_id and parent_id in self.conversation_data["messages"]:
            parent = self.conversation_data["messages"][parent_id]
            parent.setdefault("children", [])
            if msg_id not in parent["children"]:
                parent["children"].append(msg_id)
        if branch_id not in self.conversation_data["branches"]:
            self.conversation_data["branches"][branch_id] = {
                "created_at": datetime.now().isoformat(), "last_message": None, "message_count": 0}
        branch_info = self.conversation_data["branches"][branch_id]
        branch_info["last_message"] = msg_id
        branch_info["message_count"] = sum(1 for m_data in self.conversation_data["messages"].values() if m_data.get("branch_id") == branch_id)
        if branch_id == self.active_branch:
            self.conversation_data["metadata"]["active_leaf"] = msg_id

    def _get_last_message_id(self, branch_id: Optional[str] = None) -> Optional[str]:
        if not self.conversation_data: return None
        branch_id = branch_id or self.active_branch
        return self.conversation_data.get("branches", {}).get(branch_id, {}).get("last_message")

    def _convert_old_to_new_format(self) -> None:
        if not hasattr(self, 'conversation_history') or not self.conversation_history: return
        print(f"{Colors.CYAN}Converting old format to new format...{Colors.ENDC}")
        title = "Converted Conversation"
        conv_id = self.conversation_id or self.generate_conversation_id()
        meta_item = next((item for item in self.conversation_history if item.get("type") == "metadata"), None)
        if meta_item:
            meta_content = meta_item.get("content", {})
            title = meta_content.get("title", title)
            self.model = meta_content.get("model", self.model)
            if "params" in meta_content: self.params = meta_content["params"]
        self.conversation_data = self.create_metadata_structure(title, conv_id)
        self.conversation_data["metadata"]["model"] = self.model
        self.conversation_data["metadata"]["params"] = self.params.copy()
        prev_msg_id = None
        for item in self.conversation_history:
            if item.get("type") == "message":
                content = item.get("content", {}); role = content.get("role"); text = content.get("text", "")
                if role in ["user", "assistant", "ai"]:
                    role = "assistant" if role == "ai" else role
                    msg = self.create_message_structure(role=role, text=text,
                        model=self.model if role=="assistant" else None,
                        params=self.params if role=="assistant" else {},
                        parent_id=prev_msg_id, branch_id="main")
                    self._add_message_to_conversation(msg); prev_msg_id = msg["id"]
        if prev_msg_id:
            self.conversation_data["metadata"]["active_leaf"] = prev_msg_id
            self.conversation_data["branches"]["main"]["message_count"] = sum(1 for m in self.conversation_data["messages"].values() if m.get("branch_id") == "main")
        print(f"{Colors.GREEN}Converted {len(self.conversation_data.get('messages', {}))} messages.{Colors.ENDC}")

    async def start_new_conversation(self, title: Optional[str] = None, is_web_ui: bool = False) -> None:
        print(f"{Colors.CYAN}Starting new conversation...{Colors.ENDC}")
        self.conversation_id = self.generate_conversation_id()
        if title is None and not is_web_ui: title = input("Title (blank for timestamp): ")
        if not title: title = f"Conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.conversation_name = title
        self.conversation_data = self.create_metadata_structure(title, self.conversation_id)
        self.conversation_data["metadata"]["model"] = self.model
        self.conversation_data["metadata"]["params"] = self.params.copy()
        self.active_branch = "main"
        print(f"{Colors.GREEN}Started: {title}, ID: {self.conversation_id[:8]}..., Branch: {self.active_branch}{Colors.ENDC}")
        await self.save_conversation()

    async def retry_message(self, message_id: str) -> Dict[str, Any]:
        print(f"[DEBUG AsyncClient] Retrying based on assistant message: {message_id}")
        if not self.conversation_data or "messages" not in self.conversation_data: raise ValueError("No active conversation/messages")
        messages = self.conversation_data["messages"]
        orig_asst_msg = messages.get(message_id);
        if not orig_asst_msg or orig_asst_msg["type"] != "assistant": raise ValueError("Can only retry assistant message.")
        parent_user_id = orig_asst_msg.get("parent_id");
        if not parent_user_id: raise ValueError("Assistant message has no parent.")
        parent_user_msg = messages.get(parent_user_id)
        if not parent_user_msg or parent_user_msg["type"] != "user": raise ValueError("Parent is not a user message.")

        print(f"[DEBUG AsyncClient] Found parent user message: {parent_user_id}, Content: {parent_user_msg['content'][:50]}...")
        hist_chain_ids = self._build_message_chain(self.conversation_data, parent_user_msg.get("branch_id", "main"))
        try:
            parent_idx = hist_chain_ids.index(parent_user_id)
            api_hist_ids = hist_chain_ids[:parent_idx + 1]
        except ValueError:
            print(f"{Colors.WARNING}Parent {parent_user_id} not in its branch chain. Fallback history build.{Colors.ENDC}")
            api_hist_ids = [parent_user_id] # Simplified fallback: just the parent user message

        api_history = [types.Content(role="user" if messages[mid]["type"]=="user" else "model", parts=[types.Part.from_text(text=messages[mid]["content"])]) for mid in api_hist_ids]
        print(f"[DEBUG AsyncClient] Built API history ({len(api_history)} msgs) for retry.")

        try:
            curr_model = self.conversation_data.get("metadata", {}).get("model", self.model)
            curr_params = self.conversation_data.get("metadata", {}).get("params", self.params)
            api_resp = await self.client.aio.models.generate_content(model=curr_model, contents=api_history, config=types.GenerateContentConfig(**curr_params))
            resp_text = api_resp.text or ""; token_usage = self.extract_token_usage(api_resp)
            print(f"[DEBUG AsyncClient] Got new response for retry: {resp_text[:50]}...")
            new_branch_id = f"branch-{uuid.uuid4().hex[:8]}"
            print(f"[DEBUG AsyncClient] New response on branch: {new_branch_id}")
            new_asst_msg = self.create_message_structure(role="assistant", text=resp_text, model=curr_model, params=curr_params, token_usage=token_usage, parent_id=parent_user_id, branch_id=new_branch_id)
            self._add_message_to_conversation(new_asst_msg)
            self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            self.active_branch = new_branch_id
            self.conversation_data["metadata"]["active_leaf"] = new_asst_msg["id"]
            print(f"[DEBUG AsyncClient] Created new assistant message {new_asst_msg['id']} on branch {new_branch_id}")
            sibling_ids = messages[parent_user_id].get("children", [])
            new_msg_idx = sibling_ids.index(new_asst_msg["id"]) if new_asst_msg["id"] in sibling_ids else -1
            return {"message": new_asst_msg, "sibling_index": new_msg_idx, "total_siblings": len(sibling_ids)}
        except Exception as e: print(f"{Colors.FAIL}Error during retry generation: {e}{Colors.ENDC}"); raise

    async def get_message_siblings(self, message_id: str) -> Dict[str, Any]:
        print(f"[DEBUG AsyncClient] Getting siblings for message: {message_id}")
        if not self.conversation_data or "messages" not in self.conversation_data: raise ValueError("No active conversation/messages")
        messages = self.conversation_data["messages"]; target_msg = messages.get(message_id)
        if not target_msg: raise ValueError(f"Message {message_id} not found")
        parent_id_for_sibs = target_msg.get("parent_id") if target_msg["type"] == "assistant" else message_id
        if not parent_id_for_sibs:
            sibs = [message_id] if target_msg["type"] == "assistant" else messages.get(message_id, {}).get("children", [])
            return {"siblings": sibs, "current_index": 0, "total": len(sibs)}
        parent_msg = messages.get(parent_id_for_sibs)
        if not parent_msg: raise ValueError(f"Parent {parent_id_for_sibs} not found")
        sibling_ids = parent_msg.get("children", [])
        curr_idx = sibling_ids.index(message_id) if message_id in sibling_ids and target_msg["type"] == "assistant" else -1
        print(f"[DEBUG AsyncClient] Found {len(sibling_ids)} siblings for parent {parent_id_for_sibs}. Current msg {message_id} index: {curr_idx}")
        return {"siblings": sibling_ids, "current_index": curr_idx, "total": len(sibling_ids),
                "parent_id": parent_id_for_sibs if target_msg["type"] == "assistant" else None}

    async def switch_to_sibling(self, message_id: str, direction: str) -> Dict[str, Any]:
        print(f"[DEBUG AsyncClient] Switching {direction} from message: {message_id}")
        if not self.conversation_data or "messages" not in self.conversation_data: raise ValueError("No active conversation or messages found")
        messages = self.conversation_data["messages"]; current_message = messages.get(message_id)
        if not current_message: raise ValueError(f"Message {message_id} not found")

        final_active_message = current_message
        final_sibling_ids = []; final_current_index = -1; final_total_siblings = 0
        parent_id = current_message.get("parent_id")

        if parent_id and parent_id in messages:
            parent_message_obj = messages[parent_id]
            final_sibling_ids = parent_message_obj.get("children", [])
            if message_id in final_sibling_ids: final_current_index = final_sibling_ids.index(message_id)
            final_total_siblings = len(final_sibling_ids)
        elif current_message["type"] == "assistant":
            final_sibling_ids = [message_id]; final_current_index = 0; final_total_siblings = 1

        if direction == "none":
            self.active_branch = current_message.get("branch_id", "main")
            self.conversation_data["metadata"]["active_leaf"] = message_id
            print(f"[DEBUG AsyncClient] Activated branch '{self.active_branch}' with leaf '{message_id}' for 'none'. Sibling index: {final_current_index}, Total: {final_total_siblings}")
        elif current_message["type"] == "assistant" and direction in ["prev", "next"] and parent_id and parent_id in messages:
            if not final_sibling_ids or final_total_siblings <= 1:
                print(f"[DEBUG AsyncClient] No actual siblings to navigate for {message_id} with {direction}.")
            else:
                current_idx_for_nav = final_current_index; new_idx_for_nav = current_idx_for_nav
                if direction == "prev": new_idx_for_nav = (current_idx_for_nav - 1 + final_total_siblings) % final_total_siblings
                elif direction == "next": new_idx_for_nav = (current_idx_for_nav + 1) % final_total_siblings
                if new_idx_for_nav != current_idx_for_nav:
                    final_active_message = messages[final_sibling_ids[new_idx_for_nav]]
                    final_current_index = new_idx_for_nav
                    self.active_branch = final_active_message.get("branch_id", "main")
                    self.conversation_data["metadata"]["active_leaf"] = final_active_message["id"]
                    print(f"[DEBUG AsyncClient] Switched to sibling {final_active_message['id']} (idx {final_current_index}) on branch '{self.active_branch}' for {direction}.")
                else: print(f"[DEBUG AsyncClient] Navigation {direction} no change from {message_id}.")
        else:
            print(f"{Colors.WARNING}[AsyncClient] switch_to_sibling: Unhandled case/conditions not met - msg_id={message_id}, dir={direction}, type={current_message['type']}{Colors.ENDC}")
            self.active_branch = current_message.get("branch_id", "main")
            self.conversation_data["metadata"]["active_leaf"] = message_id

        self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
        return {"message": final_active_message, "sibling_index": final_current_index, "total_siblings": final_total_siblings}

    async def get_conversation_tree(self) -> Dict[str, Any]:
        print("[DEBUG AsyncClient] Building conversation tree")
        if not self.conversation_data or "messages" not in self.conversation_data:
            return {"nodes": [], "edges": [], "metadata": self.conversation_data.get("metadata", {})}
        messages = self.conversation_data["messages"]; nodes = []; edges = []
        active_leaf_id = self.conversation_data.get("metadata", {}).get("active_leaf")
        for msg_id, msg_data in messages.items():
            nodes.append({"id": msg_id, "type": msg_data["type"],
                          "content_preview": (msg_data["content"][:50] + "...") if len(msg_data["content"]) > 50 else msg_data["content"],
                          "timestamp": msg_data["timestamp"], "branch_id": msg_data.get("branch_id", "main"),
                          "model": msg_data.get("model"), "is_active_leaf": msg_id == active_leaf_id})
            for child_id in msg_data.get("children", []):
                if child_id in messages: edges.append({"from": msg_id, "to": child_id})
                else: print(f"{Colors.WARNING}Child {child_id} of {msg_id} not in messages dict.{Colors.ENDC}")
        print(f"[DEBUG AsyncClient] Built tree with {len(nodes)} nodes and {len(edges)} edges")
        return {"nodes": nodes, "edges": edges, "metadata": self.conversation_data.get("metadata", {})}

    async def save_conversation(self, quiet: bool = False) -> None:
        if not self.conversation_id or not self.conversation_data:
            if not quiet: print(f"{Colors.WARNING}No active conversation to save.{Colors.ENDC}"); return
        title = self.conversation_data.get("metadata", {}).get("title", "Untitled")
        filename = self.format_filename(title, self.conversation_id); filepath = self.conversations_dir / filename
        if "metadata" in self.conversation_data:
            self.conversation_data["metadata"]["updated_at"] = datetime.now().isoformat()
            self.conversation_data["metadata"]["model"] = self.model
            self.conversation_data["metadata"]["params"] = self.params.copy()
        if not quiet: print(f"{Colors.CYAN}Saving conversation v{self.VERSION}...{Colors.ENDC}")
        try:
            def save_json_sync():
                with open(filepath, 'w', encoding='utf-8') as f: json.dump(self.conversation_data, f, indent=2, ensure_ascii=False)
            await asyncio.to_thread(save_json_sync)
            if not quiet: print(f"{Colors.GREEN}Saved to: {filepath}, Total messages: {len(self.conversation_data.get('messages', {}))}{Colors.ENDC}")
        except Exception as e: print(f"{Colors.FAIL}Error saving conversation: {e}{Colors.ENDC}")

    async def send_message(self, message: str) -> Optional[str]: # CLI Path
        if not message.strip(): return None
        if not self.client: print(f"{Colors.FAIL}Client not initialized.{Colors.ENDC}"); return None
        if not self.conversation_data: await self.start_new_conversation(is_web_ui=self.is_web_ui)
        try:
            print(f"\n{Colors.CYAN}=== Processing Message ==={Colors.ENDC}\nActive branch: {self.active_branch}{Colors.ENDC}")
            resp_text = ""; token_usage = {}
            parent_id = self._get_last_message_id(self.active_branch)
            print(f"Parent message: {parent_id[:8] if parent_id else 'None'}...")
            user_msg = self.create_message_structure(role="user", text=message, model=None, params={}, parent_id=parent_id, branch_id=self.active_branch)
            self._add_message_to_conversation(user_msg); user_msg_id = user_msg["id"]
            print(f"{Colors.BLUE}User message ID: {user_msg_id[:8]}...{Colors.ENDC}")

            curr_model = self.conversation_data.get("metadata", {}).get("model", self.model)
            curr_params = self.conversation_data.get("metadata", {}).get("params", self.params)
            config = types.GenerateContentConfig(**curr_params)
            chat_hist = self.build_chat_history(self.conversation_data, self.active_branch)
            print(f"Chat history length: {len(chat_hist)} messages")

            if self.use_streaming:
                print(f"\r{Colors.CYAN}AI is thinking... (streaming){Colors.ENDC}", end="", flush=True)
                print("\r" + " " * 50 + "\r", end="", flush=True); print(f"{Colors.GREEN}AI: {Colors.ENDC}", end="", flush=True)
                stream_gen = await self.client.aio.models.generate_content_stream(model=curr_model, contents=chat_hist, config=config)
                async for chunk in stream_gen:
                    if hasattr(chunk, 'text') and chunk.text: print(f"{chunk.text}", end="", flush=True); resp_text += chunk.text
                print()
            else:
                print(f"\r{Colors.CYAN}AI is thinking...{Colors.ENDC}", end="", flush=True)
                api_resp = await self.client.aio.models.generate_content(model=curr_model, contents=chat_hist, config=config)
                print("\r" + " " * 50 + "\r", end="", flush=True); resp_text = api_resp.text or ""
                print(f"\n{Colors.GREEN}AI: {Colors.ENDC}{resp_text}"); token_usage = self.extract_token_usage(api_resp)

            ai_msg = self.create_message_structure(role="assistant", text=resp_text, model=curr_model, params=curr_params, token_usage=token_usage, parent_id=user_msg_id, branch_id=self.active_branch)
            self._add_message_to_conversation(ai_msg)
            print(f"{Colors.GREEN}AI message ID: {ai_msg['id'][:8]}...{Colors.ENDC}")
            print(f"{Colors.CYAN}Auto-saving...{Colors.ENDC}"); await self.save_conversation(quiet=True)
            return resp_text
        except Exception as e:
            print(f"{Colors.FAIL}Error generating response: {e}{Colors.ENDC}")
            err_parent_id = locals().get('user_msg_id', self._get_last_message_id(self.active_branch))
            err_msg = self.create_message_structure(role="assistant", text=f"Error: {e}", model=self.model, params=self.params, parent_id=err_parent_id, branch_id=self.active_branch)
            if self.conversation_data: self._add_message_to_conversation(err_msg); await self.save_conversation(quiet=True)
            return None

    async def get_available_models(self) -> List[Dict[str, Any]]:
        if not self.client: print(f"{Colors.FAIL}Client not initialized.{Colors.ENDC}"); return []
        api_models = []
        try:
            # print(f"Fetching available models from API...")
            resp = await self.client.aio.models.list()
            if resp:
                for m in resp:
                    if hasattr(m, 'supported_actions') and "generateContent" in m.supported_actions:
                        api_models.append({"name": m.name, "display_name": getattr(m, 'display_name', m.name),
                                           "input_token_limit": getattr(m, 'input_token_limit', "N/A"),
                                           "output_token_limit": getattr(m, 'output_token_limit', "N/A")})
        except Exception as e: print(f"{Colors.FAIL}API model retrieval error: {e}{Colors.ENDC}")

        defaults = [{"name": "models/gemini-2.0-flash", "display_name": "Gemini 2.0 Flash", "input_token_limit": 32768, "output_token_limit": 8192},
                    {"name": "models/gemini-2.0-pro", "display_name": "Gemini 2.0 Pro", "input_token_limit": 32768, "output_token_limit": 8192},
                    {"name": "models/gemini-2.5-flash-preview-05-20", "display_name": "Gemini 2.5 Flash Preview", "input_token_limit": "N/A", "output_token_limit": "N/A"},
                    {"name": "models/gemini-2.5-pro-preview-05-06", "display_name": "Gemini 2.5 Pro Preview", "input_token_limit": "N/A", "output_token_limit": "N/A"}]
        final = {m["name"]: m for m in defaults}
        for m in api_models: final[m["name"]] = m
        return list(final.values())

    async def display_models(self) -> None:
        models = await self.get_available_models()
        if not models: print(f"{Colors.WARNING}No models available.{Colors.ENDC}"); return
        headers = ["#", "Name", "Display Name", "Input Tokens", "Output Tokens"]
        data = [[i+1, m["name"], m["display_name"], m["input_token_limit"], m["output_token_limit"]] for i, m in enumerate(models)]
        print(tabulate(data, headers=headers, tablefmt="pretty"))

    async def select_model(self) -> None:
        models = await self.get_available_models()
        if not models: print(f"{Colors.WARNING}No models to select.{Colors.ENDC}"); return
        await self.display_models()
        try:
            sel = int(input("\nEnter model number: ")) -1
            if 0 <= sel < len(models):
                self.model = models[sel]["name"]
                if self.conversation_data and "metadata" in self.conversation_data:
                    self.conversation_data["metadata"]["model"] = self.model
                print(f"{Colors.GREEN}Selected model: {self.model}{Colors.ENDC}")
            else: print(f"{Colors.FAIL}Invalid selection.{Colors.ENDC}")
        except ValueError: print(f"{Colors.FAIL}Invalid number.{Colors.ENDC}")

    async def customize_params(self) -> None:
        current_p = self.params
        if self.conversation_data and "metadata" in self.conversation_data and "params" in self.conversation_data["metadata"]:
            current_p = self.conversation_data["metadata"]["params"]
        print(f"\n{Colors.HEADER}Current Parameters ({'Conversation' if current_p is not self.params else 'Default'}):{Colors.ENDC}")
        for k, v in current_p.items(): print(f"  {k}: {v}")
        print("\nEnter new values (blank to keep current):")
        new_p = current_p.copy()
        try:
            t = input(f"Temperature (0.0-2.0) [{new_p['temperature']}]: "); new_p["temperature"] = float(t) if t else new_p["temperature"]
            mt = input(f"Max output tokens [{new_p['max_output_tokens']}]: "); new_p["max_output_tokens"] = int(mt) if mt else new_p["max_output_tokens"]
            tp = input(f"Top-p (0.0-1.0) [{new_p['top_p']}]: "); new_p["top_p"] = float(tp) if tp else new_p["top_p"]
            tk = input(f"Top-k [{new_p['top_k']}]: "); new_p["top_k"] = int(tk) if tk else new_p["top_k"]
            self.params = new_p # Update client default
            if self.conversation_data and "metadata" in self.conversation_data: # Update active conversation
                self.conversation_data["metadata"]["params"] = new_p
            print(f"{Colors.GREEN}Parameters updated.{Colors.ENDC}")
        except ValueError as e: print(f"{Colors.FAIL}Invalid input: {e}. Not updated.{Colors.ENDC}")


    async def list_conversations(self) -> List[Dict[str, Any]]:
        def read_files_sync():
            convs = []
            for fp_item in self.conversations_dir.glob("*.json"):
                try:
                    with open(fp_item, 'r', encoding='utf-8') as f: data = json.load(f)
                    meta_content = data.get("metadata", {})
                    if not meta_content and "history" in data: # Old format
                        for hi in data.get("history", []):
                            if hi.get("type") == "metadata": meta_content = hi.get("content", {}); break
                    msg_count = len(data.get("messages", {})) # New
                    if msg_count == 0 and "history" in data: # Old
                        msg_count = sum(1 for hi in data.get("history", []) if hi.get("type") == "message")
                    convs.append({"filename": fp_item.name, "path": str(fp_item),
                                   "title": meta_content.get("title", "Untitled"),
                                   "model": meta_content.get("model", "N/A"),
                                   "created_at": meta_content.get("created_at", "N/A"),
                                   "message_count": msg_count, "conversation_id": data.get("conversation_id")})
                except Exception as e: print(f"{Colors.WARNING}Error reading {fp_item.name}: {e}{Colors.ENDC}")
            return convs
        return await asyncio.to_thread(read_files_sync)

    async def display_conversations(self) -> List[Dict[str, Any]]:
        convs = await self.list_conversations()
        if not convs: print(f"{Colors.WARNING}No saved conversations.{Colors.ENDC}"); return convs
        headers = ["#", "Title", "Model", "Messages", "Created", "Filepath"]
        table_d = []
        for i, c in enumerate(convs, 1):
            ca = c["created_at"]
            if ca != "N/A":
                try: ca = datetime.fromisoformat(ca.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
                except: pass
            table_d.append([i, c["title"], c["model"], c["message_count"], ca, str(c["path"])])
        print(tabulate(table_d, headers=headers, tablefmt="pretty")); return convs

    async def load_conversation(self, name_or_idx: Optional[str] = None) -> None:
        all_convs = await self.list_conversations()
        if not all_convs: print(f"{Colors.WARNING}No saved conversations.{Colors.ENDC}"); return
        selected = None
        if name_or_idx:
            selected = next((c for c in all_convs if c["title"].lower() == name_or_idx.lower()), None)
            if not selected: selected = next((c for c in all_convs if c["filename"].lower() == name_or_idx.lower()), None)
            if not selected:
                try:
                    idx = int(name_or_idx) - 1
                    if 0 <= idx < len(all_convs): selected = all_convs[idx]
                except ValueError:
                    pass
            if not selected: print(f"{Colors.FAIL}Conv '{name_or_idx}' not found.{Colors.ENDC}"); await self.display_conversations(); return
        else:
            await self.display_conversations()
            try:
                sel_num = int(input("\nEnter conv number: ")) -1
                if 0 <= sel_num < len(all_convs): selected = all_convs[sel_num]
                else: print(f"{Colors.FAIL}Invalid selection.{Colors.ENDC}"); return
            except ValueError: print(f"{Colors.FAIL}Invalid number.{Colors.ENDC}"); return
            except Exception as e: print(f"{Colors.FAIL}Selection error: {e}{Colors.ENDC}"); return
        if not selected: return
        try:
            def read_json_sync(p_str):
                with open(p_str, 'r', encoding='utf-8') as f: return json.load(f)
            loaded = await asyncio.to_thread(read_json_sync, selected["path"]) # path is already str
            self.conversation_id = loaded.get("conversation_id")
            if "messages" in loaded and "metadata" in loaded: # New
                self.conversation_data = loaded; meta = loaded.get("metadata", {})
                self.model = meta.get("model", self.model); self.params = meta.get("params", self.params).copy()
                self.conversation_name = meta.get("title", "Untitled"); self.active_branch = meta.get("active_branch", "main")
                print(f"{Colors.CYAN}Loaded new format: {self.conversation_name}{Colors.ENDC}")
            else: # Old
                self.conversation_history = loaded.get("history", [])
                self._convert_old_to_new_format()
                print(f"{Colors.CYAN}Converted & loaded old format: {self.conversation_name}{Colors.ENDC}")
            await self.display_conversation_history()
        except Exception as e: print(f"{Colors.FAIL}Error loading data: {e}{Colors.ENDC}"); import traceback; traceback.print_exc()


    async def display_conversation_history(self) -> None:
        if not self.conversation_data or "messages" not in self.conversation_data or not self.conversation_data["messages"]:
            print(f"{Colors.WARNING}No history to display.{Colors.ENDC}"); return
        print(f"\n{Colors.HEADER}Conversation History:{Colors.ENDC}")
        meta = self.conversation_data.get("metadata", {})
        print(f"{Colors.BOLD}Title: {meta.get('title', 'Untitled')}{Colors.ENDC}")
        print(f"{Colors.BOLD}Model: {meta.get('model', self.model)}{Colors.ENDC}")
        print(f"{Colors.BOLD}Active Branch: {meta.get('active_branch', 'main')}{Colors.ENDC}\n")
        msg_chain_ids = self._build_message_chain(self.conversation_data, meta.get('active_branch', 'main'))
        msgs_dict = self.conversation_data["messages"]
        for mid in msg_chain_ids:
            msg = msgs_dict.get(mid, {})
            if msg.get("type") in ["user", "assistant"]:
                role = msg["type"]; text = msg.get("content", ""); ts = msg.get("timestamp", "")
                try: time_str = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
                except: time_str = "N/A"
                color = Colors.BLUE if role == "user" else Colors.GREEN
                print(f"{color}{role.capitalize()} ({time_str}): {Colors.ENDC}{text}\n")


    async def toggle_streaming(self) -> bool:
        self.use_streaming = not self.use_streaming
        print(f"{Colors.GREEN}Streaming mode {'enabled' if self.use_streaming else 'disabled'}.{Colors.ENDC}")
        return self.use_streaming

    def add_user_message(self, message: str) -> None:
        self.current_user_message = message
        if not self.conversation_data:
            print(f"{Colors.WARNING}[UI] No active conv_data. Init default.{Colors.ENDC}")
            self.conversation_id = self.generate_conversation_id()
            self.conversation_data = self.create_metadata_structure(f"UI_Conv_{self.conversation_id[:4]}", self.conversation_id)
            self.conversation_data["metadata"]["model"] = self.model
            self.conversation_data["metadata"]["params"] = self.params.copy()
            self.active_branch = "main"
        parent_id = self._get_last_message_id(self.active_branch)
        user_msg = self.create_message_structure(role="user", text=message, model=None, params={}, parent_id=parent_id, branch_id=self.active_branch)
        self._add_message_to_conversation(user_msg)
        self.current_user_message_id = user_msg["id"]

    def add_assistant_message(self, message: str, token_usage: Optional[Dict[str, Any]] = None) -> None:
        text_to_add = message if message is not None else ""
        parent_id_for_ai = self.current_user_message_id
        if not parent_id_for_ai:
            parent_id_for_ai = self._get_last_message_id(self.active_branch)
            print(f"{Colors.WARNING}[UI] current_user_message_id not set, using last in branch: {parent_id_for_ai}{Colors.ENDC}")

        ai_model = self.conversation_data.get("metadata", {}).get("model", self.model)
        ai_params = self.conversation_data.get("metadata", {}).get("params", self.params)
        ai_msg = self.create_message_structure(role="assistant", text=text_to_add, model=ai_model, params=ai_params, token_usage=token_usage, parent_id=parent_id_for_ai, branch_id=self.active_branch)
        self._add_message_to_conversation(ai_msg)
        self.current_user_message_id = None # Clear after assistant uses it for parenting

    async def get_response(self) -> Tuple[Optional[str], Optional[Dict[str, Any]]]: # For non-streaming UI
        if not self.current_user_message: return "Error: No current user message.", None
        if not self.client: return "Error: Client not initialized.", None
        if not self.conversation_data: return "Error: Conversation data not initialized.", None

        model = self.conversation_data.get("metadata", {}).get("model", self.model)
        params = self.conversation_data.get("metadata", {}).get("params", self.params)
        config = types.GenerateContentConfig(**params)
        history = self.build_chat_history(self.conversation_data, self.active_branch)
        try:
            api_resp = await self.client.aio.models.generate_content(model=model, contents=history, config=config)
            return api_resp.text or "", self.extract_token_usage(api_resp)
        except Exception as e:
            print(f"{Colors.FAIL}[UI] Non-streaming error: {e}{Colors.ENDC}"); import traceback; traceback.print_exc()
            return f"Error: {e}", None

    async def get_streaming_response(self) -> AsyncIterator[Dict[str, Any]]: # For streaming UI
        if not self.current_user_message: yield {"error": "No current user message."}; return
        if not self.client: yield {"error": "Client not initialized."}; return
        if not self.conversation_data: yield {"error": "Conversation data not initialized."}; return

        user_message_id_for_parenting = self.current_user_message_id # Capture before it's cleared

        model = self.conversation_data.get("metadata", {}).get("model", self.model)
        params = self.conversation_data.get("metadata", {}).get("params", self.params)
        config = types.GenerateContentConfig(**params)
        history = self.build_chat_history(self.conversation_data, self.active_branch)

        full_resp_text = ""; final_tokens = {}
        try:
            stream_gen = await self.client.aio.models.generate_content_stream(model=model, contents=history, config=config)
            async for chunk in stream_gen:
                if hasattr(chunk, 'text') and chunk.text:
                    full_resp_text += chunk.text; yield {"chunk": chunk.text}
                if hasattr(chunk, 'usage_metadata'): # May not be on every chunk
                    final_tokens = self.extract_token_usage(chunk)

            # Stream finished, now finalize
            self.add_assistant_message(full_resp_text, final_tokens) # This uses and clears self.current_user_message_id

            assistant_msg_id = self._get_last_message_id(self.active_branch)
            await self.save_conversation(quiet=True)

            yield {"done": True, "full_response": full_resp_text,
                   "conversation_id": self.conversation_id, "message_id": assistant_msg_id,
                   "parent_id": user_message_id_for_parenting, # Use captured ID
                   "model": model, "token_usage": final_tokens}
        except Exception as e:
            print(f"{Colors.FAIL}[UI] Streaming error: {e}{Colors.ENDC}"); import traceback; traceback.print_exc()
            yield {"error": str(e)}


    def get_conversation_history(self) -> List[Dict[str, Any]]: # For UI display
        hist_list = []
        if not self.conversation_data or "messages" not in self.conversation_data: return hist_list
        active_b = self.active_branch
        msg_chain_ids = self._build_message_chain(self.conversation_data, active_b)
        msgs_dict = self.conversation_data["messages"]
        for mid in msg_chain_ids:
            msg = msgs_dict.get(mid, {})
            if msg.get("type") in ["user", "assistant"]:
                hist_list.append({'role': msg["type"], 'content': msg.get("content", ""), 'id': mid,
                                  'model': msg.get("model"), 'timestamp': msg.get("timestamp"),
                                  'parent_id': msg.get("parent_id")})
        return hist_list
