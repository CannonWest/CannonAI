#!/usr/bin/env python3
"""
CannonAI GUI Server - Flask implementation for the web interface

This module provides the Flask server implementation for the CannonAI Web GUI.
It handles HTTP requests, Server-Sent Events for streaming, and serves the Bootstrap-based UI.
System instructions are now managed via conversation metadata.
"""

import os
import sys
import json
import asyncio
import logging
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime
from threading import Thread
import traceback

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS


# Project imports
# Ensure these paths are correct relative to where this script is run from, or use absolute imports if packaged.
# Assuming cannonai is the root package for imports like: from cannonai.async_client import AsyncClient
try:
    from async_client import AsyncClient
    from command_handler import CommandHandler
    from config import Config
    from client_manager import ClientManager
    from providers import ProviderError
    from gui import api_handlers as gui_api_handlers_module  # Import the module
except ImportError:  # Fallback for direct execution or different project structure
    sys.path.append(str(Path(__file__).resolve().parent.parent))  # Add cannonai directory to path
    from async_client import AsyncClient
    from command_handler import CommandHandler
    from config import Config
    from client_manager import ClientManager
    from providers import ProviderError
    from gui import api_handlers as gui_api_handlers_module

# Type hint for APIHandlers instance
if TYPE_CHECKING:
    from gui.api_handlers import APIHandlers

