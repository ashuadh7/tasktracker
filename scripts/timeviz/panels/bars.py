"""The 24h bars: one per day, stacked by bucket.

Sleep is drawn in three positions, not one. Days run midnight to midnight, so
a night that crosses midnight is two rows on two dates. The leading block is
pinned to the bottom of the bar and the trailing block to the very top, above
the unlogged grey -- which means one night reads as the top of Monday plus
the bottom of Tuesday, recoverable by eye without any arithmetic.
"""

import pandas as pd
from matplotlib.patches import Patch

from ..selection import shade_for
from ..theme import (BUCKET_COLOR, BUCKET_ORDER, INK_2, MUTED, SLOTS,
                     SLOT_BUCKET, UNLOGGED_COLOR, blend, ink_on)
from .base import LEGEND_GAP, LEGEND_GAP_FLUSH, StackedPanel


class BarsPanel(StackedPanel):
    SOURCE = "log"

    def draw(self, days, data, ledger, sel, roomy, day_labels=False):
        ax = self.ax
        self.begin(days, roomy)
        rows_by_slot = ledger.rows_by_slot(days)
        picked = sel.bucket if sel else None

        def stack(key, vals, color, label_ink=None):
            bucket = SLOT_BUCKET.get(key, key)
            fill = shade_for(sel, color, bucket == picked)
            ink = label_ink or ink_on(fill)
            if sel is not None and bucket != picked:
                ink = blend(MUTED, 0.35)
            self.stack(key, vals, fill, ink, rows_by_slot, ledger.log)

        # Everything except the trailing sleep block, which has to sit above
        # the unlogged gap so the sleep sandwich survives a partial day.
        for slot in SLOTS:
            if slot == "sleep_trailing":
                continue
            vals = [data.at[pd.Timestamp(d), slot] / 60 for d in days]
            if any(vals):
                stack(slot, vals, BUCKET_COLOR[SLOT_BUCKET[slot]])

        trailing = [data.at[pd.Timestamp(d), "sleep_trailing"] / 60 for d in days]
        gap = [max(0.0, 24 - b - t) for b, t in zip(self._bottom, trailing)]
        if any(g > 0.02 for g in gap):
            stack("unlogged", gap, UNLOGGED_COLOR, label_ink=MUTED)
        if any(trailing):
            stack("sleep_trailing", trailing, BUCKET_COLOR["sleep"])

        ax.set_ylim(0, 24)
        ax.set_yticks(range(0, 25, 4))
        ax.set_yticklabels([f"{h}h" for h in range(0, 25, 4)],
                           fontsize=8.5, color=MUTED)
        self.finish_axes(days, day_labels, roomy)

        handles = []
        for b in BUCKET_ORDER:
            handles.append(Patch(
                facecolor=shade_for(sel, BUCKET_COLOR[b], b == picked),
                label=b.replace("_", " ")))
        handles.append(Patch(
            facecolor=shade_for(sel, UNLOGGED_COLOR, False), label="unlogged"))
        ax.legend(handles=handles, loc="upper left",
                  bbox_to_anchor=(0, self.legend_anchor(
                      LEGEND_GAP if day_labels else LEGEND_GAP_FLUSH)),
                  ncol=8, frameon=False, fontsize=8.5, handlelength=1.1,
                  handleheight=1.1, columnspacing=1.4, labelcolor=INK_2)

        self.tooltip_artist()
