#!/usr/bin/env bash
# Diagnose a Life Ops install. Read-only — fixes nothing.
set -u

LIFEOPS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$HOME/.config/lifeops/env"

c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_red=$'\033[31m'; c_reset=$'\033[0m'
PASS=0; WARN=0; FAIL=0
ok()   { printf "  %s✓%s %s\n" "$c_green"  "$c_reset" "$*"; PASS=$((PASS+1)); }
warn() { printf "  %s!%s %s\n" "$c_yellow" "$c_reset" "$*"; WARN=$((WARN+1)); }
bad()  { printf "  %s✗%s %s\n" "$c_red"    "$c_reset" "$*"; FAIL=$((FAIL+1)); }

have() { command -v "$1" >/dev/null 2>&1; }

section() { printf "\n%s\n" "$1"; }

# ---------- prereqs ----------
section "Prerequisites"
have git    && ok "git $(git --version | awk '{print $3}')"     || bad "git missing"
have uv     && ok "uv  $(uv --version | awk '{print $2}')"       || bad "uv missing — run ./install.sh"
have gh     && ok "gh  $(gh --version | head -1 | awk '{print $3}')" || warn "gh CLI missing (only needed for data-repo init + label sync)"
have claude && ok "claude CLI $(claude --version 2>&1 | head -1)" || warn "claude CLI missing — agent loop needs it for auth (install Claude Code + 'claude login')"
have cloudflared && ok "cloudflared $(cloudflared --version 2>&1 | head -1)" || warn "cloudflared missing (only needed for remote MCP)"

# ---------- venvs ----------
section "Virtualenvs"
for pkg in todos-mcp todos-agent; do
  if [ -d "$LIFEOPS_DIR/$pkg/.venv" ]; then
    ok "$pkg/.venv present"
  else
    bad "$pkg/.venv missing — run ./install.sh"
  fi
done

# ---------- imports ----------
section "Imports"
( cd "$LIFEOPS_DIR/todos-mcp"   && uv run --quiet python -c "import todos_mcp.server" 2>/dev/null )   && ok "todos_mcp imports"   || bad "todos_mcp import failed"
( cd "$LIFEOPS_DIR/todos-agent" && uv run --quiet python -c "import todos_agent.agent" 2>/dev/null ) && ok "todos_agent imports" || bad "todos_agent import failed"

# ---------- config ----------
section "Configuration"
if [ -f "$CONFIG" ]; then
  ok "config file: $CONFIG"
  # shellcheck disable=SC1090
  set -a; . "$CONFIG"; set +a
  for var in TODOS_DIR TODOS_REPO TODOS_USER GITHUB_TOKEN; do
    val="${!var:-}"
    if [ -n "$val" ]; then
      case "$var" in
        *TOKEN*|*KEY*) ok "$var set (${val:0:6}…)" ;;
        *) ok "$var=$val" ;;
      esac
    else
      bad "$var is not set"
    fi
  done
  # ANTHROPIC_API_KEY is optional — the agent uses local claude CLI auth.
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    ok "ANTHROPIC_API_KEY set (will override CLI auth)"
  else
    ok "ANTHROPIC_API_KEY unset — using local claude CLI auth"
  fi
else
  bad "$CONFIG missing — run ./install.sh"
fi

# ---------- todos dir + git ----------
section "Todos data"
TODOS_DIR_EXPANDED="$(eval echo "${TODOS_DIR:-}")"
if [ -n "${TODOS_DIR_EXPANDED:-}" ] && [ -d "$TODOS_DIR_EXPANDED" ]; then
  ok "TODOS_DIR exists: $TODOS_DIR_EXPANDED"
  if [ -d "$TODOS_DIR_EXPANDED/.git" ]; then
    branch=$(git -C "$TODOS_DIR_EXPANDED" branch --show-current 2>/dev/null || echo "?")
    remote=$(git -C "$TODOS_DIR_EXPANDED" remote get-url origin 2>/dev/null || echo "")
    ok "git repo on $branch ($remote)"
  else
    bad "$TODOS_DIR_EXPANDED is not a git repo — run ./scripts/init-todos-repo.sh"
  fi
  IFS=',' read -ra OWNER_LIST <<< "${TODOS_OWNERS:-user-a,user-b}"
  OWNER_LIST+=("shared")
  for owner in "${OWNER_LIST[@]}"; do
    owner="${owner// /}"
    [ -d "$TODOS_DIR_EXPANDED/$owner/inbox" ] && ok "$owner/ layout" || warn "$owner/inbox missing"
  done
else
  warn "TODOS_DIR not set or directory missing"
fi

# ---------- owner context ----------
section "Agent context"
OCF="${OWNER_CONTEXT_FILE:-$HOME/.config/lifeops/owner_context.md}"
if [ -f "$OCF" ]; then
  size=$(wc -c < "$OCF" | tr -d ' ')
  if [ "$size" -gt 200 ]; then
    ok "owner_context.md present ($size bytes)"
  else
    warn "owner_context.md exists but is small ($size bytes) — fill it in for better agent results"
  fi
else
  warn "$OCF missing — agent will work but without household context"
fi

# ---------- github ----------
section "GitHub"
if [ -n "${GITHUB_TOKEN:-}" ]; then
  if curl -sf -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user >/dev/null; then
    ok "GITHUB_TOKEN authenticates"
  else
    bad "GITHUB_TOKEN does not authenticate"
  fi
  if [ -n "${TODOS_REPO:-}" ]; then
    if curl -sf -H "Authorization: token $GITHUB_TOKEN" "https://api.github.com/repos/$TODOS_REPO" >/dev/null; then
      ok "data repo accessible: $TODOS_REPO"
    else
      bad "cannot access $TODOS_REPO — wrong name, or token lacks repo scope?"
    fi
  fi
fi

# ---------- launchd ----------
section "Services"
if [ "$(uname)" = "Darwin" ]; then
  for svc in com.lifeops.todos-mcp com.lifeops.todos-agent; do
    if launchctl list "$svc" >/dev/null 2>&1; then
      ok "$svc loaded"
    else
      warn "$svc not loaded — run ./scripts/install-launchd.sh"
    fi
  done
else
  warn "non-macOS: launchd not applicable"
fi

# ---------- MCP port ----------
section "MCP server"
PORT="${MCP_PORT:-8000}"
if have lsof && lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  ok "something is listening on :$PORT"
else
  warn ":$PORT not listening (server stopped or not yet started)"
fi

# ---------- summary ----------
section "Summary"
printf "  %d passed, %d warnings, %d failures\n" "$PASS" "$WARN" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
