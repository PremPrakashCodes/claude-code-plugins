---
description: Configure agent-router (tier models, classifier, log retention, price table)
allowed-tools: Bash, Read, Edit, Write, AskUserQuestion
---

You are configuring the **agent-router** plugin. The user's config lives at
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/agent-router/config.json` and is
**deep-merged over defaults** - write only the keys the user changes and leave
every other (possibly hand-edited) key untouched.

Ask what they want to change, make the change, show the effective config, and
repeat until they are done. Don't dump every option at once.

## Step 0 - Show the effective config

```bash
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CONFIG_PATH="$CONFIG_DIR/plugins/agent-router/config.json"
echo "CONFIG_PATH=$CONFIG_PATH"
PYBIN="$(command -v python3 || command -v python)"
"$PYBIN" - <<'PY'
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["CLAUDE_PLUGIN_ROOT"], "src"))
from agent_router import config as c
print(json.dumps(c.load(), indent=2))
PY
```

The authoritative option list and defaults live in
`$CLAUDE_PLUGIN_ROOT/src/agent_router/config.py` (`DEFAULTS`).

## Options you can offer (via AskUserQuestion)

1. **Tier models** - `"tiers"`: which model alias each tier routes to. Defaults
   `{"low": "haiku", "mid": "sonnet", "high": "opus"}`. Use Claude Code model
   aliases, not full model IDs, so new versions resolve automatically. Example:
   route low-tier work to Sonnet with `{"tiers": {"low": "sonnet"}}`.

2. **Classifier** - `"classifier"`:
   - `enabled` (default `true`): `false` pauses all routing; dispatches keep
     their model and nothing is classified.
   - `model` (default `"haiku"`): the model that classifies each dispatch.
     A pricier model costs more per dispatch and can cancel out the savings.
   - `timeoutSeconds` (default `6`): calls take ~2-4 s; on timeout the dispatch
     keeps its model. Every dispatch waits for the classifier, so keep this low.

3. **Log retention** - `"log"`: `maxBytes` (default 5 MB) is the size at which
   `log.jsonl` rotates; `keepSegments` (default 3) is how many rotated files are
   kept. The log stays on this machine.

4. **Price table** - `"pricing"`: USD per million tokens per model family
   (`input`, `output`, `cacheRead`, `cacheWrite`), used only by
   `/agent-router:report` to estimate savings. Update it to match the user's
   plan or the current price list.

## Writing the file

Merge the user's changes into the existing JSON and write with 2-space indent.
Edit the marked block to apply the chosen keys:

```bash
PYBIN="$(command -v python3 || command -v python)"
"$PYBIN" - <<'PY'
import json, os
from pathlib import Path

p = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")).expanduser()
p = p / "plugins" / "agent-router" / "config.json"
cfg = {}
if p.exists():
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"config.json is not valid JSON: {exc}")
    if not isinstance(cfg, dict):
        raise SystemExit("config.json must contain a JSON object")

# --- merge the user's chosen changes into cfg here ---
cfg.setdefault("tiers", {})["low"] = "haiku"
cfg.setdefault("classifier", {})["timeoutSeconds"] = 6
# ----------------------------------------------------

p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
print("saved", p)
PY
```

After saving, re-run Step 0 to show the effective config. Changes apply to the
next subagent dispatch - hooks read the config on every call.
