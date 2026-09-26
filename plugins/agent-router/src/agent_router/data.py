"""Parse the JSON payloads Claude Code pipes to hooks on stdin.

Every field sits behind a tolerant getter so a missing or renamed field degrades
to a safe default instead of raising: a hook must never break the host.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The subagent tool is "Agent" in current Claude Code and "Task" in older builds.
DISPATCH_TOOLS = ("Agent", "Task")

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_FAMILIES = ("haiku", "sonnet", "opus", "fable", "mythos")


def _get(d: Any, *path: str, default: Any = None) -> Any:
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def read_payload() -> dict[str, Any]:
    """Read and JSON-decode the stdin payload, tolerating empty/malformed input."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (RecursionError, ValueError, OSError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


@dataclass
class DispatchEvent:
    """A PreToolUse payload for a subagent (Agent/Task) dispatch."""

    tool_name: str = ""
    tool_use_id: str = ""
    session_id: str = ""
    prompt_id: str = ""
    cwd: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)

    @property
    def is_dispatch(self) -> bool:
        return self.tool_name in DISPATCH_TOOLS

    @property
    def subagent_type(self) -> str:
        return _str(self.tool_input.get("subagent_type"))

    @property
    def description(self) -> str:
        return _str(self.tool_input.get("description"))

    @property
    def prompt(self) -> str:
        return _str(self.tool_input.get("prompt"))

    @property
    def explicit_model(self) -> str | None:
        model = _str(self.tool_input.get("model")).strip()
        return model or None


def parse_dispatch(payload: dict[str, Any]) -> DispatchEvent:
    d = payload if isinstance(payload, dict) else {}
    tool_input = d.get("tool_input")
    return DispatchEvent(
        tool_name=_str(d.get("tool_name")),
        tool_use_id=_str(d.get("tool_use_id")),
        session_id=_str(d.get("session_id")),
        prompt_id=_str(d.get("prompt_id")),
        cwd=_str(d.get("cwd")),
        tool_input=dict(tool_input) if isinstance(tool_input, dict) else {},
    )


# ---------------------------------------------------------------------------
# Agent definitions: a frontmatter `model` is an explicit choice (R6)
# ---------------------------------------------------------------------------


def _config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude"))


def _frontmatter_model(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() == "model":
            model = value.strip().strip("\"'").strip()
            if model and model.lower() != "inherit":
                return model
            return None
    return None


def _agent_files(subagent_type: str, cwd: str) -> list[Path]:
    plugin, sep, name = subagent_type.partition(":")
    if sep:
        if not (_SAFE_NAME.match(plugin) and _SAFE_NAME.match(name)) or ".." in subagent_type:
            return []
        cache = _config_dir() / "plugins" / "cache"
        return sorted(cache.glob(f"*/{plugin}/*/agents/{name}.md"))
    if not _SAFE_NAME.match(subagent_type) or ".." in subagent_type:
        return []
    candidates = []
    if cwd:
        candidates.append(Path(cwd) / ".claude" / "agents" / f"{subagent_type}.md")
    candidates.append(_config_dir() / "agents" / f"{subagent_type}.md")
    return candidates


def agent_definition_model(subagent_type: str | None, cwd: str) -> str | None:
    """The model pinned in the frontmatter of the agent ``subagent_type`` names.

    Looks in the project (``<cwd>/.claude/agents``), the user config dir
    (``agents/``), and installed plugins (``plugin:name`` form). Returns None when
    no definition is found, the model is ``inherit``, or the name is unsafe.
    """
    if not isinstance(subagent_type, str) or not subagent_type:
        return None
    for path in _agent_files(subagent_type, cwd):
        if path.is_file():
            return _frontmatter_model(path)
    return None


# ---------------------------------------------------------------------------
# Session model: the hook payloads do not carry it, the transcript does
# ---------------------------------------------------------------------------

_TAIL_BYTES = 256_000


def session_model_from_transcript(transcript_path: str) -> str | None:
    """The model of the most recent assistant message in the transcript."""
    if not transcript_path:
        return None
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - _TAIL_BYTES))
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if '"assistant"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("type") == "assistant":
            model = _get(row, "message", "model")
            if isinstance(model, str) and model:
                return model
    return None


def model_family(model: str | None) -> str | None:
    """Map a model id or alias to its family alias (``claude-opus-5`` -> ``opus``)."""
    if not isinstance(model, str):
        return None
    lowered = model.lower()
    for family in _FAMILIES:
        if family in lowered:
            return family
    return None
