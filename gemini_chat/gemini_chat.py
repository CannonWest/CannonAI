#!/usr/bin/env python3
"""
Gemini Chat - Main Entry Point

This is the single, unified entry point for the Gemini Chat application.
It handles command-line arguments, configuration, and launches the appropriate mode:
1. CLI - Traditional command-line interface
2. GUI - ttkbootstrap-based graphical interface
3. Web - React-based web interface with FastAPI backend
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
        description="Gemini Chat - A powerful interface for Google's Gemini models"
    )
    
    # Main arguments
    parser.add_argument('--api-key', help='Gemini API key (overrides config and environment variable)')
    parser.add_argument('--model', help='Model to use (default: from config or gemini-2.0-flash)')
    parser.add_argument('--async', dest='async_mode', action='store_true', 
                        help='Use asynchronous client implementation')
    parser.add_argument('--dir', '--conversations-dir', dest='conversations_dir',
                       help='Directory to store conversations')
    
    # UI mode selection (mutually exclusive)
    ui_group = parser.add_argument_group('UI Mode')
    ui_mode = ui_group.add_mutually_exclusive_group()
    ui_mode.add_argument('--ui', '-ui', dest='ui_mode', action='store_true',
                       help='Launch with ttkbootstrap graphical user interface (uses async mode)')
    ui_mode.add_argument('--web', '-web', dest='web_mode', action='store_true',
                       help='Launch with React web interface (uses async mode)')
    
    # Web server options
    web_group = parser.add_argument_group('Web Server Options')
    web_group.add_argument('--host', default='127.0.0.1', help='Host to bind web server to')
    web_group.add_argument('--port', type=int, default=8000, help='Port to bind web server to')
    web_group.add_argument('--static-dir', help='Path to static files for web interface')
    
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
    
    # If GUI or web mode is requested, always use async mode
    if args.ui_mode or args.web_mode:
        args.async_mode = True
    
    # Display welcome message (only in CLI mode)
    if not args.ui_mode and not args.web_mode:
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
    
    # Check which mode to launch
    if args.web_mode:
        # Import here to avoid circular imports
        from ui.server import run_server
        
        # Determine static directory for web files (or build it)
        static_dir = args.static_dir
        if not static_dir:
            # Use default location - frontend/build folder
            frontend_dir = Path(__file__).resolve().parent / "ui" / "frontend" / "build"
            if frontend_dir.exists():
                static_dir = str(frontend_dir)
            else:
                print(f"{Colors.WARNING}Warning: Static files directory not found at {frontend_dir}{Colors.ENDC}")
                print(f"{Colors.WARNING}Running in API-only mode. Use 'npm run build' in the frontend directory to build the UI.{Colors.ENDC}")
        
        # Run the web server (blocking)
        try:
            run_server(
                host=args.host,
                port=args.port,
                static_dir=static_dir
            )
        except Exception as e:
            print(f"{Colors.FAIL}Error launching web server: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    elif args.ui_mode:
        # Import here to avoid circular imports
        from ui_client import launch_ui
        
        # Initialize UI with async client (don't block if no API key)
        try:
            asyncio.run(launch_ui(client, config))
        except Exception as e:
            print(f"{Colors.FAIL}Error launching UI: {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # Initialize the client for CLI mode
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
