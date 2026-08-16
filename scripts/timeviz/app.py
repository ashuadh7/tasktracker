"""The figure and everything that changes it.

This is the shell: it owns the window, decides where the panels sit, routes
every event to one of them, and redraws. It holds exactly two pieces of state
of its own -- the window and the selection -- because everything else belongs
to a panel.

Selecting dims everything else, in the bars and in the index at once, so a
category can be compared straight across the week. The panel underneath then
breaks the selection down into the rows that make it up.
"""

import matplotlib.pyplot as plt
from matplotlib.widgets import Button

from .formats import tooltip_text
from .panels import (BarsPanel, DetailPanel, StripPanel, SummaryPanel,
                     TimelinePanel)
from .selection import BUCKET, GROWTH, Selection
from .theme import INK, INK_2, SLOT_BUCKET, SURFACE
from .window import Window

# Figure geometry. The main column and the side column; everything vertical
# is worked out in layout(), which depends on what is selected.
MAIN_L, MAIN_W = 0.055, 0.670
SIDE_L, SIDE_W = 0.760, 0.225
TOP, BOTTOM = 0.935, 0.072
FRAME = [MAIN_L, 0.5, MAIN_W, 0.2]        # placeholder, replaced on first draw
SIDE_FRAME = [SIDE_L, BOTTOM, SIDE_W, TOP - BOTTOM]


class Viz:
    def __init__(self, ledger, anchor, mode="week", select=None):
        self.ledger = ledger
        self.window = Window(anchor, mode)
        self.sel = Selection.parse(select) if select else None

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
        twice clears. The timeline only ever shows rows already inside the
        current selection, so a click there never changes self.sel itself --
        only which row is highlighted."""
        if event.xdata is None or event.ydata is None:
            return
        if event.inaxes is self.bars.ax:
            band = self.bars.hit(event)
            key = band.key if band else None
            new = (Selection(BUCKET, SLOT_BUCKET[key])
                   if key and key != "unlogged" else None)
            self._apply_click(new, band.row_id if band else None)
        elif event.inaxes is self.strip.ax:
            band = self.strip.hit(event)
            new = Selection(GROWTH, band.key.split("|")[1]) if band else None
            self._apply_click(new, band.row_id if band else None)
        elif event.inaxes is self.timeline.ax:
            band = self.timeline.hit(event)
            self._apply_click(self.sel, band.row_id if band else None)
        elif event.inaxes is self.side.ax:
            band = self.side.hit(event)
            self._apply_click(band.key if band else None, None)

    def clear(self):
        self.sel = None
        self.detail.selected_row = None
        self.detail.offset = 0

    def _apply_click(self, new_sel, row_id):
        same_row = row_id is not None and row_id == self.detail.selected_row
        same_no_row = row_id is None and new_sel == self.sel
        if new_sel is None or same_row or same_no_row:
            self.clear()
        else:
            self.sel = new_sel
            self.detail.selected_row = row_id
            self.detail.scroll_to_selected(self.ledger, self.sel,
                                           self.window.days())
        self.draw()

    # -- hover -------------------------------------------------------------

    def on_hover(self, event):
        """The side index doesn't look clickable otherwise -- a hand cursor
        over a live row is the whole discoverability fix."""
        from matplotlib.backend_tools import Cursors
        cursor = Cursors.POINTER
        if (event.inaxes is self.side.ax and event.ydata is not None
                and self.side.hit(event) is not None):
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
                row = self.ledger.frame_for(source).loc[row_id]
                text = tooltip_text(row, source == "growth")
            panel.paint(text, event)

    def _on_draw_event(self, event):
        """Snapshot a clean background per chart axes for hover blitting.
        Fires after every real canvas draw (draw_idle flushing, resize,
        savefig)."""
        for panel in (self.bars, self.strip, self.timeline):
            panel.snapshot()

    # -- drawing -----------------------------------------------------------

    def layout(self):
        """Where the axes sit, which depends on what is selected.

        Unselected, both ledgers are on screen at once -- that comparison is
        the default question. Select something and the other ledger is not
        answering the question any more, so it gives up its space to a
        timeline of the selection.
        """
        kind = self.sel.kind if self.sel else None

        if kind is None and self.window.mode == "day":
            # A day has no second ledger column to show alongside the bar --
            # growth already has its own readout in the side panel -- so the
            # freed space goes to the clock timeline instead, showing every
            # block rather than just a selection.
            self.bars.place([MAIN_L, 0.545, MAIN_W, TOP - 0.545])
            self.strip.hide()
            self.timeline.place([MAIN_L, 0.315, MAIN_W, 0.135])
            self.detail.place([MAIN_L, BOTTOM, MAIN_W, 0.205])
        elif kind is None:
            self.bars.place([MAIN_L, 0.425, MAIN_W, TOP - 0.425])
            self.strip.place([MAIN_L, 0.175, MAIN_W, 0.155])
            self.timeline.hide()
            self.detail.place([MAIN_L, BOTTOM, MAIN_W, 0.045])
        else:
            top, hidden = ((self.bars, self.strip) if kind == BUCKET
                           else (self.strip, self.bars))
            top.place([MAIN_L, 0.545, MAIN_W, TOP - 0.545])
            hidden.hide()
            self.timeline.place([MAIN_L, 0.315, MAIN_W, 0.135])
            self.detail.place([MAIN_L, BOTTOM, MAIN_W, 0.205])

    def draw(self):
        days = self.window.days()
        data = self.ledger.day_matrix(days)
        gdata = self.ledger.growth_matrix(days)
        self.layout()
        kind = self.sel.kind if self.sel else None
        roomy = self.window.roomy
        # The title belongs to the figure, not to the bars -- selecting a
        # growth category hides the bars entirely and the week still needs a
        # name.
        if not hasattr(self, "_title_text"):
            self._title_text = self.fig.text(MAIN_L, 0.962, "", fontsize=14,
                                             color=INK, fontweight="medium",
                                             va="center")
        self._title_text.set_text(self.window.title())
        # Whichever chart is on top carries the day labels; the one below it
        # is either hidden or has an axis of its own.
        if self.bars.visible:
            promoted = kind == BUCKET or (kind is None
                                          and self.window.mode == "day")
            self.bars.draw(days, data, self.ledger, self.sel, roomy,
                           day_labels=promoted)
        if self.strip.visible:
            self.strip.draw(days, gdata, self.ledger, self.sel, roomy,
                            day_labels=kind != BUCKET,
                            promoted=not self.bars.visible)
        if self.timeline.visible:
            self.timeline.draw(days, self.ledger, self.sel, roomy)
        self.side.draw(days, data, gdata, self.ledger, self.sel,
                       self.window.mode)
        self.detail.draw(days, self.ledger, self.sel)
        self.fig.canvas.draw_idle()
