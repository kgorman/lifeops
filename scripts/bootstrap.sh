#!/usr/bin/env bash
# Bootstrap the Life Ops dev environment.
#  - verifies uv is installed
#  - creates a uv venv in each package
#  - installs each package editable
#  - creates the local config dir
set -euo pipefail

LIFEOPS_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

echo "==> bootstrapping todos-mcp"
cd "$LIFEOPS_DIR/todos-mcp"
uv venv
uv pip install -e .

echo "==> bootstrapping todos-agent"
cd "$LIFEOPS_DIR/todos-agent"
uv venv
uv pip install -e .

CONFIG_DIR="$HOME/.config/lifeops"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/env" ]; then
  cp "$LIFEOPS_DIR/.env.example" "$CONFIG_DIR/env"
  echo "==> wrote $CONFIG_DIR/env — edit it before running services"
fi

if [ ! -f "$CONFIG_DIR/owner_context.md" ]; then
  cp "$LIFEOPS_DIR/templates/owner_context.example.md" "$CONFIG_DIR/owner_context.md"
  echo "==> wrote $CONFIG_DIR/owner_context.md — fill in your household details"
fi

mkdir -p "$HOME/logs"
echo "==> done. next: edit $CONFIG_DIR/env then run scripts/install-launchd.sh"
