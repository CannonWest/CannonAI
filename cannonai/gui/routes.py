#!/usr/bin/env python3
"""
CannonAI GUI Routes Module - All Flask route handlers

This module contains all API route definitions for the CannonAI web interface.
Routes are organized in a Flask Blueprint for modular registration.
"""
import json
import logging
from typing import Optional, Any, TYPE_CHECKING
from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask import current_app

if TYPE_CHECKING:
    from gui.api_handlers import APIHandlers
    from async_client import AsyncClient
    from config import Config

logger = logging.getLogger("cannonai.gui.routes")

# Create blueprint for GUI routes
gui_routes = Blueprint('gui_routes', __name__)

# These will be injected by the server module
_api_handlers: Optional['APIHandlers'] = None
_chat_client: Optional['AsyncClient'] = None
_event_loop: Optional[Any] = None  # asyncio.AbstractEventLoop
_main_config: Optional['Config'] = None


def inject_dependencies(
        api_handlers: 'APIHandlers',
        chat_client: 'AsyncClient',
        event_loop: Any,
        main_config: 'Config'
) -> None:
    """
    Inject dependencies into the routes module.
    Called by server.py after initialization.

    Args:
        api_handlers: The APIHandlers instance
        chat_client: The AsyncClient instance
        event_loop: The GUI event loop
        main_config: The main Config instance
    """
    global _api_handlers, _chat_client, _event_loop, _main_config
    print("[Routes] Injecting dependencies into routes module")
    _api_handlers = api_handlers
    _chat_client = chat_client
    _event_loop = event_loop
    _main_config = main_config


# ============ Status & Connection Routes ============

@gui_routes.route('/api/status', methods=['GET'])
def get_status_api_route():
    """Get the current connection status and client info."""
    print("[Routes] Handling /api/status request")
    if not _api_handlers:
        print("[Routes] API handlers not ready for /api/status")
        return jsonify({'connected': False, 'error': 'GUI API service not ready'}), 503
    return jsonify(_api_handlers.get_status())


# ============ Model Management Routes ============

@gui_routes.route('/api/models', methods=['GET'])
def get_models_api_route():
    """Get available models for the current provider."""
    print("[Routes] Handling /api/models request")
    if not _api_handlers:
        print("[Routes] API handlers not ready for /api/models")
        return jsonify({'error': 'GUI API service not ready', 'models': []}), 503
    result = _api_handlers.get_models()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


# ============ Message Handling Routes ============

@gui_routes.route('/api/send', methods=['POST'])
def send_message_api_route():
    """Send a non-streaming message to the AI."""
    print("[Routes] Handling /api/send request")
    if not _api_handlers or not _chat_client:
        print("[Routes] API handlers or chat client not ready for /api/send")
        return jsonify({'error': 'GUI API service or client not ready'}), 503

    data = request.get_json()
    message_content = data.get('message', '')
    attachments = data.get('attachments')

    print(
        f"[Routes] Send request: message='{message_content[:50]}...', attachments={len(attachments) if attachments else 0}")

    if not message_content and not attachments:
        print("[Routes] No message content or attachments provided")
        return jsonify({'error': 'No message content or attachments provided'}), 400

    try:
        # Add user message with attachments
        _chat_client.add_user_message(message_content, attachments=attachments)
        result = _api_handlers.send_message(message_content)
        return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)
    except ValueError as e:
        logger.warning(f"ValueError in send_message_api_route: {e}")
        return jsonify({'error': str(e)}), 400  # Bad Request
    except Exception as e:
        error_msg = f"Server error processing send request: {str(e)}"
        print(f"[Routes] Error in /api/send: {error_msg}")
        logger.error(error_msg, exc_info=True)
        return jsonify({'error': error_msg}), 500


