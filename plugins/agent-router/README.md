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
   `low`, `mid`, or `high` with a confidence, in about 2-3 seconds for about
   $0.0007. The classifier runs with its own short system prompt instead of
   Claude Code's, which is what keeps it this cheap.
3. The answer can move **up** one tier, never down:
   - **low confidence** - the confidence is missing or below
     `classifier.minConfidence` (0.7), so the router picks the next tier up;
   - **adaptive** - past routed dispatches of this subagent type at this tier
     showed too many quality issues (see below).
4. The tier maps to a model (`haiku` / `sonnet` / `opus` by default) and the
   dispatch is rewritten to that model.
5. When the subagent finishes, its token usage, duration, and a quality signal
   are logged.

The router leaves a dispatch unchanged when:

- the user chose its model: a `model` on the dispatch, a `model` in the agent's
  definition, or `CLAUDE_CODE_SUBAGENT_MODEL`;
- the pick would be pricier than the model it would already use (the session
  model, which subagents without a pinned model inherit - built-in Explore
  included);
- the session model or the picked model is not a known family, so the router
  cannot prove the switch is cheaper;
- the classifier fails or times out.

Main-session prompts are never classified. No hook can switch the main-session
model, so an advisory would only add the classifier's cost on top of the model
that answers anyway.

### Quality signals and adaptive routing

A routed dispatch has a **quality issue** when its subagent returned a
near-empty result (under `adaptive.shortResultChars` characters), or when the
same task - same subagent type and description - was dispatched again in the
same session within `adaptive.redispatchWindowSeconds`. Both suggest the
cheaper model was not enough.

After each turn in which subagents finished, the router counts outcomes and
issues per subagent type and tier into a small `adaptive.json`. Once a
type/tier has at least `adaptive.minSamples` (5) outcomes and an issue rate of
`adaptive.maxIssueRate` (40%) or more, later dispatches of that type at that
tier route one tier up. It only ever escalates, so the worst case is a smaller
saving. `/agent-router:report` shows the counts per subagent type.

### Build an eval set from your own tasks

Set `capture.enabled` to `true` and the router saves each dispatch's
description and prompt excerpt to `captures.jsonl` in its data directory (never
into the routing log). Then:

```bash
python3 src/router.py export-captures --out my-golden.jsonl
# review and correct each expected_tier (pre-filled with the router's pick)
python3 src/router.py eval --golden my-golden.jsonl
```

### Flow

```text
 MAIN SESSION (e.g. Opus)          no router hook on your prompts: no cost, no delay
 ──────────────────────────
  you: "fix the login bug"
          │
          ▼
  Claude decides to use a subagent (Agent / Task tool)
          │
          │  PreToolUse hook  ──►  router.py route-task
          ▼
 ┌───────────────────────────── ROUTE-TASK ─────────────────────────────┐
 │                                                                      │
 │  1. Did the user already choose the model?                           │
 │     • `model` set on the dispatch                                    │
 │     • `model:` in the agent's .md frontmatter             ── yes ──► KEEP
 │     • CLAUDE_CODE_SUBAGENT_MODEL env var                  (override) │
 │                        │ no                                          │
 │                        ▼                                             │
 │  2. Ask the classifier ────────────────────────────┐                 │
 │                                                    ▼                 │
 │                        ┌────────── classifier (nested claude -p) ──┐ │
 │                        │ model: haiku   safe-mode, no tools,       │ │
 │                        │ thinking off, hooks disabled,             │ │
 │                        │ AGENT_ROUTER_NESTED=1                     │ │
 │                        │ input: type + description + 4k of prompt  │ │
 │                        │ output: {"tier":..,"confidence":..}       │ │
 │                        │ ~2-3 s, ~$0.0007                          │ │
 │                        └───────────────────────────────────────────┘ │
 │                        │ fail/timeout (6 s)  ──────────────────────► KEEP
 │                        ▼                                   (fallback)│
 │  3. one tier up if confidence < 0.7, or if this subagent type        │
 │     keeps showing quality issues at this tier (adaptive)             │
 │                        │                                             │
 │  4. tier ─► model:   low ─► haiku   mid ─► sonnet   high ─► opus     │
 │                        │                                             │
 │  5. Compare with the model it would otherwise use (the session       │
 │     model, read from the transcript):                                │
 │     • either model family unknown  ──────────────────────────────►  KEEP
 │     • pick is pricier than the session model  ───────────────────►  KEEP
 │     • pick is the same model  ───────────────────────────────────►  KEEP
 │     • pick is cheaper  ───────────────┐                              │
 └───────────────────────────────────────┼──────────────────────────────┘
                                         ▼
                 REWRITE: updatedInput = original input + {"model": "haiku"}
                                         │
                                         ▼
                 subagent runs on the cheaper model  (Opus ─► Haiku)

   every path above appends a "decision" record ─────┐
                                                     ▼
 ┌──────────────────────── OUTCOME CAPTURE ─────────────────────────────┐
 │  PostToolUse     ─► "link"          tool_use_id ↔ agentId, model     │
 │  SubagentStop    ─► "subagent_stop" path to the subagent transcript  │
 │  Stop (turn end) ─► read transcript ─► "outcome": tokens, duration,  │
 │                     result length (quality signal)                   │
 │                  ─► session totals ─► summary.json (locked, atomic)  │
 │                  ─► per type/tier issue rates ─► adaptive.json       │
 └──────────────────────────────────────────────────────────────────────┘
                     │                                 │
                     ▼                                 ▼
   ~/.claude/plugins/data/agent-router/     ~/.claude/plugins/agent-router/
   log.jsonl (+ log.1..3, 5 MB rotation)    summary.json (last 50 sessions)
   (no prompt text, only a hash and sizes)
                     │                                 │
                     ▼                                 ▼
   /agent-router:report                      status-line `router` segment
   ─────────────────────                     ──────────────────────────────
   decisions: LLM / override / fallback      [Opus 5] | ctx 9% | router: 4↓ $0.38 saved
   tier-up adjustments, quality issues
   per-subagent-type breakdown
   classifier cost + avg latency
   net savings (estimate) =
     cost on the session model
   − cost on the routed model
   − classifier cost
```