logging.basicConfig(
    level=logging.DEBUG,  # Consider INFO for production
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cannonai.gui.server")

# Global variables for the GUI's client instance and event loop management
gui_chat_client: Optional[AsyncClient] = None
gui_command_handler: Optional[CommandHandler] = None  # Retained if some commands are still relevant
gui_event_loop: Optional[asyncio.AbstractEventLoop] = None
gui_loop_thread: Optional[Thread] = None
gui_api_handlers_instance: Optional['APIHandlers'] = None  # Instance of APIHandlers
main_config_for_gui: Optional[Config] = None  # To store the loaded application config


def run_async_loop_for_gui(loop: asyncio.AbstractEventLoop) -> None:
    """Runs the asyncio event loop in a separate thread."""
    logger.info("Starting asyncio event loop for GUI client in a new thread.")
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("GUI Async event loop interrupted by KeyboardInterrupt.")
    finally:
        logger.info("GUI Async event loop stopping...")
        # Gracefully stop and close the loop
        if not loop.is_closed():
            # Schedule stop() to be called from the loop's thread
            loop.call_soon_threadsafe(loop.stop)
            # Wait for loop to fully stop before closing (optional, depends on cleanup needs)
            # For simple cases, loop.close() after stop might be sufficient if run_forever exited.
            # If loop.close() is called from another thread while loop is running/stopping, it can error.
            # A more robust shutdown might involve awaiting tasks or using loop.shutdown_asyncgens().
        logger.info("GUI Async event loop has stopped.")


async def initialize_gui_client_async(app_config: Config, cli_args: Optional[Any]) -> None:
    """Initializes the AsyncClient, CommandHandler, and APIHandlers for the GUI."""
    global gui_chat_client, gui_command_handler, gui_api_handlers_instance, gui_event_loop

    # Dynamically import APIHandlers class here to ensure module context is set up
    from gui.api_handlers import APIHandlers

    logger.info("Initializing AI client and API handlers for GUI...")
    try:
        # Resolve effective generation parameters and streaming preference
        # These would typically come from combining global config and CLI arguments.
        # For simplicity, assuming cli_args (if provided) has these resolved.
        # If not, cannonai.py (main entry) should resolve them before calling start_gui_server.

        # Default effective params if not available from cli_args
        effective_params = app_config.get("generation_params", {}).copy()
        if cli_args and hasattr(cli_args, 'effective_gen_params') and cli_args.effective_gen_params is not None:
            effective_params.update(cli_args.effective_gen_params)

        effective_streaming = app_config.get("use_streaming", False)
        if cli_args and hasattr(cli_args, 'effective_use_streaming') and cli_args.effective_use_streaming is not None:
            effective_streaming = cli_args.effective_use_streaming

        # Create the AI client instance
        gui_chat_client = ClientManager.create_client(
            config=app_config,  # Pass the main Config object
            provider_name_override=cli_args.provider if cli_args and hasattr(cli_args, 'provider') else None,
            model_override=cli_args.model if cli_args and hasattr(cli_args, 'model') else None,
            conversations_dir_override=Path(cli_args.conversations_dir) if cli_args and hasattr(cli_args, 'conversations_dir') and cli_args.conversations_dir else None,
            params_override=effective_params,  # Pass resolved params
            use_streaming_override=effective_streaming  # Pass resolved streaming pref
        )

        if not await gui_chat_client.initialize_client():  # This initializes the provider
            logger.error("Failed to initialize AI client for GUI. Provider did not initialize.")
            gui_chat_client = None  # Ensure it's None if init failed
            return

        gui_command_handler = CommandHandler(gui_chat_client)  # CommandHandler might still be used for some CLI-like actions
        gui_chat_client.is_web_ui = True  # Mark client as being used by Web UI

        if gui_event_loop is None:  # Should be set by initialize_async_components_for_gui
            logger.critical("GUI Event loop is None during APIHandlers initialization! This is a critical error.")
            # Attempt to get current loop as a last resort, though this indicates a flow issue
            try:
                gui_event_loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.critical("No running event loop available. API Handlers cannot be initialized.")
                return  # Cannot proceed

        # Initialize API Handlers instance
        gui_api_handlers_instance = APIHandlers(gui_chat_client, gui_command_handler, gui_event_loop)

        # Pass the main application config to the API Handlers module (if it expects it globally)
        # or to the instance if it has a config attribute.
        gui_api_handlers_module.main_config = app_config  # Set on the module
        # If APIHandlers class itself takes config: gui_api_handlers_instance.main_config = app_config

        logger.info(f"GUI AI Client and API Handlers initialized. Provider: {gui_chat_client.provider.provider_name}, Model: {gui_chat_client.current_model_name}")

    except (ValueError, ProviderError) as e:
        logger.error(f"Configuration or Provider error creating AI client for GUI: {e}", exc_info=True)
        gui_chat_client = None  # Ensure client is None on failure
    except Exception as e:
        logger.error(f"Unexpected error initializing AI client/API Handlers for GUI: {e}", exc_info=True)
        gui_chat_client = None  # Ensure client is None on failure


def initialize_async_components_for_gui(app_config: Config, cli_args: Optional[Any]) -> None:
    """Sets up the asyncio event loop and schedules the client initialization."""
    global gui_event_loop, gui_loop_thread, main_config_for_gui

    main_config_for_gui = app_config  # Store config globally for access by API handlers if needed

    if gui_event_loop is None or gui_event_loop.is_closed():
        gui_event_loop = asyncio.new_event_loop()
        logger.info("New asyncio event loop created for GUI components.")

    if gui_loop_thread is None or not gui_loop_thread.is_alive():
        gui_loop_thread = Thread(target=run_async_loop_for_gui, args=(gui_event_loop,), daemon=True)
        gui_loop_thread.start()
        logger.info("Asyncio event loop thread started for GUI.")

    # Schedule the asynchronous initialization of the client and API handlers
    if gui_event_loop and gui_event_loop.is_running():
        # Ensure cli_args has effective_gen_params and effective_use_streaming if they were resolved in cannonai.py
        # These are needed by initialize_gui_client_async
        future = asyncio.run_coroutine_threadsafe(initialize_gui_client_async(app_config, cli_args), gui_event_loop)
        try:
            future.result(timeout=15)  # Wait for initialization to complete or timeout
            logger.info("Async initialization of GUI client components scheduled and completed.")
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for async initialization of GUI client components.")
        except Exception as e:
            logger.error(f"Exception during async initialization scheduling/execution: {e}", exc_info=True)
    else:
        logger.critical("GUI event loop not running or not available. Cannot schedule client initialization.")


# --- Flask App Setup ---
flask_app = Flask(__name__, template_folder='templates', static_folder='static')
flask_app.secret_key = os.urandom(24)  # For session management, if used
CORS(flask_app)  # Enable CORS for all routes


# --- Flask Route Definitions ---
@flask_app.before_request
def ensure_api_handlers_ready_for_request():
    """Check if API handlers are ready before processing API requests."""
    # Exclude static file requests from this check
    if request.endpoint and 'static' not in request.endpoint:
        if gui_api_handlers_instance is None or gui_chat_client is None:
            logger.warning(f"API request to '{request.endpoint}' but API handlers or client not fully initialized.")
            # This is a critical state. Ideally, initialization completes before server accepts requests.
            # For now, we'll let routes return 503 if handlers are None.
            # A more robust solution might involve a startup probe or readiness check.
            # Consider if re-initialization attempt here is safe or desired.
            # For now, rely on initial setup.


@flask_app.route('/')
def index_route():
    """Serves the main index.html page for the GUI."""
    logger.debug("Serving index.html")
    return render_template('index.html')


@flask_app.route('/api/status', methods=['GET'])
def get_status_api_route():
    """API endpoint to get the current status of the client and conversation."""
    if not gui_api_handlers_instance:
        return jsonify({'connected': False, 'error': 'GUI API service not ready'}), 503
    return jsonify(gui_api_handlers_instance.get_status())


@flask_app.route('/api/models', methods=['GET'])
def get_models_api_route():
    """API endpoint to list available AI models from the current provider."""
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready', 'models': []}), 503
    result = gui_api_handlers_instance.get_models()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/send', methods=['POST'])
def send_message_api_route():
    """API endpoint for sending a non-streaming message."""
    if not gui_api_handlers_instance or not gui_chat_client:
        return jsonify({'error': 'GUI API service or client not ready'}), 503

    data = request.get_json()
    message_content = data.get('message', '')
    if not message_content:
        return jsonify({'error': 'No message content provided'}), 400

    try:
        # GUI flow: client.add_user_message is called first by JS (via API or directly if state managed differently)
        # For this API, let's assume the JS side might not have added it yet, or we want to ensure it's added here.
        # However, client.add_user_message is synchronous.
        # The API handler's send_message method expects current_user_message_id to be set.
        gui_chat_client.add_user_message(message_content)  # This sets current_user_message_id

        result = gui_api_handlers_instance.send_message(message_content)  # Pass content for logging/context
        return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)
    except Exception as e:
        logger.error(f"Error in /api/send route: {e}", exc_info=True)
        return jsonify({'error': f'Server error processing send request: {str(e)}'}), 500


