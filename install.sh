#!/usr/bin/env bash
# Life Ops installer.
#
# Usage:
#   ./install.sh            # full install: prereqs, venvs, config dir
#   ./install.sh --no-services   # skip launchd install
#   ./install.sh --with-tunnel   # also run setup-tunnel.sh
#
# Idempotent — safe to re-run.

set -euo pipefail

LIFEOPS_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_SERVICES=1
INSTALL_TUNNEL=0

for arg in "$@"; do
  case "$arg" in
    --no-services) INSTALL_SERVICES=0 ;;
    --with-tunnel) INSTALL_TUNNEL=1 ;;
    -h|--help)
      sed -n '2,9p' "$0" | sed 's/^# //; s/^#//'
      exit 0
      ;;
    *) echo "unknown arg: $arg" >&2; exit 1 ;;
  esac
done

# ---------- helpers ----------

c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_red=$'\033[31m'; c_reset=$'\033[0m'
say()  { printf "%s==>%s %s\n" "$c_green" "$c_reset" "$*"; }
warn() { printf "%s[!]%s %s\n" "$c_yellow" "$c_reset" "$*"; }
fail() { printf "%s[x]%s %s\n" "$c_red" "$c_reset" "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

# ---------- platform ----------

if [ "$(uname)" != "Darwin" ]; then
  warn "Life Ops targets macOS (launchd, iCloud Drive). Continuing, but services/tunnel won't work here."
  INSTALL_SERVICES=0
fi

# ---------- prereqs ----------

say "checking prerequisites"

if ! have git;    then fail "git is required (xcode-select --install)"; fi
if ! have gh;     then warn "gh CLI not found — install with: brew install gh (needed for the data repo + label setup)"; fi

if ! have uv; then
  say "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # shellcheck disable=SC1091
  if [ -f "$HOME/.local/bin/env" ]; then . "$HOME/.local/bin/env"; fi
  export PATH="$HOME/.local/bin:$PATH"
fi
have uv || fail "uv install failed. install manually: https://astral.sh/uv"
say "uv: $(uv --version)"

# uv will manage Python itself; ensure a 3.11+ runtime is available
uv python install 3.12 >/dev/null 2>&1 || true

# ---------- venvs ----------

install_pkg() {
  local pkg="$1"
  say "installing $pkg"
  ( cd "$LIFEOPS_DIR/$pkg" && uv venv --python 3.12 --quiet --allow-existing && uv pip install --quiet -e . )
}

install_pkg todos-mcp
install_pkg todos-agent

# ---------- import smoke test ----------

say "verifying imports"
( cd "$LIFEOPS_DIR/todos-mcp" && uv run --quiet python -c "import todos_mcp.server; print('todos-mcp ok')" )
( cd "$LIFEOPS_DIR/todos-agent" && uv run --quiet python -c "import todos_agent.agent; print('todos-agent ok')" )

# ---------- config dir ----------

CONFIG_DIR="$HOME/.config/lifeops"
mkdir -p "$CONFIG_DIR" "$HOME/logs"

if [ ! -f "$CONFIG_DIR/env" ]; then
  cp "$LIFEOPS_DIR/.env.example" "$CONFIG_DIR/env"
  warn "wrote $CONFIG_DIR/env — EDIT IT before the services will work"
else
  say "config exists: $CONFIG_DIR/env"
fi

if [ ! -f "$CONFIG_DIR/owner_context.md" ]; then
  cp "$LIFEOPS_DIR/templates/owner_context.example.md" "$CONFIG_DIR/owner_context.md"
  warn "wrote $CONFIG_DIR/owner_context.md — fill in your household details"
fi

# ---------- launchd ----------

if [ "$INSTALL_SERVICES" = "1" ]; then
  say "installing launchd services"
  "$LIFEOPS_DIR/scripts/install-launchd.sh"
else
  warn "skipped launchd (use ./scripts/install-launchd.sh later)"
fi

# ---------- tunnel ----------

if [ "$INSTALL_TUNNEL" = "1" ]; then
  say "setting up Cloudflare Tunnel"
  "$LIFEOPS_DIR/scripts/setup-tunnel.sh"
fi

# ---------- done ----------

cat <<EOF

${c_green}install complete${c_reset}

Next steps:
  1. Edit ${CONFIG_DIR}/env           (GITHUB_TOKEN, ANTHROPIC_API_KEY, TODOS_REPO, TODOS_USER)
  2. Edit ${CONFIG_DIR}/owner_context.md  (household background for the agent)
  3. Create the data repo:
       TODOS_REPO=<your-user>/lifeops_todos ./scripts/init-todos-repo.sh
  4. Sanity check:
       ./scripts/doctor.sh
  5. (Optional) Cloudflare Tunnel:
       ./scripts/setup-tunnel.sh
  6. Wire the MCP endpoint into your Claude client.

EOF
