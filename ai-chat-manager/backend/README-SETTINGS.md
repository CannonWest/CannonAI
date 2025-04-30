# Settings Storage Implementation

This document outlines the implementation of persistent user settings storage in the CannonAI Chat Manager application.

## Overview

The settings system is designed to store and retrieve:

1. Provider-specific settings (OpenAI, Anthropic, etc.)
2. UI preferences (theme, sidebar state, etc.)
3. Arbitrary custom settings with a flexible key-value approach

All settings are persisted in SQLite and can be retrieved across sessions.

## Database Models

Three main models have been implemented:

### 1. ProviderSettings

Stores provider-specific configuration:
- Default model
- Temperature
- Max tokens
- Additional settings (JSON)

### 2. UISettings

Stores UI preferences:
- Theme
- Sidebar collapsed state
- Token count visibility
- Additional settings (JSON)

### 3. UserSettings

Stores arbitrary key-value settings:
- Setting key
- Setting value (JSON)

## Service Layer

The `SettingsService` provides methods for:

- Getting all settings
- Getting/updating provider settings
- Getting/updating UI settings
- Setting/getting custom settings
- Retrieving default model parameters

## API Endpoints

New endpoints have been added:

- `GET /api/v1/settings` - Get all settings
- `POST /api/v1/settings` - Save all settings
- `GET /api/v1/settings/provider/{provider_name}` - Get provider settings
- `POST /api/v1/settings/provider/{provider_name}` - Update provider settings
- `GET /api/v1/settings/ui` - Get UI settings
- `POST /api/v1/settings/ui` - Update UI settings
- `GET /api/v1/settings/custom/{key}` - Get custom setting
- `POST /api/v1/settings/custom/{key}` - Set custom setting

## Implementation Details

### Database Integration

- Tables are automatically created during application startup
- Default settings are generated when first accessed

### Data Structure

Settings are returned as a nested JSON structure:

```json
{
  "providers": {
    "openai": {
      "default_model": "gpt-4.1-mini",
      "temperature": 0.7,
      "max_tokens": 2000
    },
    "anthropic": {
      "default_model": "claude-3.5-sonnet",
      "temperature": 0.7,
      "max_tokens": 2000
    }
  },
  "ui": {
    "theme": "light",
    "sidebar_collapsed": false,
    "show_token_count": true
  },
  "custom_setting1": "value",
  "custom_setting2": ["array", "values"]
}
```

### Flexibility

- Additional settings can be stored in the JSON fields
- New provider types can be added without schema changes
- User ID field enables future multi-user support

## Testing

Two test scripts are provided:

1. `tools/init_settings_db.py` - Initializes the settings database
2. `tools/test_settings.py` - Tests settings CRUD operations

## Future Enhancements

- User authentication integration
- Settings validation
- Default settings templates
- Settings backup/restore
- Settings migration between versions

## Implementation Files

- `app/models/settings/models.py` - Database models
- `app/services/settings_service.py` - Service layer
- `app/api/routes/settings.py` - API endpoints
- `tools/init_settings_db.py` - Database initialization
- `tools/test_settings.py` - Testing script

## Usage Example

```python
# Get all settings
from app.core.database import get_db
from app.services.settings_service import SettingsService

db = next(get_db())
all_settings = SettingsService.get_all_settings(db)

# Update a provider setting
SettingsService.update_provider_settings(
    db, 
    "openai", 
    {"default_model": "gpt-4o"}
)

# Store a custom setting
SettingsService.set_user_setting(
    db,
    "recent_conversations",
    ["conv1", "conv2", "conv3"]
)
```