@flask_app.route('/api/stream', methods=['POST'])
def stream_message_api_route():
    """API endpoint for sending a message and receiving a streaming response via SSE."""
    logger.debug("GUI /api/stream endpoint hit")
    if not gui_api_handlers_instance or not gui_chat_client or not gui_event_loop:
        logger.error("GUI API service, client, or event loop not ready for streaming.")

        def error_stream_gen(): yield f"data: {json.dumps({'error': 'Server not ready for streaming.'})}\n\n"

        return Response(stream_with_context(error_stream_gen()), mimetype='text/event-stream')

    data = request.get_json()
    message_content = data.get('message', '')
    if not message_content:
        logger.warning("No message content provided for streaming via /api/stream.")

        def error_no_msg_gen(): yield f"data: {json.dumps({'error': 'No message provided for streaming.'})}\n\n"

        return Response(stream_with_context(error_no_msg_gen()), mimetype='text/event-stream')

    logger.info(f"Streaming request received for message: '{message_content[:50]}...'")

    try:
        # Add user message to conversation data. This sets client.current_user_message_id.
        gui_chat_client.add_user_message(message_content)
    except Exception as e_add_user:
        logger.error(f"Error adding user message before streaming: {e_add_user}", exc_info=True)

        def error_add_user_gen():
            yield f"data: {json.dumps({'error': f'Failed to process user message for stream: {e_add_user}'})}\n\n"

        return Response(stream_with_context(error_add_user_gen()), mimetype='text/event-stream')

    # SSE Generator
    def generate_sse_from_async():
        # This generator runs in a Flask thread. We need to interact with the asyncio loop.
        queue = asyncio.Queue()

        async def producer():  # Runs in the asyncio loop
            try:
                # gui_api_handlers_instance.stream_message itself is an async generator
                async for item in gui_api_handlers_instance.stream_message(message_content):
                    await queue.put(item)
            except Exception as e_prod:
                logger.error(f"Error in SSE producer (stream_message async_gen): {e_prod}", exc_info=True)
                await queue.put({"error": f"Streaming producer error: {str(e_prod)}"})
            finally:
                await queue.put(None)  # Signal end of production

        # Schedule the producer in the asyncio event loop
        asyncio.run_coroutine_threadsafe(producer(), gui_event_loop)

        # Consumer part (runs in Flask thread, gets items from queue)
        while True:
            try:
                item_future = asyncio.run_coroutine_threadsafe(queue.get(), gui_event_loop)
                item = item_future.result(timeout=90)  # Generous timeout for queue get

                if item is None:  # End of stream signal from producer
                    logger.debug("SSE stream generation complete (None received from queue).")
                    break

                yield f"data: {json.dumps(item)}\n\n"  # Send SSE event

                if item.get("error") or item.get("done"):  # If error or done, terminate stream
                    logger.info(f"SSE stream generation ended by event: {item}")
                    break
            except asyncio.TimeoutError:
                logger.warning("SSE queue get timed out waiting for item from producer.")
                yield f"data: {json.dumps({'error': 'Stream timeout from server.'})}\n\n"
                break
            except Exception as e_cons:
                logger.error(f"Error in SSE consumer (sync generator part): {e_cons}", exc_info=True)
                yield f"data: {json.dumps({'error': f'Streaming consumer error: {str(e_cons)}'})}\n\n"
                break

    return Response(stream_with_context(generate_sse_from_async()), mimetype='text/event-stream')


