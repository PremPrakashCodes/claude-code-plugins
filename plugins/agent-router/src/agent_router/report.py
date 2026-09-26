"""Summarize the routing log: what was routed, and what it saved.

Savings are an estimate. For each rewritten dispatch with a captured outcome,
the subagent's actual token usage is priced twice with the ``pricing`` table:
once at the model it ran on, once at the baseline model it would have used.
The difference, minus what every classifier call cost, is the net saving.
"""

from __future__ import annotations

from typing import Any, Iterable

from .data import model_family

_PRICE_FIELDS = (
    ("input_tokens", "input"),
    ("output_tokens", "output"),
    ("cache_read_input_tokens", "cacheRead"),
    ("cache_creation_input_tokens", "cacheWrite"),
)


def usage_cost(usage: dict[str, Any], model: str | None, config: dict[str, Any]) -> float | None:
    """USD cost of ``usage`` on ``model`` from the price table, or None if unpriced."""
    family = model_family(model)
    prices = (config.get("pricing") or {}).get(family or "")
    if not isinstance(prices, dict) or not isinstance(usage, dict):
        return None
    total = 0.0
    for usage_key, price_key in _PRICE_FIELDS:
        tokens = usage.get(usage_key) or 0
        price = prices.get(price_key) or 0
        if isinstance(tokens, (int, float)) and isinstance(price, (int, float)):
            total += tokens * price / 1_000_000
    return total


def _bump(counts: dict[str, int], key: Any) -> None:
    label = key if isinstance(key, str) and key else "unknown"
    counts[label] = counts.get(label, 0) + 1


def summarize(records: Iterable[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    outcomes: dict[str, dict[str, Any]] = {}
    for record in records:
        kind = record.get("kind")
        if kind == "decision":
            decisions.append(record)
        elif kind == "outcome" and record.get("tool_use_id"):
            outcomes[record["tool_use_id"]] = record

    by_source: dict[str, int] = {}
    rewrites_by_model: dict[str, int] = {}
    kept_reasons: dict[str, int] = {}
    fallback_reasons: dict[str, int] = {}
    classifier_cost = 0.0
    classifier_calls = 0
    classifier_ms = 0
    actual = baseline = 0.0
    with_outcome = without_baseline = rewrites = 0

    for record in decisions:
        source = record.get("source")
        _bump(by_source, source)
        classifier = record.get("classifier")
        if isinstance(classifier, dict):
            classifier_calls += 1
            cost = classifier.get("cost_usd")
            if isinstance(cost, (int, float)):
                classifier_cost += cost
            duration = classifier.get("duration_ms")
            if isinstance(duration, (int, float)):
                classifier_ms += duration
        if source == "fallback":
            _bump(fallback_reasons, record.get("reason"))
        if record.get("action") != "rewrite":
            if source == "LLM":
                _bump(kept_reasons, record.get("reason"))
            continue
        rewrites += 1
        _bump(rewrites_by_model, record.get("model"))
        result = outcomes.get(record.get("tool_use_id") or "")
        if not result:
            continue
        usage = result.get("usage") or {}
        spent = usage_cost(usage, result.get("model") or record.get("model"), config)
        would_have = usage_cost(usage, record.get("baseline_model"), config)
        if spent is None or would_have is None:
            without_baseline += 1
            continue
        with_outcome += 1
        actual += spent
        baseline += would_have

    return {
        "decisions": len(decisions),
        "by_source": by_source,
        "rewrites": rewrites,
        "rewrites_by_model": rewrites_by_model,
        "kept_reasons": kept_reasons,
        "fallback_reasons": fallback_reasons,
        "classifier_calls": classifier_calls,
        "classifier_cost_usd": round(classifier_cost, 6),
        "classifier_avg_ms": int(classifier_ms / classifier_calls) if classifier_calls else 0,
        "routed_with_outcome": with_outcome,
        "rewrites_without_baseline": without_baseline,
        "routed_actual_cost_usd": round(actual, 6),
        "routed_baseline_cost_usd": round(baseline, 6),
        "net_savings_usd": round(baseline - actual - classifier_cost, 6),
    }


def _counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))


def format_summary(summary: dict[str, Any], config: dict[str, Any]) -> str:
    priced = ", ".join(sorted((config.get("pricing") or {}).keys())) or "none"
    lines = [
        "agent-router report",
        "",
        f"Routing decisions:   {summary['decisions']}  ({_counts(summary['by_source'])})",
        f"Rewritten dispatches: {summary['rewrites']}  ({_counts(summary['rewrites_by_model'])})",
        f"Kept after classifying: {_counts(summary['kept_reasons'])}",
        f"Classifier failures: {_counts(summary['fallback_reasons'])}",
        "",
        f"Classifier calls:    {summary['classifier_calls']}  "
        f"(${summary['classifier_cost_usd']:.4f} total, "
        f"avg {summary['classifier_avg_ms'] / 1000:.1f} s)",
        f"Routed dispatches with outcomes: {summary['routed_with_outcome']}",
        f"  cost as routed:          ${summary['routed_actual_cost_usd']:.4f}",
        f"  cost on baseline model:  ${summary['routed_baseline_cost_usd']:.4f}",
        f"  net savings (estimate):  ${summary['net_savings_usd']:.4f}  (after classifier cost)",
        "",
        f"Savings are an estimate from the config price table ({priced}); "
        "edit `pricing` to match your plan.",
    ]
    if summary["rewrites_without_baseline"]:
        lines.append(
            f"{summary['rewrites_without_baseline']} routed dispatch(es) had no known "
            "baseline model and are left out of the estimate."
        )
    return "\n".join(lines)
