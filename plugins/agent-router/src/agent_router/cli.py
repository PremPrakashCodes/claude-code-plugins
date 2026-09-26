"""Command-line entry point for agent-router.

Every hook in ``hooks/hooks.json`` is a one-line invocation of this module with a
subcommand. Hook subcommands read the hook's JSON payload on stdin and must never
fail the host: any error degrades to "exit 0, print nothing".
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from . import config as config_mod
from . import data as data_mod
from . import eval as eval_mod
from . import hooks as hooks_mod
from . import log as log_mod
from . import outcomes as outcomes_mod
from . import report as report_mod
from . import summary as summary_mod
from .classifier import NESTED_ENV

USAGE = f"""agent-router {__version__}

Usage: agent-router <subcommand> [options]

Hook subcommands (read the hook JSON payload on stdin):
  route-task        PreToolUse on Task/Agent: classify and rewrite the subagent's model
  record-outcome    PostToolUse / SubagentStop / Stop: log tokens and duration

User subcommands:
  report            summarize the routing log
  eval              score the classifier against the golden task set (live calls)
                    options: --golden PATH, --floor 0.8, --json
"""

HOOK_COMMANDS = ("route-task", "record-outcome")


def _finish_turn(payload: dict[str, Any], config: dict[str, Any]) -> None:
    """Stop: resolve this session's finished subagents and refresh its summary."""
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return
    # Stop runs every turn: read the live log plus the newest rotated segment
    # (so one rotation mid-session loses nothing), not the full history.
    session_records = [
        r for r in log_mod.read_records(recent_segments=1) if r.get("session_id") == session_id
    ]
    new_outcomes, totals = hooks_mod.finish_turn(session_id, session_records, config)
    for record in new_outcomes:
        log_mod.append(record, config)
    if totals is not None:
        summary_mod.update(session_id, routed=totals[0], net_savings_usd=totals[1])


def _run_hook(command: str) -> None:
    payload = data_mod.read_payload()
    config = config_mod.load()
    records: list[dict[str, Any]] = []
    reply = None
    if command == "route-task":
        reply, records = hooks_mod.route_task(payload, config)
    elif command == "record-outcome":
        if payload.get("hook_event_name") == "Stop":
            _finish_turn(payload, config)
            return
        records = hooks_mod.record_outcome(payload)
    for record in records:
        log_mod.append(record, config)
    if reply is not None:
        sys.stdout.write(json.dumps(reply) + "\n")


def _run_report(args: list[str]) -> int:
    config = config_mod.load()
    records = list(log_mod.read_records())
    # Outcomes a Stop hook has not resolved yet (e.g. the session is still open).
    for outcome in outcomes_mod.resolve_pending(records):
        log_mod.append(outcome, config)
        records.append(outcome)
    summary = report_mod.summarize(records, config)
    if "--json" in args:
        print(json.dumps(summary, indent=2))
    else:
        print(report_mod.format_summary(summary, config))
        print(f"\nLog: {log_mod.log_path()}")
    return 0


def _option(args: list[str], name: str) -> str | None:
    if name in args:
        index = args.index(name)
        if index + 1 < len(args):
            return args[index + 1]
    return None


def _run_eval(args: list[str]) -> int:
    golden = Path(_option(args, "--golden") or eval_mod.DEFAULT_GOLDEN)
    floor_arg = _option(args, "--floor")
    try:
        floor = float(floor_arg) if floor_arg is not None else eval_mod.DEFAULT_FLOOR
    except ValueError:
        print(f"agent-router: --floor must be a number, got {floor_arg!r}", file=sys.stderr)
        return 2
    fixtures, warnings = eval_mod.load_golden(golden)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    result = eval_mod.run(fixtures, config_mod.load())
    if "--json" in args:
        print(json.dumps(result, indent=2))
    else:
        print(eval_mod.format_result(result, floor))
    return 0 if fixtures and result["accuracy"] >= floor else 1


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE, end="")
        return 0
    if args[0] in ("-V", "--version"):
        print(__version__)
        return 0
    command = args[0]
    if command in HOOK_COMMANDS:
        # Inside the classifier's own nested session: never re-enter the router.
        if os.environ.get(NESTED_ENV):
            return 0
        try:
            _run_hook(command)
        except Exception:
            # A hook must never break the host; routing degrades to "no change".
            pass
        return 0
    if command == "report":
        return _run_report(args[1:])
    if command == "eval":
        return _run_eval(args[1:])
    print(f"agent-router: unknown subcommand {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
