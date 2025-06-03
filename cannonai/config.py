# !/usr/bin/env python3
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

    DEFAULT_CONFIG_FILE = "cannonai_config.json"
    DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
    SUPPORTED_PROVIDERS = ["gemini", "claude", "openai"]  # Define supported providers
    DEFAULT_SYSTEM_INSTRUCTION = "You are a helpful assistant."  # This remains the global default

    def __init__(self, config_file: Optional[Union[str, Path]] = None, override_api_key_dict: Optional[Dict[str, str]] = None, quiet: bool = False):
        """Initialize the configuration manager.

        Args:
            config_file: Path to the configuration file. If None, uses default.
            override_api_key_dict: Dictionary of provider_name: api_key to override config/env, primarily for CLI.
            quiet: Suppress informational messages during load/save.
        """
        self.config_file = Path(config_file) if config_file else self._get_default_config_path()
        project_root = Path(__file__).resolve().parent.parent

        # Initialize default structure for api_keys if not present in loaded config
        default_api_keys = {provider: "" for provider in self.SUPPORTED_PROVIDERS}

        self.config = {
            "api_keys": default_api_keys,
            "default_provider": "gemini",
            "provider_models": {
                "gemini": self.DEFAULT_GEMINI_MODEL,
                "claude": "claude-3-haiku-20240307",
                "openai": "gpt-3.5-turbo"
            },
            "conversations_dir": str(project_root / "cannonai_conversations"),
            "generation_params": {
                "temperature": 0.7,
                "max_output_tokens": 800,
                "top_p": 0.95,
                "top_k": 40
            },
            "use_streaming": False,
            "default_system_instruction": self.DEFAULT_SYSTEM_INSTRUCTION,  # This is the global default
        }
        self.quiet = quiet
        self.override_api_key_dict = override_api_key_dict or {}
        self.load_config()

    def _get_default_config_path(self) -> Path:
        """Gets the default path for the configuration file."""
        current_file = Path(__file__).resolve()
        current_dir = current_file.parent
        parent_dir = current_dir.parent
        config_dir = parent_dir / "cannonai_config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / self.DEFAULT_CONFIG_FILE

    def load_config(self) -> Dict[str, Any]:
        """Loads the configuration from the JSON file.

        Returns:
            The loaded configuration dictionary.
        """
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)

                # Deep merge for nested dicts like api_keys, provider_models, generation_params
                for key, value in loaded_config.items():
                    if key == "api_keys" and isinstance(value, dict):
                        current_api_keys = self.config["api_keys"].copy()
                        current_api_keys.update(value)
                        self.config["api_keys"] = current_api_keys
                    elif isinstance(value, dict) and isinstance(self.config.get(key), dict):
                        self.config[key].update(value)
                    else:
                        self.config[key] = value

                # Ensure default_system_instruction is present, if not, add it
                if "default_system_instruction" not in self.config:
                    self.config["default_system_instruction"] = self.DEFAULT_SYSTEM_INSTRUCTION

                # Ensure api_keys in self.config has all supported providers after loading
                for provider in self.SUPPORTED_PROVIDERS:
                    if provider not in self.config["api_keys"]:
                        self.config["api_keys"][provider] = ""

                if not self.quiet:
                    msg = f"Configuration loaded from {self.config_file}"
                    print(f"{Fore.GREEN}{msg}{Style.RESET_ALL}" if colorama_available else msg)
            except Exception as e:
                msg = f"Error loading configuration from {self.config_file}: {e}. Using defaults."
                print(f"{Fore.RED}{msg}{Style.RESET_ALL}" if colorama_available else msg)
                # Re-initialize with defaults if loading fails critically, but preserve file path
                default_path = self.config_file
                self.__init__(config_file=default_path, override_api_key_dict=self.override_api_key_dict, quiet=self.quiet)  # Re-init
        else:
            if not self.quiet:
                msg = f"Configuration file not found at {self.config_file}. Using default settings. It will be created on save."
                print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}" if colorama_available else msg)
            # Ensure default api_keys structure and default_system_instruction are set if file doesn't exist
            self.config["api_keys"] = {provider: "" for provider in self.SUPPORTED_PROVIDERS}
            self.config["default_system_instruction"] = self.DEFAULT_SYSTEM_INSTRUCTION
        return self.config

    def save_config(self) -> bool:
        """Saves the current configuration to the JSON file.

        Returns:
            True if saving was successful, False otherwise.
        """
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            if not self.quiet:
                msg = f"Configuration saved to {self.config_file}"
                print(f"{Fore.GREEN}{msg}{Style.RESET_ALL}" if colorama_available else msg)
            return True
        except Exception as e:
            msg = f"Error saving configuration to {self.config_file}: {e}"
            print(f"{Fore.RED}{msg}{Style.RESET_ALL}" if colorama_available else msg)
            return False

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Gets a configuration value.

        Args:
            key: The configuration key.
            default: The default value if the key is not found.

        Returns:
            The configuration value or the default.
        """
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Sets a configuration value. Does not automatically save.

        Args:
            key: The configuration key.
            value: The value to set.
        """
        self.config[key] = value

    def get_api_key(self, provider_name: str) -> Optional[str]:
        """Gets the API key for a specific provider, checking overrides, environment, then config.

        Args:
            provider_name: The name of the provider (e.g., "gemini").

        Returns:
            The API key string if found, otherwise None.
        """
        provider_name_lower = provider_name.lower()
        if provider_name_lower in self.override_api_key_dict:
            key = self.override_api_key_dict[provider_name_lower]
            if key: return key

        env_var_name = f"{provider_name_lower.upper()}_API_KEY"
        api_key_env = os.environ.get(env_var_name)
        if api_key_env:
            return api_key_env

        return self.config.get("api_keys", {}).get(provider_name_lower)

    def set_api_key(self, provider_name: str, api_key: str) -> None:
        """Sets the API key for a specific provider in the internal config dictionary. Does not automatically save.

        Args:
            provider_name: The name of the provider.
            api_key: The API key string.
        """
        provider_name_lower = provider_name.lower()
        if "api_keys" not in self.config:
            self.config["api_keys"] = {provider: "" for provider in self.SUPPORTED_PROVIDERS}

        if provider_name_lower in self.SUPPORTED_PROVIDERS:
            self.config["api_keys"][provider_name_lower] = api_key
        else:
            msg = f"Warning: Attempted to set API key for unsupported provider: {provider_name}"
            print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}" if colorama_available else msg)

    def get_all_api_keys_status(self) -> Dict[str, bool]:
        """Checks if API keys are set for all supported providers.

        Returns:
            A dictionary with provider names as keys and boolean status.
        """
        status = {}
        for provider in self.SUPPORTED_PROVIDERS:
            status[f"{provider}_set"] = bool(self.get_api_key(provider))
        return status

    def get_default_model_for_provider(self, provider_name: str) -> Optional[str]:
        """Gets the default model for a specific provider from the config.

        Args:
            provider_name: The name of the provider.

        Returns:
            The model name string if found, otherwise None.
        """
        return self.config.get("provider_models", {}).get(provider_name.lower())

    def setup_wizard(self) -> bool:
        """Runs an interactive setup wizard to configure the application.

        Returns:
            True if configuration was saved, False otherwise.
        """
        try:
            print(f"\n{Fore.CYAN}=== CannonAI CLI Configuration Wizard ==={Style.RESET_ALL}\n")
            self._display_available_configs_for_wizard()
            return self._interactive_config_edit()
        except Exception as e:
            msg = f"Error in setup wizard: {e}"
            print(f"{Fore.RED}{msg}{Style.RESET_ALL}" if colorama_available else msg)
            return False

    def _display_available_configs_for_wizard(self) -> None:
        """Displays current configuration values for the interactive wizard."""
        header_color = Fore.CYAN if colorama_available else ""
        value_color = Fore.GREEN if colorama_available else ""
        reset = Style.RESET_ALL if colorama_available else ""
        idx = 1
        self._wizard_indices: Dict[str, Any] = {}  # Store indices for editing

        print(f"{header_color}--- API Keys ---{reset}")
        self._wizard_indices["api_keys_start"] = idx
        for provider_name in self.SUPPORTED_PROVIDERS:
            current_api_key = self.config.get("api_keys", {}).get(provider_name, "")
            api_key_display = f"{current_api_key[:4]}...{current_api_key[-4:]}" if len(current_api_key) > 7 else "Not set"
            print(f"{header_color}{idx}. {provider_name.capitalize()} API Key:{reset} {value_color}{api_key_display}{reset}")
            idx += 1
        self._wizard_indices["api_keys_end"] = idx - 1

        print(f"\n{header_color}--- Default Provider & Models ---{reset}")
        default_provider = self.get("default_provider", "gemini")
        print(f"{header_color}{idx}. Default Provider:{reset} {value_color}{default_provider}{reset}")
        self._wizard_indices["default_provider"] = idx
        idx += 1

        self._wizard_indices["provider_models_start"] = idx
        for provider_name_model in self.config.get("provider_models", {}):
            if provider_name_model in self.SUPPORTED_PROVIDERS:
                current_model = self.get_default_model_for_provider(provider_name_model)
                print(f"{header_color}{idx}. Default Model for {provider_name_model.capitalize()}:{reset} {value_color}{current_model}{reset}")
                idx += 1
        self._wizard_indices["provider_models_end"] = idx - 1

        print(f"\n{header_color}--- Default System Instruction (for new conversations) ---{reset}")
        current_system_instruction = self.get("default_system_instruction", self.DEFAULT_SYSTEM_INSTRUCTION)
        instruction_preview = current_system_instruction[:60] + ('...' if len(current_system_instruction) > 60 else '')
        print(f"{header_color}{idx}. Global Default System Instruction:{reset} {value_color}{instruction_preview}{reset}")
        self._wizard_indices["default_system_instruction"] = idx
        idx += 1

        print(f"\n{header_color}--- General Settings ---{reset}")
        current_dir = self.get("conversations_dir", str(Path.home() / "cannonai_conversations"))
        print(f"{header_color}{idx}. Conversations Directory:{reset} {value_color}{current_dir}{reset}")
        self._wizard_indices["conversations_dir"] = idx
        idx += 1

        print(f"\n{header_color}Global Generation Parameters (can be overridden per conversation):{reset}")
        current_params = self.get("generation_params", {})
        param_map = {
            "temperature": "Temperature", "max_output_tokens": "Max Output Tokens",
            "top_p": "Top-p", "top_k": "Top-k"
        }
        self._wizard_indices["generation_params_start"] = idx
        for param_key, param_desc in param_map.items():
            print(f"{header_color}{idx}. {param_desc}:{reset} {value_color}{current_params.get(param_key)}{reset}")
            self._wizard_indices[param_key] = idx  # Store specific index for each param
            idx += 1
        self._wizard_indices["generation_params_end"] = idx - 1

        current_streaming = self.get("use_streaming", False)
        print(f"\n{header_color}{idx}. Streaming Mode by Default:{reset} {value_color}{'Enabled' if current_streaming else 'Disabled'}{reset}")
        self._wizard_indices["streaming"] = idx
        idx += 1

        print(f"\n{header_color}Config File Path:{reset} {value_color}{self.config_file}{reset}")
        self._wizard_indices["_max_option"] = idx - 1

    def _interactive_config_edit(self) -> bool:
        """Handles the interactive editing loop for the setup wizard."""
        while True:
            print(f"\nEnter the number of the setting to modify (1-{self._wizard_indices['_max_option']}), 's' to save and exit, or 'q' to quit: ", end="")
            choice = input().lower().strip()

            if choice == 'q':
                print("Exiting wizard without saving changes made in this session.")
                return False
            elif choice == 's':
                self.save_config()
                print("\nConfiguration saved.\n")
                return True

            try:
                choice_num = int(choice)
                updated = False  # Flag to re-display config only if something changed

                # API Keys
                if self._wizard_indices['api_keys_start'] <= choice_num <= self._wizard_indices['api_keys_end']:
                    provider_index = choice_num - self._wizard_indices['api_keys_start']
                    provider_name = self.SUPPORTED_PROVIDERS[provider_index]
                    current_val_display = f"{self.config['api_keys'].get(provider_name, '')[:4]}..." if self.config['api_keys'].get(provider_name) else "Not set"
                    new_val = input(f"Enter new {provider_name.capitalize()} API Key [{current_val_display}]: ").strip()
                    if new_val:
                        self.config["api_keys"][provider_name] = new_val
                        updated = True

                # Default Provider
                elif choice_num == self._wizard_indices['default_provider']:
                    current_val = self.get("default_provider")
                    new_val = input(f"Default Provider ({', '.join(self.SUPPORTED_PROVIDERS)}) [{current_val}]: ").strip().lower()
                    if new_val and new_val in self.SUPPORTED_PROVIDERS:
                        self.config["default_provider"] = new_val
                        updated = True
                    elif new_val:
                        print(f"Invalid provider. Please choose from {', '.join(self.SUPPORTED_PROVIDERS)}.")

                # Default Models per Provider
                elif self._wizard_indices['provider_models_start'] <= choice_num <= self._wizard_indices['provider_models_end']:
                    provider_models_list = [p for p in self.config.get("provider_models", {}).keys() if p in self.SUPPORTED_PROVIDERS]
                    provider_name_idx = choice_num - self._wizard_indices['provider_models_start']
                    if 0 <= provider_name_idx < len(provider_models_list):
                        provider_name_model = provider_models_list[provider_name_idx]
                        current_val = self.get_default_model_for_provider(provider_name_model)
                        new_val = input(f"Default Model for {provider_name_model.capitalize()} [{current_val}]: ").strip()
                        if new_val:
                            self.config["provider_models"][provider_name_model] = new_val
                            updated = True
                    else:
                        print("Invalid selection for provider model.")

                # Default System Instruction
                elif choice_num == self._wizard_indices['default_system_instruction']:
                    current_val = self.get("default_system_instruction", self.DEFAULT_SYSTEM_INSTRUCTION)
                    print(f"Current Global Default System Instruction (full): {current_val}")
                    new_val = input(f"Enter new Global Default System Instruction (leave blank to keep current): ").strip()
                    if new_val:
                        self.config["default_system_instruction"] = new_val
                        updated = True

                # Conversations Directory
                elif choice_num == self._wizard_indices['conversations_dir']:
                    current_val = self.get("conversations_dir")
                    new_val = input(f"Conversations Directory [{current_val}]: ").strip()
                    if new_val:
                        self.config["conversations_dir"] = new_val
                        updated = True

                # Generation Parameters
                elif self._wizard_indices["generation_params_start"] <= choice_num <= self._wizard_indices["generation_params_end"]:
                    param_key_to_edit = None
                    for p_key, p_idx in self._wizard_indices.items():
                        if p_idx == choice_num and p_key in ["temperature", "max_output_tokens", "top_p", "top_k"]:
                            param_key_to_edit = p_key
                            break

                    if param_key_to_edit:
                        current_val = self.config["generation_params"].get(param_key_to_edit)
                        new_val_str = input(f"{param_key_to_edit.replace('_', ' ').capitalize()} [{current_val}]: ").strip()
                        if new_val_str:
                            try:
                                if param_key_to_edit in ["temperature", "top_p"]:
                                    self.config["generation_params"][param_key_to_edit] = float(new_val_str)
                                else:  # max_output_tokens, top_k
                                    self.config["generation_params"][param_key_to_edit] = int(new_val_str)
                                updated = True
                            except ValueError:
                                print(f"Invalid numeric value for {param_key_to_edit}.")
                    else:
                        print("Invalid selection for generation parameter.")


                # Streaming Mode
                elif choice_num == self._wizard_indices['streaming']:
                    current_val = self.get("use_streaming")
                    current_display = 'Enabled' if current_val else 'Disabled'
                    new_val_str = input(f"Enable Streaming by Default (yes/no) [current: {current_display}]: ").strip().lower()
                    if new_val_str in ("y", "yes", "true", "1", "enabled"):
                        self.config["use_streaming"] = True
                        updated = True
                    elif new_val_str in ("n", "no", "false", "0", "disabled"):
                        self.config["use_streaming"] = False
                        updated = True
                    elif new_val_str:
                        print("Invalid input. Please enter 'yes' or 'no'.")
                else:
                    print("Invalid choice.")

                if updated:
                    print("\nConfiguration updated in this session. Current values:")
                    self._display_available_configs_for_wizard()

            except ValueError:
                print("Invalid input. Please enter a number for menu selection or valid value for settings.")
            except Exception as e:
                print(f"An error occurred: {e}")

            # Re-display available configs only if no update was made, or after an update.
            # If an error occurred, it's good to re-display to show the current state.
            if not updated and choice not in ['s', 'q']:  # Avoid re-display if just quitting or saving
                print("\nNo changes made for that selection, or invalid input.")
                self._display_available_configs_for_wizard()


default_config = Config()

if __name__ == "__main__":
    config_instance = Config()  # Use a different variable name to avoid conflict with class name
    config_instance.setup_wizard()
