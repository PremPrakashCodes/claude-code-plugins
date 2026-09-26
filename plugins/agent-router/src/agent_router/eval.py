"""Evaluation harness: score the classifier against a labeled golden set.

Each line of ``evals/golden.jsonl`` is a subagent dispatch fixture with the tier
a good router should pick. ``router eval`` runs the live classifier on every
fixture - so it costs a few cents and needs the ``claude`` CLI - and reports
accuracy plus a per-tier confusion breakdown. A classifier failure counts as a
miss. The exit code is 1 when accuracy falls below the floor, so the check can
gate a release.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from . import classifier as classifier_mod
from . import tiers as tiers_mod
from .config import TIERS

DEFAULT_FLOOR = 0.8
# Each fixture is an independent `claude -p` call; a few run at once.
MAX_PARALLEL_CALLS = 4
DEFAULT_GOLDEN = Path(__file__).resolve().parents[2] / "evals" / "golden.jsonl"


def classify_fn() -> Callable[..., classifier_mod.ClassifierResult]:
    """The classifier the eval runs; a seam for tests."""
    return classifier_mod.classify


def load_golden(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read fixtures, skipping blank and ``#`` lines; malformed lines become warnings."""
    fixtures: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"cannot read {path}: {exc}"]
    for number, line in enumerate(lines, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            item = json.loads(line)
        except ValueError:
            warnings.append(f"line {number}: not valid JSON, skipped")
            continue
        if not isinstance(item, dict) or item.get("expected_tier") not in TIERS:
            warnings.append(f"line {number}: missing or invalid expected_tier, skipped")
            continue
        item.setdefault("id", f"line-{number}")
        fixtures.append(item)
    return fixtures, warnings


def golden_line(index: int, capture: dict[str, Any]) -> dict[str, Any]:
    """A golden-set fixture from a captured dispatch, labeled with the router's pick.

    The label is a starting point for human review, not ground truth.
    """
    return {
        "id": f"captured-{index + 1}",
        "subagent_type": capture.get("subagent_type") or "general-purpose",
        "description": capture.get("description") or "",
        "prompt": capture.get("prompt") or "",
        "expected_tier": capture.get("routed_tier") or capture.get("classifier_tier") or "mid",
        "label_source": "router - review before trusting",
    }


def run(
    fixtures: list[dict[str, Any]],
    config: dict[str, Any],
    classify: Callable[..., classifier_mod.ClassifierResult] | None = None,
) -> dict[str, Any]:
    """Score the routed tier (classifier answer plus the confidence adjustment).

    Adaptive escalation is left out: it depends on one user's history, not on
    the task. ``classifier_accuracy`` reports the raw classifier answer too.
    """
    classify = classify or classify_fn()
    confusion: dict[str, dict[str, int]] = {tier: {} for tier in TIERS}
    failures = []
    correct = raw_correct = under_routed = 0
    cost = 0.0

    def call(item: dict[str, Any]) -> classifier_mod.ClassifierResult:
        return classify(
            item.get("subagent_type"), item.get("description"), item.get("prompt"), config
        )

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS) as pool:
        results = list(pool.map(call, fixtures))  # map keeps fixture order
    for item, result in zip(fixtures, results):
        if isinstance(result.cost_usd, (int, float)):
            cost += result.cost_usd
        expected = item["expected_tier"]
        if result.ok and result.tier:
            got, _ = tiers_mod.confidence_adjusted(result.tier, result.confidence, config)
            raw_correct += result.tier == expected
            under_routed += TIERS.index(got) < TIERS.index(expected)
        else:
            got = "failed"
            failures.append({"id": item["id"], "reason": result.reason})
        confusion[expected][got] = confusion[expected].get(got, 0) + 1
        if got == expected:
            correct += 1
    total = len(fixtures)
    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "classifier_accuracy": raw_correct / total if total else 0.0,
        "under_routed": under_routed,
        "confusion": confusion,
        "failures": failures,
        "classifier_cost_usd": round(cost, 6),
    }


def format_result(result: dict[str, Any], floor: float) -> str:
    lines = [
        "agent-router eval",
        "",
        f"Accuracy (routed tier): {result['accuracy'] * 100:.1f}%  "
        f"({result['correct']}/{result['total']}; floor {floor * 100:.0f}%)",
        f"Classifier alone:       {result['classifier_accuracy'] * 100:.1f}%",
        f"Routed too low:         {result['under_routed']} (the risky direction)",
        f"Classifier cost:        ${result['classifier_cost_usd']:.4f}",
        "",
        "Expected tier -> routed tier:",
    ]
    for tier in TIERS:
        answers = result["confusion"].get(tier) or {}
        shown = ", ".join(f"{k} {v}" for k, v in sorted(answers.items())) or "no fixtures"
        lines.append(f"  {tier:<5} -> {shown}")
    if result["failures"]:
        lines.append("")
        lines.append("Classifier failures:")
        lines.extend(f"  {f['id']}: {f['reason']}" for f in result["failures"])
    return "\n".join(lines)
