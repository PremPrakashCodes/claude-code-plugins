"""Outcome capture: tokens and duration for routed subagent dispatches.

Background subagents report no usage in ``PostToolUse`` - it fires at launch with
only the ``agentId`` and resolved model - and a subagent's transcript may not be
flushed yet when ``SubagentStop`` fires. So outcomes are captured in three steps:

1. ``PostToolUse`` links the dispatch's ``tool_use_id`` to the ``agentId``.
2. ``SubagentStop`` records the subagent's transcript path.
3. ``Stop`` (and ``report``) read finished transcripts and write outcome records.

Token usage comes from the per-message ``usage`` blocks in the transcript.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Iterable

_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def _parse_ts(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def summarize_transcript(path: str) -> dict[str, Any] | None:
    """Sum token usage per model across a transcript's assistant messages.

    Transcripts repeat a message's row once per content block with the same
    ``usage``, so rows are de-duplicated by message id.
    """
    if not path:
        return None
    totals = {key: 0 for key in _USAGE_KEYS}
    models: dict[str, int] = {}
    seen: set[str] = set()
    first_ts = last_ts = None
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict):
                    continue
                ts = _parse_ts(row.get("timestamp"))
                if ts is not None:
                    first_ts = ts if first_ts is None else min(first_ts, ts)
                    last_ts = ts if last_ts is None else max(last_ts, ts)
                if row.get("type") != "assistant":
                    continue
                message = row.get("message")
                if not isinstance(message, dict):
                    continue
                message_id = message.get("id")
                if isinstance(message_id, str):
                    if message_id in seen:
                        continue
                    seen.add(message_id)
                usage = message.get("usage")
                if isinstance(usage, dict):
                    for key in _USAGE_KEYS:
                        value = usage.get(key)
                        if isinstance(value, int) and not isinstance(value, bool):
                            totals[key] += value
                model = message.get("model")
                if isinstance(model, str) and model:
                    models[model] = models.get(model, 0) + 1
    except OSError:
        return None
    if not models:
        return None
    duration = None
    if first_ts is not None and last_ts is not None:
        duration = int((last_ts - first_ts) * 1000)
    return {
        "model": max(models, key=lambda m: models[m]),
        "usage": totals,
        "duration_ms": duration,
        "messages": len(seen) or sum(models.values()),
    }


def link_record(payload: dict[str, Any]) -> dict[str, Any] | None:
    """A ``link`` record from a PostToolUse payload for a subagent dispatch."""
    response = payload.get("tool_response")
    if not isinstance(response, dict):
        return None
    agent_id = response.get("agentId")
    if not isinstance(agent_id, str) or not agent_id:
        return None
    resolved = response.get("resolvedModel")
    return {
        "kind": "link",
        "ts": time.time(),
        "session_id": payload.get("session_id") or "",
        "tool_use_id": payload.get("tool_use_id") or "",
        "agent_id": agent_id,
        "resolved_model": resolved if isinstance(resolved, str) else None,
        "async": bool(response.get("isAsync")),
    }


def stop_record(payload: dict[str, Any]) -> dict[str, Any] | None:
    """A ``subagent_stop`` record from a SubagentStop payload."""
    agent_id = payload.get("agent_id")
    transcript = payload.get("agent_transcript_path")
    if not isinstance(agent_id, str) or not agent_id or not isinstance(transcript, str):
        return None
    return {
        "kind": "subagent_stop",
        "ts": time.time(),
        "session_id": payload.get("session_id") or "",
        "agent_id": agent_id,
        "agent_type": payload.get("agent_type") or "",
        "transcript": transcript,
    }


def resolve_pending(
    records: Iterable[dict[str, Any]], session_id: str | None = None
) -> list[dict[str, Any]]:
    """Outcome records for finished subagents that do not have one yet.

    Limited to ``session_id`` when given. Only routed dispatches - those with a
    ``link`` back to a decision's ``tool_use_id`` - are resolved.
    """
    links: dict[str, dict[str, Any]] = {}
    stops: dict[str, dict[str, Any]] = {}
    done: set[str] = set()
    for record in records:
        kind = record.get("kind")
        agent_id = record.get("agent_id")
        if not isinstance(agent_id, str):
            continue
        if kind == "link":
            links[agent_id] = record
        elif kind == "subagent_stop":
            stops[agent_id] = record
        elif kind == "outcome":
            done.add(agent_id)
    outcomes = []
    for agent_id, stop in stops.items():
        if agent_id in done or agent_id not in links:
            continue
        if session_id and stop.get("session_id") != session_id:
            continue
        summary = summarize_transcript(stop.get("transcript") or "")
        if summary is None:
            continue
        link = links[agent_id]
        outcomes.append(
            {
                "kind": "outcome",
                "ts": time.time(),
                "session_id": stop.get("session_id") or "",
                "agent_id": agent_id,
                "tool_use_id": link.get("tool_use_id") or "",
                "resolved_model": link.get("resolved_model") or summary["model"],
                "model": summary["model"],
                "usage": summary["usage"],
                "duration_ms": summary["duration_ms"],
                "messages": summary["messages"],
            }
        )
    return outcomes
