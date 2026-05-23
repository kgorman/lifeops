# Life Ops System — Build Spec

## Overview

A personal life operations system built on markdown files, GitHub, and an MCP server. Replaces traditional reminders apps with a trusted capture-to-resolution pipeline. Two interfaces: Claude chat (primary, conversational) and Obsidian (visual). Two workers: Claude chat (collaborative, curatorial) and an autonomous agent loop (async research and problem solving).

The mental model is GitHub Issues + PRs applied to personal life. Capture is an issue. Agent work produces a PR. You review and merge. Your brain releases the item knowing the pipeline is trusted.

---

## Architecture

```
~/iCloud Drive/lifeops_todos/          ← local folder, iCloud syncs to phone/tablet
  └── (git repo)               ← also pushed to a private GitHub repo

Local machine (macOS)
  ├── todos-mcp                ← launchd, Python MCP server
  │     └── exposes tools to Claude chat
  └── todos-agent              ← launchd, Python agent loop (Claude Code SDK)
        └── runs on schedule, works delegated items

Cloudflare Tunnel              ← todos-mcp.<your-domain> → local
GitHub (private repo)          ← todos/*.md + Issues + PRs
Obsidian (Mac + iOS)           ← visual view, same folder
```

---

## File Structure

```
~/iCloud Drive/lifeops_todos/
  <user-a>/
    inbox/          ← unprocessed captures
    active/
    blocked/
    needs_review/
    someday/
    done/           ← YYYY-MM/ subfolders
  <user-b>/
    inbox/
    active/
    blocked/
    needs_review/
    someday/
    done/           ← YYYY-MM/ subfolders
  shared/
    inbox/          ← family/household items
    active/
    blocked/
    needs_review/
    someday/
    done/
  contacts/         ← shared, no namespace (vendors, contractors)
  _templates/       ← shared templates
```

Namespace is the trust boundary. Repo is the security boundary. No ACL needed — if you're in the repo you can see everything, which is the right model for a household.

---

## File Schema

Every todo is a markdown file with YAML frontmatter.

```markdown
---
title: Replace vehicle battery
owner: <user-a>          # <user-a> | <user-b> | shared
status: active
assignee: me             # me | claude | waiting | <user-a> | <user-b>
priority: high           # high | medium | low | none
quadrant: q1             # q1 | q2 | q3 | q4 (Covey 4 quadrants)
tags: [vehicles]
needs: [battery-spec]
context: Vehicle make/model + which battery is being replaced
created: 2026-05-23
updated: 2026-05-23
github_issue: 42
blocked_reason:          # populated by agent if blocked
---

Free-form notes, URLs, rich context here.
Any markdown is valid.

## Agent findings
_populated by agent when it has output_

## Decision needed
_populated by agent with clear options for review_
```

### Status values
| Status | Meaning |
|--------|---------|
| `inbox` | captured, not yet triaged |
| `active` | in progress |
| `blocked` | waiting on something external |
| `delegated` | assigned to claude agent, not yet started |
| `in_progress` | agent actively working |
| `needs_review` | agent has output, waiting for human decision |
| `done` | complete |
| `wont_do` | closed without action |

### Quadrant values (Covey)
| Quadrant | Meaning | Default assignee |
|----------|---------|-----------------|
| `q1` | Urgent + Important → Do now | `me` |
| `q2` | Not Urgent + Important → Schedule | `me` or `claude` |
| `q3` | Urgent + Not Important → Delegate | `claude` or `waiting` |
| `q4` | Not Urgent + Not Important → Eliminate | `someday/` or `wont_do` |

Q2 is where relationships, health, training, and meaningful projects live. The agent handles Q3 so you get Q2 back.

### Assignee values
| Assignee | Meaning |
|----------|---------|
| `me` | on the owner's plate |
| `claude` | delegated to agent |
| `waiting` | blocked on third party |
| `<user-a>` | explicitly assigned to user A |
| `<user-b>` | explicitly assigned to user B |

`me` is relative to the owner field — it means whoever owns the todo. Use named assignees when explicitly handing off across namespaces.

---

## GitHub Integration

### Issues
- Every todo file maps to a GitHub Issue
- File frontmatter `github_issue: N` links them
- Labels mirror tags
- Milestones = seasonal windows (spring-2026, summer-2026, etc.)
- Creating a todo creates both the file and the Issue

### PRs
- When the agent completes work on a delegated item it opens a PR
- PR title = todo title
- PR description = findings, recommendation, decision options
- PR links to the Issue
- Merging the PR = done, file moves to done/YYYY-MM/
- Closing PR without merge = wont_do

