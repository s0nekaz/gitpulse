#!/usr/bin/env python3
"""Create a throwaway git repo with a deterministic, realistic-looking history.

Used to generate the README screenshot and SVG, so the demo is reproducible:

    python scripts/make_demo_repo.py /tmp/demo-repo 2026-10-11
    python -m gitpulse /tmp/demo-repo --today 2026-10-11 --svg assets/demo.svg
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: make_demo_repo.py DEST YYYY-MM-DD", file=sys.stderr)
        return 2
    dest = Path(sys.argv[1])
    today = date.fromisoformat(sys.argv[2])
    rng = random.Random(7)

    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(dest)], check=True)

    start = today - timedelta(weeks=52)
    holiday = (today - timedelta(weeks=30), today - timedelta(weeks=28))
    day = start
    total = 0
    while day <= today:
        age = (day - start).days / 365  # busier as the year goes on
        chance = (0.72 if day.weekday() < 5 else 0.22) * (0.55 + 0.6 * age)
        if holiday[0] <= day <= holiday[1]:
            chance = 0.0
        elif day > today - timedelta(days=9):
            chance = 1.0  # a live streak, so the demo has something to show
        if rng.random() < chance:
            for _ in range(rng.choice([1, 1, 1, 2, 2, 3, 4, 6])):
                stamp = "{}T{:02d}:{:02d}:00".format(day.isoformat(), rng.randint(9, 22), rng.randint(0, 59))
                env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
                subprocess.run(
                    [
                        "git", "-C", str(dest),
                        "-c", "user.name=Demo", "-c", "user.email=demo@example.com",
                        "-c", "commit.gpgsign=false",
                        "commit", "-q", "--allow-empty", "-m", "work in progress",
                    ],
                    check=True,
                    env={**os.environ, **env},
                )
                total += 1
        day += timedelta(days=1)
    print("created {} commits in {}".format(total, dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
