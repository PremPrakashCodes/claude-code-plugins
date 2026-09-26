import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _path  # noqa: F401
from agent_router import cli, log, report
from agent_router import config as config_mod


def cfg():
    return config_mod._deep_merge(config_mod.DEFAULTS, {})


def decision(tool_use_id, source="LLM", action="rewrite", **fields):
    record = {
        "kind": "decision",
        "tool_use_id": tool_use_id,
        "source": source,
        "action": action,
        "classifier": {"cost_usd": 0.004, "duration_ms": 2500, "usage": {}},
    }
    if source == "override":
        del record["classifier"]  # overrides never call the classifier
    record.update(fields)
    return record


def outcome(tool_use_id, model, inp, out, cache_read=0, duration_ms=5000):
    return {
        "kind": "outcome",
        "tool_use_id": tool_use_id,
        "agent_id": f"a-{tool_use_id}",
        "model": model,
        "usage": {
            "input_tokens": inp,
            "output_tokens": out,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": 0,
        },
        "duration_ms": duration_ms,
    }


class TestCost(unittest.TestCase):
    def test_cost_uses_price_table(self):
        usage = {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000,
            "cache_creation_input_tokens": 1_000_000,
        }
        # haiku: 1 + 5 + 0.1 + 1.25
        self.assertAlmostEqual(report.usage_cost(usage, "claude-haiku-4-5", cfg()), 7.35)

    def test_unknown_model_has_no_cost(self):
        self.assertIsNone(report.usage_cost({"input_tokens": 10}, "gpt-5", cfg()))


class TestSummary(unittest.TestCase):
    def test_counts_and_net_savings(self):
        records = [
            decision("t1", tier="low", model="haiku", baseline_model="claude-opus-5"),
            outcome("t1", "claude-haiku-4-5", 1_000_000, 100_000),
            decision("t2", source="override", action="kept", override="dispatch"),
            decision("t3", source="fallback", action="kept", reason="timeout"),
            decision("t4", tier="high", action="kept", reason="no_upgrade"),
        ]
        summary = report.summarize(records, cfg())
        self.assertEqual(summary["decisions"], 4)
        self.assertEqual(summary["by_source"], {"LLM": 2, "override": 1, "fallback": 1})
        self.assertEqual(summary["rewrites"], 1)
        self.assertEqual(summary["rewrites_by_model"], {"haiku": 1})
        self.assertEqual(summary["fallback_reasons"], {"timeout": 1})
        # 3 classifier calls (LLM x2 + fallback) at $0.004
        self.assertAlmostEqual(summary["classifier_cost_usd"], 0.012)
        # actual haiku: 1.0 + 0.5 = 1.5; baseline opus: 5.0 + 2.5 = 7.5
        self.assertAlmostEqual(summary["routed_actual_cost_usd"], 1.5)
        self.assertAlmostEqual(summary["routed_baseline_cost_usd"], 7.5)
        self.assertAlmostEqual(summary["net_savings_usd"], 7.5 - 1.5 - 0.012)
        self.assertEqual(summary["routed_with_outcome"], 1)

    def test_empty_log(self):
        summary = report.summarize([], cfg())
        self.assertEqual(summary["decisions"], 0)
        self.assertEqual(summary["net_savings_usd"], 0.0)

    def test_rewrite_without_baseline_is_not_counted_as_savings(self):
        records = [decision("t1", model="haiku"), outcome("t1", "claude-haiku-4-5", 1000, 10)]
        summary = report.summarize(records, cfg())
        self.assertEqual(summary["routed_with_outcome"], 0)
        self.assertEqual(summary["rewrites_without_baseline"], 1)

    def test_format_is_readable(self):
        text = report.format_summary(report.summarize([decision("t1")], cfg()), cfg())
        self.assertIn("Routing decisions", text)
        self.assertIn("estimate", text.lower())


class TestReportCommand(unittest.TestCase):
    def test_report_resolves_pending_and_prints(self):
        with tempfile.TemporaryDirectory() as d:
            transcript = Path(d) / "agent.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": "2026-09-27T10:00:00Z",
                        "message": {
                            "id": "m1",
                            "model": "claude-haiku-4-5",
                            "usage": {"input_tokens": 100, "output_tokens": 5},
                        },
                    }
                )
                + "\n"
            )
            env = {"CLAUDE_PLUGIN_DATA": d, "CLAUDE_CONFIG_DIR": d}
            with mock.patch.dict(os.environ, env):
                for record in (
                    decision("t1", tier="low", model="haiku", baseline_model="claude-opus-5"),
                    {"kind": "link", "agent_id": "a1", "tool_use_id": "t1", "session_id": "s"},
                    {
                        "kind": "subagent_stop",
                        "agent_id": "a1",
                        "session_id": "s",
                        "transcript": str(transcript),
                    },
                ):
                    log.append(record, cfg())
                out = io.StringIO()
                with mock.patch("sys.stdout", out):
                    self.assertEqual(cli.main(["report", "--json"]), 0)
                summary = json.loads(out.getvalue())
                self.assertEqual(summary["routed_with_outcome"], 1)
                # the resolved outcome was persisted
                kinds = [r["kind"] for r in log.read_records()]
                self.assertIn("outcome", kinds)
                out = io.StringIO()
                with mock.patch("sys.stdout", out):
                    self.assertEqual(cli.main(["report"]), 0)
                self.assertIn("Routing decisions", out.getvalue())


if __name__ == "__main__":
    unittest.main()
