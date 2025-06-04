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
from typing import Dict, Any, Optional, TYPE_CHECKING, AsyncGenerator # Added AsyncGenerator
from datetime import datetime
from threading import Thread
import traceback

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS

# Project imports
try:
    from async_client import AsyncClient
    from command_handler import CommandHandler
    from config import Config
    from client_manager import ClientManager
    from providers import ProviderError
    from gui import api_handlers as gui_api_handlers_module # Keep as module
    from base_client import Colors
except ImportError:
    # Ensure the project root is in the Python path for direct execution or when module isn't installed
    sys.path.append(str(Path(__file__).resolve().parent.parent.parent)) # Go up two levels for cannonai project root
    from async_client import AsyncClient
    from command_handler import CommandHandler
    from config import Config
    from client_manager import ClientManager
    from providers import ProviderError
    from gui import api_handlers as gui_api_handlers_module # Keep as module
    from base_client import Colors


if TYPE_CHECKING:
    from gui.api_handlers import APIHandlers # For type hinting only

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cannonai.gui.server")

gui_chat_client: Optional[AsyncClient] = None
gui_command_handler: Optional[CommandHandler] = None
gui_event_loop: Optional[asyncio.AbstractEventLoop] = None
gui_loop_thread: Optional[Thread] = None
gui_api_handlers_instance: Optional['APIHandlers'] = None # Type hint using string
main_config_for_gui: Optional[Config] = None


def run_async_loop_for_gui(loop: asyncio.AbstractEventLoop) -> None:
    logger.info("Starting asyncio event loop for GUI client in a new thread.")
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("GUI Async event loop interrupted by KeyboardInterrupt.")
    finally:
        logger.info("GUI Async event loop stopping...")
        # Ensure all tasks are cancelled before stopping the loop
        if not loop.is_closed():
            # Gather all tasks:
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            # Wait for tasks to cancel
            # loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True)) # This can block if run_forever was interrupted
            loop.call_soon_threadsafe(loop.stop) # Request stop
        logger.info("GUI Async event loop has stopped.")


async def initialize_gui_client_async(app_config: Config, cli_args: Optional[Any]) -> None:
    global gui_chat_client, gui_command_handler, gui_api_handlers_instance, gui_event_loop
    from gui.api_handlers import APIHandlers # Import here to ensure module context

    logger.info("Initializing AI client and API handlers for GUI...")
    try:
        effective_params = app_config.get("generation_params", {}).copy()
        if cli_args and hasattr(cli_args, 'effective_gen_params') and cli_args.effective_gen_params is not None: # Check cli_args exists
            effective_params.update(cli_args.effective_gen_params)

        effective_streaming = app_config.get("use_streaming", False)
        if cli_args and hasattr(cli_args, 'effective_use_streaming') and cli_args.effective_use_streaming is not None: # Check cli_args exists
            effective_streaming = cli_args.effective_use_streaming

        gui_chat_client = ClientManager.create_client(
            config=app_config,
            provider_name_override=cli_args.provider if cli_args and hasattr(cli_args, 'provider') else None,
            model_override=cli_args.model if cli_args and hasattr(cli_args, 'model') else None,
            conversations_dir_override=Path(cli_args.conversations_dir) if cli_args and hasattr(cli_args, 'conversations_dir') and cli_args.conversations_dir else None,
            params_override=effective_params,
            use_streaming_override=effective_streaming
        )

        if not await gui_chat_client.initialize_client():
            logger.error("Failed to initialize AI client for GUI. Provider did not initialize.")
            gui_chat_client = None # Ensure it's None on failure
            return

        gui_command_handler = CommandHandler(gui_chat_client)
        gui_chat_client.is_web_ui = True # Mark client as being used by web UI

        if gui_event_loop is None: # Should have been set by initialize_async_components_for_gui
            logger.critical("GUI Event loop is None during APIHandlers initialization!")
            # Attempt to get the current running loop if possible, though this indicates a flow issue
            try:
                gui_event_loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.critical("No running event loop available. API Handlers cannot be initialized.")
                return # Cannot proceed

        gui_api_handlers_instance = APIHandlers(gui_chat_client, gui_command_handler, gui_event_loop)
        gui_api_handlers_module.main_config = app_config # Make config available to api_handlers module
        logger.info(f"GUI AI Client and API Handlers initialized. Provider: {gui_chat_client.provider.provider_name}, Model: {gui_chat_client.current_model_name}")

    except (ValueError, ProviderError) as e:
        logger.error(f"Configuration or Provider error creating AI client for GUI: {e}", exc_info=True)
        gui_chat_client = None # Ensure it's None on failure
    except Exception as e:
        logger.error(f"Unexpected error initializing AI client/API Handlers for GUI: {e}", exc_info=True)
        gui_chat_client = None # Ensure it's None on failure


