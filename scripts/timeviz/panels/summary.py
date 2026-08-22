"""The side index: the window's totals, and the surface you select from.

Reading top to bottom it answers three questions in order -- how much of the
planned work is actually done, where did the time go, and what did any of it
grow. Every row with a number beside it is clickable, which is what makes
this an index rather than a readout.
"""

from matplotlib.patches import Rectangle

from ..formats import MINUTES_PER_DAY, clock_hm, hm
from ..hits import BandHits
from ..selection import BUCKET, GROWTH, Selection, shade_for
from ..theme import (BUCKET_COLOR, BUCKET_ORDER, CATEGORY_COLOR, GRID,
                     GROWTH_KEYS, GROWTH_MODES, INK, INK_2, MUTED, SLOTS,
                     SLOT_BUCKET, TIERS, UNLOGGED_COLOR, blend)
from .base import Panel


class SummaryPanel(Panel):
    def __init__(self, fig, rect):
        super().__init__(fig, rect, axis_off=True)
        self.hits = BandHits()

    def hit(self, event):
        return self.hits.find(event.ydata)

    def draw(self, days, data, gdata, ledger, sel, mode):
        ax = self.ax
        ax.clear()
        ax.axis("off")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        self.hits.reset()

        n = len(days)
        totals = {b: 0 for b in BUCKET_ORDER}
        for slot in SLOTS:
            totals[SLOT_BUCKET[slot]] += data[slot].sum()
        logged = sum(totals.values())
        unlogged = max(0, n * MINUTES_PER_DAY - logged)
        # Averages are per *complete* day - dividing by calendar days would
        # report 0h46/night of sleep across a month with 4 days logged, and
        # counting a day logged only to 10am would drag every average down.
        per_day_total = data.sum(axis=1)
        n_logged = int((per_day_total >= MINUTES_PER_DAY).sum()) or 1
        n_partial = int(((per_day_total > 0) & (per_day_total < MINUTES_PER_DAY)).sum())

        picked = sel.buckets if sel else set()

        y = 0.988
        y = self._draw_completion(ax, ledger, y)

        if mode == "day":
            # n=1 breaks both halves of the usual line: "1 OF 1 DAYS LOGGED"
            # reads as an error when today just hasn't reached 1440 yet, and
            # the /day average below restates the number directly above it.
            # What actually answers "am I on track" here is how far into the
            # day the log already reaches.
            mins_today = int(per_day_total.iloc[0]) if len(per_day_total) else 0
            if mins_today >= MINUTES_PER_DAY:
                label = "day complete"
            else:
                label = f"{hm(mins_today) or '0h00'} logged · to {clock_hm(mins_today)}"
        else:
            label = f"{n_logged} OF {n} DAYS LOGGED"
            if n_partial:
                label += f"  ·  {n_partial} IN PROGRESS"
        ax.text(0, y, label, fontsize=8, color=MUTED)
        y -= 0.030

        for bucket in BUCKET_ORDER:
            mins = totals[bucket]
            if mins == 0:
                continue
            matches = bucket in picked
            on = not picked or matches
            ax.add_patch(Rectangle(
                (0, y - 0.012), 0.045, 0.012, clip_on=False,
                color=shade_for(sel, BUCKET_COLOR[bucket], matches)))
            ax.text(0.075, y - 0.010, bucket.replace("_", " "), fontsize=9,
                    color=INK_2 if on else blend(MUTED, 0.45),
                    fontweight="bold" if matches else "normal")
            ax.text(1, y - 0.010, hm(mins), fontsize=9,
                    color=INK if on else blend(MUTED, 0.45),
                    ha="right", fontfamily="monospace")
            if mode == "day":
                # A single day's own average is itself -- the line above.
                self.hits.add(Selection(BUCKET, bucket), y - 0.030, y)
                y -= 0.030
            else:
                ax.text(1, y - 0.027, f"{hm(mins / n_logged)}/day", fontsize=7.5,
                        color=MUTED if on else blend(MUTED, 0.55), ha="right")
                self.hits.add(Selection(BUCKET, bucket), y - 0.046, y)
                y -= 0.046

        # Never registered as a hit -- absent data isn't a category you can
        # select, which is what keeps this row inert while it still shows.
        if unlogged > 0:
            on = not picked
            ax.add_patch(Rectangle((0, y - 0.012), 0.045, 0.012,
                                   clip_on=False,
                                   color=shade_for(sel, UNLOGGED_COLOR, False)))
            ax.text(0.075, y - 0.010, "unlogged", fontsize=9,
                    color=MUTED if on else blend(MUTED, 0.45))
            ax.text(1, y - 0.010, hm(unlogged), fontsize=9,
                    color=MUTED if on else blend(MUTED, 0.45),
                    ha="right", fontfamily="monospace")
            y -= 0.046

        self._draw_growth(ax, days, gdata, ledger, sel, y)

    def _draw_completion(self, ax, ledger, y):
        """Percent-complete per project, rolled up from targets.csv +
        progress-log.csv -- see model.py's `target_progress`.

        Not clickable yet and not windowed by day/week/month, on purpose:
        a target's percent is a current state, not a per-range quantity, and
        drilling into a project's individual targets is a decision to make
        once the rollup itself has proven worth having on screen.
        """
        progress = ledger.target_progress()
        if not progress:
            return y  # nothing active - the rest of the index just starts higher

        ax.text(0, y, "COMPLETION", fontsize=8, color=MUTED)
        y -= 0.038

        for project in sorted(progress):
            pct, _ = progress[project]
            ax.text(0, y, project, fontsize=9, color=INK_2)
            ax.text(1, y, f"{pct:.0f}%", fontsize=9, color=INK,
                    ha="right", fontfamily="monospace")
            y -= 0.020
            bar_x, bar_w, bar_h = 0.0, 1.0, 0.009
            ax.add_patch(Rectangle((bar_x, y - bar_h), bar_w, bar_h,
                                   clip_on=False, color=UNLOGGED_COLOR))
            if pct:
                ax.add_patch(Rectangle(
                    (bar_x, y - bar_h), bar_w * pct / 100, bar_h,
                    clip_on=False, color=BUCKET_COLOR["targeted_work"]))
            y -= 0.030

        y -= 0.014
        ax.plot([0, 1], [y, y], color=GRID, linewidth=0.8)
        y -= 0.030
        return y

    def _draw_growth(self, ax, days, gdata, ledger, sel, y):
        window = ledger.growth_in(days)
        picked = sel.categories if sel else set()

        # The heading sits on the rule rather than below it -- the growth half
        # is a continuation of the same column, not a second panel.
        y -= 0.012
        ax.plot([0, 1], [y, y], color=GRID, linewidth=0.8)
        ax.text(0, y, "GROWTH", fontsize=8, color=MUTED)
        y -= 0.040

        total = gdata.to_numpy().sum()
        ax.text(0, y, hm(total) or "0h00", fontsize=22, color=INK, va="top")
        y -= 0.056

        if not total:
            ax.text(0, y, "nothing logged in this range", fontsize=9, color=MUTED)
            return

        free = sum(gdata[k].sum() for k in GROWTH_KEYS
                   if k.endswith("|concurrent"))
        ax.text(0, y, f"{hm(free) or '0h00'} rode along  ·  "
                      f"{hm(total - free) or '0h00'} was the activity",
                fontsize=8.5, color=INK_2)
        y -= 0.026
        # The tension worth watching: growth that displaced work rather than
        # filling time that was never going to be work anyway.
        leaked = 0
        if not window.empty:
            leaked = window[window["bucket"] == "slack"]["minutes"].sum()
        if leaked:
            ax.text(0, y, f"{hm(leaked)} of it logged as slack",
                    fontsize=8.5, color=BUCKET_COLOR["slack"])
        else:
            ax.text(0, y, "none of it logged as slack", fontsize=8.5, color=MUTED)
        y -= 0.032

        # Tier is the durable axis, so it gets the total; the categories under
        # it carry their own swatch because they have their own colour.
        for tier, cats in TIERS:
            per_cat = {c: sum(gdata[f"{tier}|{c}|{m}"].sum()
                              for m in GROWTH_MODES) for c, _ in cats}
            mins = sum(per_cat.values())
            if mins == 0:
                continue
            ax.text(0, y - 0.010, tier.upper(), fontsize=7.5, color=MUTED)
            ax.text(1, y - 0.010, hm(mins), fontsize=9, color=INK,
                    ha="right", fontfamily="monospace")
            y -= 0.026
            for cat, _ in cats:
                if per_cat[cat] == 0:
                    continue
                matches = cat in picked
                on = not picked or matches
                ax.add_patch(Rectangle(
                    (0.075, y - 0.010), 0.04, 0.010, clip_on=False,
                    color=shade_for(sel, CATEGORY_COLOR[cat], matches)))
                ax.text(0.145, y - 0.009, cat, fontsize=8.5,
                        color=INK_2 if on else blend(MUTED, 0.45),
                        fontweight="bold" if matches else "normal")
                ax.text(1, y - 0.009, hm(per_cat[cat]), fontsize=8.5,
                        color=INK_2 if on else blend(MUTED, 0.45),
                        ha="right", fontfamily="monospace")
                self.hits.add(Selection(GROWTH, cat), y - 0.024, y)
                y -= 0.024
