"""Configuration loaded from env vars."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path.home() / ".config" / "lifeops" / "env")


def _owners_from_env() -> list[str]:
    """Owner namespaces for the household. Configured via TODOS_OWNERS
    (comma-separated). The literal `shared` namespace is always included for
    household-level items. Defaults to two anonymous users if unset."""
    raw = os.environ.get("TODOS_OWNERS", "user-a,user-b")
    owners = [o.strip() for o in raw.split(",") if o.strip() and o.strip() != "shared"]
    return owners + ["shared"]


@dataclass(frozen=True)
class Config:
    todos_dir: Path
    todos_repo: str
    todos_user: str
    github_token: str
    mcp_port: int
    log_dir: Path
    owners: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Config":
        todos_dir = Path(
            os.environ.get("TODOS_DIR", str(Path.home() / "iCloud Drive" / "todos"))
        ).expanduser()
        return cls(
            todos_dir=todos_dir,
            todos_repo=os.environ.get("TODOS_REPO", ""),
            todos_user=os.environ.get("TODOS_USER", ""),
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            mcp_port=int(os.environ.get("MCP_PORT", "8000")),
            log_dir=Path(os.environ.get("LOG_DIR", str(Path.home() / "logs"))).expanduser(),
            owners=tuple(_owners_from_env()),
        )


# Computed at import time so the rest of the package can validate against
# the same owner set the server is configured for.
VALID_OWNERS: set[str] = set(_owners_from_env())
# Assignees: the fixed verbs (me/claude/waiting) plus any named owner so one
# user can hand off to another.
VALID_ASSIGNEES: set[str] = {"me", "claude", "waiting"} | (VALID_OWNERS - {"shared"})

VALID_STATUSES = {
    "inbox",
    "active",
    "blocked",
    "delegated",
    "in_progress",
    "needs_review",
    "done",
    "wont_do",
    "someday",
}
VALID_QUADRANTS = {"q1", "q2", "q3", "q4"}
VALID_PRIORITIES = {"high", "medium", "low", "none"}

# Folders that exist per-owner namespace
NAMESPACE_FOLDERS = ("inbox", "active", "blocked", "needs_review", "someday", "done")
