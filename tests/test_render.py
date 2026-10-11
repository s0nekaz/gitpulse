import unittest
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from gitpulse.core import build_grid, compute_stats
from gitpulse.render import month_label_positions, render_heatmap, render_stats, render_svg

TODAY = date(2026, 10, 11)  # a Sunday


def sample_counts():
    return {TODAY: 3, TODAY - timedelta(days=1): 1, TODAY - timedelta(days=9): 2}


class HeatmapTests(unittest.TestCase):
    def test_layout(self):
        lines = render_heatmap(build_grid(TODAY, 26), sample_counts()).splitlines()
        self.assertEqual(lines[0].split()[-1], "Oct")
        self.assertEqual([ln[:3].strip() for ln in lines[1:8]], ["Mon", "", "Wed", "", "Fri", "", "Sun"])
        self.assertTrue(lines[-1].strip().startswith("Less"))
        self.assertTrue(lines[-1].endswith("More"))

    def test_colour_is_opt_in(self):
        grid = build_grid(TODAY, 8)
        self.assertNotIn("\x1b", render_heatmap(grid, sample_counts(), color=False))
        self.assertIn("\x1b[38;5;", render_heatmap(grid, sample_counts(), color=True))

    def test_busier_days_look_hotter(self):
        counts = {TODAY: 9, TODAY - timedelta(days=1): 1}
        out = render_heatmap(build_grid(TODAY, 4), counts)
        for glyph in ("█", "░", "·"):
            self.assertIn(glyph, out)

    def test_month_labels_never_collide(self):
        for weeks in (4, 9, 13, 26, 52):
            for offset in range(0, 60, 3):
                grid = build_grid(TODAY + timedelta(days=offset), weeks)
                cols = [i for i, _ in month_label_positions(grid)]
                self.assertTrue(all(b - a >= 2 for a, b in zip(cols, cols[1:])))


class SvgTests(unittest.TestCase):
    def test_valid_xml_with_a_tooltip_per_day(self):
        grid = build_grid(TODAY, 10)
        svg = render_svg(grid, sample_counts(), title='my <repo> & "co"')
        root = ET.fromstring(svg)
        ns = "{http://www.w3.org/2000/svg}"

        days_in_grid = sum(1 for col in grid for d in col if d is not None)
        # background + one square per day + five legend squares
        self.assertEqual(len(root.findall(ns + "rect")), 1 + days_in_grid + 5)

        tips = [t.text for t in root.iter(ns + "title")]
        self.assertIn(TODAY.isoformat() + ": 3 commits", tips)
        self.assertIn((TODAY - timedelta(days=1)).isoformat() + ": 1 commit", tips)
        self.assertEqual(root.get("aria-label"), 'my <repo> & "co"')


class StatsTextTests(unittest.TestCase):
    def test_stats_text(self):
        text = render_stats(compute_stats({TODAY: 1}, TODAY))
        self.assertIn("1 on 1 active day", text)
        self.assertIn("Current streak", text)
        self.assertIn("Favourite day", text)

    def test_empty_window(self):
        self.assertEqual(render_stats(compute_stats({}, TODAY)), "No commits in this window.")


if __name__ == "__main__":
    unittest.main()
