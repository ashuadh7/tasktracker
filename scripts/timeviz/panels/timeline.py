"""The selection placed on the clock, one row per day.

The stacked bar above answers "how much"; it deliberately says nothing about
when, because it is cumulative. This says when -- and time-of-day patterns
only show up when the days are stacked vertically and you can run your eye
down a column.
"""

import pandas as pd

from ..formats import ampm, hm, to_hours
from ..hits import LaneHits
from ..theme import (BASELINE, BUCKET_COLOR, GRID, INK_2, MUTED, SURFACE,
                     blend, ink_on)
from .base import Panel


class TimelinePanel(Panel):
    HOVERS = True
    # Rows sit 1.0 apart and are drawn 0.55 tall, so half a bar's height is
    # where one row stops being the one you meant.
    TOLERANCE = 0.275
    # Hours of margin past midnight, held clear of the clock for the day
    # totals. Wide enough for "(22h30 untimed)  24h00", the longest they get.
    GUTTER = 3.2

    def __init__(self, fig, rect):
        super().__init__(fig, rect)
        # Transposed against the stacked charts: the day is the y coordinate
        # here, and the span runs along x.
        self.hits = LaneHits(self.TOLERANCE)

    def hover_target(self, event):
        band = self.hits.find(event.ydata, event.xdata)
        # Every band here is one row -- untimed rows are never registered, so
        # there is no row-less band to filter out.
        return None if band is None else (band.row_id, band.key)

    def hit(self, event):
        return self.hits.find(event.ydata, event.xdata)

    def draw(self, days, ledger, sel, roomy):
        ax = self.ax
        ax.clear()
        ax.set_facecolor(SURFACE)

        if sel:
            frame = sel.rows(ledger, days)
            source = sel.source
            const_color = sel.color
            def color_of(row):
                return const_color
        else:
            # Day mode with nothing selected: every block for the one day,
            # each in its own bucket colour -- there's no selection to
            # narrow it to, and no need for one at n=1.
            frame = ledger.log_in(days)
            source = "log"
            def color_of(row):
                return BUCKET_COLOR[row["bucket"]]

        n = len(days)
        self.hits.reset(n)

        # A selection puts a handful of blocks on each row and leaves the rest
        # of it empty, so the day totals can be written inside the clock. With
        # nothing selected every block is drawn and the rows run wall to wall
        # -- there is no empty right edge to write into, and the totals would
        # land on top of whatever ran up to midnight. They get a margin past
        # midnight instead, and the clock gives up the width for it.
        gutter = 0.0 if sel else self.GUTTER
        total_x = 23.8 if sel else 24 + gutter
        untimed_x = 21.6 if sel else total_x - 1.0

        # A faint band per day, so empty days read as empty rather than absent.
        for i in range(n):
            if i % 2 == 0:
                ax.axhspan(i - 0.5, i + 0.5, color=blend(GRID, 0.45),
                           zorder=0, linewidth=0)

        untimed = {}
        totals = {}
        for i, day in enumerate(days):
            rows = frame[frame["date"] == pd.Timestamp(day)]
            totals[i] = int(rows["minutes"].sum())
            for row_id, row in rows.iterrows():
                start, end = row["start"], row["end"]
                if not start or not end:
                    untimed[i] = untimed.get(i, 0) + int(row["minutes"])
                    continue
                a = to_hours(start)
                b = to_hours(end)
                if b <= a:                     # a block that ends at midnight
                    b = 24.0
                color = color_of(row)
                ax.barh(i, b - a, left=a, height=0.55, color=color,
                        edgecolor=SURFACE, linewidth=0.8, zorder=3)
                self.hits.add(i, row_id, source, a, b)
                # A block trailing to midnight centres close enough to the
                # right margin to collide with the day total drawn there.
                if roomy and (b - a) >= 1.4 and b < 24.0:
                    ax.text((a + b) / 2, i, hm(row["minutes"]), ha="center",
                            va="center", fontsize=7, color=ink_on(color),
                            zorder=4)

        # The day's full total for this selection -- placed blocks plus any
        # untimed minutes -- so it agrees with the side panel, which is the
        # number it will be checked against. Untimed rows can't be placed on
        # the clock, so their share of the total is called out beside it,
        # secondary and to its left -- it only needs reading when it explains
        # a gap between the total and what's actually drawn. Both sit on one
        # baseline, not stacked, because a day row is too short to hold two
        # lines without them running together.
        #
        # Week/day only, like the inline per-block labels above: a month row
        # is a few pixels tall, nowhere near enough for text between
        # neighbours.
        if roomy:
            for i, mins in totals.items():
                if mins <= 0:
                    continue
                if i in untimed:
                    ax.text(untimed_x, i, f"({hm(untimed[i])} untimed)",
                            fontsize=6.5, color=MUTED, va="center",
                            ha="right", zorder=5)
                ax.text(total_x, i, hm(mins), fontsize=7.5, color=INK_2,
                        va="center", ha="right", zorder=5)

        ax.set_xlim(0, 24 + gutter)
        ax.set_ylim(n - 0.5, -0.5)             # first day at the top
        ax.set_xticks(range(0, 25, 3))
        ax.set_xticklabels([ampm(h) for h in range(0, 25, 3)],
                           fontsize=8, color=MUTED)
        ax.set_xticks(range(0, 25), minor=True)
        ax.set_yticks(range(n))
        if roomy:
            ax.set_yticklabels([f"{d:%a} {d.day}" for d in days],
                               fontsize=8, color=INK_2)
        else:
            ax.set_yticklabels([str(d.day) if d.day % 5 == 0 or d.day == 1
                                else "" for d in days],
                               fontsize=7, color=MUTED)
        ax.grid(axis="x", which="major", color=GRID, linewidth=0.8, zorder=1)
        ax.grid(axis="x", which="minor", color=blend(GRID, 0.6),
                linewidth=0.6, zorder=1)
        ax.set_axisbelow(False)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(BASELINE)
        ax.spines["bottom"].set_linewidth(0.8)
        # The axis line means "the clock", so it stops at midnight rather than
        # running on under the totals margin. A no-op when there is no margin.
        ax.spines["bottom"].set_bounds(0, 24)
        ax.tick_params(which="both", length=0)

        self.tooltip_artist()
