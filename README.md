# OpenAI Chat Application

A desktop application for interacting with OpenAI's language models with advanced conversation management, including conversation branches, retry functionality, and persistent storage.

## Features

- **Modern PyQt6 UI** with dark mode and responsive design
- **Multiple conversation management** with tabbed interface
- **Conversation branching** with tree visualization
- **Retry functionality** to generate alternative responses
- **Chain of thought display** for reasoning steps
- **Full model configuration** with support for all API parameters
- **Model-specific settings** (e.g., reasoning_effort for o1 and o3 models)
- **Persistent storage** of conversations and settings
- **Detailed token usage information**

## Installation

1. Clone the repository:
```bash
git clone https://github.com/your-username/openai-chat-app.git
cd openai-chat-app
```

2. Create a virtual environment (optional but recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:
```bash
python -m src.main
```

2. The application will start with a default conversation. You can:
   - Create new conversations using the "+" button in the tab bar
   - Send messages using the input field and send button
   - Retry responses using the "Retry" button
   - Navigate between conversation branches using the tree view
   - Configure model settings using the "Settings" button

## Configuration

The application stores its configurations in two locations:
- `config/settings.json`: Stores model parameters and preferences
- `data/conversations/`: Stores conversation data as JSON files

## Project Structure

```
openai-chat-app/
├── src/                    # Source code directory
│   ├── __init__.py         # Makes the directory a package
│   ├── main.py             # Entry point for the application
│   ├── models/             # Data models
│   │   ├── __init__.py
│   │   └── conversation.py # Conversation tree data model
│   ├── ui/                 # UI components
│   │   ├── __init__.py
│   │   ├── components.py   # Reusable UI components
│   │   ├── conversation.py # Conversation UI components
│   │   ├── settings.py     # Settings dialog
│   │   └── main_window.py  # Main application window
│   ├── services/           # Business logic
│   │   ├── __init__.py
│   │   ├── api.py          # OpenAI API interaction
│   │   └── storage.py      # Persistence layer
│   └── utils/              # Utility functions
│       ├── __init__.py
│       └── constants.py    # Constants and configuration
├── data/                   # Data directory
│   └── conversations/      # Saved conversations
├── config/                 # Configuration files
│   └── settings.json       # Application settings
├── requirements.txt        # Dependencies
└── README.md               # Documentation
```

## Development

### Code Style

The project uses:
- [Black](https://black.readthedocs.io/) for code formatting
- [isort](https://pycqa.github.io/isort/) for import sorting
- [flake8](https://flake8.pycqa.org/) for linting

To format the code:
```bash
black src
isort src
flake8 src
```

### Testing

To run the tests:
```bash
pytest
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [OpenAI](https://openai.com/) for providing the API used in this application
