#!/usr/bin/env python3
"""Time tracker visualizer.

A clock timeline on top -- one row per day, each block placed where it
actually happened -- with the stacked 24h bars and the growth strip beneath
it as the summary view.

    python viz.py              # opens on the current week
    python viz.py 2026-08-11   # opens on the week containing that date
    python viz.py --month      # start in month view
    python viz.py --day        # start in day view, on today
    python viz.py --png out.png            # render instead of opening a window
    python viz.py --png out.png --select slack   # render with slack selected

Navigation:
    [< Prev] [Next >] buttons, or the left/right arrow keys
    [Week/Month] button, or the w / m keys
    [Day] button, or the d key -- jumps to today in day view
    t  jumps back to today (stays in day view if already there)

Selection:
    hover a segment         see that row's activity, time, duration, note
    click a segment         select that bucket (or growth category), and
                            scroll the panel below to that exact row
    click a different row   switch the highlight, even within the same bucket
    click it again, or Esc  clear the selection

Selecting dims everything else, in the bars and in the index at once, so a
category can be compared straight across the week. The panel underneath then
breaks the selection down into the rows that make it up -- project, activity,
notes -- because the question "where did the day go" is usually followed by
"yes, but what was that actually".

This file is the entry point and nothing else; the chart lives in `timeviz/`,
whose __init__ maps the package. It stays a plain script at this path because
that is what `viz.bat` and the README both call.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from timeviz.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
