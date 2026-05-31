import unittest

import _path  # noqa: F401
from hud import data as data_mod


class TestData(unittest.TestCase):
    def test_full_payload(self):
        payload = {
            "model": {"id": "claude-opus-4-8", "display_name": "Opus 4.8 (1M context)"},
            "workspace": {"current_dir": "/x/y/proj", "project_dir": "/x/y"},
            "context_window": {
                "context_window_size": 1_000_000,
                "current_usage": {
                    "input_tokens": 20_000,
                    "cache_creation_input_tokens": 6_000,
                    "cache_read_input_tokens": 60_000,
                },
            },
            "cost": {
                "total_cost_usd": 0.42,
                "total_duration_ms": 1000,
                "total_lines_added": 5,
                "total_lines_removed": 2,
            },
            "rate_limits": {
                "five_hour": {"used_percentage": 6, "resets_at": 1000},
                "seven_day": {"used_percentage": 44, "resets_at": 2000},
            },
        }
        d = data_mod.parse(payload)
        self.assertEqual(d.model_display, "Opus 4.8 (1M context)")
        self.assertEqual(d.cwd, "/x/y/proj")
        self.assertEqual(d.context_window, 1_000_000)
        self.assertEqual(d.total_tokens, 86_000)
        self.assertAlmostEqual(d.context_percent, 8.6, places=3)
        self.assertEqual(d.cost_usd, 0.42)
        self.assertEqual(d.lines_added, 5)
        self.assertEqual(d.windows["5h"].used_percent, 6)
        self.assertEqual(d.windows["7d"].resets_at, 2000)

    def test_native_used_percentage_preferred(self):
        d = data_mod.parse(
            {
                "context_window": {
                    "context_window_size": 200_000,
                    "used_percentage": 73.5,
                    "current_usage": {"input_tokens": 1000},
                }
            }
        )
        self.assertAlmostEqual(d.context_percent, 73.5)

    def test_computed_percentage_when_no_native(self):
        d = data_mod.parse(
            {
                "context_window": {
                    "context_window_size": 200_000,
                    "current_usage": {"input_tokens": 100_000},
                }
            }
        )
        self.assertAlmostEqual(d.context_percent, 50.0)

    def test_cwd_falls_back_to_top_level(self):
        d = data_mod.parse({"cwd": "/a/b"})
        self.assertEqual(d.cwd, "/a/b")

    def test_default_window_size(self):
        d = data_mod.parse({})
        self.assertEqual(d.context_window, data_mod.DEFAULT_CONTEXT_WINDOW)
        self.assertEqual(d.total_tokens, 0)

    def test_empty_and_missing_fields(self):
        d = data_mod.parse({})
        self.assertEqual(d.model_display, "")
        self.assertIsNone(d.cost_usd)
        self.assertEqual(d.windows, {})

    def test_booleans_not_treated_as_numbers(self):
        d = data_mod.parse({"cost": {"total_cost_usd": True}})
        self.assertIsNone(d.cost_usd)


if __name__ == "__main__":
    unittest.main()
