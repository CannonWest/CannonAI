#!/usr/bin/env python3
"""
Gemini Chat Synchronous Client - Synchronous implementation of Gemini Chat client.

This module provides the synchronous implementation of the Gemini Chat client,
building on the core functionality in base_client.py.
"""

import getpass
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from tabulate import tabulate

from base_client import BaseGeminiClient, Colors

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai package not installed.")
    print("Please install with: pip install google-genai")
    exit(1)


class SyncGeminiClient(BaseGeminiClient):
    """Synchronous implementation of the Gemini Chat client."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, 
                 conversations_dir: Optional[Path] = None):
        """Initialize the synchronous Gemini client.
        
        Args:
            api_key: The Gemini API key. If None, will attempt to get from environment.
            model: The model to use. Defaults to DEFAULT_MODEL.
            conversations_dir: Directory to store conversations. If None, uses default.
        """
        # Call parent constructor
        super().__init__(api_key, model, conversations_dir)
        
        # Sync-specific initialization
        self.conversation_id: Optional[str] = None
        self.conversation_history: List[Dict[str, Any]] = []
        self.params: Dict[str, Any] = self.default_params.copy()
        self.use_streaming: bool = False  # Default to non-streaming
        self.conversation_name: str = "New Conversation"  # Default conversation name
        self.is_web_ui: bool = False  # Flag for web UI mode
        
        # The base directory is already set by the parent constructor
        self.conversations_dir = self.base_directory
        self.ensure_directories(self.conversations_dir)
    
    def initialize_client(self) -> bool:
        """Initialize the Gemini client with API key.
        
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
    
    def start_new_conversation(self, title: Optional[str] = None, is_web_ui: bool = False) -> None:
        """Start a new conversation.
        
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
        
        # Update conversation name property for UI display
        self.conversation_name = title
        
        # Create initial metadata
        metadata = self.create_metadata_structure(title, self.model, self.params)
        
        # Add to conversation history
        self.conversation_history.append(metadata)
        
        print(f"{Colors.GREEN}Started new conversation: {title}{Colors.ENDC}")
        
        # Initial save of the new conversation
        self.save_conversation()
    
    def save_conversation(self, quiet: bool = False) -> None:
        """Save the current conversation to a JSON file.
        
        Args:
            quiet: If True, don't print success messages (for auto-save)
        """
        import json
        
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
        
        # Save to file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({
                    "conversation_id": self.conversation_id,
                    "history": self.conversation_history
                }, f, indent=2, ensure_ascii=False)
            if not quiet:
                print(f"{Colors.GREEN}Conversation saved to: {filepath}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}Error saving conversation: {e}{Colors.ENDC}")
    
    def send_message(self, message: str) -> Optional[str]:
        """Send a message to the model and get the response.
        
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
        
        # Create a chat session
        try:
            response_text = ""
            
            # Configure generation parameters
            config = types.GenerateContentConfig(
                temperature=self.params["temperature"],
                max_output_tokens=self.params["max_output_tokens"],
                top_p=self.params["top_p"],
                top_k=self.params["top_k"]
            )
            
            # Build chat history for the API
            chat_history = self.build_chat_history(self.conversation_history)
            
            # Add the new message
            chat_history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
            
            # Add user message to history with enhanced metadata
            user_message = self.create_message_structure("user", message, self.model, self.params)
            self.conversation_history.append(user_message)
            
            # Token usage will be populated later
            token_usage = {}
            
            # Use streaming or non-streaming based on user preference
            if self.use_streaming:
                # Call the API with streaming
                print(f"\r{Colors.CYAN}AI is thinking... (streaming mode){Colors.ENDC}", end="", flush=True)
                
                # Initialize an empty response
                response_text = ""
                
                # Clear the thinking message when starting to show response
                print("\r" + " " * 50 + "\r", end="", flush=True)  # Clear line with spaces
                
                # Print the AI prefix only once before streaming begins
                print(f"{Colors.GREEN}AI: {Colors.ENDC}", end="", flush=True)
                
                # Stream the response
                for chunk in self.client.models.generate_content_stream(
                    model=self.model,
                    contents=chat_history,
                    config=config
                ):
                    # Print each chunk as it arrives
                    if chunk.text:
                        chunk_text = chunk.text
                        print(f"{chunk_text}", end="", flush=True)
                        response_text += chunk_text
                
                print()  # Add a newline after streaming completes
                
                # Extract token usage metadata if available
                # Note: Token usage might not be available in streaming responses
            
            else:
                # Call the API without streaming
                print(f"\r{Colors.CYAN}AI is thinking...{Colors.ENDC}", end="", flush=True)
                
                # Call the API
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=chat_history,
                    config=config
                )
                
                # Clear the thinking message when we get the response
                print("\r" + " " * 50 + "\r", end="", flush=True)  # Clear line with spaces
                
                # Extract response text
                response_text = response.text
                
                # Print the response for non-streaming mode
                print(f"\n{Colors.GREEN}AI: {Colors.ENDC}{response_text}")
                
                # Extract token usage metadata if available
                token_usage = self.extract_token_usage(response)
            
            # Add AI response to history with enhanced metadata
            ai_message = self.create_message_structure("ai", response_text, self.model, self.params, token_usage)
            self.conversation_history.append(ai_message)
            
            # Update metadata in conversation history
            for item in self.conversation_history:
                if item["type"] == "metadata":
                    item["content"]["updated_at"] = datetime.now().isoformat()
                    item["content"]["model"] = self.model
                    item["content"]["params"] = self.params.copy()
                    break
            
            # Auto-save after every message exchange
            print(f"{Colors.CYAN}Auto-saving conversation...{Colors.ENDC}")
            self.save_conversation(quiet=True)
            
            return response_text
        except Exception as e:
            print(f"{Colors.FAIL}Error generating response: {e}{Colors.ENDC}")
            return None
            
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available models.
        
        Returns:
            List of model information dictionaries
        """
        if not self.client:
            print(f"{Colors.FAIL}Error: Gemini client not initialized.{Colors.ENDC}")
            return []
            
        models = []
        try:
            for model in self.client.models.list():
                # Only include models that support text generation
                for action in model.supported_actions:
                    if action == "generateContent":
                        # Extract model info
                        model_info = {
                            "name": model.name,
                            "display_name": model.display_name if hasattr(model, 'display_name') else model.name,
                            "input_token_limit": model.input_token_limit if hasattr(model, 'input_token_limit') else "Unknown",
                            "output_token_limit": model.output_token_limit if hasattr(model, 'output_token_limit') else "Unknown"
                        }
                        models.append(model_info)
                        break
        except Exception as e:
            print(f"{Colors.FAIL}Error retrieving models: {e}{Colors.ENDC}")
        
        return models
        
    def display_models(self) -> None:
        """Display available models in a formatted table."""
        models = self.get_available_models()
        
        if not models:
            print(f"{Colors.WARNING}No models available or error retrieving models.{Colors.ENDC}")
            return
        
        headers = ["#", "Name", "Display Name", "Input Tokens", "Output Tokens"]
        table_data = []
        
        for i, model in enumerate(models, 1):
            name = model["name"]
            if '/' in name:  # Handle full resource paths
                name = name.split('/')[-1]
            
            row = [
                i,
                name,
                model["display_name"],
                model["input_token_limit"],
                model["output_token_limit"]
            ]
            table_data.append(row)
        
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))
    
    def select_model(self) -> None:
        """Let user select a model from available options."""
        models = self.get_available_models()
        
        if not models:
            print(f"{Colors.WARNING}No models available to select.{Colors.ENDC}")
            return
        
        self.display_models()
        
        try:
            selection = int(input("\nEnter model number to select: "))
            if 1 <= selection <= len(models):
                model_name = models[selection-1]["name"]
                # Extract just the model name if it's a full resource path
                if '/' in model_name:
                    model_name = model_name.split('/')[-1]
                
                self.model = model_name
                print(f"{Colors.GREEN}Selected model: {self.model}{Colors.ENDC}")
            else:
                print(f"{Colors.FAIL}Invalid selection.{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.FAIL}Please enter a valid number.{Colors.ENDC}")
    
    def customize_params(self) -> None:
        """Allow user to customize generation parameters."""
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
            
    def list_conversations(self) -> List[Dict[str, Any]]:
        """List available conversation files.
        
        Returns:
            List of conversation information dictionaries
        """
        import json
        
        conversations = []
        for file in self.conversations_dir.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Extract metadata
                metadata = {}
                for item in data.get("history", []):
                    if item.get("type") == "metadata":
                        metadata = item.get("content", {})
                        break
                
                conversations.append({
                    "filename": file.name,
                    "path": file,
                    "title": metadata.get("title", "Untitled"),
                    "model": metadata.get("model", "Unknown"),
                    "created_at": metadata.get("created_at", "Unknown"),
                    "message_count": sum(1 for item in data.get("history", []) if item.get("type") == "message"),
                    "conversation_id": data.get("conversation_id")
                })
            except Exception as e:
                print(f"{Colors.WARNING}Error reading {file.name}: {e}{Colors.ENDC}")
        
        return conversations
        
    def display_conversations(self) -> List[Dict[str, Any]]:
        """Display available conversations in a formatted table.
        
        Returns:
            List of conversation information dictionaries
        """
        conversations = self.list_conversations()
        
        if not conversations:
            print(f"{Colors.WARNING}No saved conversations found.{Colors.ENDC}")
            return conversations
        
        headers = ["#", "Title", "Model", "Messages", "Created", "Filepath"]
        table_data = []
        
        for i, conv in enumerate(conversations, 1):
            # Format created_at date
            created_at = conv["created_at"]
            if created_at != "Unknown":
                try:
                    dt = datetime.fromisoformat(created_at)
                    created_at = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    pass
            
            row = [
                i,
                conv["title"],
                conv["model"],
                conv["message_count"],
                created_at,
                str(conv["path"])
            ]
            table_data.append(row)
        
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))
        return conversations
        
    def load_conversation(self) -> None:
        """Load a saved conversation."""
        import json
        
        conversations = self.display_conversations()
        
        if not conversations:
            return
        
        try:
            selection = int(input("\nEnter conversation number to load: "))
            if 1 <= selection <= len(conversations):
                selected = conversations[selection-1]
                
                # Load the conversation file
                with open(selected["path"], 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.conversation_id = data.get("conversation_id")
                self.conversation_history = data.get("history", [])
                
                # Update model and params from metadata
                for item in self.conversation_history:
                    if item.get("type") == "metadata":
                        metadata = item.get("content", {})
                        self.model = metadata.get("model", self.model)
                        if "params" in metadata:
                            self.params = metadata["params"]
                        break
                
                print(f"{Colors.GREEN}Loaded conversation: {selected['title']}{Colors.ENDC}")
                
                # Display conversation history
                self.display_conversation_history()
            else:
                print(f"{Colors.FAIL}Invalid selection.{Colors.ENDC}")
        except ValueError:
            print(f"{Colors.FAIL}Please enter a valid number.{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}Error loading conversation: {e}{Colors.ENDC}")
            
    def display_conversation_history(self) -> None:
        """Display the current conversation history."""
        if not self.conversation_history:
            print(f"{Colors.WARNING}No conversation history to display.{Colors.ENDC}")
            return
        
        print(f"\n{Colors.HEADER}Conversation History:{Colors.ENDC}")
        
        # Find the title from metadata
        title = "Untitled"
        model = self.model
        for item in self.conversation_history:
            if item["type"] == "metadata":
                metadata = item["content"]
                title = metadata.get("title", title)
                model = metadata.get("model", model)
                break
        
        print(f"{Colors.BOLD}Title: {title}{Colors.ENDC}")
        print(f"{Colors.BOLD}Model: {model}{Colors.ENDC}\n")
        
        # Print messages
        for item in self.conversation_history:
            if item["type"] == "message":
                role = item["content"]["role"]
                text = item["content"]["text"]
                
                if role == "user":
                    print(f"{Colors.BLUE}User: {Colors.ENDC}{text}")
                else:  # AI response
                    print(f"{Colors.GREEN}AI: {Colors.ENDC}{text}")
                print("")  # Add spacing between messages

    def toggle_streaming(self) -> bool:
        """Toggle streaming mode.
        
        Returns:
            Current streaming mode state (True for enabled, False for disabled)
        """
        self.use_streaming = not self.use_streaming
        status = "enabled" if self.use_streaming else "disabled"
        print(f"{Colors.GREEN}Streaming mode {status}.{Colors.ENDC}")
        return self.use_streaming
        
    # TODO: Add other methods from original implementation as needed

# TODO: Implement AsyncGeminiClient in future
"""
class AsyncGeminiClient(BaseGeminiClient):
    '''Asynchronous implementation of Gemini Chat client.
    
    This class will provide asynchronous versions of all client functionality.
    '''
    
    async def initialize_client(self):
        '''Initialize async client.'''
        pass
        
    async def send_message(self, message: str) -> Optional[str]:
        '''Send a message asynchronously.'''
        pass
        
    async def save_conversation(self, quiet: bool = False) -> None:
        '''Save conversation asynchronously.'''
        pass
        
    # ... other async methods
"""