Every hook error, timeout, or unreadable file exits cleanly and leaves the
dispatch unchanged. Two guards (`disableAllHooks` and `AGENT_ROUTER_NESTED`)
keep the classifier's own `claude -p` session from re-entering the router.

## Commands

| Command | What it does |
|---------|--------------|
| `/agent-router:setup` | Preflight: checks `python3`, the router CLI, and the `claude` CLI; shows the hooks, config, and log paths |
| `/agent-router:configure` | Change tier models, turn the classifier off or change its model and timeout, log retention, or the price table |
| `/agent-router:report` | Routed dispatches, classifier cost, estimated net savings, quality issues, and a per-subagent-type breakdown |

## Savings in the status line

With the [status-line](../status-line) plugin installed, add `router` to its
`segments` to see this session's routing at a glance:

```text
[Opus 5] | claude | ctx ▰▱▱▱▱▱▱▱▱▱ 9% | router: 4↓ $0.38 saved
```

`4↓` is the number of subagent dispatches moved to a cheaper model this session;
the dollar figure is the estimated net saving after classifier cost (the same
estimate `report` shows). After each turn the router writes these totals to
`${CLAUDE_CONFIG_DIR:-~/.claude}/plugins/agent-router/summary.json` (the most
recent 50 sessions), which the segment reads. The segment stays hidden until
something is routed.

Routing saves money, not context: a subagent's work stays out of the main
session's context whichever model it runs on.

## Configuration

`${CLAUDE_CONFIG_DIR:-~/.claude}/plugins/agent-router/config.json`, deep-merged
over the defaults in [`config.json`](config.json):

| Key | Default | Meaning |
|-----|---------|---------|
| `tiers` | `{"low": "haiku", "mid": "sonnet", "high": "opus"}` | Model alias for each tier |
| `classifier.enabled` | `true` | `false` pauses all routing |
| `classifier.model` | `"haiku"` | Model that classifies dispatches |
| `classifier.timeoutSeconds` | `6` | On timeout the dispatch keeps its model |
| `classifier.minConfidence` | `0.7` | Below this (or with no confidence), route one tier up |
| `adaptive.enabled` | `true` | Escalate a subagent type/tier that keeps showing quality issues |
| `adaptive.minSamples` | `5` | Outcomes needed before a type/tier can escalate |
| `adaptive.maxIssueRate` | `0.4` | Issue rate at which a type/tier escalates |
| `adaptive.shortResultChars` | `20` | A subagent result shorter than this counts as an issue |
| `adaptive.redispatchWindowSeconds` | `900` | Re-dispatching the same task within this window counts as an issue |
| `capture.enabled` | `false` | Save real dispatch text locally for `export-captures` |
| `log.maxBytes` | `5000000` | Size at which `log.jsonl` rotates |
| `log.keepSegments` | `3` | Rotated log files kept |
| `pricing` | Haiku, Sonnet, Opus, Fable, and Mythos list prices | USD per million tokens, used only by `report` |

## Privacy

The routing log stays on your machine under `${CLAUDE_PLUGIN_DATA}`. It records
a hash of each dispatch, its type, sizes, the chosen tier and model, token
counts, and the length of the subagent's result - never the prompt or result
text. Only the opt-in `capture.enabled` mode saves dispatch text, to a separate
`captures.jsonl`. The classifier call sends the dispatch's
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
| Same call with a classifier-only `--system-prompt` | ~2.3 s, ~600 input and ~17 output tokens, ~$0.0007 per call; golden-set accuracy rose from 85.7% to 100% (21/21, two runs) |
| `updatedInput` applies without a `permissionDecision` | Confirmed: the router never auto-approves a dispatch |

The subagent tool is named `Agent` in current Claude Code; hooks match
`Task|Agent` to cover older versions.
