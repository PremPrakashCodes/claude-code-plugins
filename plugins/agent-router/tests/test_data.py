import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _path  # noqa: F401
from agent_router import data


class TestReadPayload(unittest.TestCase):
    def _read(self, raw):
        with mock.patch("sys.stdin", io.StringIO(raw)):
            return data.read_payload()

    def test_empty_stdin(self):
        self.assertEqual(self._read(""), {})

    def test_empty_object(self):
        self.assertEqual(self._read("{}"), {})

    def test_malformed_json(self):
        self.assertEqual(self._read("{ nope"), {})

    def test_non_object_json(self):
        self.assertEqual(self._read("[1,2]"), {})

    def test_deeply_nested_json(self):
        self.assertEqual(self._read("[" * 100000 + "]" * 100000), {})


class TestPromptEvent(unittest.TestCase):
    def test_parses_fields(self):
        ev = data.parse_prompt(
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "reformat imports",
                "session_id": "s1",
                "prompt_id": "p1",
                "transcript_path": "/t.jsonl",
                "cwd": "/repo",
            }
        )
        self.assertEqual(ev.prompt, "reformat imports")
        self.assertEqual(ev.session_id, "s1")
        self.assertEqual(ev.prompt_id, "p1")
        self.assertFalse(ev.is_task_notification)

    def test_task_notification_is_flagged(self):
        ev = data.parse_prompt({"prompt": "<task-notification>\n<task-id>a1</task-id>"})
        self.assertTrue(ev.is_task_notification)

    def test_missing_fields_default(self):
        ev = data.parse_prompt({})
        self.assertEqual(ev.prompt, "")
        self.assertEqual(ev.session_id, "")

    def test_non_string_prompt(self):
        ev = data.parse_prompt({"prompt": {"x": 1}})
        self.assertEqual(ev.prompt, "")


class TestDispatchEvent(unittest.TestCase):
    def test_parses_agent_dispatch(self):
        ev = data.parse_dispatch(
            {
                "tool_name": "Agent",
                "tool_use_id": "tu1",
                "session_id": "s1",
                "prompt_id": "p1",
                "cwd": "/repo",
                "tool_input": {
                    "description": "Find usages",
                    "prompt": "find it",
                    "subagent_type": "Explore",
                },
            }
        )
        self.assertTrue(ev.is_dispatch)
        self.assertEqual(ev.subagent_type, "Explore")
        self.assertIsNone(ev.explicit_model)
        self.assertEqual(ev.tool_use_id, "tu1")

    def test_legacy_task_tool_is_a_dispatch(self):
        ev = data.parse_dispatch({"tool_name": "Task", "tool_input": {}})
        self.assertTrue(ev.is_dispatch)

    def test_other_tools_are_not_dispatches(self):
        ev = data.parse_dispatch({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertFalse(ev.is_dispatch)

    def test_explicit_model_is_detected(self):
        ev = data.parse_dispatch({"tool_name": "Agent", "tool_input": {"model": "opus"}})
        self.assertEqual(ev.explicit_model, "opus")

    def test_blank_model_is_not_explicit(self):
        ev = data.parse_dispatch({"tool_name": "Agent", "tool_input": {"model": "  "}})
        self.assertIsNone(ev.explicit_model)

    def test_non_dict_tool_input(self):
        ev = data.parse_dispatch({"tool_name": "Agent", "tool_input": "oops"})
        self.assertEqual(ev.tool_input, {})


class TestAgentDefinitionModel(unittest.TestCase):
    def _write_agent(self, root: Path, name: str, frontmatter: str) -> None:
        agents = root / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / f"{name}.md").write_text(f"---\n{frontmatter}\n---\n\nBody\n", encoding="utf-8")

    def test_project_agent_model(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as home:
            self._write_agent(Path(repo) / ".claude", "reviewer", "name: reviewer\nmodel: opus")
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": home}):
                self.assertEqual(data.agent_definition_model("reviewer", repo), "opus")

    def test_user_agent_model(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as home:
            self._write_agent(Path(home), "helper", 'model: "sonnet"')
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": home}):
                self.assertEqual(data.agent_definition_model("helper", repo), "sonnet")

    def test_plugin_agent_model(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as home:
            plugin_root = Path(home) / "plugins" / "cache" / "mkt" / "tools" / "1.0.0"
            self._write_agent(plugin_root, "deep-review", "model: opus")
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": home}):
                self.assertEqual(data.agent_definition_model("tools:deep-review", repo), "opus")

    def test_inherit_is_not_a_pinned_model(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as home:
            self._write_agent(Path(repo) / ".claude", "a", "model: inherit")
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": home}):
                self.assertIsNone(data.agent_definition_model("a", repo))

    def test_unknown_or_unsafe_names(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as home:
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": home}):
                self.assertIsNone(data.agent_definition_model("missing", repo))
                self.assertIsNone(data.agent_definition_model("../../etc/passwd", repo))
                self.assertIsNone(data.agent_definition_model("", repo))
                self.assertIsNone(data.agent_definition_model(None, repo))


class TestTranscriptModel(unittest.TestCase):
    def test_last_assistant_model_wins(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.jsonl"
            rows = [
                {"type": "user", "message": {"content": "hi"}},
                {"type": "assistant", "message": {"model": "claude-opus-5"}},
                {"type": "assistant", "message": {"model": "claude-sonnet-5"}},
                "not json",
            ]
            p.write_text(
                "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows),
                encoding="utf-8",
            )
            self.assertEqual(data.session_model_from_transcript(str(p)), "claude-sonnet-5")

    def test_missing_transcript(self):
        self.assertIsNone(data.session_model_from_transcript("/no/such/file.jsonl"))
        self.assertIsNone(data.session_model_from_transcript(""))

    def test_model_family(self):
        self.assertEqual(data.model_family("claude-opus-5"), "opus")
        self.assertEqual(data.model_family("claude-haiku-4-5-20251001"), "haiku")
        self.assertEqual(data.model_family("sonnet"), "sonnet")
        self.assertEqual(data.model_family("claude-fable-5-1"), "fable")
        self.assertIsNone(data.model_family("gpt-5"))
        self.assertIsNone(data.model_family(None))


if __name__ == "__main__":
    unittest.main()
