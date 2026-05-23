#!/usr/bin/env bash
# Install the launchd plists for the MCP server and agent loop.
# Substitutes __HOME__ and __LIFEOPS_DIR__ placeholders.
set -euo pipefail

LIFEOPS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$LIFEOPS_DIR/launchd"
LA_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LA_DIR" "$HOME/logs"

render() {
  local src="$1" dst="$2"
  sed -e "s|__HOME__|${HOME}|g" \
      -e "s|__LIFEOPS_DIR__|${LIFEOPS_DIR}|g" \
      "$src" > "$dst"
}

for name in com.lifeops.todos-mcp com.lifeops.todos-agent; do
  src="$PLIST_SRC/$name.plist"
  dst="$LA_DIR/$name.plist"
  echo "==> installing $dst"
  render "$src" "$dst"
  # reload
  launchctl unload "$dst" 2>/dev/null || true
  launchctl load "$dst"
done

echo "==> loaded. status:"
launchctl list | grep lifeops.todos || true
