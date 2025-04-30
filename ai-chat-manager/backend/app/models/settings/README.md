# Settings Database Models

This module provides database models and services for storing and retrieving application settings.

## Models Overview

### UserSettings

Stores arbitrary key-value settings for users:

- `user_id`: Optional ID for future auth support
- `settings_key`: Unique key for the setting (e.g., "favorite_models")
- `settings_value`: JSON-stored value for the setting

### ProviderSettings

Stores provider-specific settings:

- `provider_name`: Provider identifier (e.g., "openai", "anthropic")
- `default_model`: Default model ID for this provider
- `temperature`: Model temperature setting (0.0-2.0)
- `max_tokens`: Maximum tokens to generate
- `additional_settings`: JSON-stored additional settings

### UISettings

Stores UI-related settings:

- `theme`: UI theme (e.g., "light", "dark")
- `sidebar_collapsed`: Whether the sidebar is collapsed by default
- `show_token_count`: Whether to show token counts
- `additional_settings`: JSON-stored additional settings

## Usage

### Service Methods

The `SettingsService` provides several methods for interacting with settings:

```python
# Get all settings
all_settings = SettingsService.get_all_settings(db)

# Get settings for a specific provider
openai_settings = SettingsService.get_provider_settings(db, "openai")

# Update provider settings
updated_settings = SettingsService.update_provider_settings(db, "openai", {
    "default_model": "gpt-4.1-mini",
    "temperature": 0.7
})

# Get/update UI settings
ui_settings = SettingsService.get_ui_settings(db)
updated_ui = SettingsService.update_ui_settings(db, {
    "theme": "dark",
    "show_token_count": True
})

# Set/get custom settings
SettingsService.set_user_setting(db, "recent_models", ["gpt-4o", "gpt-4.1"])
recent_models = SettingsService.get_user_setting(db, "recent_models")
```

### API Endpoints

Several endpoints are available for interacting with settings:

- `GET /api/v1/settings` - Get all settings
- `POST /api/v1/settings` - Save all settings
- `GET /api/v1/settings/provider/{provider_name}` - Get provider settings
- `POST /api/v1/settings/provider/{provider_name}` - Update provider settings
- `GET /api/v1/settings/ui` - Get UI settings
- `POST /api/v1/settings/ui` - Update UI settings
- `GET /api/v1/settings/custom/{key}` - Get custom setting
- `POST /api/v1/settings/custom/{key}` - Set custom setting
- `POST /api/v1/settings/default-model` - Set default model
- `GET /api/v1/settings/provider-models` - Get model defaults

## Initialization

Settings tables are automatically initialized when the application starts.

For testing, you can use:

```bash
# Initialize settings database
python tools/init_settings_db.py

# Test settings functionality
python tools/test_settings.py
```

## Future Enhancements

- User authentication integration
- Setting validation
- Default settings templates
- Settings backup/restore