def initialize_async_components_for_gui(app_config: Config, cli_args: Optional[Any]) -> None:
    global gui_event_loop, gui_loop_thread, main_config_for_gui
    main_config_for_gui = app_config # Store the main config

    if gui_event_loop is None or gui_event_loop.is_closed():
        gui_event_loop = asyncio.new_event_loop()
        logger.info("New asyncio event loop created for GUI components.")

    if gui_loop_thread is None or not gui_loop_thread.is_alive():
        gui_loop_thread = Thread(target=run_async_loop_for_gui, args=(gui_event_loop,), daemon=True)
        gui_loop_thread.start()
        logger.info("Asyncio event loop thread started for GUI.")

    # Schedule the client initialization on the running loop
    if gui_event_loop and gui_event_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(initialize_gui_client_async(app_config, cli_args), gui_event_loop)
        try:
            future.result(timeout=15) # Wait for initialization to complete
            logger.info("Async initialization of GUI client components scheduled and completed.")
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for async initialization of GUI client components.")
        except Exception as e:
            logger.error(f"Exception during async initialization scheduling/execution: {e}", exc_info=True)
    else:
        logger.critical("GUI event loop not running or not available. Cannot schedule client initialization.")


flask_app = Flask(__name__, template_folder='templates', static_folder='static')
flask_app.secret_key = os.urandom(24) # For session management, CSRF, etc.
CORS(flask_app) # Enable CORS for all routes


@flask_app.before_request
def ensure_api_handlers_ready_for_request():
    # This is a good place for a quick check, but actual readiness is more complex
    # due to async initialization. The API routes themselves should check.
    if request.endpoint and 'static' not in request.endpoint: # Don't check for static files
        if gui_api_handlers_instance is None or gui_chat_client is None:
            logger.warning(f"API request to '{request.endpoint}' but API handlers or client not fully initialized.")
            # Could return a 503 here, but might be too aggressive if it's a timing issue.


@flask_app.route('/')
def index_route():
    logger.debug("Serving index.html")
    return render_template('index.html')


@flask_app.route('/api/status', methods=['GET'])
def get_status_api_route():
    if not gui_api_handlers_instance:
        return jsonify({'connected': False, 'error': 'GUI API service not ready'}), 503
    return jsonify(gui_api_handlers_instance.get_status())


@flask_app.route('/api/models', methods=['GET'])
def get_models_api_route():
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready', 'models': []}), 503
    result = gui_api_handlers_instance.get_models()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/send', methods=['POST'])
def send_message_api_route():
    if not gui_api_handlers_instance or not gui_chat_client:
        return jsonify({'error': 'GUI API service or client not ready'}), 503
    data = request.get_json()
    message_content = data.get('message', '')
    attachments = data.get('attachments') # Get attachments from payload

    if not message_content and not attachments: # Allow send if attachments present
        return jsonify({'error': 'No message content or attachments provided'}), 400
    try:
        # The client's add_user_message now accepts attachments
        gui_chat_client.add_user_message(message_content, attachments=attachments)
        result = gui_api_handlers_instance.send_message(message_content) # API handler might re-fetch attachments if needed or use client's state
        return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)
    except Exception as e:
        logger.error(f"Error in /api/send route: {e}", exc_info=True)
        return jsonify({'error': f'Server error processing send request: {str(e)}'}), 500


