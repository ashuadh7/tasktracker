"""What every panel has in common: an axes, and for the charts, a stack.

`Panel` is one axes plus the hover machinery that goes with it. `StackedPanel`
adds the draw pass shared by the two stacked charts -- the bars and the growth
strip are the same chart with different vocabulary, and keeping that in one
place is most of why this package exists. What differs between them is
declared as class attributes and the handful of hooks below, so the difference
is readable as a list rather than by diffing two hundred lines.
"""

from ..formats import hm
from ..hits import LaneHits
from ..theme import BASELINE, GRID, INK, INK_2, MUTED, SURFACE


class Panel:
    # Whether this panel resolves the cursor to a row and shows a tooltip.
    HOVERS = False

    def __init__(self, fig, rect, sharex=None, axis_off=False):
        self.fig = fig
        self.ax = fig.add_axes(rect, facecolor=SURFACE, sharex=sharex)
        if axis_off:
            self.ax.axis("off")
        # Rebuilt on every full draw; see `tooltip_artist`.
        self.tooltip = None
        self.bg = None

    # -- placement ---------------------------------------------------------

    @property
    def visible(self):
        return self.ax.get_visible()

    def place(self, rect):
        self.ax.set_visible(True)
        self.ax.set_position(rect)

    def hide(self):
        self.ax.set_visible(False)

    # -- hover -------------------------------------------------------------

    def hover_target(self, event):
        """(row_id, source) under the cursor, or None."""
        return None

    def tooltip_artist(self):
        """One annotation per axes, invisible until hovered. `animated` is
        what excludes it from the normal canvas draw that `snapshot` captures
        -- otherwise the cached background would have to be repainted to erase
        a stale tooltip drawn into it.

        Called at the end of every draw because `ax.clear()` has just thrown
        the previous one away.
        """
        art = self.ax.annotate(
            "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
            fontsize=8, color=INK, va="top", ha="left", zorder=10,
            bbox=dict(boxstyle="round,pad=0.35", facecolor=SURFACE,
                      edgecolor=INK_2, linewidth=0.8, alpha=0.97),
            annotation_clip=False,
        )
        art.set_visible(False)
        art.set_animated(True)
        self.tooltip = art

    def snapshot(self):
        """Cache a clean, tooltip-free background to blit hover updates over."""
        self.bg = (self.fig.canvas.copy_from_bbox(self.ax.bbox)
                   if self.visible else None)

    def paint(self, text, event):
        """Repaint just this axes: the cached background, plus the tooltip if
        there is one. Routing hover through a full redraw would rebuild five
        axes and hundreds of text objects on every mouse move."""
        if self.bg is None or self.tooltip is None:
            return
        canvas = self.fig.canvas
        canvas.restore_region(self.bg)
        if text is not None:
            self.tooltip.xy = (event.xdata, event.ydata)
            self.tooltip.set_text(text)
            self.tooltip.set_visible(True)
            self.ax.draw_artist(self.tooltip)
        else:
            self.tooltip.set_visible(False)
        canvas.blit(self.ax.bbox)


class StackedPanel(Panel):
    """A day per column, categories stacked up it.

    Subclasses set the four constants, then drive a draw with
    `begin` -> `stack` per band -> `finish_axes`.
    """

    HOVERS = True
    # A 0.62-wide bar: within 0.45 of its centre is on it or in the gutter
    # beside it, and the gutters belong to nobody.
    TOLERANCE = 0.45
    # A ~2px surface gap between stacked segments, drawn as an edge in the
    # surface colour, so neighbouring fills never touch.
    EDGE_WIDTH = 1.6
    LABEL_SIZE = 7.5
    # Minutes below which a segment goes unlabelled, in week/day. Month bars
    # are too thin to label at any size.
    LABEL_FLOOR = 45
    SOURCE = "log"

    def __init__(self, fig, rect, sharex=None):
        super().__init__(fig, rect, sharex=sharex)
        self.hits = LaneHits(self.TOLERANCE)

    def hover_target(self, event):
        band = self.hits.find(event.xdata, event.ydata)
        if band is None or band.row_id is None:
            return None
        return band.row_id, self.SOURCE

    def hit(self, event):
        return self.hits.find(event.xdata, event.ydata)

    # -- draw --------------------------------------------------------------

    def begin(self, days, roomy):
        self.ax.clear()
        self.ax.set_facecolor(SURFACE)
        self.hits.reset(len(days))
        self._x = range(len(days))
        self._bottom = [0.0] * len(days)
        self._width = 0.62 if roomy else 0.74
        self._floor = self.LABEL_FLOOR if roomy else 10_000

    def stack(self, key, vals, fill, ink, rows_by_day, frame, hatch=None):
        """Draw one band across every day and register the rows behind it.

        The band is drawn as one segment (v hours) but hit-tested as however
        many rows make it up, walked in stack order so their sub-ranges tile
        it exactly -- the drawing never changes.
        """
        bottom = self._bottom
        self.ax.bar(self._x, vals, self._width, bottom=bottom, color=fill,
                    hatch=hatch, zorder=3, edgecolor=SURFACE,
                    linewidth=self.EDGE_WIDTH)
        for i, v in enumerate(vals):
            if v <= 0:
                continue
            row_ids = rows_by_day.get(i, {}).get(key, [])
            lo = bottom[i]
            if row_ids:
                for rid in row_ids:
                    hi = lo + frame.at[rid, "minutes"] / 60
                    self.hits.add(i, rid, key, lo, hi)
                    lo = hi
            else:
                self.hits.add(i, None, key, lo, bottom[i] + v)
            if v * 60 >= self._floor:
                self.ax.text(i, bottom[i] + v / 2, hm(v * 60), ha="center",
                             va="center", fontsize=self.LABEL_SIZE, color=ink,
                             zorder=4)
        for i, v in enumerate(vals):
            bottom[i] += v

    def finish_axes(self, days, day_labels, roomy):
        """The x-axis, grid and spines, identical on both stacked charts.

        The two share an x-axis, which means set_xticklabels() sets a *shared*
        formatter -- whichever axes calls it last wins for both. Only the axes
        that should show labels ever sets them; the other controls its own
        visibility with tick_params instead of touching (and potentially
        blanking) content the other axes just set.
        """
        ax = self.ax
        ax.set_xlim(-0.7, len(days) - 0.3)
        ax.set_xticks(list(self._x))
        if day_labels:
            if roomy:
                ax.set_xticklabels([f"{d:%a}\n{d:%b} {d.day}" for d in days],
                                   fontsize=9, color=INK_2)
            else:
                ax.set_xticklabels(
                    [str(d.day) if (d.day == 1 or d.day % 5 == 0) else ""
                     for d in days], fontsize=8, color=MUTED)
        ax.tick_params(labelbottom=day_labels, length=0)

        ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(BASELINE)
            ax.spines[side].set_linewidth(0.8)
