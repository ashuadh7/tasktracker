"""The growth ledger, drawn under the day it belongs to.

A second axes rather than a second window, because the sentence worth seeing
is a comparison: 45m of targeted work, but two hours of audiobook got in
anyway. Its minutes deliberately do not reconcile against the 24h bar -- a run
with a podcast on is one row up top and two down here.

Concurrent time is hatched: it rode along with something else and cost no
extra minutes. Solid means the growth *was* the activity.
"""

import pandas as pd
from matplotlib.patches import Patch

from ..selection import shade_for
from ..theme import (CATEGORY_COLOR, CATEGORY_TIER, GROWTH_COLOR, GROWTH_KEYS,
                     GROWTH_MODES, INK_2, MUTED, SURFACE, TIERS, ink_on)
from .base import LEGEND_GAP, LEGEND_GAP_TIGHT, StackedPanel


class StripPanel(StackedPanel):
    SOURCE = "growth"
    EDGE_WIDTH = 1.2
    LABEL_SIZE = 7
    LABEL_FLOOR = 60

    def draw(self, days, gdata, ledger, sel, roomy, day_labels=True):
        ax = self.ax
        self.begin(days, roomy)
        rows_by_key = ledger.rows_by_key(days)
        picked = sel.categories if sel else set()

        for key in GROWTH_KEYS:
            vals = [gdata.at[pd.Timestamp(d), key] / 60 for d in days]
            if not any(vals):
                continue
            category = key.split("|")[1]
            concurrent = key.endswith("|concurrent")
            fill = shade_for(sel, GROWTH_COLOR[key], category in picked)
            self.stack(key, vals, fill, ink_on(fill), rows_by_key,
                       ledger.growth, hatch="////" if concurrent else None)

        top = max(3.0, max(self._bottom) if self._bottom else 0)
        top = float(int(top) + (1 if top % 1 else 0))
        ax.set_ylim(0, top)
        step = 1 if top <= 4 else 2
        ax.set_yticks([h for h in range(0, int(top) + 1, step)])
        ax.set_yticklabels([f"{h}h" for h in range(0, int(top) + 1, step)],
                           fontsize=8, color=MUTED)
        self.finish_axes(days, day_labels, roomy)

        ax.set_ylabel("growth", fontsize=9, color=MUTED, labelpad=8)

        # Nine categories is too many to legend unconditionally, so only the
        # ones actually in this window get named.
        present = [c for _, cats in TIERS for c, _ in cats
                   if any(gdata[f"{CATEGORY_TIER[c]}|{c}|{m}"].sum()
                          for m in GROWTH_MODES)]
        handles = [Patch(facecolor=shade_for(sel, CATEGORY_COLOR[c],
                                             c in picked), label=c)
                   for c in present]
        if handles:
            handles.append(Patch(facecolor=SURFACE, edgecolor=MUTED,
                                 hatch="////", label="concurrent"))
            # Standing alone where the bars usually go, the strip is tall
            # enough to afford the roomier gap; every shorter slot it lands in
            # takes the tight one.
            tall = self.ax.get_position().height > 0.3
            ax.legend(handles=handles, loc="upper left",
                      bbox_to_anchor=(0, self.legend_anchor(
                          LEGEND_GAP if tall else LEGEND_GAP_TIGHT)),
                      ncol=6, frameon=False, fontsize=8.5, handlelength=1.1,
                      handleheight=1.1, columnspacing=1.4, labelcolor=INK_2)

        self.tooltip_artist()
