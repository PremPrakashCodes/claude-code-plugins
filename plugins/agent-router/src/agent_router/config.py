"""Configuration: conservative defaults plus deep-merged user overrides.

User config lives at ``$CLAUDE_CONFIG_DIR/plugins/agent-router/config.json``
(``~/.claude/...`` by default). It is deep-merged over ``DEFAULTS`` so a partial
file only overrides the keys it sets. A missing or malformed file yields the
defaults: routing must work with zero configuration.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

# Tier names, cheapest first. Rules and the classifier both return one of these.
TIERS = ("low", "mid", "high")

DEFAULTS: dict[str, Any] = {
    # Tier -> Claude Code model alias. Aliases (never full model IDs) so new
    # model versions resolve automatically.
    "tiers": {"low": "haiku", "mid": "sonnet", "high": "opus"},
    # Main-session advisory shown on UserPromptSubmit (rules only, never LLM).
    "advisory": {"enabled": True},
    # Subagent model rewriting on PreToolUse (Task/Agent dispatches).
    "routing": {"subagents": True},
    "rules": {
        # A rules result at or above this confidence routes without the LLM.
        "threshold": 0.7,
        # Prompt-size bands, in characters.
        "shortChars": 200,
        "longChars": 2000,
    },
    # LLM fallback for ambiguous subagent dispatches: a minimal headless
    # `claude -p` call. Timeout is set from the measured ~3 s call latency.
    "classifier": {"enabled": True, "model": "haiku", "timeoutSeconds": 6},
    # Routing log: rotated by rename when it passes maxBytes; keepSegments old
    # segments are kept (log.1.jsonl ... log.N.jsonl).
    "log": {"maxBytes": 5_000_000, "keepSegments": 3},
    # USD per million tokens, used only by `report` to estimate savings.
    # Edit to match your plan or the current price list.
    "pricing": {
        "haiku": {"input": 1.0, "output": 5.0, "cacheRead": 0.1, "cacheWrite": 1.25},
        "sonnet": {"input": 2.0, "output": 10.0, "cacheRead": 0.2, "cacheWrite": 2.5},
        "opus": {"input": 5.0, "output": 25.0, "cacheRead": 0.5, "cacheWrite": 6.25},
    },
}


def config_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "plugins" / "agent-router" / "config.json"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load(path: Path | None = None) -> dict[str, Any]:
    """Return the effective config (defaults deep-merged with the user file)."""
    target = path or config_path()
    user: Any = {}
    try:
        if target.exists():
            user = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        user = {}
    if not isinstance(user, dict):
        user = {}
    return _deep_merge(DEFAULTS, user)


def tier_model(config: dict[str, Any], tier: str) -> str | None:
    """The configured model alias for ``tier``, or None when unset or invalid."""
    tiers = config.get("tiers")
    if not isinstance(tiers, dict):
        return None
    model = tiers.get(tier)
    return model if isinstance(model, str) and model.strip() else None
