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
{ command -v python3 || command -v python; } >/dev/null \
  && "$(command -v python3 || command -v python)" "$CLAUDE_PLUGIN_ROOT/src/statusline.py" --demo
```

If a HUD line prints, the engine is good. If **no** Python and **no** `uv` exist,
stop and tell the user to install Python 3.8+ (https://www.python.org/downloads/)
or uv (https://docs.astral.sh/uv/) and re-run `/status-line:setup`.

## Step 2 - Install the runtime (auto-selects uv / venv / system)

Run the installer. It prints exactly one line to **stdout**:
`STATUSLINE_CMD=<command>` - everything else is progress on stderr.

**macOS / Linux:**
```bash
bash "$CLAUDE_PLUGIN_ROOT/scripts/install.sh" "$CLAUDE_PLUGIN_ROOT"
```

**Windows (PowerShell):**
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:CLAUDE_PLUGIN_ROOT\scripts\install.ps1" -PluginSrc "$env:CLAUDE_PLUGIN_ROOT"
```

What it does, in order:
1. **uv present** → creates `<CONFIG_DIR>/plugins/status-line/.venv` and installs
   the package with uv; command is that venv's `status-line` console script.
2. **no uv, python has venv** → `python -m venv` + `pip install` the package;
   same console-script command.
3. **neither venv works** → falls back to running `src/statusline.py` with the
   system Python (no install).

Capture the value after `STATUSLINE_CMD=` - call it **CMD** (keep the surrounding
quotes exactly as printed). Verify it renders:

```bash
eval "$CMD --demo"
```

If that prints a HUD line, the runtime is installed. If the installer reported a
fallback to system Python, that's fine - CMD still works; just mention it.

## Step 3 - Back up and write settings.json

Settings file: `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json`.

1. Read it. If `statusLine.command` already exists, show it and ask
   (AskUserQuestion) whether to replace. If yes, first save the old value to
   `<CONFIG_DIR>/plugins/status-line/previous-statusline.txt`.
2. Apply with this helper, which **timestamps a backup** and writes structurally
   (parse → set → dump; never string-concatenate JSON). Set `CMD` first to the
   exact command string from Step 2.

```bash
PYBIN="$(command -v python3 || command -v python)"
CMD='<paste the command string from STATUSLINE_CMD here>'
"$PYBIN" - "$CMD" <<'PY'
import json, os, sys, shutil, datetime
cfg_dir = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
path = os.path.join(cfg_dir, "settings.json")
cmd = sys.argv[1]
data = json.load(open(path)) if os.path.exists(path) else {}
if os.path.exists(path):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy(path, f"{path}.bak.{ts}")
    print("backup:", f"{path}.bak.{ts}")
data["statusLine"] = {"type": "command", "command": cmd}
os.makedirs(cfg_dir, exist_ok=True)
json.dump(data, open(path, "w"), indent=2)
print("updated:", path)
PY
```

## Step 4 - Seed a starter config

Ask (AskUserQuestion) which preset to start from:

- **essential** *(recommended)* - model, project, git, context, usage
- **minimal** - model + context %
- **full** - adds cost + session lines, git file stats, context shown as both

Write the chosen preset merged over defaults to
`<CONFIG_DIR>/plugins/status-line/config.json` (create the dir if needed). The
preset bodies live in `$CLAUDE_PLUGIN_ROOT/src/hud/config.py` (`PRESETS`):

```bash
PYBIN="$(command -v python3 || command -v python)"
PRESET=essential   # or minimal / full, per the user's answer
"$PYBIN" - "$PRESET" <<'PY'
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["CLAUDE_PLUGIN_ROOT"], "src"))
from hud import config as c
preset = c.PRESETS.get(sys.argv[1], {})
cfg = c._deep_merge(c.DEFAULTS, preset)
cfg_dir = os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude"))
p = os.path.join(cfg_dir, "plugins", "status-line", "config.json")
os.makedirs(os.path.dirname(p), exist_ok=True)
json.dump(cfg, open(p, "w"), indent=2)
print("wrote", p)
PY
```

(Alternatively, copy the bundled `$CLAUDE_PLUGIN_ROOT/config.json` as the
starter - it equals the default preset.)

## Step 5 - Finish

Show a final preview and the exact next step:

```bash
eval "$CMD --demo"
```

Tell the user to **restart Claude Code** (or start a new session) so the new
`statusLine` loads. Mention:
- Reconfigure any time with **`/status-line:configure`**.
- Re-run **`/status-line:setup`** after updating the plugin to refresh the
  installed copy.
- Preview without Claude Code: `eval "$CMD --demo"` or
  `python3 "$CLAUDE_PLUGIN_ROOT/src/statusline.py" --demo`.
