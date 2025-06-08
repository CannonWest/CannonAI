#!/usr/bin/env python3
"""
CannonAI GUI Server - Flask application setup and coordination

This module sets up the Flask application and coordinates all GUI components.
It uses modular components for routes, streaming, and initialization.
"""

import os
import sys
import logging
import webbrowser
from pathlib import Path
from typing import Optional, Any
from flask import Flask, render_template
from flask_cors import CORS

# Add project root to path if needed
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

# Import our modular components
from .routes import gui_routes, inject_dependencies
from .init_helpers import get_component_manager
from config import Config
from base_client import Colors

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cannonai.gui.server")

# Create Flask app
print("[Server] Creating Flask application")
flask_app = Flask(__name__, template_folder='templates', static_folder='static')
flask_app.secret_key = os.urandom(24)  # For session management, CSRF, etc.
CORS(flask_app)  # Enable CORS for all routes

# Register the routes blueprint
print("[Server] Registering routes blueprint")
flask_app.register_blueprint(gui_routes)

# Component manager instance
component_manager = get_component_manager()


@flask_app.route('/')
def index_route():
    """Serve the main HTML page."""
    print("[Server] Serving index.html")
    logger.debug("Serving index.html")
    return render_template('index.html')


@flask_app.before_request
def ensure_api_handlers_ready():
    """Check if API handlers are ready before processing requests."""
    from flask import request
    
    # Skip check for static files and index
    if request.endpoint and 'static' not in request.endpoint and request.endpoint != 'index_route':
        if not component_manager.is_ready():
            status = component_manager.get_status()
            logger.warning(f"API request to '{request.endpoint}' but components not ready: {status}")


def start_gui_server(
    app_config: Config,
    host: str = "127.0.0.1",
    port: int = 8080,
    cli_args: Optional[Any] = None
) -> None:
    """
    Starts the GUI server with all components.
    
    Args:
        app_config: The main application configuration
        host: Host to bind the server to
        port: Port to run the server on
        cli_args: Command line arguments from main application
    """
    print("\n" + "=" * 60)
    print(f"{Colors.HEADER}{Colors.BOLD}STARTING CannonAI GUI (Flask + Bootstrap){Colors.ENDC}")
    print("=" * 60 + "\n")
    
    logger.info(f"Starting CannonAI GUI Server on {host}:{port}")
    
    # Initialize async components
    print("[Server] Initializing async components...")
    component_manager.initialize_async_components(app_config, cli_args)
    
    # Wait for initialization
    print("[Server] Waiting for components to initialize...")
    if not component_manager.wait_for_initialization(timeout_seconds=15.0):
        logger.critical("GUI components did NOT initialize in time. Server may not function correctly.")
        print(f"{Colors.FAIL}[Server] Failed to initialize GUI components!{Colors.ENDC}")
        
        # Show detailed status
        status = component_manager.get_status()
        print(f"[Server] Initialization status: {status}")
        
        if status.get('error'):
            print(f"{Colors.FAIL}[Server] Initialization error: {status['error']}{Colors.ENDC}")
    else:
        print(f"{Colors.GREEN}[Server] GUI components initialized successfully{Colors.ENDC}")
        logger.info("GUI AI Client and API Handlers initialized successfully")
        
        # Show provider info
        if component_manager.chat_client:
            provider_name = component_manager.chat_client.provider.provider_name
            model_name = component_manager.chat_client.current_model_name
            print(f"{Colors.CYAN}[Server] Active Provider: {provider_name}, Model: {model_name}{Colors.ENDC}")
    
    # Inject dependencies into routes module
    if component_manager.is_ready():
        print("[Server] Injecting dependencies into routes module")
        inject_dependencies(
            api_handlers=component_manager.api_handlers,
            chat_client=component_manager.chat_client,
            event_loop=component_manager.event_loop,
            main_config=app_config
        )
        print(f"{Colors.GREEN}[Server] Dependencies injected successfully{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}[Server] Warning: Starting server without all components ready{Colors.ENDC}")
        logger.warning("Starting Flask server without all components initialized")
    
    # Open browser (only if not in Werkzeug reloader process)
    if not os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        try:
            print(f"[Server] Opening web browser to: http://{host}:{port}")
            webbrowser.open(f"http://{host}:{port}")
            logger.info(f"Attempted to open web browser to: http://{host}:{port}")
        except Exception as e:
            print(f"[Server] Could not open web browser: {e}")
            logger.warning(f"Could not automatically open web browser: {e}")
    
    # Start Flask server
    print(f"\n{Colors.GREEN}Flask server starting at http://{host}:{port}{Colors.ENDC}")
    print(f"{Colors.CYAN}Press CTRL+C to quit{Colors.ENDC}\n")
    
    try:
        flask_app.run(
            host=host,
            port=port,
            debug=False,  # Set to True for development
            use_reloader=False,  # Disable reloader to avoid double initialization
            threaded=True  # Enable threading for better responsiveness
        )
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}[Server] Shutting down...{Colors.ENDC}")
        logger.info("Server shutdown requested")
    finally:
        # Cleanup
        print("[Server] Cleaning up resources")
        component_manager.cleanup()
        print(f"{Colors.GREEN}[Server] Shutdown complete{Colors.ENDC}")


# For direct execution (testing)
if __name__ == "__main__":
    print(f"{Colors.WARNING}WARNING: Running server.py directly. For full application, use 'python cannonai/cannonai.py --gui'{Colors.ENDC}")
    
    # Create a test configuration
    test_config = Config(quiet=False)
    
    # Create dummy CLI args for testing
    class DummyCLIArgs:
        """Dummy CLI arguments for direct server testing."""
        provider = None
        model = None
        conversations_dir = None
        temperature = None
        max_tokens = None
        top_p = None
        top_k = None
        use_streaming_arg = None
    
    dummy_args = DummyCLIArgs()
    
    # Start the server
    try:
        start_gui_server(test_config, cli_args=dummy_args)
    except Exception as e:
        print(f"{Colors.FAIL}[Server] Fatal error: {e}{Colors.ENDC}")
        logger.error("Fatal error during server startup", exc_info=True)
