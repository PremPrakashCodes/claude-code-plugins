"""Human-friendly number and time formatting."""

from __future__ import annotations


def humanize_tokens(n: object) -> str:
    """Format a token count compactly: 980 -> '980', 86000 -> '86k', 1_000_000 -> '1.0M'."""
    try:
        value = int(n or 0)
    except (TypeError, ValueError):
        return "0"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        thousands = round(value / 1000)
        if thousands >= 1000:  # 999_600 rounds to 1000k -> roll over to 1.0M
            return f"{value / 1_000_000:.1f}M"
        return f"{thousands}k"
    return str(value)


def format_duration(seconds: float) -> str:
    """Compact duration: '<1m', '17m', '2h 17m', '3d 6h'."""
    total = int(max(0, seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m"
    return "<1m"


def format_cost(amount: object, label: str = "$") -> str:
    try:
        return f"{label}{float(amount):.2f}"
    except (TypeError, ValueError):
        return f"{label}0.00"
