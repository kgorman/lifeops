# todos-agent

Hourly Claude Agent SDK loop that works delegated Life Ops todos.

**Auth:** the agent uses the local `claude` CLI's OAuth session (via the
[Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/)). Run
`claude login` once on the machine — **no `ANTHROPIC_API_KEY` is required.**
Your Pro/Max/Team subscription is what powers the agent loop.

## Install

```bash
uv venv
uv pip install -e .
```

## Run once (debugging)

```bash
uv run todos-agent
```

## Behavior

Each run:

1. Pulls the latest from `TODOS_REPO`.
2. Scans every namespace for files where `assignee: claude` and `status: delegated|in_progress`.
3. For each (up to `AGENT_MAX_ITEMS`):
   - flips status to `in_progress`, commits, pushes
   - creates an `agent/<slug>-<date>` branch
   - builds a prompt from title + context + instructions + household context
   - invokes Claude Code SDK with web search + file tools
   - parses output, writes `## Agent findings` and `## Decision needed`
   - flips to `needs_review` (or `blocked` with reason)
   - opens a PR linked to the GitHub Issue

## Household context

The agent injects a "household background" block into every prompt. That block lives in `$OWNER_CONTEXT_FILE` (default `~/.config/lifeops/owner_context.md`) — **never in this repo**. Example:

```markdown
We live in <city>. Vehicles include <list>. Shop tools at <location>.
Preferences: prefer local vendors, avoid Amazon when possible…
```

The agent gracefully runs without it; you just get less-tuned recommendations.
