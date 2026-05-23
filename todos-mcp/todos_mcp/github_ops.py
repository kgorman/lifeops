"""GitHub Issues integration."""
from __future__ import annotations

import logging
from typing import Any

from github import Auth, Github, GithubException

log = logging.getLogger(__name__)

# Status → label mapping (the label name used on the Issue).
STATUS_LABEL = {
    "inbox": "status:inbox",
    "active": "status:active",
    "blocked": "status:blocked",
    "delegated": "status:delegated",
    "in_progress": "status:active",
    "needs_review": "status:needs-review",
    "done": "status:done",
    "wont_do": "status:done",
    "someday": "status:inbox",
}


class GitHubOps:
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo_name = repo
        self._gh: Github | None = None

    @property
    def gh(self) -> Github:
        if self._gh is None:
            if not self.token:
                raise RuntimeError("GITHUB_TOKEN is not set")
            self._gh = Github(auth=Auth.Token(self.token))
        return self._gh

    @property
    def repo(self):
        return self.gh.get_repo(self.repo_name)

    def issue_labels(self, *, owner: str, status: str, quadrant: str | None,
                     tags: list[str]) -> list[str]:
        labels = [f"owner:{owner}"]
        if status in STATUS_LABEL:
            labels.append(STATUS_LABEL[status])
        if quadrant:
            labels.append(quadrant)
        labels.extend(tags or [])
        return labels

    def create_issue(
        self,
        *,
        title: str,
        body: str,
        owner: str,
        status: str,
        quadrant: str | None,
        tags: list[str],
    ) -> int | None:
        try:
            issue = self.repo.create_issue(
                title=title,
                body=body,
                labels=self.issue_labels(
                    owner=owner, status=status, quadrant=quadrant, tags=tags
                ),
            )
            return issue.number
        except GithubException as e:
            log.error("create_issue failed: %s", e)
            return None

    def update_issue(self, number: int, **fields: Any) -> bool:
        try:
            issue = self.repo.get_issue(number)
            issue.edit(**fields)
            return True
        except GithubException as e:
            log.error("update_issue %d failed: %s", number, e)
            return False

    def close_issue(self, number: int, *, reason: str = "completed") -> bool:
        try:
            issue = self.repo.get_issue(number)
            issue.edit(state="closed", state_reason=reason)
            return True
        except GithubException as e:
            log.error("close_issue %d failed: %s", number, e)
            return False

    def comment_on_issue(self, number: int, body: str) -> bool:
        try:
            self.repo.get_issue(number).create_comment(body)
            return True
        except GithubException as e:
            log.error("comment_on_issue %d failed: %s", number, e)
            return False

    # ---------- PRs ----------

    def find_pr_for_slug(self, slug: str):
        """Find the most recent open PR whose head branch is `agent/<slug>-*`."""
        try:
            pulls = self.repo.get_pulls(state="open", sort="created", direction="desc")
            prefix = f"agent/{slug}-"
            for pr in pulls:
                if pr.head.ref.startswith(prefix):
                    return pr
            return None
        except GithubException as e:
            log.error("find_pr_for_slug failed: %s", e)
            return None

    def find_pr_for_issue(self, issue_number: int):
        """Fallback: find an open PR whose body references the issue (`Closes #N`)."""
        try:
            needle = f"#{issue_number}"
            for pr in self.repo.get_pulls(state="open"):
                if pr.body and needle in pr.body:
                    return pr
            return None
        except GithubException as e:
            log.error("find_pr_for_issue %d failed: %s", issue_number, e)
            return None

    def merge_pr(self, pr, *, commit_message: str | None = None) -> bool:
        """Squash-merge a PR. Returns True on success."""
        try:
            pr.merge(
                merge_method="squash",
                commit_title=pr.title,
                commit_message=commit_message or "",
            )
            return True
        except GithubException as e:
            log.error("merge_pr %d failed: %s", pr.number, e)
            return False

    def comment_on_pr(self, pr, body: str) -> bool:
        try:
            pr.create_issue_comment(body)
            return True
        except GithubException as e:
            log.error("comment_on_pr %d failed: %s", pr.number, e)
            return False

    def close_pr(self, pr, *, comment: str | None = None) -> bool:
        try:
            if comment:
                pr.create_issue_comment(comment)
            pr.edit(state="closed")
            return True
        except GithubException as e:
            log.error("close_pr %d failed: %s", pr.number, e)
            return False
