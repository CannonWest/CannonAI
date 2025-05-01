"""
Main entry point for the AI Chat Manager backend.
"""
import uvicorn
import sys
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

# Add the parent directory to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.append(str(CURRENT_DIR))

# Now app imports will work properly
from app.api.router import api_router
from app.core.config import settings
from app.core.middleware import LoggingMiddleware
from app.core.database import engine, Base
from app.logging import setup_application_logging, get_logger
from app.utils.api_key_validator import get_available_providers
from app.models.settings.models import UserSettings, ProviderSettings, UISettings

# Set up application logging
setup_application_logging(default_level="INFO", colored_console=True)

# Get application logger
logger = get_logger("ai_chat_manager")
logger.info("Starting AI Chat Manager backend")

# Initialize database tables
logger.info("Initializing database tables")
Base.metadata.create_all(bind=engine)
inspector = inspect(engine)
tables = inspector.get_table_names()
logger.info(f"Database tables: {tables}")

# Check available AI providers
available_providers = get_available_providers(settings)
if not available_providers["openai"] and not available_providers["google"]:
    logger.warning("WARNING: No valid API keys found for any providers. Chat functionality will be limited.")

app = FastAPI(title="AI Chat Manager API")

# CORS settings configured for both development and production
origins = settings.BACKEND_CORS_ORIGINS
logger.info(f"Configured CORS origins: {origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Properly converted list from settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add logging middleware to capture 404 errors
app.add_middleware(LoggingMiddleware)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    """Health check endpoint."""
    logger.debug("Health check endpoint called")
    return {"status": "ok", "message": "AI Chat Manager API is running"}

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize any required app state on startup."""
    logger.info("Running startup event tasks")
    
    # Check that settings tables are properly created
    settings_tables = ["user_settings", "provider_settings", "ui_settings"]
    existing_tables = inspector.get_table_names()
    missing_tables = [table for table in settings_tables if table not in existing_tables]
    
    if missing_tables:
        logger.warning(f"Missing settings tables: {missing_tables}")
        logger.info("Creating missing tables")
        Base.metadata.create_all(bind=engine)
    
    logger.info("Startup tasks completed")

if __name__ == "__main__":
    # Using configured host/port from settings
    logger.info(f"Starting uvicorn server at {settings.HOST}:{settings.PORT}")
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True, log_level="info")
