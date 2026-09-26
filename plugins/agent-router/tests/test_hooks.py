import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _path  # noqa: F401
from agent_router import cli, hooks, log
from agent_router import config as config_mod
from agent_router.classifier import ClassifierResult

PLUGIN_DIR = Path(__file__).resolve().parent.parent


def cfg():
    return config_mod._deep_merge(config_mod.DEFAULTS, {})


def ok(tier, confidence=0.9):
    return ClassifierResult(
        ok=True,
        tier=tier,
        confidence=confidence,
        duration_ms=2500,
        cost_usd=0.004,
        usage={"input_tokens": 4000, "output_tokens": 22},
    )


def classify_as(tier_or_result):
    calls = []

    def fake(subagent_type, description, prompt, config):
        calls.append((subagent_type, description, prompt))
        if isinstance(tier_or_result, ClassifierResult):
            return tier_or_result
        return ok(tier_or_result)

    fake.calls = calls
    return fake


def dispatch_payload(**tool_input):
    base = {"description": "Find config usages", "prompt": "Find usages.", "subagent_type": "x"}
    base.update(tool_input)
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_use_id": "toolu_1",
        "session_id": "s1",
        "prompt_id": "p1",
        "cwd": "/nonexistent-repo",
        "transcript_path": "/t.jsonl",
        "tool_input": base,
    }


def session(model):
    return lambda _transcript: model


