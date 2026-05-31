"""Progress-bar rendering with selectable styles.

Add a new look by registering a (filled, empty) glyph pair in ``BAR_PRESETS``,
or use the special ``"smooth"`` / ``"braille"`` renderers. Styles in
``_BRACKETED`` are wrapped in ``[ ]`` for a classic ASCII gauge look.
"""

from __future__ import annotations

from .colors import colorize

# name -> (filled glyph, empty glyph)
BAR_PRESETS: dict[str, tuple[str, str]] = {
    "rounded": ("▰", "▱"),   # default, matches the reference HUD
    "blocks": ("█", "░"),
    "shade": ("█", "▒"),
    "bars": ("▮", "▯"),
    "dots": ("●", "○"),
    "line": ("━", "─"),
    "equals": ("=", "-"),
    "hash": ("#", "."),
    "ascii": ("#", "-"),
    "arrows": ("►", "─"),
}

# Styles rendered inside [ ] brackets.
_BRACKETED = {"equals", "hash", "ascii"}

# Fractional eighth-blocks for the "smooth" style (index 1..7 = partial cell).
_SMOOTH_PARTIALS = " ▏▎▍▌▋▊▉"
_SMOOTH_EMPTY = "·"


def available_styles() -> list[str]:
    return [*BAR_PRESETS.keys(), "smooth", "braille"]


def _clamp(percent: float) -> float:
    return max(0.0, min(100.0, percent))


def render_bar(
    percent: float,
    width: int = 10,
    style: str = "rounded",
    fill_color: object = None,
    empty_color: object = None,
    filled_char: str | None = None,
    empty_char: str | None = None,
) -> str:
    """Render a ``width``-cell bar filled to ``percent`` (0-100)."""
    percent = _clamp(percent)
    width = max(1, int(width))

    if style == "smooth":
        return _smooth_bar(percent, width, fill_color, empty_color)
    if style == "braille":
        return _two_glyph_bar(percent, width, "⣿", "⣀", fill_color, empty_color)

    filled_glyph, empty_glyph = BAR_PRESETS.get(style, BAR_PRESETS["rounded"])
    if filled_char:
        filled_glyph = filled_char
    if empty_char:
        empty_glyph = empty_char

    bar = _two_glyph_bar(percent, width, filled_glyph, empty_glyph, fill_color, empty_color)
    if style in _BRACKETED:
        bracket = colorize("[", empty_color)
        return f"{bracket}{bar}{colorize(']', empty_color)}"
    return bar


def _two_glyph_bar(
    percent: float, width: int, filled_glyph: str, empty_glyph: str,
    fill_color: object, empty_color: object,
) -> str:
    filled = round(width * percent / 100)
    filled = max(0, min(width, filled))
    return (
        colorize(filled_glyph * filled, fill_color)
        + colorize(empty_glyph * (width - filled), empty_color)
    )


def _smooth_bar(percent: float, width: int, fill_color: object, empty_color: object) -> str:
    total_eighths = round(width * 8 * percent / 100)
    full = total_eighths // 8
    remainder = total_eighths % 8
    cells = "█" * full
    used = full
    if remainder and full < width:
        cells += _SMOOTH_PARTIALS[remainder]
        used += 1
    body = colorize(cells, fill_color)
    body += colorize(_SMOOTH_EMPTY * (width - used), empty_color)
    return body
