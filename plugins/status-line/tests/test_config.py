import json
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from hud import config as config_mod


class TestConfig(unittest.TestCase):
    def test_deep_merge_nested(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 9, "z": 4}}
        merged = config_mod._deep_merge(base, override)
        self.assertEqual(merged, {"a": {"x": 1, "y": 9, "z": 4}, "b": 3})
        # original untouched
        self.assertEqual(base["a"], {"x": 1, "y": 2})

    def test_load_missing_file_returns_defaults(self):
        cfg = config_mod.load(Path("/nonexistent/whatever.json"))
        self.assertEqual(cfg["theme"], "default")
        self.assertEqual(cfg["segments"], ["model", "project", "git", "context", "usage"])

    def test_load_merges_partial_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(
                json.dumps(
                    {
                        "theme": "nord",
                        "usage": {"labels": {"7d": "weekly"}},
                    }
                ),
                encoding="utf-8",
            )
            cfg = config_mod.load(p)
        self.assertEqual(cfg["theme"], "nord")
        self.assertEqual(cfg["usage"]["labels"]["7d"], "weekly")
        # untouched nested defaults survive the merge
        self.assertEqual(cfg["usage"]["labels"]["5h"], "5h")
        self.assertEqual(cfg["context"]["barStyle"], "rounded")

    def test_load_invalid_json_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text("{ not valid json ", encoding="utf-8")
            cfg = config_mod.load(p)
        self.assertEqual(cfg["theme"], "default")

    def test_resolve_theme_overrides(self):
        cfg = config_mod.load(Path("/nope.json"))
        cfg["theme"] = "default"
        cfg["colors"] = {"project": "#ff8800"}
        theme = config_mod.resolve_theme(cfg)
        self.assertEqual(theme["project"], "#ff8800")
        # other roles come from the base theme
        self.assertEqual(theme["model"], "cyan")

    def test_presets_exist_and_shaped(self):
        for name in ("minimal", "essential", "full"):
            self.assertIn(name, config_mod.PRESETS)
            self.assertIn("segments", config_mod.PRESETS[name])

    def test_config_path_respects_env(self):
        import os

        old = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = "/tmp/xyz"
        try:
            p = config_mod.config_path()
            self.assertEqual(str(p), "/tmp/xyz/plugins/status-line/config.json")
        finally:
            if old is None:
                del os.environ["CLAUDE_CONFIG_DIR"]
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old

    def test_shipped_config_matches_defaults(self):
        """The bundled config.json must stay in sync with DEFAULTS."""
        shipped = Path(__file__).resolve().parent.parent / "config.json"
        loaded = json.loads(shipped.read_text(encoding="utf-8"))
        merged = config_mod._deep_merge(config_mod.DEFAULTS, loaded)
        self.assertEqual(merged, config_mod._deep_merge(config_mod.DEFAULTS, config_mod.DEFAULTS))


if __name__ == "__main__":
    unittest.main()
