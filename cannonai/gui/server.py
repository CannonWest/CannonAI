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
from typing import Dict, Any, Optional
from datetime import datetime
from threading import Thread

# Add the parent directory to the Python path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Flask imports
from flask import Flask, render_template, request, jsonify, Response, session, stream_with_context
from flask_cors import CORS

# Import from the project
from async_client import AsyncGeminiClient
from command_handler import CommandHandler
from config import Config
from base_client import Colors
from gui.api_handlers import APIHandlers

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cannonai.gui.server")

# Create Flask app
app = Flask(__name__, 
    template_folder='templates',
    static_folder='static'
)
app.secret_key = 'cannonai-gui-secret-key'  # Change this in production
CORS(app)

# Global variables
chat_client: Optional[AsyncGeminiClient] = None
command_handler: Optional[CommandHandler] = None
event_loop: Optional[asyncio.AbstractEventLoop] = None
loop_thread: Optional[Thread] = None
api_handlers: Optional[APIHandlers] = None


def run_async_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Run the async event loop in a separate thread"""
    print("[DEBUG] Starting async event loop in thread")
    asyncio.set_event_loop(loop)
    loop.run_forever()
    print("[DEBUG] Async event loop stopped")


def initialize_async_components(config: Config) -> None:
    """Initialize async components in a separate thread"""
    global chat_client, command_handler, event_loop, loop_thread, api_handlers
    
    print("[DEBUG] Initializing async components...")
    
    # Create new event loop for the thread
    event_loop = asyncio.new_event_loop()
    
    # Start the event loop in a separate thread
    loop_thread = Thread(target=run_async_loop, args=(event_loop,), daemon=True)
    loop_thread.start()
    
    # Initialize client in the async loop
    future = asyncio.run_coroutine_threadsafe(
        initialize_client(config), event_loop
    )
    
    try:
        chat_client = future.result(timeout=30)  # Wait up to 30 seconds
        print(f"[DEBUG] Successfully initialized Gemini client with model: {chat_client.model}")
        
        # Initialize command handler
        command_handler = CommandHandler(chat_client)
        print("[DEBUG] Command handler initialized")
        
        # Set the client to web UI mode
        chat_client.is_web_ui = True
        print("[DEBUG] Client set to web UI mode")
        
        # Initialize API handlers
        api_handlers = APIHandlers(chat_client, command_handler, event_loop)
        print("[DEBUG] API handlers initialized")
        
    except Exception as e:
        print(f"[ERROR] Failed to initialize client: {e}")
        import traceback
        traceback.print_exc()
        raise


async def initialize_client(config: Config) -> AsyncGeminiClient:
    """Initialize the Gemini chat client asynchronously"""
    print("[DEBUG] Creating AsyncGeminiClient...")
    
    # Get configuration values
    api_key = config.get_api_key()
    model = config.get("default_model")
    conversations_dir = config.get("conversations_dir")
    gen_params = config.get("generation_params", {}).copy()
    use_streaming = config.get("use_streaming", False)
    
    print(f"[DEBUG] Config - Model: {model}, Streaming: {use_streaming}")
    
    # Create client
    client = AsyncGeminiClient(
        api_key=api_key,
        model=model,
        conversations_dir=Path(conversations_dir) if conversations_dir else None
    )
    
    # Set parameters
    client.params = gen_params
    client.use_streaming = use_streaming
    
    # Initialize the client
    success = await client.initialize_client()
    if not success:
        raise Exception("Failed to initialize Gemini client")
    
    return client


# Routes
@app.route('/')
def index():
    """Serve the main GUI page"""
    print("[DEBUG] Serving index page")
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    """Get current client status"""
    if not api_handlers:
        return jsonify({'connected': False, 'error': 'API handlers not initialized'}), 500
    
    return jsonify(api_handlers.get_status())


@app.route('/api/models')
def get_models():
    """Get available models"""
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    result = api_handlers.get_models()
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/conversations')
def get_conversations():
    """Get list of saved conversations"""
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    result = api_handlers.get_conversations()
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/conversation/new', methods=['POST'])
def new_conversation():
    """Start a new conversation"""
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    data = request.get_json()
    title = data.get('title', '')
    
    result = api_handlers.new_conversation(title)
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/conversation/load', methods=['POST'])
def load_conversation():
    """Load a saved conversation"""
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    data = request.get_json()
    conversation_name = data.get('conversation_name', '')
    
    if not conversation_name:
        return jsonify({'error': 'No conversation name provided'}), 400
    
    result = api_handlers.load_conversation(conversation_name)
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/conversation/save', methods=['POST'])
def save_conversation():
    """Save the current conversation"""
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    result = api_handlers.save_conversation()
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/send', methods=['POST'])
def send_message():
    """Send a message and get response (non-streaming)"""
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    data = request.get_json()
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    
    result = api_handlers.send_message(message)
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/stream', methods=['POST'])
def stream_message():
    """Send a message and stream the response using Server-Sent Events"""
    print("[DEBUG] Streaming message")
    
    if not api_handlers:
        return Response("API handlers not initialized", status=500)
    
    data = request.get_json()
    message = data.get('message', '')
    
    if not message:
        return Response("No message provided", status=400)
    
    print(f"[DEBUG] User message for streaming: {message[:50]}...")
    
    def generate():
        """Generator function for SSE streaming"""
        try:
            # Use a queue to bridge async and sync
            import queue
            result_queue = queue.Queue()
            
            async def stream_task():
                """Async task to handle streaming"""
                try:
                    async for chunk in api_handlers.stream_message(message):
                        result_queue.put(chunk)
                    result_queue.put(None)  # Signal completion
                except Exception as e:
                    result_queue.put(f"data: {json.dumps({'error': str(e)})}\n\n")
                    result_queue.put(None)
            
            # Start the streaming task
            future = asyncio.run_coroutine_threadsafe(stream_task(), event_loop)
            
            # Yield chunks from the queue
            while True:
                try:
                    chunk = result_queue.get(timeout=60)  # 60 second timeout
                    if chunk is None:
                        break
                    yield chunk
                except queue.Empty:
                    # Timeout - check if task is still running
                    if future.done():
                        break
                    continue
                    
        except Exception as e:
            print(f"[ERROR] Streaming error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'  # Disable Nginx buffering
        }
    )

@app.route('/api/conversation/duplicate/<conversation_id>', methods=['POST'])
def duplicate_conversation_route(conversation_id: str):
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500

    data = request.get_json()
    new_title = data.get('new_title')
    if not new_title:
        return jsonify({'error': 'New title not provided for duplication'}), 400

    result = api_handlers.duplicate_conversation(conversation_id, new_title)
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


@app.route('/api/conversation/rename/<conversation_id>', methods=['POST'])
def rename_conversation_route(conversation_id: str):
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500

    data = request.get_json()
    new_title = data.get('new_title')
    if not new_title:
        return jsonify({'error': 'New title not provided for renaming'}), 400

    result = api_handlers.rename_conversation(conversation_id, new_title)
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)


@app.route('/api/conversation/delete/<conversation_id>', methods=['DELETE'])
def delete_conversation_route(conversation_id: str):
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500

    result = api_handlers.delete_conversation(conversation_id)
    if 'error' in result:
        return jsonify(result), result.get('status_code', 500)
    return jsonify(result)

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update client settings"""
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    data = request.get_json()
    
    result = api_handlers.update_settings(
        model=data.get('model'),
        streaming=data.get('streaming'),
        params=data.get('params')
    )
    
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/command', methods=['POST'])
def execute_command():
    """Execute a command through the command handler"""
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    data = request.get_json()
    command = data.get('command', '')
    
    if not command:
        return jsonify({'error': 'No command provided'}), 400
    
    result = api_handlers.execute_command(command)
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/retry/<message_id>', methods=['POST'])
def retry_message(message_id: str):
    """Retry generating a response for a specific message"""
    print(f"[DEBUG Flask] Retry request for message: {message_id}")
    
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    result = api_handlers.retry_message(message_id)
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/message/<message_id>', methods=['GET'])
def get_message_info(message_id: str):
    """Get detailed information about a message including siblings"""
    print(f"[DEBUG Flask] Getting info for message: {message_id}")
    
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    result = api_handlers.get_message_info(message_id)
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/navigate', methods=['POST'])
def navigate_sibling():
    """Navigate to a sibling message"""
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    data = request.get_json()
    message_id = data.get('message_id')
    direction = data.get('direction', 'next')
    
    if not message_id:
        return jsonify({'error': 'No message ID provided'}), 400
    
    print(f"[DEBUG Flask] Navigate {direction} from message: {message_id}")
    result = api_handlers.navigate_sibling(message_id, direction)
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route('/api/tree', methods=['GET'])
def get_conversation_tree():
    """Get the full conversation tree structure"""
    print("[DEBUG Flask] Getting conversation tree")
    
    if not api_handlers:
        return jsonify({'error': 'API handlers not initialized'}), 500
    
    result = api_handlers.get_conversation_tree()
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


def start_gui_server(config: Config, host: str = "127.0.0.1", port: int = 8080):
    """Start the Flask GUI server"""
    print("\n" + "=" * 60)
    print("STARTING CANNONAI GUI (Flask + Bootstrap)")
    print("=" * 60 + "\n")
    
    # Initialize async components
    try:
        initialize_async_components(config)
    except Exception as e:
        print(f"[ERROR] Failed to initialize components: {e}")
        sys.exit(1)
    
    # Open browser
    webbrowser.open(f"http://{host}:{port}")
    
    # Run Flask server
    print(f"[INFO] Starting Flask server at http://{host}:{port}")
    app.run(host=host, port=port, debug=True, use_reloader=False)


if __name__ == "__main__":
    # For testing
    config = Config()
    start_gui_server(config)
