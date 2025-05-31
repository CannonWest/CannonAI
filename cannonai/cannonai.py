# import os # Not used directly at top level
import sys  # Used for sys.exit
import argparse
import asyncio
from pathlib import Path
from typing import Dict, Any  # Optional removed as not used in top-level type hints here

# Import configuration
from config import Config # Import SUPPORTED_PROVIDERS

# Import client management
from client_manager import ClientManager
from providers import ProviderError  # To catch provider related errors during client creation

# Import command handling
from command_handler import sync_command_loop, async_command_loop

# Import colors
from base_client import Colors


# from gui.server import start_gui_server # Imported locally when --gui is used


def display_welcome_message():
    """Display the welcome message for the CannonAI application."""
    header_color = "\033[95m"  # Magenta
    bold_style = "\033[1m"
    end_color = "\033[0m"

    if hasattr(Colors, 'HEADER') and hasattr(Colors, 'BOLD') and hasattr(Colors, 'ENDC'):
        header_color = Colors.HEADER
        bold_style = Colors.BOLD
        end_color = Colors.ENDC

    print(f"{header_color}{bold_style}")
    print("╔═════════════════════════════════════════╗")
    print("║           CannonAI Application          ║")
    print("║         ----------------------          ║")
    print("║    An interface for multiple AI models  ║")
    print("╚═════════════════════════════════════════╝")
    print(f"{end_color}")


def parse_arguments():
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="CannonAI - A versatile interface for multiple AI providers."
    )

    # Main arguments
    # --api-key is now only for CLI mode and applies to the active provider.
    # It will be ignored if --gui is present.
    parser.add_argument('--api-key',
                        help='API key for the active provider (CLI mode only). Overrides config and environment variables for the session. Ignored if --gui is used.')
    parser.add_argument('--provider',
                        choices=Config.SUPPORTED_PROVIDERS + [None], # Allow None to use config default
                        default=None,
                        help=f'AI provider to use (e.g., {", ".join(Config.SUPPORTED_PROVIDERS)}). Defaults to provider set in config.')
    parser.add_argument('--model',
                        help='Model to use (e.g., gemini-2.0-flash, claude-3-opus-20240229). Overrides provider default in config.')
    parser.add_argument('--dir', '--conversations-dir', dest='conversations_dir',
                        help='Directory to store conversations. Overrides config.')
    parser.add_argument('--gui', action='store_true',
                        help='Launch with GUI interface. CLI --api-key is ignored in GUI mode.')
    parser.add_argument('--quiet', action='store_true',
                        help='Suppress non-essential output messages (like "Config loaded").')


    # Configuration options
    config_group = parser.add_argument_group('Configuration')
    config_group.add_argument('--config', help='Path to configuration file.')
    config_group.add_argument('--setup', action='store_true',
                              help='Run configuration setup wizard.')

    # Advanced options for generation parameters
    advanced_group = parser.add_argument_group('Generation Parameters (Overrides Config)')
    advanced_group.add_argument('--temp', '--temperature', type=float, dest='temperature',
                                help='Generation temperature (e.g., 0.7).')
    advanced_group.add_argument('--max-tokens', type=int, dest='max_tokens',
                                help='Maximum output tokens (e.g., 800).')
    advanced_group.add_argument('--top-p', type=float, dest='top_p',
                                help='Top-p sampling parameter (e.g., 0.95).')
    advanced_group.add_argument('--top-k', type=int, dest='top_k',
                                help='Top-k sampling parameter (e.g., 40).')
    advanced_group.add_argument('--stream', action='store_true', dest='use_streaming_arg', default=None,
                                help='Enable streaming mode by default for this session.')
    advanced_group.add_argument('--no-stream', action='store_false', dest='use_streaming_arg',
                                help='Disable streaming mode by default for this session.')

    return parser.parse_args()