@flask_app.route('/api/conversations', methods=['GET'])
def get_conversations_api_route():
    """API endpoint to list all saved conversations."""
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready', 'conversations': []}), 503
    result = gui_api_handlers_instance.get_conversations()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/conversation/duplicate/<conversation_id>', methods=['POST'])
def duplicate_conversation_api_route(conversation_id: str):
    """API endpoint to duplicate a conversation."""
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json();
    new_title = data.get('new_title')
    if not new_title: return jsonify({'error': 'New title not provided for duplication'}), 400
    result = gui_api_handlers_instance.duplicate_conversation(conversation_id, new_title)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/conversation/rename/<conversation_id>', methods=['POST'])
def rename_conversation_api_route(conversation_id: str):
    """API endpoint to rename a conversation."""
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json();
    new_title = data.get('new_title')
    if not new_title: return jsonify({'error': 'New title not provided for renaming'}), 400
    result = gui_api_handlers_instance.rename_conversation(conversation_id, new_title)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/conversation/delete/<conversation_id>', methods=['DELETE'])
def delete_conversation_api_route(conversation_id: str):
    """API endpoint to delete a conversation."""
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    result = gui_api_handlers_instance.delete_conversation(conversation_id)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/settings', methods=['POST'])
def update_settings_api_route():
    """API endpoint to update client/conversation settings (model, params, session streaming)."""
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json()
    # System instruction is handled by a separate endpoint now
    result = gui_api_handlers_instance.update_settings(
        provider=data.get('provider'),  # Note: provider change is complex, mostly logs for now
        model=data.get('model'),
        streaming=data.get('streaming'),  # Client's session default streaming
        params=data.get('params')
    )
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/conversation/<conversation_id>/system_instruction', methods=['POST'])
def update_conversation_system_instruction_api_route(conversation_id: str):
    """API endpoint to update the system instruction for a specific conversation."""
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json()
    new_instruction = data.get('system_instruction')
    if new_instruction is None:  # Allow empty string, but not missing key
        return jsonify({'error': 'system_instruction field missing or null'}), 400

    result = gui_api_handlers_instance.update_conversation_system_instruction(conversation_id, new_instruction)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/command', methods=['POST'])