@gui_routes.route('/api/stream', methods=['POST'])
def stream_message_api_route():
    """Stream a message response from the AI."""
    print("[Routes] Handling /api/stream request")

    if not _api_handlers or not _chat_client or not _event_loop:
        print("[Routes] Required components not ready for streaming")
        logger.error("GUI API service, client, or event loop not ready for streaming.")

        def error_stream_not_ready():
            yield f"data: {json.dumps({'error': 'Server not ready for streaming.'})}\n\n"

        return Response(stream_with_context(error_stream_not_ready()), mimetype='text/event-stream')

    data = request.get_json()
    message_content = data.get('message', '')
    attachments = data.get('attachments')

    print(
        f"[Routes] Stream request: message='{message_content[:50]}...', attachments={len(attachments) if attachments else 0}")

    if not message_content and not attachments:
        print("[Routes] No message content or attachments for streaming")
        logger.warning("No message content or attachments provided for streaming via /api/stream.")

        def error_no_content():
            yield f"data: {json.dumps({'error': 'No message or attachments provided for streaming.'})}\n\n"

        return Response(stream_with_context(error_no_content()), mimetype='text/event-stream')

    logger.info(
        f"Streaming request received for message: '{message_content[:50]}...' with {len(attachments or [])} attachments.")

    try:
        # Add user message with attachments
        _chat_client.add_user_message(message_content, attachments=attachments)
        print("[Routes] User message added successfully, starting stream")
    except ValueError as e:
        logger.warning(f"ValueError in stream_message_api_route before streaming: {e}")

        def error_add_message():
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return Response(stream_with_context(error_add_message()), mimetype='text/event-stream')
    except Exception as e:
        error_msg = f"Failed to process user message for stream: {str(e)}"
        print(f"[Routes] Error adding user message: {error_msg}")
        logger.error(error_msg, exc_info=True)

        def error_add_message_generic():
            yield f"data: {json.dumps({'error': error_msg})}\n\n"

        return Response(stream_with_context(error_add_message_generic()), mimetype='text/event-stream')

    # Import streaming utilities
    from .streaming import stream_with_queue

    # Create the SSE stream generator
    stream_generator = stream_with_queue(
        api_handlers=_api_handlers,
        message_content=message_content,
        event_loop=_event_loop,
        timeout_seconds=90
    )

    print("[Routes] Returning SSE stream response")
    return Response(stream_with_context(stream_generator), mimetype='text/event-stream')


# ============ Conversation Management Routes ============

@gui_routes.route('/api/conversations', methods=['GET'])
def get_conversations_api_route():
    """Get list of saved conversations."""
    print("[Routes] Handling /api/conversations request")
    if not _api_handlers:
        print("[Routes] API handlers not ready for /api/conversations")
        return jsonify({'error': 'GUI API service not ready', 'conversations': []}), 503
    result = _api_handlers.get_conversations()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@gui_routes.route('/api/conversation/new', methods=['POST'])
def new_conversation_api_route():
    """Start a new conversation."""
    print("[Routes] Handling /api/conversation/new request")
    if not _api_handlers:
        print("[Routes] API handlers not ready for new conversation")
        return jsonify({'error': 'GUI API service not ready'}), 503

    data = request.get_json()
    title = data.get('title', '')
    print(f"[Routes] New conversation request with title: '{title}'")

    result = _api_handlers.new_conversation(title)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@gui_routes.route('/api/conversation/load/<conversation_identifier>', methods=['POST'])
def load_conversation_api_route(conversation_identifier: str):
    """Load a saved conversation."""
    print(f"[Routes] Handling /api/conversation/load/{conversation_identifier}")
    if not _api_handlers:
        print("[Routes] API handlers not ready for load conversation")
        return jsonify({'error': 'GUI API service not ready'}), 503

    result = _api_handlers.load_conversation(conversation_identifier)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@gui_routes.route('/api/conversation/save', methods=['POST'])
def save_conversation_api_route():
    """Save the current conversation."""
    print("[Routes] Handling /api/conversation/save request")
    if not _api_handlers:
        print("[Routes] API handlers not ready for save conversation")
        return jsonify({'error': 'GUI API service not ready'}), 503

    result = _api_handlers.save_conversation()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@gui_routes.route('/api/conversation/duplicate/<conversation_id>', methods=['POST'])
def duplicate_conversation_api_route(conversation_id: str):
    """Duplicate a conversation with a new title."""
    print(f"[Routes] Handling /api/conversation/duplicate/{conversation_id}")
    if not _api_handlers:
        print("[Routes] API handlers not ready for duplicate")
        return jsonify({'error': 'GUI API service not ready'}), 503

    data = request.get_json()
    new_title = data.get('new_title')
    if not new_title:
        print("[Routes] No new title provided for duplication")
        return jsonify({'error': 'New title not provided for duplication'}), 400

    print(f"[Routes] Duplicating conversation {conversation_id} with title: '{new_title}'")
    result = _api_handlers.duplicate_conversation(conversation_id, new_title)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@gui_routes.route('/api/conversation/rename/<conversation_id>', methods=['POST'])
