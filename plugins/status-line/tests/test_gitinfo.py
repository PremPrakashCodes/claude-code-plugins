import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from hud import gitinfo

HAS_GIT = shutil.which("git") is not None


class TestGitInfoNonRepo(unittest.TestCase):
    def test_empty_cwd(self):
        self.assertFalse(gitinfo.collect("").is_repo)

    def test_non_repo_dir(self):
        with tempfile.TemporaryDirectory() as d:
            status = gitinfo.collect(d)
        self.assertFalse(status.is_repo)
        self.assertEqual(status.branch, "")


@unittest.skipUnless(HAS_GIT, "git not installed")
class TestGitInfoRealRepo(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._git("init", "-b", "main")
        self._git("config", "user.email", "t@t.t")
        self._git("config", "user.name", "t")
        self._git("config", "commit.gpgsign", "false")
        (Path(self.dir) / "a.txt").write_text("hello")
        self._git("add", "a.txt")
        self._git("commit", "-m", "init")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _git(self, *args):
        subprocess.run(["git", "-C", self.dir, *args], capture_output=True, check=True)

    def test_clean_repo(self):
        status = gitinfo.collect(self.dir)
        self.assertTrue(status.is_repo)
        self.assertEqual(status.branch, "main")
        self.assertFalse(status.dirty)

    def test_dirty_repo(self):
        (Path(self.dir) / "a.txt").write_text("changed")
        status = gitinfo.collect(self.dir)
        self.assertTrue(status.dirty)

    def test_file_stats_counts_untracked(self):
        (Path(self.dir) / "new.txt").write_text("x")
        status = gitinfo.collect(self.dir, file_stats=True)
        self.assertEqual(status.untracked, 1)


if __name__ == "__main__":
    unittest.main()