def execute_command_api_route():
    """API endpoint to execute text-based commands (e.g., /new, /load)."""
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json()
    command_str = data.get('command', '')
    if not command_str:
        return jsonify({'error': 'No command string provided'}), 400
    result = gui_api_handlers_instance.execute_command(command_str)  # This now maps to specific API handler methods
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/retry/<message_id>', methods=['POST'])
def retry_message_api_route(message_id: str):
    """API endpoint to retry generating an AI response for a previous user message."""
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    result = gui_api_handlers_instance.retry_message(message_id)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/message/<message_id>', methods=['GET'])
def get_message_info_api_route(message_id: str):
    """API endpoint to get detailed info about a message and its siblings."""
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    result = gui_api_handlers_instance.get_message_info(message_id)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/navigate', methods=['POST'])
def navigate_sibling_api_route():
    """API endpoint to navigate to a sibling (alternative) AI response."""
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json()
    message_id = data.get('message_id')
    direction = data.get('direction', 'next')  # Default to 'next'
    if not message_id: return jsonify({'error': 'No message_id provided for navigation'}), 400
    result = gui_api_handlers_instance.navigate_sibling(message_id, direction)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/tree', methods=['GET'])
def get_conversation_tree_api_route():
    """API endpoint to get the full message tree structure for visualization."""
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    result = gui_api_handlers_instance.get_conversation_tree()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


def start_gui_server(app_config: Config, host: str = "127.0.0.1", port: int = 8080, cli_args: Optional[Any] = None) -> None:
    """Initializes async components and starts the Flask GUI server."""
    logger.info("\n" + "=" * 60 + f"\n{Colors.HEADER}{Colors.BOLD}STARTING CannonAI GUI (Flask + Bootstrap){Colors.ENDC}\n" + "=" * 60 + "\n")

    # Initialize asyncio components (event loop, client, API handlers)
    initialize_async_components_for_gui(app_config, cli_args)

    # Wait a bit for async components to initialize, especially the client and API handlers
    import time
    max_wait_init_secs = 10
    wait_interval_secs = 0.5
    elapsed_wait_secs = 0
    while (gui_api_handlers_instance is None or gui_chat_client is None or not gui_chat_client.provider.is_initialized) and elapsed_wait_secs < max_wait_init_secs:
        logger.info(f"Waiting for GUI client and API handlers to initialize... ({elapsed_wait_secs:.1f}s / {max_wait_init_secs}s)")
        time.sleep(wait_interval_secs)
        elapsed_wait_secs += wait_interval_secs

    if gui_api_handlers_instance is None or gui_chat_client is None:
        logger.critical("GUI API Handlers or AI Client did NOT initialize in time. Flask server may not function correctly or at all.")
    elif not gui_chat_client.provider.is_initialized:
        logger.error(f"GUI AI Client's provider ({gui_chat_client.provider.provider_name}) failed to initialize. Flask server might not function correctly.")
    else:
        logger.info("GUI AI Client and API Handlers appear initialized. Proceeding to start Flask server.")

    # Open browser only if not in a reloader process (Werkzeug specific)
    if not (os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
        try:
            url_to_open = f"http://{host}:{port}"
            webbrowser.open(url_to_open)
            logger.info(f"Attempted to open web browser to: {url_to_open}")
        except Exception as e_wb:
            logger.warning(f"Could not automatically open web browser: {e_wb}")

    logger.info(f"Flask server starting at http://{host}:{port}")
    logger.info("Press CTRL+C to quit.")

    # Recommended: Use a production-ready WSGI server (like Gunicorn or Waitress) for deployment.
    # flask_app.run() is suitable for development.
    # threaded=True can handle multiple requests concurrently but isn't as robust as a proper WSGI server.
    # use_reloader=False is important when managing our own async loop thread.
    flask_app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    print(f"{Colors.WARNING}WARNING: Running server.py directly. For full application, use 'python cannonai/cannonai.py --gui'{Colors.ENDC}")
    # Basic setup for direct run (for testing/dev of server.py itself)
    test_config = Config(quiet=True)  # Load default config quietly


    # Create dummy cli_args for direct run, as cannonai.py would normally provide these.
    class DummyCLIArgs:
        provider = None;
        model = None;
        conversations_dir = None
        effective_gen_params = test_config.get("generation_params", {}).copy()
        effective_use_streaming = test_config.get("use_streaming", False)
        # Add other args if initialize_gui_client_async expects them
        temperature = None;
        max_tokens = None;
        top_p = None;
        top_k = None;
        use_streaming_arg = None;
        # These are normally resolved in cannonai.py main()


    start_gui_server(test_config, cli_args=DummyCLIArgs())
