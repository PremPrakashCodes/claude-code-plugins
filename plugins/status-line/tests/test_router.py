import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _path  # noqa: F401
from hud import config as config_mod
from hud import data as data_mod
from hud import render as render_mod
from hud import router as router_mod
from hud.colors import strip_ansi


def build_config(**overrides):
    return config_mod._deep_merge(config_mod.DEFAULTS, {"segments": ["router"], **overrides})


def visible(payload, config):
    theme = config_mod.resolve_theme(config)
    return strip_ansi(render_mod.render(data_mod.parse(payload), config, theme))


class RouterCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = Path(self.tmp.name) / "plugins" / "agent-router" / "summary.json"

    def write(self, content):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = content if isinstance(content, str) else json.dumps(content)
        self.path.write_text(text, encoding="utf-8")


class TestSummaryPath(RouterCase):
    def test_path_follows_config_dir(self):
        self.assertEqual(router_mod.summary_path(), self.path)


class TestRouterSegment(RouterCase):
    def test_renders_current_session(self):
        self.write(
            {
                "version": 1,
                "sessions": {
                    "s1": {"routed": 4, "net_savings_usd": 0.383},
                    "other": {"routed": 9, "net_savings_usd": 5.0},
                },
            }
        )
        line = visible({"session_id": "s1"}, build_config())
        self.assertEqual(line, "router: 4↓ $0.38 saved")

    def test_negative_savings_are_shown_honestly(self):
        self.write({"version": 1, "sessions": {"s1": {"routed": 1, "net_savings_usd": -0.004}}})
        self.assertEqual(visible({"session_id": "s1"}, build_config()), "router: 1↓ -$0.00 saved")

    def test_custom_label(self):
        self.write({"version": 1, "sessions": {"s1": {"routed": 2, "net_savings_usd": 1.5}}})
        cfg = build_config(router={"label": "routed"})
        self.assertEqual(visible({"session_id": "s1"}, cfg), "routed: 2↓ $1.50 saved")

    def test_hidden_without_summary_file(self):
        self.assertEqual(visible({"session_id": "s1"}, build_config()), "")

    def test_hidden_for_unknown_session_or_no_session_id(self):
        self.write({"version": 1, "sessions": {"s1": {"routed": 2, "net_savings_usd": 1.0}}})
        self.assertEqual(visible({"session_id": "s2"}, build_config()), "")
        self.assertEqual(visible({}, build_config()), "")

    def test_hidden_when_nothing_routed(self):
        self.write({"version": 1, "sessions": {"s1": {"routed": 0, "net_savings_usd": 0.0}}})
        self.assertEqual(visible({"session_id": "s1"}, build_config()), "")

    def test_malformed_summary_is_ignored(self):
        for content in ("{ nope", "[]", {"sessions": "x"}, {"sessions": {"s1": "x"}}):
            self.write(content)
            self.assertEqual(visible({"session_id": "s1"}, build_config()), "", content)

    def test_bad_numbers_are_ignored(self):
        self.write({"sessions": {"s1": {"routed": "four", "net_savings_usd": None}}})
        self.assertEqual(visible({"session_id": "s1"}, build_config()), "")

    def test_other_segments_unaffected_when_absent(self):
        cfg = build_config(segments=["model", "router"])
        line = visible({"session_id": "s1", "model": {"display_name": "Opus 5"}}, cfg)
        self.assertEqual(line, "[Opus 5]")


if __name__ == "__main__":
    unittest.main()