@flask_app.route('/api/stream', methods=['POST'])
def stream_message_api_route():
    logger.debug("GUI /api/stream endpoint hit")
    if not gui_api_handlers_instance or not gui_chat_client or not gui_event_loop:
        logger.error("GUI API service, client, or event loop not ready for streaming.")
        def error_stream_gen_server_not_ready(): # Renamed for clarity
            yield f"data: {json.dumps({'error': 'Server not ready for streaming.'})}\n\n"
        return Response(stream_with_context(error_stream_gen_server_not_ready()), mimetype='text/event-stream')

    data = request.get_json()
    message_content = data.get('message', '')
    attachments = data.get('attachments')

    if not message_content and not attachments:
        logger.warning("No message content or attachments provided for streaming via /api/stream.")
        def error_no_msg_gen():
            yield f"data: {json.dumps({'error': 'No message or attachments provided for streaming.'})}\n\n"
        return Response(stream_with_context(error_no_msg_gen()), mimetype='text/event-stream')

    logger.info(f"Streaming request received for message: '{message_content[:50]}...' with {len(attachments or [])} attachments.")

    try:
        # *** FIX: Call add_user_message with attachments ***
        gui_chat_client.add_user_message(message_content, attachments=attachments)
    except Exception as e_add_user_msg: # Changed variable name
        logger.error(f"Error adding user message before streaming: {e_add_user_msg}", exc_info=True)
        # *** FIX: Pass the error message to the generator ***
        def error_add_user_gen_fixed(error_str: str):
            yield f"data: {json.dumps({'error': f'Failed to process user message for stream: {error_str}'})}\n\n"
        return Response(stream_with_context(error_add_user_gen_fixed(str(e_add_user_msg))), mimetype='text/event-stream')


    def generate_sse_from_async() -> AsyncGenerator[str, None]: # Added type hint
        queue: asyncio.Queue[Optional[Dict[Any, Any]]] = asyncio.Queue() # Added type hint for queue items

        async def producer():
            try:
                # message_content and attachments are already added to client state by gui_chat_client.add_user_message
                # The stream_message method in APIHandlers will use the client's current state.
                async for item in gui_api_handlers_instance.stream_message(message_content): # Pass message_content for context if needed by handler
                    await queue.put(item)
            except Exception as e_prod:
                logger.error(f"Error in SSE producer (stream_message async_gen): {e_prod}", exc_info=True)
                await queue.put({"error": f"Streaming producer error: {str(e_prod)}"})
            finally:
                await queue.put(None) # Sentinel to indicate end of stream

        # Ensure producer is scheduled on the correct loop
        if gui_event_loop and gui_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(producer(), gui_event_loop)
        else:
            logger.error("Cannot schedule SSE producer: GUI event loop not running.")
            # Immediately yield an error and stop if loop isn't running
            yield f"data: {json.dumps({'error': 'Server event loop not available for streaming.'})}\n\n"
            return


        while True:
            try:
                if not gui_event_loop or not gui_event_loop.is_running():
                    logger.warning("SSE consumer: GUI event loop stopped or not available.")
                    yield f"data: {json.dumps({'error': 'Stream interrupted: server event loop stopped.'})}\n\n"
                    break

                item_future = asyncio.run_coroutine_threadsafe(queue.get(), gui_event_loop)
                item = item_future.result(timeout=90) # Increased timeout slightly

                if item is None: # End of stream sentinel
                    logger.debug("SSE stream generation complete (sentinel received).")
                    break
                yield f"data: {json.dumps(item)}\n\n" # Send data to client
                if item.get("error") or item.get("done"):
                    logger.info(f"SSE stream generation ended by event: {item}")
                    break
            except asyncio.TimeoutError:
                logger.warning("SSE queue get timed out waiting for item from producer.")
                yield f"data: {json.dumps({'error': 'Stream timeout from server.'})}\n\n"
                break
            except Exception as e_cons: # Catch other exceptions during queue.get or processing
                logger.error(f"Error in SSE consumer: {e_cons}", exc_info=True)
                yield f"data: {json.dumps({'error': f'Streaming consumer error: {str(e_cons)}'})}\n\n"
                break

    return Response(stream_with_context(generate_sse_from_async()), mimetype='text/event-stream')


@flask_app.route('/api/conversations', methods=['GET'])
def get_conversations_api_route():
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready', 'conversations': []}), 503
    result = gui_api_handlers_instance.get_conversations()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)

