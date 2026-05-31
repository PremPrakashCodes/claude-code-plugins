"""Configuration: defaults, named themes, presets, and loading/merging.

User config lives at ``$CLAUDE_CONFIG_DIR/plugins/status-line/config.json``
(``~/.claude/...`` by default). It is deep-merged over ``DEFAULTS`` so a partial
file only overrides the keys it sets. A ``"theme"`` selects a base color set;
anything under ``"colors"`` overrides individual roles on top of the theme.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "layout": "compact",          # "compact" (one line) | "expanded" (multi-line)
    "separator": " | ",           # joins segments; rendered in the "separator" color
    "theme": "default",
    "pathLevels": 1,              # directory levels shown for the project segment

    # Segment order. Remove an entry to hide it. Known: model, project, git,
    # context, usage, cost, session.
    "segments": ["model", "project", "git", "context", "usage"],

    "model": {
        "format": "short",        # "short" -> "Opus 4.8" | "full" -> raw display name
        "brackets": True,
    },
    "context": {
        "label": "ctx",
        "value": "tokens",        # "tokens" (86k/1.0M) | "percent" | "both" | "none"
        "bar": True,
        "barStyle": "rounded",    # any name from bars.available_styles()
        "barWidth": 10,
        "warnThreshold": 70,
        "critThreshold": 85,
    },
    "usage": {
        "windows": ["5h", "7d"],
        "labels": {"5h": "5h", "7d": "7d"},      # rename here, e.g. {"7d": "weekly"}
        "value": "percent",       # "percent" | "remaining"
        "bar": False,
        "barStyle": "rounded",
        "barWidth": 8,
        "showReset": True,        # the "(2h 17m)" countdown
        "resetFormat": "relative",  # "relative" | "absolute"
        "warnThreshold": 75,
        "critThreshold": 90,
    },
    "git": {
        "show": True,
        "showDirty": True,
        "showAheadBehind": True,
        "showFileStats": False,
        "wrap": ["git:(", ")"],   # text around the branch
    },
    "cost": {
        "label": "$",
    },
    "session": {
        "showDuration": False,
        "showLines": False,       # +added/-removed
    },

    # Per-role color overrides applied on top of the active theme.
    "colors": {},

    # Optional explicit bar glyphs; when set they override the style's glyphs.
    # Named customBar* to avoid colliding with the "barEmpty" theme *color* role.
    "customBarFilled": None,
    "customBarEmpty": None,
}

# ---------------------------------------------------------------------------
# Themes -- role -> color spec (see colors.py for spec syntax)
# ---------------------------------------------------------------------------

_BASE_ROLES: dict[str, Any] = {
    "model": "cyan",
    "project": "yellow+underline",
    "gitLabel": "magenta",
    "gitBranch": "cyan",
    "label": "dim",
    "separator": "dim",
    "value": "green",
    "valueDim": "dim",
    "barEmpty": "gray",
    "contextOk": "green",
    "contextWarn": "yellow",
    "contextCrit": "red",
    "cost": "green",
    "session": "dim",
    "linesAdded": "green",
    "linesRemoved": "red",
    # per-window usage colors; <window>Warn/<window>Crit escalate.
    "5h": "brightBlue",
    "7d": "brightMagenta",
    "usageWarn": "brightMagenta",
    "usageCrit": "red",
}

THEMES: dict[str, dict[str, Any]] = {
    "default": _BASE_ROLES,
    "nord": {
        **_BASE_ROLES,
        "model": "#88c0d0", "project": "#ebcb8b",
        "gitBranch": "#8fbcbb", "gitLabel": "#b48ead",
        "contextOk": "#a3be8c", "contextWarn": "#ebcb8b", "contextCrit": "#bf616a",
        "value": "#a3be8c", "5h": "#81a1c1", "7d": "#b48ead",
        "usageWarn": "#d08770", "usageCrit": "#bf616a", "barEmpty": "#4c566a",
    },
    "dracula": {
        **_BASE_ROLES,
        "model": "#8be9fd", "project": "#f1fa8c", "gitBranch": "#50fa7b",
        "gitLabel": "#ff79c6", "contextOk": "#50fa7b", "contextWarn": "#f1fa8c",
        "contextCrit": "#ff5555", "value": "#50fa7b", "5h": "#bd93f9",
        "7d": "#ff79c6", "usageWarn": "#ffb86c", "usageCrit": "#ff5555",
        "barEmpty": "#44475a",
    },
    "gruvbox": {
        **_BASE_ROLES,
        "model": "#83a598", "project": "#fabd2f", "gitBranch": "#8ec07c",
        "gitLabel": "#d3869b", "contextOk": "#b8bb26", "contextWarn": "#fabd2f",
        "contextCrit": "#fb4934", "value": "#b8bb26", "5h": "#83a598",
        "7d": "#d3869b", "usageWarn": "#fe8019", "usageCrit": "#fb4934",
        "barEmpty": "#504945",
    },
    "mono": {
        **_BASE_ROLES,
        "model": "white", "project": "white+underline", "gitBranch": "white",
        "gitLabel": "dim", "contextOk": "white", "contextWarn": "white",
        "contextCrit": "bold", "value": "white", "5h": "white", "7d": "white",
        "usageWarn": "white", "usageCrit": "bold", "barEmpty": "dim",
    },
}

# ---------------------------------------------------------------------------
# Presets -- partial configs applied over DEFAULTS by /configure
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict[str, Any]] = {
    "minimal": {
        "segments": ["model", "context"],
        "context": {"value": "percent"},
        "git": {"show": False},
    },
    "essential": {
        "segments": ["model", "project", "git", "context", "usage"],
    },
    "full": {
        "segments": ["model", "project", "git", "context", "usage", "cost", "session"],
        "context": {"value": "both"},
        "session": {"showDuration": True, "showLines": True},
        "git": {"showFileStats": True},
    },
}


# ---------------------------------------------------------------------------
# Loading / merging
# ---------------------------------------------------------------------------

def config_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "plugins" / "status-line" / "config.json"


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
    user: dict[str, Any] = {}
    try:
        if target.exists():
            user = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        user = {}
    if not isinstance(user, dict):
        user = {}
    return _deep_merge(DEFAULTS, user)


def resolve_theme(config: dict[str, Any]) -> dict[str, Any]:
    """Merge the named theme with per-role ``colors`` overrides."""
    theme = THEMES.get(config.get("theme", "default"), THEMES["default"])
    overrides = config.get("colors")
    if not isinstance(overrides, dict):  # a non-dict "colors" must not crash {**...}
        overrides = {}
    return {**theme, **overrides}
