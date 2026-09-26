---
description: Summarize agent-router's routing log - routed dispatches, classifier cost, and estimated net savings
allowed-tools: Bash
---

Show the user the agent-router routing report.

```bash
PYBIN="$(command -v python3 || command -v python)"
"$PYBIN" "$CLAUDE_PLUGIN_ROOT/src/router.py" report
```

Relay the report, then briefly interpret it:

- **Routing decisions** by source: `LLM` (the classifier picked the tier),
  `override` (a model the user chose was kept), `fallback` (the classifier
  failed; the dispatch kept its model).
- **Routed one tier up**: `low_confidence` (the classifier was unsure) and
  `adaptive` (this subagent type kept showing quality issues at the lower tier).
- **Quality issues**: `short_result` (the subagent returned almost nothing) and
  `redispatched` (the same task was sent again soon after). A subagent type with
  many issues in the breakdown table is a candidate for pinning a stronger model
  in its agent definition.
- **Kept after classifying**: `no_upgrade` and `same_model` mean the classifier's
  pick was not cheaper than the model the dispatch would already use.
- **Net savings** are an estimate: each routed subagent's real token usage priced
  at the model it ran on versus its baseline model, minus every classifier call.
  It uses the `pricing` table in the config; suggest `/agent-router:configure` if
  the prices look wrong for the user's plan.
- If there are many `fallback` decisions, name the most common reason (for
  example `timeout` or `claude_not_found`) and the fix.

For machine-readable output, run the same command with `--json`.
