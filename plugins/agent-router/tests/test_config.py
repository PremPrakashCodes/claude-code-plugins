import json
import os
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from agent_router import config as config_mod


class TestConfig(unittest.TestCase):
    def test_load_missing_file_returns_defaults(self):
        cfg = config_mod.load(Path("/nonexistent/whatever.json"))
        self.assertEqual(cfg, config_mod.DEFAULTS)
        self.assertEqual(cfg["tiers"], {"low": "haiku", "mid": "sonnet", "high": "opus"})
        self.assertEqual(cfg["rules"]["threshold"], 0.7)
        self.assertTrue(cfg["classifier"]["enabled"])
        self.assertEqual(cfg["classifier"]["model"], "haiku")
        self.assertEqual(cfg["log"]["maxBytes"], 5_000_000)

    def test_partial_config_deep_merges(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps({"tiers": {"low": "sonnet"}, "rules": {"threshold": 0.5}}))
            cfg = config_mod.load(p)
        self.assertEqual(cfg["tiers"], {"low": "sonnet", "mid": "sonnet", "high": "opus"})
        self.assertEqual(cfg["rules"]["threshold"], 0.5)
        # untouched nested defaults survive
        self.assertEqual(cfg["classifier"]["timeoutSeconds"], 6)

    def test_malformed_json_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text("{ not json")
            self.assertEqual(config_mod.load(p), config_mod.DEFAULTS)

    def test_non_object_json_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text("[1, 2, 3]")
            self.assertEqual(config_mod.load(p), config_mod.DEFAULTS)

    def test_unknown_keys_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps({"futureKey": {"x": 1}}))
            cfg = config_mod.load(p)
        self.assertEqual(cfg["futureKey"], {"x": 1})

    def test_classifier_settings_are_configurable(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps({"classifier": {"enabled": False, "model": "sonnet"}}))
            cfg = config_mod.load(p)
        self.assertFalse(cfg["classifier"]["enabled"])
        self.assertEqual(cfg["classifier"]["model"], "sonnet")

    def test_config_path_respects_env(self):
        old = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = "/tmp/xyz"
        try:
            self.assertEqual(
                str(config_mod.config_path()), "/tmp/xyz/plugins/agent-router/config.json"
            )
        finally:
            if old is None:
                del os.environ["CLAUDE_CONFIG_DIR"]
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old

    def test_tier_model_lookup(self):
        cfg = config_mod.load(Path("/nope.json"))
        self.assertEqual(config_mod.tier_model(cfg, "low"), "haiku")
        self.assertIsNone(config_mod.tier_model(cfg, "bogus"))
        cfg["tiers"]["low"] = ""
        self.assertIsNone(config_mod.tier_model(cfg, "low"))

    def test_shipped_config_matches_defaults(self):
        """The bundled config.json must stay in sync with DEFAULTS."""
        shipped = Path(__file__).resolve().parent.parent / "config.json"
        loaded = json.loads(shipped.read_text(encoding="utf-8"))
        self.assertEqual(config_mod._deep_merge(config_mod.DEFAULTS, loaded), config_mod.DEFAULTS)
        self.assertEqual(loaded, config_mod.DEFAULTS)


if __name__ == "__main__":
    unittest.main()
