"""
Routes for managing application settings.
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import logging

from app.core.database import get_db
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/")
async def get_settings(
    provider: Optional[str] = Query(None, description="Filter settings by provider"),
    db: Session = Depends(get_db)
):
    """
    Get user settings.
    
    Args:
        provider: Optional provider name to filter settings
        db: Database session
    
    Returns:
        The current settings
    """
    try:
        if provider:
            # Get settings for a specific provider
            provider_settings = SettingsService.get_provider_settings(db, provider)
            return {"providers": {provider: provider_settings}}
        else:
            # Get all settings
            return SettingsService.get_all_settings(db)
    except Exception as e:
        logger.error(f"Error retrieving settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving settings: {str(e)}")

@router.post("/")
async def save_settings(
    settings: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Save user settings.
    
    Args:
        settings: Dictionary of settings to save
        db: Database session
    
    Returns:
        The saved settings
    """
    try:
        logger.info(f"Saving settings: {settings}")
        return SettingsService.save_settings(db, settings)
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving settings: {str(e)}")

@router.get("/provider-models")
async def get_provider_model_settings(
    provider: Optional[str] = Query(None, description="Filter by provider name")
):
    """
    Get default model settings for each provider.
    
    Args:
        provider: Optional provider name to filter results
    
    Returns:
        Default settings for each supported provider
    """
    try:
        if provider:
            return SettingsService.get_model_defaults(provider)
        else:
            return {
                "openai": SettingsService.get_model_defaults("openai"),
                "anthropic": SettingsService.get_model_defaults("anthropic")
            }
    except Exception as e:
        logger.error(f"Error retrieving provider model settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving provider model settings: {str(e)}")

@router.post("/default-model")
async def set_default_model(
    provider: str = Body(..., description="Provider name"),
    model_id: str = Body(..., description="Model ID to set as default"),
    db: Session = Depends(get_db)
):
    """
    Set the default model for a provider.
    
    Args:
        provider: Provider name (e.g., "openai", "anthropic")
        model_id: Model ID to set as default
        db: Database session
        
    Returns:
        The updated default model setting
    """
    try:
        logger.info(f"Setting default model for {provider} to {model_id}")
        provider_settings = SettingsService.update_provider_settings(
            db, provider, {"default_model": model_id}
        )
        return {"provider": provider, "default_model": provider_settings["default_model"]}
    except Exception as e:
        logger.error(f"Error setting default model: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error setting default model: {str(e)}")

@router.get("/ui")
async def get_ui_settings(db: Session = Depends(get_db)):
    """
    Get UI settings.
    
    Args:
        db: Database session
    
    Returns:
        Dictionary of UI settings
    """
    try:
        return SettingsService.get_ui_settings(db)
    except Exception as e:
        logger.error(f"Error retrieving UI settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving UI settings: {str(e)}")

@router.post("/ui")
async def update_ui_settings(
    settings: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update UI settings.
    
    Args:
        settings: Dictionary of UI settings to update
        db: Database session
    
    Returns:
        The updated UI settings
    """
    try:
        logger.info(f"Updating UI settings: {settings}")
        return SettingsService.update_ui_settings(db, settings)
    except Exception as e:
        logger.error(f"Error updating UI settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating UI settings: {str(e)}")

@router.get("/provider/{provider_name}")
async def get_provider_settings(
    provider_name: str,
    db: Session = Depends(get_db)
):
    """
    Get settings for a specific provider.
    
    Args:
        provider_name: Name of the provider
        db: Database session
    
    Returns:
        Dictionary of provider settings
    """
    try:
        return SettingsService.get_provider_settings(db, provider_name)
    except Exception as e:
        logger.error(f"Error retrieving provider settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving provider settings: {str(e)}")

@router.post("/provider/{provider_name}")
async def update_provider_settings(
    provider_name: str,
    settings: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update settings for a specific provider.
    
    Args:
        provider_name: Name of the provider
        settings: Dictionary of settings to update
        db: Database session
    
    Returns:
        The updated provider settings
    """
    try:
        logger.info(f"Updating provider settings for {provider_name}: {settings}")
        return SettingsService.update_provider_settings(db, provider_name, settings)
    except Exception as e:
        logger.error(f"Error updating provider settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating provider settings: {str(e)}")

@router.get("/custom/{key}")
async def get_custom_setting(
    key: str,
    db: Session = Depends(get_db)
):
    """
    Get a custom setting by key.
    
    Args:
        key: Setting key
        db: Database session
    
    Returns:
        Setting value or None if not found
    """
    try:
        value = SettingsService.get_user_setting(db, key)
        return {key: value}
    except Exception as e:
        logger.error(f"Error retrieving custom setting {key}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving custom setting: {str(e)}")

@router.post("/custom/{key}")
async def set_custom_setting(
    key: str,
    value: Any = Body(...),
    db: Session = Depends(get_db)
):
    """
    Set a custom setting.
    
    Args:
        key: Setting key
        value: Setting value
        db: Database session
    
    Returns:
        The updated setting
    """
    try:
        logger.info(f"Setting custom setting {key}: {value}")
        return SettingsService.set_user_setting(db, key, value)
    except Exception as e:
        logger.error(f"Error setting custom setting {key}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error setting custom setting: {str(e)}")
