#!/usr/bin/env python3
"""
WebSocket Connection Troubleshooter for Gemini Chat

This specialized script performs deep diagnostic testing of WebSocket connections
and helps identify exactly why connections are being rejected with 403 Forbidden errors.
"""
import os
import sys
import time
import json
import socket
import requests
import websocket
import argparse
import traceback
from pathlib import Path

# Add color support for console output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_section(title):
    """Print a formatted section header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 50}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD} {title} {Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 50}{Colors.ENDC}\n")

def print_info(message):
    """Print information message."""
    print(f"{Colors.BLUE}[INFO] {message}{Colors.ENDC}")

def print_success(message):
    """Print success message."""
    print(f"{Colors.GREEN}[SUCCESS] {message}{Colors.ENDC}")

def print_warning(message):
    """Print warning message."""
    print(f"{Colors.YELLOW}[WARNING] {message}{Colors.ENDC}")

def print_error(message):
    """Print error message."""
    print(f"{Colors.RED}[ERROR] {message}{Colors.ENDC}")

def check_server_availability(host, port):
    """Check if the server is available using a simple socket connection."""
    print_section("CHECKING SERVER AVAILABILITY")
    
    try:
        # Try to connect to the port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        
        if result == 0:
            print_success(f"Server is reachable on {host}:{port}")
            sock.close()
            return True
        else:
            print_error(f"Cannot connect to {host}:{port} - Error code: {result}")
            return False
    except Exception as e:
        print_error(f"Error checking server availability: {str(e)}")
        return False

def test_http_endpoint(host, port):
    """Test the HTTP endpoint to ensure server is responding."""
    print_section("TESTING HTTP ENDPOINT")
    
    try:
        url = f"http://{host}:{port}/"
        print_info(f"Requesting: {url}")
        
        response = requests.get(url, timeout=5)
        print_info(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            print_success("HTTP endpoint is working correctly")
            return True
        else:
            print_warning(f"HTTP endpoint returned non-200 status: {response.status_code}")
            if response.text:
                print_info(f"Response content: {response.text[:500]}...")
            return False
    except Exception as e:
        print_error(f"Error testing HTTP endpoint: {str(e)}")
        return False

def test_ws_test_endpoint(host, port):
    """Test the WebSocket test endpoint to check API functionality."""
    print_section("TESTING WEBSOCKET TEST ENDPOINT")
    
    try:
        url = f"http://{host}:{port}/ws-test"
        print_info(f"Requesting: {url}")
        
        response = requests.get(url, timeout=5)
        print_info(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            print_success("WebSocket test endpoint is working correctly")
            try:
                data = response.json()
                print_info(f"Response data: {json.dumps(data, indent=2)}")
                return True
            except:
                print_warning("Could not parse JSON response")
                print_info(f"Raw response: {response.text[:500]}...")
                return False
        else:
            print_warning(f"WebSocket test endpoint returned non-200 status: {response.status_code}")
            if response.text:
                print_info(f"Response content: {response.text[:500]}...")
            return False
    except Exception as e:
        print_error(f"Error testing WebSocket test endpoint: {str(e)}")
        return False

def test_websocket_handshake(host, port, path):
    """Test WebSocket handshake by constructing a custom HTTP request."""
    print_section("TESTING WEBSOCKET HANDSHAKE")
    
    try:
        url = f"http://{host}:{port}{path}"
        print_info(f"Testing WebSocket handshake for: {url}")
        
        # Create custom WebSocket handshake headers
        headers = {
            "Connection": "Upgrade",
            "Upgrade": "websocket",
            "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",  # Example key
            "Sec-WebSocket-Version": "13",
            "Sec-WebSocket-Extensions": "permessage-deflate",
            "Origin": f"http://{host}:{port}"
        }
        
        print_info(f"Handshake headers: {json.dumps(headers, indent=2)}")
        
        response = requests.get(url, headers=headers, timeout=5)
        print_info(f"Status code: {response.status_code}")
        print_info(f"Response headers: {json.dumps(dict(response.headers), indent=2)}")
        
        if response.status_code == 101:
            print_success("WebSocket handshake successful!")
            return True
        elif response.status_code == 403:
            print_error("WebSocket handshake rejected with 403 Forbidden")
            print_error("This suggests:")
            print_error("1. Authentication/authorization issue")
            print_error("2. CORS policy restriction")
            print_error("3. Server-side middleware rejecting the connection")
            
            # Try to get more information from the response
            if response.text:
                print_info(f"Response content: {response.text[:500]}...")
            return False
        else:
            print_warning(f"Unexpected status code: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error testing WebSocket handshake: {str(e)}")
        return False

def on_ws_open(ws):
    """WebSocket on_open callback."""
    print_success("WebSocket connection opened successfully!")
    print_info("Sending test message...")
    ws.send(json.dumps({"type": "diagnostic", "content": "Testing connection"}))

def on_ws_message(ws, message):
    """WebSocket on_message callback."""
    print_info(f"Received message: {message[:500]}...")
    # Close the connection after receiving a message
    ws.close()

def on_ws_error(ws, error):
    """WebSocket on_error callback."""
    print_error(f"WebSocket error: {str(error)}")
    
    # Additional diagnostic information
    if "403" in str(error):
        print_error("403 Forbidden - Access is denied")
        print_error("This could be caused by:")
        print_error("1. Server-side middleware rejecting the connection")
        print_error("2. Authentication/authorization issue")
        print_error("3. CORS policy restriction")
        print_error("4. Origin header validation")

def on_ws_close(ws, close_status_code, close_reason):
    """WebSocket on_close callback."""
    print_info(f"WebSocket connection closed: {close_status_code}, {close_reason}")

def test_websocket_client(host, port, path, headers=None):
    """Test full WebSocket connection using websocket-client library."""
    print_section("TESTING FULL WEBSOCKET CONNECTION")
    
    ws_url = f"ws://{host}:{port}{path}"
    print_info(f"Connecting to: {ws_url}")
    
    if headers is None:
        headers = {}
    
    # Optional - add custom headers to debug the issue
    base_headers = {
        "Origin": f"http://{host}:{port}",
        "User-Agent": "WebSocketDiagnosticsTool/1.0",
        "X-Debug": "true"
    }
    headers = {**base_headers, **headers}
    
    print_info(f"Using headers: {json.dumps(headers, indent=2)}")
    
    # Create WebSocket with debugging enabled
    websocket.enableTrace(True)
    
    ws = websocket.WebSocketApp(
        ws_url,
        header=headers,
        on_open=on_ws_open,
        on_message=on_ws_message,
        on_error=on_ws_error,
        on_close=on_ws_close
    )
    
    # Run the WebSocket connection for a short time
    ws.run_forever(dispatcher=None, ping_interval=0, ping_timeout=0, ping_payload="")
    
    return True

def analyze_various_header_combinations(host, port, path):
    """Test various header combinations to find what works."""
    print_section("TESTING DIFFERENT HEADER COMBINATIONS")
    
    # Test different header combinations
    test_cases = [
        {"description": "Default headers", "headers": {}},
        {"description": "No Origin header", "headers": {"Origin": ""}},
        {"description": "Different Origin", "headers": {"Origin": "http://localhost:8000"}},
        {"description": "With Sec-WebSocket-Key", "headers": {"Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="}},
        {"description": "With Connection and Upgrade", "headers": {
            "Connection": "Upgrade",
            "Upgrade": "websocket"
        }}
    ]
    
    for test_case in test_cases:
        print_info(f"\nTrying: {test_case['description']}")
        print_info(f"Headers: {json.dumps(test_case['headers'], indent=2)}")
        
        try:
            test_websocket_client(host, port, path, test_case['headers'])
        except Exception as e:
            print_error(f"Test failed: {str(e)}")
        
        # Wait before next test
        time.sleep(1)

def check_middleware_order():
    """Attempt to identify middleware ordering issues in the server code."""
    print_section("CHECKING MIDDLEWARE ORDER")
    
    try:
        # Try to locate the server.py file
        server_paths = [
            Path("gemini_chat/ui/server.py"),
            Path("ui/server.py"),
            Path("server.py")
        ]
        
        server_file = None
        for path in server_paths:
            if path.exists():
                server_file = path
                break
        
        if not server_file:
            print_warning("Could not locate server.py file")
            return
        
        print_info(f"Found server file: {server_file}")
        
        # Read the server file
        with open(server_file, "r") as f:
            content = f.read()
        
        # Check for middleware registration
        middleware_lines = []
        for i, line in enumerate(content.split("\n")):
            if "add_middleware" in line:
                middleware_lines.append((i+1, line.strip()))
        
        if not middleware_lines:
            print_warning("No middleware found in server.py")
            return
        
        print_info("Found middleware registrations:")
        for line_num, line in middleware_lines:
            print(f"  Line {line_num}: {line}")
        
        # Check for CORS middleware
        cors_middleware = any("CORSMiddleware" in line for _, line in middleware_lines)
        if cors_middleware:
            print_success("CORS middleware is registered")
        else:
            print_warning("CORS middleware not found")
        
        # Check for order issues
        if len(middleware_lines) > 1:
            print_info("Checking middleware order...")
            # If CORS is not first, it might be an issue
            if cors_middleware and "CORSMiddleware" not in middleware_lines[0][1]:
                print_warning("CORS middleware is not the first middleware")
                print_warning("This could cause WebSocket connection issues")
                print_info("Consider moving CORS middleware to be registered first")
    except Exception as e:
        print_error(f"Error checking middleware: {str(e)}")

def suggest_solutions():
    """Provide potential solutions based on common issues."""
    print_section("SUGGESTED SOLUTIONS")
    
    print_info("Based on common WebSocket 403 issues, here are potential solutions:")
    
    print(f"{Colors.BOLD}1. CORS Configuration:{Colors.ENDC}")
    print("   - Ensure CORS middleware is registered before other middleware")
    print("   - Make sure CORS allows WebSocket connections")
    print("   - Example fix:")
    print("     ```python")
    print("     from fastapi.middleware.cors import CORSMiddleware")
    print("     app.add_middleware(")
    print("         CORSMiddleware,")
    print("         allow_origins=[\"*\"],")
    print("         allow_credentials=True,")
    print("         allow_methods=[\"*\"],")
    print("         allow_headers=[\"*\"],")
    print("     )")
    print("     ```")
    
    print(f"\n{Colors.BOLD}2. Authentication/Authorization Middleware:{Colors.ENDC}")
    print("   - Check if any auth middleware is blocking WebSocket connections")
    print("   - Add a bypass for WebSocket connections in auth middleware")
    
    print(f"\n{Colors.BOLD}3. WebSocket Route Configuration:{Colors.ENDC}")
    print("   - Ensure the WebSocket route is correctly defined")
    print("   - Example:")
    print("     ```python")
    print("     @app.websocket(\"/ws\")")
    print("     async def websocket_endpoint(websocket: WebSocket):")
    print("         await websocket.accept()")
    print("         # Rest of the handler")
    print("     ```")
    
    print(f"\n{Colors.BOLD}4. Uvicorn Configuration:{Colors.ENDC}")
    print("   - Try running Uvicorn with explicit WebSocket options:")
    print("     ```python")
    print("     uvicorn.run(")
    print("         app,")
    print("         host=\"127.0.0.1\",")
    print("         port=8000,")
    print("         ws=\"auto\",  # Explicitly enable WebSockets")
    print("         ws_max_size=16777216,  # Increase max message size")
    print("     )")
    print("     ```")
    
    print(f"\n{Colors.BOLD}5. Debug Decorator Fix:{Colors.ENDC}")
    print("   - Add a decorator to print connection details before rejection:")
    print("     ```python")
    print("     # Add this import")
    print("     from starlette.websockets import WebSocketDisconnect")
    print("     from starlette.middleware.base import BaseHTTPMiddleware")
    print("     ")
    print("     class WebSocketDebugMiddleware(BaseHTTPMiddleware):")
    print("         async def dispatch(self, request, call_next):")
    print("             print(f\"Request path: {request.url.path}\")")
    print("             print(f\"Request headers: {request.headers}\")")
    print("             return await call_next(request)")
    print("     ")
    print("     app.add_middleware(WebSocketDebugMiddleware)")
    print("     ```")
    
    print(f"\n{Colors.BOLD}6. Origin Verification Fix:{Colors.ENDC}")
    print("   - If your server is checking the Origin header, try:")
    print("     ```python")
    print("     @app.websocket(\"/ws\")")
    print("     async def websocket_endpoint(websocket: WebSocket):")
    print("         # Allow any origin for WebSocket connections")
    print("         origin = websocket.headers.get(\"origin\", \"\")")
    print("         print(f\"WebSocket request from origin: {origin}\")")
    print("         await websocket.accept()")
    print("         # Rest of the handler")
    print("     ```")
    
    print(f"\n{Colors.BOLD}7. FastAPI Version:{Colors.ENDC}")
    print("   - Check FastAPI and Uvicorn versions")
    print("   - Some versions have known WebSocket issues")
    print("   - Try upgrading both packages:")
    print("     ```")
    print("     pip install --upgrade fastapi uvicorn")
    print("     ```")

def run_diagnostics(host, port, path):
    """Run a complete set of diagnostics."""
    print_section("GEMINI CHAT WEBSOCKET DIAGNOSTICS")
    print_info(f"Testing server: {host}:{port}")
    print_info(f"WebSocket path: {path}")
    
    # Check if server is available
    if not check_server_availability(host, port):
        print_error("Server is not available. Diagnostics cannot continue.")
        return
    
    # Test HTTP endpoint
    test_http_endpoint(host, port)
    
    # Test WebSocket test endpoint
    test_ws_test_endpoint(host, port)
    
    # Test WebSocket handshake
    test_websocket_handshake(host, port, path)
    
    # Test full WebSocket connection
    test_websocket_client(host, port, path)
    
    # Test with different headers
    analyze_various_header_combinations(host, port, path)
    
    # Check middleware order
    check_middleware_order()
    
    # Suggest solutions
    suggest_solutions()

def main():
    """Main function to run the diagnostic tool."""
    parser = argparse.ArgumentParser(description="WebSocket Connection Troubleshooter for Gemini Chat")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--path", default="/ws", help="WebSocket path (default: /ws)")
    
    args = parser.parse_args()
    
    try:
        run_diagnostics(args.host, args.port, args.path)
    except KeyboardInterrupt:
        print_info("\nDiagnostics interrupted by user")
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
