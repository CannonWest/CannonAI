# import os # Not used directly at top level
import sys  # Used for sys.exit
import argparse
import asyncio
from pathlib import Path
from typing import Dict, Any  # Optional removed as not used in top-level type hints here

# Import configuration
from config import Config

# Import client management
from client_manager import ClientManager  # initialize_client was removed from client_manager
from providers import ProviderError  # To catch provider related errors during client creation

# Import command handling
from command_handler import sync_command_loop, async_command_loop

# Import colors
from base_client import Colors


# from gui.server import start_gui_server # Imported locally when --gui is used


def display_welcome_message():
    """Display the welcome message for the CannonAI application."""
    # ANSI escape codes for color and style
    header_color = "\033[95m"  # Magenta
    bold_style = "\033[1m"
    end_color = "\033[0m"

    # Using Colors class if available and preferred
    if hasattr(Colors, 'HEADER') and hasattr(Colors, 'BOLD') and hasattr(Colors, 'ENDC'):
        header_color = Colors.HEADER
        bold_style = Colors.BOLD
        end_color = Colors.ENDC

    print(f"{header_color}{bold_style}")
    print("╔═════════════════════════════════════════╗")
    print("║           CannonAI Application          ║")
    print("║         ----------------------          ║")
    print("║    An interface for multiple AI models  ║")  # Updated description
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
    parser.add_argument('--api-key',
                        help='API key for the specified or default provider. Overrides config and environment variable.')
    parser.add_argument('--provider',
                        help='AI provider to use (e.g., gemini, claude, openai). Defaults to provider set in config.')
    parser.add_argument('--model',
                        help='Model to use (e.g., gemini-2.0-flash, claude-3-opus-20240229). Overrides provider default in config.')
    # parser.add_argument('--async', dest='async_mode', action='store_true', # Async is now default for client
    #                     help='Use asynchronous client implementation')
    parser.add_argument('--dir', '--conversations-dir', dest='conversations_dir',
                        help='Directory to store conversations. Overrides config.')
    parser.add_argument('--gui', action='store_true',
                        help='Launch with GUI interface (Flask + Bootstrap)')

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

    # Prepare API key override dictionary
    override_api_key_dict = {}
    if args.api_key:
        # If --api-key is given, it's for the --provider if specified, or for the default_provider from config.
        # The Config class will determine the default_provider if args.provider is None.
        # We need to know which provider this key is for.
        # For simplicity now, if --api-key is given, we assume it's for the provider that will be active.
        # Config's get_api_key will check this dict first.
        # A more robust way would be --gemini-api-key, --openai-api-key etc.
        # For now, we'll pass it and let Config decide if it's used for the determined provider.
        # The Config class's __init__ was changed to override_api_key_dict.
        # We need to determine the target provider for this single API key.
        # If args.provider is set, use that. Otherwise, we can't know yet, so we pass it to Config
        # and Config can use it if the default_provider matches.
        # A better approach: Config takes this single key and applies it if the active provider needs it.
        # Let's assume the config will handle this: if a provider is chosen, and this dict has its key, it's used.
        # The issue is `args.api_key` is a string, `override_api_key_dict` expects a dict.
        # We need to determine the provider *before* initializing Config if we want to pass a targeted dict.
        # OR Config needs to be smarter.
        # Let's make a provisional dict. The actual provider is determined later by ClientManager.
        # This is slightly tricky. The Config needs the override *at init time*.

        # If a provider is specified via CLI, the API key is for that provider.
        # If no provider is specified, the API key is for the *default* provider (which Config knows).
        # So, we can determine the target provider for the CLI API key.

        target_provider_for_cli_key = args.provider  # If None, Config will use its default_provider
        # We can't know the default_provider from config *before* initializing config.
        # So, let's pass a special marker or handle it post-config-load.
        # For now, let's pass it as a dict with a placeholder key if provider isn't specified,
        # or the specified provider. This is still imperfect.

        # Corrected approach:
        # Initialize config *without* CLI API key override first, to find out default provider.
        # Then, if CLI API key is given, create the dict and re-init or update config.
        # OR, pass the args to Config, and Config can internally use args.api_key and args.provider.

        # Simpler: The `override_api_key_dict` in `Config` is for multiple overrides.
        # If `args.api_key` is given, it's for the *active* provider.
        # The active provider is determined by `args.provider` or `config.default_provider`.

        # Initialize Config first to see what the default provider would be
        temp_config_for_provider_check = Config(args.config, quiet=True)  # Load config to check default provider
        provider_for_cli_api_key = args.provider or temp_config_for_provider_check.get("default_provider", "gemini")

        if args.api_key:
            override_api_key_dict = {provider_for_cli_api_key: args.api_key}
            print(f"[Main] CLI API key provided will be used for provider: {provider_for_cli_api_key}")

    config = Config(args.config, override_api_key_dict=override_api_key_dict, quiet=True)

    if args.setup:
        config.setup_wizard()
        sys.exit(0)

    display_welcome_message()

    # Determine effective generation parameters by layering: config -> CLI args
    effective_gen_params = config.get("generation_params", {}).copy()
    if args.temperature is not None: effective_gen_params["temperature"] = args.temperature
    if args.max_tokens is not None: effective_gen_params["max_output_tokens"] = args.max_tokens  # Note: key is max_output_tokens
    if args.top_p is not None: effective_gen_params["top_p"] = args.top_p
    if args.top_k is not None: effective_gen_params["top_k"] = args.top_k

    # Determine effective streaming mode: CLI arg > config
    effective_use_streaming = args.use_streaming_arg if args.use_streaming_arg is not None else config.get("use_streaming", False)

    if args.gui:
        print(f"{Colors.BLUE}Starting GUI mode (Flask + Bootstrap)...{Colors.ENDC}")
        try:
            from gui.server import start_gui_server
            # GUI server will use the config object to create its own client instance via ClientManager
            start_gui_server(config,
                             host="127.0.0.1",  # Can be made configurable
                             port=8080,  # Can be made configurable
                             cli_args=args)  # Pass CLI args for GUI to potentially use overrides
        except ImportError as e:
            print(f"{Colors.FAIL}Error: GUI components not found or import failed: {e}{Colors.ENDC}")
            print(f"{Colors.WARNING}Please ensure Flask and other GUI dependencies are installed and paths are correct.{Colors.ENDC}")
            sys.exit(1)
        except Exception as e:
            print(f"{Colors.FAIL}Error starting GUI: {e}{Colors.ENDC}")
            sys.exit(1)
        return  # Exit after starting GUI (or attempting to)

    # --- CLI Mode ---
    print(f"{Colors.CYAN}Starting CLI mode...{Colors.ENDC}")

    try:
        # ClientManager now takes the main config object and CLI overrides
        client = ClientManager.create_client(
            config=config,
            provider_name_override=args.provider,
            model_override=args.model,
            conversations_dir_override=Path(args.conversations_dir) if args.conversations_dir else None,
            params_override=effective_gen_params,  # Pass the fully resolved params
            use_streaming_override=effective_use_streaming
        )
    except (ValueError, ProviderError) as e:  # Catch errors from client/provider creation
        print(f"{Colors.FAIL}Error creating AI client: {e}{Colors.ENDC}")
        sys.exit(1)

    # Initialize the client (which initializes the provider)
    # For CLI, we assume async client is preferred.
    # If a sync CLI is ever needed, this part would branch.
    asyncio.run(async_initialize_and_run(client))


async def async_initialize_and_run(client):
    """Initialize async client and run command loop.

    Args:
        client: The async client to initialize and run
    """
    if not await client.initialize_client():  # This calls provider.initialize()
        print(f"{Colors.FAIL}Failed to initialize the AI client (provider: {client.provider.provider_name}). Exiting.{Colors.ENDC}")
        sys.exit(1)

    # Run async command loop
    await async_command_loop(client)


if __name__ == "__main__":
    main()
