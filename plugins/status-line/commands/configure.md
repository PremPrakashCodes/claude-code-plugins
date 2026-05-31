---
description: Configure the status-line HUD (segments, bar style, themes, labels, layout)
allowed-tools: Bash, Read, Edit, Write, AskUserQuestion
---

You are configuring the **status-line** HUD. The user's config lives at
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/status-line/config.json` and is
**deep-merged over defaults** - so write only the keys the user changes and
leave every other (possibly hand-edited) key untouched. Confirm the result with
a live preview before finishing.

Guide the conversation: ask what they want to change, make the change, show the
preview, repeat until they're happy. Don't dump every option at once.

## Step 0 - Resolve the preview command and config path

```bash
echo "PLUGIN_ROOT=$CLAUDE_PLUGIN_ROOT"
CONFIG_PATH="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/status-line/config.json"
echo "CONFIG_PATH=$CONFIG_PATH"
```

Choose the **preview command (PREVIEW)** - prefer the installed runtime, fall
back to running the script with system Python:

```bash
VENV_BIN="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/status-line/.venv/bin/status-line"
if [ -x "$VENV_BIN" ]; then
  PREVIEW="$VENV_BIN"
else
  PREVIEW="$(command -v python3 || command -v python) $CLAUDE_PLUGIN_ROOT/src/statusline.py"
fi
echo "PREVIEW=$PREVIEW"
```

Render the current config any time with:

```bash
$PREVIEW --demo --config "$CONFIG_PATH"
```

(If the file doesn't exist yet, the preview uses built-in defaults - that's fine;
your first write creates it.)

## How config works

- Defaults, themes, and presets live in `$CLAUDE_PLUGIN_ROOT/src/hud/config.py`
  (`DEFAULTS`, `THEMES`, `PRESETS`). Read it for the authoritative option list.
- A partial config file overrides only its own keys. Never rewrite the whole
  file from scratch unless the user asks to reset - load the existing JSON, merge
  the user's choices in, write it back (preserve unknown keys).
- After every change, run the preview and show the user the output.

## Options you can offer (via AskUserQuestion)

Pick the questions that match what the user wants.

1. **Preset** - `minimal`, `essential`, or `full`. Apply by merging
   `PRESETS[name]` over the current config.

2. **Segments & order** - which of `model, project, git, context, usage, cost,
   session` to show and in what order (the `"segments"` array; order matters,
   omit a name to hide it).

3. **Progress-bar style** - `"context.barStyle"` (and optionally
   `"usage.barStyle"`). Valid values:
   `rounded, blocks, shade, bars, dots, line, equals, hash, ascii, arrows, smooth, braille`.
   List them live: `$PREVIEW --styles`. To show them side by side, preview a tiny
   temp config per style. Bar width is `"context.barWidth"` / `"usage.barWidth"`.

4. **Context value** - `"context.value"`: `tokens` (86k/1.0M), `percent`,
   `both`, or `none`. Label via `"context.label"` (default `ctx`).

5. **Usage windows & labels** - `"usage.windows"` (subset of `["5h","7d"]`) and
   `"usage.labels"` to rename them, e.g. `{"7d": "weekly"}`. Other usage keys:
   `value` (`percent`/`remaining`), `bar` (true/false), `showReset` (the
   `(2h 17m)` countdown), `resetFormat` (`relative`/`absolute`).

6. **Theme** - `"theme"`: `default, nord, dracula, gruvbox, mono`. For finer
   control, set individual roles under `"colors"`, e.g.
   `{"colors": {"project": "#ff8800", "7d": "magenta"}}`. Color specs accept
   named colors, 256 indices, `#rrggbb`, and `+`-joined styles like
   `"yellow+underline"`.

7. **Git detail** - `"git"`: `show`, `showDirty`, `showAheadBehind`,
   `showFileStats`.

8. **Layout** - `"layout"`: `compact` (one line) or `expanded` (one segment per
   line). Separator between compact segments is `"separator"` (default `" | "`).

9. **Thresholds** - context warn/crit at `"context.warnThreshold"` /
   `"context.critThreshold"`; usage at `"usage.warnThreshold"` /
   `"usage.critThreshold"`.

## Writing the file

Merge changes into the existing JSON and write with 2-space indent. Edit the
marked block to apply the user's chosen keys:

```bash
PYBIN="$(command -v python3 || command -v python)"
"$PYBIN" - <<'PY'
import json, os
p = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude")),
                 "plugins", "status-line", "config.json")
os.makedirs(os.path.dirname(p), exist_ok=True)
cfg = {}
if os.path.exists(p):
    try:
        cfg = json.load(open(p))
    except Exception:
        cfg = {}

# --- merge the user's chosen changes into cfg here ---
cfg.setdefault("context", {})["barStyle"] = "blocks"
cfg.setdefault("usage", {}).setdefault("labels", {})["7d"] = "weekly"
# ----------------------------------------------------

json.dump(cfg, open(p, "w"), indent=2)
print("saved", p)
PY
```

To **apply a preset**, merge it instead of setting individual keys:

```bash
PYBIN="$(command -v python3 || command -v python)"
PRESET=full   # minimal | essential | full
"$PYBIN" - "$PRESET" <<'PY'
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["CLAUDE_PLUGIN_ROOT"], "src"))
from hud import config as c
p = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude")),
                 "plugins", "status-line", "config.json")
cfg = {}
if os.path.exists(p):
    try: cfg = json.load(open(p))
    except Exception: cfg = {}
cfg = c._deep_merge(cfg, c.PRESETS.get(sys.argv[1], {}))
os.makedirs(os.path.dirname(p), exist_ok=True)
json.dump(cfg, open(p, "w"), indent=2)
print("applied preset", sys.argv[1])
PY
```

After saving, render the preview one final time and confirm the user is happy.
Remind them changes apply on the next status-line refresh (usually immediate; a
new session guarantees it).
