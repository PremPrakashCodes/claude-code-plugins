"""Hook handlers: decide the routing and build the hook's JSON reply.

Handlers are pure functions over the parsed payload and config. They return the
JSON object to print (or None to print nothing) plus the records to log; the CLI
does the I/O. Nothing here may raise into the host.
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Callable

from . import classifier as classifier_mod
from . import data as data_mod
from . import outcomes as outcomes_mod
from . import report as report_mod
from .config import tier_model

# Claude Code's setting for a default subagent model; a user-chosen default is
# an explicit choice the router must respect.
SUBAGENT_MODEL_ENV = "CLAUDE_CODE_SUBAGENT_MODEL"


def _fingerprint(event: data_mod.DispatchEvent) -> str:
    digest = hashlib.sha256(f"{event.description}\n{event.prompt}".encode()).hexdigest()
    return digest[:16]


def _decision(event: data_mod.DispatchEvent, **fields: Any) -> dict[str, Any]:
    record = {
        "kind": "decision",
        "ts": time.time(),
        "session_id": event.session_id,
        "prompt_id": event.prompt_id,
        "tool_use_id": event.tool_use_id,
        "subagent_type": event.subagent_type,
        "fingerprint": _fingerprint(event),
        "signals": {
            "description_chars": len(event.description),
            "prompt_chars": len(event.prompt),
        },
    }
    record.update(fields)
    return record


def _classifier_fields(result: classifier_mod.ClassifierResult) -> dict[str, Any]:
    return {
        "duration_ms": result.duration_ms,
        "cost_usd": result.cost_usd,
        "usage": result.usage,
    }


def route_task(
    payload: dict[str, Any],
    config: dict[str, Any],
    classify: Callable[..., classifier_mod.ClassifierResult] = classifier_mod.classify,
    session_model: Callable[[str], str | None] = data_mod.session_model_from_transcript,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """PreToolUse on Task/Agent: classify the dispatch and rewrite its model."""
    event = data_mod.parse_dispatch(payload)
    if not event.is_dispatch:
        return None, []
    if not (config.get("classifier") or {}).get("enabled", True):
        return None, []

    override = None
    if event.explicit_model:
        override = ("dispatch", event.explicit_model)
    else:
        pinned = data_mod.agent_definition_model(event.subagent_type, event.cwd)
        if pinned:
            override = ("agent_definition", pinned)
        elif os.environ.get(SUBAGENT_MODEL_ENV, "").strip():
            override = ("subagent_model_env", os.environ[SUBAGENT_MODEL_ENV].strip())
    if override:
        record = _decision(
            event, source="override", action="kept", override=override[0], model=override[1]
        )
        return None, [record]

    result = classify(event.subagent_type, event.description, event.prompt, config)
    if not result.ok or not result.tier:
        record = _decision(
            event,
            source="fallback",
            action="kept",
            reason=result.reason,
            classifier=_classifier_fields(result),
        )
        return None, [record]

    target = tier_model(config, result.tier)
    fields: dict[str, Any] = {
        "source": "LLM",
        "tier": result.tier,
        "confidence": result.confidence,
        "classifier": _classifier_fields(result),
    }
    if not target:
        record = _decision(event, action="kept", reason="no_tier_model", **fields)
        return None, [record]

    transcript = payload.get("transcript_path") if isinstance(payload, dict) else None
    # Subagents without a pinned model (built-ins such as Explore included)
    # inherit the session model, so that is the baseline never to upgrade past.
    baseline = session_model(transcript if isinstance(transcript, str) else "")
    fields["baseline_model"] = baseline
    target_family = data_mod.model_family(target)
    baseline_family = data_mod.model_family(baseline)
    if not (target_family and baseline_family):
        # Without both families the router cannot prove the rewrite is not an
        # upgrade, so it fails closed and leaves the dispatch alone.
        record = _decision(event, action="kept", reason="unknown_model_family", **fields)
        return None, [record]
    target_rank = data_mod.FAMILY_RANK[target_family]
    baseline_rank = data_mod.FAMILY_RANK[baseline_family]
    if target_rank > baseline_rank:
        record = _decision(event, action="kept", model=baseline, reason="no_upgrade", **fields)
        return None, [record]
    if target_family == baseline_family:
        record = _decision(event, action="kept", model=baseline, reason="same_model", **fields)
        return None, [record]

    updated = dict(event.tool_input)  # updatedInput replaces the whole input
    updated["model"] = target
    reply = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": updated}}
    return reply, [_decision(event, action="rewrite", model=target, **fields)]


def record_outcome(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """PostToolUse / SubagentStop: records that link a dispatch to its outcome."""
    if not isinstance(payload, dict):
        return []
    event_name = payload.get("hook_event_name")
    if event_name == "PostToolUse":
        if payload.get("tool_name") not in data_mod.DISPATCH_TOOLS:
            return []
        link = outcomes_mod.link_record(payload)
        return [link] if link else []
    if event_name == "SubagentStop":
        stop = outcomes_mod.stop_record(payload)
        return [stop] if stop else []
    return []


def finish_turn(
    session_id: str, session_records: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], tuple[int, float] | None]:
    """Stop: new outcome records, plus the session's (routed, net savings) totals.

    Totals are None when the session has made no routing decisions, so sessions
    that never dispatched a subagent leave no summary behind.
    """
    new_outcomes = outcomes_mod.resolve_pending(session_records, session_id)
    if not any(r.get("kind") == "decision" for r in session_records):
        return new_outcomes, None
    totals = report_mod.summarize(session_records + new_outcomes, config)
    return new_outcomes, (totals["rewrites"], totals["net_savings_usd"])