@flask_app.route('/api/conversation/new', methods=['POST'])
def new_conversation_api_route():
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json()
    title = data.get('title', '') # Default to empty string if not provided
    result = gui_api_handlers_instance.new_conversation(title)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)

@flask_app.route('/api/conversation/load/<conversation_identifier>', methods=['POST'])
def load_conversation_api_route(conversation_identifier: str):
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready'}), 503
    result = gui_api_handlers_instance.load_conversation(conversation_identifier)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)

@flask_app.route('/api/conversation/save', methods=['POST'])
def save_conversation_api_route():
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready'}), 503
    result = gui_api_handlers_instance.save_conversation()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/conversation/duplicate/<conversation_id>', methods=['POST'])
def duplicate_conversation_api_route(conversation_id: str):
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json();
    new_title = data.get('new_title')
    if not new_title: return jsonify({'error': 'New title not provided for duplication'}), 400
    result = gui_api_handlers_instance.duplicate_conversation(conversation_id, new_title)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/conversation/rename/<conversation_id>', methods=['POST'])
def rename_conversation_api_route(conversation_id: str):
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json();
    new_title = data.get('new_title')
    if not new_title: return jsonify({'error': 'New title not provided for renaming'}), 400
    result = gui_api_handlers_instance.rename_conversation(conversation_id, new_title)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/conversation/delete/<conversation_id>', methods=['DELETE'])
def delete_conversation_api_route(conversation_id: str):
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    result = gui_api_handlers_instance.delete_conversation(conversation_id)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/settings', methods=['GET'])
def get_settings_api_route():
    if not main_config_for_gui:
        return jsonify({'error': 'Global application configuration not ready'}), 503
    if not gui_api_handlers_instance or not gui_chat_client or not gui_chat_client.provider:
        logger.warning("/api/settings GET: API handlers or client not fully ready, returning defaults from main_config_for_gui.")
        settings_data = {
            "default_provider": main_config_for_gui.get("default_provider"),
            "provider_models": main_config_for_gui.get("provider_models", {}), # Send all provider models
            "system_instruction": main_config_for_gui.get("default_system_instruction", Config.DEFAULT_SYSTEM_INSTRUCTION),
            "generation_params": main_config_for_gui.get("generation_params", {}),
            "use_streaming": main_config_for_gui.get("use_streaming", False)
        }
        return jsonify(settings_data), 200

    settings_data = {
        "default_provider": main_config_for_gui.get("default_provider"),
        "provider_models": main_config_for_gui.get("provider_models", {}),
        "system_instruction": main_config_for_gui.get("default_system_instruction", Config.DEFAULT_SYSTEM_INSTRUCTION),
        "generation_params": main_config_for_gui.get("generation_params", {}),
        "use_streaming": main_config_for_gui.get("use_streaming", False),
        # Current session specific settings from the client if available
        "current_provider_name": gui_chat_client.provider.provider_name,
        "current_model": gui_chat_client.current_model_name,
        "current_params": gui_chat_client.params,
        "current_streaming_preference": gui_chat_client.use_streaming,
        "current_system_instruction_for_active_conv": gui_chat_client.system_instruction
    }
    return jsonify(settings_data), 200


@flask_app.route('/api/settings', methods=['POST'])
def update_settings_api_route():
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json()
    result = gui_api_handlers_instance.update_settings(
        provider=data.get('provider'),
        model=data.get('model'),
        streaming=data.get('streaming'), # This is client's session default streaming
        params=data.get('params')
        # system_instruction is updated via a separate endpoint per conversation
    )
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)

@flask_app.route('/api/conversation/<conversation_id>/system_instruction', methods=['POST'])
def update_conversation_system_instruction_api_route(conversation_id: str):
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json()
    new_instruction = data.get('system_instruction')
    if new_instruction is None: # Check for None explicitly
        return jsonify({'error': 'system_instruction field missing or null'}), 400
    result = gui_api_handlers_instance.update_conversation_system_instruction(conversation_id, new_instruction)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/command', methods=['POST'])
