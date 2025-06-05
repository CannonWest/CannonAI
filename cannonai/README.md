# **CannonAI**

A powerful, modular application for interacting with Google's Gemini AI models, supporting both command-line and web interfaces.

## **Features**

* Multi-turn conversations with Google's Gemini models and other supported providers (Claude, OpenAI \- placeholder implementations).  
* Select from available AI models.  
* Customize generation parameters (temperature, max tokens, etc.).  
* Save and load conversations as JSON files.  
* Navigate between different saved conversations.  
* Full conversation history management, including retrying messages and navigating alternative responses (branching).  
* Support for both streaming and non-streaming responses.  
* Provider-agnostic asynchronous client at its core.  
* Cross-platform terminal colors for CLI.  
* Persistent configuration system.  
* Web-based user interface using Flask and Bootstrap, featuring:  
  * Markdown rendering with syntax highlighting for code blocks.  
  * Visual conversation management.  
  * Intuitive settings interface.  
  * Real-time streaming with visual feedback.

## **Project Structure**

The application is organized with a modular architecture:

CannonAI\_GIT/                 \# Your main project root  
├── cannonai/                 \# Main application code  
│   ├── cannonai.py           \# Single unified entry point  
│   ├── base\_client.py        \# Core shared functionality (conversation structure, file I/O)  
│   ├── async\_client.py       \# Asynchronous, provider-agnostic client  
│   ├── command\_handler.py    \# Command processing for CLI mode  
│   ├── client\_manager.py     \# Client creation and provider management  
│   ├── config.py             \# Configuration management  
│   ├── providers/            \# AI Provider implementations  
│   │   ├── \_\_init\_\_.py  
│   │   ├── base\_provider.py  
│   │   ├── gemini\_provider.py  
│   │   ├── claude\_provider.py  \# Placeholder  
│   │   └── openai\_provider.py  \# Placeholder  
│   ├── gui/                  \# Web interface implementation (Flask)  
│   │   ├── server.py         \# Flask server for web UI  
│   │   ├── api\_handlers.py   \# Business logic for API endpoints  
│   │   ├── static/           \# Static UI assets (CSS, JS)  
│   │   ├── templates/        \# HTML templates  
│   │   ├── \_\_init\_\_.py  
│   │   └── GUI\_README.md     \# Detailed documentation for the GUI  
│   ├── \_\_init\_\_.py           \# Package initialization  
│   └── requirements.txt      \# Core and GUI dependencies  
├── cannonai\_config/          \# Configuration storage (auto-created)  
│   └── cannonai\_config.json  \# Default configuration file  
└── cannonai\_conversations/   \# Saved conversations (auto-created)

## **Installation**

