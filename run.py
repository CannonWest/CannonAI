#!/usr/bin/env python3
"""
Convenience script to run the OpenAI Chat application.
Updated to use the fully asynchronous architecture.
"""

import sys
import os
import logging

# Ensure src directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the main function from the updated async main file
from src.main import main

if __name__ == "__main__":
    sys.exit(main())