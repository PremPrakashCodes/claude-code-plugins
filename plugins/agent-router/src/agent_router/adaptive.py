"""Quality signals and adaptive tier escalation.

A rewritten dispatch has a *quality issue* when its subagent returned a
near-empty result, or when the same task (same subagent type and description)
was dispatched again in the same session soon after - a sign the first,
cheaper attempt was not good enough.

Adaptive routing counts outcomes and issues per ``(subagent type, tier)``. Once
a group has at least ``adaptive.minSamples`` outcomes and its issue rate reaches
``adaptive.maxIssueRate``, later dispatches of that type at that tier route one
tier up. It only ever escalates, so the worst case is a smaller saving.

The Stop hook recomputes the counts from the log and writes them to a small
``adaptive.json``; the routing hook only reads that file, never the log.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

from .log import data_dir, locked

VERSION = 1


def stats_path() -> Path:
    return data_dir() / "adaptive.json"


def _setting(config: dict[str, Any], key: str, default: float) -> float:
    value = (config.get("adaptive") or {}).get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return default
    return value


def quality_issues(
    records: Iterable[dict[str, Any]], config: dict[str, Any]
) -> dict[str, list[str]]:
    """Map each dispatch ``tool_use_id`` to its quality issues (empty list = none).

    Only dispatches with a captured outcome are included, so a missing key means
    "no evidence yet", not "fine".
    """
    decisions: list[dict[str, Any]] = []
    outcomes: dict[str, dict[str, Any]] = {}
    for record in records:
        kind = record.get("kind")
        if kind == "decision" and record.get("tool_use_id"):
            decisions.append(record)
        elif kind == "outcome" and record.get("tool_use_id"):
            outcomes[record["tool_use_id"]] = record

    short_chars = _setting(config, "shortResultChars", 20)
    window = _setting(config, "redispatchWindowSeconds", 900)

    # Later dispatches of the same task in the same session.
    redispatched: set[str] = set()
    by_task: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in decisions:
        key = (
            record.get("session_id") or "",
            record.get("subagent_type") or "",
            record.get("task_key") or "",
        )
        if not key[2]:
            continue
        by_task.setdefault(key, []).append(record)
    for group in by_task.values():
        group.sort(key=lambda r: r.get("ts") or 0)
        for earlier, later in zip(group, group[1:]):
            gap = (later.get("ts") or 0) - (earlier.get("ts") or 0)
            if 0 <= gap <= window:
                redispatched.add(earlier["tool_use_id"])

    issues: dict[str, list[str]] = {}
    for tool_use_id, outcome in outcomes.items():
        found = []
        chars = outcome.get("result_chars")
        if isinstance(chars, int) and chars < short_chars:
            found.append("short_result")
        if tool_use_id in redispatched:
            found.append("redispatched")
        issues[tool_use_id] = found
    return issues


def compute(records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """Outcome and issue counts per ``subagent_type|tier`` for rewritten dispatches."""
    issues = quality_issues(records, config)
    groups: dict[str, dict[str, int]] = {}
    for record in records:
        if record.get("kind") != "decision" or record.get("action") != "rewrite":
            continue
        tool_use_id = record.get("tool_use_id")
        if tool_use_id not in issues:
            continue
        key = f"{record.get('subagent_type') or ''}|{record.get('tier') or ''}"
        group = groups.setdefault(key, {"outcomes": 0, "issues": 0})
        group["outcomes"] += 1
        if issues[tool_use_id]:
            group["issues"] += 1
    return {"version": VERSION, "updated": time.time(), "groups": groups}


def is_escalated(
    stats: dict[str, Any], subagent_type: str, tier: str, config: dict[str, Any]
) -> bool:
    """True when this type/tier's issue rate says to route one tier up."""
    if not (config.get("adaptive") or {}).get("enabled", True):
        return False
    groups = stats.get("groups") if isinstance(stats, dict) else None
    group = groups.get(f"{subagent_type}|{tier}") if isinstance(groups, dict) else None
    if not isinstance(group, dict):
        return False
    outcomes, issues = group.get("outcomes"), group.get("issues")
    if not isinstance(outcomes, int) or not isinstance(issues, int) or outcomes <= 0:
        return False
    if outcomes < _setting(config, "minSamples", 5):
        return False
    return issues / outcomes >= _setting(config, "maxIssueRate", 0.4)


def load(path: Path | None = None) -> dict[str, Any]:
    try:
        data = json.loads((path or stats_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def save(stats: dict[str, Any], path: Path | None = None) -> bool:
    """Atomically replace the stats file. Returns False (never raises) on failure."""
    target = path or stats_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with locked(target):
            fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".adaptive-", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(stats, indent=2) + "\n")
                os.replace(tmp, target)
            except OSError:
                os.unlink(tmp)
                raise
        return True
    except OSError:
        return False
