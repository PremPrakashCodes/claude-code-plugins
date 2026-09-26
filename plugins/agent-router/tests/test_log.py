import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import _path  # noqa: F401
from agent_router import config as config_mod
from agent_router import log


def cfg(**log_overrides):
    return config_mod._deep_merge(config_mod.DEFAULTS, {"log": log_overrides})


class TestPaths(unittest.TestCase):
    def test_plugin_data_env_wins(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": "/data/ar"}):
            self.assertEqual(log.data_dir(), Path("/data/ar"))
            self.assertEqual(log.log_path(), Path("/data/ar/log.jsonl"))

    def test_fallback_to_config_dir(self):
        env = {"CLAUDE_CONFIG_DIR": "/cfg"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("CLAUDE_PLUGIN_DATA", None)
            self.assertEqual(log.data_dir(), Path("/cfg/plugins/data/agent-router"))


class TestAppendAndRead(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "log.jsonl"
            record = {"kind": "decision", "tier": "low", "confidence": 0.9, "signals": {"a": 1}}
            self.assertTrue(log.append(record, cfg(), path=path))
            self.assertEqual(list(log.read_records(path)), [record])

    def test_bad_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            path.write_text('{"ok": 1}\nnot json\n[1]\n{"ok": 2}\n', encoding="utf-8")
            self.assertEqual(list(log.read_records(path)), [{"ok": 1}, {"ok": 2}])

    def test_missing_log_reads_empty(self):
        self.assertEqual(list(log.read_records(Path("/no/such/log.jsonl"))), [])

    def test_unwritable_path_is_silently_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            blocker = Path(d) / "file"
            blocker.write_text("x")
            # a regular file where the directory should be
            self.assertFalse(log.append({"a": 1}, cfg(), path=blocker / "log.jsonl"))

    def test_unserializable_record_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            self.assertFalse(log.append({"a": object()}, cfg(), path=path))
            self.assertFalse(path.exists())


class TestRotation(unittest.TestCase):
    def _fill(self, path, n, config):
        for i in range(n):
            log.append({"i": i, "pad": "x" * 80}, config, path=path)

    def test_rotates_past_cap_and_keeps_segments(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            config = cfg(maxBytes=500, keepSegments=2)
            self._fill(path, 40, config)
            names = sorted(p.name for p in Path(d).glob("log*.jsonl"))
            self.assertEqual(names, ["log.1.jsonl", "log.2.jsonl", "log.jsonl"])
            self.assertLessEqual(path.stat().st_size, 500 + 200)
            records = list(log.read_records(path))
            # oldest records were dropped; newest survive, in order
            self.assertEqual(records[-1]["i"], 39)
            self.assertGreater(records[0]["i"], 0)
            self.assertEqual([r["i"] for r in records], sorted(r["i"] for r in records))

    def test_live_only_read_skips_rotated_segments(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            self._fill(path, 40, cfg(maxBytes=500, keepSegments=5))
            live = list(log.read_records(path, include_rotated=False))
            everything = list(log.read_records(path))
            self.assertLess(len(live), len(everything))
            self.assertEqual(live, everything[-len(live) :])

    def test_configured_cap_changes_pruning_point(self):
        with tempfile.TemporaryDirectory() as small, tempfile.TemporaryDirectory() as big:
            self._fill(Path(small) / "log.jsonl", 40, cfg(maxBytes=500, keepSegments=1))
            self._fill(Path(big) / "log.jsonl", 40, cfg(maxBytes=5000, keepSegments=1))
            kept_small = len(list(log.read_records(Path(small) / "log.jsonl")))
            kept_big = len(list(log.read_records(Path(big) / "log.jsonl")))
            self.assertLess(kept_small, kept_big)
            self.assertEqual(kept_big, 40)

    def test_default_cap_is_documented_value(self):
        self.assertEqual(config_mod.DEFAULTS["log"]["maxBytes"], 5_000_000)

    def test_invalid_log_config_uses_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            self.assertTrue(log.append({"a": 1}, cfg(maxBytes="big", keepSegments=-3), path=path))

    def test_concurrent_appenders_across_rotation(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            config = cfg(maxBytes=2000, keepSegments=1000)

            def worker(w):
                for i in range(50):
                    log.append({"w": w, "i": i, "pad": "y" * 60}, config, path=path)

            threads = [threading.Thread(target=worker, args=(w,)) for w in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            raw_lines = []
            for seg in Path(d).glob("log*.jsonl"):
                raw_lines.extend(seg.read_text(encoding="utf-8").splitlines())
            parsed = [json.loads(line) for line in raw_lines]  # no truncated lines
            self.assertEqual(len(parsed), 400)
            self.assertEqual(len({(r["w"], r["i"]) for r in parsed}), 400)


if __name__ == "__main__":
    unittest.main()
