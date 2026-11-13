#!/usr/bin/env bash
# KaizenReader Launcher Script
# Automatically activates local virtual environment and launches KaizenReader.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment with uv..."
    uv venv --python /opt/homebrew/bin/python3.12 .venv
    uv pip install --python .venv/bin/python -r requirements.txt
fi

exec .venv/bin/python src/main.py "$@"
