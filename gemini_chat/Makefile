# CannonAI CLI Makefile

.PHONY: install test lint run run-async clean help

# Default target when just running 'make'
.DEFAULT_GOAL := help

# Project variables
PYTHON := python
PIP := pip
PROJECT_NAME := cannonai
TEST_DIR := tests
VENV_DIR := venv

# Help command
help:
	@echo "CannonAI CLI Makefile commands:"
	@echo ""
	@echo "Usage:"
	@echo "  make install    - Install dependencies"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linters"
	@echo "  make run        - Run in sync mode"
	@echo "  make run-async  - Run in async mode"
	@echo "  make clean      - Clean up generated files"
	@echo "  make help       - Show this help message"
	@echo ""

# Install dependencies
install:
	$(PIP) install -r requirements.txt

# Run tests
test:
	pytest $(TEST_DIR)

# Run linters
lint:
	@echo "Running linters..."
	@command -v flake8 >/dev/null 2>&1 || (echo "flake8 not found, installing..." && $(PIP) install flake8)
	flake8 $(PROJECT_NAME)

# Run in sync mode
run:
	$(PYTHON) $(PROJECT_NAME).py

# Run in async mode
run-async:
	$(PYTHON) $(PROJECT_NAME).py --async

# Clean up generated files
clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".coverage" -exec rm -rf {} +
	@echo "Cleanup complete!"