class EnvCase(unittest.TestCase):
    """Isolates config, plugin data, and agent lookups in temp dirs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data_dir = root / "data"
        self.config_dir = root / "config"
        self.config_dir.mkdir()
        patcher = mock.patch.dict(
            os.environ,
            {"CLAUDE_PLUGIN_DATA": str(self.data_dir), "CLAUDE_CONFIG_DIR": str(self.config_dir)},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in ("AGENT_ROUTER_NESTED", hooks.SUBAGENT_MODEL_ENV):
            os.environ.pop(key, None)
        self.addCleanup(self.tmp.cleanup)


class TestRouteTask(EnvCase):
    def test_low_dispatch_is_rewritten_with_full_input(self):
        payload = dispatch_payload(run_in_background=True)
        reply, records = hooks.route_task(
            payload, cfg(), classify=classify_as("low"), session_model=session("claude-opus-5")
        )
        updated = reply["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(reply["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(updated["model"], "haiku")
        for key, value in payload["tool_input"].items():
            self.assertEqual(updated[key], value)
        self.assertNotIn("permissionDecision", reply["hookSpecificOutput"])
        (record,) = records
        self.assertEqual(record["source"], "LLM")
        self.assertEqual(record["action"], "rewrite")
        self.assertEqual(record["tier"], "low")
        self.assertEqual(record["model"], "haiku")
        self.assertEqual(record["baseline_model"], "claude-opus-5")
        self.assertEqual(record["tool_use_id"], "toolu_1")
        # the classifier's own cost is on the record
        self.assertEqual(record["classifier"]["usage"]["input_tokens"], 4000)
        self.assertEqual(record["classifier"]["duration_ms"], 2500)
        self.assertNotIn("Find usages.", json.dumps(record))

    def test_low_confidence_routes_one_tier_up(self):
        reply, records = hooks.route_task(
            dispatch_payload(),
            cfg(),
            classify=classify_as(ok("low", confidence=0.4)),
            session_model=session("claude-opus-5"),
            adaptive_stats=lambda: {},
        )
        self.assertEqual(reply["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")
        self.assertEqual(records[0]["classifier_tier"], "low")
        self.assertEqual(records[0]["tier"], "mid")
        self.assertEqual(records[0]["adjustments"], ["low_confidence"])

    def test_adaptive_stats_escalate_a_struggling_type(self):
        stats = {"groups": {"x|low": {"outcomes": 6, "issues": 4}}}
        reply, records = hooks.route_task(
            dispatch_payload(),
            cfg(),
            classify=classify_as("low"),
            session_model=session("claude-opus-5"),
            adaptive_stats=lambda: stats,
        )
        self.assertEqual(reply["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")
        self.assertEqual(records[0]["adjustments"], ["adaptive"])

    def test_decision_carries_task_key_not_description(self):
        _, records = hooks.route_task(
            dispatch_payload(description="Find Config Usages"),
            cfg(),
            classify=classify_as("low"),
            session_model=session("claude-opus-5"),
            adaptive_stats=lambda: {},
        )
        _, again = hooks.route_task(
            dispatch_payload(description="  find config   usages "),
            cfg(),
            classify=classify_as("low"),
            session_model=session("claude-opus-5"),
            adaptive_stats=lambda: {},
        )
        self.assertEqual(records[0]["task_key"], again[0]["task_key"])
        self.assertNotIn("Find Config Usages", json.dumps(records))

    def test_capture_record_only_when_enabled(self):
        _, records = hooks.route_task(
            dispatch_payload(), cfg(), classify=classify_as("low"), adaptive_stats=lambda: {}
        )
        self.assertEqual([r["kind"] for r in records], ["decision"])
        config = cfg()
        config["capture"]["enabled"] = True
        _, records = hooks.route_task(
            dispatch_payload(), config, classify=classify_as("low"), adaptive_stats=lambda: {}
        )
        capture = records[-1]
        self.assertEqual(capture["kind"], "capture")
        self.assertEqual(capture["description"], "Find config usages")
        self.assertEqual(capture["routed_tier"], "low")

    def test_explicit_model_is_kept_and_not_classified(self):
        fake = classify_as("low")
        reply, records = hooks.route_task(dispatch_payload(model="opus"), cfg(), classify=fake)
        self.assertIsNone(reply)
        self.assertEqual(fake.calls, [])
        self.assertEqual(records[0]["source"], "override")
        self.assertEqual(records[0]["override"], "dispatch")

    def test_agent_definition_model_is_kept(self):
        with tempfile.TemporaryDirectory() as repo:
            agents = Path(repo) / ".claude" / "agents"
            agents.mkdir(parents=True)
            (agents / "reviewer.md").write_text("---\nmodel: opus\n---\n", encoding="utf-8")
            payload = dispatch_payload(subagent_type="reviewer")
            payload["cwd"] = repo
            fake = classify_as("low")
            reply, records = hooks.route_task(payload, cfg(), classify=fake)
        self.assertIsNone(reply)
        self.assertEqual(fake.calls, [])
        self.assertEqual(records[0]["override"], "agent_definition")
        self.assertEqual(records[0]["model"], "opus")

    def test_subagent_model_env_is_kept(self):
        with mock.patch.dict(os.environ, {hooks.SUBAGENT_MODEL_ENV: "sonnet"}):
            reply, records = hooks.route_task(
                dispatch_payload(), cfg(), classify=classify_as("low")
            )
        self.assertIsNone(reply)
        self.assertEqual(records[0]["override"], "subagent_model_env")

    def test_classifier_failure_falls_back(self):
        failed = ClassifierResult(ok=False, reason="timeout", duration_ms=6000)
        reply, records = hooks.route_task(dispatch_payload(), cfg(), classify=classify_as(failed))
        self.assertIsNone(reply)
        self.assertEqual(records[0]["source"], "fallback")
        self.assertEqual(records[0]["reason"], "timeout")
        self.assertEqual(records[0]["classifier"]["duration_ms"], 6000)

    def test_never_upgrades_past_session_model(self):
        reply, records = hooks.route_task(
            dispatch_payload(),
            cfg(),
            classify=classify_as("high"),
            session_model=session("claude-sonnet-5"),
        )
        self.assertIsNone(reply)
        self.assertEqual(records[0]["reason"], "no_upgrade")

    def test_same_family_is_left_alone(self):
        reply, records = hooks.route_task(
            dispatch_payload(),
            cfg(),
            classify=classify_as("mid"),
            session_model=session("claude-sonnet-5"),
        )
        self.assertIsNone(reply)
        self.assertEqual(records[0]["reason"], "same_model")

    def test_explore_inherits_session_model_baseline(self):
        # Verified live: built-in Explore runs on the session model by default
        reply, records = hooks.route_task(
            dispatch_payload(subagent_type="Explore"),
            cfg(),
            classify=classify_as("mid"),
            session_model=session("claude-opus-5"),
        )
        self.assertEqual(reply["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")
        self.assertEqual(records[0]["baseline_model"], "claude-opus-5")

    def test_unknown_session_model_keeps_dispatch(self):
        # Without a known baseline the rewrite could be an upgrade: fail closed
        reply, records = hooks.route_task(
            dispatch_payload(), cfg(), classify=classify_as("mid"), session_model=session(None)
        )
        self.assertIsNone(reply)
        self.assertEqual(records[0]["reason"], "unknown_model_family")

    def test_unrecognized_tier_model_keeps_dispatch(self):
        config = cfg()
        config["tiers"]["low"] = "custom-cheap-model"
        reply, records = hooks.route_task(
            dispatch_payload(),
            config,
            classify=classify_as("low"),
            session_model=session("claude-opus-5"),
        )
        self.assertIsNone(reply)
        self.assertEqual(records[0]["reason"], "unknown_model_family")

    def test_custom_tier_mapping(self):
        config = cfg()
        config["tiers"]["low"] = "sonnet"
        reply, _ = hooks.route_task(
            dispatch_payload(),
            config,
            classify=classify_as("low"),
            session_model=session("claude-opus-5"),
        )
        self.assertEqual(reply["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")

    def test_missing_tier_model_is_kept(self):
        config = cfg()
        config["tiers"] = {}
        reply, records = hooks.route_task(dispatch_payload(), config, classify=classify_as("low"))
        self.assertIsNone(reply)
        self.assertEqual(records[0]["reason"], "no_tier_model")

    def test_disabled_classifier_does_nothing(self):
        config = cfg()
        config["classifier"]["enabled"] = False
        fake = classify_as("low")
        self.assertEqual(hooks.route_task(dispatch_payload(), config, classify=fake), (None, []))
        self.assertEqual(fake.calls, [])

    def test_non_dispatch_tool_is_ignored(self):
        payload = dispatch_payload()
        payload["tool_name"] = "Bash"
        self.assertEqual(hooks.route_task(payload, cfg(), classify=classify_as("low")), (None, []))

    def test_legacy_task_tool_is_routed(self):
        payload = dispatch_payload()
        payload["tool_name"] = "Task"
        reply, _ = hooks.route_task(
            payload, cfg(), classify=classify_as("low"), session_model=session("claude-opus-5")
        )
        self.assertIsNotNone(reply)


def _write_transcript(path: Path, agent_msgs):
    rows = [{"type": "user", "timestamp": "2026-09-27T10:00:00.000Z"}]
    for i, (model, inp, out, ts) in enumerate(agent_msgs):
        row = {
            "type": "assistant",
            "timestamp": ts,
            "message": {
                "id": f"msg_{i}",
                "model": model,
                "usage": {"input_tokens": inp, "output_tokens": out},
            },
        }
        rows.append(row)
        rows.append(row)  # transcripts repeat a message once per content block
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


class TestRecordOutcome(EnvCase):
    def test_full_outcome_flow_joins_decision(self):
        # PostToolUse link + SubagentStop + Stop -> outcome record
        transcript = Path(self.tmp.name) / "agent-a1.jsonl"
        _write_transcript(
            transcript,
            [
                ("claude-haiku-4-5", 700, 50, "2026-09-27T10:00:01.000Z"),
                ("claude-haiku-4-5", 900, 80, "2026-09-27T10:00:04.500Z"),
            ],
        )
        post = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_use_id": "toolu_1",
            "session_id": "s1",
            "tool_response": {
                "isAsync": True,
                "agentId": "a1",
                "resolvedModel": "claude-haiku-4-5-20251001",
            },
        }
        stop_sub = {
            "hook_event_name": "SubagentStop",
            "session_id": "s1",
            "agent_id": "a1",
            "agent_type": "Explore",
            "agent_transcript_path": str(transcript),
        }
        stop = {"hook_event_name": "Stop", "session_id": "s1"}
        run_cli(post)
        run_cli(stop_sub)
        run_cli(stop)
        run_cli(stop)  # idempotent: no second outcome
        outcomes = [r for r in log.read_records() if r["kind"] == "outcome"]
        self.assertEqual(len(outcomes), 1)
        outcome = outcomes[0]
        self.assertEqual(outcome["tool_use_id"], "toolu_1")
        self.assertEqual(outcome["resolved_model"], "claude-haiku-4-5-20251001")
        self.assertEqual(outcome["usage"]["input_tokens"], 1600)
        self.assertEqual(outcome["usage"]["output_tokens"], 130)
        self.assertEqual(outcome["duration_ms"], 4500)

    def test_stop_refreshes_adaptive_stats_when_outcomes_arrive(self):
        from agent_router import adaptive

        transcript = Path(self.tmp.name) / "agent-a9.jsonl"
        _write_transcript(transcript, [("claude-haiku-4-5", 10, 1, "2026-09-27T10:00:01.000Z")])
        log.append(
            {
                "kind": "decision",
                "session_id": "s1",
                "tool_use_id": "t9",
                "subagent_type": "Explore",
                "action": "rewrite",
                "tier": "low",
            },
            cfg(),
        )
        run_cli(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Agent",
                "tool_use_id": "t9",
                "session_id": "s1",
                "tool_response": {"agentId": "a9"},
            }
        )
        run_cli(
            {
                "hook_event_name": "SubagentStop",
                "session_id": "s1",
                "agent_id": "a9",
                "agent_transcript_path": str(transcript),
                "last_assistant_message": "",
            }
        )
        run_cli({"hook_event_name": "Stop", "session_id": "s1"})
        outcome = [r for r in log.read_records() if r["kind"] == "outcome"][0]
        self.assertEqual(outcome["result_chars"], 0)
        stats = adaptive.load()
        self.assertEqual(stats["groups"]["Explore|low"], {"outcomes": 1, "issues": 1})

    def test_stop_before_transcript_exists_retries_later(self):
        post = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_use_id": "t",
            "session_id": "s1",
            "tool_response": {"agentId": "a2"},
        }
        missing = Path(self.tmp.name) / "late.jsonl"
        run_cli(post)
        run_cli(
            {
                "hook_event_name": "SubagentStop",
                "session_id": "s1",
                "agent_id": "a2",
                "agent_transcript_path": str(missing),
            }
        )
        run_cli({"hook_event_name": "Stop", "session_id": "s1"})
        self.assertEqual([r for r in log.read_records() if r["kind"] == "outcome"], [])
        _write_transcript(missing, [("claude-haiku-4-5", 10, 1, "2026-09-27T10:00:01.000Z")])
        run_cli({"hook_event_name": "Stop", "session_id": "s1"})
        self.assertEqual(len([r for r in log.read_records() if r["kind"] == "outcome"]), 1)

    def test_other_tools_are_not_linked(self):
        run_cli({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_response": {}})
        self.assertEqual(list(log.read_records()), [])


def run_cli(payload, command=None, raw=None):
    command = command or (
        "route-task" if payload.get("hook_event_name") == "PreToolUse" else "record-outcome"
    )
    stdin = io.StringIO(raw if raw is not None else json.dumps(payload))
    stdout = io.StringIO()
    with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", stdout):
        code = cli.main([command])
    return code, stdout.getvalue()


class TestCli(EnvCase):
    def test_route_task_end_to_end(self):
        # Defaults are bound at import, so inject the fakes through the CLI's handle.
        real_route_task = hooks.route_task
        with mock.patch.object(
            cli.hooks_mod,
            "route_task",
            lambda p, c: real_route_task(
                p, c, classify=classify_as("low"), session_model=session("claude-opus-5")
            ),
        ):
            code, out = run_cli(dispatch_payload())
        self.assertEqual(code, 0)
        reply = json.loads(out)
        self.assertEqual(reply["hookSpecificOutput"]["updatedInput"]["model"], "haiku")
        (record,) = list(log.read_records())
        self.assertEqual(record["action"], "rewrite")

    def test_capture_goes_to_capture_file_not_log(self):
        config_file = self.config_dir / "plugins" / "agent-router" / "config.json"
        config_file.parent.mkdir(parents=True)
        config_file.write_text(json.dumps({"capture": {"enabled": True}}))
        real_route_task = hooks.route_task
        with mock.patch.object(
            cli.hooks_mod,
            "route_task",
            lambda p, c: real_route_task(
                p,
                c,
                classify=classify_as("low"),
                session_model=session("claude-opus-5"),
                adaptive_stats=lambda: {},
            ),
        ):
            run_cli(dispatch_payload())
        self.assertEqual([r["kind"] for r in log.read_records()], ["decision"])
        captures = list(log.read_records(cli.capture_path()))
        self.assertEqual(captures[0]["prompt"], "Find usages.")
        out = self.data_dir / "golden.jsonl"
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(cli.main(["export-captures", "--out", str(out)]), 0)
        fixture = json.loads(out.read_text().splitlines()[0])
        self.assertEqual(fixture["expected_tier"], "low")
        self.assertEqual(fixture["description"], "Find config usages")

    def test_export_without_captures_fails_clearly(self):
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            self.assertEqual(cli.main(["export-captures"]), 1)
        self.assertIn("capture.enabled", err.getvalue())

    def test_garbage_stdin_is_silent(self):
        code, out = run_cli({}, command="route-task", raw="{{{ not json")
        self.assertEqual((code, out), (0, ""))
        code, out = run_cli({}, command="record-outcome", raw="")
        self.assertEqual((code, out), (0, ""))

    def test_internal_error_is_silent(self):
        def boom(_p, _c):
            raise RuntimeError("bug")

        with mock.patch.object(cli.hooks_mod, "route_task", boom):
            self.assertEqual(run_cli(dispatch_payload()), (0, ""))

    def test_nested_env_is_a_no_op(self):
        with mock.patch.dict(os.environ, {"AGENT_ROUTER_NESTED": "1"}):
            with mock.patch.object(cli.hooks_mod, "route_task") as route:
                self.assertEqual(run_cli(dispatch_payload()), (0, ""))
                self.assertEqual(run_cli({"hook_event_name": "Stop"}), (0, ""))
                route.assert_not_called()
        self.assertEqual(list(log.read_records()), [])

    def test_unknown_subcommand(self):
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(cli.main(["nope"]), 2)


class TestHooksJson(unittest.TestCase):
    def setUp(self):
        self.hooks = json.loads((PLUGIN_DIR / "hooks" / "hooks.json").read_text())["hooks"]

    def test_no_main_session_prompt_hook(self):
        # main-session prompts are never classified
        self.assertNotIn("UserPromptSubmit", self.hooks)

    def test_dispatch_and_outcome_hooks_registered(self):
        self.assertEqual(self.hooks["PreToolUse"][0]["matcher"], "Task|Agent")
        self.assertEqual(self.hooks["PostToolUse"][0]["matcher"], "Task|Agent")
        for event in ("SubagentStop", "Stop"):
            self.assertIn(event, self.hooks)
        commands = [
            h["command"] for entries in self.hooks.values() for e in entries for h in e["hooks"]
        ]
        for command in commands:
            self.assertIn("${CLAUDE_PLUGIN_ROOT}/src/router.py", command)
        self.assertIn("route-task", self.hooks["PreToolUse"][0]["hooks"][0]["command"])

    def test_route_timeout_exceeds_classifier_timeout(self):
        hook_timeout = self.hooks["PreToolUse"][0]["hooks"][0]["timeout"]
        self.assertGreater(hook_timeout, config_mod.DEFAULTS["classifier"]["timeoutSeconds"])


if __name__ == "__main__":
    unittest.main()
