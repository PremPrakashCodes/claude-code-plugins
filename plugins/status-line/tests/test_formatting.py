import unittest

import _path  # noqa: F401

from hud.formatting import format_cost, format_duration, humanize_tokens


class TestFormatting(unittest.TestCase):
    def test_humanize_tokens(self):
        self.assertEqual(humanize_tokens(0), "0")
        self.assertEqual(humanize_tokens(980), "980")
        self.assertEqual(humanize_tokens(86_000), "86k")
        self.assertEqual(humanize_tokens(1_000_000), "1.0M")
        self.assertEqual(humanize_tokens(1_500_000), "1.5M")

    def test_humanize_tokens_bad_input(self):
        self.assertEqual(humanize_tokens(None), "0")
        self.assertEqual(humanize_tokens("nope"), "0")

    def test_format_duration(self):
        self.assertEqual(format_duration(0), "<1m")
        self.assertEqual(format_duration(59), "<1m")
        self.assertEqual(format_duration(17 * 60), "17m")
        self.assertEqual(format_duration(8220), "2h 17m")
        self.assertEqual(format_duration(280800), "3d 6h")

    def test_format_duration_negative(self):
        self.assertEqual(format_duration(-100), "<1m")

    def test_format_cost(self):
        self.assertEqual(format_cost(0.42), "$0.42")
        self.assertEqual(format_cost(1.2, label="USD "), "USD 1.20")
        self.assertEqual(format_cost(None), "$0.00")


if __name__ == "__main__":
    unittest.main()
