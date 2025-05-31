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
    DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"  # Fallback if not in provider_models

    def __init__(self, config_file: Optional[Union[str, Path]] = None, override_api_key_dict: Optional[Dict[str, str]] = None, quiet: bool = False):
        """Initialize the configuration manager.

        Args:
            config_file: Path to the configuration file. If None, uses default.
            override_api_key_dict: Dictionary of provider_name: api_key to override config/env.
        """
        self.config_file = Path(config_file) if config_file else self._get_default_config_path()
        project_root = Path(__file__).resolve().parent.parent

        self.config = {
            "api_keys": {
                "gemini": "",
                "claude": "",
                "openai": ""
            },
            "default_provider": "gemini",
            "provider_models": {
                "gemini": self.DEFAULT_GEMINI_MODEL,
                "claude": "claude-3-haiku-20240307",  # Example
                "openai": "gpt-3.5-turbo"  # Example
            },
            "conversations_dir": str(project_root / "cannonai_conversations"),
            "generation_params": {
                "temperature": 0.7,
                "max_output_tokens": 800,
                "top_p": 0.95,
                "top_k": 40
            },
            "use_streaming": False
        }
        self.quiet = quiet
        self.override_api_key_dict = override_api_key_dict or {}
        self.load_config()

    def _get_default_config_path(self) -> Path:
        current_file = Path(__file__).resolve()
        current_dir = current_file.parent
        parent_dir = current_dir.parent
        config_dir = parent_dir / "cannonai_config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / self.DEFAULT_CONFIG_FILE

    def load_config(self) -> Dict[str, Any]:
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)

                # Deep merge for nested dicts like api_keys, provider_models, generation_params
                for key, value in loaded_config.items():
                    if isinstance(value, dict) and isinstance(self.config.get(key), dict):
                        self.config[key].update(value)
                    else:
                        self.config[key] = value

                if not self.quiet:
                    msg = f"Configuration loaded from {self.config_file}"
                    print(f"{Fore.GREEN}{msg}{Style.RESET_ALL}" if colorama_available else msg)
            except Exception as e:
                msg = f"Error loading configuration: {e}"
                print(f"{Fore.RED}{msg}{Style.RESET_ALL}" if colorama_available else msg)
        return self.config

    def save_config(self) -> bool:
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            msg = f"Configuration saved to {self.config_file}"
            print(f"{Fore.GREEN}{msg}{Style.RESET_ALL}" if colorama_available else msg)
            return True
        except Exception as e:
            msg = f"Error saving configuration: {e}"
            print(f"{Fore.RED}{msg}{Style.RESET_ALL}" if colorama_available else msg)
            return False

    def get(self, key: str, default=None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.config[key] = value

    def get_api_key(self, provider_name: str) -> Optional[str]:
        # Check override first
        if provider_name in self.override_api_key_dict:
            return self.override_api_key_dict[provider_name]

        # Then check environment variable (e.g., GEMINI_API_KEY, OPENAI_API_KEY)
        env_var_name = f"{provider_name.upper()}_API_KEY"
        api_key = os.environ.get(env_var_name)
        if api_key:
            return api_key

        # Fallback to config file
        return self.config.get("api_keys", {}).get(provider_name)

    def set_api_key(self, provider_name: str, api_key: str) -> None:
        if "api_keys" not in self.config:
            self.config["api_keys"] = {}
        self.config["api_keys"][provider_name] = api_key
        self.save_config()

    def get_default_model_for_provider(self, provider_name: str) -> Optional[str]:
        return self.config.get("provider_models", {}).get(provider_name)

    def setup_wizard(self) -> bool:
        try:
            print("\n=== CannonAI CLI Configuration Wizard ===\n")
            self._display_available_configs()
            return self._interactive_config_edit()
        except Exception as e:
            msg = f"Error in setup wizard: {e}"
            print(f"{Fore.RED}{msg}{Style.RESET_ALL}" if colorama_available else msg)
            return False

    def _display_available_configs(self) -> None:
        header_color = Fore.CYAN if colorama_available else ""
        value_color = Fore.GREEN if colorama_available else ""
        reset = Style.RESET_ALL if colorama_available else ""

        print(f"{header_color}=== Current Configuration ==={reset}\n")

        print(f"{header_color}API Keys (Provider Specific):{reset}")
        idx = 1
        providers_for_keys = ["gemini", "claude", "openai"]  # Can be dynamic later
        for provider_name in providers_for_keys:
            current_api_key = self.get_api_key(provider_name) or ""
            api_key_display = current_api_key[:4] + "..." + current_api_key[-4:] if current_api_key else "Not set"
            print(f"{header_color}{idx}. {provider_name.capitalize()} API Key:{reset} {value_color}{api_key_display}{reset}")
            idx += 1

        default_provider = self.get("default_provider", "gemini")
        print(f"\n{header_color}{idx}. Default Provider:{reset} {value_color}{default_provider}{reset}")
        current_idx_offset = idx
        idx += 1

        print(f"\n{header_color}Default Models (Per Provider):{reset}")
        for provider_name_model in self.get("provider_models", {}):
            current_model = self.get_default_model_for_provider(provider_name_model)
            print(f"{header_color}{idx}. Default Model for {provider_name_model.capitalize()}:{reset} {value_color}{current_model}{reset}")
            idx += 1

        print(f"\n{header_color}General Settings:{reset}")
        current_dir = self.get("conversations_dir", str(Path.home() / "cannonai_conversations"))
        print(f"{header_color}{idx}. Conversations Directory:{reset} {value_color}{current_dir}{reset}")
        gen_params_start_idx = idx + 1
        idx += 1

        current_params = self.get("generation_params", {})
        print(f"\n{header_color}Global Generation Parameters:{reset}")
        print(f"{header_color}{idx}. Temperature:{reset} {value_color}{current_params.get('temperature', 0.7)}{reset}")
        idx += 1
        print(f"{header_color}{idx}. Max Output Tokens:{reset} {value_color}{current_params.get('max_output_tokens', 800)}{reset}")
        idx += 1
        print(f"{header_color}{idx}. Top-p:{reset} {value_color}{current_params.get('top_p', 0.95)}{reset}")
        idx += 1
        print(f"{header_color}{idx}. Top-k:{reset} {value_color}{current_params.get('top_k', 40)}{reset}")
        streaming_idx = idx + 1
        idx += 1

        current_streaming = self.get("use_streaming", False)
        print(f"\n{header_color}{idx}. Streaming Mode by Default:{reset} {value_color}{'Enabled' if current_streaming else 'Disabled'}{reset}")

        print(f"\n{header_color}Config File:{reset} {value_color}{self.config_file}{reset}")

        # Store indices for _interactive_config_edit
        self._wizard_indices = {
            "api_keys_start": 1,
            "api_keys_end": len(providers_for_keys),
            "default_provider": current_idx_offset,
            "provider_models_start": current_idx_offset + 1,
            "provider_models_end": current_idx_offset + len(self.get("provider_models", {})),
            "conversations_dir": gen_params_start_idx - 1,  # was idx before gen_params
            "gen_params_start": gen_params_start_idx,
            "gen_params_end": streaming_idx - 1,  # was idx before streaming
            "streaming": streaming_idx
        }

    def _interactive_config_edit(self) -> bool:
        providers_for_keys = ["gemini", "claude", "openai"]  # Match _display_available_configs

        while True:
            print(f"\nEnter the number of the setting to modify (1-{self._wizard_indices['streaming']}), 's' to save, or 'q' to quit: ", end="")
            choice = input().lower()

            if choice == 'q':
                print("Exiting without saving.")
                return False
            elif choice == 's':
                self.save_config()
                print("\nConfiguration saved.\n")
                return True

            try:
                choice_num = int(choice)
                if 1 <= choice_num <= self._wizard_indices['api_keys_end']:  # API Keys
                    provider_index = choice_num - self._wizard_indices['api_keys_start']
                    provider_name = providers_for_keys[provider_index]
                    current_val = self.get_api_key(provider_name) or "Not set"
                    new_val = input(f"{provider_name.capitalize()} API Key [{current_val[:4]}...{current_val[-4:] if len(current_val) > 7 else ''}]: ").strip()
                    if new_val: self.config["api_keys"][provider_name] = new_val

                elif choice_num == self._wizard_indices['default_provider']:
                    current_val = self.get("default_provider")
                    new_val = input(f"Default Provider [{current_val}]: ").strip()
                    if new_val: self.config["default_provider"] = new_val

                elif self._wizard_indices['provider_models_start'] <= choice_num <= self._wizard_indices['provider_models_end']:
                    provider_models_list = list(self.get("provider_models", {}).keys())
                    provider_name_idx = choice_num - self._wizard_indices['provider_models_start']
                    if 0 <= provider_name_idx < len(provider_models_list):
                        provider_name_model = provider_models_list[provider_name_idx]
                        current_val = self.get_default_model_for_provider(provider_name_model)
                        new_val = input(f"Default Model for {provider_name_model.capitalize()} [{current_val}]: ").strip()
                        if new_val: self.config["provider_models"][provider_name_model] = new_val
                    else:
                        print("Invalid selection for provider model.")

                elif choice_num == self._wizard_indices['conversations_dir']:
                    current_val = self.get("conversations_dir")
                    new_val = input(f"Conversations Directory [{current_val}]: ").strip()
                    if new_val: self.config["conversations_dir"] = new_val

                elif self._wizard_indices['gen_params_start'] <= choice_num <= self._wizard_indices['gen_params_end']:
                    gen_params_keys = ["temperature", "max_output_tokens", "top_p", "top_k"]
                    param_idx = choice_num - self._wizard_indices['gen_params_start']
                    param_key = gen_params_keys[param_idx]
                    current_val = self.config["generation_params"].get(param_key)
                    new_val_str = input(f"{param_key.replace('_', ' ').capitalize()} [{current_val}]: ").strip()
                    if new_val_str:
                        try:
                            self.config["generation_params"][param_key] = float(new_val_str) if '.' in new_val_str else int(new_val_str)
                        except ValueError:
                            print(f"Invalid value for {param_key}.")

                elif choice_num == self._wizard_indices['streaming']:
                    current_val = self.get("use_streaming")
                    new_val_str = input(f"Enable Streaming by Default [{'yes' if current_val else 'no'}]: ").strip().lower()
                    if new_val_str in ("y", "yes", "true", "1"):
                        self.config["use_streaming"] = True
                    elif new_val_str in ("n", "no", "false", "0"):
                        self.config["use_streaming"] = False

                else:
                    print("Invalid choice.")
            except ValueError:
                print("Invalid input. Please enter a number.")

            self._display_available_configs()  # Show updated config


default_config = Config()

if __name__ == "__main__":
    config = Config()
    config.setup_wizard()