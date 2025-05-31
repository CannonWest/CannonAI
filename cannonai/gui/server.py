#!/usr/bin/env python3
"""
CannonAI GUI Server - Flask implementation for the web interface

This module provides the Flask server implementation for the CannonAI Web GUI.
It handles HTTP requests, Server-Sent Events for streaming, and serves the Bootstrap-based UI.
"""

import os
import sys
import json
import asyncio
import logging
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING  # Added TYPE_CHECKING
from datetime import datetime
from threading import Thread
import traceback

# Flask imports
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS

# Import from the project
from async_client import AsyncClient
from command_handler import CommandHandler
from config import Config
from base_client import Colors
# from gui.api_handlers import APIHandlers # Keep this, but handle type hint below
from client_manager import ClientManager
from providers import ProviderError
from gui import api_handlers as gui_api_handlers_module # Import the module itself

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cannonai.gui.server")

# Global variables for the GUI's own client instance
gui_chat_client: Optional[AsyncClient] = None
gui_command_handler: Optional[CommandHandler] = None
gui_event_loop: Optional[asyncio.AbstractEventLoop] = None
gui_loop_thread: Optional[Thread] = None
gui_api_handlers: Optional['APIHandlers'] = None  # Use string literal for the type hint
main_config_for_gui: Optional[Config] = None


def run_async_loop_for_gui(loop: asyncio.AbstractEventLoop) -> None:
    logger.info("Starting async event loop for GUI client in a new thread.")
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("GUI Async event loop interrupted.")
    finally:
        logger.info("GUI Async event loop stopped.")
        if not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
            # loop.close() # close() must be called from the loop's thread or after it's stopped


async def initialize_gui_client_async(app_config: Config, cli_args: Optional[Any]) -> None:
    global gui_chat_client, gui_command_handler, gui_api_handlers, gui_event_loop

    # This import is fine here as it's within a function, executed after module-level imports
    from gui.api_handlers import APIHandlers

    logger.info("Initializing AI client for GUI...")
    try:
        # Determine effective parameters for ClientManager, prioritizing CLI args
        effective_params = app_config.get("generation_params", {}).copy()
        if cli_args and hasattr(cli_args, 'effective_gen_params') and cli_args.effective_gen_params is not None:
            effective_params.update(cli_args.effective_gen_params)

        effective_streaming = app_config.get("use_streaming", False)
        if cli_args and hasattr(cli_args, 'effective_use_streaming') and cli_args.effective_use_streaming is not None:
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
            logger.error("Failed to initialize AI client for GUI.")
            return

        gui_command_handler = CommandHandler(gui_chat_client)
        gui_chat_client.is_web_ui = True

        if gui_event_loop is None:
            logger.error("GUI Event loop not set before APIHandlers initialization!")
            try:
                gui_event_loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.error("No running event loop to assign to APIHandlers.")
                return

        gui_api_handlers = APIHandlers(gui_chat_client, gui_command_handler, gui_event_loop)

        # Pass config to api_handlers if it's designed to use it
        if hasattr(gui_api_handlers, 'main_config'):
            gui_api_handlers.main_config = app_config
        # Corrected part: Check the imported module for 'main_config'
        elif hasattr(gui_api_handlers_module, 'main_config'):
            gui_api_handlers_module.main_config = app_config

        logger.info(f"GUI AI Client initialized successfully with provider: {gui_chat_client.provider.provider_name}, model: {gui_chat_client.current_model_name}")

    except (ValueError, ProviderError) as e:
        logger.error(f"Error creating AI client for GUI: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error initializing AI client for GUI: {e}", exc_info=True)


