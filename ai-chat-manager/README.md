# AI Chat Manager

A portable, scalable, open-source browser-based application for managing conversation threads with AI chat interfaces such as OpenAI or Google's Gemini models.

## Features

- Converse with AI chat models through a responsive browser interface
- Switch between different AI providers and models
- Customize model settings (temperature, max tokens, etc.)
- Manage and save conversation threads
- Dark mode support
- Real-time streaming of AI responses

## Project Structure

```
ai-chat-manager/
├── backend/                      # Python FastAPI backend
│   ├── app/                      # Application code
│   │   ├── api/                  # API endpoints
│   │   ├── models/               # Data models
│   │   ├── services/             # Business logic
│   │   └── core/                 # Core functionality
│   ├── utils/                    # Utilities including logging
│   └── main.py                   # Entry point
│
├── frontend/                     # React frontend
│   ├── public/                   # Static files
│   └── src/
│       ├── components/           # UI components
│       ├── hooks/                # Custom React hooks
│       ├── services/             # API client code
│       └── store/                # State management
│
├── tools/                        # Utility scripts
│   ├── Launch_App.bat            # Main launcher with dependency checks
│   ├── Start_App.bat             # Simple starter script
│   ├── Stop_App.bat              # Application shutdown script
│   └── setup.py                  # Setup and installation script
│
├── data/                         # Data storage
├── logs/                         # Application logs
├── docker/                       # Docker configuration
└── START_APP.bat                 # Root launcher shortcut
```

## Technology Stack

- **Backend**:
  - Python with FastAPI
  - SQLAlchemy ORM
  - WebSockets for real-time communication
  - SQLite database (can be swapped for other databases)

- **Frontend**:
  - React with TypeScript
  - TailwindCSS for styling
  - React Router for navigation
  - Zustand for state management

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- API keys for OpenAI, Google, or other providers you want to use

### Installation

1. Clone the repository
```bash
git clone https://github.com/yourusername/ai-chat-manager.git
cd ai-chat-manager
```

2. Run the setup script
```bash
cd tools
python setup.py
```
This will:
- Install backend dependencies
- Set up environment variables
- Initialize the database
- Install frontend dependencies

### Running the application

#### Option 1: Using the launcher (Recommended)

Simply double-click on `START_APP.bat` in the project root directory.

This will:
- Start the backend server
- Start the frontend development server
- Open your browser to http://localhost:3000

#### Option 2: Manual startup

1. Start the backend server
```bash
cd tools
python run_backend.py
```

2. In a separate terminal, start the frontend server
```bash
cd tools
run_frontend.bat
```

3. Open your browser and navigate to `http://localhost:3000`

#### Using Docker

```bash
docker-compose up
```

Then open your browser and navigate to `http://localhost`

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## TODO

- [ ] Implement authentication and user management
- [ ] Add support for more AI providers
- [ ] Implement conversation export/import features
- [ ] Add file upload capabilities for context
- [ ] Improve error handling and rate limiting
- [ ] Create desktop application version with Electron
