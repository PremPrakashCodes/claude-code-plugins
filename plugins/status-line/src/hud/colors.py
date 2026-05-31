"""ANSI color and text-style handling.

Color specs are strings, ints, or lists. A spec is one or more tokens joined
with ``+``. Each token is either:

* a named color     -- ``"green"``, ``"brightMagenta"``, ``"gray"``
* a 256-color index -- ``"208"`` or the int ``208``
* a hex truecolor   -- ``"#ff8800"``
* a text style      -- ``"bold"``, ``"dim"``, ``"italic"``, ``"underline"``

Example: ``"yellow+underline"`` renders underlined yellow text.
"""

from __future__ import annotations

import re

RESET = "\x1b[0m"

# Foreground SGR codes for named colors.
_NAMED: dict[str, int] = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
    "gray": 90,
    "grey": 90,
    "brightBlack": 90,
    "brightRed": 91,
    "brightGreen": 92,
    "brightYellow": 93,
    "brightBlue": 94,
    "brightMagenta": 95,
    "brightCyan": 96,
    "brightWhite": 97,
}

# Text-style SGR codes.
_STYLES: dict[str, int] = {
    "bold": 1,
    "dim": 2,
    "faint": 2,
    "italic": 3,
    "underline": 4,
    "blink": 5,
    "reverse": 7,
    "strike": 9,
}

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Control chars (incl. ESC \x1b and BEL \x07) -- stripped from rendered text so an
# attacker-controlled payload field (model name, cwd, git branch) can't inject
# its own escape/OSC sequences into the terminal.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _token_code(token: str) -> str | None:
    """Resolve a single spec token to its SGR parameter string."""
    t = token.strip()
    if not t:
        return None
    if t in _STYLES:
        return str(_STYLES[t])
    if t in _NAMED:
        return str(_NAMED[t])
    if t.startswith("#") and len(t) == 7:
        try:
            r, g, b = (int(t[i : i + 2], 16) for i in (1, 3, 5))
            return f"38;2;{r};{g};{b}"
        except ValueError:
            return None
    try:
        n = int(t)
    except ValueError:
        return None
    return f"38;5;{n}" if 0 <= n <= 255 else None


def ansi(spec: object) -> str:
    """Build the opening escape sequence for a color spec (``""`` if empty)."""
    if not spec and spec != 0:
        return ""
    if isinstance(spec, (list, tuple)):
        tokens = [str(t) for t in spec]
    else:
        tokens = str(spec).split("+")
    codes = [c for c in (_token_code(t) for t in tokens) if c]
    return f"\x1b[{';'.join(codes)}m" if codes else ""


def colorize(text: str, spec: object) -> str:
    """Wrap ``text`` in the escape codes for ``spec`` and a reset."""
    if not text:
        return text
    text = _CONTROL_RE.sub("", text)
    opening = ansi(spec)
    return f"{opening}{text}{RESET}" if opening else text


def visible_len(text: str) -> int:
    """Length of ``text`` ignoring ANSI escape sequences."""
    return len(_ANSI_RE.sub("", text))


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)
