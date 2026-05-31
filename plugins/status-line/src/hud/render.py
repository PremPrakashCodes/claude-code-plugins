"""Compose HUD segments into the final status line(s)."""

from __future__ import annotations

import os
import time
from typing import Any, Callable

from . import bars, gitinfo
from .colors import colorize, visible_len
from .data import HudData
from .formatting import format_cost, format_duration, humanize_tokens


def _threshold_color(percent: float, cfg: dict[str, Any], ok: Any, warn: Any, crit: Any) -> Any:
    """Pick a color by where ``percent`` falls against the cfg warn/crit thresholds.

    Thresholds always exist here -- config is deep-merged over DEFAULTS before
    rendering -- so this trusts ``cfg`` rather than re-declaring default values.
    """
    if percent >= cfg["critThreshold"]:
        return crit
    if percent >= cfg["warnThreshold"]:
        return warn
    return ok


def _model_name(data: HudData, cfg: dict[str, Any]) -> str:
    name = data.model_display or data.model_id or "?"
    if cfg.get("format", "short") == "short":
        name = name.split("(")[0].strip()
        prefix = "Claude "
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def _project_path(data: HudData, levels: int) -> str:
    path = data.cwd or ""
    segments = [s for s in path.replace("\\", "/").split("/") if s]
    if not segments:
        return "/"
    return "/".join(segments[-max(1, levels):])


# --- individual segment renderers -----------------------------------------

def _seg_model(data, config, theme) -> str | None:
    cfg = config["model"]
    name = _model_name(data, cfg)
    text = f"[{name}]" if cfg.get("brackets", True) else name
    return colorize(text, theme["model"])


def _seg_project(data, config, theme) -> str | None:
    if not data.cwd:
        return None
    return colorize(_project_path(data, config.get("pathLevels", 1)), theme["project"])


def _seg_git(data, config, theme) -> str | None:
    cfg = config["git"]
    if not cfg.get("show", True):
        return None
    show_ahead_behind = cfg.get("showAheadBehind", True)
    show_file_stats = cfg.get("showFileStats", False)
    status = gitinfo.collect(
        data.cwd,
        ahead_behind=show_ahead_behind,
        file_stats=show_file_stats,
    )
    if not status.is_repo:
        return None

    branch = status.branch
    if cfg.get("showDirty", True) and status.dirty:
        branch += "*"
    if show_ahead_behind:
        if status.ahead:
            branch += f" ↑{status.ahead}"
        if status.behind:
            branch += f" ↓{status.behind}"
    if show_file_stats:
        stats = []
        if status.modified:
            stats.append(f"!{status.modified}")
        if status.added:
            stats.append(f"+{status.added}")
        if status.deleted:
            stats.append(f"✘{status.deleted}")
        if status.untracked:
            stats.append(f"?{status.untracked}")
        if stats:
            branch += " " + " ".join(stats)

    wrap = cfg.get("wrap") or ["git:(", ")"]  # tolerate a mis-sized/non-list value
    open_wrap, close_wrap = (list(wrap) + ["", ""])[:2]
    return (
        colorize(open_wrap, theme["gitLabel"])
        + colorize(branch, theme["gitBranch"])
        + colorize(close_wrap, theme["gitLabel"])
    )


def _seg_context(data, config, theme) -> str | None:
    cfg = config["context"]
    percent = data.context_percent
    color = _threshold_color(
        percent, cfg, theme["contextOk"], theme["contextWarn"], theme["contextCrit"]
    )
    parts: list[str] = []

    label = cfg.get("label", "ctx")
    if label:
        parts.append(colorize(label, theme["label"]))

    if cfg.get("bar", True):
        parts.append(bars.render_bar(
            percent,
            width=cfg.get("barWidth", 10),
            style=cfg.get("barStyle", "rounded"),
            fill_color=color,
            empty_color=theme["barEmpty"],
            filled_char=config.get("customBarFilled"),
            empty_char=config.get("customBarEmpty"),
        ))

    value_mode = cfg.get("value", "tokens")
    value = _context_value(data, percent, value_mode, color, theme)
    if value:
        parts.append(value)

    return " ".join(p for p in parts if p) or None


def _context_value(data, percent, mode, color, theme) -> str:
    if mode == "none":
        return ""
    pct = colorize(f"{percent:.0f}%", color)
    if mode == "percent":
        return pct
    tokens = colorize(humanize_tokens(data.total_tokens), color) + colorize(
        f"/{humanize_tokens(data.context_window)}", theme["valueDim"]
    )
    return f"{tokens} {pct}" if mode == "both" else tokens


