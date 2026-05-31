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
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CONFIG_PATH="$CONFIG_DIR/plugins/status-line/config.json"
echo "CONFIG_PATH=$CONFIG_PATH"
```

Choose the **preview command (PREVIEW)** - prefer the installed runtime, fall
back to running the script with system Python. Keep it as a Bash array so paths
with spaces still work:

```bash
VENV_BIN="$CONFIG_DIR/plugins/status-line/.venv/bin/status-line"
if [ -x "$VENV_BIN" ]; then
  PREVIEW=("$VENV_BIN")
else
  PYBIN="$(command -v python3 || command -v python || true)"
  if [ -z "$PYBIN" ]; then
    echo "No Python found. Run /status-line:setup after installing Python 3.8+ or uv."
    exit 1
  fi
  PREVIEW=("$PYBIN" "$CLAUDE_PLUGIN_ROOT/src/statusline.py")
fi
printf 'PREVIEW='
printf '%q ' "${PREVIEW[@]}"
printf '\n'
```

Render the current config any time with:

```bash
"${PREVIEW[@]}" --demo --config "$CONFIG_PATH"
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

1. **Preset** - `minimal`, `essential`, or `full`. Apply with the preset helper
   below so previous preset-only keys are cleared before the new preset is
   merged.

2. **Segments & order** - which of `model, project, git, context, usage, cost,
   session` to show and in what order (the `"segments"` array; order matters,
   omit a name to hide it).

3. **Progress-bar style** - `"context.barStyle"` (and optionally
   `"usage.barStyle"`). Valid values:
   `rounded, blocks, shade, bars, dots, line, equals, hash, ascii, arrows, smooth, braille`.
   List them live: `"${PREVIEW[@]}" --styles`. To show them side by side,
   preview a tiny temp config per style. Bar width is `"context.barWidth"` /
   `"usage.barWidth"`.

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
VENV_PY="$CONFIG_DIR/plugins/status-line/.venv/bin/python"
if [ -x "$VENV_PY" ]; then
  PYBIN="$VENV_PY"
else
  PYBIN="$(command -v python3 || command -v python)"
fi
"$PYBIN" - <<'PY'
import json, os
from pathlib import Path

p = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")).expanduser()
p = p / "plugins" / "status-line" / "config.json"
cfg = {}
if p.exists():
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"config.json is not valid JSON: {exc}")
    if not isinstance(cfg, dict):
        raise SystemExit("config.json must contain a JSON object")

# --- merge the user's chosen changes into cfg here ---
cfg.setdefault("context", {})["barStyle"] = "blocks"
cfg.setdefault("usage", {}).setdefault("labels", {})["7d"] = "weekly"
# ----------------------------------------------------

p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
print("saved", p)
PY
```

To **apply a preset**, replace the keys controlled by presets, then merge the
selected preset. This lets switching from `minimal` back to `essential` restore
default git/session behavior while preserving unrelated custom keys like theme,
colors, labels, and bar styles:

```bash
VENV_PY="$CONFIG_DIR/plugins/status-line/.venv/bin/python"
if [ -x "$VENV_PY" ]; then
  PYBIN="$VENV_PY"
else
  PYBIN="$(command -v python3 || command -v python)"
fi
PRESET=full   # minimal | essential | full
"$PYBIN" - "$PRESET" <<'PY'
import json, os, sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.environ["CLAUDE_PLUGIN_ROOT"], "src"))
from hud import config as c

p = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")).expanduser()
p = p / "plugins" / "status-line" / "config.json"
name = sys.argv[1]
if name not in c.PRESETS:
    raise SystemExit(f"unknown preset: {name}")

cfg = {}
if p.exists():
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"config.json is not valid JSON: {exc}")
    if not isinstance(cfg, dict):
        raise SystemExit("config.json must contain a JSON object")

def leaf_paths(value, prefix=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaf_paths(child, prefix + (key,))
    else:
        yield prefix

def drop_path(target, path):
    cur = target
    for key in path[:-1]:
        cur = cur.get(key)
        if not isinstance(cur, dict):
            return
    cur.pop(path[-1], None)

for preset in c.PRESETS.values():
    for path in leaf_paths(preset):
        drop_path(cfg, path)

cfg = c._deep_merge(cfg, c.PRESETS[name])
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
print("applied preset", name)
PY
```

After saving, render the preview one final time and confirm the user is happy.
Remind them changes apply on the next status-line refresh (usually immediate; a
new session guarantees it).
