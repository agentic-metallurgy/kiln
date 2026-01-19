#!/bin/bash
set -e

PYTHON_VERSION="3.13"
BREW_PYTHON="python@${PYTHON_VERSION}"

# Ensure Homebrew Python is installed
if ! brew list "$BREW_PYTHON" &>/dev/null; then
    echo "Installing $BREW_PYTHON via Homebrew..."
    brew install "$BREW_PYTHON"
fi

# Get the Homebrew Python path
PYTHON_PATH="$(brew --prefix $BREW_PYTHON)/bin/python${PYTHON_VERSION}"

if [ ! -x "$PYTHON_PATH" ]; then
    echo "Error: Could not find Python at $PYTHON_PATH"
    exit 1
fi

echo "Using Python: $PYTHON_PATH"

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON_PATH" -m venv .venv
fi

source .venv/bin/activate

# Clean up corrupted pip distributions (e.g., ~ygments leftover directories)
rm -rf .venv/lib/python*/site-packages/~*

# Upgrade pip first
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install --force-reinstall -e ".[dev]"

python -m src.cli "$@"