### Labels
```
# Owner labels (one per user in the household)
owner:<user-a>
owner:<user-b>
owner:shared

# Status labels
status:inbox
status:active
status:blocked
status:delegated
status:needs-review
status:done

# Quadrant labels (Covey)
q1:urgent-important
q2:not-urgent-important
q3:urgent-not-important
q4:eliminate

# Type labels (extend per your needs)
type:maintenance
type:errand
type:project
type:research
type:family
type:vehicles
type:yard
type:finance
```

---

## MCP Server

**Location:** `todos-mcp/` in this repo
**Language:** Python
**Dependencies:** `mcp`, `python-frontmatter`, `gitpython`, `PyGithub`
**Process manager:** launchd
**Endpoint:** `https://todos-mcp.<your-domain>` via Cloudflare Tunnel

### Tools to implement

```python
capture_todo(title, context, tags, assignee, priority, quadrant, owner)
# owner defaults to caller's identity (TODOS_USER env)
# shared/ namespace for household items
# Creates markdown file in {owner}/inbox/
# Creates GitHub Issue with owner label
# Commits and pushes
# Returns file path and issue number

list_todos(owner, status, assignee, tags, priority, quadrant)
# owner filter: <user-a> | <user-b> | shared | all
# Returns filtered list across namespaces
# Supports multiple filters combined

get_todo(id_or_title, owner)

update_todo(id, owner, fields)
# Commits and pushes
# Updates GitHub Issue

move_todo(id, owner, new_status)
# Moves file within owner's namespace
# Can move to shared/ with explicit owner=shared

get_my_queue(owner)
# Returns needs_review items for this owner
# Returns blocked items where blocker may be resolved
# Returns high priority active items assigned to owner
# Returns stale q2 items as nudge
# Returns shared/ items needing attention
# 3-5 items max

delegate_todo(id, owner, assignee, instructions)
# assignee: claude | <user-a> | <user-b>
# Cross-namespace handoff supported
# Moves to assignee's active/ if cross-user

get_shared_queue()
# Returns all shared/ items needing attention
# Surfaces items assigned to any user from shared/

complete_todo(id, owner)

# Review verbs — speak todo-language, hide GitHub mechanics
approve_review(id, choice, comment, owner)
# Accept the agent's recommendation
# Records the chosen option, merges the PR, closes the Issue,
# moves the file to done/YYYY-MM/

request_revision(id, feedback, owner)
# Send the agent back for another pass
# Closes the prior PR with the feedback as a comment,
# appends feedback to the file's ## Instructions section,
# flips status to delegated so the next agent run picks it up

dismiss_todo(id, reason, owner)
# Won't-do. Closes any open PR without merging,
# moves the file to done/YYYY-MM/ with status wont_do,
# closes the Issue as not_planned

add_contact(name, role, phone, email, notes)
# contacts/ is always shared namespace
```

---

## Agent Loop

**Location:** `todos-agent/` in this repo
**Language:** Python
**SDK:** Claude Code Python SDK (`claude-code-sdk`)
**Schedule:** launchd every 60 minutes

### Behavior

1. Pull latest from GitHub
2. Find all todos where `assignee: claude` and `status: delegated` or `in_progress` — across all namespaces
3. For each todo:
   - Set status to `in_progress`
   - Build prompt from title + context + instructions + owner_context
   - Run Claude Code SDK agent with web search + filesystem tools
   - Agent researches, reasons, produces output
   - Write findings to `## Agent findings` section of file
   - Write clear decision options to `## Decision needed` section
   - Set assignee to owner's name (not `me`) so it's unambiguous who reviews
   - Set status to `needs_review` or `blocked` with reason
   - Open GitHub PR with findings, tag the owner
4. Commit and push all changes

### Agent prompt template

The prompt is parameterized. Household-specific background (names, properties, vehicles, vendor preferences, hard constraints) lives in a local-only file referenced by `$OWNER_CONTEXT_FILE` — never in this repo. The default location is `~/.config/lifeops/owner_context.md`.

```
You are working on a personal task for {owner}.

Task: {title}
Owner: {owner}
Context: {context}
Instructions: {instructions}

{owner_context}    ← injected from OWNER_CONTEXT_FILE if present

Your job:
1. Research and solve as much as possible autonomously
2. Produce a clear recommendation with rationale
3. If you need {owner} to provide information, state exactly what you need
4. Write findings clearly — will be reviewed on a phone
5. Offer 2-3 concrete decision options, not open-ended questions
6. Be direct and specific. No fluff.

Output findings under ## Agent findings
State what you need under ## Decision needed
Set assignee to '{owner}' when done so it's clear who reviews
```

