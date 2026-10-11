"""Command-line interface for gitpulse."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from . import __version__
from .core import (
    GitError,
    build_grid,
    commit_dates,
    compute_stats,
    count_days,
    window_start,
)
from .render import render_heatmap, render_stats, render_svg


def _weeks(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a whole number") from None
    if not 1 <= n <= 520:
        raise argparse.ArgumentTypeError("must be between 1 and 520")
    return n


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gitpulse",
        description="A commit heatmap and streak stats for any git repository.",
    )
    p.add_argument("path", nargs="?", default=".", help="repository path (default: current directory)")
    p.add_argument("-w", "--weeks", type=_weeks, default=52, help="weeks of history to show (default: 52)")
    p.add_argument("-a", "--author", help="only count commits whose author matches this pattern")
    p.add_argument("--all", dest="all_branches", action="store_true", help="count every branch, not just HEAD")
    p.add_argument("--no-merges", action="store_true", help="ignore merge commits")
    p.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="colour output (default: auto)")
    p.add_argument("--json", action="store_true", help="print per-day counts and stats as JSON instead")
    p.add_argument("--svg", metavar="FILE", help="also write the heatmap as an SVG image, handy for READMEs")
    p.add_argument("--today", type=_iso_date, help=argparse.SUPPRESS)  # for reproducible demos and tests
    p.add_argument("-V", "--version", action="version", version="%(prog)s " + __version__)
    return p


def _use_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return (
        sys.stdout.isatty()
        and "NO_COLOR" not in os.environ
        and os.environ.get("TERM") != "dumb"
    )


def _tolerate_odd_terminals() -> None:
    """Print '?' instead of crashing if the terminal can't encode the heatmap glyphs."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass


def main(argv: Optional[List[str]] = None) -> int:
    try:
        return _run(argv)
    except BrokenPipeError:
        # `gitpulse | head`: the reader hung up early, which is fine. Point stdout
        # at /dev/null so Python doesn't complain again while shutting down.
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError):
            pass
        return 0


def _run(argv: Optional[List[str]]) -> int:
    args = build_parser().parse_args(argv)
    _tolerate_odd_terminals()

    today = args.today or date.today()
    start = window_start(today, args.weeks)

    try:
        dates = commit_dates(
            args.path,
            author=args.author,
            since=start,
            no_merges=args.no_merges,
            all_branches=args.all_branches,
        )
    except GitError as exc:
        print("gitpulse: {}".format(exc), file=sys.stderr)
        return 2

    counts = count_days(dates, start, today)
    stats = compute_stats(counts, today)
    grid = build_grid(today, args.weeks)
    name = Path(args.path).resolve().name or str(args.path)
    title = "{} · {} commits in the last {} weeks".format(name, stats.total, args.weeks)

    if args.svg:
        try:
            Path(args.svg).write_text(render_svg(grid, counts, title), encoding="utf-8")
        except OSError as exc:
            print("gitpulse: cannot write {}: {}".format(args.svg, exc.strerror or exc), file=sys.stderr)
            return 2

    if args.json:
        payload = {
            "weeks": args.weeks,
            "start": start.isoformat(),
            "end": today.isoformat(),
            "days": {d.isoformat(): counts[d] for d in sorted(counts)},
            "stats": stats.to_dict(),
        }
        print(json.dumps(payload, indent=2))
        return 0

    print("{} - last {} weeks".format(name, args.weeks))
    print()
    print(render_heatmap(grid, counts, color=_use_color(args.color)))
    print()
    print(render_stats(stats))
    return 0
