#!/usr/bin/env bash
# Install the status-line HUD runtime and print the statusLine command to stdout.
#
# Strategy (best available wins):
#   1. uv          -> create a venv + install the package with uv
#   2. python venv -> create .venv with `python -m venv` + install with pip
#   3. system      -> no install; run src/statusline.py with system python
#
# The venv is created in a STABLE location ($CONFIG/plugins/status-line/.venv)
# and the package is installed by copy (non-editable), so Claude Code marketplace
# version bumps do not invalidate it. Re-run this (via /status-line:setup) after
# updating the plugin to refresh the installed copy.
#
# Usage:  install.sh <PLUGIN_SOURCE_DIR>
#   PLUGIN_SOURCE_DIR defaults to the plugin root inferred from this script.
#
# Output (stdout): exactly one line ->  STATUSLINE_CMD=<command string>
# Diagnostics go to stderr.

set -euo pipefail

log() { printf '%s\n' "$*" >&2; }

# --- Resolve directories ---------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SRC="${1:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PLUGIN_SRC="$(cd "$PLUGIN_SRC" && pwd)"

CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
STABLE_DIR="$CONFIG_DIR/plugins/status-line"
VENV_DIR="$STABLE_DIR/.venv"
mkdir -p "$STABLE_DIR"

if [ ! -f "$PLUGIN_SRC/pyproject.toml" ]; then
  log "error: pyproject.toml not found in $PLUGIN_SRC"
  exit 1
fi

emit() { printf 'STATUSLINE_CMD=%s\n' "$1"; }

# --- 1. uv -----------------------------------------------------------------
if command -v uv >/dev/null 2>&1; then
  log "==> uv detected; installing into $VENV_DIR"
  rm -rf "$VENV_DIR"
  uv venv "$VENV_DIR" >&2
  # Install a copy of the package into the venv (non-editable).
  VIRTUAL_ENV="$VENV_DIR" uv pip install --python "$VENV_DIR/bin/python" "$PLUGIN_SRC" >&2
  log "==> done (uv)"
  emit "\"$VENV_DIR/bin/status-line\""
  exit 0
fi

# --- 2. python -m venv + pip ----------------------------------------------
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$(command -v "$cand")"; break; fi
done

if [ -z "$PY" ]; then
  log "error: no uv, python3, or python found on PATH. Install Python 3.8+ or uv."
  exit 1
fi

if "$PY" -c 'import venv' >/dev/null 2>&1; then
  log "==> python venv detected ($PY); installing into $VENV_DIR"
  rm -rf "$VENV_DIR"
  "$PY" -m venv "$VENV_DIR" >&2
  VENV_PY="$VENV_DIR/bin/python"
  "$VENV_PY" -m pip install --quiet --upgrade pip >&2 || log "warn: pip upgrade skipped"
  if "$VENV_PY" -m pip install --quiet "$PLUGIN_SRC" >&2; then
    log "==> done (venv + pip)"
    emit "\"$VENV_DIR/bin/status-line\""
    exit 0
  fi
  log "warn: pip install failed; falling back to system python"
fi

# --- 3. system python (no install) ----------------------------------------
log "==> using system python (no venv); running src/statusline.py directly"
emit "bash -c 's=\$(ls -d \"\${CLAUDE_CONFIG_DIR:-\$HOME/.claude}\"/plugins/cache/*/status-line/*/src/statusline.py 2>/dev/null | sort | tail -1); [ -z \"\$s\" ] && s=\"$PLUGIN_SRC/src/statusline.py\"; exec \"$PY\" \"\$s\"'"
exit 0
