"""Turn a grid of days and their commit counts into terminal text or an SVG."""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

from .core import Stats, level_for, level_thresholds

Grid = List[List[Optional[date]]]

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ROW_LABELS = ("Mon", "", "Wed", "", "Fri", "", "Sun")

PLAIN_CELLS = ("·", "░", "▒", "▓", "█")
ANSI_COLORS = (238, 22, 28, 34, 40)  # 256-colour palette: grey, then four greens
SVG_COLORS = ("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353")

LABEL_WIDTH = 4  # characters reserved for the weekday labels


def month_label_positions(grid: Grid) -> List[Tuple[int, str]]:
    """(column index, month name) pairs, skipping labels that would collide."""
    labels: List[Tuple[int, str]] = []
    last_col = -10
    for i, column in enumerate(grid):
        month = column[0].month  # a column's Monday is never in the future
        if i == 0:
            # A one-week sliver of a month at the left edge: label the next month instead.
            if len(grid) > 1 and grid[1][0].month != month:
                continue
        elif month == grid[i - 1][0].month:
            continue
        if i - last_col < 2:
            continue
        labels.append((i, MONTHS[month - 1]))
        last_col = i
    return labels


def _cell(level: int, color: bool) -> str:
    if color:
        return "\x1b[38;5;{}m■\x1b[0m".format(ANSI_COLORS[level])
    return PLAIN_CELLS[level]


def render_heatmap(grid: Grid, counts: Dict[date, int], color: bool = False) -> str:
    thresholds = level_thresholds(counts)

    header = [" "] * (LABEL_WIDTH + len(grid) * 2 + 3)
    for i, name in month_label_positions(grid):
        for k, ch in enumerate(name):
            header[LABEL_WIDTH + i * 2 + k] = ch
    lines = ["".join(header).rstrip()]

    for r in range(7):
        parts = [ROW_LABELS[r].ljust(LABEL_WIDTH)]
        for column in grid:
            d = column[r]
            if d is None:
                parts.append("  ")
            else:
                parts.append(_cell(level_for(counts.get(d, 0), thresholds), color) + " ")
        lines.append("".join(parts).rstrip())

    legend = " ".join(_cell(level, color) for level in range(5))
    lines.append("")
    lines.append(" " * LABEL_WIDTH + "Less " + legend + " More")
    return "\n".join(lines)


def _plural(n: int, word: str) -> str:
    return "{} {}{}".format(n, word, "" if n == 1 else "s")


def render_stats(stats: Stats) -> str:
    if stats.total == 0:
        return "No commits in this window."
    rows = [
        ("Commits", "{} on {}".format(stats.total, _plural(stats.active_days, "active day"))),
        ("Current streak", _plural(stats.current_streak, "day")),
        ("Longest streak", _plural(stats.longest_streak, "day")),
        (
            "Busiest day",
            "{} ({})".format(stats.busiest_day.isoformat(), _plural(stats.busiest_count, "commit")),
        ),
        ("Favourite day", stats.favorite_weekday or "-"),
    ]
    width = max(len(label) for label, _ in rows)
    return "\n".join("{}  {}".format(label.ljust(width), value) for label, value in rows)


def render_svg(grid: Grid, counts: Dict[date, int], title: str = "") -> str:
    """A self-contained SVG heatmap with a hover tooltip on every day."""
    cell, gap = 11, 3
    step = cell + gap
    left, top = 34, 46
    width = left + len(grid) * step + 14
    height = top + 7 * step + 36
    thresholds = level_thresholds(counts)

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        'viewBox="0 0 {w} {h}" role="img" aria-label={label}>'.format(
            w=width, h=height, label=quoteattr(title or "Commit heatmap")
        ),
        '<rect width="{}" height="{}" rx="8" fill="#0d1117"/>'.format(width, height),
        '<g font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
        'font-size="10" fill="#8b949e">',
    ]
    if title:
        out.append(
            '<text x="{}" y="24" font-size="12" fill="#e6edf3">{}</text>'.format(left, escape(title))
        )
    for i, name in month_label_positions(grid):
        out.append('<text x="{}" y="{}">{}</text>'.format(left + i * step, top - 8, name))
    for r in (0, 2, 4):
        out.append(
            '<text x="8" y="{}">{}</text>'.format(top + r * step + cell - 1, ROW_LABELS[r])
        )
    out.append("</g>")

    for c, column in enumerate(grid):
        for r, d in enumerate(column):
            if d is None:
                continue
            n = counts.get(d, 0)
            level = level_for(n, thresholds)
            tip = "{}: {}".format(d.isoformat(), "no commits" if n == 0 else _plural(n, "commit"))
            out.append(
                '<rect x="{}" y="{}" width="{}" height="{}" rx="2" fill="{}">'
                "<title>{}</title></rect>".format(
                    left + c * step, top + r * step, cell, cell, SVG_COLORS[level], escape(tip)
                )
            )

    legend_y = top + 7 * step + 12
    legend_right = left + len(grid) * step
    legend_x = legend_right - (5 * step + 52)
    out.append(
        '<text x="{}" y="{}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
        'font-size="10" fill="#8b949e">Less</text>'.format(legend_x, legend_y + cell - 1)
    )
    for level in range(5):
        out.append(
            '<rect x="{}" y="{}" width="{}" height="{}" rx="2" fill="{}"/>'.format(
                legend_x + 28 + level * step, legend_y, cell, cell, SVG_COLORS[level]
            )
        )
    out.append(
        '<text x="{}" y="{}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
        'font-size="10" fill="#8b949e">More</text>'.format(legend_x + 28 + 5 * step + 4, legend_y + cell - 1)
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"
