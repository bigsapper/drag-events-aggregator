#!/usr/bin/env bash
# Sets up the project environment.
# Run once before first use.

set -e

# Install pip if missing
sudo apt-get install -y python3-pip python3-venv

# Create virtual environment
python3 -m venv .venv

# Activate and install dependencies
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt

echo ""
echo "Setup complete. To activate the environment:"
echo "  source .venv/bin/activate"
echo ""
echo "Copy .env.example to .env and add your Anthropic API key:"
echo "  cp .env.example .env"
