import json
import subprocess
import unittest

import _path  # noqa: F401
from agent_router import classifier
from agent_router import config as config_mod


def cfg(**classifier_overrides):
    return config_mod._deep_merge(config_mod.DEFAULTS, {"classifier": classifier_overrides})


def cli_output(result_text, *, is_error=False, as_list=True):
    result = {
        "type": "result",
        "subtype": "success" if not is_error else "error",
        "is_error": is_error,
        "result": result_text,
        "duration_ms": 2810,
        "total_cost_usd": 0.0048,
        "usage": {
            "input_tokens": 3671,
            "output_tokens": 221,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }
    payload = [{"type": "system", "subtype": "init"}, result] if as_list else result
    return json.dumps(payload)


class FakeRunner:
    """Records the subprocess call and returns a canned CompletedProcess."""

    def __init__(self, stdout="", returncode=0, exc=None):
        self.stdout = stdout
        self.returncode = returncode
        self.exc = exc
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.exc:
            raise self.exc
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "")


def which_found(_name):
    return "/usr/local/bin/claude"


def classify(runner, config=None, **kwargs):
    return classifier.classify(
        subagent_type=kwargs.get("subagent_type", "Explore"),
        description=kwargs.get("description", "Find config loader usages"),
        prompt=kwargs.get("prompt", "Find where the config loader is used."),
        config=config or cfg(),
        runner=runner,
        which=kwargs.get("which", which_found),
    )


class TestClassifier(unittest.TestCase):
    def test_bare_json_reply(self):
        runner = FakeRunner(cli_output('{"tier": "low", "confidence": 0.93}'))
        result = classify(runner)
        self.assertTrue(result.ok)
        self.assertEqual(result.tier, "low")
        self.assertAlmostEqual(result.confidence, 0.93)
        self.assertEqual(result.usage["input_tokens"], 3671)
        self.assertEqual(result.usage["output_tokens"], 221)
        self.assertAlmostEqual(result.cost_usd, 0.0048)
        self.assertIsInstance(result.duration_ms, int)
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_fenced_json_reply(self):
        # Haiku wraps JSON in a code fence in practice
        runner = FakeRunner(cli_output('```json\n{"tier": "high", "confidence": 0.8}\n```'))
        result = classify(runner)
        self.assertTrue(result.ok)
        self.assertEqual(result.tier, "high")

    def test_single_object_output(self):
        runner = FakeRunner(cli_output('{"tier": "mid", "confidence": 0.7}', as_list=False))
        self.assertEqual(classify(runner).tier, "mid")

    def test_confidence_is_clamped_and_optional(self):
        runner = FakeRunner(cli_output('{"tier": "mid", "confidence": 7}'))
        self.assertEqual(classify(runner).confidence, 1.0)
        runner = FakeRunner(cli_output('{"tier": "mid"}'))
        result = classify(runner)
        self.assertTrue(result.ok)
        self.assertIsNone(result.confidence)

    def test_unknown_tier_is_a_failure(self):
        runner = FakeRunner(cli_output('{"tier": "extreme", "confidence": 0.9}'))
        result = classify(runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "bad_reply")

    def test_unparseable_reply(self):
        result = classify(FakeRunner(cli_output("I think this is a low task.")))
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "bad_reply")

    def test_unparseable_cli_output(self):
        result = classify(FakeRunner("not json at all"))
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "bad_output")

    def test_cli_error_result(self):
        result = classify(FakeRunner(cli_output("rate limited", is_error=True)))
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "cli_error")

    def test_nonzero_exit(self):
        result = classify(FakeRunner("", returncode=1))
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "exit_1")

    def test_timeout(self):
        runner = FakeRunner(exc=subprocess.TimeoutExpired(cmd="claude", timeout=6))
        result = classify(runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "timeout")
        self.assertIsNotNone(result.duration_ms)

    def test_os_error(self):
        result = classify(FakeRunner(exc=OSError("boom")))
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "os_error")

    def test_missing_claude_binary(self):
        runner = FakeRunner(cli_output('{"tier": "low"}'))
        result = classify(runner, which=lambda _n: None)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "claude_not_found")
        self.assertEqual(runner.calls, [])

    def test_disabled_makes_no_call(self):
        runner = FakeRunner(cli_output('{"tier": "low"}'))
        result = classify(runner, config=cfg(enabled=False))
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "disabled")
        self.assertEqual(runner.calls, [])

    def test_command_is_minimal_and_guarded(self):
        runner = FakeRunner(cli_output('{"tier": "low"}'))
        classify(runner, config=cfg(model="sonnet", timeoutSeconds=4))
        args, kwargs = runner.calls[0]
        self.assertEqual(args[0], "/usr/local/bin/claude")
        self.assertIn("-p", args)
        self.assertEqual(args[args.index("--model") + 1], "sonnet")
        self.assertIn("--safe-mode", args)
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertIn("--no-session-persistence", args)
        settings = json.loads(args[args.index("--settings") + 1])
        self.assertIs(settings["disableAllHooks"], True)
        self.assertIs(settings["alwaysThinkingEnabled"], False)
        self.assertEqual(kwargs["env"]["AGENT_ROUTER_NESTED"], "1")
        self.assertEqual(kwargs["timeout"], 4)

    def test_task_text_goes_to_stdin_not_argv(self):
        runner = FakeRunner(cli_output('{"tier": "low"}'))
        classify(runner, description="Find usages", prompt="SECRET-PROMPT-BODY")
        args, kwargs = runner.calls[0]
        self.assertNotIn("SECRET-PROMPT-BODY", " ".join(args))
        self.assertIn("SECRET-PROMPT-BODY", kwargs["input"])
        self.assertIn("Find usages", kwargs["input"])

    def test_long_prompt_is_truncated(self):
        runner = FakeRunner(cli_output('{"tier": "low"}'))
        classify(runner, prompt="x" * 50_000)
        _args, kwargs = runner.calls[0]
        self.assertLess(len(kwargs["input"]), 10_000)

    def test_non_string_inputs_are_safe(self):
        runner = FakeRunner(cli_output('{"tier": "low"}'))
        result = classifier.classify(
            subagent_type=None,
            description=None,
            prompt=None,
            config=cfg(),
            runner=runner,
            which=which_found,
        )
        self.assertTrue(result.ok)

    def test_bad_timeout_config_falls_back(self):
        runner = FakeRunner(cli_output('{"tier": "low"}'))
        classify(runner, config=cfg(timeoutSeconds="soon"))
        self.assertEqual(runner.calls[0][1]["timeout"], 6)


if __name__ == "__main__":
    unittest.main()
