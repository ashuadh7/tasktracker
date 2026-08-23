"""The figure and everything that changes it.

This is the shell: it owns the window, decides where the panels sit, routes
every event to one of them, and redraws. It holds exactly two pieces of state
of its own -- the window and the selection -- because everything else belongs
to a panel.

The clock timeline is the permanent primary chart: always on screen, one row
per day, the day's blocks placed where they actually sit on the clock. Issue
#5 ran this arrangement against the older one (stacked bars on top, timeline
conjured only by a selection) for real and settled on this one -- time-of-day
patterns read in one glance here and are invisible in any stacked view.

Selecting dims everything else, in the bars and in the index at once, so a
category can be compared straight across the week. The panel underneath then
breaks the selection down into the rows that make it up.
"""

import matplotlib.pyplot as plt
from matplotlib.widgets import Button

from .formats import tooltip_text
from .panels import (BarsPanel, DetailPanel, StripPanel, SummaryPanel,
                     TimelinePanel)
from .selection import BUCKET, GROWTH, TARGET, Selection
from .theme import INK, INK_2, SLOT_BUCKET, SURFACE, day_tag_colors
from .window import Window

# Figure geometry. The main column and the side column; everything vertical
# is worked out in layout(), which depends on what is selected.
MAIN_L, MAIN_W = 0.055, 0.670
SIDE_L, SIDE_W = 0.760, 0.225
TOP, BOTTOM = 0.935, 0.072
FRAME = [MAIN_L, 0.5, MAIN_W, 0.2]        # placeholder, replaced on first draw
SIDE_FRAME = [SIDE_L, BOTTOM, SIDE_W, TOP - BOTTOM]


