"""
Unit tests for the SettingsManager class.
"""

import os
import sys
import json
import tempfile
import pytest
from unittest.mock import MagicMock, patch

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.services.storage import SettingsManager
from src.utils.constants import DEFAULT_PARAMS


class TestSettingsManager:
    """Tests for the SettingsManager class that manages application settings."""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save original CONFIG_DIR
            with patch('src.services.storage.CONFIG_DIR', temp_dir):
                with patch('src.services.storage.SETTINGS_FILE', os.path.join(temp_dir, 'settings.json')):
                    yield temp_dir
    
    @pytest.fixture
    def mock_qsettings(self):
        """Mock QSettings to return None."""
        with patch('src.services.storage.QSettings') as mock_qsettings:
            # Configure the mock to return None for any value
            mock_instance = mock_qsettings.return_value
            mock_instance.value.return_value = None
            yield mock_qsettings

    def test_init(self, temp_config_dir, mock_qsettings):
        """Test settings manager initialization with mocked QSettings."""
        # Create a settings manager with clean environment and no QSettings values
        with patch.dict(os.environ, {}, clear=True):
            manager = SettingsManager()

            # Check the manager has initialized with the default parameters
            for key, value in DEFAULT_PARAMS.items():
                assert manager.settings[key] == value, f"Key {key} doesn't match default value"

            # Check the config directory was created
            assert os.path.exists(temp_config_dir)

    def test_load_settings_from_json(self, temp_config_dir, mock_qsettings):
        """Test loading settings from a JSON file."""
        # Create a settings file
        settings_file = os.path.join(temp_config_dir, 'settings.json')
        test_settings = {
            "model": "gpt-4o-mini",
            "temperature": 0.5,
            "max_output_tokens": 2000,
            "stream": False
        }

        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(test_settings, f)

        # Create a settings manager that will load these settings
        with patch('src.services.storage.SETTINGS_FILE', settings_file):
            with patch.dict(os.environ, {}, clear=True):
                manager = SettingsManager()

                # Check settings were loaded correctly
                assert manager.settings["model"] == "gpt-4o-mini"
                assert manager.settings["temperature"] == 0.5
                assert manager.settings["max_output_tokens"] == 2000
                assert manager.settings["stream"] is False

                # Check default values are preserved for keys not in the file
                assert "top_p" in manager.settings
                assert manager.settings["top_p"] == DEFAULT_PARAMS["top_p"]

    def test_load_settings_from_env(self, temp_config_dir, mock_qsettings):
        """Test loading API key from environment variable."""
        # Set API key in environment
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_api_key_from_env"}, clear=True):
            # Create a settings manager
            manager = SettingsManager()

            # Check API key was loaded from environment
            assert manager.settings["api_key"] == "test_api_key_from_env"

    def test_save_settings(self, temp_config_dir, mock_qsettings):
        """Test saving settings to disk."""
        # Create a settings manager with clean environment
        with patch.dict(os.environ, {}, clear=True):
            manager = SettingsManager()

            # Update settings
            manager.settings["model"] = "gpt-4o-mini"
            manager.settings["temperature"] = 0.5
            manager.settings["api_key"] = "test_api_key"

            # Save settings
            result = manager.save_settings()

            # Check settings were saved successfully
            assert result is True

            # Check settings file exists
            settings_file = os.path.join(temp_config_dir, 'settings.json')
            assert os.path.exists(settings_file)

            # Load the saved settings and check they match
            with open(settings_file, 'r', encoding='utf-8') as f:
                saved_settings = json.load(f)

            assert saved_settings["model"] == "gpt-4o-mini"
            assert saved_settings["temperature"] == 0.5

            # API key should not be saved to disk
            assert "api_key" not in saved_settings

    def test_get_settings(self, temp_config_dir, mock_qsettings):
        """Test getting the current settings."""
        # Create a settings manager with clean environment
        with patch.dict(os.environ, {}, clear=True):
            manager = SettingsManager()

            # Update settings
            manager.settings["model"] = "gpt-4o-mini"

            # Get settings
            settings = manager.get_settings()

            # Check settings are correct
            assert settings == manager.settings

            # Check returned settings is a copy (changes don't affect original)
            settings["model"] = "gpt-4"
            assert manager.settings["model"] == "gpt-4o-mini"

    def test_update_settings(self, temp_config_dir, mock_qsettings):
        """Test updating settings with default parameters."""
        # Create a settings manager with clean environment
        with patch.dict(os.environ, {}, clear=True):
            manager = SettingsManager()

            # Save default model value
            default_model = DEFAULT_PARAMS["model"]

            # Mock save_settings to verify it's called
            manager.save_settings = MagicMock(return_value=True)

            # Update settings
            new_settings = {
                "model": "gpt-4o-mini",
                "temperature": 0.5
            }
            manager.update_settings(new_settings)

            # Check settings were updated
            assert manager.settings["model"] == "gpt-4o-mini"
            assert manager.settings["temperature"] == 0.5

            # Check save_settings was called
            manager.save_settings.assert_called_once()

            # Restore settings to verify values
            manager.settings["model"] = default_model
            assert manager.settings["model"] == DEFAULT_PARAMS["model"]

    def test_sensitive_data_handling(self, temp_config_dir, mock_qsettings):
        """Test handling of sensitive data like API keys."""
        # Create a settings manager with API key and clean environment
        with patch.dict(os.environ, {}, clear=True):
            manager = SettingsManager()
            manager.settings["api_key"] = "original_api_key"

            # Update settings without API key
            manager.save_settings = MagicMock(return_value=True)  # Prevent actual save

            manager._update_settings_exclude_sensitive({
                "model": "gpt-4o-mini",
                "temperature": 0.5
                # No API key
            })

            # Check API key is preserved
            assert manager.settings["api_key"] == "original_api_key"
            assert manager.settings["model"] == "gpt-4o-mini"

            # Update settings with new API key
            manager._update_settings_exclude_sensitive({
                "model": "gpt-4",
                "api_key": "new_api_key"
            })

            # Check API key is updated
            assert manager.settings["api_key"] == "new_api_key"
            assert manager.settings["model"] == "gpt-4"