import unittest
from unittest import mock

import _path  # noqa: F401
from hud import config as config_mod
from hud import data as data_mod
from hud import render as render_mod
from hud.colors import strip_ansi

FIXED_NOW = 1_700_000_000.0


def build_config(**override):
    return config_mod._deep_merge(config_mod.DEFAULTS, override)


def render(payload, config):
    theme = config_mod.resolve_theme(config)
    data = data_mod.parse(payload)
    return render_mod.render(data, config, theme)


def visible(payload, config):
    with mock.patch.object(render_mod.time, "time", return_value=FIXED_NOW):
        return strip_ansi(render(payload, config))


# A path that exists nowhere -> git segment is deterministically skipped,
# while the project segment still shows the basename "claude".
NON_REPO_CWD = "/Users/you/Projects/claude"


def screenshot_payload():
    return {
        "model": {"display_name": "Opus 4.8 (1M context)"},
        "workspace": {"current_dir": NON_REPO_CWD},
        "context_window": {
            "context_window_size": 1_000_000,
            "current_usage": {
                "input_tokens": 20_000,
                "cache_creation_input_tokens": 6_000,
                "cache_read_input_tokens": 60_000,
            },
        },
        "rate_limits": {
            "five_hour": {"used_percentage": 6, "resets_at": FIXED_NOW + 8220},
            "seven_day": {"used_percentage": 44, "resets_at": FIXED_NOW + 280800},
        },
    }


class TestRender(unittest.TestCase):
    def test_screenshot_parity(self):
        line = visible(screenshot_payload(), build_config())
        self.assertEqual(
            line,
            "[Opus 4.8] | claude | ctx ▰▱▱▱▱▱▱▱▱▱ 86k/1.0M | 5h: 6% (2h 17m) | 7d: 44% (3d 6h)",
        )

    def test_model_short_strips_parenthetical(self):
        line = visible(screenshot_payload(), build_config(segments=["model"]))
        self.assertEqual(line, "[Opus 4.8]")

    def test_model_full_keeps_display_name(self):
        cfg = build_config(segments=["model"], model={"format": "full"})
        self.assertEqual(visible(screenshot_payload(), cfg), "[Opus 4.8 (1M context)]")

    def test_model_without_brackets(self):
        cfg = build_config(segments=["model"], model={"brackets": False})
        self.assertEqual(visible(screenshot_payload(), cfg), "Opus 4.8")

    def test_weekly_relabel(self):
        cfg = build_config(segments=["usage"], usage={"labels": {"7d": "weekly"}})
        line = visible(screenshot_payload(), cfg)
        self.assertIn("weekly: 44%", line)
        self.assertNotIn("7d:", line)

    def test_context_percent_mode(self):
        cfg = build_config(segments=["context"], context={"value": "percent"})
        self.assertEqual(
            visible(screenshot_payload(), cfg),
            "ctx ▰▱▱▱▱▱▱▱▱▱ 9%",
        )

    def test_context_both_mode(self):
        cfg = build_config(segments=["context"], context={"value": "both"})
        self.assertEqual(
            visible(screenshot_payload(), cfg),
            "ctx ▰▱▱▱▱▱▱▱▱▱ 86k/1.0M 9%",
        )

    def test_context_no_bar(self):
        cfg = build_config(segments=["context"], context={"bar": False, "value": "tokens"})
        self.assertEqual(visible(screenshot_payload(), cfg), "ctx 86k/1.0M")

    def test_usage_remaining_mode(self):
        cfg = build_config(
            segments=["usage"], usage={"value": "remaining", "windows": ["5h"], "showReset": False}
        )
        self.assertEqual(visible(screenshot_payload(), cfg), "5h: 94%")

    def test_segment_order_respected(self):
        cfg = build_config(segments=["context", "model"], context={"value": "percent"})
        line = visible(screenshot_payload(), cfg)
        self.assertTrue(line.startswith("ctx "))
        self.assertTrue(line.endswith("[Opus 4.8]"))

    def test_git_skipped_for_non_repo(self):
        line = visible(screenshot_payload(), build_config())
        self.assertNotIn("git:(", line)

    def test_expanded_layout_one_segment_per_line(self):
        cfg = build_config(
            layout="expanded", segments=["model", "context"], context={"value": "percent"}
        )
        lines = visible(screenshot_payload(), cfg).split("\n")
        self.assertEqual(lines, ["[Opus 4.8]", "ctx ▰▱▱▱▱▱▱▱▱▱ 9%"])

    def test_cost_and_session_segments(self):
        payload = screenshot_payload()
        payload["cost"] = {
            "total_cost_usd": 0.42,
            "total_duration_ms": 8220 * 1000,
            "total_lines_added": 10,
            "total_lines_removed": 3,
        }
        cfg = build_config(
            segments=["cost", "session"], session={"showDuration": True, "showLines": True}
        )
        line = visible(payload, cfg)
        self.assertEqual(line, "$0.42 | 2h 17m | +10 -3")

    def test_custom_separator(self):
        cfg = build_config(
            segments=["model", "context"], separator=" · ", context={"value": "percent"}
        )
        self.assertIn(" · ", visible(screenshot_payload(), cfg))

    def test_empty_payload_does_not_crash(self):
        line = visible({}, build_config())
        self.assertIsInstance(line, str)
        self.assertIn("ctx", line)

    def test_truncate_drops_trailing_cells(self):
        import os

        cfg = build_config()
        old = os.environ.get("COLUMNS")
        os.environ["COLUMNS"] = "20"
        try:
            line = visible(screenshot_payload(), cfg)
        finally:
            if old is None:
                os.environ.pop("COLUMNS", None)
            else:
                os.environ["COLUMNS"] = old
        # first cell always kept; overall width within the limit
        self.assertTrue(line.startswith("[Opus 4.8]"))
        self.assertLessEqual(len(line), 20 + len(" | "))

    def test_unknown_segment_ignored(self):
        cfg = build_config(segments=["model", "bogus", "context"], context={"value": "percent"})
        line = visible(screenshot_payload(), cfg)
        self.assertEqual(line, "[Opus 4.8] | ctx ▰▱▱▱▱▱▱▱▱▱ 9%")


if __name__ == "__main__":
    unittest.main()
