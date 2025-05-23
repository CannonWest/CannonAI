#!/usr/bin/env python3
"""
WebSocket Diagnostics Tool for Gemini Chat

This script helps diagnose WebSocket connection issues by:
1. Testing WebSocket connectivity directly
2. Checking for CORS and security-related issues
3. Verifying WebSocket server configuration
4. Reporting detailed diagnostics
"""

import sys
import os
import logging
import asyncio
import websockets
import json
import socket
import requests
from pathlib import Path
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('websocket_debug.log')
    ]
)
logger = logging.getLogger("websocket_diagnostics")

# Add parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Default settings
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_WS_PATH = "/ws"

async def test_websocket_connection(host=DEFAULT_HOST, port=DEFAULT_PORT, path=DEFAULT_WS_PATH):
    """Test a direct WebSocket connection and report detailed diagnostics."""
    ws_url = f"ws://{host}:{port}{path}"
    logger.info(f"Testing WebSocket connection to: {ws_url}")
    
    # First check if the server is reachable
    try:
        # Check if the port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        if result != 0:
            logger.error(f"Port {port} is not open on {host}")
            logger.error(f"Server is not reachable on http://{host}:{port}")
            return False
        sock.close()
        logger.info(f"Server is reachable on http://{host}:{port}")
    except Exception as e:
        logger.error(f"Error checking server reachability: {e}")
        return False
    
    # Check if the HTTP server is responding correctly
    try:
        http_url = f"http://{host}:{port}/"
        response = requests.get(http_url, timeout=5)
        logger.info(f"HTTP server response status: {response.status_code}")
        if response.status_code >= 400:
            logger.error(f"HTTP server returned error status: {response.status_code}")
    except Exception as e:
        logger.error(f"Error checking HTTP server: {e}")
    
    # Now test the WebSocket connection
    try:
        # Create connection with debug headers
        headers = {
            "Origin": f"http://{host}:{port}",
            "User-Agent": "WebSocketDiagnosticsTool/1.0",
            "X-Debug": "true"
        }
        
        logger.debug(f"Connecting with headers: {headers}")
        
        async with websockets.connect(ws_url, extra_headers=headers) as websocket:
            logger.info("WebSocket connection established successfully!")
            
            # Send a test message
            test_msg = {"type": "diagnostic", "content": "Testing connection"}
            await websocket.send(json.dumps(test_msg))
            logger.info(f"Sent test message: {test_msg}")
            
            # Wait for a response with timeout
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                logger.info(f"Received response: {response}")
            except asyncio.TimeoutError:
                logger.warning("No response received within timeout period (5s)")
            
            return True
            
    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(f"WebSocket connection rejected with status code: {e.status_code}")
        if e.status_code == 403:
            logger.error("403 Forbidden error - This typically indicates:")
            logger.error("1. Authentication/authorization issue")
            logger.error("2. CORS policy restriction")
            logger.error("3. Server-side middleware rejecting the connection")
            
            # CORS verification
            logger.info("Checking CORS configuration...")
            
        elif e.status_code == 404:
            logger.error("404 Not Found - The WebSocket endpoint does not exist")
            logger.error(f"Verify the WebSocket path: {path}")
        else:
            logger.error(f"Unexpected status code: {e.status_code}")
            
        return False
        
    except Exception as e:
        logger.error(f"WebSocket connection failed: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        return False

async def check_cors_configuration(host=DEFAULT_HOST, port=DEFAULT_PORT):
    """Check CORS configuration of the server."""
    http_url = f"http://{host}:{port}/"
    
    # Try with different origins to test CORS
    test_origins = [
        f"http://{host}:{port}",  # Same origin
        "http://localhost:8000",   # Localhost with same port
        "http://127.0.0.1:8000",   # IP with same port
        "http://example.com",      # Different domain
        "null"                     # null origin
    ]
    
    logger.info("Testing CORS configuration with different origins...")
    
    for origin in test_origins:
        headers = {"Origin": origin}
        try:
            response = requests.options(http_url, headers=headers, timeout=5)
            cors_headers = {
                "Access-Control-Allow-Origin": response.headers.get("Access-Control-Allow-Origin"),
                "Access-Control-Allow-Methods": response.headers.get("Access-Control-Allow-Methods"),
                "Access-Control-Allow-Headers": response.headers.get("Access-Control-Allow-Headers"),
                "Access-Control-Allow-Credentials": response.headers.get("Access-Control-Allow-Credentials")
            }
            
            logger.info(f"CORS test with origin '{origin}':")
            logger.info(f"  Status: {response.status_code}")
            logger.info(f"  CORS Headers: {cors_headers}")
            
            # Check if this origin is allowed
            if cors_headers["Access-Control-Allow-Origin"] == origin or cors_headers["Access-Control-Allow-Origin"] == "*":
                logger.info(f"  Origin '{origin}' is allowed by CORS policy")
            else:
                logger.warning(f"  Origin '{origin}' might be restricted by CORS policy")
                
        except Exception as e:
            logger.error(f"Error checking CORS for origin '{origin}': {e}")

async def debug_websocket_protocol(host=DEFAULT_HOST, port=DEFAULT_PORT, path=DEFAULT_WS_PATH):
    """Analyze the WebSocket upgrade protocol in detail."""
    http_url = f"http://{host}:{port}{path}"
    
    logger.info(f"Analyzing WebSocket upgrade protocol: {http_url}")
    
    # Create a custom HTTP request that mimics WebSocket upgrade
    headers = {
        "Connection": "Upgrade",
        "Upgrade": "websocket",
        "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",  # Example key
        "Sec-WebSocket-Version": "13",
        "Sec-WebSocket-Extensions": "permessage-deflate",
        "Origin": f"http://{host}:{port}"
    }
    
    try:
        # Use a GET request to mimic the WebSocket handshake
        response = requests.get(http_url, headers=headers, timeout=5)
        
        logger.info(f"HTTP status code: {response.status_code}")
        logger.info(f"HTTP response headers: {dict(response.headers)}")
        
        if response.status_code == 101:
            logger.info("WebSocket upgrade successful!")
        elif response.status_code == 403:
            logger.error("WebSocket upgrade forbidden (403):")
            logger.error("This suggests the server is rejecting the WebSocket connection due to:")
            logger.error("1. Authentication issues")
            logger.error("2. Authorization issues")
            logger.error("3. Security middleware restrictions")
        else:
            logger.warning(f"Unexpected status code for WebSocket upgrade: {response.status_code}")
            
        # Check response content
        try:
            if response.text:
                logger.info(f"Response content: {response.text[:500]}...")
        except:
            pass
            
    except Exception as e:
        logger.error(f"Error analyzing WebSocket upgrade: {e}")

async def run_connection_diagnostics():
    """Run comprehensive WebSocket diagnostics."""
    logger.info("=== Starting WebSocket Diagnostics ===")
    
    # Check system information
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Websockets library version: {websockets.__version__}")
    
    # Test basic WebSocket connectivity
    connection_success = await test_websocket_connection()
    
    # If direct connection fails, run additional diagnostics
    if not connection_success:
        logger.info("Running additional diagnostics...")
        await check_cors_configuration()
        await debug_websocket_protocol()
    
    logger.info("=== WebSocket Diagnostics Complete ===")
    
    return connection_success

if __name__ == "__main__":
    # Parse command line arguments for custom host/port
    import argparse
    
    parser = argparse.ArgumentParser(description="WebSocket Diagnostics Tool")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Server host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Server port (default: {DEFAULT_PORT})")
    parser.add_argument("--path", default=DEFAULT_WS_PATH, help=f"WebSocket path (default: {DEFAULT_WS_PATH})")
    
    args = parser.parse_args()
    
    # Run the diagnostics
    result = asyncio.run(run_connection_diagnostics())
    
    # Return appropriate exit code
    sys.exit(0 if result else 1)
