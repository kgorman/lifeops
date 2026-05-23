#!/usr/bin/env bash
# Unload and remove the Life Ops launchd services.
set -euo pipefail

LA_DIR="$HOME/Library/LaunchAgents"
for name in com.lifeops.todos-mcp com.lifeops.todos-agent; do
  plist="$LA_DIR/$name.plist"
  if [ -f "$plist" ]; then
    echo "==> unloading $plist"
    launchctl unload "$plist" 2>/dev/null || true
    rm -f "$plist"
  fi
done
echo "==> done"
