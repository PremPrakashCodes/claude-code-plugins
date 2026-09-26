import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _path  # noqa: F401
from agent_router import adaptive, tiers
from agent_router import config as config_mod


def cfg(**overrides):
    return config_mod._deep_merge(config_mod.DEFAULTS, overrides)


def decision(tool_use_id, ts=0.0, session="s1", subagent="Explore", task="k1", tier="low"):
    return {
        "kind": "decision",
        "tool_use_id": tool_use_id,
        "ts": ts,
        "session_id": session,
        "subagent_type": subagent,
        "task_key": task,
        "action": "rewrite",
        "tier": tier,
    }


def outcome(tool_use_id, result_chars=500):
    return {"kind": "outcome", "tool_use_id": tool_use_id, "result_chars": result_chars}


class TestConfidenceAdjustment(unittest.TestCase):
    def test_low_confidence_routes_one_tier_up(self):
        self.assertEqual(tiers.confidence_adjusted("low", 0.5, cfg()), ("mid", ["low_confidence"]))
        self.assertEqual(
            tiers.confidence_adjusted("mid", 0.69, cfg()), ("high", ["low_confidence"])
        )

    def test_missing_confidence_is_treated_as_low(self):
        self.assertEqual(tiers.confidence_adjusted("low", None, cfg()), ("mid", ["low_confidence"]))

    def test_confident_answer_is_kept(self):
        self.assertEqual(tiers.confidence_adjusted("low", 0.7, cfg()), ("low", []))
        self.assertEqual(tiers.confidence_adjusted("low", 0.95, cfg()), ("low", []))

    def test_high_stays_high(self):
        self.assertEqual(tiers.confidence_adjusted("high", 0.1, cfg()), ("high", []))

    def test_threshold_is_configurable(self):
        config = cfg(classifier={"minConfidence": 0.9})
        self.assertEqual(tiers.confidence_adjusted("low", 0.85, config)[0], "mid")
        config = cfg(classifier={"minConfidence": 0})
        self.assertEqual(tiers.confidence_adjusted("low", 0.0, config)[0], "low")

    def test_bad_threshold_uses_default(self):
        config = cfg(classifier={"minConfidence": "high"})
        self.assertEqual(tiers.confidence_adjusted("low", 0.5, config)[0], "mid")


class TestQualityIssues(unittest.TestCase):
    def test_short_result_is_an_issue(self):
        records = [decision("t1"), outcome("t1", result_chars=3)]
        self.assertEqual(adaptive.quality_issues(records, cfg()), {"t1": ["short_result"]})

    def test_normal_result_has_no_issue(self):
        records = [decision("t1"), outcome("t1", result_chars=400)]
        self.assertEqual(adaptive.quality_issues(records, cfg()), {"t1": []})

    def test_redispatch_of_same_task_within_window(self):
        records = [
            decision("t1", ts=100),
            decision("t2", ts=400),
            outcome("t1"),
            outcome("t2"),
        ]
        issues = adaptive.quality_issues(records, cfg())
        self.assertEqual(issues["t1"], ["redispatched"])
        self.assertEqual(issues["t2"], [])

    def test_redispatch_outside_window_or_other_session_is_not_an_issue(self):
        records = [
            decision("t1", ts=100),
            decision("t2", ts=100 + 901),
            decision("t3", ts=110, session="s2"),
            outcome("t1"),
        ]
        self.assertEqual(adaptive.quality_issues(records, cfg())["t1"], [])

    def test_dispatches_without_outcome_are_not_judged(self):
        self.assertEqual(adaptive.quality_issues([decision("t1")], cfg()), {})


class TestEscalation(unittest.TestCase):
    def _records(self, total, bad):
        records = []
        for i in range(total):
            records.append(decision(f"t{i}", task=f"k{i}"))
            records.append(outcome(f"t{i}", result_chars=0 if i < bad else 300))
        return records

    def test_compute_groups_by_type_and_tier(self):
        stats = adaptive.compute(self._records(6, 3), cfg())
        self.assertEqual(stats["groups"]["Explore|low"], {"outcomes": 6, "issues": 3})

    def test_escalates_at_issue_rate_with_enough_samples(self):
        stats = adaptive.compute(self._records(5, 2), cfg())
        self.assertTrue(adaptive.is_escalated(stats, "Explore", "low", cfg()))

    def test_not_escalated_below_rate_or_samples(self):
        self.assertFalse(
            adaptive.is_escalated(
                adaptive.compute(self._records(5, 1), cfg()), "Explore", "low", cfg()
            )
        )
        self.assertFalse(
            adaptive.is_escalated(
                adaptive.compute(self._records(4, 4), cfg()), "Explore", "low", cfg()
            )
        )

    def test_disabled_never_escalates(self):
        stats = adaptive.compute(self._records(5, 5), cfg())
        self.assertFalse(
            adaptive.is_escalated(stats, "Explore", "low", cfg(adaptive={"enabled": False}))
        )

    def test_route_tier_applies_adaptive_after_confidence(self):
        stats = adaptive.compute(self._records(5, 5), cfg())
        self.assertEqual(
            tiers.route_tier("low", 0.95, "Explore", cfg(), stats), ("mid", ["adaptive"])
        )
        # other subagent types are unaffected
        self.assertEqual(tiers.route_tier("low", 0.95, "Plan", cfg(), stats), ("low", []))

    def test_malformed_stats_do_not_escalate(self):
        for stats in ({}, {"groups": "x"}, {"groups": {"Explore|low": {"outcomes": "5"}}}):
            self.assertFalse(adaptive.is_escalated(stats, "Explore", "low", cfg()))


class TestStatsFile(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": d}):
                stats = {"version": 1, "groups": {"Explore|low": {"outcomes": 5, "issues": 2}}}
                self.assertTrue(adaptive.save(stats))
                self.assertEqual(adaptive.load(), stats)
                self.assertEqual(adaptive.stats_path(), Path(d) / "adaptive.json")

    def test_missing_or_corrupt_file_loads_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "adaptive.json"
            self.assertEqual(adaptive.load(path), {})
            path.write_text("{ nope")
            self.assertEqual(adaptive.load(path), {})
            path.write_text(json.dumps([1]))
            self.assertEqual(adaptive.load(path), {})

    def test_unwritable_location_returns_false(self):
        with tempfile.TemporaryDirectory() as d:
            blocker = Path(d) / "file"
            blocker.write_text("x")
            self.assertFalse(adaptive.save({}, path=blocker / "adaptive.json"))


if __name__ == "__main__":
    unittest.main()
