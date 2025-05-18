# Gemini Chat Web UI

This directory contains the web-based user interface for the Gemini Chat application. It consists of a FastAPI backend server and a React frontend.

## Architecture

- **Backend:** FastAPI server that handles API requests and WebSocket connections
- **Frontend:** React application with Material-UI for a modern, responsive UI

## Directory Structure

```
ui/
├── server.py          # Main FastAPI server
├── routes.py          # API routes
├── websocket.py       # WebSocket handler for streaming
└── frontend/          # React frontend
    ├── public/        # Static files
    ├── src/           # React source code
    │   ├── components/  # React components
    │   ├── services/    # API services
    │   ├── App.js       # Main app component
    │   └── index.js     # App entry point
    ├── package.json   # Dependencies and scripts
    └── README.md      # Frontend README
```

## Running the Web UI

### Building the Frontend

Before running the web UI, you need to build the React frontend:

```bash
# Install dependencies and build the frontend
python build_frontend.py

# For development with hot reloading
python build_frontend.py --dev
```

### Starting the Server

Start the Gemini Chat application with the `--web` flag:

```bash
# Run with default settings
python gemini_chat.py --web

# Specify host and port
python gemini_chat.py --web --host 0.0.0.0 --port 8080

# Use a specific static directory (if the frontend is built elsewhere)
python gemini_chat.py --web --static-dir ./ui/frontend/build
```

Then open a web browser and navigate to http://localhost:8000 (or the host/port you specified).

## Features

- Modern, responsive UI with dark mode support
- Real-time streaming of AI responses via WebSockets
- Conversation management (create, rename, delete)
- Markdown rendering with syntax highlighting for code
- Configuration of model parameters
- Mobile-friendly design

## Development

### Backend

The backend is built with FastAPI and provides:

- RESTful API for conversation management
- WebSocket endpoint for streaming responses
- Session management for multiple clients

To make changes to the backend, modify the `server.py`, `routes.py`, or `websocket.py` files as needed.

### Frontend

The frontend is built with React and Material-UI. To develop the frontend:

1. Run the development server: `python build_frontend.py --dev`
2. Make changes to the files in the `frontend/src` directory
3. The browser will automatically refresh with your changes

## Dependencies

- **Backend:** FastAPI, Uvicorn, WebSockets
- **Frontend:** React, Material-UI, react-markdown, react-use-websocket
