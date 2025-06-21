#!/usr/bin/env python3
"""
CannonAI GUI Initialization Helpers - Manages async component setup

This module handles the initialization of async components for the GUI,
including setting up the event loop, creating the AI client, and managing
the thread that runs async operations.
"""

import asyncio
import logging
import time
from pathlib import Path
from threading import Thread
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from async_client import AsyncClient
    from command_handler import CommandHandler
    from config import Config
    from gui.api_handlers import APIHandlers

logger = logging.getLogger("cannonai.gui.init_helpers")


class AsyncComponentManager:
    """Manages async components for the GUI server."""

    def __init__(self):
        print("[Init] Creating AsyncComponentManager")
        self.event_loop: Optional[asyncio.AbstractEventLoop] = None
        self.loop_thread: Optional[Thread] = None
        self.chat_client: Optional['AsyncClient'] = None
        self.command_handler: Optional['CommandHandler'] = None
        self.api_handlers: Optional['APIHandlers'] = None
        self.main_config: Optional['Config'] = None
        self._initialization_complete = False
        self._initialization_error: Optional[str] = None

    def run_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Runs the asyncio event loop in a separate thread.

        Args:
            loop: The asyncio event loop to run
        """
        print("[Init] Starting asyncio event loop for GUI client in new thread")
        logger.info("Starting asyncio event loop for GUI client in a new thread.")
        asyncio.set_event_loop(loop)

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            print("[Init] GUI async loop interrupted by KeyboardInterrupt")
            logger.info("GUI Async event loop interrupted by KeyboardInterrupt.")
        finally:
            print("[Init] GUI async loop stopping...")
            logger.info("GUI Async event loop stopping...")

            # Cleanup tasks before stopping
            if not loop.is_closed():
                # Cancel all tasks
                tasks = asyncio.all_tasks(loop)
                print(f"[Init] Cancelling {len(tasks)} async tasks")
                for task in tasks:
                    task.cancel()

                # Request stop
                loop.call_soon_threadsafe(loop.stop)

            print("[Init] GUI async loop has stopped")
            logger.info("GUI Async event loop has stopped.")

    async def initialize_client_async(self, app_config: 'Config', cli_args: Optional[Any]) -> None:
        """
        Asynchronously initializes the AI client and API handlers.

        Args:
            app_config: The main application configuration
            cli_args: Command line arguments passed from main app
        """
        print("[Init] Starting async client initialization")
        logger.info("Initializing AI client and API handlers for GUI...")

        try:
            # Import here to avoid circular imports
            from gui.api_handlers import APIHandlers
            from client_manager import ClientManager
            from command_handler import CommandHandler
            from providers import ProviderError
            from provider_manager import ProviderManager  # *** ADDED: For seamless provider switching ***

            # Prepare effective parameters
            effective_params = app_config.get("generation_params", {}).copy()
            if cli_args and hasattr(cli_args, 'temperature') and cli_args.temperature is not None:
                effective_params['temperature'] = cli_args.temperature
            if cli_args and hasattr(cli_args, 'max_tokens') and cli_args.max_tokens is not None:
                effective_params['max_output_tokens'] = cli_args.max_tokens
            if cli_args and hasattr(cli_args, 'top_p') and cli_args.top_p is not None:
                effective_params['top_p'] = cli_args.top_p
            if cli_args and hasattr(cli_args, 'top_k') and cli_args.top_k is not None:
                effective_params['top_k'] = cli_args.top_k

            # Determine streaming preference
            effective_streaming = app_config.get("use_streaming", False)
            if cli_args and hasattr(cli_args, 'use_streaming_arg') and cli_args.use_streaming_arg is not None:
                effective_streaming = cli_args.use_streaming_arg

            print(f"[Init] Creating client with provider: {cli_args.provider if cli_args and hasattr(cli_args, 'provider') else 'default'}")

            # Create the AI client
            self.chat_client = ClientManager.create_client(
                config=app_config,
                provider_name_override=cli_args.provider if cli_args and hasattr(cli_args, 'provider') else None,
                model_override=cli_args.model if cli_args and hasattr(cli_args, 'model') else None,
                conversations_dir_override=Path(cli_args.conversations_dir) if cli_args and hasattr(cli_args, 'conversations_dir') and cli_args.conversations_dir else None,
                params_override=effective_params,
                use_streaming_override=effective_streaming
            )

            print("[Init] Client created, initializing...")

            # Initialize the client
            if not await self.chat_client.initialize_client():
                error_msg = "Failed to initialize AI client for GUI. Provider did not initialize."
                print(f"[Init] Error: {error_msg}")
                logger.error(error_msg)
                self.chat_client = None
                self._initialization_error = error_msg
                return

            print("[Init] Client initialized successfully, creating handlers...")

            # Create command handler
            self.command_handler = CommandHandler(self.chat_client)
            self.chat_client.is_web_ui = True  # Mark as web UI

            # Ensure event loop is available
            if self.event_loop is None:
                logger.critical("GUI Event loop is None during APIHandlers initialization!")
                try:
                    self.event_loop = asyncio.get_running_loop()
                    print("[Init] Retrieved running event loop")
                except RuntimeError:
                    error_msg = "No running event loop available. API Handlers cannot be initialized."
                    print(f"[Init] Critical error: {error_msg}")
                    logger.critical(error_msg)
                    self._initialization_error = error_msg
                    return

            # Create API handlers
            self.api_handlers = APIHandlers(self.chat_client, self.command_handler, self.event_loop)

            # *** ADDED: Create and set provider manager for seamless switching ***
            print("[Init] Creating provider manager for seamless provider switching...")
            provider_manager = ProviderManager(app_config)
            # Set initial provider in manager
            await provider_manager.switch_provider(self.chat_client.provider.provider_name, self.chat_client.current_model_name)
            self.api_handlers.set_provider_manager(provider_manager)
            print("[Init] Provider manager configured successfully")

            # Store main config reference in api_handlers module
            import gui.api_handlers as api_handlers_module
            api_handlers_module.main_config = app_config

            print(f"[Init] Initialization complete. Provider: {self.chat_client.provider.provider_name}, Model: {self.chat_client.current_model_name}")
            logger.info(f"GUI AI Client and API Handlers initialized. Provider: {self.chat_client.provider.provider_name}, Model: {self.chat_client.current_model_name}")

            self._initialization_complete = True

        except (ValueError, ProviderError) as e:
            error_msg = f"Configuration or Provider error creating AI client for GUI: {e}"
            print(f"[Init] Error: {error_msg}")
            logger.error(error_msg, exc_info=True)
            self.chat_client = None
            self._initialization_error = str(e)

        except Exception as e:
            error_msg = f"Unexpected error initializing AI client/API Handlers for GUI: {e}"
            print(f"[Init] Unexpected error: {error_msg}")
            logger.error(error_msg, exc_info=True)
            self.chat_client = None
            self._initialization_error = str(e)

    def initialize_async_components(self, app_config: 'Config', cli_args: Optional[Any]) -> None:
        """
        Initializes async components, creating event loop and thread if needed.

        Args:
            app_config: The main application configuration
            cli_args: Command line arguments
        """
        print("[Init] Initializing async components")
        self.main_config = app_config

        # Create event loop if needed
        if self.event_loop is None or self.event_loop.is_closed():
            self.event_loop = asyncio.new_event_loop()
            print("[Init] New asyncio event loop created for GUI components")
            logger.info("New asyncio event loop created for GUI components.")

        # Start loop thread if needed
        if self.loop_thread is None or not self.loop_thread.is_alive():
            self.loop_thread = Thread(
                target=self.run_async_loop,
                args=(self.event_loop,),
                daemon=True,
                name="GUI-AsyncLoop"
            )
            self.loop_thread.start()
            print("[Init] Asyncio event loop thread started for GUI")
            logger.info("Asyncio event loop thread started for GUI.")

        # =================== FIX START ===================
        # Wait for the loop to actually start running in the new thread to prevent a race condition.
        # This loop will pause the main thread for a very short time until the background
        # thread's event loop is confirmed to be running.
        wait_start_time = time.monotonic()
        while not self.event_loop.is_running():
            time.sleep(0.01) # Poll with a small delay
            if time.monotonic() - wait_start_time > 5: # Add a timeout to prevent an infinite loop
                self._initialization_error = "Timeout waiting for background event loop to start."
                logger.critical(self._initialization_error)
                return
        # =================== FIX END =====================

        # Schedule client initialization
        if self.event_loop and self.event_loop.is_running():
            print("[Init] Scheduling async client initialization")
            future = asyncio.run_coroutine_threadsafe(
                self.initialize_client_async(app_config, cli_args),
                self.event_loop
            )

            try:
                # Wait for initialization with timeout
                future.result(timeout=15)
                print("[Init] Async initialization completed successfully")
                logger.info("Async initialization of GUI client components scheduled and completed.")
            except asyncio.TimeoutError:
                error_msg = "Timeout waiting for async initialization of GUI client components."
                print(f"[Init] Error: {error_msg}")
                logger.error(error_msg)
                self._initialization_error = error_msg
            except Exception as e:
                error_msg = f"Exception during async initialization: {e}"
                print(f"[Init] Error: {error_msg}")
                logger.error(error_msg, exc_info=True)
                self._initialization_error = str(e)
        else:
            error_msg = "GUI event loop not running or not available. Cannot schedule client initialization."
            print(f"[Init] Critical: {error_msg}")
            logger.critical(error_msg)
            self._initialization_error = error_msg

    def wait_for_initialization(self, timeout_seconds: float = 15.0) -> bool:
        """
        Waits for initialization to complete.

        Args:
            timeout_seconds: Maximum time to wait

        Returns:
            True if initialization completed successfully, False otherwise
        """
        print(f"[Init] Waiting up to {timeout_seconds}s for initialization to complete")

        wait_interval = 0.5
        elapsed = 0.0

        while elapsed < timeout_seconds:
            # Check for successful initialization
            if self._initialization_complete and self.is_ready():
                print(f"[Init] Initialization completed successfully after {elapsed:.1f}s")
                return True

            # Check for initialization error
            if self._initialization_error:
                print(f"[Init] Initialization failed with error: {self._initialization_error}")
                return False

            # Show progress
            print(f"[Init] Waiting for initialization... ({elapsed:.1f}s / {timeout_seconds}s)")
            logger.info(f"Waiting for GUI client and API handlers to initialize... ({elapsed:.1f}s / {timeout_seconds}s)")

            time.sleep(wait_interval)
            elapsed += wait_interval

        # Timeout reached
        print(f"[Init] Initialization timeout after {timeout_seconds}s")
        logger.error(f"GUI initialization timed out after {timeout_seconds}s")
        return False

    def is_ready(self) -> bool:
        """
        Checks if all components are ready.

        Returns:
            True if all components are initialized and ready
        """
        ready = (
            self.api_handlers is not None and
            self.chat_client is not None and
            hasattr(self.chat_client, 'provider') and
            self.chat_client.provider.is_initialized
        )

        if not ready and self.chat_client and hasattr(self.chat_client, 'provider'):
            provider_name = getattr(self.chat_client.provider, 'provider_name', 'Unknown')
            print(f"[Init] Not ready - Provider '{provider_name}' initialized: {self.chat_client.provider.is_initialized}")

        return ready

    def get_status(self) -> dict:
        """
        Gets the initialization status.

        Returns:
            Dictionary with status information
        """
        status = {
            'initialized': self._initialization_complete,
            'ready': self.is_ready(),
            'error': self._initialization_error,
            'event_loop_running': self.event_loop and self.event_loop.is_running(),
            'loop_thread_alive': self.loop_thread and self.loop_thread.is_alive(),
            'chat_client_exists': self.chat_client is not None,
            'api_handlers_exists': self.api_handlers is not None,
            'command_handler_exists': self.command_handler is not None
        }

        if self.chat_client and hasattr(self.chat_client, 'provider'):
            status['provider'] = {
                'name': self.chat_client.provider.provider_name,
                'initialized': self.chat_client.provider.is_initialized,
                'model': self.chat_client.current_model_name
            }

        return status

    def cleanup(self) -> None:
        """Cleanup resources when shutting down."""
        print("[Init] Cleaning up async components")
        logger.info("Cleaning up GUI async components")

        # Stop event loop
        if self.event_loop and self.event_loop.is_running():
            print("[Init] Stopping event loop")
            self.event_loop.call_soon_threadsafe(self.event_loop.stop)

        # Wait for thread to finish
        if self.loop_thread and self.loop_thread.is_alive():
            print("[Init] Waiting for loop thread to finish")
            self.loop_thread.join(timeout=5.0)

        # Close event loop
        if self.event_loop and not self.event_loop.is_closed():
            print("[Init] Closing event loop")
            self.event_loop.close()

        print("[Init] Cleanup complete")


# Global instance for managing async components
_component_manager: Optional[AsyncComponentManager] = None


def get_component_manager() -> AsyncComponentManager:
    """Get or create the global component manager."""
    global _component_manager
    if _component_manager is None:
        _component_manager = AsyncComponentManager()
    return _component_manager
