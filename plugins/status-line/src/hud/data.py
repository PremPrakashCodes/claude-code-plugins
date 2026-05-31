"""Parse the JSON payload Claude Code pipes to the status line on stdin.

Only the fields the HUD needs are extracted, each behind a tolerant getter so a
missing or renamed field degrades gracefully instead of crashing the line.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from typing import Any

DEFAULT_CONTEXT_WINDOW = 200_000


@dataclass
class Window:
    """A rate-limit window (e.g. the 5-hour or 7-day quota)."""

    used_percent: float | None = None
    resets_at: float | None = None  # unix seconds


@dataclass
class HudData:
    model_display: str = ""
    model_id: str = ""
    cwd: str = ""
    context_window: int = DEFAULT_CONTEXT_WINDOW
    total_tokens: int = 0
    context_percent: float = 0.0
    cost_usd: float | None = None
    duration_ms: float | None = None
    lines_added: int | None = None
    lines_removed: int | None = None
    windows: dict[str, Window] = field(default_factory=dict)


def _get(d: Any, *path: str, default: Any = None) -> Any:
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        # json.loads accepts NaN/Infinity; keep them out so int()/formatting
        # downstream never raises or renders "inf%".
        result = float(value)
        return result if math.isfinite(result) else None
    return None


def parse(stdin_json: dict[str, Any]) -> HudData:
    d = stdin_json or {}
    data = HudData()

    data.model_display = _get(d, "model", "display_name", default="") or ""
    data.model_id = _get(d, "model", "id", default="") or ""

    data.cwd = _get(d, "workspace", "current_dir") or d.get("cwd") or ""

    window_size = _num(_get(d, "context_window", "context_window_size"))
    data.context_window = int(window_size) if window_size else DEFAULT_CONTEXT_WINDOW

    usage = _get(d, "context_window", "current_usage", default={}) or {}
    data.total_tokens = int(
        (_num(usage.get("input_tokens")) or 0)
        + (_num(usage.get("cache_creation_input_tokens")) or 0)
        + (_num(usage.get("cache_read_input_tokens")) or 0)
    )

    native_used = _num(_get(d, "context_window", "used_percentage"))
    if native_used is not None and native_used >= 0:  # trust an explicit 0
        data.context_percent = native_used
    elif data.context_window > 0:
        data.context_percent = 100.0 * data.total_tokens / data.context_window

    data.cost_usd = _num(_get(d, "cost", "total_cost_usd"))
    data.duration_ms = _num(_get(d, "cost", "total_duration_ms"))
    la = _num(_get(d, "cost", "total_lines_added"))
    lr = _num(_get(d, "cost", "total_lines_removed"))
    data.lines_added = int(la) if la is not None else None
    data.lines_removed = int(lr) if lr is not None else None

    limits = _get(d, "rate_limits", default={}) or {}
    mapping = {"5h": "five_hour", "7d": "seven_day"}
    for key, source in mapping.items():
        block = limits.get(source) or {}
        if block:
            data.windows[key] = Window(
                used_percent=_num(block.get("used_percentage")),
                resets_at=_num(block.get("resets_at")),
            )
    return data


def read_payload() -> dict[str, Any]:
    """Read and JSON-decode the stdin payload, tolerating empty/malformed input."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (RecursionError, ValueError):
        payload = {}
    return payload if isinstance(payload, dict) else {}
