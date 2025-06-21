#!/usr/bin/env python3
"""
CannonAI Provider Manager - Dynamic provider instance management for seamless switching.

This module provides a manager for creating, caching, and switching between AI provider
instances without requiring application restart.
"""

import asyncio
from typing import Dict, Optional, Type
from pathlib import Path

from providers import get_provider_class, ProviderConfig, BaseAIProvider, ProviderError
from config import Config
from base_client import Colors


class ProviderManager:
    """Manages dynamic creation and caching of AI provider instances."""
    
    def __init__(self, main_config: Config):
        """
        Initialize the provider manager.
        
        Args:
            main_config: The main application configuration object.
        """
        print(f"[ProviderManager] Initializing provider manager")
        self.main_config = main_config
        self._provider_cache: Dict[str, BaseAIProvider] = {}
        self._current_provider_name: Optional[str] = None
        self._current_provider: Optional[BaseAIProvider] = None
        
    def get_current_provider(self) -> Optional[BaseAIProvider]:
        """Get the currently active provider instance."""
        return self._current_provider
    
    def get_current_provider_name(self) -> Optional[str]:
        """Get the name of the currently active provider."""
        return self._current_provider_name
    
    async def get_or_create_provider(self, provider_name: str, model: Optional[str] = None) -> BaseAIProvider:
        """
        Get an existing provider instance or create a new one.
        
        Args:
            provider_name: Name of the provider (e.g., 'gemini', 'openai', 'deepseek')
            model: Optional model name. If not specified, uses config default.
            
        Returns:
            An initialized provider instance.
            
        Raises:
            ValueError: If API key is not found.
            ProviderError: If provider cannot be created or initialized.
        """
        print(f"[ProviderManager] Getting or creating provider: {provider_name}")
        
        # Check if we have a cached instance
        if provider_name in self._provider_cache:
            provider = self._provider_cache[provider_name]
            print(f"[ProviderManager] Using cached provider instance for {provider_name}")
            
            # Update model if specified and different
            if model and model != provider.config.model:
                if provider.validate_model(model):
                    print(f"[ProviderManager] Updating model for {provider_name} from {provider.config.model} to {model}")
                    provider.config.model = model
                else:
                    print(f"{Colors.WARNING}[ProviderManager] Model '{model}' not valid for {provider_name}. Keeping {provider.config.model}{Colors.ENDC}")
            
            # Ensure provider is initialized
            if not provider.is_initialized:
                print(f"[ProviderManager] Cached provider {provider_name} not initialized. Initializing...")
                success = await provider.initialize()
                if not success:
                    raise ProviderError(f"Failed to initialize cached provider {provider_name}")
                    
            return provider
        
        # Create new provider instance
        print(f"[ProviderManager] Creating new provider instance for {provider_name}")
        
        # Get API key
        api_key = self.main_config.get_api_key(provider_name)
        if not api_key:
            raise ValueError(f"API key for provider '{provider_name}' not found. "
                           f"Please set it in config or environment variable ({provider_name.upper()}_API_KEY)")
        
        # Determine model
        if not model:
            model = self.main_config.get_default_model_for_provider(provider_name)
            if not model:
                # Fallback for known providers
                if provider_name == "gemini":
                    model = Config.DEFAULT_GEMINI_MODEL
                else:
                    raise ValueError(f"No default model found for provider '{provider_name}'")
        
        print(f"[ProviderManager] Creating {provider_name} provider with model {model}")
        
        # Create provider instance
        try:
            provider_class = get_provider_class(provider_name)
            provider_config = ProviderConfig(api_key=api_key, model=model)
            provider = provider_class(provider_config)
            
            # Initialize the provider
            print(f"[ProviderManager] Initializing new {provider_name} provider...")
            success = await provider.initialize()
            if not success:
                raise ProviderError(f"Failed to initialize provider {provider_name}")
            
            # Cache the provider
            self._provider_cache[provider_name] = provider
            print(f"[ProviderManager] Successfully created and cached {provider_name} provider")
            
            return provider
            
        except Exception as e:
            print(f"{Colors.FAIL}[ProviderManager] Error creating provider {provider_name}: {e}{Colors.ENDC}")
            raise ProviderError(f"Failed to create provider {provider_name}: {str(e)}") from e
    
    async def switch_provider(self, provider_name: str, model: Optional[str] = None) -> BaseAIProvider:
        """
        Switch to a different provider.
        
        Args:
            provider_name: Name of the provider to switch to.
            model: Optional model name.
            
        Returns:
            The new active provider instance.
        """
        print(f"[ProviderManager] Switching from {self._current_provider_name} to {provider_name}")
        
        # Get or create the provider
        provider = await self.get_or_create_provider(provider_name, model)
        
        # Update current provider
        self._current_provider_name = provider_name
        self._current_provider = provider
        
        print(f"{Colors.GREEN}[ProviderManager] Successfully switched to {provider_name} provider{Colors.ENDC}")
        return provider
    
    def cleanup(self):
        """Clean up all cached provider instances."""
        print("[ProviderManager] Cleaning up provider instances")
        for provider_name, provider in self._provider_cache.items():
            try:
                if hasattr(provider, 'cleanup'):
                    provider.cleanup()
                print(f"[ProviderManager] Cleaned up {provider_name} provider")
            except Exception as e:
                print(f"{Colors.WARNING}[ProviderManager] Error cleaning up {provider_name}: {e}{Colors.ENDC}")
        
        self._provider_cache.clear()
        self._current_provider = None
        self._current_provider_name = None
        print("[ProviderManager] Provider cleanup complete")
    
    def get_all_cached_providers(self) -> Dict[str, BaseAIProvider]:
        """Get all cached provider instances."""
        return self._provider_cache.copy()
