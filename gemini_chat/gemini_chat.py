#!/usr/bin/env python3
"""
Gemini Chat CLI - Main Entry Point

This is the single, unified entry point for the Gemini Chat CLI application.
It handles command-line arguments, configuration, and launches the appropriate mode.
"""

import os
import sys
import argparse
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

# Import configuration
from config import Config

# Import client management
from client_manager import ClientManager, initialize_client

# Import command handling
from command_handler import sync_command_loop, async_command_loop

# Import colors
from base_client import Colors


def display_welcome_message():
    """Display the welcome message for the Gemini Chat application."""
    print(f"{Colors.HEADER}{Colors.BOLD}")
    print("╔═════════════════════════════════════════╗")
    print("║         Gemini Chat Application         ║")
    print("║         ----------------------          ║")
    print("║  A command-line interface for Google's  ║")
    print("║            Gemini AI models             ║")
    print("╚═════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")


def parse_arguments():
    """Parse command-line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Gemini Chat CLI - A powerful interface for Google's Gemini models"
    )
    
    # Main arguments
    parser.add_argument('--api-key', help='Gemini API key (overrides config and environment variable)')
    parser.add_argument('--model', help='Model to use (default: from config or gemini-2.0-flash)')
    parser.add_argument('--async', dest='async_mode', action='store_true', 
                        help='Use asynchronous client implementation')
    parser.add_argument('--dir', '--conversations-dir', dest='conversations_dir',
                       help='Directory to store conversations')
    parser.add_argument('--ui', action='store_true',
                       help='Launch with web UI interface')
    
    # Configuration options
    config_group = parser.add_argument_group('Configuration')
    config_group.add_argument('--config', help='Path to configuration file')
    config_group.add_argument('--setup', action='store_true', 
                             help='Run configuration setup wizard')
    
    # Advanced options
    advanced_group = parser.add_argument_group('Advanced')
    advanced_group.add_argument('--temp', '--temperature', type=float, dest='temperature',
                               help='Generation temperature (0.0-2.0)')
    advanced_group.add_argument('--max-tokens', type=int, dest='max_tokens',
                               help='Maximum output tokens')
    advanced_group.add_argument('--top-p', type=float, dest='top_p',
                               help='Top-p sampling parameter (0.0-1.0)')
    advanced_group.add_argument('--top-k', type=int, dest='top_k',
                               help='Top-k sampling parameter')
    advanced_group.add_argument('--stream', action='store_true', dest='use_streaming',
                               help='Enable streaming mode by default')
    
    return parser.parse_args()


def main():
    """Main entry point for the application."""
    # Parse arguments
    args = parse_arguments()
    
    # Load configuration with API key from command line and suppress first load message
    config = Config(args.config, override_api_key=args.api_key, quiet=True)
    
    # Run setup wizard if requested
    if args.setup:
        config.setup_wizard()
        sys.exit(0)
    
    # Launch web UI if requested
    if args.ui:
        display_welcome_message()
        print(f"{Colors.BLUE}Starting Web UI mode...{Colors.ENDC}")
        try:
            # Import the UI module
            try:
                from ui.server import start_web_ui
                start_web_ui(config)
            except ModuleNotFoundError:
                print(f"{Colors.FAIL}Error: Required UI packages not installed{Colors.ENDC}")
                print(f"{Colors.WARNING}Please install UI dependencies: pip install -r gemini_chat/ui_requirements.txt{Colors.ENDC}")
                sys.exit(1)
        except ImportError as e:
            print(f"{Colors.FAIL}Error: {e}{Colors.ENDC}")
            print(f"{Colors.WARNING}Please install required packages: pip install fastapi uvicorn websockets{Colors.ENDC}")
            sys.exit(1)
        except Exception as e:
            print(f"{Colors.FAIL}Error starting Web UI: {e}{Colors.ENDC}")
            sys.exit(1)
        return
    
    # Display welcome message
    display_welcome_message()
    
    # Merge configuration with command-line arguments
    api_key = args.api_key or config.get_api_key()
    model = args.model or config.get("default_model")
    conversations_dir = args.conversations_dir or config.get("conversations_dir")
    
    # Convert conversations_dir to Path if provided
    if conversations_dir:
        conversations_dir = Path(conversations_dir)
    
    # Get generation parameters
    gen_params = config.get("generation_params", {}).copy()
    
    # Override with command-line arguments if provided
    if args.temperature is not None:
        gen_params["temperature"] = args.temperature
    if args.max_tokens is not None:
        gen_params["max_output_tokens"] = args.max_tokens
    if args.top_p is not None:
        gen_params["top_p"] = args.top_p
    if args.top_k is not None:
        gen_params["top_k"] = args.top_k
    
    # Determine streaming mode
    use_streaming = args.use_streaming if args.use_streaming is not None else config.get("use_streaming", False)
    
    # Create client
    client = ClientManager.create_client(
        async_mode=args.async_mode,
        api_key=api_key,
        model=model,
        conversations_dir=conversations_dir,
        params=gen_params,
        use_streaming=use_streaming
    )
    
    # Initialize the client
    if args.async_mode:
        # Initialize async client and run command loop
        asyncio.run(async_initialize_and_run(client))
    else:
        # Initialize sync client
        if not client.initialize_client():
            print(f"{Colors.FAIL}Failed to initialize client. Exiting.{Colors.ENDC}")
            sys.exit(1)
        
        # Run sync command loop
        sync_command_loop(client)


async def async_initialize_and_run(client):
    """Initialize async client and run command loop.
    
    Args:
        client: The async client to initialize and run
    """
    # Initialize the client
    if not await client.initialize_client():
        print(f"{Colors.FAIL}Failed to initialize async client. Exiting.{Colors.ENDC}")
        sys.exit(1)
    
    # Run async command loop
    await async_command_loop(client)


if __name__ == "__main__":
    main()
