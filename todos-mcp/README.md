# todos-mcp

MCP server exposing the Life Ops capture / list / delegate tools.

## Install

```bash
uv venv
uv pip install -e .
```

## Run

```bash
# SSE transport (default — used by Cloudflare Tunnel)
uv run todos-mcp

# stdio transport (for local Claude Desktop wiring)
MCP_TRANSPORT=stdio uv run todos-mcp
```

## Tools exposed

| Tool | Purpose |
|------|---------|
| `capture_todo` | New item → file + Issue + push |
| `list_todos` | Filter by owner / status / assignee / tags / priority / quadrant |
| `get_todo` | Read one item including body |
| `update_todo` | Patch frontmatter |
| `move_todo` | Change status (and optionally owner) |
| `get_my_queue` | 3-5 items needing the caller's attention |
| `get_shared_queue` | Open items in shared/ |
| `delegate_todo` | Assign to `claude` or to another configured owner |
| `complete_todo` | Mark done, move to done/YYYY-MM/, close Issue |
| `approve_review` | Accept the agent's recommendation. Merges the PR, records the choice, closes the Issue, moves the file to done/. |
| `request_revision` | Send the agent back with feedback. Closes the prior PR, appends new instructions, flips to delegated. |
| `dismiss_todo` | Won't-do. Closes any open PR, moves the file to done/ with `wont_do`, closes the Issue as `not_planned`. |
| `add_contact` | Add contact to shared `contacts/` |

The last three are review verbs — they let the caller resolve a `needs_review`
item without ever touching GitHub. The PR / Issue lifecycle is mediated for you.

## Configuration

See [.env.example](../.env.example) in the repo root.
