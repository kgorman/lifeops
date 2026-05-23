"""Data models for todos."""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class TodoFrontmatter(BaseModel):
    """YAML frontmatter for a todo markdown file."""

    title: str
    owner: str = "user-a"
    status: str = "inbox"
    assignee: str = "me"
    priority: str = "none"
    quadrant: str | None = None
    tags: list[str] = Field(default_factory=list)
    # Covey roles — which part of life this item serves (parent, athlete,
    # business-owner, …). Separate from `tags`, which are free-form context
    # (vehicles, garage, project-x). Roles drive the weekly-review balance check.
    roles: list[str] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)
    context: str = ""
    created: date = Field(default_factory=date.today)
    updated: date = Field(default_factory=date.today)
    github_issue: int | None = None
    blocked_reason: str | None = None

    model_config = {"extra": "allow"}


class Todo(BaseModel):
    """A todo: frontmatter + body + on-disk path + slug."""

    slug: str
    path: str
    frontmatter: TodoFrontmatter
    body: str = ""

    def to_dict(self) -> dict[str, Any]:
        fm = self.frontmatter.model_dump(mode="json", exclude_none=True)
        return {
            "slug": self.slug,
            "path": self.path,
            "title": fm.get("title"),
            "owner": fm.get("owner"),
            "status": fm.get("status"),
            "assignee": fm.get("assignee"),
            "priority": fm.get("priority"),
            "quadrant": fm.get("quadrant"),
            "tags": fm.get("tags", []),
            "roles": fm.get("roles", []),
            "github_issue": fm.get("github_issue"),
            "updated": fm.get("updated"),
            "blocked_reason": fm.get("blocked_reason"),
            "body_preview": (self.body or "").strip().split("\n\n", 1)[0][:240],
        }
