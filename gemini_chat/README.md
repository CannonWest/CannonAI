# Gemini Chat CLI

A powerful command-line interface for having conversations with Google's Gemini AI models.

## Features

- Multi-turn conversations with Google's Gemini models
- Select from available Gemini models
- Customize generation parameters (temperature, max tokens, etc.)
- Save and load conversations as JSON files
- Navigate between different saved conversations
- Full conversation history management

## Installation

1. Clone this repository or download the files.

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up your API key (choose one method):
   - Set as an environment variable:
     ```
     # Linux/macOS
     export GEMINI_API_KEY='your_api_key_here'
     
     # Windows
     set GEMINI_API_KEY=your_api_key_here
     ```
   - Enter when prompted when running the application
   - Pass as a command-line argument:
     ```
     python gemini_chat.py --api-key 'your_api_key_here'
     ```

## Usage

Run the application:
```
python gemini_chat.py
```

### Command-line arguments

```
python gemini_chat.py --help
```

Available arguments:
- `--api-key`: Specify your Gemini API key (overrides environment variable)
- `--model`: Specify the model to use (default: gemini-2.0-flash)
- `--conversations-dir`: Specify a custom directory to store conversations

### Commands during chat

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
| /clear    | Clear the screen              |

## Conversation Management

Conversations are saved as JSON files in the conversations directory (by default, `~/gemini_chat_conversations`). Each conversation includes:

- Metadata (model, parameters, timestamps)
- Complete message history

You can navigate between different conversations using the `/list` and `/load` commands.

## Getting an API Key

To use this application, you need a Google Gemini API key:

1. Visit the [Google AI Studio](https://ai.google.dev/)
2. Sign in with your Google account
3. Create a new API key from the settings page
4. Copy and use this key with the application

## Requirements

- Python 3.6 or higher
- `google-genai` package
- `tabulate` package

## License

MIT License
