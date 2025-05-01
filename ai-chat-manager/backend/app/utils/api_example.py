"""
Example usage of the API client with comprehensive logging.

This module demonstrates how to use the ApiClient for making API requests to
various providers with automatic logging of requests, responses, and errors.
"""

import asyncio
import os
from app.logging import setup_application_logging, get_logger
from app.utils.api_client import create_api_client

# Set up logging
setup_application_logging(default_level="DEBUG", colored_console=True)
logger = get_logger("api_example")

def example_openai_request():
    """Example of making a request to OpenAI API with logging"""
    # Get API key from environment
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.error("OPENAI_API_KEY not found in environment")
        return
    
    logger.info("Making request to OpenAI API")
    
    try:
        # Create API client
        client = create_api_client("openai", api_key)
        
        # Make API request with automatic logging
        response = client.request(
            method="POST",
            endpoint="/v1/chat/completions",
            json_data={
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello, how are you?"}
                ],
                "max_tokens": 150
            }
        )
        
        # Process response (all logging is handled automatically)
        message = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        logger.info(f"Received response: {message[:50]}...")
        
    except Exception as e:
        # The ApiClient automatically logs the error with full details
        logger.error(f"API request failed: {str(e)}")
    
    finally:
        # Close the client
        if 'client' in locals():
            client.close()


async def example_async_anthropic_request():
    """Example of making an async request to Anthropic API with logging"""
    # Get API key from environment
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not found in environment")
        return
    
    logger.info("Making async request to Anthropic API")
    
    try:
        # Create API client
        client = create_api_client("anthropic", api_key)
        
        # Make async API request with automatic logging
        response = await client.async_request(
            method="POST",
            endpoint="/v1/messages",
            json_data={
                "model": "claude-3-opus-20240229",
                "max_tokens": 150,
                "messages": [
                    {"role": "user", "content": "Hello, how are you?"}
                ]
            }
        )
        
        # Process response (all logging is handled automatically)
        message = response.get("content", [{}])[0].get("text", "")
        logger.info(f"Received response: {message[:50]}...")
        
    except Exception as e:
        # The ApiClient automatically logs the error with full details
        logger.error(f"Async API request failed: {str(e)}")
    
    finally:
        # Close the client
        if 'client' in locals():
            await client.aclose()


# Example of handling API errors
def example_error_handling():
    """Example of handling and logging API errors"""
    # Create client with invalid API key to demonstrate error handling
    logger.info("Testing error handling with invalid API key")
    
    try:
        # Create API client with invalid key
        client = create_api_client("openai", "invalid_key")
        
        # Make API request that will fail
        response = client.request(
            method="POST",
            endpoint="/v1/chat/completions",
            json_data={
                "model": "gpt-4",
                "messages": [
                    {"role": "user", "content": "Hello"}
                ]
            }
        )
        
    except Exception as e:
        # The error is automatically logged by the ApiClient
        logger.info("Error was caught and logged successfully")
    
    finally:
        # Close the client
        if 'client' in locals():
            client.close()


async def run_examples():
    """Run all examples"""
    # Run synchronous example
    example_openai_request()
    
    # Run error handling example
    example_error_handling()
    
    # Run asynchronous example
    await example_async_anthropic_request()


if __name__ == "__main__":
    # Run the examples
    asyncio.run(run_examples())