class Viz:
    def __init__(self, ledger, anchor, mode="week", select=None, day_tags=None):
        self.ledger = ledger
        self.window = Window(anchor, mode)
        self.sel = Selection.parse(select) if select else None
        # Optional, schema-external: date -> tag, from --day-tags. Colours
        # are assigned on load since the tracker never knows the vocabulary
        # ahead of time.
        self.day_tags = day_tags or {}
        self.day_tag_colors = day_tag_colors(self.day_tags.values())

        self.fig = plt.figure(figsize=(15, 10), facecolor=SURFACE)
        self.fig.canvas.manager.set_window_title("Time tracker")
        # Positioned by hand in layout() rather than by a gridspec, because
        # selecting something rearranges the figure: the chart you did not
        # click gets out of the way and a timeline takes its place.
        self.bars = BarsPanel(self.fig, FRAME)
        self.strip = StripPanel(self.fig, FRAME, sharex=self.bars.ax)
        self.timeline = TimelinePanel(self.fig, FRAME)
        self.detail = DetailPanel(self.fig, FRAME)
        self.side = SummaryPanel(self.fig, SIDE_FRAME)

        self._hover_row = None
        self._hover_ax = None

        self._buttons = []
        for label, x, handler in (
            ("< Prev", 0.055, self.prev),
            ("Next >", 0.155, self.next),
            ("Week / Month", 0.265, self.toggle),
            ("Today", 0.400, self.today),
            ("Day", 0.510, self.day),
        ):
            axb = self.fig.add_axes([x, 0.012, 0.09, 0.034])
            btn = Button(axb, label, color="#f0efec", hovercolor="#e1e0d9")
            btn.label.set_fontsize(9)
            btn.label.set_color(INK_2)
            btn.on_clicked(handler)
            self._buttons.append(btn)

        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.fig.canvas.mpl_connect("scroll_event", self.on_scroll)
        self.fig.canvas.mpl_connect("motion_notify_event", self.on_hover)
        self.fig.canvas.mpl_connect("draw_event", self._on_draw_event)
        self.draw()

    # -- navigation --------------------------------------------------------

    def prev(self, _=None):
        self.window.step(-1)
        self.draw()

    def next(self, _=None):
        self.window.step(+1)
        self.draw()

    def today(self, _=None):
        self.window.go_today()
        self.draw()

    def day(self, _=None):
        self.window.go_day()
        self.draw()

    def toggle(self, _=None):
        self.window.toggle()
        self.draw()

    # -- events ------------------------------------------------------------

    def on_key(self, event):
        if event.key == "left":
            self.prev()
        elif event.key == "right":
            self.next()
        elif event.key in ("w", "m"):
            self.window.mode = "week" if event.key == "w" else "month"
            self.draw()
        elif event.key == "d":
            self.day()
        elif event.key == "t":
            self.today()
        elif event.key == "escape" and self.sel:
            self.clear()
            self.draw()

    def on_scroll(self, event):
        """Scroll the detail list. Anywhere over the lower panel."""
        if event.inaxes is not self.detail.ax or not self.sel:
            return
        if self.detail.scroll(1 if event.button == "down" else -1):
            self.draw()

    def on_click(self, event):
        """Selection is a toggle: clicking the current selection clears it,
        and so does clicking a gap. A click that resolves to a specific row
        (bars, strip, timeline) also scrolls the detail list to that row and
        highlights it -- clicking a *different* row switches the highlight
        even when it is the same bucket, and only clicking the same row
        twice clears.

        Shift-click adds or removes one name from the selection instead of
        replacing it -- see `Selection.toggled`."""
        if event.xdata is None or event.ydata is None:
            return
        shift = event.key == "shift"
        if event.inaxes is self.bars.ax:
            band = self.bars.hit(event)
            key = band.key if band else None
            new = (Selection(BUCKET, SLOT_BUCKET[key])
                   if key and key != "unlogged" else None)
            self._apply_click(new, band.row_id if band else None, shift)
        elif event.inaxes is self.strip.ax:
            band = self.strip.hit(event)
            new = Selection(GROWTH, band.key.split("|")[1]) if band else None
            self._apply_click(new, band.row_id if band else None, shift)
        elif event.inaxes is self.timeline.ax:
            band = self.timeline.hit(event)
            self._apply_click(self._from_timeline(band),
                              band.row_id if band else None, shift)
        elif event.inaxes is self.side.ax:
            idx = self.side.completion_at(event)
            if idx is not None:
                _, name = self.side.target_key(idx)
                self._apply_click(Selection(TARGET, name), None, shift)
                return
            band = self.side.hit(event)
            self._apply_click(band.key if band else None, None, shift)

    def _from_timeline(self, band):
        """What a click on the timeline selects.

        With something already selected the timeline is only showing rows from
        inside it, so the click can't mean a new selection -- it just moves the
        highlight. With nothing selected the timeline is the primary chart and
        is showing the whole log, so clicking a block there means what
        clicking it on the bar means: select its bucket.
        """
        if self.sel is not None or band is None:
            return self.sel
        return Selection(BUCKET, self.ledger.log.at[band.row_id, "bucket"])

    def clear(self):
        self.sel = None
        self.detail.selected_row = None
        self.detail.offset = 0

    def _apply_click(self, new_sel, row_id, shift=False):
        if shift and new_sel is not None:
            self._select(new_sel if self.sel is None
                        else self.sel.toggled(new_sel.kind, new_sel.names[0]),
                        row_id)
            self.draw()
            return

        same_row = row_id is not None and row_id == self.detail.selected_row
        same_no_row = row_id is None and new_sel == self.sel
        if new_sel is None or same_row or same_no_row:
            self.clear()
        else:
            self._select(new_sel, row_id)
        self.draw()

    def _select(self, sel, row_id):
        if sel is None:
            self.clear()
            return
        self.sel = sel
        self.detail.selected_row = row_id
        self.detail.scroll_to_selected(self.ledger, self.sel,
                                       self.window.days())

    # -- hover -------------------------------------------------------------

    def on_hover(self, event):
        """The side index doesn't look clickable otherwise -- a hand cursor
        over a live row is the whole discoverability fix."""
        from matplotlib.backend_tools import Cursors
        cursor = Cursors.POINTER
        if (event.inaxes is self.side.ax and event.ydata is not None
                and (self.side.hit(event) is not None
                     or self.side.completion_at(event) is not None)):
            cursor = Cursors.HAND
        self.fig.canvas.set_cursor(cursor)
        self._update_hover(event)

    def _panel_at(self, ax):
        for panel in (self.bars, self.strip, self.timeline, self.detail,
                      self.side):
            if panel.ax is ax:
                return panel
        return None

    def _update_hover(self, event):
        """Resolve the cursor to a row (or nothing) and repaint the tooltip
        only if that row actually changed."""
        ax = event.inaxes
        panel = self._panel_at(ax)
        row_id = source = None
        if panel is not None and panel.HOVERS:
            target = panel.hover_target(event)
            if target is not None:
                row_id, source = target

        if row_id == self._hover_row and ax is self._hover_ax:
            return

        prev, prev_ax = self._panel_at(self._hover_ax), self._hover_ax
        self._hover_row, self._hover_ax = row_id, ax
        if prev is not None and prev_ax is not ax:
            prev.paint(None, None)
        if panel is not None:
            text = None
            if row_id is not None:
                if source == "target":
                    # Not a log/growth row -- a joined targets.csv +
                    # progress-log.csv figure the panel already built while
                    # drawing the completion bars, so it owns the text too.
                    text = panel.target_tooltip(row_id)
                else:
                    row = self.ledger.frame_for(source).loc[row_id]
                    text = tooltip_text(row, source == "growth")
            panel.paint(text, event)

    def _on_draw_event(self, event):
        """Snapshot a clean background per chart axes for hover blitting.
        Fires after every real canvas draw (draw_idle flushing, resize,
        savefig)."""
        for panel in (self.bars, self.strip, self.timeline, self.side):
            panel.snapshot()

    # -- drawing -----------------------------------------------------------

    def layout(self):
        """Where the axes sit, which depends on what is selected.

        The clock timeline is always on top, full width, and never moves.
        Beneath it: unselected, both ledgers are on screen at once -- that
        comparison is the default question. Select something and the other
        ledger is not answering the question any more, so it gives up its
        space to the selected one, promoted and given the row list below it.
        """
        kind = self.sel.kind if self.sel else None
        self.timeline.place([MAIN_L, 0.590, MAIN_W, TOP - 0.590])

        if kind is None and self.window.mode != "day":
            self.bars.place([MAIN_L, 0.325, MAIN_W, 0.215])
            self.strip.place([MAIN_L, 0.180, MAIN_W, 0.100])
            self.detail.place([MAIN_L, BOTTOM, MAIN_W, 0.045])
        elif kind is None:
            # A day has no second ledger column to show alongside the bar --
            # growth already has its own readout in the side panel.
            self.bars.place([MAIN_L, 0.345, MAIN_W, 0.195])
            self.strip.hide()
            self.detail.place([MAIN_L, BOTTOM, MAIN_W, 0.185])
        else:
            # A target selection is log-sourced (see selection.py), so it
            # gets the same top slot a bucket selection would.
            top, hidden = ((self.bars, self.strip) if kind in (BUCKET, TARGET)
                           else (self.strip, self.bars))
            top.place([MAIN_L, 0.345, MAIN_W, 0.195])
            hidden.hide()
            self.detail.place([MAIN_L, BOTTOM, MAIN_W, 0.185])

    def _lowest_stacked(self):
        """The bottom-most visible stacked chart, or None if neither is up.

        Whichever it is carries the day labels the two share an x-axis for --
        strip when both are up, since it always sits under bars; whichever one
        is left when a selection hides the other.
        """
        shown = [p for p in (self.bars, self.strip) if p.visible]
        return min(shown, key=lambda p: p.ax.get_position().y0, default=None)

    def draw(self):
        days = self.window.days()
        data = self.ledger.day_matrix(days)
        gdata = self.ledger.growth_matrix(days)
        self.layout()
        roomy = self.window.roomy
        # The title belongs to the figure, not to the bars -- selecting a
        # growth category hides the bars entirely and the week still needs a
        # name.
        if not hasattr(self, "_title_text"):
            self._title_text = self.fig.text(MAIN_L, 0.962, "", fontsize=14,
                                             color=INK, fontweight="medium",
                                             va="center")
        self._title_text.set_text(self.window.title())
        # The two stacked charts share an x-axis, so exactly one of them may
        # carry the day labels: whichever one is lower on screen.
        labelled = self._lowest_stacked()
        if self.bars.visible:
            self.bars.draw(days, data, self.ledger, self.sel, roomy,
                           day_labels=labelled is self.bars)
        if self.strip.visible:
            self.strip.draw(days, gdata, self.ledger, self.sel, roomy,
                            day_labels=labelled is self.strip)
        if self.timeline.visible:
            self.timeline.draw(days, self.ledger, self.sel, roomy,
                               day_tags=self.day_tags,
                               day_tag_colors=self.day_tag_colors)
        self.side.draw(days, data, gdata, self.ledger, self.sel,
                       self.window.mode)
        self.detail.draw(days, self.ledger, self.sel)
        self.fig.canvas.draw_idle()
