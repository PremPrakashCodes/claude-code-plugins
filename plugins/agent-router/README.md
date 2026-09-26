# agent-router

A model-routing layer for Claude Code. It classifies each of Claude's subagent
dispatches with a fast AI classifier (Haiku by default), rewrites that dispatch's
model to the cheapest capable tier, and logs every routing decision locally,
including what the classifier itself cost.

Main-session prompts are never classified: no hook can switch the main-session
model, so classifying them would only add cost on top of the model that answers
anyway.

Pure Python, standard library only (Python 3.8+).

## Install

```text
/plugin marketplace add PremPrakashCodes/claude-code-plugins
/plugin install agent-router
/reload-plugins
/agent-router:setup
```

Requirements: `python3` (3.8+) and the `claude` CLI on `PATH`. There is nothing
else to install; the hooks run the plugin's `src/router.py` directly.

## How it works

1. Claude dispatches a subagent (the `Agent`/`Task` tool).
2. The `PreToolUse` hook sends the dispatch's type, description, and the first
   4,000 characters of its prompt to a classifier (Haiku by default). It answers
   `low`, `mid`, or `high` in about 2-4 seconds for about $0.004.
3. The tier maps to a model (`haiku` / `sonnet` / `opus` by default) and the
   dispatch is rewritten to that model.
4. When the subagent finishes, its token usage and duration are logged.

The router leaves a dispatch unchanged when:

- the user chose its model: a `model` on the dispatch, a `model` in the agent's
  definition, or `CLAUDE_CODE_SUBAGENT_MODEL`;
- the pick would be pricier than the model it would already use (the session
  model, which subagents without a pinned model inherit - built-in Explore
  included);
- the classifier fails or times out.

Main-session prompts are never classified. No hook can switch the main-session
model, so an advisory would only add the classifier's cost on top of the model
that answers anyway.

## Commands

| Command | What it does |
|---------|--------------|
| `/agent-router:setup` | Preflight: checks `python3`, the router CLI, and the `claude` CLI; shows the hooks, config, and log paths |
| `/agent-router:configure` | Change tier models, turn the classifier off or change its model and timeout, log retention, or the price table |
| `/agent-router:report` | Routed dispatches, classifier cost, and estimated net savings |

## Configuration

`${CLAUDE_CONFIG_DIR:-~/.claude}/plugins/agent-router/config.json`, deep-merged
over the defaults in [`config.json`](config.json):

| Key | Default | Meaning |
|-----|---------|---------|
| `tiers` | `{"low": "haiku", "mid": "sonnet", "high": "opus"}` | Model alias for each tier |
| `classifier.enabled` | `true` | `false` pauses all routing |
| `classifier.model` | `"haiku"` | Model that classifies dispatches |
| `classifier.timeoutSeconds` | `6` | On timeout the dispatch keeps its model |
| `log.maxBytes` | `5000000` | Size at which `log.jsonl` rotates |
| `log.keepSegments` | `3` | Rotated log files kept |
| `pricing` | Haiku, Sonnet, and Opus list prices | USD per million tokens, used only by `report` |

## Privacy

The routing log stays on your machine under `${CLAUDE_PLUGIN_DATA}`. It records
a hash of each dispatch, its type, sizes, the chosen tier and model, and token
counts - never the prompt text. The classifier call sends the dispatch's
description and prompt excerpt to Anthropic through your own `claude` CLI login,
the same as any other Claude Code request.

## Development

```bash
cd plugins/agent-router
python3 -m unittest discover -s tests
ruff check . && ruff format --check .
python3 src/router.py report           # summarize your local log
```

Tests mock the classifier and make no network calls.

## Platform notes

Behavior of the Claude Code hook platform that this plugin depends on, verified
against Claude Code 2.1.283 with a throwaway probe plugin (2026-09-27):

| Assumption | Result |
|------------|--------|
| `hooks/hooks.json` loads without a manifest `hooks` key | Confirmed |
| `${CLAUDE_PLUGIN_DATA}` reaches hook processes | Confirmed (`~/.claude/plugins/data/<plugin>/`) |
| `PreToolUse` `updatedInput.model` changes an `Agent` dispatch's model | Confirmed, including over an agent definition's frontmatter `model` |
| `updatedInput` replaces the whole tool input | Treated as replace: the router always returns a full copy |
| `SessionStart` payload carries the session model | **No** - the session model is read from the transcript instead |
| `PostToolUse` on `Agent` carries tokens and duration | **No** for background subagents (`isAsync: true`); it carries `agentId` and `resolvedModel` |
| `SubagentStop` / `Stop` expose token usage | Via `agent_transcript_path` / `transcript_path` (per-message `usage`) |
| Built-in `Explore` subagent runs on a cheaper default model | **No** - it inherits the session model |
| Nested `claude -p` classifier starts inside a hook (`CLAUDECODE=1`) | Confirmed |
| Minimal classifier call (`--safe-mode --tools ""`, thinking off, Haiku) | 2-4 s, ~4k input and ~20 output tokens, ~$0.004 per call |
| `updatedInput` applies without a `permissionDecision` | Confirmed: the router never auto-approves a dispatch |

The subagent tool is named `Agent` in current Claude Code; hooks match
`Task|Agent` to cover older versions.