### Blocked handling

If the agent cannot proceed without human input:
```yaml
status: blocked
blocked_reason: >
  Need irrigation controller model to source correct
  sprinkler heads. Check sticker inside panel in garage.
```

---

## Launchd Configs

See `launchd/com.lifeops.todos-mcp.plist` and `launchd/com.lifeops.todos-agent.plist`. Both use `__HOME__` and `__LIFEOPS_DIR__` placeholders that `scripts/install-launchd.sh` substitutes at install time.

The MCP server runs continuously (`KeepAlive`). The agent loop runs every 3600s (`StartInterval`).

---

## Cloudflare Tunnel

See `cloudflared/config.yml.example`. Steps:

```bash
brew install cloudflared
cloudflared tunnel login
cloudflared tunnel create todos-mcp
cloudflared tunnel route dns todos-mcp todos-mcp.<your-domain>
# edit ~/.cloudflared/config.yml
cloudflared tunnel run todos-mcp
```

---

## Obsidian Setup

1. Create vault pointing at `~/iCloud Drive/lifeops_todos/`
2. Install plugins:
   - **Kanban** — board view per namespace
   - **Dataview** — query todos by frontmatter fields
   - **Obsidian Git** — auto-pull/push to GitHub
   - **Templater** — consistent frontmatter on new files
3. Kanban board columns: `inbox → active → blocked → needs_review → done`
4. Per-user queue (replace `<user>`):
```dataview
TABLE priority, quadrant, tags, updated
FROM "<user>" OR "shared"
WHERE assignee = "me" OR assignee = "<user>" OR status = "needs_review"
SORT quadrant ASC, priority DESC
```

5. Shared Q2 view (relationships, meaningful projects):
```dataview
TABLE title, owner, assignee, tags, updated
WHERE quadrant = "q2"
SORT priority DESC
```

---

## Daily Workflow

### Capture (anytime)
> "Claude, vehicle battery — find cheapest Group 35 near home"

→ Creates issue, delegates to agent, brain released.

### Checkin (morning or whenever)
> "What needs me today?"

→ Claude calls `get_my_queue()`, surfaces only items needing a decision. 3-5 items max. You respond, Claude updates files and GitHub.

### Review (async, conversational)
> "Approve the van battery — go with option 2"
> "Send the agent back, the budget needs to be lower"
> "Dismiss it"

→ Claude calls `approve_review`, `request_revision`, or `dismiss_todo`.
  Behind the scenes the MCP merges / comments / closes the PR, closes the
  Issue, and moves the file to `done/YYYY-MM/`. The user never has to know
  that GitHub exists.

GitHub PR notifications on the phone are still useful as a *notification*
surface — but they are not the review interface. You can resolve any item
entirely through chat.

---

## Build Order

1. `todos-mcp` — MCP server with core tools
2. GitHub data repo + label taxonomy (`scripts/init-todos-repo.sh`)
3. File templates
4. launchd configs for MCP server
5. Cloudflare Tunnel
6. Migrate existing reminders (`scripts/migrate-reminders.sh`)
7. Obsidian vault setup (Mac + iOS)
8. `todos-agent` — agent loop with Claude Code SDK
9. launchd config for agent loop
10. Wire MCP server into Claude settings

---

## Notes for implementers

- Use `uv` for dependency management throughout
- All file paths relative to `~/iCloud Drive/lifeops_todos/` — configurable via env var `TODOS_DIR`
- GitHub token via env var `GITHUB_TOKEN`
- GitHub data repo via env var `TODOS_REPO` (e.g. `<your-user>/lifeops_todos`) — a separate, private repo, distinct from the public `lifeops` code repo
- Anthropic API key via env var `ANTHROPIC_API_KEY`
- Default user via env var `TODOS_USER` (e.g. one of your household users) — MCP server uses this to scope `get_my_queue()` and default `owner` on capture
- Household context via `OWNER_CONTEXT_FILE` (default `~/.config/lifeops/owner_context.md`) — local-only, never committed
- MCP server listens on `localhost:8000`
- Git operations: always pull before read, commit + push after write
- Log verbosely to the log files — this is infrastructure, observability matters
- Handle merge conflicts gracefully — last write wins on frontmatter, append on notes sections
- `contacts/` and `_templates/` are always shared, never namespaced
- Cross-namespace operations (one user delegates to another) move the file to the assignee's `active/` folder and update the owner field
