## User Interface Modes

The application supports two different user interface modes:

### Command-Line Interface (CLI) Mode

This is the default mode when running the application without any UI-related flags:

```bash
python gemini_chat/gemini_chat.py
```

The CLI mode provides a traditional terminal-based interface with command-line commands.

### Web Interface Mode (FastAPI)

The original web interface provides a WebSocket-based experience:

```bash
python gemini_chat/gemini_chat.py --ui
```

When using the web UI mode:
- A FastAPI server will start (default: http://127.0.0.1:8000)
- Uses WebSockets for real-time communication
- Provides a modern, responsive interface

### GUI Mode (Flask + Bootstrap)

The new GUI mode provides a clean, Bootstrap-based interface:

```bash
python gemini_chat/gemini_chat.py --gui
```

When using the GUI mode:
- A Flask web server will start (default: http://127.0.0.1:8080)
- Your default web browser will automatically open to the Gemini Chat GUI
- Uses Server-Sent Events (SSE) for streaming responses
- Interactive modals for user inputs (conversation titles, model selection, etc.)
- Bootstrap-based responsive design
- All CLI commands are available through the graphical interface

#### UI Versions

The application includes two UI versions:
- **Standard UI**: The default web interface (index.html, style.css, main.js)
- **Modern UI**: An enhanced interface with improved styling and features (new_index.html, modern_style.css, modern_main.js)

The modern UI includes additional features:
- Markdown rendering with syntax highlighting for code blocks
- Improved conversation management
- More intuitive settings interface
- Real-time streaming with visual feedback

**Note**: To use the web interfaces, you need to install the additional dependencies:

For FastAPI UI mode:
```bash
pip install -r gemini_chat/ui_requirements.txt
```

For Flask GUI mode:
```bash
pip install -r gemini_chat/gui_requirements.txt
```

# Gemini Chat

A powerful, modular application for interacting with Google's Gemini AI models, supporting both command-line and web interfaces.

[![Python Version](https://img.shields.io/badge/python-3.6%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Features

- Multi-turn conversations with Google's Gemini models
- Select from available Gemini models
- Customize generation parameters (temperature, max tokens, etc.)
- Save and load conversations as JSON files
- Navigate between different saved conversations
- Full conversation history management
- Support for both streaming and non-streaming responses
- Support for both synchronous and asynchronous implementations
- Cross-platform terminal colors
- Persistent configuration system
- Web-based user interface

## Project Structure

The application is organized with a modular architecture to minimize redundancy:

```
CannonAI_GIT/
├── gemini_chat/                  # Main application code
│   ├── gemini_chat.py            # Single unified entry point
│   ├── base_client.py            # Core shared functionality
│   ├── sync_client.py            # Synchronous implementation
│   ├── async_client.py           # Asynchronous implementation
│   ├── command_handler.py        # Command processing for both modes
│   ├── client_manager.py         # Client creation and management
│   ├── config.py                 # Configuration management
│   ├── ui/                       # Web interface implementation
│   │   ├── server.py             # FastAPI server for web UI
│   │   ├── websocket_fix.py      # WebSocket handling improvements
│   │   ├── static/               # Static UI assets
│   │   │   ├── css/style.css     # UI styling
│   │   │   ├── js/main.js        # UI JavaScript functionality
│   │   │   └── index.html        # Main UI template
│   │   └── deprecated/           # Legacy code kept for reference
│   ├── __init__.py               # Package initialization
│   ├── requirements.txt          # Core dependencies
│   ├── ui_requirements.txt       # Web UI dependencies
│   └── tests/                    # Test suite
├── gemini_chat_config/           # Configuration storage
└── gemini_chat_conversations/    # Saved conversations (auto-created)
```

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/CannonAI.git
   cd CannonAI
   ```

2. Install the required dependencies:
   ```bash
   # Core dependencies
   pip install -r gemini_chat/requirements.txt
   
   # Optional: Web UI dependencies (if you want to use the web interface)
   pip install -r gemini_chat/ui_requirements.txt
   ```

3. Set up your API key (choose one method):
   - Set as an environment variable:
     ```bash
     # Linux/macOS
     export GEMINI_API_KEY='your_api_key_here'
     
     # Windows
     set GEMINI_API_KEY=your_api_key_here
     ```
   - Run the configuration wizard:
     ```bash
     python gemini_chat/gemini_chat.py --setup
     ```
   - Pass as a command-line argument:
     ```bash
     python gemini_chat/gemini_chat.py --api-key 'your_api_key_here'
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
- `--api-key`: Specify your Gemini API key (overrides config and environment variable)
- `--model`: Specify the model to use (default: from config or gemini-2.0-flash)
- `--async`: Use asynchronous client implementation
- `--dir`, `--conversations-dir`: Directory to store conversations
- `--ui`: Launch with the web-based user interface
- `--setup`: Run the configuration setup wizard
- `--config`: Specify a custom configuration file path

Advanced options:
- `--temp`, `--temperature`: Generation temperature (0.0-2.0)
- `--max-tokens`: Maximum output tokens
- `--top-p`: Top-p sampling parameter (0.0-1.0)
- `--top-k`: Top-k sampling parameter
- `--stream`: Enable streaming mode by default

### Commands During Chat

During the chat session, you can use the following commands:

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

Conversations are saved as JSON files in the `gemini_chat_conversations` directory, which is automatically created adjacent to the `gemini_chat` directory. Each conversation includes:

- Metadata (model, parameters, timestamps)
- Complete message history
- Token usage statistics (when available)

You can navigate between saved conversations using the `/list` and `/load` commands during a chat session.

## Configuration System

The application uses a persistent configuration system that saves your settings between sessions. Configuration is stored in the `gemini_chat_config` directory adjacent to the `gemini_chat` directory:

```
CannonAI_GIT/
├── gemini_chat/             # Main application code
└── gemini_chat_config/      # Configuration storage
    └── gemini_chat_config.json
```

Configuration options include:
- API key
- Default model
- Conversations directory
- Generation parameters
- Default streaming mode

Run the configuration wizard to set up or modify your configuration:
```bash
python gemini_chat/gemini_chat.py --setup
```

## Sync vs Async Mode

The application supports both synchronous and asynchronous operations:

- **Synchronous Mode (Default)**: Traditional mode where operations block until completed
- **Asynchronous Mode**: Non-blocking mode for better responsiveness with I/O operations

Use asynchronous mode when working with:
- High-volume API requests
- Applications that need to remain responsive during network operations
- Integration with other asynchronous systems

To enable asynchronous mode:
```bash
python gemini_chat/gemini_chat.py --async
```

## Getting an API Key

To use this application, you need a Google Gemini API key:

1. Visit the [Google AI Studio](https://ai.google.dev/)
2. Sign in with your Google account
3. Create a new API key from the settings page
4. Copy and use this key with the application

## Development

### Running Tests

```bash
pytest gemini_chat/tests/
```

### Using the Makefile

A Makefile is provided for common development tasks:

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
- `google-genai` package (≥ 0.5.0)
- `tabulate` package (≥ 0.9.0)
- `colorama` package (≥ 0.4.4)

### Web UI Additional Requirements
- `fastapi` (≥ 0.68.0)
- `uvicorn` (≥ 0.15.0)
- `websockets` (≥ 10.0)
- `jinja2` (≥ 3.0.0) 
- `markdown` (for rendering markdown in the modern UI)
- `pygments` (for syntax highlighting in the modern UI)

## Supported Models

Gemini Chat supports multiple Gemini AI models, including:

- **Gemini 2.0 Flash** - Fastest model, good for quick responses
- **Gemini 2.0 Pro** - More advanced model with better reasoning capabilities
- **Gemini 2.0 Vision** - Model with support for image understanding

Model availability may vary based on your API access level and Google's current offerings.

## Troubleshooting

### Common Issues

#### WebSocket Connection Errors
- **Symptom**: "Not connected to server" messages in the web UI
- **Solution**: Check that the server is running and refresh the page. The UI will automatically attempt to reconnect.

#### Model Selector Not Populating
- **Symptom**: Empty model dropdown in settings
- **Solution**: The UI automatically fetches available models when the settings sidebar is opened. If this fails, try closing and reopening the settings panel.

#### JavaScript Console Errors
- If you encounter JavaScript errors in the browser console, please report them as issues on the repository.

### Debugging

For WebSocket connection debugging, you can use the diagnostic tools in the `debug` directory:
```bash
python gemini_chat/debug/websocket_diagnostics.py
```

## Browser Compatibility

The web interface has been tested and confirmed working on:
- Chrome 90+
- Firefox 88+
- Edge 90+
- Safari 14+

## License

MIT License
