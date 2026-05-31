---
description: Install the status-line HUD and set it as your Claude Code statusLine
allowed-tools: Bash, Read, Edit, Write, AskUserQuestion
---

You are setting up the **status-line** HUD for the user. Your job: pick the best
available Python runtime, install/prepare it, wire it into `settings.json`
(backing up first), seed a starter config, and confirm it renders. Be concrete -
resolve every path, never guess. Keep the user informed but don't over-ask.

The plugin ships an installer that already encodes the runtime strategy
(**uv → python venv + pip → system python**). Prefer it over doing this by hand.

---

## Step 1 - Locate the plugin and confirm the engine runs

```bash
echo "PLUGIN_ROOT=$CLAUDE_PLUGIN_ROOT"
echo "CONFIG_DIR=${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
ls "$CLAUDE_PLUGIN_ROOT/scripts/install.sh" "$CLAUDE_PLUGIN_ROOT/src/statusline.py"
```

Quick sanity check that the code works with whatever Python is around (the
installer will improve on this in Step 2):

```bash
PYBIN="$(command -v python3 || command -v python || true)"
if [ -n "$PYBIN" ]; then
  "$PYBIN" "$CLAUDE_PLUGIN_ROOT/src/statusline.py" --demo
elif ! command -v uv >/dev/null 2>&1; then
  echo "No Python or uv found. Install Python 3.8+ or uv, then re-run /status-line:setup."
  exit 1
fi
```

