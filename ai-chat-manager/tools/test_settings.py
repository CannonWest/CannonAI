"""
Test script for settings functionality.
"""
import sys
import os
import json

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal
from app.services.settings_service import SettingsService

def test_settings():
    """Test settings storage and retrieval."""
    db = SessionLocal()
    
    try:
        print("Testing settings functionality...\n")
        
        # 1. Retrieve all settings (should create defaults)
        print("1. Getting all settings (should create defaults if not exist):")
        all_settings = SettingsService.get_all_settings(db)
        print(json.dumps(all_settings, indent=2))
        print()
        
        # 2. Update provider settings
        print("2. Updating OpenAI provider settings:")
        openai_settings = SettingsService.update_provider_settings(db, "openai", {
            "default_model": "gpt-4.1-nano",
            "temperature": 0.5,
            "max_tokens": 4000
        })
        print(json.dumps(openai_settings, indent=2))
        print()
        
        # 3. Update UI settings
        print("3. Updating UI settings:")
        ui_settings = SettingsService.update_ui_settings(db, {
            "theme": "dark",
            "show_token_count": False
        })
        print(json.dumps(ui_settings, indent=2))
        print()
        
        # 4. Set custom setting
        print("4. Setting custom setting:")
        custom_setting = SettingsService.set_user_setting(db, "recent_models", [
            "gpt-4.1", "gpt-4o-mini", "gpt-4.1-nano"
        ])
        print(json.dumps(custom_setting, indent=2))
        print()
        
        # 5. Retrieve all settings again to verify changes
        print("5. Getting all settings again to verify changes:")
        updated_settings = SettingsService.get_all_settings(db)
        print(json.dumps(updated_settings, indent=2))
        print()
        
        # 6. Get specific provider settings
        print("6. Getting specific provider settings:")
        provider_settings = SettingsService.get_provider_settings(db, "openai")
        print(json.dumps(provider_settings, indent=2))
        print()
        
        # 7. Save all settings at once
        print("7. Saving all settings at once:")
        all_at_once = SettingsService.save_settings(db, {
            "providers": {
                "openai": {
                    "default_model": "gpt-4o",
                    "temperature": 0.8
                },
                "anthropic": {
                    "default_model": "claude-3-opus"
                }
            },
            "ui": {
                "theme": "light",
                "sidebar_collapsed": True
            },
            "favorite_models": ["gpt-4o", "claude-3-opus"]
        })
        print(json.dumps(all_at_once, indent=2))
        print()
        
        # 8. Verify final state
        print("8. Final state of all settings:")
        final_settings = SettingsService.get_all_settings(db)
        print(json.dumps(final_settings, indent=2))
        print()
        
        print("Settings test completed successfully!")
        
    finally:
        db.close()

if __name__ == "__main__":
    test_settings()
