"""
Gemini Chat CLI - Command Handler Module

This module provides command handling functionality for the Gemini Chat CLI
application, supporting both synchronous and asynchronous clients.
"""

import os
import sys
from typing import Union, Callable, Any, Dict, Optional, List, Tuple

from base_client import Colors


class CommandHandler:
    """Unified command handler for both sync and async clients."""
    
    def __init__(self, client):
        """Initialize the command handler.
        
        Args:
            client: The client instance (sync or async)
        """
        self.client = client
        self.is_async = hasattr(client, 'initialize_client') and callable(getattr(client, 'initialize_client')) and 'async' in getattr(client.initialize_client, '__code__').co_varnames
        self.commands = self._build_command_map()
    
    def _build_command_map(self) -> Dict[str, Dict[str, Any]]:
        """Build a map of commands and their handlers.
        
        Returns:
            Dictionary mapping command names to their handlers and descriptions
        """
        # Common commands for both sync and async
        commands = {
            "/help": {
                "handler": self.cmd_help,
                "description": "Show help message"
            },
            "/quit": {
                "handler": self.cmd_quit,
                "description": "Save and exit the application",
                "aliases": ["/exit"]
            },
            "/save": {
                "handler": self.cmd_save,
                "description": "Save the current conversation"
            },
            "/new": {
                "handler": self.cmd_new,
                "description": "Start a new conversation"
            },
            "/list": {
                "handler": self.cmd_list,
                "description": "List saved conversations"
            },
            "/load": {
                "handler": self.cmd_load,
                "description": "Load a saved conversation"
            },
            "/history": {
                "handler": self.cmd_history,
                "description": "Display conversation history"
            },
            "/model": {
                "handler": self.cmd_model,
                "description": "Select a different model"
            },
            "/params": {
                "handler": self.cmd_params,
                "description": "Customize generation parameters"
            },
            "/stream": {
                "handler": self.cmd_stream,
                "description": f"Toggle streaming mode (current: {'ON' if self.client.use_streaming else 'OFF'})"
            },
            "/clear": {
                "handler": self.cmd_clear,
                "description": "Clear the screen"
            },
            "/version": {
                "handler": self.cmd_version,
                "description": "Show version information"
            },
            "/config": {
                "handler": self.cmd_config,
                "description": "Open configuration settings"
            }
        }
        
        return commands
    
    async def async_handle_command(self, command: str) -> bool:
        """Handle a command asynchronously.
        
        Args:
            command: The command to handle
            
        Returns:
            True if the application should exit, False otherwise
        """
        # Parse command and arguments
        parts = command.lower().split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        
        # Check for command aliases
        for command_key, info in self.commands.items():
            aliases = info.get("aliases", [])
            if cmd == command_key or cmd in aliases:
                # Call the method with await since we're in an async context
                # Pass arguments if the command accepts them
                handler = info["handler"]
                if args and (cmd == "/model" or cmd == "/load"):
                    result = await handler(args)
                else:
                    result = await handler()
                return result
        
        print(f"{Colors.WARNING}Unknown command. Type /help for available commands.{Colors.ENDC}")
        return False
    
    def sync_handle_command(self, command: str) -> bool:
        """Handle a command synchronously.
        
        Args:
            command: The command to handle
            
        Returns:
            True if the application should exit, False otherwise
        """
        # Parse command and arguments
        parts = command.lower().split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        
        # Check for command aliases
        for command_key, info in self.commands.items():
            aliases = info.get("aliases", [])
            if cmd == command_key or cmd in aliases:
                # Call the sync version of the method
                sync_method = getattr(self, f"sync_{info['handler'].__name__}")
                
                # Pass arguments if the command accepts them
                if args and (cmd == "/model" or cmd == "/load"):
                    result = sync_method(args)
                else:
                    result = sync_method()
                return result
        
        print(f"{Colors.WARNING}Unknown command. Type /help for available commands.{Colors.ENDC}")
        return False
    
    def handle_command(self, command: str) -> bool:
        """Handle a command (sync or async as appropriate).
        
        Args:
            command: The command to handle
            
        Returns:
            True if the application should exit, False otherwise
        """
        if self.is_async:
            # This isn't really proper, but it's just a wrapper to avoid
            # having to deal with async/sync distinction at call site
            import asyncio
            return asyncio.run(self.async_handle_command(command))
        else:
            return self.sync_handle_command(command)
    
    # =============================================
    # Async command implementations
    # =============================================
    
    async def cmd_help(self) -> bool:
        """Display available commands (async version)."""
        print(f"\n{Colors.HEADER}Available Commands:{Colors.ENDC}")
        
        for cmd, info in sorted(self.commands.items()):
            print(f"  {Colors.BOLD}{cmd}{Colors.ENDC} - {info['description']}")
            if "aliases" in info and info["aliases"]:
                aliases = ", ".join(info["aliases"])
                print(f"      {Colors.CYAN}(aliases: {aliases}){Colors.ENDC}")
        
        return False
    
    async def cmd_quit(self) -> bool:
        """Save and exit the application (async version)."""
        print("Saving conversation before exit...")
        await self.client.save_conversation()
        print(f"{Colors.GREEN}Goodbye!{Colors.ENDC}")
        return True
    
    async def cmd_save(self) -> bool:
        """Save the current conversation (async version)."""
        await self.client.save_conversation()
        return False
    
    async def cmd_new(self) -> bool:
        """Start a new conversation (async version)."""
        await self.client.save_conversation()
        await self.client.start_new_conversation()
        return False
    
    async def cmd_list(self) -> bool:
        """List saved conversations (async version)."""
        await self.client.display_conversations()
        return False
    
    async def cmd_load(self, command_args: str = "") -> bool:
        """Load a saved conversation (async version).
        
        Args:
            command_args: Optional name or number of conversation to load directly
        """
        await self.client.save_conversation()
        
        # If we have a conversation name passed as an argument, use it
        if command_args.strip():
            await self.client.load_conversation(command_args.strip())
        else:
            # Otherwise use interactive mode
            await self.client.load_conversation()
        return False
    
    async def cmd_history(self) -> bool:
        """Display conversation history (async version)."""
        await self.client.display_conversation_history()
        return False
    
    async def cmd_model(self, command_args: str = "") -> bool:
        """Select a different model (async version).
        
        Args:
            command_args: Optional model name to switch to directly
        """
        # If model name is provided, try to set it directly
        if command_args.strip():
            model_name = command_args.strip()
            print(f"Attempting to set model to: {model_name}")
            
            # Check if the model is available (fetch models first)
            available_models = await self.client.get_available_models()
            
            # Map to keep both full path and short names
            model_map = {}
            for model in available_models:
                # Get both the full and short name
                full_name = model["name"]
                short_name = full_name.split('/')[-1] if '/' in full_name else full_name
                model_map[short_name.lower()] = full_name
                model_map[full_name.lower()] = full_name
            
            # Check if the provided model name exists (case insensitive)
            if model_name.lower() in model_map:
                # Set the model
                actual_model_name = model_map[model_name.lower()]
                self.client.model = actual_model_name
                print(f"{Colors.GREEN}Model set to: {self.client.model}{Colors.ENDC}")
                return False
            else:
                print(f"{Colors.WARNING}Model '{model_name}' not found. Available models:{Colors.ENDC}")
                # Show the model list if the provided name is not found
                await self.client.display_models()
                return False
        
        # No model name provided, show the list as usual
        await self.client.select_model()
        return False
    
    async def cmd_params(self) -> bool:
        """Customize generation parameters (async version)."""
        await self.client.customize_params()
        return False
    
    async def cmd_clear(self) -> bool:
        """Clear the screen (async version)."""
        os.system('cls' if os.name == 'nt' else 'clear')
        return False
    
    async def cmd_stream(self) -> bool:
        """Toggle streaming mode (async version)."""
        await self.client.toggle_streaming()
        # Update the description
        self.commands["/stream"]["description"] = f"Toggle streaming mode (current: {'ON' if self.client.use_streaming else 'OFF'})"
        return False
    
    async def cmd_version(self) -> bool:
        """Show version information (async version)."""
        print(f"{Colors.CYAN}Gemini Chat CLI v{self.client.get_version()}{Colors.ENDC}")
        return False
    
    async def cmd_config(self) -> bool:
        """Open configuration settings (async version)."""
        # Import here to avoid circular imports
        from config import Config
        
        # Pass the current client's API key to the config
        api_key = self.client.api_key if hasattr(self.client, 'api_key') else None
        config = Config(override_api_key=api_key)
        config.setup_wizard()
        return False
    
    # =============================================
    # Sync command implementations
    # =============================================
    
    def sync_cmd_help(self) -> bool:
        """Display available commands (sync version)."""
        print(f"\n{Colors.HEADER}Available Commands:{Colors.ENDC}")
        
        for cmd, info in sorted(self.commands.items()):
            print(f"  {Colors.BOLD}{cmd}{Colors.ENDC} - {info['description']}")
            if "aliases" in info and info["aliases"]:
                aliases = ", ".join(info["aliases"])
                print(f"      {Colors.CYAN}(aliases: {aliases}){Colors.ENDC}")
        
        return False
    
    def sync_cmd_quit(self) -> bool:
        """Save and exit the application (sync version)."""
        print("Saving conversation before exit...")
        self.client.save_conversation()
        print(f"{Colors.GREEN}Goodbye!{Colors.ENDC}")
        return True
    
    def sync_cmd_save(self) -> bool:
        """Save the current conversation (sync version)."""
        self.client.save_conversation()
        return False
    
    def sync_cmd_new(self) -> bool:
        """Start a new conversation (sync version)."""
        self.client.save_conversation()
        self.client.start_new_conversation()
        return False
    
    def sync_cmd_list(self) -> bool:
        """List saved conversations (sync version)."""
        self.client.display_conversations()
        return False
    
    def sync_cmd_load(self) -> bool:
        """Load a saved conversation (sync version)."""
        self.client.save_conversation()
        self.client.load_conversation()
        return False
    
    def sync_cmd_history(self) -> bool:
        """Display conversation history (sync version)."""
        self.client.display_conversation_history()
        return False
    
    def sync_cmd_model(self, command_args: str = "") -> bool:
        """Select a different model (sync version).
        
        Args:
            command_args: Optional model name to switch to directly
        """
        # If model name is provided, try to set it directly
        if command_args.strip():
            model_name = command_args.strip()
            print(f"Attempting to set model to: {model_name}")
            
            # Check if the model is available (fetch models first)
            available_models = self.client.get_available_models()
            
            # Map to keep both full path and short names
            model_map = {}
            for model in available_models:
                # Get both the full and short name
                full_name = model["name"]
                short_name = full_name.split('/')[-1] if '/' in full_name else full_name
                model_map[short_name.lower()] = full_name
                model_map[full_name.lower()] = full_name
            
            # Check if the provided model name exists (case insensitive)
            if model_name.lower() in model_map:
                # Set the model
                actual_model_name = model_map[model_name.lower()]
                self.client.model = actual_model_name
                print(f"{Colors.GREEN}Model set to: {self.client.model}{Colors.ENDC}")
                return False
            else:
                print(f"{Colors.WARNING}Model '{model_name}' not found. Available models:{Colors.ENDC}")
                # Show the model list if the provided name is not found
                self.client.display_models()
                return False
        
        # No model name provided, show the list as usual
        self.client.select_model()
        return False
    
    def sync_cmd_params(self) -> bool:
        """Customize generation parameters (sync version)."""
        self.client.customize_params()
        return False
    
    def sync_cmd_clear(self) -> bool:
        """Clear the screen (sync version)."""
        os.system('cls' if os.name == 'nt' else 'clear')
        return False
    
    def sync_cmd_stream(self) -> bool:
        """Toggle streaming mode (sync version)."""
        self.client.toggle_streaming()
        # Update the description
        self.commands["/stream"]["description"] = f"Toggle streaming mode (current: {'ON' if self.client.use_streaming else 'OFF'})"
        return False
    
    def sync_cmd_version(self) -> bool:
        """Show version information (sync version)."""
        print(f"{Colors.CYAN}Gemini Chat CLI v{self.client.get_version()}{Colors.ENDC}")
        return False
    
    def sync_cmd_config(self) -> bool:
        """Open configuration settings (sync version)."""
        # Import here to avoid circular imports
        from config import Config
        
        # Pass the current client's API key to the config
        api_key = self.client.api_key if hasattr(self.client, 'api_key') else None
        config = Config(override_api_key=api_key)
        config.setup_wizard()
        return False


