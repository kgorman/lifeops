# Life Ops

> Stephen Covey's 4-quadrant framework, wired into a markdown todo system and an autonomous agent. The agent works your Q3 so you get your Q2 back.

Life Ops is a personal operations system organised around the **time-management matrix** from *The 7 Habits of Highly Effective People*. Every captured item is classified into one of four quadrants. The system then operates on the quadrant — not on a flat list — so that the *quality* of work you do moves over time, not just the volume.

```
                    URGENT              NOT URGENT
                 ┌───────────────────┬────────────────────┐
   IMPORTANT     │   Q1: Do now      │   Q2: Schedule     │
                 │   crises, fires   │   relationships,   │
                 │                   │   health, building │
                 ├───────────────────┼────────────────────┤
   NOT IMPORTANT │   Q3: Delegate    │   Q4: Eliminate    │
                 │   errands, chores │   noise, trivia    │
                 │                   │                    │
                 └───────────────────┴────────────────────┘
```

**The point of the system is to grow Q2.** Q2 is where leverage lives — relationships, training, learning, building. Most people live in Q1 and Q3 and never get there. Life Ops attacks that asymmetry directly:

- **Q1 items** surface immediately in your daily queue. You do them.
- **Q2 items** get protected. The system nudges stale Q2 work so it never drowns.
- **Q3 items** are auto-delegated to a Claude agent that researches, sources, and recommends. You review the result and move on.
- **Q4 items** go straight to `someday/` — captured so your brain can release them, but not consuming attention.

---

## What it does

- **Capture** anywhere via Claude chat. Just state the item and its quadrant: *"vehicle battery — q3, find me the cheapest Group 35 available locally"*.
- **Classify** by quadrant + **role** (parent, athlete, professional, …). Roles are Covey's second lens: which *part of your life* this item serves.
- **Delegate** Q3 work to an autonomous agent. It researches, sources, drafts a recommendation, and surfaces 2-3 decision options.
- **Review** conversationally: *"approve the van battery, go with option 2"* / *"send the agent back, budget needs to be lower"* / *"dismiss it"*. You never have to know what a pull request is.
- **Sharpen the saw** with `weekly_review` — a Habit-7 dashboard that shows your quadrant distribution, role balance, Q2 leverage list, and Q3 throughput. Watch over time whether Q2 share is actually growing.
- **Sync** across devices via iCloud (files) and a private GitHub repo (audit log). View in Obsidian for a visual board over the same files.

The data is **just markdown**. You can read, edit, and grep it without the tool running.

---

## Why a quadrant-shaped system, not a list

Flat todo lists treat every item equally. The result is well-known: the loud, urgent things win every day, and the meaningful, non-urgent things never get done. Apple Reminders, Things, Todoist — all of them are excellent at *capturing* and terrible at *protecting Q2*.

The four quadrants are not just tags here. They drive behaviour:

| Quadrant | What the system does automatically |
|----------|-------------------------------------|
| **Q1** Urgent + Important | Surfaces in your daily queue with high priority. |
| **Q2** Not Urgent + Important | Tracked, protected. Stale Q2 items trigger a nudge in the weekly review. |
| **Q3** Urgent + Not Important | Default assignee is `claude` — the agent handles it. |
| **Q4** Not Urgent + Not Important | Captured directly to `someday/` so it can't consume attention. |

Roles add a second axis. Every item can be tagged with the roles it serves (`parent`, `athlete`, `business-owner`, …). The weekly review shows which roles are getting attention and which are starving. If you have zero open items under `parent` for a month, that's a signal.

---

## Daily rhythm

Borrowed directly from Covey's "Put First Things First" weekly + daily flow:

- **Capture** — anytime, conversationally. Drop the item in, classify it.
- **Morning check-in** — *"what needs me today?"* The system returns 3-5 items biased toward Q1 + needs-review + stale Q2.
- **Async review** — when the agent finishes a Q3 item, you approve, request a revision, or dismiss. Two-sentence interaction.
- **Sunday weekly review** — `weekly_review` shows quadrant distribution, role balance, Q2-in-progress, and what the agent took off your plate. Adjust where you spend the coming week.

---

## Components in this repo

| Path | Purpose |
|------|---------|
| `todos-mcp/` | MCP server exposing the tools below. |
| `todos-agent/` | Hourly Claude Code SDK loop that works items where `assignee: claude`. |
| `launchd/` | macOS service definitions for both daemons. |
| `cloudflared/` | Tunnel config example for exposing the MCP server. |
| `templates/` | Frontmatter templates for new items + contacts. |
| `scripts/` | Bootstrap, install, doctor, data-repo init, migration helpers. |
| `life-ops-system.md` | Full build spec. |

MCP tools, grouped by Covey concept:

- **Capture**: `capture_todo`
- **Classify / find**: `list_todos`, `get_todo`
- **Sequence (move items through statuses)**: `update_todo`, `move_todo`, `delegate_todo`
- **Daily focus**: `get_my_queue`, `get_shared_queue`
- **Resolve (Q3 → done without touching GitHub)**: `approve_review`, `request_revision`, `dismiss_todo`, `complete_todo`
- **Habit 7 / sharpen the saw**: `weekly_review`
- **Shared world**: `add_contact`

---

## Install

> Requires macOS (for launchd) and a GitHub account. `uv` is installed for you if missing.

```bash
git clone https://github.com/<your-user>/lifeops.git ~/code/lifeops
cd ~/code/lifeops
./install.sh
```

