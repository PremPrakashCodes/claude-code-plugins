"""Lightweight git status, gathered with short-timeout subprocess calls.

Everything is best-effort: if git is missing, the directory is not a repo, or a
call is slow, the corresponding field stays empty and the segment is skipped.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

# Per-call cap. collect() makes up to ~4 of these sequentially, so this is also
# (roughly) the worst-case prompt stall on a slow/network repo -- keep it tight.
_TIMEOUT = 0.5


@dataclass
class GitStatus:
    branch: str = ""
    dirty: bool = False
    ahead: int = 0
    behind: int = 0
    modified: int = 0
    added: int = 0
    deleted: int = 0
    untracked: int = 0

    @property
    def is_repo(self) -> bool:
        return bool(self.branch)


def _run(args: list[str], cwd: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def collect(cwd: str, *, ahead_behind: bool = True, file_stats: bool = False) -> GitStatus:
    status = GitStatus()
    if not cwd:
        return status

    branch = _run(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch is None:
        return status
    branch = branch.strip()
    if branch == "HEAD":  # detached -> short sha
        sha = _run(["rev-parse", "--short", "HEAD"], cwd)
        branch = sha.strip() if sha else "HEAD"
    status.branch = branch

    porcelain = _run(["status", "--porcelain"], cwd)
    if porcelain:
        lines = [ln for ln in porcelain.splitlines() if ln]
        status.dirty = bool(lines)
        if file_stats:
            for ln in lines:
                code = ln[:2]
                if code == "??":
                    status.untracked += 1
                    continue
                index, worktree = code[0], code[1]
                if "A" in code:
                    status.added += 1
                elif "D" in (index, worktree):
                    status.deleted += 1
                elif "M" in (index, worktree) or "R" in code:
                    status.modified += 1

    if ahead_behind:
        counts = _run(["rev-list", "--left-right", "--count", "@{upstream}...HEAD"], cwd)
        if counts:
            parts = counts.split()
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                status.behind, status.ahead = int(parts[0]), int(parts[1])

    return status
