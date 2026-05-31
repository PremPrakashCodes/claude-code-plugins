import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

import _path  # noqa: F401

from hud import cli, data as data_mod


def _run(argv, stdin=""):
    """Run cli.main(argv) with a fake stdin, returning what it printed to stdout."""
    buf = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(buf):
        cli.main(argv)
    return buf.getvalue()


class TestCliFlags(unittest.TestCase):
    def test_styles_lists_known_style(self):
        out = _run(["--styles"])
        self.assertIn("rounded", out)
        self.assertIn("smooth", out)

    def test_demo_renders_a_line(self):
        out = _run(["--demo"]).strip()
        self.assertTrue(out)  # non-empty HUD line
        self.assertIn("Opus", out)


class TestCliFailSilent(unittest.TestCase):
    """The status line must never dump a traceback onto the prompt."""

    def test_stdin_render_error_prints_blank_line(self):
        with mock.patch("hud.cli.render_mod.render", side_effect=RuntimeError("boom")):
            out = _run([], stdin='{"model": {"display_name": "X"}}')
        self.assertEqual(out, "\n")

    def test_demo_render_error_prints_blank_line(self):
        # The --demo path is guarded too, not just the stdin path.
        with mock.patch("hud.cli.render_mod.render", side_effect=RuntimeError("boom")):
            out = _run(["--demo"])
        self.assertEqual(out, "\n")

    def test_deeply_nested_stdin_does_not_crash(self):
        # json.loads raises RecursionError (not a ValueError) on deep nesting;
        # read_payload() runs inside main's guard, so this must stay silent.
        hostile = "[" * 60000 + "]" * 60000
        out = _run([], stdin=hostile)
        self.assertEqual(out, "\n")

    def test_nan_token_count_does_not_crash(self):
        out = _run([], stdin='{"context_window": {"current_usage": {"input_tokens": NaN}}}')
        # Either a rendered line or a blank line is fine; the point is no traceback.
        self.assertNotIn("Traceback", out)


class TestReadPayloadTolerance(unittest.TestCase):
    def test_empty_stdin(self):
        with mock.patch("sys.stdin", io.StringIO("")):
            self.assertEqual(data_mod.read_payload(), {})

    def test_malformed_json(self):
        with mock.patch("sys.stdin", io.StringIO("{not json")):
            self.assertEqual(data_mod.read_payload(), {})

    def test_non_dict_json(self):
        with mock.patch("sys.stdin", io.StringIO("[1, 2, 3]")):
            self.assertEqual(data_mod.read_payload(), {})


if __name__ == "__main__":
    unittest.main()
