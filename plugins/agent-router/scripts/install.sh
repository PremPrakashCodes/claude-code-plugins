#!/usr/bin/env bash
# Preflight check for the agent-router plugin.
#
# agent-router needs no install: its hooks (hooks/hooks.json) run
# src/router.py directly with `python3`, using only the standard library. This
# script verifies the pieces those hooks depend on:
#   1. a Python 3.8+ interpreter reachable as `python3`
#   2. the router CLI runs from the plugin directory
#   3. the `claude` CLI is on PATH (the classifier runs `claude -p`)
#
# Usage:  install.sh [PLUGIN_SOURCE_DIR]
#   PLUGIN_SOURCE_DIR defaults to the plugin root inferred from this script.
#
# Output (stdout): exactly two lines ->
#   ROUTER_CMD=<command that runs the router CLI>
#   CLASSIFIER=<ok | missing-claude>
# Diagnostics go to stderr. Exits non-zero when the hooks cannot run at all.

set -euo pipefail

log() { printf '%s\n' "$*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SRC="${1:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PLUGIN_SRC="$(cd "$PLUGIN_SRC" && pwd)"
ROUTER="$PLUGIN_SRC/src/router.py"

if [ ! -f "$ROUTER" ]; then
  log "error: $ROUTER not found"
  exit 1
fi

# --- 1. python3 ------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  log "error: python3 not found on PATH. The hooks run 'python3'; install Python 3.8+."
  exit 1
fi
PY="$(command -v python3)"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
  log "error: $PY is older than Python 3.8"
  exit 1
fi
log "==> python3: $PY ($("$PY" -c 'import platform; print(platform.python_version())'))"

# --- 2. router CLI ---------------------------------------------------------
if ! "$PY" "$ROUTER" --version >/dev/null 2>&1; then
  log "error: '$PY $ROUTER --version' failed"
  exit 1
fi
log "==> router CLI runs"

# --- 3. claude CLI ---------------------------------------------------------
if command -v claude >/dev/null 2>&1; then
  log "==> claude CLI: $(command -v claude)"
  CLASSIFIER=ok
else
  log "warn: 'claude' not on PATH; the classifier cannot run, so dispatches keep their model"
  CLASSIFIER=missing-claude
fi

printf 'ROUTER_CMD="%s" "%s"\n' "$PY" "$ROUTER"
printf 'CLASSIFIER=%s\n' "$CLASSIFIER"
