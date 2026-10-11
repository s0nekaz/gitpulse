import subprocess
import unittest
from datetime import date, timedelta

from gitpulse.core import (
    GitError,
    build_grid,
    commit_dates,
    compute_stats,
    count_days,
    level_for,
    level_thresholds,
    window_start,
)
from tests.helpers import TempDirTestCase

TODAY = date(2026, 10, 11)  # a Sunday


def ago(*offsets):
    """Counts of 1 commit on each day ``offset`` days before TODAY."""
    return {TODAY - timedelta(days=o): 1 for o in offsets}


class StatsTests(unittest.TestCase):
    def test_empty_history(self):
        s = compute_stats({}, TODAY)
        self.assertEqual((s.total, s.active_days, s.current_streak, s.longest_streak), (0, 0, 0, 0))
        self.assertIsNone(s.busiest_day)
        self.assertIsNone(s.favorite_weekday)

    def test_current_and_longest_streak(self):
        s = compute_stats(ago(0, 1, 2, 10, 11, 12, 13, 14), TODAY)
        self.assertEqual(s.current_streak, 3)
        self.assertEqual(s.longest_streak, 5)
        self.assertEqual(s.active_days, 8)

    def test_streak_is_alive_if_you_have_not_committed_yet_today(self):
        self.assertEqual(compute_stats(ago(1, 2, 3), TODAY).current_streak, 3)

    def test_streak_is_broken_by_a_gap(self):
        s = compute_stats(ago(2, 3, 4), TODAY)
        self.assertEqual(s.current_streak, 0)
        self.assertEqual(s.longest_streak, 3)

    def test_busiest_day_prefers_the_most_recent_on_a_tie(self):
        counts = {TODAY - timedelta(days=5): 4, TODAY - timedelta(days=2): 4, TODAY: 1}
        s = compute_stats(counts, TODAY)
        self.assertEqual(s.busiest_day, TODAY - timedelta(days=2))
        self.assertEqual(s.busiest_count, 4)
        self.assertEqual(s.total, 9)

    def test_favorite_weekday_counts_commits_not_days(self):
        counts = {date(2026, 10, 6): 5, date(2026, 10, 7): 2, date(2026, 10, 8): 2}
        self.assertEqual(compute_stats(counts, TODAY).favorite_weekday, "Tuesday")

    def test_days_after_today_are_ignored(self):
        s = compute_stats({TODAY + timedelta(days=3): 9, TODAY: 1}, TODAY)
        self.assertEqual(s.total, 1)

    def test_count_days_keeps_only_the_window(self):
        dates = [date(2026, 9, 1), date(2026, 10, 1), date(2026, 10, 1), date(2026, 10, 20)]
        self.assertEqual(count_days(dates, date(2026, 10, 1), TODAY), {date(2026, 10, 1): 2})


class GridTests(unittest.TestCase):
    def test_grid_is_monday_first_and_ends_in_this_week(self):
        grid = build_grid(TODAY, 4)
        self.assertEqual(len(grid), 4)
        self.assertTrue(all(len(col) == 7 for col in grid))
        self.assertEqual(grid[0][0], window_start(TODAY, 4))
        self.assertEqual(grid[0][0], date(2026, 9, 14))
        self.assertEqual(grid[-1][0], date(2026, 10, 5))  # Monday
        self.assertEqual(grid[-1][6], TODAY)  # Sunday, so the last column is full

    def test_grid_blanks_out_the_future(self):
        wednesday = date(2026, 10, 14)
        last = build_grid(wednesday, 2)[-1]
        self.assertEqual(last[:3], [date(2026, 10, 12), date(2026, 10, 13), wednesday])
        self.assertEqual(last[3:], [None] * 4)


class LevelTests(unittest.TestCase):
    def test_levels_follow_quartiles_of_active_days(self):
        counts = {TODAY - timedelta(days=i): i + 1 for i in range(4)}  # 1, 2, 3, 4
        t = level_thresholds(counts)
        self.assertEqual(t, (1, 2, 3))
        self.assertEqual([level_for(n, t) for n in (0, 1, 2, 3, 4)], [0, 1, 2, 3, 4])

    def test_a_big_outlier_gets_the_top_level_alone(self):
        counts = {TODAY - timedelta(days=i): 1 for i in range(9)}
        counts[TODAY - timedelta(days=20)] = 50
        t = level_thresholds(counts)
        self.assertEqual(level_for(1, t), 1)
        self.assertEqual(level_for(50, t), 4)

    def test_the_busiest_day_is_always_the_hottest_level(self):
        t = level_thresholds({TODAY: 9, TODAY - timedelta(days=1): 1})
        self.assertEqual(level_for(9, t), 4)
        self.assertEqual(level_for(1, t), 1)

    def test_uniform_activity_is_shown_at_full_brightness(self):
        t = level_thresholds({TODAY: 1, TODAY - timedelta(days=1): 1})
        self.assertEqual(level_for(1, t), 4)

    def test_no_activity_is_harmless(self):
        self.assertEqual(level_for(0, level_thresholds({})), 0)


class ReadingGitTests(TempDirTestCase):
    def test_one_date_per_commit(self):
        repo = self.repo([date(2026, 10, 1), date(2026, 10, 1), date(2026, 10, 3)])
        self.assertEqual(
            sorted(commit_dates(repo)), [date(2026, 10, 1), date(2026, 10, 1), date(2026, 10, 3)]
        )

    def test_author_filter(self):
        repo = self.repo([(date(2026, 10, 1), "Ada"), (date(2026, 10, 2), "Grace")])
        self.assertEqual(commit_dates(repo, author="Grace"), [date(2026, 10, 2)])

    def test_since_is_exact_to_the_day(self):
        repo = self.repo([date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)])
        found = commit_dates(repo, since=date(2026, 10, 1))
        self.assertEqual(sorted(found), [date(2026, 10, 1), date(2026, 10, 2)])

    def test_history_with_out_of_order_dates_is_still_counted(self):
        # HEAD is the oldest commit here, as after a rebase or an import.
        repo = self.repo([date(2026, 10, 11), date(2026, 10, 10), date(2026, 10, 1)])
        found = commit_dates(repo, since=date(2026, 10, 5))
        self.assertEqual(sorted(found), [date(2026, 10, 10), date(2026, 10, 11)])

    def test_repo_without_commits_is_just_empty(self):
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        self.assertEqual(commit_dates(self.tmp), [])

    def test_folder_that_is_not_a_repo_raises(self):
        with self.assertRaises(GitError):
            commit_dates(self.tmp)


if __name__ == "__main__":
    unittest.main()
