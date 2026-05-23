"""Git operations: pull before read, commit + push after write.

Designed to be tolerant of merge conflicts on data files:
- frontmatter conflicts → last write wins
- body section conflicts → append both sides
"""
from __future__ import annotations

import logging
from pathlib import Path

from git import GitCommandError, Repo

log = logging.getLogger(__name__)


class GitOps:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._repo: Repo | None = None

    @property
    def repo(self) -> Repo:
        if self._repo is None:
            self._repo = Repo(self.root)
        return self._repo

    def is_repo(self) -> bool:
        try:
            _ = self.repo
            return True
        except Exception:
            return False

    def pull(self) -> None:
        if not self.is_repo():
            log.warning("not a git repo at %s, skipping pull", self.root)
            return
        try:
            origin = self.repo.remotes["origin"]
        except (IndexError, AttributeError):
            log.debug("no origin remote at %s, skipping pull", self.root)
            return
        try:
            origin.pull(rebase=True)
        except GitCommandError as e:
            log.error("git pull failed: %s", e)
            self._resolve_conflicts()

    def commit_and_push(self, message: str, paths: list[Path] | None = None) -> bool:
        if not self.is_repo():
            log.warning("not a git repo, skipping commit/push")
            return False
        repo = self.repo
        if paths:
            for p in paths:
                try:
                    repo.index.add([str(p.relative_to(self.root))])
                except Exception:
                    repo.index.add([str(p)])
        else:
            repo.git.add(A=True)
        if not repo.is_dirty(index=True, working_tree=False, untracked_files=True):
            return False
        repo.index.commit(message)
        try:
            origin = repo.remotes["origin"]
        except (IndexError, AttributeError):
            log.debug("no origin remote, skipping push")
            return True
        try:
            origin.push()
        except GitCommandError as e:
            log.error("push failed: %s", e)
            return False
        return True

    def _resolve_conflicts(self) -> None:
        """Naive conflict resolution: prefer 'theirs' for frontmatter lines,
        keep both bodies. For data files only — code conflicts will halt."""
        repo = self.repo
        for entry in repo.index.unmerged_blobs():
            path = self.root / entry
            if path.suffix != ".md":
                continue
            try:
                text = path.read_text(encoding="utf-8")
                cleaned = self._strip_conflict_markers(text)
                path.write_text(cleaned, encoding="utf-8")
                repo.index.add([entry])
            except Exception as e:
                log.error("could not auto-resolve %s: %s", path, e)
        try:
            repo.git.rebase("--continue")
        except GitCommandError:
            repo.git.rebase("--abort")

    @staticmethod
    def _strip_conflict_markers(text: str) -> str:
        out: list[str] = []
        in_left = False
        in_right = False
        for line in text.splitlines():
            if line.startswith("<<<<<<<"):
                in_left = True
                continue
            if line.startswith("======="):
                in_left = False
                in_right = True
                continue
            if line.startswith(">>>>>>>"):
                in_right = False
                continue
            # keep both halves
            if in_left or in_right or (not in_left and not in_right):
                out.append(line)
        return "\n".join(out) + "\n"