def initialize_async_components_for_gui(app_config: Config, cli_args: Optional[Any]) -> None:
    global gui_event_loop, gui_loop_thread, main_config_for_gui

    main_config_for_gui = app_config

    if gui_event_loop is None or gui_event_loop.is_closed():
        gui_event_loop = asyncio.new_event_loop()
        logger.info("New asyncio event loop created for GUI.")

    if gui_loop_thread is None or not gui_loop_thread.is_alive():
        gui_loop_thread = Thread(target=run_async_loop_for_gui, args=(gui_event_loop,), daemon=True)
        gui_loop_thread.start()
        logger.info("Asyncio event loop thread started for GUI.")

    if gui_event_loop and gui_event_loop.is_running():
        # Ensure effective_gen_params and effective_use_streaming are passed if needed by initialize_gui_client_async
        # These should be resolved in cannonai.py and passed via cli_args
        if cli_args and not hasattr(cli_args, 'effective_gen_params'):
            # Resolve them here if not passed, similar to cannonai.py's logic
            cli_args.effective_gen_params = app_config.get("generation_params", {}).copy()
            if hasattr(cli_args, 'temperature') and cli_args.temperature is not None: cli_args.effective_gen_params["temperature"] = cli_args.temperature
            if hasattr(cli_args, 'max_tokens') and cli_args.max_tokens is not None: cli_args.effective_gen_params["max_output_tokens"] = cli_args.max_tokens
            if hasattr(cli_args, 'top_p') and cli_args.top_p is not None: cli_args.effective_gen_params["top_p"] = cli_args.top_p
            if hasattr(cli_args, 'top_k') and cli_args.top_k is not None: cli_args.effective_gen_params["top_k"] = cli_args.top_k

        if cli_args and not hasattr(cli_args, 'effective_use_streaming'):
            cli_args.effective_use_streaming = cli_args.use_streaming_arg if hasattr(cli_args, 'use_streaming_arg') and cli_args.use_streaming_arg is not None else app_config.get("use_streaming", False)

        asyncio.run_coroutine_threadsafe(initialize_gui_client_async(app_config, cli_args), gui_event_loop)
    else:
        logger.error("GUI event loop not running or not available to schedule client initialization.")


flask_app = Flask(__name__,
                  template_folder='templates',
                  static_folder='static'
                  )
flask_app.secret_key = os.urandom(24)
CORS(flask_app)


# --- Flask Routes ---
@flask_app.route('/')
def index():
    logger.debug("Serving index page.")
    return render_template('index.html')


@flask_app.before_request
def ensure_api_handlers_ready():
    if request.endpoint and 'static' not in request.endpoint:
        if gui_api_handlers is None:
            logger.warning(f"Accessing {request.endpoint} but gui_api_handlers is None.")
            # Attempt to re-initialize if it's None and we have the config
            # This is a fallback, ideally it should be initialized correctly from the start
            if main_config_for_gui and gui_event_loop and gui_event_loop.is_running():
                logger.info("Attempting to re-initialize gui_api_handlers due to being None.")
                # This is a simplified re-init call, might need more context (cli_args)
                # For now, just ensuring it's not None if possible
                try:
                    # Create a dummy cli_args if not available globally here
                    class DummyArgs: pass
                    dummy_cli_args = DummyArgs()
                    # Populate with essential defaults if possible
                    dummy_cli_args.provider = None
                    dummy_cli_args.model = None
                    dummy_cli_args.conversations_dir = None
                    dummy_cli_args.effective_gen_params = main_config_for_gui.get("generation_params", {}).copy()
                    dummy_cli_args.effective_use_streaming = main_config_for_gui.get("use_streaming", False)

                    asyncio.run_coroutine_threadsafe(initialize_gui_client_async(main_config_for_gui, dummy_cli_args), gui_event_loop).result(timeout=5)
                    if gui_api_handlers is None:
                        logger.error("Re-initialization attempt failed to set gui_api_handlers.")
                except Exception as e:
                    logger.error(f"Error during fallback re-initialization of gui_api_handlers: {e}")


@flask_app.route('/api/status')
def get_status_route():
    if not gui_api_handlers:
        return jsonify({'connected': False, 'error': 'GUI API handlers not initialized'}), 503
    return jsonify(gui_api_handlers.get_status())


@flask_app.route('/api/models')
def get_models_route():
    if not gui_api_handlers:
        return jsonify({'error': 'GUI API handlers not initialized', 'models': [], 'current_provider': 'N/A'}), 503
    result = gui_api_handlers.get_models()
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


@flask_app.route('/api/send', methods=['POST'])
def send_message_api_route():
    if not gui_api_handlers:
        return jsonify({'error': 'GUI API handlers not initialized'}), 503
    data = request.get_json()
    message = data.get('message', '')
    if not message:
        return jsonify({'error': 'No message provided'}), 400

    if gui_api_handlers.client:
        try:
            gui_api_handlers.client.add_user_message(message)
        except Exception as e_add_user:
            logger.error(f"Error adding user message via API: {e_add_user}", exc_info=True)
            return jsonify({'error': f'Failed to process user message: {e_add_user}'}), 500
    else:
        return jsonify({'error': 'Client not available in API Handlers'}), 503

    result = gui_api_handlers.send_message(message)
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


