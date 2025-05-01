"""
API client utility for making HTTP requests to external services.

This module provides a wrapper around httpx with built-in logging,
error handling, and retry capabilities for API calls.
"""
import time
import json
import asyncio
from typing import Any, Dict, Optional, Union
import httpx
from app.logging import get_logger
from app.logging.config import log_api_call

# Get logger for API client
logger = get_logger("app.utils.api_client")

class ApiClient:
    """
    API client with automatic logging and error handling.
    
    This class wraps httpx to provide consistent API access patterns
    with built-in logging, timeouts, and error handling.
    """
    
    def __init__(
        self,
        base_url: str,
        provider_name: str,
        default_headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        Initialize API client.
        
        Args:
            base_url: Base URL for the API
            provider_name: Name of the API provider (e.g., 'openai', 'anthropic')
            default_headers: Default headers to include in all requests
            timeout: Default timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.provider_name = provider_name
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Create httpx client
        self.client = httpx.Client(
            base_url=self.base_url,
            headers=self.default_headers,
            timeout=self.timeout
        )
        
        # Create async httpx client
        self.async_client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.default_headers,
            timeout=self.timeout
        )
    
    def request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        retry_on_status: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Make a synchronous HTTP request with automatic logging and retries.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            headers: Additional headers for this request
            params: URL parameters
            data: Request body data
            json_data: JSON data to send in the request
            retry_on_status: List of status codes to retry on
            
        Returns:
            Response data as a dictionary
            
        Raises:
            httpx.HTTPError: If the request fails after retries
        """
        # Normalize endpoint
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        
        # Combine headers
        request_headers = {**self.default_headers}
        if headers:
            request_headers.update(headers)
        
        # Status codes to retry on
        retry_status_codes = retry_on_status or [429, 500, 502, 503, 504]
        
        # Prepare request data for logging
        request_data = {
            "method": method,
            "url": f"{self.base_url}{endpoint}",
            "headers": request_headers,
        }
        if params:
            request_data["params"] = params
        if json_data:
            request_data["json"] = json_data
        elif data:
            request_data["data"] = data
        
        # Track retry attempts
        attempt = 0
        start_time = time.time()
        last_error = None
        
        while attempt <= self.max_retries:
            try:
                # Make the request
                if method.upper() == "GET":
                    response = self.client.get(
                        endpoint, headers=request_headers, params=params
                    )
                elif method.upper() == "POST":
                    response = self.client.post(
                        endpoint,
                        headers=request_headers,
                        params=params,
                        data=data,
                        json=json_data,
                    )
                elif method.upper() == "PUT":
                    response = self.client.put(
                        endpoint,
                        headers=request_headers,
                        params=params,
                        data=data,
                        json=json_data,
                    )
                elif method.upper() == "DELETE":
                    response = self.client.delete(
                        endpoint, headers=request_headers, params=params
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Calculate request duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Check if we need to retry based on status code
                if response.status_code in retry_status_codes and attempt < self.max_retries:
                    attempt += 1
                    logger.warning(
                        f"API request to {endpoint} failed with status {response.status_code}, "
                        f"retrying ({attempt}/{self.max_retries})..."
                    )
                    time.sleep(self.retry_delay * attempt)  # Exponential backoff
                    continue
                
                # Raise exception for error status codes
                response.raise_for_status()
                
                # Parse response
                if response.headers.get("content-type", "").startswith("application/json"):
                    response_data = response.json()
                else:
                    response_data = {"text": response.text}
                
                # Log successful API call
                log_api_call(
                    logger=logger,
                    provider=self.provider_name,
                    endpoint=endpoint,
                    request_data=request_data,
                    response_data=response_data,
                    duration_ms=duration_ms,
                )
                
                return response_data
                
            except httpx.HTTPError as e:
                last_error = e
                
                # Calculate request duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Determine if we should retry
                if attempt < self.max_retries:
                    attempt += 1
                    logger.warning(
                        f"API request to {endpoint} failed: {str(e)}, "
                        f"retrying ({attempt}/{self.max_retries})..."
                    )
                    time.sleep(self.retry_delay * attempt)  # Exponential backoff
                else:
                    # Log the final error
                    log_api_call(
                        logger=logger,
                        provider=self.provider_name,
                        endpoint=endpoint,
                        request_data=request_data,
                        error=e,
                        duration_ms=duration_ms,
                    )
                    raise
        
        # If we got here, all retries failed
        if last_error:
            raise last_error
        
        raise RuntimeError("API request failed after retries")
    
    async def async_request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        retry_on_status: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Make an asynchronous HTTP request with automatic logging and retries.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            headers: Additional headers for this request
            params: URL parameters
            data: Request body data
            json_data: JSON data to send in the request
            retry_on_status: List of status codes to retry on
            
        Returns:
            Response data as a dictionary
            
        Raises:
            httpx.HTTPError: If the request fails after retries
        """
        # Normalize endpoint
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        
        # Combine headers
        request_headers = {**self.default_headers}
        if headers:
            request_headers.update(headers)
        
        # Status codes to retry on
        retry_status_codes = retry_on_status or [429, 500, 502, 503, 504]
        
        # Prepare request data for logging
        request_data = {
            "method": method,
            "url": f"{self.base_url}{endpoint}",
            "headers": request_headers,
        }
        if params:
            request_data["params"] = params
        if json_data:
            request_data["json"] = json_data
        elif data:
            request_data["data"] = data
        
        # Track retry attempts
        attempt = 0
        start_time = time.time()
        last_error = None
        
        while attempt <= self.max_retries:
            try:
                # Make the request
                if method.upper() == "GET":
                    response = await self.async_client.get(
                        endpoint, headers=request_headers, params=params
                    )
                elif method.upper() == "POST":
                    response = await self.async_client.post(
                        endpoint,
                        headers=request_headers,
                        params=params,
                        data=data,
                        json=json_data,
                    )
                elif method.upper() == "PUT":
                    response = await self.async_client.put(
                        endpoint,
                        headers=request_headers,
                        params=params,
                        data=data,
                        json=json_data,
                    )
                elif method.upper() == "DELETE":
                    response = await self.async_client.delete(
                        endpoint, headers=request_headers, params=params
                    )
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Calculate request duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Check if we need to retry based on status code
                if response.status_code in retry_status_codes and attempt < self.max_retries:
                    attempt += 1
                    logger.warning(
                        f"API request to {endpoint} failed with status {response.status_code}, "
                        f"retrying ({attempt}/{self.max_retries})..."
                    )
                    await asyncio.sleep(self.retry_delay * attempt)  # Exponential backoff
                    continue
                
                # Raise exception for error status codes
                response.raise_for_status()
                
                # Parse response
                if response.headers.get("content-type", "").startswith("application/json"):
                    response_data = response.json()
                else:
                    response_data = {"text": response.text}
                
                # Log successful API call
                log_api_call(
                    logger=logger,
                    provider=self.provider_name,
                    endpoint=endpoint,
                    request_data=request_data,
                    response_data=response_data,
                    duration_ms=duration_ms,
                )
                
                return response_data
                
            except httpx.HTTPError as e:
                last_error = e
                
                # Calculate request duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Determine if we should retry
                if attempt < self.max_retries:
                    attempt += 1
                    logger.warning(
                        f"API request to {endpoint} failed: {str(e)}, "
                        f"retrying ({attempt}/{self.max_retries})..."
                    )
                    await asyncio.sleep(self.retry_delay * attempt)  # Exponential backoff
                else:
                    # Log the final error
                    log_api_call(
                        logger=logger,
                        provider=self.provider_name,
                        endpoint=endpoint,
                        request_data=request_data,
                        error=e,
                        duration_ms=duration_ms,
                    )
                    raise
        
        # If we got here, all retries failed
        if last_error:
            raise last_error
        
        raise RuntimeError("API request failed after retries")
    
    def close(self):
        """Close the HTTP clients."""
        self.client.close()
        asyncio.create_task(self.async_client.aclose())
    
    async def aclose(self):
        """Close the async HTTP client."""
        await self.async_client.aclose()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()


# Factory function to create pre-configured API clients for specific providers
def create_api_client(provider: str, api_key: str) -> ApiClient:
    """
    Create an API client for a specific provider.
    
    Args:
        provider: Provider name ('openai', 'anthropic', etc.)
        api_key: API key for authentication
        
    Returns:
        Configured ApiClient instance
        
    Raises:
        ValueError: If the provider is not supported
    """
    if provider.lower() == "openai":
        return ApiClient(
            base_url="https://api.openai.com",
            provider_name="openai",
            default_headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
    elif provider.lower() == "anthropic":
        return ApiClient(
            base_url="https://api.anthropic.com",
            provider_name="anthropic",
            default_headers={
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
        )
    elif provider.lower() == "google":
        return ApiClient(
            base_url="https://generativelanguage.googleapis.com",
            provider_name="google",
            default_headers={
                "Content-Type": "application/json",
            },
            # For Google's Vertex AI or PaLM, API key is usually passed as a parameter
        )
    else:
        raise ValueError(f"Unsupported API provider: {provider}")