# Command-line interface
async def async_command_loop(client):
    """Run the command loop asynchronously.
    
    Args:
        client: The AsyncGeminiClient instance
    """
    # Initialize the command handler
    handler = CommandHandler(client)
    
    # Display welcome message and command options
    print(f"\n{Colors.HEADER}Welcome to Gemini Chat CLI!{Colors.ENDC}")
    print(f"\nType {Colors.BOLD}/new{Colors.ENDC} to start a new conversation")
    print(f"Type {Colors.BOLD}/list{Colors.ENDC} to see your saved conversations")
    print(f"Type {Colors.BOLD}/help{Colors.ENDC} for all available commands")
    
    while True:
        try:
            user_input = input(f"\n{Colors.BLUE}You: {Colors.ENDC}")
            
            # Handle commands
            if user_input.startswith('/'):
                command = user_input.split()[0].lower()
                should_exit = await handler.async_handle_command(command)
                if should_exit:
                    break
                continue
            
            # Process normal message
            if client.conversation_id is None:
                print(f"\n{Colors.WARNING}No active conversation. Please start a new one with /new first.{Colors.ENDC}")
                continue
            
            # Send message and get response
            response = await client.send_message(user_input)
            
            if not response:
                print(f"{Colors.WARNING}No response received.{Colors.ENDC}")
        
        except KeyboardInterrupt:
            print("\nDetected Ctrl+C. Saving conversation...")
            await client.save_conversation()
            print(f"{Colors.GREEN}Goodbye!{Colors.ENDC}")
            break
        except Exception as e:
            print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")


