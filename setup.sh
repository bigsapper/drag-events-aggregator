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
echo "Recommended: create a local .env file in the project root:"
echo '  printf "%s\n" "ANTHROPIC_API_KEY=your_api_key_here" > .env'
echo ""
echo "Alternatives:"
echo '  export ANTHROPIC_API_KEY="your_api_key_here"'
echo '  export ANTHROPIC_API_KEY_FILE="/path/to/anthropic_api_key"'
