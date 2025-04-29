"""
Main entry point for the AI Chat Manager backend.
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.middleware import LoggingMiddleware
from utils.logger import setup_logger
from app.utils.api_key_validator import get_available_providers

# Set up logger
logger = setup_logger("ai_chat_manager")
logger.info("Starting AI Chat Manager backend")

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

if __name__ == "__main__":
    # Using configured host/port from settings
    logger.info(f"Starting uvicorn server at {settings.HOST}:{settings.PORT}")
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True, log_level="info")