`install.sh` is idempotent. It checks prereqs, installs `uv` if needed, creates a venv per package, seeds `~/.config/lifeops/{env,owner_context.md}`, and loads the launchd services.

Then:

```bash
$EDITOR ~/.config/lifeops/env              # GITHUB_TOKEN, ANTHROPIC_API_KEY, TODOS_REPO, TODOS_USER
$EDITOR ~/.config/lifeops/owner_context.md # household background for the agent

TODOS_REPO=<your-user>/todos make data-repo   # creates the data repo + label taxonomy
make doctor                                    # verify the install
```

Day-to-day:

```bash
make mcp        # run the MCP server in the foreground (debug)
make agent      # one agent pass (debug)
make services   # reload launchd
make tunnel     # Cloudflare Tunnel setup
make uninstall  # remove launchd services
```

---

## Wire it into a client

The MCP server speaks two transports:

- **stdio** — for clients running on the same machine. Cheapest, no network. The client launches the server as a subprocess.
- **SSE over HTTPS** — for clients reaching in from elsewhere (`claude.ai`, ChatGPT). Cloudflare Tunnel exposes `localhost:8000` at a public hostname.

### Claude Desktop (local, stdio)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lifeops": {
      "command": "/Users/<you>/.local/bin/uv",
      "args": [
        "run",
        "--directory",
        "/Users/<you>/code/lifeops/todos-mcp",
        "todos-mcp"
      ],
      "env": { "MCP_TRANSPORT": "stdio" }
    }
  }
}
```

Restart Claude Desktop. The Life Ops tools (`capture_todo`, `get_my_queue`, `weekly_review`, …) appear in the tool list.

The server reads `TODOS_REPO`, `TODOS_USER`, `GITHUB_TOKEN`, etc. from `~/.config/lifeops/env` automatically — only `MCP_TRANSPORT` needs to be in the client config.

### Claude Code (CLI, stdio)

```bash
claude mcp add lifeops \
  --env MCP_TRANSPORT=stdio \
  -- uv run --directory ~/code/lifeops/todos-mcp todos-mcp
```

Or hand-edit `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "lifeops": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/Users/<you>/code/lifeops/todos-mcp", "todos-mcp"],
      "env": { "MCP_TRANSPORT": "stdio" }
    }
  }
}
```

### claude.ai (remote, via Cloudflare Tunnel)

1. **Expose the server**:
   ```bash
   make tunnel    # creates the tunnel + ~/.cloudflared/config.yml
   cloudflared tunnel route dns todos-mcp todos-mcp.<your-domain>
   ```
   Either run `cloudflared tunnel run todos-mcp` in a terminal or install it as a launchd service.
2. **Add the connector**: claude.ai → Settings → Connectors → *Add custom connector* → paste `https://todos-mcp.<your-domain>/sse`.
3. The Life Ops tools appear in your sidebar.

### ChatGPT (remote, via Cloudflare Tunnel)

Same tunnel as above, then in ChatGPT: Settings → Connectors → *Add MCP server* → URL `https://todos-mcp.<your-domain>/sse`. ChatGPT advertises and calls the tools the same way Claude does.

### Security caveat — important

The MCP server has **no built-in authentication**. Anyone who knows the tunnel URL can call its tools, which means anyone with that URL can read, create, mutate, and delete your todos and drive your GitHub repo.

Before exposing the tunnel publicly, put something in front of it:

- **Cloudflare Access** (zero-trust) — restrict by email / SSO. Free for personal use. Recommended.
- **mTLS** at the tunnel — `cloudflared` supports it.
- **A long, random hostname** is *not* sufficient by itself, but pairs reasonably with Access for defense in depth.

For stdio (Claude Desktop / Claude Code on your own machine) this doesn't apply — there's no network surface.

---

## Configuration

All runtime configuration is via environment variables — nothing personal is checked into the repo.

| Variable | Purpose |
|----------|---------|
| `TODOS_DIR` | Local folder holding the markdown data. |
| `TODOS_REPO` | Backing GitHub repo, e.g. `your-user/todos`. |
| `TODOS_OWNERS` | Comma-separated owner namespaces, e.g. `alice,bob`. `shared` is always included. |
| `TODOS_USER` | Default identity for the MCP server — must be one of `TODOS_OWNERS`. |
| `GITHUB_TOKEN` | PAT with `repo` scope. |
| `ANTHROPIC_API_KEY` | Used by the agent loop. |
| `MCP_PORT` | Local port the MCP server listens on. |
| `OWNER_CONTEXT_FILE` | Local-only file describing household background for the agent. |

See `.env.example`.

---

## Design principles

1. **Lead with the quadrants.** They're the primary mental model. Everything else (status, assignee, repo) is plumbing in service of moving items through the matrix.
2. **Defend Q2 actively.** The system nudges stale Q2 work, surfaces it in the weekly review, and never lets a flat-list firehose drown it.
3. **Files are the source of truth.** GitHub is sync + audit. Obsidian is a view. If Life Ops disappears, your data is still readable markdown.
4. **Hide the mechanics.** You speak in items, quadrants, roles, decisions. Pull requests, branches, and labels are how the system keeps state — not how you interact with it.
5. **Plain text wins.** No vendor lock-in.

---

## Status

Early. Built for a single household. Open-sourced so others can fork and adapt the pattern.

## License

[Apache License 2.0](./LICENSE)