@flask_app.route('/api/stream', methods=['POST'])
def stream_message_api_route():
    logger.debug("GUI /api/stream endpoint hit")
    if not gui_api_handlers or not gui_event_loop or not gui_api_handlers.client:
        logger.error("GUI API handlers, event loop, or client not initialized for streaming.")

        def error_stream(): yield f"data: {json.dumps({'error': 'Server not ready for streaming.'})}\n\n"

        return Response(stream_with_context(error_stream()), mimetype='text/event-stream')

    data = request.get_json()
    message_content = data.get('message', '')
    if not message_content:
        logger.warning("No message content provided for streaming.")

        def error_stream_no_msg(): yield f"data: {json.dumps({'error': 'No message provided for streaming.'})}\n\n"

        return Response(stream_with_context(error_stream_no_msg()), mimetype='text/event-stream')

    logger.info(f"Streaming request for message: '{message_content[:50]}...'")

    try:
        gui_api_handlers.client.add_user_message(message_content)
    except Exception as e_add_user_stream:
        logger.error(f"Error adding user message before streaming: {e_add_user_stream}", exc_info=True)

        def error_stream_user_add():
            yield f"data: {json.dumps({'error': f'Failed to process user message for stream: {e_add_user_stream}'})}\n\n"

        return Response(stream_with_context(error_stream_user_add()), mimetype='text/event-stream')

    def generate_sse_from_async_gen():
        q = asyncio.Queue()

        async def produce_to_queue():
            try:
                async for item in gui_api_handlers.stream_message(message_content):
                    await q.put(item)
            except Exception as e_prod:
                logger.error(f"Error in SSE producer (async_gen): {e_prod}", exc_info=True)
                await q.put({"error": f"Streaming producer error: {str(e_prod)}"})
            finally:
                await q.put(None)

        asyncio.run_coroutine_threadsafe(produce_to_queue(), gui_event_loop)

        while True:
            try:
                future = asyncio.run_coroutine_threadsafe(q.get(), gui_event_loop)
                item = future.result(timeout=60)

                if item is None:
                    logger.debug("SSE stream generation complete (None received from queue).")
                    break

                sse_event = f"data: {json.dumps(item)}\n\n"
                yield sse_event

                if item.get("error") or item.get("done"):
                    logger.info(f"SSE stream generation ended by event: {item}")
                    break
            except asyncio.TimeoutError:
                logger.warning("SSE queue get timed out.")
                yield f"data: {json.dumps({'error': 'Stream timeout from server.'})}\n\n"
                break
            except Exception as e_cons:
                logger.error(f"Error in SSE consumer (sync_gen): {e_cons}", exc_info=True)
                yield f"data: {json.dumps({'error': f'Streaming consumer error: {str(e_cons)}'})}\n\n"
                break

    return Response(stream_with_context(generate_sse_from_async_gen()), mimetype='text/event-stream')


@flask_app.route('/api/conversations')
def get_conversations_route():
    if not gui_api_handlers:
        return jsonify({'error': 'GUI API handlers not initialized', 'conversations': []}), 503 # Return 503 if not ready
    result = gui_api_handlers.get_conversations()
    if 'error' in result:
        # If get_conversations itself returns an error (e.g., directory not found),
        # use its status code or default to 500.
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


@flask_app.route('/api/conversation/duplicate/<conversation_id>', methods=['POST'])
def duplicate_conversation_api_route(conversation_id: str):
    if not gui_api_handlers: return jsonify({'error': 'GUI API handlers not initialized'}), 503
    data = request.get_json();
    new_title = data.get('new_title')
    if not new_title: return jsonify({'error': 'New title not provided'}), 400
    result = gui_api_handlers.duplicate_conversation(conversation_id, new_title)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/conversation/rename/<conversation_id>', methods=['POST'])
def rename_conversation_api_route(conversation_id: str):
    if not gui_api_handlers: return jsonify({'error': 'GUI API handlers not initialized'}), 503
    data = request.get_json();
    new_title = data.get('new_title')
    if not new_title: return jsonify({'error': 'New title not provided'}), 400
    result = gui_api_handlers.rename_conversation(conversation_id, new_title)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/conversation/delete/<conversation_id>', methods=['DELETE'])