def _seg_usage(data, config, theme) -> list[str]:
    cfg = config["usage"]
    labels = cfg.get("labels", {})
    now = time.time()
    cells: list[str] = []

    for window in cfg.get("windows", ["5h", "7d"]):
        info = data.windows.get(window)
        if not info or info.used_percent is None:
            continue
        percent = info.used_percent
        shown = (100 - percent) if cfg.get("value") == "remaining" else percent
        color = _threshold_color(
            percent, cfg, theme.get(window, theme["5h"]), theme["usageWarn"], theme["usageCrit"]
        )
        label = labels.get(window, window)

        piece = colorize(f"{label}:", theme["label"]) + " "
        if cfg.get("bar", False):
            piece += bars.render_bar(
                percent, width=cfg.get("barWidth", 8),
                style=cfg.get("barStyle", "rounded"),
                fill_color=color, empty_color=theme["barEmpty"],
                filled_char=config.get("customBarFilled"),
                empty_char=config.get("customBarEmpty"),
            ) + " "
        piece += colorize(f"{shown:.0f}%", color)

        if cfg.get("showReset", True) and info.resets_at:
            reset = _format_reset(info.resets_at, now, cfg.get("resetFormat", "relative"))
            if reset:
                piece += " " + colorize(f"({reset})", theme["label"])
        cells.append(piece)
    return cells


def _format_reset(resets_at: float, now: float, mode: str) -> str:
    if resets_at <= now:  # already elapsed -> show nothing, in either mode
        return ""
    if mode == "absolute":
        return time.strftime("%H:%M", time.localtime(resets_at))
    return format_duration(resets_at - now)


def _seg_cost(data, config, theme) -> str | None:
    if data.cost_usd is None:
        return None
    return colorize(format_cost(data.cost_usd, config["cost"].get("label", "$")), theme["cost"])


def _seg_session(data, config, theme) -> list[str]:
    cfg = config["session"]
    cells: list[str] = []
    if cfg.get("showDuration") and data.duration_ms:
        cells.append(colorize(format_duration(data.duration_ms / 1000), theme["session"]))
    if cfg.get("showLines") and (data.lines_added or data.lines_removed):
        added = colorize(f"+{data.lines_added or 0}", theme["linesAdded"])
        removed = colorize(f"-{data.lines_removed or 0}", theme["linesRemoved"])
        cells.append(f"{added} {removed}")
    return cells


# Renderers may return a str, a list[str], or None.
_RENDERERS: dict[str, Callable] = {
    "model": _seg_model,
    "project": _seg_project,
    "git": _seg_git,
    "context": _seg_context,
    "usage": _seg_usage,
    "cost": _seg_cost,
    "session": _seg_session,
}


def _collect_cells(data: HudData, config: dict[str, Any], theme: dict[str, Any]) -> list[str]:
    cells: list[str] = []
    for name in config.get("segments", []):
        renderer = _RENDERERS.get(name)
        if not renderer:
            continue
        try:
            result = renderer(data, config, theme)
        except Exception:  # a single bad segment must never break the line
            continue
        if not result:
            continue
        if isinstance(result, list):
            cells.extend(c for c in result if c)
        else:
            cells.append(result)
    return cells


def render(data: HudData, config: dict[str, Any], theme: dict[str, Any]) -> str:
    cells = _collect_cells(data, config, theme)
    if not cells:
        return ""
    separator = colorize(config.get("separator", " | "), theme["separator"])

    if config.get("layout") == "expanded":
        return "\n".join(cells)

    return _truncate(cells, separator)


def _columns() -> int:
    """Best-effort terminal width: COLUMNS env, then /dev/tty, else 0 (unknown).

    Status-line stdout is a pipe (Claude Code captures it), so we query the
    controlling terminal directly via /dev/tty rather than stdout. The fd is
    opened non-blocking so this never hangs when there is no controlling
    terminal (e.g. headless or under a test harness).
    """
    try:
        env = int(os.environ.get("COLUMNS", "0"))
        if env > 0:
            return env
    except ValueError:
        pass
    fd = None
    try:
        fd = os.open("/dev/tty", os.O_RDONLY | os.O_NONBLOCK)
        return os.get_terminal_size(fd).columns
    except (OSError, ValueError):
        return 0
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _truncate(cells: list[str], separator: str) -> str:
    """Drop trailing cells if the joined line overflows the terminal width.

    Operates on the cell list, not the joined string, so a cell whose text
    happens to contain the (colored) separator's escape bytes can't corrupt the
    cell boundaries.
    """
    columns = _columns()
    cells = list(cells)
    if columns <= 0 or visible_len(separator.join(cells)) <= columns:
        return separator.join(cells)
    while len(cells) > 1 and visible_len(separator.join(cells)) > columns:
        cells.pop()
    return separator.join(cells)