def main():
    """Main entry point for the application."""
    args = parse_arguments()

    override_api_key_dict = {}
    # Determine quiet mode for Config initialization.
    # If --setup is passed, Config should be quiet to avoid "Config loaded" before wizard.
    # If --quiet is passed, Config should also be quiet.
    config_init_quiet = args.setup or args.quiet

    if args.gui:
        if not args.quiet: # Only print if not globally quiet
            print(f"{Colors.CYAN}GUI mode enabled. CLI --api-key will be ignored. API keys should be managed via GUI settings or config file.{Colors.ENDC}")
        # No override_api_key_dict for GUI mode.
    elif args.api_key:
        # For CLI mode, determine the target provider for the --api-key
        # Load a temporary config to find the default provider if args.provider is not set
        temp_config_for_provider_check = Config(args.config, quiet=True) # Always quiet for this temp instance
        active_provider_for_cli_key = args.provider or temp_config_for_provider_check.get("default_provider", "gemini")
        override_api_key_dict = {active_provider_for_cli_key.lower(): args.api_key}
        if not args.quiet: # Only print if not globally quiet
            print(f"{Colors.CYAN}[Main] CLI --api-key provided. It will be used for provider: {active_provider_for_cli_key}{Colors.ENDC}")

    # Initialize main config
    config = Config(args.config, override_api_key_dict=override_api_key_dict, quiet=config_init_quiet)


    if args.setup:
        config.setup_wizard() # Wizard uses its own print statements
        sys.exit(0)

    display_welcome_message()
    # The "Config loaded from..." message is now handled by Config class itself based on its quiet flag.

    # Determine effective generation parameters by layering: config -> CLI args
    effective_gen_params = config.get("generation_params", {}).copy()
    if args.temperature is not None: effective_gen_params["temperature"] = args.temperature
    if args.max_tokens is not None: effective_gen_params["max_output_tokens"] = args.max_tokens
    if args.top_p is not None: effective_gen_params["top_p"] = args.top_p
    if args.top_k is not None: effective_gen_params["top_k"] = args.top_k

    effective_use_streaming = args.use_streaming_arg if args.use_streaming_arg is not None else config.get("use_streaming", False)

    if args.gui:
        if not args.quiet:
            print(f"{Colors.BLUE}Starting GUI mode (Flask + Bootstrap)...{Colors.ENDC}")
        try:
            from gui.server import start_gui_server
            start_gui_server(config,
                             host="127.0.0.1",
                             port=8080,
                             cli_args=args)
        except ImportError as e:
            print(f"{Colors.FAIL}Error: GUI components not found or import failed: {e}{Colors.ENDC}")
            print(f"{Colors.WARNING}Please ensure Flask and other GUI dependencies are installed and paths are correct.{Colors.ENDC}")
            sys.exit(1)
        except Exception as e:
            print(f"{Colors.FAIL}Error starting GUI: {e}{Colors.ENDC}")
            sys.exit(1)
        return

    # --- CLI Mode ---
    if not args.quiet:
        print(f"{Colors.CYAN}Starting CLI mode...{Colors.ENDC}")

    try:
        client = ClientManager.create_client(
            config=config, # Main config object
            provider_name_override=args.provider,
            model_override=args.model,
            conversations_dir_override=Path(args.conversations_dir) if args.conversations_dir else None,
            params_override=effective_gen_params,
            use_streaming_override=effective_use_streaming
        )
    except (ValueError, ProviderError) as e:
        print(f"{Colors.FAIL}Error creating AI client: {e}{Colors.ENDC}")
        sys.exit(1)

    asyncio.run(async_initialize_and_run(client))


async def async_initialize_and_run(client):
    """Initialize async client and run command loop.

    Args:
        client: The async client to initialize and run
    """
    if not await client.initialize_client():
        print(f"{Colors.FAIL}Failed to initialize the AI client (provider: {client.provider.provider_name}). Exiting.{Colors.ENDC}")
        sys.exit(1)

    await async_command_loop(client)


if __name__ == "__main__":
    main()
