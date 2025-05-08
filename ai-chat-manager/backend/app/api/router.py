"""
Main API router for the application.
"""
from fastapi import APIRouter
from app.api.routes import conversations, providers, websocket, settings

# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(
    conversations.router,
    prefix="/conversations",
    tags=["conversations"]
)

api_router.include_router(
    providers.router,
    prefix="/providers",
    tags=["providers"]
)

api_router.include_router(
    websocket.router,
    prefix="/ws",
    tags=["websocket"]
)

# Add additional path for frontend compatibility
api_router.include_router(
    websocket.router,
    prefix="/chat",
    tags=["websocket"]
)

api_router.include_router(
    settings.router,
    prefix="/settings",
    tags=["settings"]
)
