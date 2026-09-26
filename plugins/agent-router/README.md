# agent-router

A model-routing layer for Claude Code. It classifies each of Claude's subagent
dispatches with a fast AI classifier (Haiku by default), rewrites that dispatch's
model to the cheapest capable tier, and logs every routing decision locally,
including what the classifier itself cost.

Main-session prompts are never classified: no hook can switch the main-session
model, so classifying them would only add cost on top of the model that answers
anyway.

Pure Python, standard library only (Python 3.8+).

> Status: under active development. Setup and usage docs land with the slash
> commands.

## Platform notes

Behavior of the Claude Code hook platform that this plugin depends on, verified
against Claude Code 2.1.283 with a throwaway probe plugin (2026-09-27):

| Assumption | Result |
|------------|--------|
| `hooks/hooks.json` loads without a manifest `hooks` key | Confirmed |
| `${CLAUDE_PLUGIN_DATA}` reaches hook processes | Confirmed (`~/.claude/plugins/data/<plugin>/`) |
| `UserPromptSubmit` `systemMessage` is shown to the user | Confirmed: rendered as a notice, prompt continues |
| `PreToolUse` `updatedInput.model` changes an `Agent` dispatch's model | Confirmed, including over an agent definition's frontmatter `model` |
| `updatedInput` replaces the whole tool input | Treated as replace: the router always returns a full copy |
| `SessionStart` payload carries the session model | **No** - the session model is read from the transcript instead |
| `PostToolUse` on `Agent` carries tokens and duration | **No** for background subagents (`isAsync: true`); it carries `agentId` and `resolvedModel` |
| `SubagentStop` / `Stop` expose token usage | Via `agent_transcript_path` / `transcript_path` (per-message `usage`) |
| `UserPromptSubmit` fires only for user prompts | **No** - it also fires for `<task-notification>` turns, which the router skips |
| Nested `claude -p` classifier starts inside a hook (`CLAUDECODE=1`) | Confirmed |
| Minimal classifier call (`--safe-mode --tools "" --model haiku`) | ~2.6-3.1 s, ~3.7k input tokens, ~$0.005 per call |

The subagent tool is named `Agent` in current Claude Code; hooks match
`Task|Agent` to cover older versions.
