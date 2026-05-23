"""Hourly Life Ops agent.

For each todo where assignee=claude AND status in {delegated, in_progress}:
  1. Mark in_progress, commit, push
  2. Pull latest, build prompt from title + context + instructions + owner_context
  3. Run Claude Code SDK agent (web search + file tools allowed)
  4. Parse agent output into Findings + Decision sections
  5. Write back into the file, flip status to needs_review (or blocked)
  6. Open a PR linking to the issue, tag the owner
  7. Commit + push

The household / owner context lives in OWNER_CONTEXT_FILE (default
~/.config/lifeops/owner_context.md). It is intentionally NOT in this repo
so the codebase can be open-sourced.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import anyio
import frontmatter
from dotenv import load_dotenv
from git import Repo
from github import Auth, Github

load_dotenv()
load_dotenv(Path.home() / ".config" / "lifeops" / "env")

log = logging.getLogger("todos-agent")

# Use the official Claude Agent SDK. It spawns the local `claude` CLI as a
# subprocess and inherits its OAuth session — no ANTHROPIC_API_KEY required
# when the user has already run `claude login`. (Previously published as
# claude-code-sdk; the package has been renamed.)
try:
    from claude_agent_sdk import ClaudeAgentOptions, query  # type: ignore
    _SDK_STYLE = "query"
except Exception:  # pragma: no cover
    _SDK_STYLE = None
    ClaudeAgentOptions = None  # type: ignore
    query = None  # type: ignore


DEFAULT_PROMPT_TEMPLATE = """You are working on a personal task for {owner}.

Task: {title}
Owner: {owner}
Context:
{context}

Instructions:
{instructions}

{owner_context_block}

Your job:
1. Research and solve as much as possible autonomously.
2. Produce a clear recommendation with rationale.
3. If you need {owner} to provide information, state exactly what you need.
4. Write findings clearly — they will be reviewed on a phone.
5. Offer 2-3 concrete decision options, not open-ended questions.
6. Be direct and specific. No fluff.

Output sections (use these exact headings):

## Agent findings
<your research, comparisons, recommendation>

