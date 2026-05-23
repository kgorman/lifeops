"""MCP server exposing the todos tools defined in the build spec.

Runs on localhost (default :8000). Cloudflare Tunnel maps the public hostname
to this process. All file mutations: pull → write → commit → push.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import (
    VALID_ASSIGNEES,
    VALID_OWNERS,
    VALID_PRIORITIES,
    VALID_QUADRANTS,
    VALID_STATUSES,
    Config,
)
from .git_ops import GitOps
from .github_ops import GitHubOps
from .store import TodoStore

log = logging.getLogger("todos-mcp")


def _setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "todos-mcp.log")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(logging.StreamHandler())


def _resolve_owner(cfg: Config, owner: str | None) -> str:
    if owner is None or owner == "":
        return cfg.todos_user
    if owner not in VALID_OWNERS:
        raise ValueError(f"unknown owner: {owner}. valid: {sorted(VALID_OWNERS)}")
    return owner


def _validate_choice(value: str | None, valid: set[str], name: str) -> None:
    if value is not None and value not in valid:
        raise ValueError(f"unknown {name}: {value}. valid: {sorted(valid)}")


def create_server(cfg: Config) -> FastMCP:
    store = TodoStore(cfg.todos_dir)
    git = GitOps(cfg.todos_dir)
    gh = GitHubOps(cfg.github_token, cfg.todos_repo) if cfg.github_token else None

    store.ensure_layout()

    mcp = FastMCP("todos")

    # ---------- capture ----------

    @mcp.tool()
    def capture_todo(
        title: str,
        context: str = "",
        tags: list[str] | None = None,
        roles: list[str] | None = None,
        assignee: str | None = None,
        priority: str = "none",
        quadrant: str | None = None,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Capture a new item, classified by Covey quadrant.

        Quadrants (Covey 4-quadrant framework):
          q1 — Urgent + Important     → do now, defaults to assignee=me
          q2 — Not Urgent + Important → schedule, defaults to assignee=me
                                        (this is where leverage lives)
          q3 — Urgent + Not Important → delegate, defaults to assignee=claude
          q4 — Not Urgent + Not Important → captured directly to someday/

        `roles` is the Covey role list this item serves (parent, athlete,
        builder, …). `tags` stay free-form context (vehicles, garage, project).

        Owner defaults to the caller (TODOS_USER); use owner="shared" for
        household items.
        """
        owner = _resolve_owner(cfg, owner)
        _validate_choice(priority, VALID_PRIORITIES, "priority")
        _validate_choice(quadrant, VALID_QUADRANTS, "quadrant")

        # Quadrant-driven defaults — Covey's "delegate Q3" and "eliminate Q4"
        # are operationalised here so the caller doesn't have to remember.
        status = "inbox"
        if quadrant == "q3" and assignee is None:
            assignee = "claude"
        if quadrant == "q4":
            status = "someday"
            if assignee is None:
                assignee = "me"
        if assignee is None:
            assignee = "me"
        _validate_choice(assignee, VALID_ASSIGNEES, "assignee")

        git.pull()
        todo = store.create(
            title=title,
            owner=owner,
            context=context,
            tags=tags or [],
            roles=roles or [],
            assignee=assignee,
            priority=priority,
            quadrant=quadrant,
            status=status,
        )

        issue_number: int | None = None
        if gh:
            body = (
                f"**Owner:** {owner}\n"
                f"**Quadrant:** {quadrant or '—'}  "
                f"**Priority:** {priority}  "
                f"**Assignee:** {assignee}\n"
                f"**Roles:** {', '.join(roles or []) or '—'}\n\n"
                f"{context}\n\n"
                f"_File: `{Path(todo.path).relative_to(cfg.todos_dir)}`_"
            )
            issue_number = gh.create_issue(
                title=title,
                body=body,
                owner=owner,
                status=status,
                quadrant=quadrant,
                tags=(tags or []) + [f"role:{r}" for r in (roles or [])],
            )
            if issue_number:
                todo = store.update(todo, {"github_issue": issue_number})

        git.commit_and_push(f"capture: {title}", [Path(todo.path)])
        return todo.to_dict()

    # ---------- list / get ----------

    @mcp.tool()
    def list_todos(
        owner: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        tags: list[str] | None = None,
        roles: list[str] | None = None,
        priority: str | None = None,
        quadrant: str | None = None,
    ) -> list[dict[str, Any]]:
        """List todos with filters. owner="all" returns across all namespaces;
        omitting owner uses TODOS_USER. Filters combine with AND.

        `quadrant` filters by Covey quadrant (q1-q4). `roles` filters by any
        of the provided role names (e.g. ["athlete"] returns items tagged
        with that role).
        """
        _validate_choice(status, VALID_STATUSES, "status")
        _validate_choice(assignee, VALID_ASSIGNEES, "assignee")
        _validate_choice(priority, VALID_PRIORITIES, "priority")
        _validate_choice(quadrant, VALID_QUADRANTS, "quadrant")
        git.pull()

        if owner == "all" or owner is None:
            candidates = list(store.iter_all()) if owner == "all" else list(
                store.iter_owner(cfg.todos_user)
            )
        else:
            if owner not in VALID_OWNERS:
                raise ValueError(f"unknown owner: {owner}")
            candidates = list(store.iter_owner(owner))

        def keep(t):
            fm = t.frontmatter
            if status and fm.status != status:
                return False
            if assignee and fm.assignee != assignee:
                return False
            if priority and fm.priority != priority:
                return False
            if quadrant and fm.quadrant != quadrant:
                return False
            if tags:
                if not set(tags).issubset(set(fm.tags or [])):
                    return False
            if roles:
                if not set(roles).intersection(set(fm.roles or [])):
                    return False
            return True

        return [t.to_dict() for t in candidates if keep(t)]

    @mcp.tool()
    def get_todo(id_or_title: str, owner: str | None = None) -> dict[str, Any]:
        """Look up one todo by slug or title (substring match within owner)."""
        owner = _resolve_owner(cfg, owner) if owner != "all" else None
        git.pull()
        t = store.find(id_or_title, owner=owner)
        if not t:
            raise ValueError(f"no todo found for {id_or_title!r}")
        d = t.to_dict()
        d["body"] = t.body
        return d

    # ---------- update / move ----------

    @mcp.tool()
    def update_todo(
        id_or_title: str,
        owner: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Patch frontmatter fields on a todo. Commits + pushes."""
        owner = _resolve_owner(cfg, owner) if owner != "all" else None
        git.pull()
        t = store.find(id_or_title, owner=owner)
        if not t:
            raise ValueError(f"no todo found for {id_or_title!r}")
        fields = fields or {}
        _validate_choice(fields.get("status"), VALID_STATUSES, "status")
        _validate_choice(fields.get("assignee"), VALID_ASSIGNEES, "assignee")
        _validate_choice(fields.get("priority"), VALID_PRIORITIES, "priority")
        _validate_choice(fields.get("quadrant"), VALID_QUADRANTS, "quadrant")
        updated = store.update(t, fields)
        if gh and updated.frontmatter.github_issue:
            gh.update_issue(
                updated.frontmatter.github_issue,
                labels=gh.issue_labels(
                    owner=updated.frontmatter.owner,
                    status=updated.frontmatter.status,
                    quadrant=updated.frontmatter.quadrant,
                    tags=updated.frontmatter.tags or [],
                ),
            )
        git.commit_and_push(
            f"update: {updated.frontmatter.title}", [Path(updated.path)]
        )
        return updated.to_dict()

    @mcp.tool()
    def move_todo(
        id_or_title: str,
        new_status: str,
        owner: str | None = None,
        new_owner: str | None = None,
    ) -> dict[str, Any]:
        """Move a todo to a new status (and optionally hand off to another owner)."""
        _validate_choice(new_status, VALID_STATUSES, "status")
        if new_owner:
            _validate_choice(new_owner, VALID_OWNERS, "owner")
        owner = _resolve_owner(cfg, owner) if owner != "all" else None
        git.pull()
        t = store.find(id_or_title, owner=owner)
        if not t:
            raise ValueError(f"no todo found for {id_or_title!r}")
        moved = store.move(t, new_status=new_status, new_owner=new_owner)
        if gh and moved.frontmatter.github_issue:
            gh.update_issue(
                moved.frontmatter.github_issue,
                labels=gh.issue_labels(
                    owner=moved.frontmatter.owner,
                    status=moved.frontmatter.status,
                    quadrant=moved.frontmatter.quadrant,
                    tags=moved.frontmatter.tags or [],
                ),
            )
            if moved.frontmatter.status in ("done", "wont_do"):
                gh.close_issue(
                    moved.frontmatter.github_issue,
                    reason="completed" if moved.frontmatter.status == "done" else "not_planned",
                )
        git.commit_and_push(
            f"move: {moved.frontmatter.title} → {new_status}", [Path(moved.path)]
        )
        return moved.to_dict()

    # ---------- queues ----------

    @mcp.tool()
    def get_my_queue(owner: str | None = None) -> list[dict[str, Any]]:
        """Return 3-5 items needing the owner's attention now:
        - needs_review items
        - blocked items where the blocker may be resolved
        - high priority active items
        - stale Q2 items as nudge
        - shared/ items needing attention
        """
        owner = _resolve_owner(cfg, owner)
        git.pull()

        mine = list(store.iter_owner(owner))
        shared = list(store.iter_owner("shared"))
        pool = mine + [
            t for t in shared
            if t.frontmatter.assignee in (owner, "me")
            or t.frontmatter.status == "needs_review"
        ]

        scored: list[tuple[int, Any]] = []
        for t in pool:
            fm = t.frontmatter
            if fm.status in ("done", "wont_do", "someday"):
                continue
            score = 0
            if fm.status == "needs_review":
                score += 100
            if fm.status == "blocked":
                score += 30
            if fm.priority == "high":
                score += 40
            if fm.quadrant == "q1":
                score += 50
            if fm.quadrant == "q2" and fm.status == "active":
                score += 10  # gentle Q2 nudge
            scored.append((score, t))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [t for score, t in scored[:5] if score > 0]
        return [t.to_dict() for t in top]

    @mcp.tool()
    def get_shared_queue() -> list[dict[str, Any]]:
        """All shared/ items needing attention (active, blocked, needs_review)."""
        git.pull()
        out = []
        for t in store.iter_owner("shared"):
            if t.frontmatter.status not in ("done", "wont_do", "someday"):
                out.append(t.to_dict())
        return out

    # ---------- Covey weekly review (habit 7: sharpen the saw) ----------

    @mcp.tool()
    def weekly_review(
        owner: str | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """Covey-style weekly review.

        Returns:
          - quadrant_distribution: how many open items sit in each quadrant
            (a high q1+q3 share = firefighting; the goal is to grow q2)
          - role_balance: open items grouped by role, so you can see whether
            any role (parent, athlete, business-owner, …) is being starved
          - q2_in_progress: every q2 item currently active or delegated —
            this is the leverage list
          - q2_stale: q2 items that haven't moved in `days` (default 7)
          - completed: items closed in the last `days`, grouped by quadrant
          - delegated_to_agent: open items the agent is handling so you can
            see how much q3 was lifted off your plate

        Run this every Sunday-ish. The signal you want over time: q1/q3 down,
        q2 up, more role coverage, more agent throughput.
        """
        from collections import Counter, defaultdict
        from datetime import date as _date, timedelta

        owner = _resolve_owner(cfg, owner) if owner != "all" else None
        git.pull()

        candidates: list[Any]
        if owner is None:
            candidates = list(store.iter_all())
        else:
            candidates = list(store.iter_owner(owner)) + list(store.iter_owner("shared"))

        cutoff = _date.today() - timedelta(days=days)

        quadrant_dist: Counter[str] = Counter()
        role_balance: defaultdict[str, list[str]] = defaultdict(list)
        q2_active: list[dict[str, Any]] = []
        q2_stale: list[dict[str, Any]] = []
        completed_by_q: defaultdict[str, list[str]] = defaultdict(list)
        delegated: list[dict[str, Any]] = []

        for t in candidates:
            fm = t.frontmatter
            q = fm.quadrant or "unspecified"
            roles = fm.roles or []

            if fm.status in ("done", "wont_do"):
                if fm.updated and fm.updated >= cutoff:
                    completed_by_q[q].append(fm.title)
                continue

            quadrant_dist[q] += 1
            for r in roles:
                role_balance[r].append(fm.title)

            if fm.assignee == "claude" and fm.status in ("delegated", "in_progress"):
                delegated.append(t.to_dict())

            if q == "q2" and fm.status in ("active", "in_progress", "needs_review"):
                q2_active.append(t.to_dict())
            if q == "q2" and fm.status == "active":
                if fm.updated and fm.updated < cutoff:
                    q2_stale.append(t.to_dict())

        # Coaching insight: ratio of firefighting (q1+q3) to leverage (q2).
        total_open = sum(quadrant_dist.values()) or 1
        firefighting = quadrant_dist.get("q1", 0) + quadrant_dist.get("q3", 0)
        leverage = quadrant_dist.get("q2", 0)
        coaching = (
            f"{leverage}/{total_open} open items are q2 (leverage). "
            f"{firefighting} are q1/q3 (firefighting). "
            + (
                "Most of your open work is firefighting — push more q3 to the agent and protect q2 time."
                if firefighting > leverage * 2 and total_open > 4
                else "Q2 share is healthy — keep it."
                if leverage >= firefighting
                else "Balanced, but watch for q3 creep."
            )
        )

        return {
            "window_days": days,
            "quadrant_distribution": dict(quadrant_dist),
            "role_balance": {r: items for r, items in role_balance.items()},
            "q2_in_progress": q2_active,
            "q2_stale_over_window": q2_stale,
            "delegated_to_agent": delegated,
            "completed_in_window": dict(completed_by_q),
            "coaching": coaching,
        }

    # ---------- delegate ----------

    @mcp.tool()
    def delegate_todo(
        id_or_title: str,
        assignee: str,
        instructions: str = "",
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Assign a todo to claude or to another configured owner.
        Cross-namespace handoff moves the file into the new assignee's namespace."""
        _validate_choice(assignee, VALID_ASSIGNEES, "assignee")
        owner = _resolve_owner(cfg, owner) if owner != "all" else None
        git.pull()
        t = store.find(id_or_title, owner=owner)
        if not t:
            raise ValueError(f"no todo found for {id_or_title!r}")

        fields: dict[str, Any] = {"assignee": assignee}
        if assignee == "claude":
            fields["status"] = "delegated"
        if instructions:
            t = store.append_section(t, "Instructions", instructions)

        # Cross-user handoff: if assignee names another owner namespace,
        # move the file under their tree.
        named_owners = VALID_OWNERS - {"shared"}
        new_owner_ns = None
        if assignee in named_owners and assignee != t.frontmatter.owner:
            new_owner_ns = assignee
            fields["status"] = "active"

        updated = store.update(t, fields)
        if new_owner_ns:
            updated = store.move(updated, new_status=fields.get("status", "active"),
                                 new_owner=new_owner_ns)

        if gh and updated.frontmatter.github_issue:
            gh.update_issue(
                updated.frontmatter.github_issue,
                labels=gh.issue_labels(
                    owner=updated.frontmatter.owner,
                    status=updated.frontmatter.status,
                    quadrant=updated.frontmatter.quadrant,
                    tags=updated.frontmatter.tags or [],
                ),
            )
        git.commit_and_push(
            f"delegate: {updated.frontmatter.title} → {assignee}",
            [Path(updated.path)],
        )
        return updated.to_dict()

    # ---------- complete ----------

    @mcp.tool()
    def complete_todo(id_or_title: str, owner: str | None = None) -> dict[str, Any]:
        """Mark a todo done — moves file to done/YYYY-MM/, closes the issue."""
        owner = _resolve_owner(cfg, owner) if owner != "all" else None
        git.pull()
        t = store.find(id_or_title, owner=owner)
        if not t:
            raise ValueError(f"no todo found for {id_or_title!r}")
        moved = store.move(t, new_status="done")
        if gh and moved.frontmatter.github_issue:
            gh.close_issue(moved.frontmatter.github_issue, reason="completed")
        git.commit_and_push(
            f"done: {moved.frontmatter.title}", [Path(moved.path)]
        )
        return moved.to_dict()

    # ---------- review verbs (todo-language, hide GitHub) ----------

    def _find_pr(todo) -> Any:
        """Locate the agent's open PR for a todo, if there is one."""
        if not gh:
            return None
        pr = gh.find_pr_for_slug(todo.slug)
        if pr is not None:
            return pr
        if todo.frontmatter.github_issue:
            return gh.find_pr_for_issue(todo.frontmatter.github_issue)
        return None

    @mcp.tool()
    def approve_review(
        id_or_title: str,
        choice: str = "",
        comment: str = "",
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Accept the agent's recommendation on a `needs_review` todo.

        Records the user's decision (e.g. "option 2" or free text) into a
        `## Decision` section on the file, merges the agent's PR if there is
        one, moves the file to `done/YYYY-MM/`, and closes the underlying
        GitHub Issue. The caller does not need to know what a PR is.
        """
        owner = _resolve_owner(cfg, owner) if owner != "all" else None
        git.pull()
        t = store.find(id_or_title, owner=owner)
        if not t:
            raise ValueError(f"no todo found for {id_or_title!r}")
        if t.frontmatter.status not in ("needs_review", "blocked", "in_progress"):
            log.info("approving %s from non-review status %s",
                     t.slug, t.frontmatter.status)

        pr = _find_pr(t)
        if pr is not None:
            merge_msg = f"Approved: {choice or 'agent recommendation'}"
            if comment:
                merge_msg += f"\n\n{comment}"
            if not gh.merge_pr(pr, commit_message=merge_msg):
                log.warning("could not merge PR %d; continuing without merge",
                            pr.number)
            else:
                git.pull()
                t = store.find(t.slug, owner=t.frontmatter.owner) or t

        decision_body_lines: list[str] = []
        if choice:
            decision_body_lines.append(f"**Chosen:** {choice}")
        if comment:
            decision_body_lines.append(comment)
        if decision_body_lines:
            t = store.append_section(t, "Decision", "\n\n".join(decision_body_lines))

        moved = store.move(t, new_status="done")
        if gh and moved.frontmatter.github_issue:
            if comment or choice:
                gh.comment_on_issue(
                    moved.frontmatter.github_issue,
                    f"Approved by {moved.frontmatter.owner}: {choice or ''}\n\n{comment}".strip(),
                )
            gh.close_issue(moved.frontmatter.github_issue, reason="completed")
        git.commit_and_push(f"approve: {moved.frontmatter.title}", [Path(moved.path)])
        return moved.to_dict()

    @mcp.tool()
    def request_revision(
        id_or_title: str,
        feedback: str,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Ask the agent to take another pass.

        Appends the user's feedback to the file's `## Instructions` section,
        flips the todo back to `delegated` (assignee=claude) so the next agent
        run picks it up, closes the prior PR (its work was rejected) and
        records the feedback as an issue comment.
        """
        if not feedback or not feedback.strip():
            raise ValueError("feedback is required")
        owner = _resolve_owner(cfg, owner) if owner != "all" else None
        git.pull()
        t = store.find(id_or_title, owner=owner)
        if not t:
            raise ValueError(f"no todo found for {id_or_title!r}")

        pr = _find_pr(t)
        if pr is not None:
            gh.close_pr(
                pr,
                comment=f"Superseded — requesting revision:\n\n{feedback}",
            )

        from datetime import date as _date
        revision_note = f"_Revision requested {_date.today().isoformat()}_\n\n{feedback.strip()}"
        t = store.append_section(t, "Instructions", revision_note)
        updated = store.update(
            t, {"status": "delegated", "assignee": "claude", "blocked_reason": None}
        )

        if gh and updated.frontmatter.github_issue:
            gh.update_issue(
                updated.frontmatter.github_issue,
                labels=gh.issue_labels(
                    owner=updated.frontmatter.owner,
                    status=updated.frontmatter.status,
                    quadrant=updated.frontmatter.quadrant,
                    tags=updated.frontmatter.tags or [],
                ),
            )
            gh.comment_on_issue(
                updated.frontmatter.github_issue,
                f"Revision requested:\n\n{feedback}",
            )

        git.commit_and_push(
            f"revise: {updated.frontmatter.title}", [Path(updated.path)]
        )
        return updated.to_dict()

    @mcp.tool()
    def dismiss_todo(
        id_or_title: str,
        reason: str = "",
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Close a todo without completing it (won't-do).

        Moves the file to `done/YYYY-MM/` with status `wont_do`, closes any
        open PR without merging, and closes the Issue as `not_planned`.
        """
        owner = _resolve_owner(cfg, owner) if owner != "all" else None
        git.pull()
        t = store.find(id_or_title, owner=owner)
        if not t:
            raise ValueError(f"no todo found for {id_or_title!r}")

        pr = _find_pr(t)
        if pr is not None:
            gh.close_pr(pr, comment=f"Dismissed: {reason}" if reason else "Dismissed")

        if reason:
            t = store.append_section(t, "Dismissed", reason)

        moved = store.move(t, new_status="wont_do")
        if gh and moved.frontmatter.github_issue:
            if reason:
                gh.comment_on_issue(
                    moved.frontmatter.github_issue, f"Dismissed: {reason}"
                )
            gh.close_issue(moved.frontmatter.github_issue, reason="not_planned")

        git.commit_and_push(
            f"dismiss: {moved.frontmatter.title}", [Path(moved.path)]
        )
        return moved.to_dict()

    # ---------- contacts ----------

    @mcp.tool()
    def add_contact(
        name: str,
        role: str = "",
        phone: str = "",
        email: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        """Add a contact to the shared contacts/ folder."""
        git.pull()
        path = store.add_contact(
            name=name, role=role, phone=phone, email=email, notes=notes
        )
        git.commit_and_push(f"contact: {name}", [path])
        return {"path": str(path), "name": name}

    return mcp


def main() -> None:
    cfg = Config.from_env()
    _setup_logging(cfg.log_dir)
    log.info("starting todos-mcp on port %d, dir=%s, repo=%s, user=%s",
             cfg.mcp_port, cfg.todos_dir, cfg.todos_repo, cfg.todos_user)
    mcp = create_server(cfg)
    transport = os.environ.get("MCP_TRANSPORT", "sse")
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        os.environ["FASTMCP_PORT"] = str(cfg.mcp_port)
        mcp.run(transport="sse")


if __name__ == "__main__":
    main()
