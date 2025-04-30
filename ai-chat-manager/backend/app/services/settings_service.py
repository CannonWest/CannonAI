"""
Service for managing application settings.
"""
from typing import Dict, Any, Optional, List
import logging
from sqlalchemy.orm import Session

from app.models.settings.models import UserSettings, ProviderSettings, UISettings
from app.models.openai.model_config import get_default_model

logger = logging.getLogger(__name__)

class SettingsService:
    """Service for managing user and application settings."""
    
    @staticmethod
    def get_all_settings(db: Session, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get all settings for a user.
        
        Args:
            db: Database session
            user_id: Optional user ID (for future auth)
            
        Returns:
            Dictionary containing all settings
        """
        # Get provider settings
        provider_settings = db.query(ProviderSettings).filter(
            ProviderSettings.user_id == user_id
        ).all()
        
        providers = {}
        for setting in provider_settings:
            providers[setting.provider_name] = {
                "default_model": setting.default_model,
                "temperature": setting.temperature,
                "max_tokens": setting.max_tokens,
                **setting.additional_settings
            }
        
        # If no provider settings found, create defaults
        if not providers:
            openai_settings = ProviderSettings.get_or_create(db, "openai", user_id)
            anthropic_settings = ProviderSettings.get_or_create(db, "anthropic", user_id)
            
            providers = {
                "openai": {
                    "default_model": openai_settings.default_model,
                    "temperature": openai_settings.temperature,
                    "max_tokens": openai_settings.max_tokens,
                    **openai_settings.additional_settings
                },
                "anthropic": {
                    "default_model": anthropic_settings.default_model,
                    "temperature": anthropic_settings.temperature,
                    "max_tokens": anthropic_settings.max_tokens,
                    **anthropic_settings.additional_settings
                }
            }
        
        # Get UI settings
        ui_settings = UISettings.get_or_create(db, user_id)
        
        ui = {
            "theme": ui_settings.theme,
            "sidebar_collapsed": ui_settings.sidebar_collapsed,
            "show_token_count": ui_settings.show_token_count,
            **ui_settings.additional_settings
        }
        
        # Get any other user settings
        other_settings = db.query(UserSettings).filter(
            UserSettings.user_id == user_id
        ).all()
        
        others = {}
        for setting in other_settings:
            others[setting.settings_key] = setting.settings_value
        
        # Combine all settings
        return {
            "providers": providers,
            "ui": ui,
            **others
        }
    
    @staticmethod
    def get_provider_settings(db: Session, provider_name: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get settings for a specific provider.
        
        Args:
            db: Database session
            provider_name: Name of the provider
            user_id: Optional user ID (for future auth)
            
        Returns:
            Dictionary of provider-specific settings
        """
        setting = ProviderSettings.get_or_create(db, provider_name, user_id)
        
        return {
            "default_model": setting.default_model,
            "temperature": setting.temperature,
            "max_tokens": setting.max_tokens,
            **setting.additional_settings
        }
    
    @staticmethod
    def update_provider_settings(
        db: Session, 
        provider_name: str, 
        settings: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update settings for a specific provider.
        
        Args:
            db: Database session
            provider_name: Name of the provider
            settings: Dictionary of settings to update
            user_id: Optional user ID (for future auth)
            
        Returns:
            Updated provider settings
        """
        provider_settings = ProviderSettings.get_or_create(db, provider_name, user_id)
        
        # Extract known fields
        if "default_model" in settings:
            provider_settings.default_model = settings.pop("default_model")
        if "temperature" in settings:
            provider_settings.temperature = settings.pop("temperature")
        if "max_tokens" in settings:
            provider_settings.max_tokens = settings.pop("max_tokens")
        
        # Store remaining settings in additional_settings
        if settings:
            provider_settings.additional_settings.update(settings)
        
        db.commit()
        db.refresh(provider_settings)
        
        logger.info(f"Updated provider settings for {provider_name}: {settings}")
        
        return {
            "default_model": provider_settings.default_model,
            "temperature": provider_settings.temperature,
            "max_tokens": provider_settings.max_tokens,
            **provider_settings.additional_settings
        }
    
    @staticmethod
    def get_ui_settings(db: Session, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get UI settings.
        
        Args:
            db: Database session
            user_id: Optional user ID (for future auth)
            
        Returns:
            Dictionary of UI settings
        """
        setting = UISettings.get_or_create(db, user_id)
        
        return {
            "theme": setting.theme,
            "sidebar_collapsed": setting.sidebar_collapsed,
            "show_token_count": setting.show_token_count,
            **setting.additional_settings
        }
    
    @staticmethod
    def update_ui_settings(
        db: Session, 
        settings: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update UI settings.
        
        Args:
            db: Database session
            settings: Dictionary of settings to update
            user_id: Optional user ID (for future auth)
            
        Returns:
            Updated UI settings
        """
        ui_settings = UISettings.get_or_create(db, user_id)
        
        # Extract known fields
        if "theme" in settings:
            ui_settings.theme = settings.pop("theme")
        if "sidebar_collapsed" in settings:
            ui_settings.sidebar_collapsed = settings.pop("sidebar_collapsed")
        if "show_token_count" in settings:
            ui_settings.show_token_count = settings.pop("show_token_count")
        
        # Store remaining settings in additional_settings
        if settings:
            ui_settings.additional_settings.update(settings)
        
        db.commit()
        db.refresh(ui_settings)
        
        logger.info(f"Updated UI settings: {settings}")
        
        return {
            "theme": ui_settings.theme,
            "sidebar_collapsed": ui_settings.sidebar_collapsed,
            "show_token_count": ui_settings.show_token_count,
            **ui_settings.additional_settings
        }
    
    @staticmethod
    def set_user_setting(
        db: Session, 
        key: str,
        value: Any,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Set an arbitrary user setting.
        
        Args:
            db: Database session
            key: Setting key
            value: Setting value
            user_id: Optional user ID (for future auth)
            
        Returns:
            Updated setting
        """
        setting = UserSettings.get_or_create(db, key, user_id)
        
        setting.settings_value = value
        db.commit()
        db.refresh(setting)
        
        logger.info(f"Updated user setting {key}: {value}")
        
        return {key: setting.settings_value}
    
    @staticmethod
    def get_user_setting(
        db: Session, 
        key: str,
        user_id: Optional[str] = None
    ) -> Any:
        """
        Get an arbitrary user setting.
        
        Args:
            db: Database session
            key: Setting key
            user_id: Optional user ID (for future auth)
            
        Returns:
            Setting value or None if not found
        """
        setting = db.query(UserSettings).filter(
            UserSettings.settings_key == key,
            UserSettings.user_id == user_id
        ).first()
        
        if setting:
            return setting.settings_value
        return None
    
    @staticmethod
    def get_model_defaults(provider_name: str) -> Dict[str, Any]:
        """
        Get default model settings for a provider.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            Dictionary with default settings
        """
        if provider_name == "openai":
            return {
                "default_model": get_default_model().model_id,
                "temperature_range": {
                    "min": 0.0,
                    "max": 2.0,
                    "default": 0.7,
                    "step": 0.1
                },
                "max_tokens_range": {
                    "min": 100,
                    "max": 8192,
                    "default": 2000,
                    "step": 100
                }
            }
        elif provider_name == "anthropic":
            return {
                "default_model": "claude-3.5-sonnet",
                "temperature_range": {
                    "min": 0.0,
                    "max": 1.0,
                    "default": 0.7,
                    "step": 0.1
                },
                "max_tokens_range": {
                    "min": 100,
                    "max": 100000,
                    "default": 2000,
                    "step": 100
                }
            }
        else:
            return {}
    
    @staticmethod
    def save_settings(
        db: Session,
        settings: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save all settings.
        
        Args:
            db: Database session
            settings: Dictionary of settings to save
            user_id: Optional user ID (for future auth)
            
        Returns:
            Saved settings
        """
        result = {}
        
        # Process provider settings
        if "providers" in settings:
            providers = {}
            for provider, provider_settings in settings["providers"].items():
                providers[provider] = SettingsService.update_provider_settings(
                    db, provider, provider_settings, user_id
                )
            result["providers"] = providers
        
        # Process UI settings
        if "ui" in settings:
            result["ui"] = SettingsService.update_ui_settings(
                db, settings["ui"], user_id
            )
        
        # Process other settings
        for key, value in settings.items():
            if key not in ["providers", "ui"]:
                result[key] = SettingsService.set_user_setting(
                    db, key, value, user_id
                )[key]
        
        logger.info(f"Saved all settings: {settings}")
        
        return result