If a HUD line prints, the engine is good. If **no** Python and **no** `uv` exist,
stop and tell the user to install Python 3.8+ (https://www.python.org/downloads/)
or uv (https://docs.astral.sh/uv/) and re-run `/status-line:setup`.

## Step 2 - Install the runtime (auto-selects uv / venv / system)

Run the installer. It prints exactly one line to **stdout**:
`STATUSLINE_CMD=<command>` - everything else is progress on stderr.

**macOS / Linux:**
```bash
INSTALL_OUTPUT="$(bash "$CLAUDE_PLUGIN_ROOT/scripts/install.sh" "$CLAUDE_PLUGIN_ROOT")" || exit 1
printf '%s\n' "$INSTALL_OUTPUT"
case "$INSTALL_OUTPUT" in
  STATUSLINE_CMD=*) CMD="${INSTALL_OUTPUT#STATUSLINE_CMD=}" ;;
  *) echo "Installer did not print STATUSLINE_CMD=<command>"; exit 1 ;;
esac
printf 'CMD=%s\n' "$CMD"
```

**Windows (PowerShell):**
```powershell
$installOutput = & "$env:CLAUDE_PLUGIN_ROOT\scripts\install.ps1" -PluginSrc "$env:CLAUDE_PLUGIN_ROOT"
Write-Output $installOutput
if (-not $installOutput.StartsWith("STATUSLINE_CMD=")) {
  throw "Installer did not print STATUSLINE_CMD=<command>"
}
$CMD = $installOutput.Substring("STATUSLINE_CMD=".Length)
Write-Output "CMD=$CMD"
```

What it does, in order:
1. **uv present** → creates `<CONFIG_DIR>/plugins/status-line/.venv` and installs
   the package with uv; command is that venv's `status-line` console script.
2. **no uv, python has venv** → `python -m venv` + `pip install` the package;
   same console-script command.
3. **neither venv works** → falls back to running `src/statusline.py` with the
   system Python (no install).

Keep the value after `STATUSLINE_CMD=` as **CMD**, including any quotes printed
by the installer. Verify the renderer with a preview command. Do **not** use
`eval "$CMD --demo"` for this check because the system-Python fallback command
is a shell wrapper and does not forward preview flags:

```bash
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
VENV_PREVIEW="$CONFIG_DIR/plugins/status-line/.venv/bin/status-line"
if [ -x "$VENV_PREVIEW" ]; then
  "$VENV_PREVIEW" --demo
else
  PYBIN="$(command -v python3 || command -v python)"
  "$PYBIN" "$CLAUDE_PLUGIN_ROOT/src/statusline.py" --demo
fi
```

If that prints a HUD line, the runtime is installed. If the installer reported a
fallback to system Python, that's fine - CMD still works; just mention it.

## Step 3 - Back up and write settings.json

Settings file: `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json`.

1. Read it. If `statusLine.command` already exists, show it and ask
   (AskUserQuestion) whether to replace. If yes, first save the old value to
   `<CONFIG_DIR>/plugins/status-line/previous-statusline.txt`.
2. Apply with this helper, which **timestamps a backup**, saves the previous
   command value when it changes, and writes structurally (parse → set → dump;
   never string-concatenate JSON). Use the `CMD` variable captured in Step 2.

```bash
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
VENV_PY="$CONFIG_DIR/plugins/status-line/.venv/bin/python"
if [ -x "$VENV_PY" ]; then
  PYBIN="$VENV_PY"
else
  PYBIN="$(command -v python3 || command -v python)"
fi
"$PYBIN" - "$CMD" <<'PY'
import datetime, json, os, shutil, sys
from pathlib import Path

cfg_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
path = cfg_dir / "settings.json"
status_dir = cfg_dir / "plugins" / "status-line"
cmd = sys.argv[1]

data = {}
if path.exists():
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise SystemExit(f"settings.json is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise SystemExit("settings.json must contain a JSON object")

old_status = data.get("statusLine")
old_cmd = old_status.get("command") if isinstance(old_status, dict) else None

cfg_dir.mkdir(parents=True, exist_ok=True)
status_dir.mkdir(parents=True, exist_ok=True)
if path.exists():
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(path.name + f".bak.{ts}")
    shutil.copy(path, backup)
    print("backup:", backup)
if old_cmd and old_cmd != cmd:
    previous = status_dir / "previous-statusline.txt"
    previous.write_text(old_cmd + "\n", encoding="utf-8")
    print("previous command:", previous)

data["statusLine"] = {"type": "command", "command": cmd}
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print("updated:", path)
PY
```

## Step 4 - Seed a starter config

Ask (AskUserQuestion) which preset to start from:

- **essential** *(recommended)* - model, project, git, context, usage
- **minimal** - model + context %
- **full** - adds cost + session lines, git file stats, context shown as both

If a config file already exists, leave it untouched unless the user explicitly
asks to reset it; setup is often re-run after plugin updates and must not wipe
hand-tuned settings. If no config exists, write the chosen preset as a partial
config to `<CONFIG_DIR>/plugins/status-line/config.json` (create the dir if
needed). The preset bodies live in `$CLAUDE_PLUGIN_ROOT/src/hud/config.py`
(`PRESETS`):

```bash
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
VENV_PY="$CONFIG_DIR/plugins/status-line/.venv/bin/python"
if [ -x "$VENV_PY" ]; then
  PYBIN="$VENV_PY"
else
  PYBIN="$(command -v python3 || command -v python)"
fi
PRESET=essential   # or minimal / full, per the user's answer
"$PYBIN" - "$PRESET" <<'PY'
import json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.environ["CLAUDE_PLUGIN_ROOT"], "src"))
from hud import config as c

name = sys.argv[1]
if name not in c.PRESETS:
    raise SystemExit(f"unknown preset: {name}")

cfg_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
p = cfg_dir / "plugins" / "status-line" / "config.json"
if p.exists():
    print("config exists; left unchanged:", p)
    raise SystemExit(0)

p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(c.PRESETS[name], indent=2) + "\n", encoding="utf-8")
print("wrote", p)
PY
```

## Step 5 - Finish

Show a final preview and the exact next step:

```bash
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CONFIG_PATH="$CONFIG_DIR/plugins/status-line/config.json"
VENV_PREVIEW="$CONFIG_DIR/plugins/status-line/.venv/bin/status-line"
if [ -x "$VENV_PREVIEW" ]; then
  "$VENV_PREVIEW" --demo --config "$CONFIG_PATH"
else
  PYBIN="$(command -v python3 || command -v python)"
  "$PYBIN" "$CLAUDE_PLUGIN_ROOT/src/statusline.py" --demo --config "$CONFIG_PATH"
fi
```

Tell the user to **restart Claude Code** (or start a new session) so the new
`statusLine` loads. Mention:
- Reconfigure any time with **`/status-line:configure`**.
- Re-run **`/status-line:setup`** after updating the plugin to refresh the
  installed copy; existing config is preserved.
- Preview without Claude Code with the final preview command above, or with
  `python3 "$CLAUDE_PLUGIN_ROOT/src/statusline.py" --demo`.
