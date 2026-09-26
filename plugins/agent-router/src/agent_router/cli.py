"""Command-line entry point for agent-router.

Every hook in ``hooks/hooks.json`` is a one-line invocation of this module with a
subcommand. Hook subcommands read the hook's JSON payload on stdin and must never
fail the host: any error degrades to "exit 0, print nothing".
"""

from __future__ import annotations

import sys

from . import __version__

USAGE = f"""agent-router {__version__}

Usage: agent-router <subcommand> [options]

Hook subcommands (read the hook JSON payload on stdin):
  classify-prompt   UserPromptSubmit: rules-only model advisory for the prompt
  route-task        PreToolUse on Task/Agent: rewrite the subagent's model
  record-outcome    PostToolUse / SubagentStop / Stop: log tokens and duration

User subcommands:
  report            summarize the routing log
  eval              score the rules engine against the golden task set
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE, end="")
        return 0
    if args[0] in ("-V", "--version"):
        print(__version__)
        return 0
    print(f"agent-router: unknown subcommand {args[0]!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
