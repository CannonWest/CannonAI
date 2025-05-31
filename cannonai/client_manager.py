"""
CannonAI - Client Manager Module

This module provides a factory for creating client instances (currently AsyncClient)
and handles the initialization of the AI provider for the client.
"""

from pathlib import Path
from typing import Optional, Union, Dict, Any

from async_client import AsyncClient # The refactored provider-agnostic client
# from sync_client import SyncClient # Sync client would need similar refactoring if used

from providers import get_provider_class, ProviderConfig, BaseAIProvider, ProviderError
from config import Config # For accessing API keys and default models
from base_client import Colors # For printing error messages during client creation


class ClientManager:
    """Factory for creating and managing CannonAI clients."""

    @staticmethod
    def create_client(
        config: Config, # Pass the main Config object
        provider_name_override: Optional[str] = None,
        model_override: Optional[str] = None,
        conversations_dir_override: Optional[Path] = None,
        params_override: Optional[Dict[str, Any]] = None,
        use_streaming_override: Optional[bool] = None,
        # async_mode: bool = True # Currently only refactoring async_client, so it's always async
    ) -> AsyncClient: # Return type is now the refactored AsyncClient
        """
        Creates an AsyncClient instance with the specified or default AI provider.

        Args:
            config: The main application Config object.
            provider_name_override: Explicitly set the provider name, overriding config default.
            model_override: Explicitly set the model name, overriding config default for provider.
            conversations_dir_override: Override default conversation directory.
            params_override: Override default generation parameters.
            use_streaming_override: Override default streaming preference.

        Returns:
            An initialized AsyncClient instance.

        Raises:
            ValueError: If API key or model for the selected provider is not found.
            ProviderError: If the provider class cannot be found or instantiated.
        """
        # 1. Determine Provider Name
        provider_name = provider_name_override or config.get("default_provider", "gemini")
        print(f"[ClientManager] Selected provider: {provider_name}")

        # 2. Get API Key for the Provider
        api_key = config.get_api_key(provider_name)
        if not api_key:
            raise ValueError(f"API key for provider '{provider_name}' not found. "
                             f"Please set it in config, environment variable ({provider_name.upper()}_API_KEY), "
                             f"or via --api-key if using CLI.")

        # 3. Determine Model for the Provider
        model_name = model_override or config.get_default_model_for_provider(provider_name)
        if not model_name:
            # Fallback strategy if provider_models doesn't have an entry.
            # This could be more sophisticated, e.g., trying to list models from provider.
            # For now, if it's Gemini, use its known fallback. Otherwise, error.
            if provider_name == "gemini" and hasattr(config, 'DEFAULT_GEMINI_MODEL'):
                 model_name = config.DEFAULT_GEMINI_MODEL
                 print(f"[ClientManager] Warning: No default model for '{provider_name}' in config. "
                       f"Falling back to Gemini default: {model_name}")
            else:
                 raise ValueError(f"Default model for provider '{provider_name}' not found in configuration. "
                                  "Please set 'provider_models' in your config file.")
        print(f"[ClientManager] Selected model for {provider_name}: {model_name}")

        # 4. Determine Conversations Directory
        conversations_dir_str = config.get("conversations_dir") # Should be a string from config
        conversations_dir = conversations_dir_override or (Path(conversations_dir_str) if conversations_dir_str else Path.home() / "cannonai_conversations")


        # 5. Initialize Provider Instance
        try:
            provider_class = get_provider_class(provider_name) # from providers/__init__.py
            # ProviderConfig holds API key and model, potentially other provider-specific settings later
            provider_config_obj = ProviderConfig(api_key=api_key, model=model_name)
            provider_instance: BaseAIProvider = provider_class(provider_config_obj)
            print(f"[ClientManager] Instantiated provider: {provider_instance.__class__.__name__}")
        except ValueError as ve: # Unknown provider from get_provider_class
            print(f"{Colors.FAIL}[ClientManager] Error: {ve}{Colors.ENDC}")
            raise ProviderError(f"Unknown provider specified: {provider_name}") from ve
        except Exception as e:
            print(f"{Colors.FAIL}[ClientManager] Failed to instantiate provider '{provider_name}': {e}{Colors.ENDC}")
            import traceback
            traceback.print_exc()
            raise ProviderError(f"Could not create provider instance for {provider_name}") from e


        # 6. Create the AsyncClient instance with the initialized provider
        client = AsyncClient(
            provider=provider_instance,
            conversations_dir=conversations_dir
        )
        print(f"[ClientManager] AsyncClient created with provider '{provider_name}'.")

        # 7. Apply Client-Level Settings (Generation Params, Streaming Preference)
        # Start with provider's defaults, then layer global config, then specific overrides.

        # Generation Parameters:
        # These are general params; the provider might only use a subset or map them.
        effective_params = provider_instance.get_default_params().copy() # Start with provider's own defaults

        global_gen_params_from_config = config.get("generation_params", {}).copy()
        effective_params.update(global_gen_params_from_config) # Global config overrides provider defaults

        if params_override: # Specific call-time overrides take highest precedence
            effective_params.update(params_override)
        client.params = effective_params # Set on the client instance
        print(f"[ClientManager] Client generation parameters set to: {client.params}")

        # Streaming Preference:
        client.use_streaming = use_streaming_override if use_streaming_override is not None \
                               else config.get("use_streaming", False)
        print(f"[ClientManager] Client streaming preference set to: {client.use_streaming}")

        return client

# Note: The actual client.initialize_client() call (which initializes the provider's connection)
# should be done *after* ClientManager.create_client() returns the client instance.
# Example in main application logic:
#
#   config_obj = Config()
#   try:
#       ai_client = ClientManager.create_client(config_obj)
#       if not asyncio.run(ai_client.initialize_client()): # This now calls provider.initialize()
#           print(f"{Colors.FAIL}Failed to initialize the AI client and its provider. Exiting.{Colors.ENDC}")
#           sys.exit(1)
#       # ... proceed with using ai_client ...
#   except (ValueError, ProviderError) as e:
#       print(f"{Colors.FAIL}Error during client creation: {e}{Colors.ENDC}")
#       sys.exit(1)
