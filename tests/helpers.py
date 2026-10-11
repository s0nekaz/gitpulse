"""Shared helpers: build real git repos and run the CLI in-process."""

import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from gitpulse.cli import main


def make_repo(path, commits):
    """Create a real git repo at ``path`` with one empty commit per item.

    Each item is a ``date`` or a ``(date, author_name)`` pair.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for item in commits:
        day, author = item if isinstance(item, tuple) else (item, "Ada")
        stamp = day.isoformat() + "T12:00:00"
        subprocess.run(
            [
                "git", "-C", str(path),
                "-c", "user.name=" + author,
                "-c", "user.email=" + author.lower() + "@example.com",
                "-c", "commit.gpgsign=false",
                "commit", "-q", "--allow-empty", "-m", "x",
            ],
            check=True,
            env={**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
        )
    return path


def run_main(argv):
    """Run the CLI and return ``(exit_code, stdout, stderr)``."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class TempDirTestCase(unittest.TestCase):
    """A test case with ``self.tmp`` (a fresh folder) and ``self.repo(commits)``."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gitpulse-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def repo(self, commits, name="repo"):
        return make_repo(self.tmp / name, commits)