def rename_conversation_api_route(conversation_id: str):
    """Rename a conversation."""
    print(f"[Routes] Handling /api/conversation/rename/{conversation_id}")
    if not _api_handlers:
        print("[Routes] API handlers not ready for rename")
        return jsonify({'error': 'GUI API service not ready'}), 503

    data = request.get_json()
    new_title = data.get('new_title')
    if not new_title:
        print("[Routes] No new title provided for renaming")
        return jsonify({'error': 'New title not provided for renaming'}), 400

    print(f"[Routes] Renaming conversation {conversation_id} to: '{new_title}'")
    result = _api_handlers.rename_conversation(conversation_id, new_title)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@gui_routes.route('/api/conversation/delete/<conversation_id>', methods=['DELETE'])
def delete_conversation_api_route(conversation_id: str):
    """Delete a conversation."""
    print(f"[Routes] Handling /api/conversation/delete/{conversation_id}")
    if not _api_handlers:
        print("[Routes] API handlers not ready for delete")
        return jsonify({'error': 'GUI API service not ready'}), 503

    result = _api_handlers.delete_conversation(conversation_id)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


# ============ Settings & Configuration Routes ============

@gui_routes.route('/api/settings', methods=['GET'])
def get_settings_api_route():
    """Get current settings and configuration."""
    print("[Routes] Handling GET /api/settings request")

    if not _main_config:
        print("[Routes] Main config not available")
        return jsonify({'error': 'Global application configuration not ready'}), 503

    # Check if client is fully initialized
    if not _api_handlers or not _chat_client or not _chat_client.provider:
        print("[Routes] Client not fully ready, returning defaults from config")
        logger.warning(
            "/api/settings GET: API handlers or client not fully ready, returning defaults from main_config.")

        settings_data = {
            "default_provider": _main_config.get("default_provider"),
            "provider_models": _main_config.get("provider_models", {}),
            "system_instruction": _main_config.get("default_system_instruction", "You are a helpful assistant."),
            "generation_params": _main_config.get("generation_params", {}),
            "use_streaming": _main_config.get("use_streaming", False)
        }
        return jsonify(settings_data), 200

    # Return full settings including current session state
    settings_data = {
        "default_provider": _main_config.get("default_provider"),
        "provider_models": _main_config.get("provider_models", {}),
        "system_instruction": _main_config.get("default_system_instruction", "You are a helpful assistant."),
        "generation_params": _main_config.get("generation_params", {}),
        "use_streaming": _main_config.get("use_streaming", False),
        # Current session specific settings
        "current_provider_name": _chat_client.provider.provider_name,
        "current_model": _chat_client.current_model_name,
        "current_params": _chat_client.params,
        "current_streaming_preference": _chat_client.use_streaming,
        "current_system_instruction_for_active_conv": _chat_client.system_instruction
    }

    print(f"[Routes] Returning settings with provider: {settings_data['current_provider_name']}")
    return jsonify(settings_data), 200


@gui_routes.route('/api/settings', methods=['POST'])
def update_settings_api_route():
    """Update settings (provider, model, streaming, params)."""
    print("[Routes] Handling POST /api/settings request")
    if not _api_handlers:
        print("[Routes] API handlers not ready for settings update")
        return jsonify({'error': 'GUI API service not ready'}), 503

    data = request.get_json()
    print(f"[Routes] Settings update request with keys: {list(data.keys())}")

    result = _api_handlers.update_settings(
        provider=data.get('provider'),
        model=data.get('model'),
        streaming=data.get('streaming'),
        params=data.get('params')
    )
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@gui_routes.route('/api/conversation/<conversation_id>/system_instruction', methods=['POST'])
def update_conversation_system_instruction_api_route(conversation_id: str):
    """Update system instruction for a specific conversation."""
    print(f"[Routes] Handling /api/conversation/{conversation_id}/system_instruction")
    if not _api_handlers:
        print("[Routes] API handlers not ready for system instruction update")
        return jsonify({'error': 'GUI API service not ready'}), 503

    data = request.get_json()
    new_instruction = data.get('system_instruction')
    if new_instruction is None:
        print("[Routes] No system_instruction provided")
        return jsonify({'error': 'system_instruction field missing or null'}), 400

    print(f"[Routes] Updating system instruction for conversation {conversation_id}: '{new_instruction[:50]}...'")
    result = _api_handlers.update_conversation_system_instruction(conversation_id, new_instruction)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