def delete_conversation_api_route(conversation_id: str):
    if not gui_api_handlers: return jsonify({'error': 'GUI API handlers not initialized'}), 503
    result = gui_api_handlers.delete_conversation(conversation_id)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@flask_app.route('/api/settings', methods=['POST'])
def update_settings_api_route():
    if not gui_api_handlers:
        return jsonify({'error': 'GUI API handlers not initialized'}), 503
    data = request.get_json()
    result = gui_api_handlers.update_settings(
        provider=data.get('provider'),
        model=data.get('model'),
        streaming=data.get('streaming'),
        params=data.get('params')
    )
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


@flask_app.route('/api/command', methods=['POST'])
def execute_command_api_route():
    if not gui_api_handlers:
        return jsonify({'error': 'GUI API handlers not initialized'}), 503
    data = request.get_json()
    command_str = data.get('command', '')
    if not command_str:
        return jsonify({'error': 'No command provided'}), 400
    result = gui_api_handlers.execute_command(command_str)
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


@flask_app.route('/api/retry/<message_id>', methods=['POST'])
def retry_message_api_route(message_id: str):
    if not gui_api_handlers:
        return jsonify({'error': 'GUI API handlers not initialized'}), 503
    result = gui_api_handlers.retry_message(message_id)
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


@flask_app.route('/api/message/<message_id>', methods=['GET'])
def get_message_info_api_route(message_id: str):
    if not gui_api_handlers:
        return jsonify({'error': 'GUI API handlers not initialized'}), 503
    result = gui_api_handlers.get_message_info(message_id)
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


@flask_app.route('/api/navigate', methods=['POST'])
def navigate_sibling_api_route():
    if not gui_api_handlers:
        return jsonify({'error': 'GUI API handlers not initialized'}), 503
    data = request.get_json()
    message_id = data.get('message_id')
    direction = data.get('direction', 'next')
    if not message_id:
        return jsonify({'error': 'No message ID provided'}), 400
    result = gui_api_handlers.navigate_sibling(message_id, direction)
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


@flask_app.route('/api/tree', methods=['GET'])
def get_conversation_tree_api_route():
    if not gui_api_handlers:
        return jsonify({'error': 'GUI API handlers not initialized'}), 503
    result = gui_api_handlers.get_conversation_tree()
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


def start_gui_server(app_config: Config, host: str = "127.0.0.1", port: int = 8080, cli_args: Optional[Any] = None):
    logger.info("\n" + "=" * 60)
    logger.info("STARTING CannonAI GUI (Flask + Bootstrap)")
    logger.info("=" * 60 + "\n")

    initialize_async_components_for_gui(app_config, cli_args)

    import time
    # Wait a bit for async components to potentially initialize
    # Check if gui_api_handlers is initialized after the async call
    # This loop is a bit of a hack; ideally, initialize_async_components_for_gui would signal completion.
    max_wait_time = 10  # seconds
    wait_interval = 0.5 # seconds
    elapsed_time = 0
    while gui_api_handlers is None and elapsed_time < max_wait_time:
        logger.info(f"Waiting for gui_api_handlers to be initialized... ({elapsed_time:.1f}s)")
        time.sleep(wait_interval)
        elapsed_time += wait_interval

    if gui_api_handlers is None:
         logger.error("GUI API Handlers did not initialize in time. Flask server might not function correctly.")
    elif gui_chat_client is None or (gui_chat_client.provider and not gui_chat_client.provider.is_initialized):
        logger.error("GUI AI Client or its provider failed to initialize properly. Flask server might not function correctly.")
    else:
        logger.info("GUI AI Client and API Handlers appear initialized. Starting Flask server.")

    if not (os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
        try:
            webbrowser.open(f"http://{host}:{port}")
            logger.info(f"Opened browser to http://{host}:{port}")
        except Exception as e_wb:
            logger.warning(f"Could not open browser: {e_wb}")

    logger.info(f"Starting Flask server at http://{host}:{port}")
    flask_app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    print("WARNING: Running server.py directly. For full application, use 'python cannonai/cannonai.py --gui'")
    test_config = Config()


    class DummyArgs:
        provider = None;
        model = None;
        conversations_dir = None
        effective_gen_params = None;
        effective_use_streaming = None
        # Add any other attributes from cli_args that initialize_gui_client_async might access
        temperature = None;
        max_tokens = None;
        top_p = None;
        top_k = None;
        use_streaming_arg = None


    start_gui_server(test_config, cli_args=DummyArgs())