def execute_command_api_route():
    if not gui_api_handlers_instance:
        return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json();
    command_str = data.get('command', '')
    if not command_str: return jsonify({'error': 'No command string provided'}), 400
    result = gui_api_handlers_instance.execute_command(command_str)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/retry/<message_id>', methods=['POST'])
def retry_message_api_route(message_id: str):
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    result = gui_api_handlers_instance.retry_message(message_id)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/message/<message_id>', methods=['GET'])
def get_message_info_api_route(message_id: str):
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    result = gui_api_handlers_instance.get_message_info(message_id)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/navigate', methods=['POST'])
def navigate_sibling_api_route():
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    data = request.get_json();
    message_id = data.get('message_id');
    direction = data.get('direction', 'next') # Default to 'next' if not provided
    if not message_id: return jsonify({'error': 'No message_id provided for navigation'}), 400
    result = gui_api_handlers_instance.navigate_sibling(message_id, direction)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/tree', methods=['GET'])
def get_conversation_tree_api_route():
    if not gui_api_handlers_instance: return jsonify({'error': 'GUI API service not ready'}), 503
    result = gui_api_handlers_instance.get_conversation_tree()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


def start_gui_server(app_config: Config, host: str = "127.0.0.1", port: int = 8080, cli_args: Optional[Any] = None) -> None:
    logger.info("\n" + "=" * 60 + f"\n{Colors.HEADER}{Colors.BOLD}STARTING CannonAI GUI (Flask + Bootstrap){Colors.ENDC}\n" + "=" * 60 + "\n")
    initialize_async_components_for_gui(app_config, cli_args)
    import time
    max_wait_init_secs = 15 # Increased timeout for initialization
    wait_interval_secs = 0.5
    elapsed_wait_secs = 0
    while (gui_api_handlers_instance is None or \
           gui_chat_client is None or \
           (hasattr(gui_chat_client, 'provider') and not gui_chat_client.provider.is_initialized)) and \
            elapsed_wait_secs < max_wait_init_secs:
        logger.info(f"Waiting for GUI client and API handlers to initialize... ({elapsed_wait_secs:.1f}s / {max_wait_init_secs}s)")
        time.sleep(wait_interval_secs)
        elapsed_wait_secs += wait_interval_secs

    if gui_api_handlers_instance is None or gui_chat_client is None:
        logger.critical("GUI API Handlers or AI Client did NOT initialize in time. Flask server may not function correctly.")
    elif hasattr(gui_chat_client, 'provider') and not gui_chat_client.provider.is_initialized: # Check if provider exists before checking is_initialized
        provider_name = getattr(gui_chat_client.provider, 'provider_name', 'N/A')
        logger.error(f"GUI AI Client's provider ({provider_name}) failed to initialize.")
    else:
        logger.info("GUI AI Client and API Handlers appear initialized. Proceeding to start Flask server.")

    # Open browser only if not in Werkzeug reloader process
    if not (os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
        try:
            webbrowser.open(f"http://{host}:{port}")
            logger.info(f"Attempted to open web browser to: http://{host}:{port}")
        except Exception as e_wb:
            logger.warning(f"Could not automatically open web browser: {e_wb}")
    logger.info(f"Flask server starting at http://{host}:{port}\nPress CTRL+C to quit.")
    flask_app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True) # threaded=True can help with responsiveness


if __name__ == "__main__":
    print(f"{Colors.WARNING}WARNING: Running server.py directly. For full application, use 'python cannonai/cannonai.py --gui'{Colors.ENDC}")
    # Create a dummy config and args for direct execution
    test_config = Config(quiet=True) # Load default config quietly

    # Define a simple class or Namespace for cli_args
    class DummyCLIArgs:
        provider = None
        model = None
        conversations_dir = None
        # These should match how they are accessed in initialize_gui_client_async
        effective_gen_params = test_config.get("generation_params", {}).copy()
        effective_use_streaming = test_config.get("use_streaming", False)
        # Add other args if cannonai.py sets them and they are used
        temperature = None
        max_tokens = None
        top_p = None
        top_k = None
        use_streaming_arg = None # Add this if it's checked in init

    dummy_args = DummyCLIArgs()
    start_gui_server(test_config, cli_args=dummy_args)
