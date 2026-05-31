import unittest

import _path  # noqa: F401

from hud import bars
from hud.colors import strip_ansi


class TestBars(unittest.TestCase):
    def test_all_styles_render_correct_width(self):
        for style in bars.available_styles():
            bar = strip_ansi(bars.render_bar(50, width=10, style=style))
            # bracketed styles add two characters
            expected = 12 if style in {"equals", "hash", "ascii"} else 10
            self.assertEqual(len(bar), expected, f"style={style}")

    def test_fill_proportional(self):
        bar = strip_ansi(bars.render_bar(50, width=10, style="blocks"))
        self.assertEqual(bar.count("█"), 5)
        self.assertEqual(bar.count("░"), 5)

    def test_zero_and_full(self):
        empty = strip_ansi(bars.render_bar(0, width=8, style="blocks"))
        full = strip_ansi(bars.render_bar(100, width=8, style="blocks"))
        self.assertEqual(empty.count("█"), 0)
        self.assertEqual(full.count("█"), 8)

    def test_clamp_out_of_range(self):
        self.assertEqual(strip_ansi(bars.render_bar(-50, 6, "blocks")).count("█"), 0)
        self.assertEqual(strip_ansi(bars.render_bar(500, 6, "blocks")).count("█"), 6)

    def test_unknown_style_falls_back_to_rounded(self):
        bar = strip_ansi(bars.render_bar(100, width=5, style="does-not-exist"))
        self.assertEqual(bar, "▰" * 5)

    def test_smooth_uses_partial_cell(self):
        # 5% of a 1-cell bar -> a fractional eighth glyph, not empty/full
        bar = strip_ansi(bars.render_bar(50, width=2, style="smooth"))
        self.assertEqual(len(bar), 2)
        self.assertIn("█", bar)

    def test_braille(self):
        bar = strip_ansi(bars.render_bar(100, width=4, style="braille"))
        self.assertEqual(bar, "⣿" * 4)

    def test_custom_glyph_override(self):
        bar = strip_ansi(bars.render_bar(100, width=3, style="blocks",
                                         filled_char="#", empty_char="."))
        self.assertEqual(bar, "###")

    def test_bracketed_style_has_brackets(self):
        bar = strip_ansi(bars.render_bar(50, width=4, style="equals"))
        self.assertTrue(bar.startswith("[") and bar.endswith("]"))


if __name__ == "__main__":
    unittest.main()