## Decision needed
<2-3 numbered options OR a single bulleted list of info you need from {owner}>
"""


@dataclass
class AgentConfig:
    todos_dir: Path
    todos_repo: str
    github_token: str
    owner_context_file: Path | None
    log_dir: Path
    max_items_per_run: int = 8

    @classmethod
    def from_env(cls) -> "AgentConfig":
        # Note: no ANTHROPIC_API_KEY here — auth is delegated to the local
        # `claude` CLI via the Claude Agent SDK. If the env var is set, the
        # SDK will pick it up directly, but the agent does not require it.
        return cls(
            todos_dir=Path(
                os.environ.get("TODOS_DIR", str(Path.home() / "iCloud Drive" / "lifeops_todos"))
            ).expanduser(),
            todos_repo=os.environ.get("TODOS_REPO", ""),
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            owner_context_file=_resolve_optional_path(
                os.environ.get("OWNER_CONTEXT_FILE")
            ),
            log_dir=Path(os.environ.get("LOG_DIR", str(Path.home() / "logs"))).expanduser(),
            max_items_per_run=int(os.environ.get("AGENT_MAX_ITEMS", "8")),
        )


def _resolve_optional_path(p: str | None) -> Path | None:
    if not p:
        default = Path.home() / ".config" / "lifeops" / "owner_context.md"
        return default if default.exists() else None
    path = Path(p).expanduser()
    return path if path.exists() else None


def _setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "todos-agent.log")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(logging.StreamHandler())


# ---------- file helpers ----------

def _owner_dirs(root: Path) -> list[str]:
    """Owner namespaces the agent should scan.

    Configured via $TODOS_OWNERS (comma-separated). If unset, falls back to
    scanning every top-level directory in TODOS_DIR that contains an `inbox/`
    subfolder — keeps the agent owner-agnostic.
    """
    env = os.environ.get("TODOS_OWNERS", "").strip()
    if env:
        owners = [o.strip() for o in env.split(",") if o.strip()]
        if "shared" not in owners:
            owners.append("shared")
        return owners
    return [
        p.name for p in root.iterdir()
        if p.is_dir() and (p / "inbox").is_dir()
    ]


def find_delegated(root: Path) -> Iterable[tuple[Path, dict, str]]:
    """Yield (path, frontmatter_dict, body) for every assignee=claude todo."""
    for owner in _owner_dirs(root):
        owner_dir = root / owner
        if not owner_dir.exists():
            continue
        for md in owner_dir.rglob("*.md"):
            try:
                post = frontmatter.load(md)
            except Exception as e:
                log.warning("could not parse %s: %s", md, e)
                continue
            meta = dict(post.metadata)
            if meta.get("assignee") != "claude":
                continue
            if meta.get("status") not in ("delegated", "in_progress"):
                continue
            yield md, meta, post.content or ""


def write_back(path: Path, meta: dict, body: str) -> None:
    meta["updated"] = date.today().isoformat()
    post = frontmatter.Post(body, **{k: v for k, v in meta.items() if v is not None})
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def upsert_section(body: str, heading: str, content: str) -> str:
    marker = f"## {heading}"
    if marker in body:
        parts = body.split(marker, 1)
        tail = parts[1]
        nxt = tail.find("\n## ")
        if nxt == -1:
            return parts[0] + f"{marker}\n{content.strip()}\n"
        return parts[0] + f"{marker}\n{content.strip()}\n" + tail[nxt:]
    sep = "\n\n" if body.strip() else ""
    return f"{body.rstrip()}{sep}{marker}\n{content.strip()}\n"


# ---------- git ----------

def git_pull(root: Path) -> None:
    repo = Repo(root)
    try:
        repo.remotes.origin.pull(rebase=True)
    except Exception as e:
        log.warning("pull failed: %s", e)


def git_commit_push(root: Path, message: str, paths: list[Path]) -> None:
    repo = Repo(root)
    for p in paths:
        try:
            repo.index.add([str(p.relative_to(root))])
        except Exception:
            repo.index.add([str(p)])
    if not repo.is_dirty(index=True, working_tree=False, untracked_files=True):
        return
    repo.index.commit(message)
    try:
        repo.remotes.origin.push()
    except Exception as e:
        log.warning("push failed: %s", e)


def open_pr(
    cfg: AgentConfig,
    *,
    title: str,
    body: str,
    issue_number: int | None,
    branch: str,
) -> str | None:
    if not cfg.github_token:
        log.info("no GITHUB_TOKEN, skipping PR")
        return None
    gh = Github(auth=Auth.Token(cfg.github_token))
    repo = gh.get_repo(cfg.todos_repo)
    pr_body = body
    if issue_number:
        pr_body = f"Closes #{issue_number}\n\n{body}"
    try:
        pr = repo.create_pull(
            title=title, body=pr_body, head=branch, base=repo.default_branch
        )
        return pr.html_url
    except Exception as e:
        log.error("create_pull failed: %s", e)
        return None


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


# ---------- agent invocation ----------

def load_owner_context(cfg: AgentConfig) -> str:
    if cfg.owner_context_file and cfg.owner_context_file.exists():
        return cfg.owner_context_file.read_text(encoding="utf-8").strip()
    return ""


def build_prompt(*, title: str, owner: str, context: str, instructions: str,
                 owner_context: str) -> str:
    block = ""
    if owner_context:
        block = f"Household background you may rely on:\n{owner_context}\n"
    return DEFAULT_PROMPT_TEMPLATE.format(
        title=title,
        owner=owner,
        context=context or "(none)",
        instructions=instructions or "(none — use your judgment)",
        owner_context_block=block,
    )


async def run_agent(prompt: str) -> str:
    """Invoke the Claude Agent SDK and return the agent's final text output.

    Uses the local `claude` CLI's OAuth session — no API key required.
    Make sure `claude login` has been run on the machine.
    """
    if _SDK_STYLE != "query":
        raise RuntimeError(
            "claude-agent-sdk not available — install it in the todos-agent venv"
        )

    options = ClaudeAgentOptions(
        permission_mode="acceptEdits",
        allowed_tools=["WebSearch", "WebFetch", "Read", "Grep", "Glob"],
    )
    chunks: list[str] = []
    async for message in query(prompt=prompt, options=options):
        # The SDK yields typed message objects. We're interested in the
        # assistant's final text; pull out any TextBlock content.
        content = getattr(message, "content", None)
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for block in content:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    chunks.append(text)
    return "\n".join(chunks).strip()


# ---------- section extraction ----------

FINDINGS_RE = re.compile(r"##\s*Agent findings\s*\n(.*?)(?=\n##\s|\Z)", re.S | re.I)
DECISION_RE = re.compile(r"##\s*Decision needed\s*\n(.*?)(?=\n##\s|\Z)", re.S | re.I)
BLOCKED_HINT_RE = re.compile(r"\b(blocked|need(s)? input|cannot proceed)\b", re.I)


def parse_agent_output(text: str) -> tuple[str, str, bool]:
    findings_m = FINDINGS_RE.search(text)
    decision_m = DECISION_RE.search(text)
    findings = findings_m.group(1).strip() if findings_m else text.strip()
    decision = decision_m.group(1).strip() if decision_m else ""
    blocked = bool(BLOCKED_HINT_RE.search(decision)) and not findings_m
    return findings, decision, blocked


# ---------- main loop ----------

def process_one(cfg: AgentConfig, md: Path, meta: dict, body: str) -> None:
    title = meta.get("title", md.stem)
    owner = meta.get("owner", "user-a")
    context = meta.get("context", "")

    # find instructions section in body, if any
    instructions = ""
    m = re.search(r"##\s*Instructions\s*\n(.*?)(?=\n##\s|\Z)", body, re.S | re.I)
    if m:
        instructions = m.group(1).strip()

    log.info("working on %s (owner=%s)", md.name, owner)

    # 1. mark in_progress
    meta["status"] = "in_progress"
    write_back(md, meta, body)
    git_commit_push(cfg.todos_dir, f"agent: start {title}", [md])

    # 2. branch
    branch = f"agent/{md.stem}-{date.today().isoformat()}"
    try:
        _git(cfg.todos_dir, "checkout", "-B", branch)
    except subprocess.CalledProcessError as e:
        log.error("could not create branch: %s", e.stderr)
        return

    # 3. run agent
    prompt = build_prompt(
        title=title,
        owner=owner,
        context=context,
        instructions=instructions,
        owner_context=load_owner_context(cfg),
    )
    try:
        output = anyio.run(run_agent, prompt)
    except Exception as e:
        log.exception("agent failed for %s: %s", md.name, e)
        meta["status"] = "blocked"
        meta["blocked_reason"] = f"agent error: {e}"
        write_back(md, meta, body)
        git_commit_push(cfg.todos_dir, f"agent: blocked {title}", [md])
        _git(cfg.todos_dir, "checkout", "-")
        return

    findings, decision, blocked = parse_agent_output(output)

    # 4. write back
    new_body = upsert_section(body, "Agent findings", findings or "(no output)")
    if decision:
        new_body = upsert_section(new_body, "Decision needed", decision)

    if blocked:
        meta["status"] = "blocked"
        meta["blocked_reason"] = decision or "agent could not proceed"
    else:
        meta["status"] = "needs_review"
        meta["assignee"] = owner  # so it's clear who reviews

    write_back(md, meta, new_body)
    git_commit_push(cfg.todos_dir, f"agent: {title}", [md])

    # 5. push branch + open PR
    try:
        _git(cfg.todos_dir, "push", "-u", "origin", branch)
    except subprocess.CalledProcessError as e:
        log.error("push branch failed: %s", e.stderr)
        _git(cfg.todos_dir, "checkout", "-")
        return

    pr_url = open_pr(
        cfg,
        title=title,
        body=(findings or "") + ("\n\n---\n\n" + decision if decision else ""),
        issue_number=meta.get("github_issue"),
        branch=branch,
    )
    if pr_url:
        log.info("opened PR %s", pr_url)

    # back to default branch for next iteration
    try:
        _git(cfg.todos_dir, "checkout", "-")
    except subprocess.CalledProcessError:
        _git(cfg.todos_dir, "checkout", "main")


def run_once(cfg: AgentConfig) -> int:
    git_pull(cfg.todos_dir)
    items = list(find_delegated(cfg.todos_dir))
    log.info("found %d delegated items", len(items))
    processed = 0
    for md, meta, body in items[: cfg.max_items_per_run]:
        try:
            process_one(cfg, md, meta, body)
            processed += 1
        except Exception:
            log.exception("error processing %s", md)
    return processed


def main() -> None:
    cfg = AgentConfig.from_env()
    _setup_logging(cfg.log_dir)
    log.info("todos-agent run, dir=%s, repo=%s", cfg.todos_dir, cfg.todos_repo)
    n = run_once(cfg)
    log.info("processed %d items", n)


if __name__ == "__main__":
    main()
