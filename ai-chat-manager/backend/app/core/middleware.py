"""
Middleware for the CannonAI application.
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import status

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging HTTP requests and responses.
    Currently focusing on capturing 404 errors that aren't appearing in application logs.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process an incoming request and log interesting details.
        
        Args:
            request: The incoming HTTP request
            call_next: The next middleware or route handler
            
        Returns:
            The HTTP response
        """
        response = await call_next(request)
        
        # Log 404 errors with details
        if response.status_code == status.HTTP_404_NOT_FOUND:
            logger.warning(
                f"404 Not Found: {request.method} {request.url.path}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "client": request.client.host if request.client else "unknown",
                }
            )
        
        return response
