#!/usr/bin/env python3
"""
Gemini Chat CLI Configuration - Unified configuration management.

This module provides a centralized configuration system for the Gemini Chat CLI application,
handling API keys, model selection, and other application settings.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Union

try:
    from colorama import Fore, Style
    colorama_available = True
except ImportError:
    colorama_available = False


class Config:
    """Configuration manager for Gemini Chat CLI."""
    
    # Default settings
    DEFAULT_MODEL = "gemini-2.0-flash"
    DEFAULT_CONFIG_FILE = "gemini_chat_config.json"
    
    def __init__(self, config_file: Optional[Union[str, Path]] = None):
        """Initialize the configuration manager.
        
        Args:
            config_file: Path to the configuration file. If None, uses default.
        """
        # Set up config file path
        self.config_file = Path(config_file) if config_file else self._get_default_config_path()
        
        # Default configuration
        self.config = {
            "api_key": "",
            "default_model": self.DEFAULT_MODEL,
            "conversations_dir": str(Path(__file__).resolve().parent.parent / "gemini_chat_conversations"),
            "generation_params": {
                "temperature": 0.7,
                "max_output_tokens": 800,
                "top_p": 0.95,
                "top_k": 40
            },
            "use_streaming": False
        }
        
        # Load configuration if it exists
        self.load_config()
    
    def _get_default_config_path(self) -> Path:
        """Get the default configuration file path.
        
        Returns:
            Path to the default configuration file
        """
        # Determine appropriate config location based on OS
        if sys.platform == 'win32':
            config_dir = Path(os.environ.get('APPDATA', Path.home()))
        else:
            config_dir = Path.home() / '.config'
        
        # Ensure the config directory exists
        config_dir.mkdir(parents=True, exist_ok=True)
        
        return config_dir / self.DEFAULT_CONFIG_FILE
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file.
        
        Returns:
            The loaded configuration dictionary
        """
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    
                # Update current config with loaded values
                self.config.update(loaded_config)
                
                # Print success message with colorama if available
                if colorama_available:
                    print(f"{Fore.GREEN}Configuration loaded from {self.config_file}{Style.RESET_ALL}")
                else:
                    print(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                if colorama_available:
                    print(f"{Fore.RED}Error loading configuration: {e}{Style.RESET_ALL}")
                else:
                    print(f"Error loading configuration: {e}")
        
        return self.config
    
    def save_config(self) -> bool:
        """Save configuration to file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            # Print success message with colorama if available
            if colorama_available:
                print(f"{Fore.GREEN}Configuration saved to {self.config_file}{Style.RESET_ALL}")
            else:
                print(f"Configuration saved to {self.config_file}")
            
            return True
        except Exception as e:
            if colorama_available:
                print(f"{Fore.RED}Error saving configuration: {e}{Style.RESET_ALL}")
            else:
                print(f"Error saving configuration: {e}")
            return False
    
    def get(self, key: str, default=None) -> Any:
        """Get a configuration value.
        
        Args:
            key: The configuration key
            default: Default value if key is not found
            
        Returns:
            The configuration value or default
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set a configuration value.
        
        Args:
            key: The configuration key
            value: The value to set
        """
        self.config[key] = value
    
    def get_api_key(self) -> Optional[str]:
        """Get the API key from config or environment variable.
        
        Returns:
            The API key or None if not found
        """
        # First check environment variable
        api_key = os.environ.get("GEMINI_API_KEY")
        
        # If not in environment, check config
        if not api_key:
            api_key = self.get("api_key")
        
        return api_key if api_key else None
    
    def set_api_key(self, api_key: str) -> None:
        """Set the API key and save the configuration.
        
        Args:
            api_key: The API key to set
        """
        self.set("api_key", api_key)
        self.save_config()
    
    def setup_wizard(self) -> bool:
        """Run the configuration setup wizard.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            print("\n=== Gemini Chat CLI Configuration Wizard ===\n")
            
            # API Key
            current_api_key = self.get_api_key() or ""
            api_key_display = current_api_key[:4] + "..." + current_api_key[-4:] if current_api_key else "Not set"
            print(f"API Key [{api_key_display}]: ", end="")
            api_key_input = input()
            if api_key_input:
                self.set("api_key", api_key_input)
            
            # Default model
            current_model = self.get("default_model", self.DEFAULT_MODEL)
            print(f"Default Model [{current_model}]: ", end="")
            model_input = input()
            if model_input:
                self.set("default_model", model_input)

            # Conversations directory
            current_dir = self.get("conversations_dir", str(Path(__file__).resolve().parent.parent / "gemini_chat_conversations"))
            print(f"Conversations Directory [{current_dir}]: ", end="")
            dir_input = input()
            if dir_input:
                self.set("conversations_dir", dir_input)
            
            # Generation parameters
            print("\nGeneration Parameters:")
            current_params = self.get("generation_params", {})
            
            print(f"  Temperature [{current_params.get('temperature', 0.7)}]: ", end="")
            temp_input = input()
            if temp_input:
                current_params["temperature"] = float(temp_input)
            
            print(f"  Max Output Tokens [{current_params.get('max_output_tokens', 800)}]: ", end="")
            tokens_input = input()
            if tokens_input:
                current_params["max_output_tokens"] = int(tokens_input)
            
            print(f"  Top-p [{current_params.get('top_p', 0.95)}]: ", end="")
            top_p_input = input()
            if top_p_input:
                current_params["top_p"] = float(top_p_input)
            
            print(f"  Top-k [{current_params.get('top_k', 40)}]: ", end="")
            top_k_input = input()
            if top_k_input:
                current_params["top_k"] = int(top_k_input)
            
            self.set("generation_params", current_params)
            
            # Default streaming mode
            current_streaming = self.get("use_streaming", False)
            print(f"Enable Streaming by Default [{'yes' if current_streaming else 'no'}]: ", end="")
            streaming_input = input().lower()
            if streaming_input in ("y", "yes", "true", "1"):
                self.set("use_streaming", True)
            elif streaming_input in ("n", "no", "false", "0"):
                self.set("use_streaming", False)
            
            # Save configuration
            if self.save_config():
                print("\nConfiguration saved successfully!\n")
                return True
            else:
                print("\nFailed to save configuration.\n")
                return False
        
        except Exception as e:
            if colorama_available:
                print(f"{Fore.RED}Error in setup wizard: {e}{Style.RESET_ALL}")
            else:
                print(f"Error in setup wizard: {e}")
            return False


# Create a default configuration instance
default_config = Config()


if __name__ == "__main__":
    # If run directly, run the setup wizard
    config = Config()
    config.setup_wizard()
