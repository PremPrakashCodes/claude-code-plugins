import unittest

import _path  # noqa: F401  (sets up import path)

from hud import colors


class TestColors(unittest.TestCase):
    def test_named_color_wraps_with_reset(self):
        out = colors.colorize("hi", "green")
        self.assertTrue(out.startswith("\x1b[32m"))
        self.assertTrue(out.endswith(colors.RESET))
        self.assertIn("hi", out)

    def test_bright_color(self):
        self.assertEqual(colors.ansi("brightBlue"), "\x1b[94m")

    def test_256_color_from_int_and_str(self):
        self.assertEqual(colors.ansi(208), "\x1b[38;5;208m")
        self.assertEqual(colors.ansi("208"), "\x1b[38;5;208m")

    def test_hex_truecolor(self):
        self.assertEqual(colors.ansi("#ff8800"), "\x1b[38;2;255;136;0m")

    def test_combined_color_and_style(self):
        # order preserved: fg then style
        self.assertEqual(colors.ansi("yellow+underline"), "\x1b[33;4m")

    def test_list_spec(self):
        self.assertEqual(colors.ansi(["red", "bold"]), "\x1b[31;1m")

    def test_empty_spec_is_noop(self):
        self.assertEqual(colors.ansi(""), "")
        self.assertEqual(colors.ansi(None), "")
        self.assertEqual(colors.colorize("x", None), "x")

    def test_invalid_token_ignored(self):
        self.assertEqual(colors.ansi("notacolor"), "")
        self.assertEqual(colors.ansi("#zzzzzz"), "")
        self.assertEqual(colors.ansi("999"), "")  # out of 0-255 range

    def test_visible_len_ignores_ansi(self):
        styled = colors.colorize("hello", "red+bold")
        self.assertEqual(colors.visible_len(styled), 5)

    def test_strip_ansi(self):
        self.assertEqual(colors.strip_ansi(colors.colorize("abc", "cyan")), "abc")


if __name__ == "__main__":
    unittest.main()
