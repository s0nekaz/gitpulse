"""Read commit history from git and turn it into per-day counts and stats."""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


class GitError(RuntimeError):
    """Raised when git is missing or the path is not a usable repository."""


def commit_dates(
    repo: str = ".",
    *,
    author: Optional[str] = None,
    since: Optional[date] = None,
    no_merges: bool = False,
    all_branches: bool = False,
) -> List[date]:
    """Return one date per commit (the commit's author date, as recorded)."""
    cmd = ["git", "-C", str(repo), "log", "--date=short", "--pretty=format:%ad"]
    if all_branches:
        cmd.append("--all")
    if no_merges:
        cmd.append("--no-merges")
    if author:
        cmd.append("--author=" + author)
    # No `git log --since` here on purpose: git stops walking at the first commit
    # older than the cutoff, which silently drops commits in histories whose dates
    # run out of order (rebases, imports, clock skew). We filter exactly below.
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as exc:
        raise GitError("git was not found on your PATH") from exc
    if proc.returncode != 0:
        message = proc.stderr.strip()
        if "does not have any commits yet" in message:
            return []
        if message.startswith("fatal: "):
            message = message[len("fatal: "):]
        raise GitError(message or "git log failed")
    found = [date.fromisoformat(ln) for ln in proc.stdout.splitlines() if ln.strip()]
    if since is not None:
        found = [d for d in found if d >= since]
    return found


def count_days(dates: Iterable[date], start: date, end: date) -> Dict[date, int]:
    """Count commits per day, keeping only days inside [start, end]."""
    return dict(Counter(d for d in dates if start <= d <= end))


@dataclass(frozen=True)
class Stats:
    total: int
    active_days: int
    longest_streak: int
    current_streak: int
    busiest_day: Optional[date]
    busiest_count: int
    favorite_weekday: Optional[str]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "active_days": self.active_days,
            "longest_streak": self.longest_streak,
            "current_streak": self.current_streak,
            "busiest_day": self.busiest_day.isoformat() if self.busiest_day else None,
            "busiest_count": self.busiest_count,
            "favorite_weekday": self.favorite_weekday,
        }


def compute_stats(counts: Dict[date, int], today: date) -> Stats:
    """Summarise per-day counts: totals, streaks, busiest day, favourite weekday."""
    counts = {d: c for d, c in counts.items() if c > 0 and d <= today}
    if not counts:
        return Stats(0, 0, 0, 0, None, 0, None)

    one_day = timedelta(days=1)
    days = sorted(counts)

    longest = run = 0
    previous: Optional[date] = None
    for d in days:
        run = run + 1 if previous is not None and d - previous == one_day else 1
        longest = max(longest, run)
        previous = d

    # A streak is still alive if you haven't committed *yet* today, so start
    # counting from yesterday in that case.
    cursor = today if today in counts else today - one_day
    current = 0
    while cursor in counts:
        current += 1
        cursor -= one_day

    busiest = max(days, key=lambda d: (counts[d], d))  # ties: most recent day

    per_weekday: Counter = Counter()
    for d, c in counts.items():
        per_weekday[d.weekday()] += c
    favorite = max(per_weekday, key=lambda w: (per_weekday[w], -w))  # ties: earlier

    return Stats(
        total=sum(counts.values()),
        active_days=len(counts),
        longest_streak=longest,
        current_streak=current,
        busiest_day=busiest,
        busiest_count=counts[busiest],
        favorite_weekday=WEEKDAYS[favorite],
    )


def week_start(d: date) -> date:
    """The Monday of the week containing ``d``."""
    return d - timedelta(days=d.weekday())


def window_start(today: date, weeks: int) -> date:
    """First day (a Monday) of a ``weeks``-column grid ending in today's week."""
    return week_start(today) - timedelta(weeks=weeks - 1)


def build_grid(today: date, weeks: int) -> List[List[Optional[date]]]:
    """Columns of 7 days (Monday first). Days after ``today`` are ``None``."""
    start = window_start(today, weeks)
    grid: List[List[Optional[date]]] = []
    for w in range(weeks):
        column: List[Optional[date]] = []
        for r in range(7):
            d = start + timedelta(weeks=w, days=r)
            column.append(d if d <= today else None)
        grid.append(column)
    return grid


def level_thresholds(counts: Dict[date, int]) -> Tuple[int, int, int]:
    """Quartile cut-offs over the non-zero days, so busy outliers don't wash out the map."""
    values = sorted(c for c in counts.values() if c > 0)
    if not values:
        return (1, 1, 1)
    if values[0] == values[-1]:
        # Perfectly uniform activity: show every active day at full brightness.
        return (0, 0, 0)
    n = len(values)

    def pick(p: float) -> int:
        return values[int(p * (n - 1))]

    return (pick(0.25), pick(0.5), pick(0.75))


def level_for(count: int, thresholds: Tuple[int, int, int]) -> int:
    """Map a day's commit count to a heat level from 0 (none) to 4 (hottest)."""
    if count <= 0:
        return 0
    for level, limit in enumerate(thresholds, start=1):
        if count <= limit:
            return level
    return 4
