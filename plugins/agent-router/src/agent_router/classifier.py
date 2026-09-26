"""AI classifier: pick a complexity tier for a subagent dispatch.

Runs a minimal headless ``claude -p`` call on a fast model. The nested session is
started with ``--safe-mode`` (no plugins, hooks, MCP servers, or CLAUDE.md), no
tools, no session persistence, and thinking off, so each call stays small
(~4k input tokens, ~20 output tokens, 2-4 s in practice). Two independent
recursion guards keep the nested session from re-entering the router:
``disableAllHooks`` in its settings and ``AGENT_ROUTER_NESTED=1`` in its
environment.

Every failure returns a result with ``ok=False`` and a short ``reason``; nothing
here raises, because the caller must fall back to the dispatch's own model.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import TIERS

NESTED_ENV = "AGENT_ROUTER_NESTED"
DEFAULT_TIMEOUT = 6.0
_PROMPT_EXCERPT_CHARS = 4000
_JSON_OBJECT = re.compile(r"\{[^{}]*\}")

_INSTRUCTIONS = """You route coding tasks to the cheapest Claude model that can do them well.
Classify the task below into exactly one tier:

low  - mechanical or lookup work: searching or listing files, reading and
       summarizing, renaming, formatting, small single-file edits with an
       obvious answer.
mid  - ordinary implementation: writing or changing code across a few files,
       adding tests, fixing a bug whose cause is clear.
high - deep reasoning: architecture or design decisions, debugging with an
       unclear root cause, concurrency, security, performance, large refactors
       or migrations, reviews that need judgment.

When unsure between two tiers, pick the higher one.
Reply with only a JSON object: {"tier": "low" | "mid" | "high", "confidence": <0.0-1.0>}"""


@dataclass
class ClassifierResult:
    ok: bool
    tier: str | None = None
    confidence: float | None = None
    reason: str = ""
    duration_ms: int | None = None
    cost_usd: float | None = None
    usage: dict[str, int] = field(default_factory=dict)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def build_prompt(subagent_type: Any, description: Any, prompt: Any) -> str:
    body = _text(prompt)
    if len(body) > _PROMPT_EXCERPT_CHARS:
        body = body[:_PROMPT_EXCERPT_CHARS] + "\n[... truncated]"
    return (
        f"{_INSTRUCTIONS}\n\n"
        f"Subagent type: {_text(subagent_type) or 'general-purpose'}\n"
        f"Task description: {_text(description) or '(none)'}\n"
        f"Task prompt:\n{body or '(none)'}\n"
    )


def build_command(claude: str, model: str) -> list[str]:
    return [
        claude,
        "-p",
        "--model",
        model,
        "--safe-mode",
        "--tools",
        "",
        "--no-session-persistence",
        "--settings",
        # Thinking off: a tier label needs no reasoning trace, and thinking
        # doubled latency (6-7 s vs 2-4 s) in measurement.
        json.dumps({"disableAllHooks": True, "alwaysThinkingEnabled": False}),
        "--output-format",
        "json",
    ]


def _timeout(config: dict[str, Any]) -> float:
    value = (config.get("classifier") or {}).get("timeoutSeconds", DEFAULT_TIMEOUT)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return DEFAULT_TIMEOUT
    return value


def _result_entry(stdout: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(stdout)
    except (ValueError, RecursionError):
        return None
    entries = payload if isinstance(payload, list) else [payload]
    for entry in reversed(entries):
        if isinstance(entry, dict) and entry.get("type") == "result":
            return entry
    return None


def _usage(entry: dict[str, Any]) -> dict[str, int]:
    raw = entry.get("usage")
    if not isinstance(raw, dict):
        return {}
    usage = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ):
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            usage[key] = value
    return usage


def parse_reply(text: str) -> tuple[str, float | None] | None:
    """Extract ``(tier, confidence)`` from the model's reply, tolerating fences."""
    for match in _JSON_OBJECT.findall(text or ""):
        try:
            obj = json.loads(match)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        tier = obj.get("tier")
        if tier not in TIERS:
            return None
        confidence = obj.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return tier, None
        return tier, max(0.0, min(1.0, float(confidence)))
    return None


def classify(
    subagent_type: Any,
    description: Any,
    prompt: Any,
    config: dict[str, Any],
    runner: Callable[..., Any] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> ClassifierResult:
    settings = config.get("classifier") or {}
    if not settings.get("enabled", True):
        return ClassifierResult(ok=False, reason="disabled")
    claude = which("claude")
    if not claude:
        return ClassifierResult(ok=False, reason="claude_not_found")
    model = settings.get("model")
    if not isinstance(model, str) or not model.strip():
        model = "haiku"

    env = dict(os.environ)
    env[NESTED_ENV] = "1"
    started = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        completed = runner(
            build_command(claude, model),
            input=build_prompt(subagent_type, description, prompt),
            capture_output=True,
            text=True,
            timeout=_timeout(config),
            env=env,
        )
    except subprocess.TimeoutExpired:
        return ClassifierResult(ok=False, reason="timeout", duration_ms=elapsed())
    except (OSError, ValueError, subprocess.SubprocessError):
        return ClassifierResult(ok=False, reason="os_error", duration_ms=elapsed())

    if completed.returncode != 0:
        return ClassifierResult(
            ok=False, reason=f"exit_{completed.returncode}", duration_ms=elapsed()
        )
    entry = _result_entry(completed.stdout or "")
    if entry is None:
        return ClassifierResult(ok=False, reason="bad_output", duration_ms=elapsed())

    cost = entry.get("total_cost_usd")
    base = ClassifierResult(
        ok=False,
        # Wall-clock time: the delay the dispatch actually waited, including
        # CLI startup (the CLI's own duration_ms covers only the API call).
        duration_ms=elapsed(),
        cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
        usage=_usage(entry),
    )
    if entry.get("is_error"):
        base.reason = "cli_error"
        return base
    parsed = parse_reply(_text(entry.get("result")))
    if parsed is None:
        base.reason = "bad_reply"
        return base
    base.ok = True
    base.tier, base.confidence = parsed
    return base
