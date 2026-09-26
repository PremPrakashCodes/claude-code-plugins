"""Append-only JSONL routing log with rotate-by-rename retention.

Records live at ``${CLAUDE_PLUGIN_DATA}/log.jsonl`` (falling back to
``$CLAUDE_CONFIG_DIR/plugins/data/agent-router/log.jsonl``). Several hook
processes can write at once - Claude often dispatches subagents in parallel - so
writers only ever append whole lines, and retention never rewrites a file: when
the log passes ``log.maxBytes`` it is renamed to ``log.1.jsonl`` (older segments
shift up; segments past ``log.keepSegments`` are deleted). A best-effort file
lock serializes the check-rotate-append step where the platform supports it.

Logging must never break routing: every failure is swallowed and reported only
through the return value.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any, Iterator

try:  # POSIX only; on other platforms rotation runs unlocked.
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows only
    fcntl = None  # type: ignore[assignment]

DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_KEEP_SEGMENTS = 3


def data_dir() -> Path:
    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if plugin_data:
        return Path(plugin_data)
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "plugins" / "data" / "agent-router"


def log_path() -> Path:
    return data_dir() / "log.jsonl"


def _segment(path: Path, index: int) -> Path:
    return path.with_name(f"{path.stem}.{index}{path.suffix}")


def _int_setting(config: dict[str, Any], key: str, default: int, minimum: int) -> int:
    value = (config.get("log") or {}).get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return default
    return value


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    if fcntl is None:
        yield
        return
    with open(path.with_name(path.name + ".lock"), "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _rotate(path: Path, keep: int) -> None:
    if keep <= 0:
        path.unlink()
        return
    oldest = _segment(path, keep)
    if oldest.exists():
        oldest.unlink()
    for index in range(keep - 1, 0, -1):
        src = _segment(path, index)
        if src.exists():
            os.replace(src, _segment(path, index + 1))
    os.replace(path, _segment(path, 1))


def append(record: dict[str, Any], config: dict[str, Any], path: Path | None = None) -> bool:
    """Append one record. Returns False (never raises) if it could not be written."""
    target = path or log_path()
    try:
        line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
    except (TypeError, ValueError):
        return False
    max_bytes = _int_setting(config, "maxBytes", DEFAULT_MAX_BYTES, 1)
    keep = _int_setting(config, "keepSegments", DEFAULT_KEEP_SEGMENTS, 0)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with _locked(target):
            try:
                if target.stat().st_size >= max_bytes:
                    _rotate(target, keep)
            except FileNotFoundError:
                pass
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(line)
        return True
    except OSError:
        return False


def _read_file(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    yield record
    except OSError:
        return


def read_records(path: Path | None = None) -> Iterator[dict[str, Any]]:
    """Yield every record, oldest segment first, skipping unreadable lines."""
    target = path or log_path()
    segments = []
    index = 1
    while _segment(target, index).exists():
        segments.append(_segment(target, index))
        index += 1
    for segment in reversed(segments):
        yield from _read_file(segment)
    yield from _read_file(target)
