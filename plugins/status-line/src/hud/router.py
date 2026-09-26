"""Read the agent-router plugin's per-session savings summary.

agent-router (a sibling plugin in this marketplace) writes
``$CLAUDE_CONFIG_DIR/plugins/agent-router/summary.json`` when each turn ends:

    {"version": 1, "sessions": {"<session_id>": {"routed": 4, "net_savings_usd": 0.38}}}

The status line reads only this small file - never the routing log - because it
refreshes constantly. A missing or malformed file simply hides the segment.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .data import _num


def summary_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "plugins" / "agent-router" / "summary.json"


def session_summary(session_id: str) -> tuple[int, float] | None:
    """``(routed dispatches, net savings in USD)`` for the session, or None."""
    if not session_id:
        return None
    try:
        raw: Any = json.loads(summary_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    sessions = raw.get("sessions") if isinstance(raw, dict) else None
    entry = sessions.get(session_id) if isinstance(sessions, dict) else None
    if not isinstance(entry, dict):
        return None
    routed = _num(entry.get("routed"))
    savings = _num(entry.get("net_savings_usd"))
    if routed is None or savings is None or routed < 1:
        return None
    return int(routed), savings
