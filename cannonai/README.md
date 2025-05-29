Okay, I can help you update the README file.

Based on the provided files, here's an updated version of your `gemini_chat/README.md`. The key changes include:
* Correcting the Web Interface Mode details (Flask instead of FastAPI, correct port number).
* Updating the Project Structure to reflect the `gui` directory and its contents (Flask server, API handlers, templates).
* Aligning the Web UI dependencies with Flask.
* Adding the Gemini 2.5 preview models to the Supported Models list.
* Removing references to non-existent files like `websocket_fix.py` and `websocket_diagnostics.py`.
* Clarifying the GUI requirements installation.

```markdown
# CannonAI

A powerful, modular application for interacting with Google's Gemini AI models, supporting both command-line and web interfaces.

[![Python Version](https://img.shields.io/badge/python-3.6%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Features

- Multi-turn conversations with Google's Gemini models
- Select from available Gemini models
- Customize generation parameters (temperature, max tokens, etc.)
- Save and load conversations as JSON files
- Navigate between different saved conversations
- Full conversation history management, including retrying messages and navigating alternative responses (branching)
- Support for both streaming and non-streaming responses
- Support for both synchronous and asynchronous implementations
- Cross-platform terminal colors
- Persistent configuration system
- Web-based user interface using Flask and Bootstrap

## Project Structure

The application is organized with a modular architecture to minimize redundancy:

```
CannonAI_GIT/
├── gemini_chat/                  # Main application code (to be renamed to cannonai)
│   ├── gemini_chat.py            # Single unified entry point
│   ├── base_client.py            # Core shared functionality
│   ├── sync_client.py            # Synchronous implementation
│   ├── async_client.py           # Asynchronous implementation
│   ├── command_handler.py        # Command processing for both modes
│   ├── client_manager.py         # Client creation and management
│   ├── config.py                 # Configuration management
│   ├── gui/                      # Web interface implementation (Flask)
│   │   ├── server.py             # Flask server for web UI
│   │   ├── api_handlers.py       # Business logic for API endpoints
│   │   ├── static/               # Static UI assets
│   │   │   ├── css/style.css     # UI styling
│   │   │   ├── js/app.js         # UI JavaScript functionality
│   │   ├── templates/
│   │   │   └── index.html        # Main UI template
│   │   └── __init__.py           # GUI package initialization
│   ├── __init__.py               # Package initialization
│   ├── requirements.txt          # Core and GUI dependencies
│   ├── GUI_README.md             # Detailed documentation for the GUI
│   └── tests/                    # Test suite (if present)
├── gemini_chat_config/           # Configuration storage (to be renamed to cannonai_config)
└── gemini_chat_conversations/    # Saved conversations (auto-created, to be renamed to cannonai_conversations)
```

## Installation

1.  Clone this repository:
    ```bash
    git clone https://github.com/yourusername/CannonAI.git
    cd CannonAI
    ```

2.  Install the required dependencies:
    ```bash
    # Core and Web UI (Flask) dependencies
    pip install -r gemini_chat/requirements.txt
    ```
    Alternatively, if you have a separate `gui_requirements.txt` specifically for Flask (as mentioned in GUI_README.md):
    ```bash
    pip install -r gemini_chat/requirements.txt # for core
    pip install -r gemini_chat/gui_requirements.txt # for GUI
    ```

3.  Set up your API key (choose one method):
    * Set as an environment variable:
        ```bash
        # Linux/macOS
        export GEMINI_API_KEY='your_api_key_here'

        # Windows
        set GEMINI_API_KEY=your_api_key_here
        ```
    * Run the configuration wizard:
        ```bash
        python cannonai/cannonai.py --setup
        ```
    * Pass as a command-line argument:
        ```bash
        python cannonai/cannonai.py --api-key 'your_api_key_here'
        ```

## Usage

### Running the Application

```bash
python gemini_chat/gemini_chat.py [options]
```

### Command-line Arguments

```bash
python gemini_chat/gemini_chat.py --help
```

Available arguments:
* `--api-key`: Specify your Gemini API key (overrides config and environment variable)
* `--model`: Specify the model to use (default: from config or gemini-2.0-flash)
* `--async`: Use asynchronous client implementation
* `--dir`, `--conversations-dir`: Directory to store conversations
* `--gui`: Launch with the web-based user interface (Flask + Bootstrap)
* `--setup`: Run the configuration setup wizard
* `--config`: Specify a custom configuration file path

Advanced options:
* `--temp`, `--temperature`: Generation temperature (0.0-2.0)
* `--max-tokens`: Maximum output tokens
* `--top-p`: Top-p sampling parameter (0.0-1.0)
* `--top-k`: Top-k sampling parameter
* `--stream`: Enable streaming mode by default

## User Interface Modes

The application supports two different user interface modes:

### Command-Line Interface (CLI) Mode

This is the default mode when running the application without any UI-related flags:

```bash
python gemini_chat/gemini_chat.py
```

The CLI mode provides a traditional terminal-based interface with command-line commands.

### Web Interface Mode

The web interface provides a more user-friendly experience with the same functionality:

```bash
python gemini_chat/gemini_chat.py --gui
```

When using the web UI mode:
* A local web server will start (default: `http://127.0.0.1:8080`)
* Your default web browser will automatically open to the CannonAI interface
* The same commands available in CLI mode are available through the web interface
* The web interface provides a more visual experience with better formatting

The modern UI includes additional features:
* Markdown rendering with syntax highlighting for code blocks
* Improved conversation management
* More intuitive settings interface
* Real-time streaming with visual feedback

