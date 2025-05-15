#!/usr/bin/env python3
"""
Gemini Chat - A command-line interface for Google's Gemini models.

This application allows multi-turn conversations with Google Gemini models,
model selection, parameter customization, and conversation management.
"""

import argparse
import getpass
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from tabulate import tabulate

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai package not installed.")
    print("Please install with: pip install google-genai")
    exit(1)

class Colors:
    """Terminal colors for better user experience."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class GeminiChat:
    """Main class for the Gemini Chat application."""
    
    DEFAULT_MODEL = "gemini-2.0-flash"
    BASE_DIRECTORY = Path(__file__).resolve().parent.parent / "gemini_chat_conversations"
    
    def __init__(self):
        """Initialize the GeminiChat application."""
        self.api_key: Optional[str] = None
        self.client: Optional[genai.Client] = None
        self.model: str = self.DEFAULT_MODEL
        self.conversation_id: Optional[str] = None
        self.conversation_history: List[Dict[str, Any]] = []
        self.params: Dict[str, Any] = {
            "temperature": 0.7,
            "max_output_tokens": 800,
            "top_p": 0.95,
            "top_k": 40
        }
        self.use_streaming: bool = False  # Default to non-streaming
        self.conversations_dir: Path = self.BASE_DIRECTORY
        self.ensure_directories()
        # Client will be initialized in main() after parsing command line args
    
    def ensure_directories(self) -> None:
        """Ensure necessary directories exist."""
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        print(f"Conversations will be saved to: {self.conversations_dir}")
    
    def validate_client(self) -> bool:
        """Validate that the client is properly initialized."""
        if not self.client:
            print(f"{Colors.FAIL}Error: Gemini client not initialized.{Colors.ENDC}")
            return False
        return True
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available models."""
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
    
    def generate_conversation_id(self) -> str:
        """Generate a unique conversation ID."""
        return str(uuid.uuid4())
    
    def start_new_conversation(self) -> None:
        """Start a new conversation."""
        self.conversation_id = self.generate_conversation_id()
        self.conversation_history = []
        
        # Get title for the conversation
        title = input("Enter a title for this conversation (or leave blank for timestamp): ")
        if not title:
            title = f"Conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create initial metadata with enhanced fields
        metadata = {
            "title": title,
            "model": self.model,
            "params": self.params.copy(),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "message_count": 0,
            "version": "1.1",  # Added for future compatibility
            "app_info": "Gemini Chat CLI"
        }
        
        # Add to conversation history
        self.conversation_history.append({
            "type": "metadata",
            "content": metadata
        })
        
        print(f"{Colors.GREEN}Started new conversation: {title}{Colors.ENDC}")
        
        # Initial save of the new conversation
        self.save_conversation()
    
    def save_conversation(self, quiet: bool = False) -> None:
        """Save the current conversation to a JSON file.
        
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
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
        filename = f"{safe_title}_{self.conversation_id[:8]}.json"
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
    
    def list_conversations(self) -> List[Dict[str, Any]]:
        """List available conversation files."""
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
    
    def display_conversations(self) -> None:
        """Display available conversations in a formatted table."""
        conversations = self.list_conversations()
        
        if not conversations:
            print(f"{Colors.WARNING}No saved conversations found.{Colors.ENDC}")
            return
        
        headers = ["#", "Title", "Model", "Messages", "Created"]
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
                created_at
            ]
            table_data.append(row)
        
        print(tabulate(table_data, headers=headers, tablefmt="pretty"))
        return conversations
    
    def load_conversation(self) -> None:
        """Load a saved conversation."""
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
    
    def send_message(self, message: str) -> Optional[str]:
        """Send a message to the model and get the response."""
        if not message.strip():
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
            chat_history = []
            for item in self.conversation_history:
                if item["type"] == "message":
                    role = item["content"]["role"]
                    text = item["content"]["text"]
                    
                    # Convert to API role format
                    api_role = "user" if role == "user" else "model"
                    chat_history.append(types.Content(role=api_role, parts=[types.Part.from_text(text=text)]))
            
            # Add the new message
            chat_history.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
            
            # Add user message to history with enhanced metadata
            user_message = {
                "type": "message",
                "content": {
                    "role": "user",
                    "text": message,
                    "timestamp": datetime.now().isoformat(),
                    "model": self.model,
                    "params": self.params.copy()
                }
            }
            self.conversation_history.append(user_message)
            
            # Token usage will be populated later
            token_usage = {}
            
            # Use streaming or non-streaming based on user preference
            if self.use_streaming:
                # Call the API with streaming
                print(f"{Colors.CYAN}AI is thinking... (streaming mode){Colors.ENDC}")
                
                # Initialize an empty response
                response_text = ""
                
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
                # Note: Token usage might not be available in streaming responses in all implementations
            
            else:
                # Call the API without streaming
                print(f"{Colors.CYAN}AI is thinking...{Colors.ENDC}")
                
                # Call the API
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=chat_history,
                    config=config
                )
                
                # Extract response text
                response_text = response.text
                
                # Print the response for non-streaming mode
                print(f"\n{Colors.GREEN}AI: {Colors.ENDC}{response_text}")
                try:
                    if hasattr(response, 'usage_metadata'):
                        # Extract token counts from the usage_metadata
                        token_usage = {
                            "prompt_token_count": getattr(response.usage_metadata, 'prompt_token_count', None),
                            "candidates_token_count": getattr(response.usage_metadata, 'candidates_token_count', None),
                            "total_token_count": getattr(response.usage_metadata, 'total_token_count', None)
                        }
                        # Filter out None values
                        token_usage = {k: v for k, v in token_usage.items() if v is not None}
                except Exception as e:
                    print(f"{Colors.WARNING}Warning: Could not extract token usage metadata: {e}{Colors.ENDC}")
            
            # Add AI response to history with enhanced metadata
            ai_message = {
                "type": "message",
                "content": {
                    "role": "ai",
                    "text": response_text,
                    "timestamp": datetime.now().isoformat(),
                    "model": self.model,
                    "params": self.params.copy(),
                    "token_usage": token_usage
                }
            }
            self.conversation_history.append(ai_message)
            
            # Update metadata in conversation history
            for item in self.conversation_history:
                if item["type"] == "metadata":
                    item["content"]["updated_at"] = datetime.now().isoformat()
                    item["content"]["model"] = self.model
                    item["content"]["params"] = self.params.copy()
                    break
            
            # Auto-save after every message exchange
            print(f"\n{Colors.CYAN}Auto-saving conversation...{Colors.ENDC}")
            self.save_conversation(quiet=True)
            
            return response_text
        except Exception as e:
            print(f"{Colors.FAIL}Error generating response: {e}{Colors.ENDC}")
            return None
    
    def chat_loop(self) -> None:
        """Main chat loop for the application."""
        if not self.conversation_id:
            self.start_new_conversation()
        
        print(f"\n{Colors.HEADER}Chat Session Started{Colors.ENDC}")
        print(f"Type {Colors.BOLD}/help{Colors.ENDC} to see available commands")
        
        while True:
            try:
                user_input = input(f"\n{Colors.BLUE}You: {Colors.ENDC}")
                
                # Handle commands
                if user_input.startswith('/'):
                    command = user_input.split()[0].lower()
                    
                    if command == '/help':
                        self.display_help()
                    elif command == '/quit' or command == '/exit':
                        print("Saving conversation before exit...")
                        self.save_conversation()
                        print(f"{Colors.GREEN}Goodbye!{Colors.ENDC}")
                        break
                    elif command == '/save':
                        self.save_conversation()
                    elif command == '/new':
                        self.save_conversation()  # Save current conversation
                        self.start_new_conversation()
                    elif command == '/list':
                        self.display_conversations()
                    elif command == '/load':
                        self.save_conversation()  # Save current conversation
                        self.load_conversation()
                    elif command == '/history':
                        self.display_conversation_history()
                    elif command == '/model':
                        self.select_model()
                    elif command == '/params':
                        self.customize_params()
                    elif command == '/clear':
                        os.system('cls' if os.name == 'nt' else 'clear')
                    elif command == '/stream':
                        self.use_streaming = not self.use_streaming
                        status = "enabled" if self.use_streaming else "disabled"
                        print(f"{Colors.GREEN}Streaming mode {status}.{Colors.ENDC}")
                    else:
                        print(f"{Colors.WARNING}Unknown command. Type /help for available commands.{Colors.ENDC}")
                    
                    continue
                
                # Process normal message
                if self.conversation_id is None:
                    self.start_new_conversation()
                
                # Send message and get response - no thinking message here, it's handled in send_message
                response = self.send_message(user_input)
                
                # No response printing here either - it's all handled in send_message
                if not response:
                    print(f"{Colors.WARNING}No response received.{Colors.ENDC}")
            
            except KeyboardInterrupt:
                print("\nDetected Ctrl+C. Saving conversation...")
                self.save_conversation()
                print(f"{Colors.GREEN}Goodbye!{Colors.ENDC}")
                break
            except Exception as e:
                print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")
    
    def display_help(self) -> None:
        """Display available commands."""
        print(f"\n{Colors.HEADER}Available Commands:{Colors.ENDC}")
        commands = [
            ("/help", "Show this help message"),
            ("/quit", "Save and exit the application"),
            ("/save", "Save the current conversation"),
            ("/new", "Start a new conversation"),
            ("/list", "List saved conversations"),
            ("/load", "Load a saved conversation"),
            ("/history", "Display current conversation history"),
            ("/model", "Select a different model"),
            ("/params", "Customize generation parameters"),
            ("/stream", "Toggle streaming mode (current: " + ("ON" if self.use_streaming else "OFF") + ")"),
            ("/clear", "Clear the screen")
        ]
        
        for cmd, desc in commands:
            print(f"  {Colors.BOLD}{cmd}{Colors.ENDC} - {desc}")
    
    def main(self) -> None:
        """Main entry point for the application."""
        parser = argparse.ArgumentParser(description="Gemini Chat - A command-line interface for Google's Gemini models")
        parser.add_argument('--api-key', help='Gemini API key (overrides environment variable)')
        parser.add_argument('--model', help=f'Model to use (default: {self.DEFAULT_MODEL})')
        parser.add_argument('--conversations-dir', help='Directory to store conversations')
        
        args = parser.parse_args()
        
        # Apply command-line arguments if provided
        if args.api_key:
            self.api_key = args.api_key
        else:
            # Try to get API key from environment
            self.api_key = os.environ.get("GEMINI_API_KEY")
            
            if not self.api_key:
                print(f"{Colors.WARNING}No GEMINI_API_KEY found in environment variables.{Colors.ENDC}")
                self.api_key = getpass.getpass("Please enter your Gemini API key: ")
        
        # Initialize client with API key
        try:
            print(f"Initializing client with API key: {self.api_key[:4]}...{self.api_key[-4:]}")
            self.client = genai.Client(api_key=self.api_key)
            print(f"{Colors.GREEN}Successfully connected to Gemini API.{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}Failed to initialize Gemini client: {e}{Colors.ENDC}")
            exit(1)
        
        if args.model:
            self.model = args.model
            print(f"Using model: {self.model}")
        
        if args.conversations_dir:
            self.conversations_dir = Path(args.conversations_dir)
            self.ensure_directories()
        
        # Start the chat loop
        self.chat_loop()

if __name__ == "__main__":
    # Display welcome message
    print(f"{Colors.HEADER}{Colors.BOLD}")
    print("╔═════════════════════════════════════════╗")
    print("║         Gemini Chat Application         ║")
    print("║         ----------------------          ║")
    print("║  A command-line interface for Google's  ║")
    print("║            Gemini AI models             ║")
    print("╚═════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")
    
    app = GeminiChat()
    app.main()
