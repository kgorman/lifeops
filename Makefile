# Life Ops convenience targets.
# Run `make` with no args for the menu.

SHELL := bash

.PHONY: help install data-repo services tunnel doctor uninstall mcp agent clean

help:
	@echo "Life Ops"
	@echo
	@echo "  make install        full install (uv, venvs, config dir, launchd)"
	@echo "  make data-repo      create the GitHub data repo + labels (needs TODOS_REPO env)"
	@echo "  make services       (re)install launchd services"
	@echo "  make tunnel         set up Cloudflare Tunnel"
	@echo "  make doctor         diagnose the install"
	@echo "  make mcp            run the MCP server in the foreground (debug)"
	@echo "  make agent          run one pass of the agent loop (debug)"
	@echo "  make uninstall      remove launchd services"
	@echo "  make clean          remove venvs"

install:
	./install.sh

data-repo:
	./scripts/init-todos-repo.sh

services:
	./scripts/install-launchd.sh

tunnel:
	./scripts/setup-tunnel.sh

doctor:
	./scripts/doctor.sh

mcp:
	cd todos-mcp && uv run todos-mcp

agent:
	cd todos-agent && uv run todos-agent

uninstall:
	./scripts/uninstall-launchd.sh

clean:
	rm -rf todos-mcp/.venv todos-agent/.venv
