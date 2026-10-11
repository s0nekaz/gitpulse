import contextlib
import io
import json
import unittest
from datetime import date
from unittest import mock

from gitpulse import cli
from gitpulse.cli import main
from tests.helpers import TempDirTestCase, run_main

TODAY = "2026-10-11"


class CliTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.repo_path = self.repo(
            [date(2026, 10, 11), date(2026, 10, 10), date(2026, 10, 9), date(2026, 10, 1), date(2026, 10, 1)]
        )

    def test_prints_heatmap_and_stats(self):
        code, out, _ = run_main([str(self.repo_path), "--today", TODAY, "--color", "never"])
        self.assertEqual(code, 0)
        self.assertIn("last 52 weeks", out)
        self.assertIn("5 on 4 active days", out)
        self.assertIn("Current streak  3 days", out)
        self.assertIn("Longest streak  3 days", out)

    def test_json_output(self):
        code, out, _ = run_main([str(self.repo_path), "--today", TODAY, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(
            data["days"], {"2026-10-01": 2, "2026-10-09": 1, "2026-10-10": 1, "2026-10-11": 1}
        )
        self.assertEqual(data["stats"]["current_streak"], 3)
        self.assertEqual(data["end"], TODAY)

    def test_author_filter(self):
        repo = self.repo([(date(2026, 10, 11), "Ada"), (date(2026, 10, 10), "Grace")], name="two-authors")
        code, out, _ = run_main([str(repo), "--today", TODAY, "--json", "--author", "Grace"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["days"], {"2026-10-10": 1})

    def test_weeks_sets_the_window(self):
        code, out, _ = run_main([str(self.repo_path), "--today", TODAY, "--json", "--weeks", "1"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["start"], "2026-10-05")
        self.assertEqual(list(data["days"]), ["2026-10-09", "2026-10-10", "2026-10-11"])

    def test_svg_file_is_written(self):
        target = self.tmp / "out.svg"
        code, _, _ = run_main(
            [str(self.repo_path), "--today", TODAY, "--color", "never", "--svg", str(target)]
        )
        self.assertEqual(code, 0)
        self.assertTrue(target.read_text(encoding="utf-8").startswith("<svg"))

    def test_unwritable_svg_path_is_a_clean_error(self):
        bad = self.tmp / "missing-folder" / "out.svg"
        code, _, err = run_main([str(self.repo_path), "--today", TODAY, "--svg", str(bad)])
        self.assertEqual(code, 2)
        self.assertIn("cannot write", err)

    def test_not_a_repo_is_a_clean_error(self):
        code, _, err = run_main([str(self.tmp)])
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("gitpulse:"))

    def test_closed_pipe_exits_quietly(self):
        # What `gitpulse | head -1` looks like once `head` has gone away.
        class HungUp(io.StringIO):
            def write(self, _text):
                raise BrokenPipeError

        with contextlib.redirect_stdout(HungUp()):
            self.assertEqual(main([str(self.repo_path), "--today", TODAY]), 0)


class ColorChoiceTests(unittest.TestCase):
    def _auto_on_windows(self, console_supports_ansi):
        terminal = mock.Mock()
        terminal.isatty.return_value = True
        with mock.patch.object(cli.sys, "stdout", terminal), \
                mock.patch.object(cli.sys, "platform", "win32"), \
                mock.patch.dict(cli.os.environ, {}, clear=True), \
                mock.patch.object(cli, "_enable_windows_ansi", return_value=console_supports_ansi):
            return cli._use_color("auto")

    def test_old_windows_console_gets_plain_output(self):
        self.assertFalse(self._auto_on_windows(False))

    def test_windows_console_that_supports_ansi_gets_colour(self):
        self.assertTrue(self._auto_on_windows(True))

    def test_never_always_win_over_detection(self):
        self.assertFalse(cli._use_color("never"))


class ArgumentTests(unittest.TestCase):
    def _exit_code(self, argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main(argv)
        return cm.exception.code

    def test_bad_weeks_is_rejected(self):
        self.assertEqual(self._exit_code(["--weeks", "0"]), 2)
        self.assertEqual(self._exit_code(["--weeks", "many"]), 2)

    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertTrue(out.getvalue().startswith("gitpulse "))


if __name__ == "__main__":
    unittest.main()
