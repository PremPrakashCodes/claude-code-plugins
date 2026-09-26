import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _path  # noqa: F401
from agent_router import cli
from agent_router import config as config_mod
from agent_router import eval as eval_mod
from agent_router.classifier import ClassifierResult

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden.jsonl"


def cfg():
    return config_mod._deep_merge(config_mod.DEFAULTS, {})


def fixture(fid, expected, description="d"):
    return {
        "id": fid,
        "subagent_type": "general-purpose",
        "description": description,
        "prompt": "p",
        "expected_tier": expected,
    }


def answers(mapping):
    """A fake classifier answering by description; None means failure."""

    def fake(subagent_type, description, prompt, config):
        tier = mapping.get(description)
        if tier is None:
            return ClassifierResult(ok=False, reason="timeout")
        return ClassifierResult(ok=True, tier=tier, confidence=0.9, cost_usd=0.004)

    return fake


class TestLoadGolden(unittest.TestCase):
    def test_malformed_lines_are_skipped_with_warning(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "g.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps(fixture("a", "low")),
                        "not json",
                        json.dumps({"id": "b", "expected_tier": "extreme"}),
                        "",
                        "# comment",
                        json.dumps(fixture("c", "high")),
                    ]
                ),
                encoding="utf-8",
            )
            fixtures, warnings = eval_mod.load_golden(path)
        self.assertEqual([f["id"] for f in fixtures], ["a", "c"])
        self.assertEqual(len(warnings), 2)

    def test_shipped_golden_set_is_valid_and_covers_every_tier(self):
        fixtures, warnings = eval_mod.load_golden(GOLDEN)
        self.assertEqual(warnings, [])
        self.assertGreaterEqual(len(fixtures), 15)
        tiers = {f["expected_tier"] for f in fixtures}
        self.assertEqual(tiers, set(config_mod.TIERS))
        self.assertEqual(len({f["id"] for f in fixtures}), len(fixtures))


class TestRun(unittest.TestCase):
    def test_all_correct(self):
        fixtures = [fixture("a", "low", "x"), fixture("b", "high", "y")]
        result = eval_mod.run(fixtures, cfg(), classify=answers({"x": "low", "y": "high"}))
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["failures"], [])
        self.assertAlmostEqual(result["classifier_cost_usd"], 0.008)

    def test_confusion_counts_disagreements(self):
        fixtures = [fixture("a", "low", "x"), fixture("b", "high", "y"), fixture("c", "mid", "z")]
        result = eval_mod.run(
            fixtures, cfg(), classify=answers({"x": "low", "y": "mid", "z": "mid"})
        )
        self.assertAlmostEqual(result["accuracy"], 2 / 3)
        self.assertEqual(result["confusion"]["high"], {"mid": 1})
        self.assertEqual(result["confusion"]["low"], {"low": 1})

    def test_low_confidence_answers_are_scored_after_adjustment(self):
        def fake(subagent_type, description, prompt, config):
            return ClassifierResult(ok=True, tier="low", confidence=0.3)

        result = eval_mod.run([fixture("a", "mid", "x")], cfg(), classify=fake)
        self.assertEqual(result["accuracy"], 1.0)  # routed low -> mid
        self.assertEqual(result["classifier_accuracy"], 0.0)
        self.assertEqual(result["under_routed"], 0)

    def test_under_routing_is_counted(self):
        result = eval_mod.run([fixture("a", "high", "x")], cfg(), classify=answers({"x": "low"}))
        self.assertEqual(result["under_routed"], 1)

    def test_classifier_failure_is_a_miss(self):
        result = eval_mod.run([fixture("a", "low", "x")], cfg(), classify=answers({}))
        self.assertEqual(result["accuracy"], 0.0)
        self.assertEqual(result["failures"], [{"id": "a", "reason": "timeout"}])
        self.assertEqual(result["confusion"]["low"], {"failed": 1})

    def test_empty_set(self):
        result = eval_mod.run([], cfg(), classify=answers({}))
        self.assertEqual(result["accuracy"], 0.0)


class TestEvalCommand(unittest.TestCase):
    def _run(self, args, mapping, fixtures):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "g.jsonl"
            path.write_text("\n".join(json.dumps(f) for f in fixtures), encoding="utf-8")
            out = io.StringIO()
            with mock.patch.object(eval_mod, "classify_fn", lambda: answers(mapping)):
                with mock.patch("sys.stdout", out), mock.patch("sys.stderr", io.StringIO()):
                    code = cli.main(["eval", "--golden", str(path), *args])
        return code, out.getvalue()

    def test_passes_floor(self):
        code, out = self._run([], {"x": "low"}, [fixture("a", "low", "x")])
        self.assertEqual(code, 0)
        self.assertIn("100.0%", out)

    def test_fails_below_floor(self):
        fixtures = [fixture("a", "low", "x"), fixture("b", "high", "y")]
        code, _ = self._run([], {"x": "low", "y": "low"}, fixtures)
        self.assertEqual(code, 1)

    def test_floor_is_configurable(self):
        fixtures = [fixture("a", "low", "x"), fixture("b", "high", "y")]
        code, _ = self._run(["--floor", "0.5"], {"x": "low", "y": "low"}, fixtures)
        self.assertEqual(code, 0)

    def test_json_output(self):
        code, out = self._run(["--json"], {"x": "low"}, [fixture("a", "low", "x")])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