# ============ Command & Control Routes ============

@gui_routes.route('/api/command', methods=['POST'])
def execute_command_api_route():
    """Execute a CLI-style command."""
    print("[Routes] Handling /api/command request")
    if not _api_handlers:
        print("[Routes] API handlers not ready for command execution")
        return jsonify({'error': 'GUI API service not ready'}), 503

    data = request.get_json()
    command_str = data.get('command', '')
    if not command_str:
        print("[Routes] No command string provided")
        return jsonify({'error': 'No command string provided'}), 400

    print(f"[Routes] Executing command: '{command_str}'")
    result = _api_handlers.execute_command(command_str)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


# ============ Message Navigation & Tree Routes ============

@gui_routes.route('/api/retry/<message_id>', methods=['POST'])
def retry_message_api_route(message_id: str):
    """Retry generating a response for a message."""
    print(f"[Routes] Handling /api/retry/{message_id}")
    if not _api_handlers:
        print("[Routes] API handlers not ready for retry")
        return jsonify({'error': 'GUI API service not ready'}), 503

    result = _api_handlers.retry_message(message_id)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@gui_routes.route('/api/message/<message_id>', methods=['GET'])
def get_message_info_api_route(message_id: str):
    """Get information about a specific message."""
    print(f"[Routes] Handling /api/message/{message_id}")
    if not _api_handlers:
        print("[Routes] API handlers not ready for message info")
        return jsonify({'error': 'GUI API service not ready'}), 503

    result = _api_handlers.get_message_info(message_id)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@gui_routes.route('/api/navigate', methods=['POST'])
def navigate_sibling_api_route():
    """Navigate between sibling messages (alternative responses)."""
    print("[Routes] Handling /api/navigate request")
    if not _api_handlers:
        print("[Routes] API handlers not ready for navigation")
        return jsonify({'error': 'GUI API service not ready'}), 503

    data = request.get_json()
    message_id = data.get('message_id')
    direction = data.get('direction', 'next')

    if not message_id:
        print("[Routes] No message_id provided for navigation")
        return jsonify({'error': 'No message_id provided for navigation'}), 400

    print(f"[Routes] Navigating {direction} from message {message_id}")
    result = _api_handlers.navigate_sibling(message_id, direction)
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


@gui_routes.route('/api/tree', methods=['GET'])
def get_conversation_tree_api_route():
    """Get the conversation tree structure for visualization."""
    print("[Routes] Handling /api/tree request")
    if not _api_handlers:
        print("[Routes] API handlers not ready for tree request")
        return jsonify({'error': 'GUI API service not ready'}), 503

    result = _api_handlers.get_conversation_tree()
    return jsonify(result), result.get('status_code', 200 if 'error' not in result else 500)


# ============ Health Check & Debug Routes ============

@gui_routes.route('/api/health', methods=['GET'])
def health_check_route():
    """Simple health check endpoint."""
    print("[Routes] Health check requested")

    health_status = {
        'status': 'ok',
        'api_handlers_ready': _api_handlers is not None,
        'chat_client_ready': _chat_client is not None,
        'event_loop_ready': _event_loop is not None,
        'config_ready': _main_config is not None
    }

    # Determine overall health
    all_ready = all(health_status.values())
    status_code = 200 if all_ready else 503

    if not all_ready:
        health_status['status'] = 'degraded'
        print(f"[Routes] Health check degraded: {health_status}")

    return jsonify(health_status), status_code


@gui_routes.route('/api/test/stream', methods=['GET'])
def test_streaming_route():
    """Test endpoint for SSE streaming functionality."""
    print("[Routes] Test streaming endpoint requested")

    if not _event_loop:
        print("[Routes] Event loop not available for test streaming")
        return jsonify({'error': 'Event loop not ready for streaming test'}), 503

    from .streaming import test_streaming_connection

    stream_generator = test_streaming_connection(_event_loop)
    return Response(stream_with_context(stream_generator), mimetype='text/event-stream')
