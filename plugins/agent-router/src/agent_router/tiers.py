"""Turn the classifier's answer into the tier the dispatch is routed to.

Two adjustments, each moving at most one tier up and never down:

- ``low_confidence``: the classifier's confidence is missing or below
  ``classifier.minConfidence``. Routing too low risks weaker subagent work;
  routing one tier too high only costs a little more.
- ``adaptive``: past rewritten dispatches of this subagent type at this tier
  show too many quality issues (see ``adaptive.py``).
"""

from __future__ import annotations

from typing import Any

from . import adaptive as adaptive_mod
from .config import next_tier

DEFAULT_MIN_CONFIDENCE = 0.7


def _min_confidence(config: dict[str, Any]) -> float:
    value = (config.get("classifier") or {}).get("minConfidence", DEFAULT_MIN_CONFIDENCE)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DEFAULT_MIN_CONFIDENCE
    return value


def confidence_adjusted(
    tier: str, confidence: float | None, config: dict[str, Any]
) -> tuple[str, list[str]]:
    if confidence is None or confidence < _min_confidence(config):
        raised = next_tier(tier)
        if raised != tier:
            return raised, ["low_confidence"]
    return tier, []


def route_tier(
    tier: str,
    confidence: float | None,
    subagent_type: str,
    config: dict[str, Any],
    stats: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """The routed tier and the adjustments that produced it."""
    routed, adjustments = confidence_adjusted(tier, confidence, config)
    if stats and adaptive_mod.is_escalated(stats, subagent_type, routed, config):
        raised = next_tier(routed)
        if raised != routed:
            routed = raised
            adjustments.append("adaptive")
    return routed, adjustments
