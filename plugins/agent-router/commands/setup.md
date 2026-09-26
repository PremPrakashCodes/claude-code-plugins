---
description: Check that agent-router's hooks can run and show where routing decisions are logged
allowed-tools: Bash, Read, AskUserQuestion
---

You are setting up the **agent-router** plugin for the user. There is nothing to
install: the plugin's hooks (`hooks/hooks.json`) load automatically when the
plugin is enabled and run `src/router.py` with `python3`, using only the Python
standard library. Your job is to confirm those hooks can actually run, explain
what the plugin does, and point at the config and log. Resolve every path; never
guess.

What agent-router does, so you can explain it:

- When Claude dispatches a **subagent** (the `Agent`/`Task` tool), a fast AI
  classifier (Haiku by default, ~2-4 s and ~$0.004 per call) picks a tier -
  low / mid / high - and the dispatch's model is rewritten to the cheapest
  capable model (`haiku` / `sonnet` / `opus` by default).
- It never touches main-session prompts: no hook can switch the main model, so
  classifying them would only add cost.
- It never overrides a model the user chose: an explicit `model` on the
  dispatch, a `model` in the agent's definition, or `CLAUDE_CODE_SUBAGENT_MODEL`.
  It never moves a subagent to a pricier model than it would otherwise use.
- If the classifier fails or times out, the dispatch keeps its model.

---

## Step 1 - Preflight

**macOS / Linux:**
```bash
echo "PLUGIN_ROOT=$CLAUDE_PLUGIN_ROOT"
bash "$CLAUDE_PLUGIN_ROOT/scripts/install.sh" "$CLAUDE_PLUGIN_ROOT"
```

**Windows (PowerShell):**
```powershell
& "$env:CLAUDE_PLUGIN_ROOT\scripts\install.ps1" -PluginSrc "$env:CLAUDE_PLUGIN_ROOT"
```

The script prints two lines on stdout - `ROUTER_CMD=<command>` and
`CLASSIFIER=ok` or `CLASSIFIER=missing-claude` - and progress on stderr.

- If it exits non-zero, stop and relay the error. The usual fix is installing
  Python 3.8+ so `python3` resolves (https://www.python.org/downloads/). On
  Windows, make sure `python3` is not the Microsoft Store stub.
- If `CLASSIFIER=missing-claude`, tell the user routing is inactive until the
  `claude` CLI is on PATH for hook processes; dispatches keep their model.

## Step 2 - Confirm the hooks are registered

Show the plugin's hook file so the user can see exactly what runs:

```bash
cat "$CLAUDE_PLUGIN_ROOT/hooks/hooks.json"
```

It should register `PreToolUse` (matcher `Task|Agent`, `route-task`) plus
`PostToolUse`, `SubagentStop`, and `Stop` (`record-outcome`), and **no**
`UserPromptSubmit` hook. Tell the user they can confirm the live registration
with the `/hooks` command in Claude Code.

## Step 3 - Config and log locations

```bash
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
echo "CONFIG=$CONFIG_DIR/plugins/agent-router/config.json"
echo "DATA=${CLAUDE_PLUGIN_DATA:-$CONFIG_DIR/plugins/data/agent-router}"
ls -la "$CONFIG_DIR/plugins/agent-router/config.json" 2>/dev/null || echo "(no user config - defaults apply)"
```

The defaults work with no config file. Do **not** create or modify the config
here; point the user to `/agent-router:configure` for changes.

## Step 4 - Finish

Tell the user:

- Routing starts in the next session (or after `/reload-plugins`).
- **`/agent-router:report`** shows routed dispatches, classifier cost, and the
  estimated net savings.
- **`/agent-router:configure`** changes the tier models, turns the classifier
  off or picks its model, or edits the price table used for the estimate.
- To pause routing without uninstalling, set `classifier.enabled` to `false`.