1. Clone this repository:  
   git clone \[https://github.com/yourusername/CannonAI.git\](https://github.com/yourusername/CannonAI.git)  
   cd CannonAI

2. Install the required dependencies:  
   \# Core and Web UI (Flask) dependencies are in one file  
   pip install \-r cannonai/requirements.txt

3. Set up your API key(s) (choose one method):  
   * Set as environment variables (e.g., GEMINI\_API\_KEY, CLAUDE\_API\_KEY, OPENAI\_API\_KEY):  
     \# Linux/macOS  
     export GEMINI\_API\_KEY='your\_gemini\_api\_key\_here'

     \# Windows  
     set GEMINI\_API\_KEY=your\_gemini\_api\_key\_here

   * Run the configuration wizard (will prompt for keys for supported providers):  
     python cannonai/cannonai.py \--setup

   * For CLI mode, you can pass an API key for the *active provider* for that session (ignored if \--gui is used):  
     python cannonai/cannonai.py \--provider gemini \--api-key 'your\_gemini\_api\_key\_here'

## **Usage**

### **Running the Application**

python cannonai/cannonai.py \[options\]

### **Command-line Arguments**

python cannonai/cannonai.py \--help

Available arguments:

* \--api-key: (CLI Mode Only) Specify API key for the active provider. Overrides config and environment variables for the session. Ignored if \--gui is used.  
* \--provider: AI provider to use (e.g., gemini, claude, openai). Defaults to provider set in config.  
* \--model: Specify the model to use (e.g., gemini-2.0-flash, claude-3-opus-20240229). Overrides provider's default model in config.  
* \--dir, \--conversations-dir: Directory to store conversations.  
* \--gui: Launch with the web-based user interface (Flask \+ Bootstrap).  
* \--setup: Run the configuration setup wizard.  
* \--config: Specify a custom configuration file path.  
* \--quiet: Suppress non-essential output messages.

Advanced options (override config for the session):

* \--temp, \--temperature: Generation temperature (0.0-2.0).  
* \--max-tokens: Maximum output tokens.  
* \--top-p: Top-p sampling parameter (0.0-1.0).  
* \--top-k: Top-k sampling parameter.  
* \--stream / \--no-stream: Enable/disable streaming mode by default for this session.

## **User Interface Modes**

The application supports two different user interface modes:

### **Command-Line Interface (CLI) Mode**

This is the default mode when running the application without the \--gui flag:

python cannonai/cannonai.py

The CLI mode provides a traditional terminal-based interface with command-line commands.

### **Web Interface Mode**

The web interface provides a more user-friendly experience with the same core functionality:

python cannonai/cannonai.py \--gui

When using the web UI mode:

* A local web server will start (default: http://127.0.0.1:8080).  
* Your default web browser will automatically open to the CannonAI interface.  
* Many commands available in CLI mode are accessible through UI interactions or by typing them into the chat input.  
* The web interface provides a visual experience with Markdown rendering, syntax highlighting, and easier conversation management.

**Note**: To use the web interface, ensure you have installed the dependencies from cannonai/requirements.txt, which includes Flask and Flask-CORS.

### **Commands During Chat (CLI and GUI via input field)**

During the chat session, you can use the following commands:

| Command | Description |
| :---- | :---- |
| /help | Show help message |
| /quit | Save and exit the application (CLI) |
| /save | Save the current conversation |
| /new | Start a new conversation |
| /list | List saved conversations |
| /load | Load a saved conversation |
| /history | Display conversation history (CLI) |
| /model | Select a different model for current provider |
| /params | Customize generation parameters (CLI) |
| /stream | Toggle streaming mode for current session/conv |
| /clear | Clear the screen (CLI) |
| /config | Open configuration setup wizard (CLI) |
| /version | Show version information |

## **Conversation Storage**

Conversations are saved as JSON files in the cannonai\_conversations directory (by default, adjacent to the cannonai directory). The conversation structure (v2.3.0+) includes:

* A unique conversation\_id.  
* metadata including title, timestamps, provider, model, parameters, active branch, active leaf, and system instruction.  
* A messages dictionary where each message has an ID, parent ID, branch ID, type (user/assistant), content, timestamp, children, and potentially attachments or token usage.  
* A branches dictionary to track different lines of conversation.

You can manage conversations through commands (CLI/GUI input) or UI elements (GUI).

## **Configuration System**

The application uses a persistent configuration system. Configuration is stored in cannonai\_config/cannonai\_config.json (by default).

Configuration options include:

* API keys for supported providers (gemini, claude, openai).  
* Default provider.  
* Default models for each provider.  
* Conversations directory.  
* Default generation parameters.  
* Default streaming mode.  
* Global default system instruction (for new conversations).

Run the configuration wizard to set up or modify your configuration:

python cannonai/cannonai.py \--setup

## **Provider-Agnostic Design**

The application is designed to be provider-agnostic via BaseAIProvider. The AsyncClient interacts with a provider instance (e.g., GeminiProvider).

* **Gemini**: Fully implemented.  
* **Claude, OpenAI**: Placeholder implementations exist in cannonai/providers/. Full integration is pending.

## **Getting an API Key**

To use this application, you need an API key for your chosen provider(s):

* **Google Gemini**: Visit [Google AI Studio](https://ai.google.dev/).  
* **Anthropic Claude**: Visit [Anthropic Console](https://console.anthropic.com/).  
* **OpenAI**: Visit [OpenAI Platform](https://platform.openai.com/).

## **Development**

### **Running Tests**

(Assuming tests are set up in a tests/ directory, which is not present in the provided file list)

pytest tests/

## **Requirements**

* Python 3.6 or higher  
* google-genai package (\>=0.5.0)  
* tabulate package (\>=0.9.0)  
* colorama package (\>=0.4.4)

### **Web UI Additional Requirements (included in cannonai/requirements.txt)**

* flask (\>=2.3.0)  
* flask-cors (\>=4.0.0)  
* asyncio (\>=3.4.3)

## **Supported Models (Examples)**

CannonAI supports multiple AI models from different providers. The client attempts to fetch available models from the active provider's API.

**Google Gemini:**

* gemini-2.0-flash \- Fast model, good for quick responses.  
* gemini-pro / gemini-1.5-pro-latest \- More advanced models.  
* gemini-1.5-flash-latest

**Anthropic Claude (Placeholder):**

* claude-3-opus-20240229  
* claude-3-sonnet-20240229  
* claude-3-haiku-20240307

**OpenAI GPT (Placeholder):**

* gpt-4-turbo  
* gpt-3.5-turbo  
* gpt-4o

Model availability may vary. The application allows selection from models that support content generation for the active provider.

## **Troubleshooting**

### **Common Issues**

#### **API Key Errors**

* **Symptom**: "API key not found" or authentication errors.  
* **Solution**: Ensure your API key is correctly set via environment variable, the config wizard (python cannonai/cannonai.py \--setup), or for CLI, the \--api-key argument for the active provider. Verify the key is valid and has permissions.

#### **WebSocket Connection Errors (GUI)**

* **Symptom**: "Disconnected" status in the web UI status bar.  
* **Solution**: Ensure the Flask server (python cannonai/cannonai.py \--gui) is running. Check the terminal for any server-side errors. Refresh the web page. The GUI uses Server-Sent Events (SSE) for streaming.

#### **Model Selector Not Populating (GUI)**

* **Symptom**: Empty model dropdown or "Loading..." in the GUI.  
* **Solution**: Check your internet connection and ensure the API key for the active provider is correctly configured and has permissions to list models. Look for errors in the browser's developer console and the Flask server terminal.

## **License**

MIT License