# Preflight check for the agent-router plugin on Windows.
#
# agent-router needs no install: its hooks run src/router.py with `python3`,
# using only the standard library. This script verifies that `python3` resolves
# to a real Python 3.8+ (not the Microsoft Store stub), that the router CLI runs,
# and that the `claude` CLI is on PATH for the classifier.
#
# Usage:  install.ps1 [-PluginSrc <path>]
# Output (stdout): exactly two lines ->
#   ROUTER_CMD=<command that runs the router CLI>
#   CLASSIFIER=<ok | missing-claude>
# Diagnostics go to the error stream.

param(
  [string]$PluginSrc = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
function Log($m) { [Console]::Error.WriteLine($m) }

$Router = Join-Path (Join-Path $PluginSrc "src") "router.py"
if (-not (Test-Path $Router)) { Log "error: $Router not found"; exit 1 }

# --- 1. python3 (the hooks invoke `python3` by name) -------------------------
if (-not (Get-Command python3 -ErrorAction SilentlyContinue)) {
  Log "error: python3 not found on PATH. The hooks run 'python3'; install Python 3.8+."
  exit 1
}
& python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
  Log "error: 'python3' is not a working Python 3.8+ (it may be the Microsoft Store stub)."
  exit 1
}
Log "==> python3 works"

# --- 2. router CLI -----------------------------------------------------------
& python3 $Router --version *> $null
if ($LASTEXITCODE -ne 0) { Log "error: 'python3 $Router --version' failed"; exit 1 }
Log "==> router CLI runs"

# --- 3. claude CLI -----------------------------------------------------------
$Classifier = "ok"
if (Get-Command claude -ErrorAction SilentlyContinue) {
  Log "==> claude CLI found"
} else {
  Log "warn: 'claude' not on PATH; the classifier cannot run, so dispatches keep their model"
  $Classifier = "missing-claude"
}

Write-Output "ROUTER_CMD=python3 `"$Router`""
Write-Output "CLASSIFIER=$Classifier"
