import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _path  # noqa: F401
from agent_router import cli, log, summary
from agent_router import config as config_mod


def cfg():
    return config_mod._deep_merge(config_mod.DEFAULTS, {})


class SummaryCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patcher = mock.patch.dict(
            os.environ,
            {"CLAUDE_CONFIG_DIR": str(self.root), "CLAUDE_PLUGIN_DATA": str(self.root / "data")},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def read_summary(self):
        return json.loads(summary.summary_path().read_text(encoding="utf-8"))


class TestUpdate(SummaryCase):
    def test_path_is_fixed_under_config_dir(self):
        # status-line reads this exact path; keep them in sync
        self.assertEqual(
            summary.summary_path(), self.root / "plugins" / "agent-router" / "summary.json"
        )

    def test_writes_session_entry(self):
        self.assertTrue(summary.update("s1", routed=3, net_savings_usd=0.4567))
        data = self.read_summary()
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["sessions"]["s1"]["routed"], 3)
        self.assertAlmostEqual(data["sessions"]["s1"]["net_savings_usd"], 0.4567)

    def test_keeps_other_sessions_and_overwrites_same(self):
        summary.update("s1", routed=1, net_savings_usd=0.1)
        summary.update("s2", routed=2, net_savings_usd=0.2)
        summary.update("s1", routed=5, net_savings_usd=0.5)
        sessions = self.read_summary()["sessions"]
        self.assertEqual(sessions["s1"]["routed"], 5)
        self.assertEqual(sessions["s2"]["routed"], 2)

    def test_prunes_to_most_recent_sessions(self):
        with mock.patch.object(summary, "MAX_SESSIONS", 3):
            for i in range(6):
                with mock.patch("time.time", return_value=1000.0 + i):
                    summary.update(f"s{i}", routed=1, net_savings_usd=0.0)
        self.assertEqual(sorted(self.read_summary()["sessions"]), ["s3", "s4", "s5"])

    def test_concurrent_updates_keep_every_session(self):
        import threading

        def worker(i):
            for _ in range(5):
                summary.update(f"s{i}", routed=i, net_savings_usd=0.0)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(self.read_summary()["sessions"]), 8)

    def test_corrupt_file_is_replaced(self):
        path = summary.summary_path()
        path.parent.mkdir(parents=True)
        path.write_text("{ nope", encoding="utf-8")
        self.assertTrue(summary.update("s1", routed=1, net_savings_usd=0.0))
        self.assertIn("s1", self.read_summary()["sessions"])

    def test_unwritable_location_returns_false(self):
        (self.root / "plugins").write_text("a file, not a directory")
        self.assertFalse(summary.update("s1", routed=1, net_savings_usd=0.0))

    def test_empty_session_id_is_ignored(self):
        self.assertFalse(summary.update("", routed=1, net_savings_usd=0.0))


def run_stop(session_id):
    stdin = io.StringIO(json.dumps({"hook_event_name": "Stop", "session_id": session_id}))
    with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", io.StringIO()):
        return cli.main(["record-outcome"])


class TestStopHook(SummaryCase):
    def _decision(self, session_id, tool_use_id, action="rewrite"):
        return {
            "kind": "decision",
            "session_id": session_id,
            "tool_use_id": tool_use_id,
            "source": "LLM",
            "action": action,
            "tier": "low",
            "model": "haiku",
            "baseline_model": "claude-opus-5",
            "classifier": {"cost_usd": 0.004, "duration_ms": 2500, "usage": {}},
        }

    def test_stop_writes_this_sessions_summary(self):
        transcript = self.root / "agent.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": "2026-09-27T10:00:00Z",
                    "message": {
                        "id": "m1",
                        "model": "claude-haiku-4-5",
                        "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        for record in (
            self._decision("s1", "t1"),
            self._decision("s1", "t2", action="kept"),
            self._decision("other", "t9"),
            {"kind": "link", "session_id": "s1", "agent_id": "a1", "tool_use_id": "t1"},
            {
                "kind": "subagent_stop",
                "session_id": "s1",
                "agent_id": "a1",
                "transcript": str(transcript),
            },
        ):
            log.append(record, cfg())
        self.assertEqual(run_stop("s1"), 0)
        entry = json.loads(summary.summary_path().read_text())["sessions"]["s1"]
        self.assertEqual(entry["routed"], 1)
        # 1M input tokens: opus $5.00 - haiku $1.00 - two classifier calls $0.008
        self.assertAlmostEqual(entry["net_savings_usd"], 3.992)
        self.assertNotIn("other", json.loads(summary.summary_path().read_text())["sessions"])

    def test_stop_counts_decisions_in_newest_rotated_segment(self):
        config = config_mod._deep_merge(cfg(), {"log": {"maxBytes": 300, "keepSegments": 3}})
        log.append(self._decision("s1", "t1"), config)
        for i in range(3):  # other sessions' traffic pushes s1 into log.1.jsonl
            log.append(self._decision("other", f"x{i}"), config)
        with mock.patch.object(cli.config_mod, "load", lambda: config):
            self.assertEqual(run_stop("s1"), 0)
        entry = json.loads(summary.summary_path().read_text())["sessions"]["s1"]
        self.assertEqual(entry["routed"], 1)

    def test_stop_without_decisions_writes_nothing(self):
        self.assertEqual(run_stop("s1"), 0)
        self.assertFalse(summary.summary_path().exists())


if __name__ == "__main__":
    unittest.main()
