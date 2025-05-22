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
        self.conversation_history: List[Dict[str, Any]] = []
        self.params: Dict[str, Any] = self.default_params.copy()
        self.use_streaming: bool = False  # Default to non-streaming
        self.conversation_name: str = "New Conversation"  # Default conversation name
        self.current_user_message: Optional[str] = None  # Store the current user message for streaming
        self.is_web_ui: bool = False  # Flag for web UI mode

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

    async def start_new_conversation(self, title: Optional[str] = None, is_web_ui: bool = False) -> None:
        """Start a new conversation asynchronously.

        Args:
            title: Optional title for the conversation. If None, will prompt or generate.
            is_web_ui: Whether this is being called from the web UI.
        """
        self.conversation_id = self.generate_conversation_id()
        self.conversation_history = []

        # Get title for the conversation
        if title is None and not is_web_ui:
            # Only prompt for input in CLI mode
            title = input("Enter a title for this conversation (or leave blank for timestamp): ")

        # Generate default title if none provided
        if not title:
            title = f"Conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Update the conversation name property
        self.conversation_name = title

        # Create initial metadata
        metadata = self.create_metadata_structure(title, self.model, self.params)

        # Add to conversation history
        self.conversation_history.append(metadata)

        print(f"{Colors.GREEN}Started new conversation: {title}{Colors.ENDC}")

        # Initial save of the new conversation
        await self.save_conversation()

    async def save_conversation(self, quiet: bool = False) -> None:
        """Save the current conversation to a JSON file asynchronously.

        Args:
            quiet: If True, don't print success messages (for auto-save)
        """
        if not self.conversation_id or not self.conversation_history:
            if not quiet:
                print(f"{Colors.WARNING}No active conversation to save.{Colors.ENDC}")
            return

        # Get conversation title from metadata
        title = "Untitled"
        for item in self.conversation_history:
            if item["type"] == "metadata" and "title" in item["content"]:
                title = item["content"]["title"]
                break

        # Create filename with sanitized title
        filename = self.format_filename(title, self.conversation_id)
        filepath = self.conversations_dir / filename

        # Update metadata
        for item in self.conversation_history:
            if item["type"] == "metadata":
                item["content"]["updated_at"] = datetime.now().isoformat()
                item["content"]["model"] = self.model
                item["content"]["params"] = self.params.copy()
                item["content"]["message_count"] = sum(1 for i in self.conversation_history if i["type"] == "message")
                break

        # Save to file using non-blocking io
        try:
            def save_json():
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump({
                        "conversation_id": self.conversation_id,
                        "history": self.conversation_history
                    }, f, indent=2, ensure_ascii=False)

            # Use to_thread to make file I/O non-blocking
            await asyncio.to_thread(save_json)

            if not quiet:
                print(f"{Colors.GREEN}Conversation saved to: {filepath}{Colors.ENDC}")
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
            response_text = ""
            token_usage = {}

            # Add user message to history with enhanced metadata
            # This is for the CLI path; UI path uses add_user_message separately.
            user_message_struct = self.create_message_structure("user", message, self.model, self.params)
            self.conversation_history.append(user_message_struct)

            # Configure generation parameters
            config = types.GenerateContentConfig(
                temperature=self.params["temperature"],
                max_output_tokens=self.params["max_output_tokens"],
                top_p=self.params["top_p"],
                top_k=self.params["top_k"]
            )

            # Build chat history for the API (now includes the latest user message)
            chat_history = self.build_chat_history(self.conversation_history)

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

            # Add AI response to history
            # Ensure response_text used for history is not None (already handled for non-streaming)
            # For streaming, response_text is initialized to ""
            ai_message_struct = self.create_message_structure("ai", response_text, self.model, self.params, token_usage)
            self.conversation_history.append(ai_message_struct)

            # Update metadata
            for item in self.conversation_history:
                if item["type"] == "metadata":
                    item["content"]["updated_at"] = datetime.now().isoformat()
                    item["content"]["model"] = self.model
                    item["content"]["params"] = self.params.copy()
                    break

            print(f"{Colors.CYAN}Auto-saving conversation...{Colors.ENDC}")
            await self.save_conversation(quiet=True)
            return response_text

        except Exception as e:
            print(f"{Colors.FAIL}Error generating response: {e}{Colors.ENDC}")
            # Add a placeholder AI message in history to mark the error
            error_ai_message = self.create_message_structure("ai", f"Error: {e}", self.model, self.params)
            self.conversation_history.append(error_ai_message)
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

                    # Extract metadata
                    metadata = {}
                    for item in data.get("history", []):
                        if item.get("type") == "metadata":
                            metadata = item.get("content", {})
                            break

                    result.append({
                        "filename": file_path.name,
                        "path": file_path,
                        "title": metadata.get("title", "Untitled"),
                        "model": metadata.get("model", "Unknown"),
                        "created_at": metadata.get("created_at", "Unknown"),
                        "message_count": sum(1 for item in data.get("history", []) if item.get("type") == "message"),
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
                self.conversation_history = data.get("history", [])

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

    async def display_conversation_history(self) -> None:
        """Display the current conversation history asynchronously."""
        if not self.conversation_history:
            print(f"{Colors.WARNING}No conversation history to display.{Colors.ENDC}")
            return

        print(f"\n{Colors.HEADER}Conversation History:{Colors.ENDC}")
        title = "Untitled"
        current_model_display = self.model # Renamed to current_model_display
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
        """Add a user message to history (called by UI message handler)."""
        self.current_user_message = message
        user_message_struct = self.create_message_structure("user", message, self.model, self.params)
        self.conversation_history.append(user_message_struct)
        # print(f"{Colors.BLUE}User (UI): {Colors.ENDC}{message}") # Optional: server-side log for UI messages

    def add_assistant_message(self, message: str, token_usage: Optional[Dict[str, Any]] = None) -> None:
        """Add an assistant message to history (called by UI message handler after response)."""
        # Ensure message is not None before adding
        text_to_add = message if message is not None else ""
        ai_message_struct = self.create_message_structure("ai", text_to_add, self.model, self.params, token_usage)
        self.conversation_history.append(ai_message_struct)
        # print(f"{Colors.GREEN}AI (UI): {Colors.ENDC}{text_to_add}") # Optional: server-side log

    async def get_response(self) -> str:
        """Get a non-streaming response for self.current_user_message (for UI)."""
        if not self.current_user_message:
            return "Error: No current user message to process."
        if not self.client:
            return "Error: Gemini client not initialized."

        config = types.GenerateContentConfig(**self.params)
        chat_history = self.build_chat_history(self.conversation_history)

        # <<< --- ADD DETAILED LOGGING HERE --- >>>
        print(f"\nDEBUG ASYNC_CLIENT: Attempting to call generate_content")
        print(f"DEBUG ASYNC_CLIENT: Model: {self.model}")
        print(f"DEBUG ASYNC_CLIENT: Current User Message: {self.current_user_message}")
        print(f"DEBUG ASYNC_CLIENT: Entire self.conversation_history (length {len(self.conversation_history)}):")
        for idx, item in enumerate(self.conversation_history):
            print(f"  Item {idx}: type={item.get('type')}, content_keys={list(item.get('content', {}).keys()) if item.get('content') else 'N/A'}")
            if item.get('type') == 'message':
                print(f"    Role: {item['content'].get('role')}, Text: '{item['content'].get('text')}'")

        print(f"DEBUG ASYNC_CLIENT: Constructed chat_history for API (length {len(chat_history)}):")
        if chat_history:
            for i, content_item in enumerate(chat_history):
                # Print role and a summary of parts to avoid overly verbose logs if parts are complex
                parts_summary = []
                if hasattr(content_item, 'parts') and content_item.parts:
                    for part_idx, part_item in enumerate(content_item.parts):
                        if hasattr(part_item, 'text'):
                            parts_summary.append(f"Part {part_idx} (text): '{part_item.text[:50]}{'...' if len(part_item.text) > 50 else ''}'")
                        else:
                            parts_summary.append(f"Part {part_idx}: (non-text part)")
                print(f"  API Content Item {i}: role='{content_item.role}', parts=[{', '.join(parts_summary)}]")
        else:
            print("  API chat_history is EMPTY or None!")
        # <<< --- END OF DETAILED LOGGING --- >>>

        try:
            print(f"\r{Colors.CYAN}AI is thinking (non-streaming UI)...{Colors.ENDC}", end="", flush=True)
            api_response = await self.client.aio.models.generate_content(
                model=self.model, contents=chat_history, config=config)
            print("\r" + " " * 50 + "\r", end="", flush=True)

            response_text = api_response.text
            if response_text is None:
                response_text = ""

            token_usage = self.extract_token_usage(api_response)
            await self.save_conversation(quiet=True)
            self.current_user_message = None
            return response_text
        except Exception as e:
            error_msg = f"Error generating non-streaming response: {e}"
            print(f"{Colors.FAIL}{error_msg}{Colors.ENDC}")
            self.current_user_message = None
            return error_msg

    async def get_streaming_response(self) -> AsyncIterator[str]:
        """Get a streaming response for self.current_user_message (for UI)."""
        if not self.current_user_message:
            yield "Error: No current user message to process."
            return
        if not self.client:
            yield "Error: Gemini client not initialized."
            return

        # current_user_message is already added to history by add_user_message()
        # So, DO NOT add it again here.

        config = types.GenerateContentConfig(**self.params)
        chat_history = self.build_chat_history(self.conversation_history) # History includes the latest user message

        complete_response_text = ""
        try:
            print(f"\r{Colors.CYAN}AI is thinking (streaming UI)...{Colors.ENDC}", end="", flush=True)
            stream_generator = await self.client.aio.models.generate_content_stream(
                model=self.model, contents=chat_history, config=config) # CORRECTED
            print("\r" + " " * 50 + "\r", end="", flush=True)

            async for chunk in stream_generator:
                if hasattr(chunk, 'text') and chunk.text:
                    chunk_text = chunk.text
                    complete_response_text += chunk_text
                    yield chunk_text
            # Add the full AI response to history after streaming is complete
            # (Handled by caller using add_assistant_message)
            # self.add_assistant_message(complete_response_text) # No, caller does this

            await self.save_conversation(quiet=True)
        except Exception as e:
            error_msg = f"Error generating streaming response: {e}"
            print(f"{Colors.FAIL}{error_msg}{Colors.ENDC}")
            yield error_msg # Yield error message to UI
            # self.add_assistant_message(error_msg) # Caller should handle
        finally:
            self.current_user_message = None # Clear after processing

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get history for UI (role and content)."""
        history = []
        for item in self.conversation_history:
            if item["type"] == "message":
                history.append({
                    'role': item["content"]["role"],
                    'content': item["content"]["text"]
                })
        return history
