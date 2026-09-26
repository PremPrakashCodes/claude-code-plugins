import unittest

import _path  # noqa: F401
from agent_router import config as config_mod
from agent_router import rules


def cfg():
    return config_mod._deep_merge(config_mod.DEFAULTS, {})


THRESHOLD = config_mod.DEFAULTS["rules"]["threshold"]


class TestPromptRules(unittest.TestCase):
    def test_short_formatting_request_is_confident_low(self):
        # AE1
        result = rules.classify_prompt("reformat this file's imports", cfg())
        self.assertEqual(result.tier, "low")
        self.assertGreaterEqual(result.confidence, THRESHOLD)
        self.assertIn("reformat", result.signals["low"])

    def test_short_prompt_with_architecture_vocabulary_is_ambiguous(self):
        # AE2 (setup half): conflicting signals stay below the threshold
        result = rules.classify_prompt("redesign the plugin architecture", cfg())
        self.assertLess(result.confidence, THRESHOLD)

    def test_long_debugging_prompt_with_error_text_is_confident_high(self):
        trace = (
            "Traceback (most recent call last):\n"
            '  File "app/server.py", line 88, in handle\n'
            "    result = pool.submit(job).result()\n"
            "RuntimeError: deadlock detected in worker pool\n"
        )
        prompt = (
            "Debug this intermittent failure. The worker pool deadlocks under load and "
            "I need the root cause, not a retry.\n" + trace * 30
        )
        result = rules.classify_prompt(prompt, cfg())
        self.assertEqual(result.tier, "high")
        self.assertGreaterEqual(result.confidence, THRESHOLD)
        self.assertIn("stack_trace", result.signals["structure"])

    def test_simple_question_routes_low(self):
        result = rules.classify_prompt("where is the config file loaded?", cfg())
        self.assertEqual(result.tier, "low")
        self.assertGreaterEqual(result.confidence, THRESHOLD)

    def test_debugging_question_is_not_confident_low(self):
        result = rules.classify_prompt("why does the login test fail intermittently?", cfg())
        self.assertFalse(result.tier == "low" and rules.is_confident(result, cfg()))
        self.assertNotIn("question", result.signals["structure"])

    def test_short_prompt_without_keywords_is_not_confident(self):
        for prompt in ("hi", "explain how the auth middleware works"):
            result = rules.classify_prompt(prompt, cfg())
            self.assertFalse(rules.is_confident(result, cfg()), prompt)

    def test_feature_request_routes_mid(self):
        prompt = (
            "Implement a new endpoint that returns the user's saved searches, add a "
            "test for it, and update the API docs. " + "Keep the existing style. " * 12
        )
        result = rules.classify_prompt(prompt, cfg())
        self.assertEqual(result.tier, "mid")

    def test_no_signals_is_not_confident(self):
        result = rules.classify_prompt("x " * 400, cfg())
        self.assertLess(result.confidence, THRESHOLD)

    def test_empty_prompt_is_safe(self):
        result = rules.classify_prompt("", cfg())
        self.assertIn(result.tier, config_mod.TIERS)
        self.assertLess(result.confidence, THRESHOLD)

    def test_non_string_prompt_is_safe(self):
        result = rules.classify_prompt(None, cfg())  # type: ignore[arg-type]
        self.assertLess(result.confidence, THRESHOLD)

    def test_size_band_edges(self):
        c = cfg()
        short, long_ = c["rules"]["shortChars"], c["rules"]["longChars"]
        self.assertEqual(rules.size_band(short - 1, c), "short")
        self.assertEqual(rules.size_band(short, c), "medium")
        self.assertEqual(rules.size_band(long_, c), "medium")
        self.assertEqual(rules.size_band(long_ + 1, c), "long")

    def test_threshold_is_configurable(self):
        c = cfg()
        c["rules"]["threshold"] = 0.99
        result = rules.classify_prompt("redesign the plugin architecture", c)
        self.assertFalse(rules.is_confident(result, c))
        c["rules"]["threshold"] = 0.0
        self.assertTrue(rules.is_confident(result, c))

    def test_keywords_match_whole_words_only(self):
        # "listing" must not count as the low keyword "list"; "designation" is not "design"
        result = rules.classify_prompt("designation listing", cfg())
        self.assertNotIn("list", result.signals["low"])
        self.assertNotIn("design", result.signals["high"])

    def test_signals_never_contain_prompt_text(self):
        secret = "hunter2-supersecret-token"
        result = rules.classify_prompt(f"rename {secret} to foo", cfg())
        self.assertNotIn(secret, repr(result.signals))


class TestDispatchRules(unittest.TestCase):
    def test_explore_lookup_dispatch_is_confident_low(self):
        # AE3: an Explore-style lookup routes to the cheap tier
        long_prompt = (
            "Find where the config loader is defined and list the files that import it. "
            "Report file paths only. " + "Be thorough across the repository. " * 40
        )
        result = rules.classify_dispatch(
            description="Find config loader usages",
            prompt=long_prompt,
            subagent_type="Explore",
            config=cfg(),
        )
        self.assertEqual(result.tier, "low")
        self.assertGreaterEqual(result.confidence, THRESHOLD)

    def test_long_dispatch_prompt_is_not_penalized_for_length(self):
        long_prompt = "Search the codebase for usages of parse_config. " * 100
        result = rules.classify_dispatch(
            description="Locate parse_config usages",
            prompt=long_prompt,
            subagent_type="general-purpose",
            config=cfg(),
        )
        self.assertEqual(result.tier, "low")
        self.assertEqual(result.signals["band"], "n/a")

    def test_architecture_review_dispatch_is_high(self):
        result = rules.classify_dispatch(
            description="Architecture review of the concurrency design",
            prompt="Review the architecture and concurrency design for race conditions "
            "and security issues; propose a redesign with trade-offs.",
            subagent_type="general-purpose",
            config=cfg(),
        )
        self.assertEqual(result.tier, "high")

    def test_dispatch_with_no_description_is_safe(self):
        result = rules.classify_dispatch(
            description=None, prompt=None, subagent_type=None, config=cfg()
        )
        self.assertIn(result.tier, config_mod.TIERS)


if __name__ == "__main__":
    unittest.main()
