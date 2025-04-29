# AI Chat Manager Tools

This directory contains utility scripts and tools for managing the AI Chat Manager application.

## Available Tools

- **Launch_App.bat** - Comprehensive launcher with dependency checking
- **Start_App.bat** - Simple application launcher
- **Stop_App.bat** - Gracefully stops the application
- **run_backend.py** - Script to run just the backend server
- **run_frontend.bat** - Script to run just the frontend server
- **run_dev.py** - Development mode script for running both frontend and backend
- **setup.py** - Initial setup and dependency installation

## Usage

Most users should use the `START_APP.bat` file in the root directory, which provides a simple way to launch the application.

### First-time Setup

When setting up the project for the first time:

```bash
# Navigate to the tools directory
cd tools

# Run the setup script
python setup.py
```

### Development Workflow

1. Start just the backend:
   ```bash
   python run_backend.py
   ```

2. Start just the frontend:
   ```bash
   run_frontend.bat
   ```

3. Stop running servers:
   ```bash
   Stop_App.bat
   ```
