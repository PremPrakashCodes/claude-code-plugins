"""Per-session savings summary for the status line.

The Stop hook writes ``$CLAUDE_CONFIG_DIR/plugins/agent-router/summary.json``
after each turn:

    {"version": 1, "sessions": {"<session_id>": {"routed": 4, "net_savings_usd": 0.38,
                                                 "updated": 1790459036.2}}}

The status-line plugin's ``router`` segment reads this file on every refresh, so
it stays tiny (the most recent ``MAX_SESSIONS`` sessions) and is replaced
atomically so a reader never sees a half-written file. The path is fixed - not
under ``CLAUDE_PLUGIN_DATA`` - because another plugin has to find it.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

VERSION = 1
MAX_SESSIONS = 50


def summary_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "plugins" / "agent-router" / "summary.json"


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    sessions = data.get("sessions") if isinstance(data, dict) else None
    return sessions if isinstance(sessions, dict) else {}


def update(session_id: str, routed: int, net_savings_usd: float) -> bool:
    """Record this session's totals. Returns False (never raises) on failure."""
    if not session_id:
        return False
    path = summary_path()
    sessions = _load(path)
    sessions[session_id] = {
        "routed": routed,
        "net_savings_usd": round(net_savings_usd, 6),
        "updated": time.time(),
    }
    recent = sorted(
        sessions.items(),
        key=lambda item: item[1].get("updated", 0) if isinstance(item[1], dict) else 0,
        reverse=True,
    )[:MAX_SESSIONS]
    payload = json.dumps({"version": VERSION, "sessions": dict(recent)}, indent=2)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".summary-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")
            os.replace(tmp, path)
        except OSError:
            os.unlink(tmp)
            raise
        return True
    except OSError:
        return False
