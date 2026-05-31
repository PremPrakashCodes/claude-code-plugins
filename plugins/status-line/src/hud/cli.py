"""Command-line entry point for the status-line HUD.

Claude Code runs this on every status-line refresh, piping a JSON payload on
stdin. We parse it, render one line (or several in expanded layout), and print.

This module is importable (``hud.cli:main``) so it can be exposed as the
``status-line`` console script when the package is installed, and is also driven
directly by ``src/statusline.py`` for no-install execution.

Flags:
    (none)              read JSON from stdin and render (normal mode)
    --demo              render sample data (preview without Claude Code)
    --config PATH       use a specific config file (with --demo or stdin)
    --styles            list available progress-bar styles
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from . import bars, config as config_mod, data as data_mod, render as render_mod


def _demo_payload() -> dict:
    now = time.time()
    return {
        "model": {"id": "claude-opus-4-8", "display_name": "Opus 4.8 (1M context)"},
        "workspace": {"current_dir": "/Users/you/Projects/claude"},
        "context_window": {
            "context_window_size": 1_000_000,
            "current_usage": {
                "input_tokens": 20_000,
                "cache_creation_input_tokens": 6_000,
                "cache_read_input_tokens": 60_000,
            },
        },
        "cost": {"total_cost_usd": 0.42, "total_duration_ms": 1_380_000,
                 "total_lines_added": 214, "total_lines_removed": 37},
        "rate_limits": {
            "five_hour": {"used_percentage": 6, "resets_at": now + 8220},      # ~2h 17m
            "seven_day": {"used_percentage": 44, "resets_at": now + 280800},   # ~3d 6h
        },
    }


def _render(payload: dict, config_path: Path | None = None) -> str:
    config = config_mod.load(config_path)
    theme = config_mod.resolve_theme(config)
    parsed = data_mod.parse(payload)
    return render_mod.render(parsed, config, theme)


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)

    if "--styles" in args:
        print("Available bar styles:", ", ".join(bars.available_styles()))
        return

    config_path = None
    if "--config" in args:
        idx = args.index("--config")
        if idx + 1 < len(args):
            config_path = Path(args[idx + 1])

    if "--demo" in args:
        try:
            print(_render(_demo_payload(), config_path))
        except Exception:
            # Even the preview must never dump a traceback.
            print("")
        return

    try:
        payload = data_mod.read_payload()
        print(_render(payload, config_path))
    except Exception:
        # Never let the status line crash the prompt; fail silent.
        # read_payload() is inside the guard too: json.loads can raise
        # RecursionError (deeply nested input), which is not a ValueError.
        print("")


if __name__ == "__main__":
    main()
