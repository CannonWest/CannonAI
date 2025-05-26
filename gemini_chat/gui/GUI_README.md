# Gemini Chat GUI Documentation

## Overview

The Gemini Chat GUI provides a modern, web-based interface for interacting with Google's Gemini AI models. Built with Flask and Bootstrap, it offers a clean, responsive design with all the functionality of the CLI version.

## Quick Start

### 1. Install Dependencies

```bash
# Install GUI-specific dependencies
pip install -r gemini_chat/gui_requirements.txt

# Or install manually
pip install flask flask-cors
```

### 2. Configure API Key

You need a Google Gemini API key. Set it up using one of these methods:

```bash
# Option 1: Environment variable
export GEMINI_API_KEY='your-api-key-here'

# Option 2: Configuration wizard
python gemini_chat/gemini_chat.py --setup

# Option 3: Command-line argument
python gemini_chat/gemini_chat.py --gui --api-key 'your-api-key-here'
```

### 3. Launch the GUI

```bash
python gemini_chat/gemini_chat.py --gui
```

The GUI will automatically open in your default web browser at `http://127.0.0.1:8080`.

## Features

### 1. **Conversation Management**

- **New Conversations**: Click the "+" button in the sidebar or use the `/new` command
- **Save Conversations**: Conversations auto-save, or click "Save Conversation" in the sidebar
- **Load Previous Conversations**: Click on any conversation in the sidebar list
- **View History**: All messages are displayed in the main chat area

### 2. **Model Selection**

- Click on the current model name in the header
- Choose from available Gemini models
- Models display their token limits and capabilities

### 3. **Streaming Responses**

- Toggle streaming mode using the "Toggle Streaming" option
- Watch responses appear in real-time
- Streaming status is shown in the status bar

### 4. **Customizable Parameters**

Access the Settings modal to adjust:
- **Temperature** (0.0-2.0): Controls response creativity
- **Max Output Tokens**: Maximum response length
- **Top-p** (0.0-1.0): Nucleus sampling parameter
- **Top-k**: Vocabulary limiting parameter

### 5. **Command Support**

All CLI commands work in the GUI by typing them in the message input:
- `/new [title]` - Start a new conversation
- `/save` - Save current conversation
- `/list` - List all conversations
- `/load [name/number]` - Load a specific conversation
- `/model [name]` - Change the AI model
- `/stream` - Toggle streaming mode
- `/help` - Show available commands

## User Interface Components

### Header Bar
- **Application Title**: Shows "Gemini Chat" and current conversation name
- **Model Selector**: Click to change the active model
- **Settings Button**: Access generation parameters

### Sidebar
- **Conversation List**: All saved conversations with metadata
- **New Conversation Button**: Start fresh conversations
- **Quick Actions**: Save, view history, toggle streaming

### Main Chat Area
- **Message Display**: Color-coded messages (blue for user, green for AI)
- **Thinking Indicator**: Shows when AI is processing
- **Input Field**: Type messages or commands
- **Send Button**: Submit messages (or press Enter)

### Status Bar
- **Connection Status**: Green when connected, red when disconnected
- **Streaming Mode**: Shows if streaming is enabled
- Real-time status updates

## Interactive Elements

### Modals

1. **New Conversation Modal**
   - Enter a custom title or leave blank for auto-generated
   - Creates a new conversation immediately

2. **Model Selector Modal**
   - Displays all available models in a table
   - Shows token limits and capabilities
   - One-click model switching

3. **Settings Modal**
   - Sliders for temperature and top-p
   - Input fields for max tokens and top-k
   - Toggle switch for streaming mode
   - Changes apply immediately

### Responsive Design

- Works on desktop, tablet, and mobile devices
- Sidebar collapses on smaller screens
- Touch-friendly interface elements
- Optimized for various screen sizes

## Technical Details

### Architecture

- **Backend**: Flask server with async support
- **Frontend**: Vanilla JavaScript with Bootstrap 5
- **Communication**: RESTful API + Server-Sent Events (SSE)
- **State Management**: Server-side with client synchronization

### API Endpoints

- `GET /api/status` - Get client status
- `GET /api/models` - List available models
- `GET /api/conversations` - List saved conversations
- `POST /api/conversation/new` - Create new conversation
- `POST /api/conversation/load` - Load a conversation
- `POST /api/conversation/save` - Save current conversation
- `POST /api/send` - Send message (non-streaming)
- `POST /api/stream` - Send message (streaming)
- `POST /api/settings` - Update settings
- `POST /api/command` - Execute commands

### File Structure

```
gemini_chat/gui/
├── server.py           # Flask server implementation
├── api_handlers.py     # Business logic for API endpoints
├── templates/
│   └── index.html     # Main HTML template
├── static/
│   ├── js/
│   │   └── app.js     # Frontend JavaScript
│   └── css/
│       └── style.css  # Custom styles
└── __init__.py        # Package initialization
```

## Troubleshooting

### Common Issues

1. **"Client not initialized" error**
   - Ensure your API key is configured correctly
   - Check the terminal for initialization errors
   - Restart the server if needed

2. **Streaming not working**
   - Check browser console for errors
   - Ensure your browser supports Server-Sent Events
   - Try disabling browser extensions

3. **Conversations not loading**
   - Verify the conversations directory exists
   - Check file permissions
   - Look for error messages in the terminal

### Browser Compatibility

Tested and supported on:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

### Debug Mode

The Flask server runs in debug mode by default, providing:
- Detailed error messages
- Auto-reload on code changes
- Enhanced logging output

## Advanced Usage

### Custom Configuration

You can customize the GUI behavior by modifying:
- `gui/server.py` - Server settings and routes
- `gui/static/js/app.js` - Frontend behavior
- `gui/static/css/style.css` - Visual styling

### Integration

The GUI can be integrated into larger applications:
- Import `start_gui_server` from `gui.server`
- Pass custom configuration objects
- Extend API endpoints as needed

### Security Considerations

For production use:
- Change the Flask secret key in `server.py`
- Implement authentication if needed
- Use HTTPS for secure communication
- Validate all user inputs

## Tips and Best Practices

1. **Conversations**: Name your conversations descriptively for easy retrieval
2. **Models**: Start with gemini-2.0-flash for faster responses
3. **Streaming**: Enable for long responses to see progress
4. **Parameters**: Lower temperature for factual responses, higher for creativity
5. **Commands**: Use `/help` to see all available commands

## Future Enhancements

Planned features include:
- Markdown rendering with syntax highlighting
- File upload support
- Conversation export options
- Theme customization
- Multi-language support

## Support

If you encounter issues:
1. Check the terminal output for error messages
2. Review the browser console for JavaScript errors
3. Ensure all dependencies are properly installed
4. Refer to the main README for general troubleshooting

---

Enjoy using the Gemini Chat GUI! For more information, see the main project documentation.
