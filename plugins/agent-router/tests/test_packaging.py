import json
import subprocess
import sys
import unittest
from pathlib import Path

import _path  # noqa: F401

PLUGIN_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PLUGIN_DIR.parent.parent


class TestPackaging(unittest.TestCase):
    def test_manifest_lists_command_files(self):
        manifest = json.loads(
            (PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["name"], "agent-router")
        self.assertEqual(
            manifest["commands"],
            ["./commands/setup.md", "./commands/configure.md", "./commands/report.md"],
        )

    def test_marketplace_registers_plugin(self):
        market = json.loads(
            (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        entries = {p["name"]: p["source"] for p in market["plugins"]}
        self.assertEqual(entries.get("agent-router"), "./plugins/agent-router")
        self.assertIn("status-line", entries)

    def test_manifest_and_pyproject_versions_match(self):
        manifest = json.loads(
            (PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        pyproject = (PLUGIN_DIR / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{manifest["version"]}"', pyproject)

    def test_router_help_runs_without_install(self):
        result = subprocess.run(
            [sys.executable, str(PLUGIN_DIR / "src" / "router.py"), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("route-task", result.stdout)


if __name__ == "__main__":
    unittest.main()
