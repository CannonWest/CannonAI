#!/usr/bin/env python3
"""
CannonAI CLI Configuration - Unified configuration management.

This module provides a centralized configuration system for the CannonAI CLI application,
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
    """Configuration manager for CannonAI CLI."""
    
    # Default settings
    DEFAULT_MODEL = "gemini-2.0-flash"
    DEFAULT_CONFIG_FILE = "cannonai_config.json"
    
    def __init__(self, config_file: Optional[Union[str, Path]] = None, override_api_key: Optional[str] = None, quiet: bool = False):
        """Initialize the configuration manager.
        
        Args:
            config_file: Path to the configuration file. If None, uses default.
        """
        # Set up config file path
        self.config_file = Path(config_file) if config_file else self._get_default_config_path()
        
        # Determine project root directory
        project_root = Path(__file__).resolve().parent.parent
        
        # Default configuration
        self.config = {
            "api_key": "",
            "default_model": self.DEFAULT_MODEL,
            "conversations_dir": str(project_root / "cannonai_conversations"),
            "generation_params": {
                "temperature": 0.7,
                "max_output_tokens": 800,
                "top_p": 0.95,
                "top_k": 40
            },
            "use_streaming": False
        }
        
        # Store quiet flag for suppressing messages
        self.quiet = quiet
        
        # Store any API key override
        self.override_api_key = override_api_key
        
        # Load configuration if it exists
        self.load_config()
    
    def _get_default_config_path(self) -> Path:
        """Get the default configuration file path.
        
        Returns:
            Path to the default configuration file
        """
        # Always use the cannonai_config directory relative to the project
        try:
            # Get the current file path and determine the project structure
            current_file = Path(__file__).resolve()
            current_dir = current_file.parent
            
            # The parent should be the repository root
            parent_dir = current_dir.parent
            
            # Set config directory adjacent to cannonai
            config_dir = parent_dir / "cannonai_config"
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir / self.DEFAULT_CONFIG_FILE
        except Exception as e:
            # If we can't determine the project structure, use the current directory
            print(f"Error finding project structure: {e}. Using current directory.")
            config_dir = Path.cwd() / "cannonai_config"
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
                if not self.quiet:
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
        """Get the API key from override, environment variable, or config.
        
        Returns:
            The API key or None if not found
        """
        # First check override (from command line)
        if hasattr(self, 'override_api_key') and self.override_api_key:
            return self.override_api_key
            
        # Then check environment variable
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
            print("\n=== CannonAI CLI Configuration Wizard ===\n")
            
            # Show available configuration options
            self._display_available_configs()
            
            # Let the user select which configurations to modify
            return self._interactive_config_edit()
            
        except Exception as e:
            if colorama_available:
                print(f"{Fore.RED}Error in setup wizard: {e}{Style.RESET_ALL}")
            else:
                print(f"Error in setup wizard: {e}")
            return False
            
    def _display_available_configs(self) -> None:
        """Display all available configuration options with their current values."""
        # Use colorama if available
        header_color = Fore.CYAN if colorama_available else ""
        value_color = Fore.GREEN if colorama_available else ""
        reset = Style.RESET_ALL if colorama_available else ""
        
        print(f"{header_color}=== Current Configuration ==={reset}\n")
        
        # API Key (masked for security)
        current_api_key = self.get_api_key() or ""
        api_key_display = current_api_key[:4] + "..." + current_api_key[-4:] if current_api_key else "Not set"
        print(f"{header_color}1. API Key:{reset} {value_color}{api_key_display}{reset}")
        
        # Default model
        current_model = self.get("default_model", self.DEFAULT_MODEL)
        print(f"{header_color}2. Default Model:{reset} {value_color}{current_model}{reset}")
        
        # Conversations directory
        current_dir = self.get("conversations_dir", str(Path.home() / "cannonai_conversations"))
        print(f"{header_color}3. Conversations Directory:{reset} {value_color}{current_dir}{reset}")
        
        # Generation parameters
        current_params = self.get("generation_params", {})
        print(f"\n{header_color}Generation Parameters:{reset}")
        print(f"{header_color}4. Temperature:{reset} {value_color}{current_params.get('temperature', 0.7)}{reset}")
        print(f"{header_color}5. Max Output Tokens:{reset} {value_color}{current_params.get('max_output_tokens', 800)}{reset}")
        print(f"{header_color}6. Top-p:{reset} {value_color}{current_params.get('top_p', 0.95)}{reset}")
        print(f"{header_color}7. Top-k:{reset} {value_color}{current_params.get('top_k', 40)}{reset}")
        
        # Streaming mode
        current_streaming = self.get("use_streaming", False)
        print(f"\n{header_color}8. Streaming Mode:{reset} {value_color}{'Enabled' if current_streaming else 'Disabled'}{reset}")
        
        # Configuration file location
        print(f"\n{header_color}Configuration File Location:{reset} {value_color}{self.config_file}{reset}")
    
    def _interactive_config_edit(self) -> bool:
        """Interactive configuration editor allowing users to select which settings to modify.
        
        Returns:
            True if configuration was saved successfully, False otherwise
        """
        while True:
            print("\nEnter the number of the setting to modify (1-8), 'a' for all settings,")
            print("'s' to save current changes, or 'q' to quit without saving: ", end="")
            choice = input().lower()
            
            if choice == 'q':
                print("Exiting without saving changes.")
                return False
            
            elif choice == 's':
                if self.save_config():
                    print("\nConfiguration saved successfully!\n")
                    return True
                else:
                    print("\nFailed to save configuration.\n")
                    return False
            
            elif choice == 'a':
                self._edit_all_settings()
            
            elif choice.isdigit() and 1 <= int(choice) <= 8:
                self._edit_specific_setting(int(choice))
            
            else:
                if colorama_available:
                    print(f"{Fore.RED}Invalid choice. Please try again.{Style.RESET_ALL}")
                else:
                    print("Invalid choice. Please try again.")
                
            # Redisplay configuration after changes
            self._display_available_configs()
    
    def _edit_all_settings(self) -> None:
        """Edit all configuration settings in sequence."""
        # Edit all settings one by one
        for setting_num in range(1, 9):
            self._edit_specific_setting(setting_num)
    
    def _edit_specific_setting(self, setting_num: int) -> None:
        """Edit a specific configuration setting by its number.
        
        Args:
            setting_num: The number of the setting to edit (1-8)
        """
        try:
            # API Key
            if setting_num == 1:
                current_api_key = self.get_api_key() or ""
                api_key_display = current_api_key[:4] + "..." + current_api_key[-4:] if current_api_key else "Not set"
                print(f"\nAPI Key [{api_key_display}]: ", end="")
                api_key_input = input()
                if api_key_input:
                    self.set("api_key", api_key_input)
            
            # Default model
            elif setting_num == 2:
                current_model = self.get("default_model", self.DEFAULT_MODEL)
                print(f"\nDefault Model [{current_model}]: ", end="")
                model_input = input()
                if model_input:
                    self.set("default_model", model_input)
            
            # Conversations directory
            elif setting_num == 3:
                current_dir = self.get("conversations_dir", str(Path.home() / "cannonai_conversations"))
                print(f"\nConversations Directory [{current_dir}]: ", end="")
                dir_input = input()
                if dir_input:
                    self.set("conversations_dir", dir_input)
            
            # Temperature
            elif setting_num == 4:
                current_params = self.get("generation_params", {})
                print(f"\nTemperature [{current_params.get('temperature', 0.7)}]: ", end="")
                temp_input = input()
                if temp_input:
                    current_params["temperature"] = float(temp_input)
                    self.set("generation_params", current_params)
            
            # Max Output Tokens
            elif setting_num == 5:
                current_params = self.get("generation_params", {})
                print(f"\nMax Output Tokens [{current_params.get('max_output_tokens', 800)}]: ", end="")
                tokens_input = input()
                if tokens_input:
                    current_params["max_output_tokens"] = int(tokens_input)
                    self.set("generation_params", current_params)
            
            # Top-p
            elif setting_num == 6:
                current_params = self.get("generation_params", {})
                print(f"\nTop-p [{current_params.get('top_p', 0.95)}]: ", end="")
                top_p_input = input()
                if top_p_input:
                    current_params["top_p"] = float(top_p_input)
                    self.set("generation_params", current_params)
            
            # Top-k
            elif setting_num == 7:
                current_params = self.get("generation_params", {})
                print(f"\nTop-k [{current_params.get('top_k', 40)}]: ", end="")
                top_k_input = input()
                if top_k_input:
                    current_params["top_k"] = int(top_k_input)
                    self.set("generation_params", current_params)
            
            # Streaming mode
            elif setting_num == 8:
                current_streaming = self.get("use_streaming", False)
                print(f"\nEnable Streaming by Default [{'yes' if current_streaming else 'no'}]: ", end="")
                streaming_input = input().lower()
                if streaming_input in ("y", "yes", "true", "1"):
                    self.set("use_streaming", True)
                elif streaming_input in ("n", "no", "false", "0"):
                    self.set("use_streaming", False)
        
        except ValueError as ve:
            if colorama_available:
                print(f"{Fore.RED}Invalid input: {ve}{Style.RESET_ALL}")
            else:
                print(f"Invalid input: {ve}")
            return False
        
        except Exception as e:
            if colorama_available:
                print(f"{Fore.RED}Error in setup wizard: {e}{Style.RESET_ALL}")
            else:
                print(f"Error in setup wizard: {e}")
            return False
        
        # Return True for successful completion
        return True


# Create a default configuration instance
default_config = Config()


if __name__ == "__main__":
    # If run directly, run the setup wizard
    config = Config()
    config.setup_wizard()
