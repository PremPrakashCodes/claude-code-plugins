# Install the status-line HUD runtime on Windows and print the statusLine command.
#
# Strategy: uv -> python venv + pip -> system python (no install).
# The venv is created in a stable location so plugin updates don't wipe it.
#
# Usage:  install.ps1 [-PluginSrc <path>]
# Output (stdout): exactly one line ->  STATUSLINE_CMD=<command string>
# Diagnostics go to the error stream.

param(
  [string]$PluginSrc = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
function Log($m) { [Console]::Error.WriteLine($m) }

$ConfigDir = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $HOME ".claude" }
$StableDir = Join-Path (Join-Path $ConfigDir "plugins") "status-line"
$VenvDir   = Join-Path $StableDir ".venv"
New-Item -ItemType Directory -Force -Path $StableDir | Out-Null

if (-not (Test-Path (Join-Path $PluginSrc "pyproject.toml"))) {
  Log "error: pyproject.toml not found in $PluginSrc"; exit 1
}

function Emit($cmd) { Write-Output "STATUSLINE_CMD=$cmd" }

# --- 1. uv -----------------------------------------------------------------
if (Get-Command uv -ErrorAction SilentlyContinue) {
  Log "==> uv detected; installing into $VenvDir"
  if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
  uv venv $VenvDir 2>&1 | ForEach-Object { Log $_ }
  $py = Join-Path (Join-Path $VenvDir "Scripts") "python.exe"
  uv pip install --python $py $PluginSrc 2>&1 | ForEach-Object { Log $_ }
  $exe = Join-Path (Join-Path $VenvDir "Scripts") "status-line.exe"
  Log "==> done (uv)"; Emit "`"$exe`""; exit 0
}

# --- 2. python venv + pip --------------------------------------------------
$PY = $null
foreach ($c in @("python", "python3", "py")) {
  if (Get-Command $c -ErrorAction SilentlyContinue) { $PY = $c; break }
}
if (-not $PY) { Log "error: no uv or python found. Install Python 3.8+ or uv."; exit 1 }

Log "==> python venv ($PY); installing into $VenvDir"
if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
& $PY -m venv $VenvDir 2>&1 | ForEach-Object { Log $_ }
$venvPy = Join-Path (Join-Path $VenvDir "Scripts") "python.exe"
try {
  & $venvPy -m pip install --quiet --upgrade pip 2>&1 | ForEach-Object { Log $_ }
  & $venvPy -m pip install --quiet $PluginSrc 2>&1 | ForEach-Object { Log $_ }
  $exe = Join-Path (Join-Path $VenvDir "Scripts") "status-line.exe"
  Log "==> done (venv + pip)"; Emit "`"$exe`""; exit 0
} catch {
  Log "warn: pip install failed; falling back to system python"
}

# --- 3. system python (no install) ----------------------------------------
$script = Join-Path (Join-Path $PluginSrc "src") "statusline.py"
Log "==> using system python (no venv)"
Emit "`"$PY`" `"$script`""
exit 0
