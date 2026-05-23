#!/usr/bin/env bash
# Walks you through setting up a Cloudflare Tunnel for the MCP server.
# Idempotent — safe to re-run.
set -euo pipefail

TUNNEL_NAME="${TUNNEL_NAME:-todos-mcp}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found. install with: brew install cloudflared"
  exit 1
fi

if [ ! -f "$HOME/.cloudflared/cert.pem" ]; then
  echo "==> you need to log in to Cloudflare first:"
  echo "    cloudflared tunnel login"
  exit 1
fi

if ! cloudflared tunnel list | grep -q "^[a-z0-9-]\+ \+${TUNNEL_NAME} "; then
  echo "==> creating tunnel $TUNNEL_NAME"
  cloudflared tunnel create "$TUNNEL_NAME"
fi

if [ ! -f "$HOME/.cloudflared/config.yml" ]; then
  echo "==> creating $HOME/.cloudflared/config.yml — edit it to add your hostname"
  cp "$(dirname "$0")/../cloudflared/config.yml.example" "$HOME/.cloudflared/config.yml"
fi

echo "==> next steps:"
echo "    1. edit $HOME/.cloudflared/config.yml (hostname, credentials path)"
echo "    2. cloudflared tunnel route dns $TUNNEL_NAME <hostname>"
echo "    3. cloudflared tunnel run $TUNNEL_NAME    (or run it as a service)"
