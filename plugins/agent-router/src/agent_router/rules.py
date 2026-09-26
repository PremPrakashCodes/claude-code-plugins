"""Rules engine: weighted signal scoring with a confidence value, no LLM calls.

Each signal adds evidence points to a tier. The winning tier is the one with the
most points; confidence is its share of all points, damped when there is little
evidence overall. A short prompt counts as evidence for the cheap tier, so a short
prompt with heavyweight vocabulary lands below the threshold and is treated as
ambiguous rather than confidently routed either way.

Signals record matched keywords and structural markers only - never prompt text -
so they are safe to write to the routing log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Keyword classes. Multi-word phrases are matched as whole phrases.
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "low": (
        "format",
        "reformat",
        "rename",
        "typo",
        "spelling",
        "lint",
        "imports",
        "sort",
        "summarize",
        "summary",
        "list",
        "find",
        "search",
        "grep",
        "locate",
        "lookup",
        "look up",
        "where is",
        "which file",
        "what is",
        "show me",
        "count",
        "translate",
        "docstring",
        "comment",
        "usages",
    ),
    "mid": (
        "implement",
        "add",
        "create",
        "write",
        "build",
        "fix",
        "update",
        "change",
        "test",
        "tests",
        "feature",
        "endpoint",
        "function",
        "component",
        "docs",
    ),
    "high": (
        "architecture",
        "architect",
        "design",
        "redesign",
        "debug",
        "root cause",
        "race condition",
        "race conditions",
        "deadlock",
        "deadlocks",
        "concurrency",
        "refactor",
        "migrate",
        "migration",
        "security",
        "vulnerability",
        "performance",
        "optimize",
        "scalability",
        "distributed",
        "algorithm",
        "trade-off",
        "trade-offs",
        "tradeoff",
        "investigate",
        "review",
        "intermittent",
        "intermittently",
        "flaky",
        "why does",
        "why is",
    ),
}

_WEIGHTS = {"low": 1.0, "mid": 1.0, "high": 1.5}
# Low-tier keywords that on their own mark a mechanical task.
_STRONG_LOW = {
    "format",
    "reformat",
    "rename",
    "typo",
    "spelling",
    "lint",
    "summarize",
    "summary",
    "grep",
    "docstring",
}
_MAX_HITS_PER_CLASS = 3

_PATTERNS = {
    tier: re.compile(r"\b(" + "|".join(re.escape(k) for k in words) + r")\b")
    for tier, words in _KEYWORDS.items()
}

_STACK_TRACE = re.compile(
    r"(Traceback \(most recent call last\)|\bException\b|\bError:|\bat \S+\(\S+:\d+\)|panic:)"
)
_CODE_FENCE = re.compile(r"```")
_QUESTION_START = re.compile(r"^\s*(what|where|which|who|when|how many|is|does|do)\b")

# Built-in subagent types with a known workload shape.
_SUBAGENT_HINTS = {"Explore": ("low", 1.5), "Plan": ("high", 1.0)}


@dataclass
class RulesResult:
    tier: str
    confidence: float
    signals: dict[str, Any] = field(default_factory=dict)


def size_band(chars: int, config: dict[str, Any]) -> str:
    rules_cfg = config.get("rules") or {}
    short = rules_cfg.get("shortChars", 200)
    long_ = rules_cfg.get("longChars", 2000)
    if chars < short:
        return "short"
    if chars > long_:
        return "long"
    return "medium"


def is_confident(result: RulesResult, config: dict[str, Any]) -> bool:
    threshold = (config.get("rules") or {}).get("threshold", 0.7)
    try:
        return result.confidence >= float(threshold)
    except (TypeError, ValueError):
        return result.confidence >= 0.7


def _keyword_hits(text: str) -> dict[str, list[str]]:
    lowered = text.lower()
    hits: dict[str, list[str]] = {}
    for tier, pattern in _PATTERNS.items():
        found: list[str] = []
        for match in pattern.findall(lowered):
            if match not in found:
                found.append(match)
        hits[tier] = found
    return hits


def _score(points: dict[str, float], signals: dict[str, Any]) -> RulesResult:
    total = sum(points.values())
    signals["scores"] = {k: round(v, 2) for k, v in points.items()}
    if total <= 0:
        return RulesResult(tier="mid", confidence=0.0, signals=signals)
    # Ties go to the more capable tier: under-powering a task is the costlier error.
    tier = max(("high", "mid", "low"), key=lambda t: points[t])
    share = points[tier] / total
    damping = min(1.0, total / 2.5)
    confidence = round(min(0.95, share * damping), 3)
    return RulesResult(tier=tier, confidence=confidence, signals=signals)


def _keyword_weight(tier: str, word: str) -> float:
    if tier == "low" and word in _STRONG_LOW:
        return 1.5
    return _WEIGHTS[tier]


def _add_keywords(points: dict[str, float], hits: dict[str, list[str]], scale: float) -> None:
    for tier, words in hits.items():
        weights = sorted((_keyword_weight(tier, w) for w in words), reverse=True)
        points[tier] += scale * sum(weights[:_MAX_HITS_PER_CLASS])


def classify_prompt(prompt: str, config: dict[str, Any]) -> RulesResult:
    """Classify a main-session prompt."""
    text = prompt if isinstance(prompt, str) else ""
    points = {"low": 0.0, "mid": 0.0, "high": 0.0}
    hits = _keyword_hits(text)
    _add_keywords(points, hits, 1.0)

    structure: list[str] = []
    band = size_band(len(text), config)
    if text.strip():
        if band == "short":
            points["low"] += 1.5
        elif band == "long":
            points["high"] += 1.0
    if _STACK_TRACE.search(text):
        structure.append("stack_trace")
        points["high"] += 2.0
    if _CODE_FENCE.search(text):
        structure.append("code_block")
        points["mid"] += 0.5
    is_question = text.rstrip().endswith("?") or _QUESTION_START.match(text.lower())
    if band == "short" and is_question and not hits["high"]:
        structure.append("question")
        points["low"] += 1.0

    signals = {"kind": "prompt", "chars": len(text), "band": band, **hits, "structure": structure}
    return _score(points, signals)


def classify_dispatch(
    description: str | None,
    prompt: str | None,
    subagent_type: str | None,
    config: dict[str, Any],
) -> RulesResult:
    """Classify a subagent dispatch.

    Claude writes long, structured dispatch prompts even for trivial lookups, so
    prompt length is ignored here. The short ``description`` carries more weight
    than the prompt body, and known built-in subagent types add a hint.
    """
    desc = description if isinstance(description, str) else ""
    body = prompt if isinstance(prompt, str) else ""
    points = {"low": 0.0, "mid": 0.0, "high": 0.0}
    desc_hits = _keyword_hits(desc)
    body_hits = _keyword_hits(body)
    _add_keywords(points, desc_hits, 1.0)
    _add_keywords(points, body_hits, 0.5)

    structure: list[str] = []
    if _STACK_TRACE.search(body):
        structure.append("stack_trace")
        points["high"] += 1.5
    hint = _SUBAGENT_HINTS.get(subagent_type or "")
    if hint:
        structure.append(f"subagent:{subagent_type}")
        points[hint[0]] += hint[1]

    merged = {t: sorted(set(desc_hits[t]) | set(body_hits[t])) for t in desc_hits}
    signals = {
        "kind": "dispatch",
        "chars": len(body),
        "band": "n/a",
        **merged,
        "structure": structure,
        "subagent_type": subagent_type or "",
    }
    return _score(points, signals)