def sync_command_loop(client):
    """Run the command loop synchronously.
    
    Args:
        client: The SyncGeminiClient instance
    """
    # Initialize the command handler
    handler = CommandHandler(client)
    
    # Display welcome message and command options
    print(f"\n{Colors.HEADER}Welcome to Gemini Chat CLI!{Colors.ENDC}")
    print(f"\nType {Colors.BOLD}/new{Colors.ENDC} to start a new conversation")
    print(f"Type {Colors.BOLD}/list{Colors.ENDC} to see your saved conversations")
    print(f"Type {Colors.BOLD}/help{Colors.ENDC} for all available commands")
    
    while True:
        try:
            user_input = input(f"\n{Colors.BLUE}You: {Colors.ENDC}")
            
            # Handle commands
            if user_input.startswith('/'):
                command = user_input.split()[0].lower()
                should_exit = handler.sync_handle_command(command)
                if should_exit:
                    break
                continue
            
            # Process normal message
            if client.conversation_id is None:
                print(f"\n{Colors.WARNING}No active conversation. Please start a new one with /new first.{Colors.ENDC}")
                continue
            
            # Send message and get response
            response = client.send_message(user_input)
            
            if not response:
                print(f"{Colors.WARNING}No response received.{Colors.ENDC}")
        
        except KeyboardInterrupt:
            print("\nDetected Ctrl+C. Saving conversation...")
            client.save_conversation()
            print(f"{Colors.GREEN}Goodbye!{Colors.ENDC}")
            break
        except Exception as e:
            print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")
