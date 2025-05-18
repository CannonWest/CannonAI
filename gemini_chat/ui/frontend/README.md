# Gemini Chat React Frontend

This directory contains the React frontend for the Gemini Chat application. It provides a modern, responsive user interface for interacting with Google's Gemini AI models.

## Development

### Prerequisites

- Node.js 16+ and npm
- Python 3.6+ with FastAPI backend running

### Getting Started

To start development:

```bash
# Install dependencies
npm install

# Start development server
npm start
```

The development server will run on port 3000 and proxy API requests to the backend server on port 8000. The proxy configuration is defined in `package.json`.

### Building for Production

To build the frontend for production:

```bash
# Build the frontend
npm run build
```

The build output will be in the `build` directory. These files can be served by the FastAPI backend.

### Scripts

- `npm start`: Start the development server
- `npm run build`: Build for production
- `npm test`: Run tests
- `npm run eject`: Eject from Create React App (not recommended)

## Structure

- `public/`: Static assets and HTML template
- `src/`: Source code
  - `components/`: React components
    - `ChatView.jsx`: Main chat interface
    - `ConversationList.jsx`: List of conversations
    - `MessageBubble.jsx`: Individual message component
    - `SettingsPanel.jsx`: Settings interface
  - `services/`: API service functions
    - `api.js`: API client functions
  - `App.js`: Main application component
  - `index.js`: Application entry point

## Features

- Dark mode support
- Real-time streaming of AI responses
- Conversation management
- Markdown rendering with syntax highlighting
- Mobile-responsive design
- Settings management

## Dependencies

- React: UI library
- Material-UI: Component library for styling
- react-markdown: Markdown rendering
- react-syntax-highlighter: Code syntax highlighting
- react-use-websocket: WebSocket communication for streaming
- axios: HTTP client for API communication
