"""
Configuration settings for the application.
"""
import os
from pydantic_settings import BaseSettings
from typing import List, Optional, Union, Any
import json

class Settings(BaseSettings):
    """Application settings."""
    
    # Base settings
    PROJECT_NAME: str = "AI Chat Manager"
    API_V1_STR: str = "/api/v1"
    
    # Server settings
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # Logging settings
    LOG_LEVEL: str = "INFO"
    
    # CORS settings
    # The field can be a JSON-formatted list or a comma-separated string
    BACKEND_CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://localhost:8000"]
    
    def _parse_cors_origins(self) -> List[str]:
        """Convert CORS origins to a list if it's a string."""
        if isinstance(self.BACKEND_CORS_ORIGINS, str):
            try:
                # Try parsing as JSON
                return json.loads(self.BACKEND_CORS_ORIGINS)
            except json.JSONDecodeError:
                # Fallback to comma-separated string
                return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]
        return self.BACKEND_CORS_ORIGINS
    
    # Database settings
    DATABASE_URL: str = "sqlite:///./data/chat_manager.db"
    
    # Security settings
    # JWT authentication with configurable key
    SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week
    
    # AI Provider settings
    # API keys for various AI providers, loaded from environment variables
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# Convert CORS origins to the correct format
settings.BACKEND_CORS_ORIGINS = settings._parse_cors_origins()
