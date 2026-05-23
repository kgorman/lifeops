"""File-system store for todos.

Layout under TODOS_DIR:
    {owner}/{status_folder}/{slug}.md   for owner in VALID_OWNERS (incl. shared)
    contacts/{slug}.md                  (always shared)
    _templates/...                      (shared)

VALID_OWNERS is derived from $TODOS_OWNERS at import time.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Iterable

import frontmatter
from slugify import slugify

from .config import (
    NAMESPACE_FOLDERS,
    VALID_OWNERS,
    VALID_STATUSES,
)
from .models import Todo, TodoFrontmatter

log = logging.getLogger(__name__)

# Status → folder mapping. Most statuses share a folder name; a few are virtual.
STATUS_FOLDER = {
    "inbox": "inbox",
    "active": "active",
    "blocked": "blocked",
    "delegated": "active",       # delegated lives with active, assignee tells you it's claude's
    "in_progress": "active",     # agent is working — still active
    "needs_review": "needs_review",
    "someday": "someday",
    "done": "done",
    "wont_do": "done",
}


class TodoStore:
    """Reads and writes todo markdown files under TODOS_DIR."""

    def __init__(self, root: Path):
        self.root = Path(root)

    # ---------- path helpers ----------

    def ensure_layout(self) -> None:
        """Create the namespace + shared folders if missing."""
        for owner in VALID_OWNERS:
            for sub in NAMESPACE_FOLDERS:
                (self.root / owner / sub).mkdir(parents=True, exist_ok=True)
        (self.root / "contacts").mkdir(parents=True, exist_ok=True)
        (self.root / "_templates").mkdir(parents=True, exist_ok=True)

    def folder_for(self, owner: str, status: str) -> Path:
        if owner not in VALID_OWNERS:
            raise ValueError(f"unknown owner: {owner}")
        if status not in STATUS_FOLDER:
            raise ValueError(f"unknown status: {status}")
        sub = STATUS_FOLDER[status]
        if sub == "done":
            month = date.today().strftime("%Y-%m")
            return self.root / owner / "done" / month
        return self.root / owner / sub

    # ---------- write ----------

    def make_slug(self, title: str) -> str:
        return slugify(title)[:80] or "untitled"

    def write(self, todo: Todo) -> Path:
        path = Path(todo.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        post = frontmatter.Post(
            todo.body,
            **todo.frontmatter.model_dump(mode="json", exclude_none=True),
        )
        path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
        return path

    def create(
        self,
        *,
        title: str,
        owner: str,
        context: str = "",
        tags: list[str] | None = None,
        roles: list[str] | None = None,
        assignee: str = "me",
        priority: str = "none",
        quadrant: str | None = None,
        status: str = "inbox",
    ) -> Todo:
        if owner not in VALID_OWNERS:
            raise ValueError(f"unknown owner: {owner}")
        if status not in VALID_STATUSES:
            raise ValueError(f"unknown status: {status}")
        slug = self._unique_slug(owner, self.make_slug(title))
        folder = self.folder_for(owner, status)
        path = folder / f"{slug}.md"
        fm = TodoFrontmatter(
            title=title,
            owner=owner,
            status=status,
            assignee=assignee,
            priority=priority,
            quadrant=quadrant,
            tags=tags or [],
            roles=roles or [],
            context=context,
        )
        todo = Todo(slug=slug, path=str(path), frontmatter=fm, body="")
        self.write(todo)
        log.info("created todo %s at %s", slug, path)
        return todo

    def _unique_slug(self, owner: str, base: str) -> str:
        """Avoid collisions across the owner's namespace."""
        existing = {t.slug for t in self.iter_owner(owner)}
        if base not in existing:
            return base
        i = 2
        while f"{base}-{i}" in existing:
            i += 1
        return f"{base}-{i}"

    # ---------- read ----------

    def iter_owner(self, owner: str) -> Iterable[Todo]:
        """Yield every todo under one owner's namespace (all folders)."""
        owner_root = self.root / owner
        if not owner_root.exists():
            return
        for md_path in owner_root.rglob("*.md"):
            try:
                yield self._read_path(md_path)
            except Exception as e:
                log.warning("failed to parse %s: %s", md_path, e)

    def iter_all(self) -> Iterable[Todo]:
        for owner in VALID_OWNERS:
            yield from self.iter_owner(owner)

    def _read_path(self, path: Path) -> Todo:
        text = path.read_text(encoding="utf-8")
        post = frontmatter.loads(text)
        meta = dict(post.metadata)
        meta.setdefault("title", path.stem.replace("-", " ").title())
        fm = TodoFrontmatter(**meta)
        return Todo(
            slug=path.stem,
            path=str(path),
            frontmatter=fm,
            body=post.content or "",
        )

    def find(self, id_or_title: str, owner: str | None = None) -> Todo | None:
        """Find a todo by slug or fuzzy title match within an owner (or all)."""
        candidates: Iterable[Todo]
        if owner:
            candidates = list(self.iter_owner(owner))
        else:
            candidates = list(self.iter_all())

        needle = id_or_title.lower().strip()
        # exact slug
        for t in candidates:
            if t.slug == needle:
                return t
        # slugified title match
        slugged = slugify(needle)
        for t in candidates:
            if t.slug == slugged:
                return t
        # substring title match
        matches = [t for t in candidates if needle in t.frontmatter.title.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f"{len(matches)} todos match {id_or_title!r}: "
                + ", ".join(t.slug for t in matches[:5])
            )
        return None

    # ---------- update / move ----------

    def update(self, todo: Todo, fields: dict) -> Todo:
        """Patch frontmatter fields and bump `updated`."""
        data = todo.frontmatter.model_dump(mode="json", exclude_none=True)
        data.update({k: v for k, v in fields.items() if v is not None})
        data["updated"] = date.today().isoformat()
        new_fm = TodoFrontmatter(**data)
        updated = Todo(slug=todo.slug, path=todo.path, frontmatter=new_fm, body=todo.body)
        self.write(updated)
        return updated

    def move(self, todo: Todo, new_status: str, new_owner: str | None = None) -> Todo:
        """Move file to {owner}/{status_folder}/. Updates frontmatter."""
        if new_status not in VALID_STATUSES:
            raise ValueError(f"unknown status: {new_status}")
        owner = new_owner or todo.frontmatter.owner
        new_folder = self.folder_for(owner, new_status)
        new_folder.mkdir(parents=True, exist_ok=True)
        new_path = new_folder / f"{todo.slug}.md"

        old_path = Path(todo.path)
        # rewrite content at new path with updated frontmatter
        data = todo.frontmatter.model_dump(mode="json", exclude_none=True)
        data["status"] = new_status
        data["owner"] = owner
        data["updated"] = date.today().isoformat()
        new_fm = TodoFrontmatter(**data)
        moved = Todo(slug=todo.slug, path=str(new_path), frontmatter=new_fm, body=todo.body)
        self.write(moved)
        if old_path != new_path and old_path.exists():
            old_path.unlink()
        return moved

    def append_section(self, todo: Todo, heading: str, body: str) -> Todo:
        """Append a `## heading` section to the body if not present, replace if present."""
        marker = f"## {heading}"
        existing = todo.body or ""
        if marker in existing:
            parts = existing.split(marker, 1)
            tail = parts[1]
            # find next h2 boundary
            next_h2 = tail.find("\n## ")
            if next_h2 == -1:
                new_existing = parts[0] + f"{marker}\n{body.strip()}\n"
            else:
                new_existing = parts[0] + f"{marker}\n{body.strip()}\n" + tail[next_h2:]
        else:
            sep = "\n\n" if existing.strip() else ""
            new_existing = f"{existing.rstrip()}{sep}{marker}\n{body.strip()}\n"
        updated = Todo(
            slug=todo.slug,
            path=todo.path,
            frontmatter=todo.frontmatter,
            body=new_existing,
        )
        self.write(updated)
        return updated

    # ---------- contacts ----------

    def add_contact(
        self,
        *,
        name: str,
        role: str = "",
        phone: str = "",
        email: str = "",
        notes: str = "",
    ) -> Path:
        slug = slugify(name)[:80] or "contact"
        path = self.root / "contacts" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "name": name,
            "role": role,
            "phone": phone,
            "email": email,
            "created": date.today().isoformat(),
        }
        post = frontmatter.Post(notes, **{k: v for k, v in meta.items() if v})
        path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
        return path