**Note**: To use the web interface, ensure you have installed the GUI dependencies as mentioned in the Installation section (typically via `pip install -r gemini_chat/requirements.txt` which includes Flask and Flask-CORS, or a specific `gui_requirements.txt`).

### Commands During Chat

During the chat session (both CLI and GUI), you can use the following commands:

| Command   | Description                   |
|-----------|-------------------------------|
| /help     | Show help message             |
| /quit     | Save and exit the application |
| /save     | Save the current conversation |
| /new      | Start a new conversation      |
| /list     | List saved conversations      |
| /load     | Load a saved conversation     |
| /history  | Display conversation history  |
| /model    | Select a different model      |
| /params   | Customize generation parameters |
| /stream   | Toggle streaming mode         |
| /clear    | Clear the screen              |
| /config   | Open configuration settings   |
| /version  | Show version information      |

## Conversation Storage

Conversations are saved as JSON files in the `gemini_chat_conversations` directory, which is automatically created adjacent to the `gemini_chat` directory. The new conversation structure (v2.0.0) includes:
- A unique `conversation_id`.
- `metadata` including title, timestamps, model, parameters, active branch, and active leaf.
- A `messages` dictionary where each message has an ID, parent ID, branch ID, type (user/assistant), content, timestamp, and children.
- A `branches` dictionary to track different lines of conversation.
- Token usage statistics (when available) are stored within assistant messages.

You can navigate between saved conversations using the `/list` and `/load` commands during a chat session.

## Configuration System

The application uses a persistent configuration system that saves your settings between sessions. Configuration is stored in the `gemini_chat_config` directory adjacent to the `gemini_chat` directory:

```
CannonAI_GIT/
├── gemini_chat/             # Main application code
└── gemini_chat_config/      # Configuration storage
    └── gemini_chat_config.json  # (to be renamed to cannonai_config.json)
```

Configuration options include:
* API key
* Default model
* Conversations directory
* Generation parameters
* Default streaming mode

Run the configuration wizard to set up or modify your configuration:
```bash
python gemini_chat/gemini_chat.py --setup
```

## Sync vs Async Mode

The application supports both synchronous and asynchronous operations:

* **Synchronous Mode (Default)**: Traditional mode where operations block until completed.
* **Asynchronous Mode**: Non-blocking mode for better responsiveness with I/O operations.

Use asynchronous mode when working with:
* High-volume API requests
* Applications that need to remain responsive during network operations
* Integration with other asynchronous systems
* The Web Interface (GUI) mode, which utilizes the asynchronous client.

To enable asynchronous mode for the CLI:
```bash
python gemini_chat/gemini_chat.py --async
```

## Getting an API Key

To use this application, you need a Google Gemini API key:

1.  Visit the [Google AI Studio](https://ai.google.dev/)
2.  Sign in with your Google account
3.  Create a new API key from the settings page
4.  Copy and use this key with the application

## Development

### Running Tests

(Assuming tests are set up in `gemini_chat/tests/`)
```bash
pytest gemini_chat/tests/
```

### Using the Makefile

(If a Makefile is present and configured)
A Makefile might be provided for common development tasks:

```bash
# Install dependencies
make install

# Run tests
make test

# Run linters
make lint

# Run in sync mode
make run

# Run in async mode
make run-async

# Clean up generated files
make clean

# Show help message
make help
```

## Requirements

- Python 3.6 or higher
- `google-genai` package (>=0.5.0)
- `tabulate` package (>=0.9.0)
- `colorama` package (>=0.4.4)

### Web UI Additional Requirements (Flask-based)
- `flask` (>=2.3.0)
- `flask-cors` (>=4.0.0)
- `asyncio` (>=3.4.3) (for running the async client with Flask)
- `Jinja2` (typically installed with Flask)
- `Markdown` and `Pygments` (if you wish to ensure specific versions for Markdown rendering in the GUI, though `marked.js` and `highlight.js` are used client-side)

## Supported Models

CannonAI supports multiple Gemini AI models. The client attempts to fetch available models from the API, and falls back to a default list if the API call fails or returns no usable models. This list includes:

-   **`models/gemini-2.0-flash`** (Often referred to as Gemini 2.0 Flash) - Fast model, good for quick responses.
-   **`models/gemini-2.0-pro`** (Often referred to as Gemini 2.0 Pro) - More advanced model with better reasoning capabilities.
-   **`models/gemini-2.5-flash-preview-05-20`**
-   **`models/gemini-2.5-pro-preview-05-06`**

Model availability may vary based on your API access level and Google's current offerings. The application allows selection from models that support "generateContent".

## Troubleshooting

### Common Issues

#### WebSocket Connection Errors (GUI)
-   **Symptom**: "Disconnected" status in the web UI status bar.
-   **Solution**: Ensure the Flask server (`python gemini_chat/gemini_chat.py --gui`) is running. Check the terminal for any server-side errors. Refresh the web page. The GUI uses Server-Sent Events (SSE) for streaming, not WebSockets directly for the chat stream, so check for SSE compatibility or proxy issues if streaming fails.

#### Model Selector Not Populating (GUI)
-   **Symptom**: Empty model dropdown or "Loading..." in the GUI.
-   **Solution**: The UI fetches models when the model selector or settings are opened. Check your internet connection and ensure the Gemini API key is correctly configured and has permissions to list models. Look for errors in the browser's developer console and the Flask server terminal.

#### JavaScript Console Errors (GUI)
-   If you encounter JavaScript errors in the browser console, please report them as issues on the repository, including the error message and steps to reproduce.

### Browser Compatibility (GUI)

The web interface is generally expected to work on modern browsers:
- Chrome 90+
- Firefox 88+
- Edge 90+
- Safari 14+

## License

MIT License
```