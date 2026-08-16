#!/usr/bin/env python3
"""Time tracker visualizer.

Stacked 24h bars, one per day, coloured by bucket, with the growth ledger
drawn as a companion strip beneath them.

    python viz.py              # opens on the current week
    python viz.py 2026-08-11   # opens on the week containing that date
    python viz.py --month      # start in month view
    python viz.py --png out.png            # render instead of opening a window
    python viz.py --png out.png --select slack   # render with slack selected

Navigation:
    [< Prev] [Next >] buttons, or the left/right arrow keys
    [Week/Month] button, or the w / m keys
    t  jumps back to today

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

Three things about the layout are load-bearing rather than decorative:

Sleep is drawn in three positions, not one. Days run midnight to midnight, so
a night that crosses midnight is two rows on two dates. The leading block is
pinned to the bottom of the bar and the trailing block to the very top, above
the unlogged grey -- which means one night reads as the top of Monday plus
the bottom of Tuesday, recoverable by eye without any arithmetic.

The growth strip is a second axes rather than a second window, because the
sentence worth seeing is a comparison: 45m of targeted work, but two hours of
audiobook got in anyway. Its minutes deliberately do not reconcile against
the 24h bar -- a run with a podcast on is one row up top and two down here.

Only targeted work is saturated. Everything you cannot not do is a
desaturated blue-grey that recedes. The ranking IS the palette.
"""

import calendar
import datetime as dt
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.widgets import Button

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csv_io

# The CSVs live one level up -- scripts/ holds code, the tracker root holds
# data, so the data is what you see when you open the folder.
DATA = Path(__file__).resolve().parent.parent
LOG_FILE = DATA / "time-log.csv"
OPEN_FILE = DATA / "open-day.csv"
PLAN_FILE = DATA / "plan.csv"
GROWTH_FILE = DATA / "growth-log.csv"

MINUTES_PER_DAY = 1440
MIDNIGHT = {"00:00", "24:00"}

# One hue, ranked by how much attention the category deserves. Targeted work
# is the only saturated colour on the chart. Changing a hex changes what the
# chart argues, so change them deliberately.
BUCKETS = [
    ("sleep", "#AAB8C5"),          # background   - pale blue-grey
    ("necessities", "#C2CFD9"),    # background   - palest blue-grey
    ("obligations", "#536578"),    # background   - dark muted navy-grey
    ("rest", "#9DB6CF"),           # tertiary     - soft dusty blue
    ("work", "#5B7DB1"),           # secondary    - medium slate-blue
    ("targeted_work", "#2563EB"),  # PRIMARY      - vivid cobalt
    ("slack", "#7C72B8"),          # secondary    - muted blue-violet
]
BUCKET_COLOR = dict(BUCKETS)
BUCKET_ORDER = [b for b, _ in BUCKETS]

# Stack order, bottom -> top. Sleep appears three times: the block that opens
# the day, naps in among everything else, and the block that closes it.
SLOTS = [
    "sleep_leading",
    "necessities", "obligations", "rest", "work", "targeted_work", "slack",
    "sleep_nap",
    "sleep_trailing",
]
SLOT_BUCKET = {s: ("sleep" if s.startswith("sleep_") else s) for s in SLOTS}

# Growth ledger. Each category carries its own colour, related within a tier
# but distinguishable -- so the strip reads as nine nameable things rather
# than three blocks you have to hover to identify.
TIERS = [
    ("reading", [("fiction", "#4F6F8F"),
                 ("non-fiction", "#7895AE"),
                 ("article", "#A9BDCD")]),
    ("audio", [("podcast", "#5F8583"),
               ("audiobook", "#91AAA7")]),
    ("self-care", [("self-improvement", "#786F8D"),
                   ("hobby", "#9B92AA"),
                   ("physical", "#718673"),
                   ("mental", "#9AAA9B")]),
]
TIER_ORDER = [t for t, _ in TIERS]
# The tier's darkest category stands in for it wherever one swatch is needed.
TIER_COLOR = {t: cats[0][1] for t, cats in TIERS}
GROWTH_MODES = ["concurrent", "dedicated"]

# Not a bucket - this is absent data, so it gets the faintest neutral there is.
UNLOGGED_COLOR = "#E5E7EB"

# Figure geometry. The main column and the side column; everything vertical
# is worked out in layout(), which depends on what is selected.
MAIN_L, MAIN_W = 0.055, 0.670
SIDE_L, SIDE_W = 0.760, 0.225
TOP, BOTTOM = 0.935, 0.072
FRAME = [MAIN_L, 0.5, MAIN_W, 0.2]        # placeholder, replaced on first draw
SIDE_FRAME = [SIDE_L, BOTTOM, SIDE_W, TOP - BOTTOM]

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"


def blend(hex_color, amount, toward=SURFACE):
    """Move a colour toward another. 0 = unchanged, 1 = fully `toward`."""
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(toward[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(
        round(x + (y - x) * amount) for x, y in zip(a, b))


def ink_on(hex_color):
    """Readable text colour for a fill. Half this palette is pale enough that
    white labels disappear into it, so the choice has to be computed."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return INK if luminance > 0.55 else "white"


GROWTH_KEYS = []          # stack order for the strip
GROWTH_COLOR = {}
CATEGORY_COLOR = {}
CATEGORY_TIER = {}
for _tier, _cats in TIERS:
    for _cat, _hex in _cats:
        CATEGORY_COLOR[_cat] = _hex
        CATEGORY_TIER[_cat] = _tier
        for _mode in GROWTH_MODES:
            _key = f"{_tier}|{_cat}|{_mode}"
            GROWTH_KEYS.append(_key)
            GROWTH_COLOR[_key] = _hex


def slot_of(row):
    """Which stack position a log row occupies."""
    if row["bucket"] != "sleep":
        return row["bucket"]
    start, end = row["start"], row["end"]
    if end in MIDNIGHT and start:
        return "sleep_trailing"
    if start == "00:00" or (not start and not end):
        return "sleep_leading"
    return "sleep_nap"


def read_log(path):
    """One time-log-shaped file as a DataFrame, decoded leniently and with
    start/end already zero-padded (see csv_io.py -- this is what tolerates a
    file last saved by Excel). Blank start/end stay blank, not 'nan'."""
    fieldnames, rows = csv_io.read_rows(path)
    if not fieldnames:
        return pd.DataFrame()
    frame = pd.DataFrame(rows, columns=fieldnames)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    for col in ("start", "end", "project", "activity", "notes"):
        if col in frame.columns:
            frame[col] = frame[col].fillna("").astype(str).str.strip()
    return frame


def load():
    """Read the log, plan and growth ledger. Missing optional files are fine.

    The open day is drawn alongside the sealed ones -- it shows as a partly
    filled bar with grey on top, which is what a day in progress actually is.
    It stays out of the per-day averages, though: dividing a week's sleep by a
    day that is only logged to 10am would understate every one of them.
    """
    log = read_log(LOG_FILE)
    log["sealed"] = True
    if OPEN_FILE.exists():
        opened = read_log(OPEN_FILE)
        if not opened.empty:
            opened["sealed"] = False
            log = pd.concat([log, opened], ignore_index=True)
    log["minutes"] = log["minutes"].astype(int)

    unknown = set(log["bucket"].unique()) - set(BUCKET_ORDER)
    if unknown:
        print(f"warning: unrecognised bucket(s) in time-log.csv: {sorted(unknown)}")
        print("         add them to BUCKETS (and re-validate colours) or fix the log")
    log["slot"] = log.apply(slot_of, axis=1)

    plan = read_log(PLAN_FILE)
    if not plan.empty:
        plan["minutes"] = plan["minutes"].astype(int)
    else:
        plan = pd.DataFrame(columns=["date", "minutes", "bucket", "project"])

    if GROWTH_FILE.exists():
        growth = read_log(GROWTH_FILE)
        if not growth.empty:
            growth["minutes"] = growth["minutes"].astype(int)
            growth["key"] = (growth["tier"] + "|" + growth["category"]
                             + "|" + growth["mode"])
    else:
        growth = pd.DataFrame(columns=["date", "minutes", "tier", "category",
                                       "mode", "bucket", "key"])
    return log, plan, growth


def row_order(frame, days, column_field):
    """day index -> column value -> ordered list of row ids (frame index),
    in the same order draw_detail lists them (`["date", "start"]`). This is
    what lets a stacked bar's hit registry point at a row instead of just the
    slot/key it belongs to."""
    out = {i: {} for i in range(len(days))}
    if frame.empty:
        return out
    day_pos = {pd.Timestamp(d): i for i, d in enumerate(days)}
    window = frame[frame["date"].isin(day_pos)].sort_values(["date", "start"])
    for row_id, row in window.iterrows():
        i = day_pos[row["date"]]
        out[i].setdefault(row[column_field], []).append(row_id)
    return out


def matrix(frame, days, columns, column_field):
    """days -> DataFrame indexed by date, one column per slot, in minutes."""
    stamps = pd.DatetimeIndex(days)
    out = pd.DataFrame(0, index=stamps, columns=columns)
    if frame.empty:
        return out
    window = frame[frame["date"].isin(stamps)]
    if not window.empty:
        pivot = window.pivot_table(
            index="date", columns=column_field, values="minutes",
            aggfunc="sum", fill_value=0,
        )
        for col in pivot.columns:
            if col in out.columns:
                out[col] = pivot[col].reindex(out.index, fill_value=0)
    return out


def to_hours(hhmm):
    """'10:33' -> 10.55. For placing a block on the clock."""
    h, m = hhmm.split(":")
    return int(h) + int(m) / 60


def hm(minutes):
    """540 -> '9h00'. Blank for zero."""
    minutes = int(round(minutes))
    if minutes == 0:
        return ""
    return f"{minutes // 60}h{minutes % 60:02d}"


def ampm(hour):
    """15 -> '3pm'. 0 and 24 both -> '12am' -- the axis runs midnight to
    midnight, so both ends of the timeline are the same instant."""
    hour = hour % 24
    period = "am" if hour < 12 else "pm"
    hour12 = hour % 12 or 12
    return f"{hour12}{period}"


def truncate(text, n):
    text = str(text or "").strip()
    return text if len(text) <= n else text[:n - 1] + "…"


class Viz:
    def __init__(self, log, plan, growth, anchor, mode="week", select=None):
        self.log, self.plan, self.growth = log, plan, growth
        self.anchor = anchor
        self.mode = mode
        # ("bucket", name) or ("growth", category), or None for no selection.
        self.sel = None
        if select:
            if select in BUCKET_ORDER:
                self.sel = ("bucket", select)
            elif select in CATEGORY_COLOR:
                self.sel = ("growth", select)

        self.fig = plt.figure(figsize=(15, 10), facecolor=SURFACE)
        self.fig.canvas.manager.set_window_title("Time tracker")
        # Positioned by hand in layout() rather than by a gridspec, because
        # selecting something rearranges the figure: the chart you did not
        # click gets out of the way and a timeline takes its place.
        self.ax = self.fig.add_axes(FRAME, facecolor=SURFACE)
        self.strip = self.fig.add_axes(FRAME, facecolor=SURFACE, sharex=self.ax)
        self.timeline = self.fig.add_axes(FRAME, facecolor=SURFACE)
        self.detail = self.fig.add_axes(FRAME, facecolor=SURFACE)
        self.detail.axis("off")
        self.side = self.fig.add_axes(SIDE_FRAME, facecolor=SURFACE)
        self.side.axis("off")

        # Hit-test geometry, rebuilt on every draw: day index -> list of
        # (row_id, key, bottom, top) in hours. row_id is None for spans with
        # no underlying row (the unlogged gap).
        self._bar_hits = {}
        self._strip_hits = {}
        # Timeline hit geometry: day index -> list of (row_id, source, lo, hi)
        # in clock hours. Only timed rows get an entry -- see draw_timeline.
        self._timeline_hits = {}
        # Side index rows: list of (("bucket", name) | ("growth", name), low, high)
        # in the side axes' own 0-1 fraction coordinates. Tier headings and the
        # unlogged row are never appended, which is what keeps them inert.
        self._side_hits = []
        # The detail list scrolls rather than changing shape when it is long.
        self._detail_offset = 0
        self._detail_total = 0
        # The row a click resolved to, highlighted in the detail list. Not
        # the same thing as self.sel: side-panel clicks select a whole
        # bucket/category with no specific row.
        self._selected_row = None

        # Hover tooltip. One annotation artist per chart axes, `animated` so
        # a normal canvas draw skips it -- which is what makes the bg cache
        # below a clean "no tooltip" snapshot to blit back over. Both dicts
        # are rebuilt every full draw(); see _on_draw_event and the bottom of
        # draw_bars/draw_strip/draw_timeline.
        self._tooltip = {}
        self._bg = {}
        self._hover_row = None
        self._hover_source = None
        self._hover_ax = None

        self._buttons = []
        for label, x, handler in (
            ("< Prev", 0.055, self.prev),
            ("Next >", 0.155, self.next),
            ("Week / Month", 0.265, self.toggle),
            ("Today", 0.400, self.today),
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

    # -- range -------------------------------------------------------------

    def days(self):
        if self.mode == "week":
            start = self.anchor - dt.timedelta(days=self.anchor.weekday())
            return [start + dt.timedelta(days=i) for i in range(7)]
        first = self.anchor.replace(day=1)
        n = calendar.monthrange(first.year, first.month)[1]
        return [first + dt.timedelta(days=i) for i in range(n)]

    def title(self):
        days = self.days()
        if self.mode == "week":
            a, b = days[0], days[-1]
            return (f"Week of {a:%a} {a:%b} {a.day} – "
                    f"{b:%a} {b:%b} {b.day}, {b.year}")
        return f"{days[0]:%B %Y}"

    # -- events ------------------------------------------------------------

    def step(self, direction):
        if self.mode == "week":
            self.anchor += dt.timedelta(days=7 * direction)
        else:
            first = self.anchor.replace(day=1)
            self.anchor = (
                (first + dt.timedelta(days=32)).replace(day=1) if direction > 0
                else (first - dt.timedelta(days=1)).replace(day=1)
            )
        self.draw()

    def prev(self, _=None):
        self.step(-1)

    def next(self, _=None):
        self.step(+1)

    def today(self, _=None):
        self.anchor = dt.date.today()
        self.draw()

    def toggle(self, _=None):
        self.mode = "month" if self.mode == "week" else "week"
        self.draw()

    def on_key(self, event):
        if event.key == "left":
            self.prev()
        elif event.key == "right":
            self.next()
        elif event.key in ("w", "m"):
            self.mode = "week" if event.key == "w" else "month"
            self.draw()
        elif event.key == "t":
            self.today()
        elif event.key == "escape" and self.sel:
            self.sel = None
            self._selected_row = None
            self._detail_offset = 0
            self.draw()

    def on_scroll(self, event):
        """Scroll the detail list. Anywhere over the lower panel.

        Manual scrolling is allowed even with a row highlighted -- the
        highlight stays where it is, including off screen, rather than
        snapping back. Auto-scroll only happens on selection."""
        if event.inaxes is not self.detail or not self.sel:
            return
        step = 1 if event.button == "down" else -1
        new = max(0, min(self._detail_offset + step,
                         max(0, self._detail_total - 1)))
        if new != self._detail_offset:
            self._detail_offset = new
            self.draw()

    def on_click(self, event):
        """Selection is a toggle: clicking the current selection clears it,
        and so does clicking a gap. A click that resolves to a specific row
        (bars, strip) also scrolls the detail list to that row and highlights
        it -- clicking a *different* row switches the highlight even when it
        is the same bucket, and only clicking the same row twice clears."""
        if event.xdata is None or event.ydata is None:
            return
        if event.inaxes is self.ax:
            hit = self._hit(self._bar_hits, event)
            row_id, key = hit if hit else (None, None)
            new = ("bucket", SLOT_BUCKET[key]) if key and key != "unlogged" else None
            self._apply_click(new, row_id)
        elif event.inaxes is self.strip:
            hit = self._hit(self._strip_hits, event)
            row_id, key = hit if hit else (None, None)
            new = ("growth", key.split("|")[1]) if key else None
            self._apply_click(new, row_id)
        elif event.inaxes is self.side:
            self._apply_click(self._side_hit(event), None)

    def _apply_click(self, new_sel, row_id):
        same_row = row_id is not None and row_id == self._selected_row
        same_no_row = row_id is None and new_sel == self.sel
        if new_sel is None or same_row or same_no_row:
            self.sel = None
            self._selected_row = None
            self._detail_offset = 0
        else:
            self.sel = new_sel
            self._selected_row = row_id
            self._scroll_to_selected_row()
        self.draw()

    def _scroll_to_selected_row(self):
        """Set _detail_offset so the newly selected row is on screen, with a
        line or two of context above it rather than pinned to the very top."""
        self._detail_offset = 0
        if self._selected_row is None or not self.sel:
            return
        frame, _, _ = self.selection_frame(self.days())
        if frame.empty:
            return
        order = list(frame.sort_values(["date", "start"]).index)
        try:
            pos = order.index(self._selected_row)
        except ValueError:
            return
        self._detail_offset = max(0, min(pos - 2, max(0, len(order) - 1)))

    def _hit(self, hits, event):
        idx = int(round(event.xdata))
        if idx not in hits or abs(event.xdata - idx) > 0.45:
            return None
        for row_id, key, low, high in hits[idx]:
            if low <= event.ydata < high:
                return row_id, key
        return None

    def _side_hit(self, event):
        for key, low, high in self._side_hits:
            if low <= event.ydata < high:
                return key
        return None

    def _timeline_hit(self, event):
        """(row_id, source) under the cursor in the timeline, or None. The
        timeline already draws one bar per row, so this is a direct lookup --
        no subdivision needed, unlike the two stacked charts."""
        if event.xdata is None or event.ydata is None:
            return None
        idx = int(round(event.ydata))
        if idx not in self._timeline_hits or abs(event.ydata - idx) > 0.275:
            return None
        for row_id, source, lo, hi in self._timeline_hits[idx]:
            if lo <= event.xdata < hi:
                return row_id, source
        return None

    def on_hover(self, event):
        """The side index doesn't look clickable otherwise -- a hand cursor
        over a live row is the whole discoverability fix."""
        from matplotlib.backend_tools import Cursors
        cursor = Cursors.POINTER
        if (event.inaxes is self.side and event.ydata is not None
                and self._side_hit(event) is not None):
            cursor = Cursors.HAND
        self.fig.canvas.set_cursor(cursor)
        self._update_hover(event)

    def _update_hover(self, event):
        """Resolve the cursor to a row (or nothing) and repaint the tooltip
        only if that row actually changed. Routing this through draw() would
        rebuild five axes and hundreds of text objects on every mouse move --
        instead this blits a single cached background plus one annotation."""
        ax = event.inaxes
        row_id = source = None
        if ax is self.ax:
            hit = self._hit(self._bar_hits, event)
            if hit and hit[0] is not None:
                row_id, source = hit[0], "log"
        elif ax is self.strip:
            hit = self._hit(self._strip_hits, event)
            if hit and hit[0] is not None:
                row_id, source = hit[0], "growth"
        elif ax is self.timeline:
            hit = self._timeline_hit(event)
            if hit is not None:
                row_id, source = hit

        if row_id == self._hover_row and ax is self._hover_ax:
            return

        prev_ax = self._hover_ax
        self._hover_row, self._hover_source, self._hover_ax = row_id, source, ax
        if prev_ax is not None and prev_ax is not ax:
            self._paint_tooltip(prev_ax, None, None, None)
        self._paint_tooltip(ax, row_id, source, event)

    def _paint_tooltip(self, ax, row_id, source, event):
        bg = self._bg.get(ax)
        artist = self._tooltip.get(ax)
        if bg is None or artist is None:
            return
        canvas = self.fig.canvas
        canvas.restore_region(bg)
        if row_id is not None:
            artist.xy = (event.xdata, event.ydata)
            artist.set_text(self._tooltip_text(row_id, source))
            artist.set_visible(True)
            ax.draw_artist(artist)
        else:
            artist.set_visible(False)
        canvas.blit(ax.bbox)

    def _tooltip_text(self, row_id, source):
        frame = self.log if source == "log" else self.growth
        row = frame.loc[row_id]
        when = (f"{row['start']}–{row['end']}"
                if row["start"] and row["end"] else "untimed")
        label = str(row.get("activity", ""))
        project = str(row.get("project", "") or "")
        if project:
            label = f"{project} · {label}"
        if source == "growth":
            label += f"  [{row['mode']} · {row['bucket']}]"
        lines = [truncate(label, 60),
                 f"{when}   {hm(row['minutes']) or '0h00'}"]
        note = truncate(row.get("notes", ""), 70)
        if note:
            lines.append(note)
        return "\n".join(lines)

    def _make_tooltip(self, ax):
        """One annotation per axes, invisible until hovered. `animated` is
        what excludes it from the normal canvas draw that _on_draw_event
        snapshots -- otherwise the cached background would have to be
        repainted to erase a stale tooltip drawn into it."""
        art = ax.annotate(
            "", xy=(0, 0), xytext=(14, 14), textcoords="offset points",
            fontsize=8, color=INK, va="top", ha="left", zorder=10,
            bbox=dict(boxstyle="round,pad=0.35", facecolor=SURFACE,
                      edgecolor=INK_2, linewidth=0.8, alpha=0.97),
            annotation_clip=False,
        )
        art.set_visible(False)
        art.set_animated(True)
        return art

    def _on_draw_event(self, event):
        """Snapshot a clean background per chart axes for hover blitting.
        Fires after every real canvas draw (draw_idle flushing, resize,
        savefig)."""
        self._bg = {}
        for a in (self.ax, self.strip, self.timeline):
            if a.get_visible():
                self._bg[a] = self.fig.canvas.copy_from_bbox(a.bbox)

    # -- selection helpers -------------------------------------------------

    def sel_bucket(self):
        return self.sel[1] if self.sel and self.sel[0] == "bucket" else None

    def sel_category(self):
        return self.sel[1] if self.sel and self.sel[0] == "growth" else None

    def shade_for(self, color, is_selected_kind, matches):
        """Full colour if it matches the selection or nothing is selected;
        faded most of the way to the surface otherwise."""
        if not self.sel or not is_selected_kind:
            return color
        return color if matches else blend(color, 0.80)

    # -- drawing -----------------------------------------------------------

    def layout(self):
        """Where the axes sit, which depends on what is selected.

        Unselected, both ledgers are on screen at once -- that comparison is
        the default question. Select something and the other ledger is not
        answering the question any more, so it gives up its space to a
        timeline of the selection.
        """
        kind = self.sel[0] if self.sel else None

        def place(ax, bottom, height, visible=True):
            ax.set_visible(visible)
            if visible:
                ax.set_position([MAIN_L, bottom, MAIN_W, height])

        if kind is None:
            place(self.ax, 0.425, TOP - 0.425)
            place(self.strip, 0.175, 0.155)
            place(self.timeline, 0, 0.01, visible=False)
            place(self.detail, BOTTOM, 0.045)
        else:
            top_ax = self.ax if kind == "bucket" else self.strip
            hidden = self.strip if kind == "bucket" else self.ax
            place(top_ax, 0.545, TOP - 0.545)
            place(hidden, 0, 0.01, visible=False)
            place(self.timeline, 0.315, 0.135)
            place(self.detail, BOTTOM, 0.205)

    def draw(self):
        days = self.days()
        data = matrix(self.log, days, SLOTS, "slot")
        gdata = matrix(self.growth, days, GROWTH_KEYS, "key")
        self.layout()
        kind = self.sel[0] if self.sel else None
        # The title belongs to the figure, not to the bars -- selecting a
        # growth category hides the bars entirely and the week still needs a
        # name.
        if not hasattr(self, "_title_text"):
            self._title_text = self.fig.text(MAIN_L, 0.962, "", fontsize=14,
                                             color=INK, fontweight="medium",
                                             va="center")
        self._title_text.set_text(self.title())
        # Whichever chart is on top carries the day labels; the one below it
        # is either hidden or has an axis of its own.
        if self.ax.get_visible():
            self.draw_bars(days, data, day_labels=kind == "bucket")
        if self.strip.get_visible():
            self.draw_strip(days, gdata, day_labels=kind != "bucket")
        if self.timeline.get_visible():
            self.draw_timeline(days)
        self.draw_summary(days, data, gdata)
        self.draw_detail(days)
        self.fig.canvas.draw_idle()

    def selection_frame(self, days):
        """The rows behind the current selection, and how to colour them."""
        kind, name = self.sel
        stamps = pd.DatetimeIndex(days)
        if kind == "bucket":
            frame = self.log[self.log["date"].isin(stamps)
                             & (self.log["bucket"] == name)]
            return frame, BUCKET_COLOR[name], name.replace("_", " ").upper()
        frame = self.growth[self.growth["date"].isin(stamps)
                            & (self.growth["category"] == name)]
        return (frame, CATEGORY_COLOR[name],
                f"{CATEGORY_TIER[name].upper()} · {name.upper()}")

    def draw_timeline(self, days):
        """The selection placed on the clock, one row per day.

        The stacked bar above answers "how much"; it deliberately says nothing
        about when, because it is cumulative. This says when -- and time-of-day
        patterns only show up when the days are stacked vertically and you can
        run your eye down a column.
        """
        ax = self.timeline
        ax.clear()
        ax.set_facecolor(SURFACE)

        frame, color, _ = self.selection_frame(days)
        source = "log" if self.sel[0] == "bucket" else "growth"
        n = len(days)
        week = self.mode == "week"
        self._timeline_hits = {i: [] for i in range(n)}

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
                ax.barh(i, b - a, left=a, height=0.55, color=color,
                        edgecolor=SURFACE, linewidth=0.8, zorder=3)
                self._timeline_hits[i].append((row_id, source, a, b))
                # A block trailing to midnight centres close enough to the
                # right margin to collide with the day total drawn there.
                if week and (b - a) >= 1.4 and b < 24.0:
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
        # Week-only, like the inline per-block labels above: a month row is a
        # few pixels tall, nowhere near enough for text between neighbours.
        if week:
            for i, mins in totals.items():
                if mins <= 0:
                    continue
                if i in untimed:
                    ax.text(21.6, i, f"({hm(untimed[i])} untimed)",
                            fontsize=6.5, color=MUTED, va="center",
                            ha="right", zorder=5)
                ax.text(23.8, i, hm(mins), fontsize=7.5, color=INK_2,
                        va="center", ha="right", zorder=5)

        ax.set_xlim(0, 24)
        ax.set_ylim(n - 0.5, -0.5)             # first day at the top
        ax.set_xticks(range(0, 25, 3))
        ax.set_xticklabels([ampm(h) for h in range(0, 25, 3)],
                           fontsize=8, color=MUTED)
        ax.set_xticks(range(0, 25), minor=True)
        ax.set_yticks(range(n))
        if week:
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
        ax.tick_params(which="both", length=0)

        self._tooltip[ax] = self._make_tooltip(ax)

    def draw_bars(self, days, data, day_labels=False):
        ax = self.ax
        ax.clear()
        ax.set_facecolor(SURFACE)
        self._bar_hits = {i: [] for i in range(len(days))}
        rows_by_day_slot = row_order(self.log, days, "slot")

        week = self.mode == "week"
        width = 0.62 if week else 0.74
        # A 2px surface gap between stacked segments, drawn as an edge in the
        # surface colour, so neighbouring fills never touch.
        edge = dict(edgecolor=SURFACE, linewidth=1.6)
        label_floor = 45 if week else 10_000  # month bars are too thin to label
        picked = self.sel_bucket()
        dimming = self.sel is not None

        x = range(len(days))
        bottom = [0.0] * len(days)

        def stack(key, vals, color, label_ink=None):
            bucket = SLOT_BUCKET.get(key, key)
            shown = self.shade_for(color, True, bucket == picked)
            ax.bar(x, vals, width, bottom=bottom, color=shown, zorder=3, **edge)
            ink = label_ink or ink_on(shown)
            if dimming and bucket != picked:
                ink = blend(MUTED, 0.35)
            for i, v in enumerate(vals):
                if v <= 0:
                    continue
                # The band is drawn as one segment (v hours) but hit-tested as
                # however many rows make it up, walked in stack order so their
                # sub-ranges tile it exactly -- the drawing never changes.
                row_ids = rows_by_day_slot.get(i, {}).get(key, [])
                lo = bottom[i]
                if row_ids:
                    for rid in row_ids:
                        hi = lo + self.log.at[rid, "minutes"] / 60
                        self._bar_hits[i].append((rid, key, lo, hi))
                        lo = hi
                else:
                    self._bar_hits[i].append((None, key, lo, bottom[i] + v))
                if v * 60 >= label_floor:
                    ax.text(i, bottom[i] + v / 2, hm(v * 60), ha="center",
                            va="center", fontsize=7.5, color=ink, zorder=4)
            for i, v in enumerate(vals):
                bottom[i] += v

        # Everything except the trailing sleep block, which has to sit above
        # the unlogged gap so the sleep sandwich survives a partial day.
        for slot in SLOTS:
            if slot == "sleep_trailing":
                continue
            vals = [data.at[pd.Timestamp(d), slot] / 60 for d in days]
            if any(vals):
                stack(slot, vals, BUCKET_COLOR[SLOT_BUCKET[slot]])

        trailing = [data.at[pd.Timestamp(d), "sleep_trailing"] / 60 for d in days]
        gap = [max(0.0, 24 - b - t) for b, t in zip(bottom, trailing)]
        if any(g > 0.02 for g in gap):
            stack("unlogged", gap, UNLOGGED_COLOR, label_ink=MUTED)
        if any(trailing):
            stack("sleep_trailing", trailing, BUCKET_COLOR["sleep"])

        ax.set_ylim(0, 24)
        ax.set_yticks(range(0, 25, 4))
        ax.set_yticklabels([f"{h}h" for h in range(0, 25, 4)],
                           fontsize=8.5, color=MUTED)
        ax.set_xlim(-0.7, len(days) - 0.3)
        ax.set_xticks(list(x))
        # ax and strip share an x-axis, which means set_xticklabels() sets a
        # *shared* formatter -- whichever axes calls it last wins for both.
        # Only the axes that should show labels ever sets them; the other
        # controls its own visibility with tick_params instead of touching
        # (and potentially blanking) content the other axes just set.
        if day_labels:
            if self.mode == "week":
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

        handles = []
        for b in BUCKET_ORDER:
            handles.append(Patch(
                facecolor=self.shade_for(BUCKET_COLOR[b], True, b == picked),
                label=b.replace("_", " ")))
        handles.append(Patch(
            facecolor=self.shade_for(UNLOGGED_COLOR, True, False),
            label="unlogged"))
        ax.legend(handles=handles, loc="upper left",
                  bbox_to_anchor=(0, -0.155 if day_labels else -0.02),
                  ncol=8, frameon=False, fontsize=8.5, handlelength=1.1,
                  handleheight=1.1, columnspacing=1.4, labelcolor=INK_2)

        self._tooltip[ax] = self._make_tooltip(ax)

    def draw_strip(self, days, gdata, day_labels=True):
        """The growth ledger, drawn under the day it belongs to.

        Concurrent time is hatched: it rode along with something else and cost
        no extra minutes. Solid means the growth *was* the activity.
        """
        ax = self.strip
        ax.clear()
        ax.set_facecolor(SURFACE)
        self._strip_hits = {i: [] for i in range(len(days))}
        rows_by_day_key = row_order(self.growth, days, "key")

        week = self.mode == "week"
        width = 0.62 if week else 0.74
        edge = dict(edgecolor=SURFACE, linewidth=1.2)
        label_floor = 60 if week else 10_000
        picked = self.sel_category()

        x = range(len(days))
        bottom = [0.0] * len(days)

        for key in GROWTH_KEYS:
            vals = [gdata.at[pd.Timestamp(d), key] / 60 for d in days]
            if not any(vals):
                continue
            category = key.split("|")[1]
            concurrent = key.endswith("|concurrent")
            shown = self.shade_for(GROWTH_COLOR[key], True, category == picked)
            ax.bar(x, vals, width, bottom=bottom, color=shown,
                   hatch="////" if concurrent else None, zorder=3, **edge)
            for i, v in enumerate(vals):
                if v <= 0:
                    continue
                row_ids = rows_by_day_key.get(i, {}).get(key, [])
                lo = bottom[i]
                if row_ids:
                    for rid in row_ids:
                        hi = lo + self.growth.at[rid, "minutes"] / 60
                        self._strip_hits[i].append((rid, key, lo, hi))
                        lo = hi
                else:
                    self._strip_hits[i].append((None, key, lo, bottom[i] + v))
                if v * 60 >= label_floor:
                    ax.text(i, bottom[i] + v / 2, hm(v * 60), ha="center",
                            va="center", fontsize=7, color=ink_on(shown),
                            zorder=4)
            bottom = [b + v for b, v in zip(bottom, vals)]

        top = max(3.0, max(bottom) if bottom else 0)
        top = float(int(top) + (1 if top % 1 else 0))
        ax.set_ylim(0, top)
        step = 1 if top <= 4 else 2
        ax.set_yticks([h for h in range(0, int(top) + 1, step)])
        ax.set_yticklabels([f"{h}h" for h in range(0, int(top) + 1, step)],
                           fontsize=8, color=MUTED)
        ax.set_xlim(-0.7, len(days) - 0.3)
        ax.set_xticks(list(x))
        # See the matching comment in draw_bars -- ax and strip share an
        # x-axis, so only the axes showing labels sets them; the other only
        # toggles its own visibility.
        if day_labels:
            if week:
                ax.set_xticklabels([f"{d:%a}\n{d:%b} {d.day}" for d in days],
                                   fontsize=9, color=INK_2)
            else:
                ax.set_xticklabels(
                    [str(d.day) if (d.day == 1 or d.day % 5 == 0) else ""
                     for d in days], fontsize=8, color=MUTED)

        ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(BASELINE)
            ax.spines[side].set_linewidth(0.8)
        ax.tick_params(labelbottom=day_labels, length=0)

        ax.set_ylabel("growth", fontsize=9, color=MUTED, labelpad=8)

        # Nine categories is too many to legend unconditionally, so only the
        # ones actually in this window get named.
        present = [c for _, cats in TIERS for c, _ in cats
                   if any(gdata[f"{CATEGORY_TIER[c]}|{c}|{m}"].sum()
                          for m in GROWTH_MODES)]
        handles = [Patch(facecolor=self.shade_for(CATEGORY_COLOR[c], True,
                                                  c == picked), label=c)
                   for c in present]
        if handles:
            handles.append(Patch(facecolor=SURFACE, edgecolor=MUTED,
                                 hatch="////", label="concurrent"))
            # Promoted to the top chart it is tall, so the same axes-fraction
            # offset would throw the legend off the figure.
            promoted = not self.ax.get_visible()
            ax.legend(handles=handles, loc="upper left",
                      bbox_to_anchor=(0, -0.155 if promoted else -0.26),
                      ncol=6, frameon=False, fontsize=8.5, handlelength=1.1,
                      handleheight=1.1, columnspacing=1.4, labelcolor=INK_2)

        self._tooltip[ax] = self._make_tooltip(ax)

    def draw_summary(self, days, data, gdata):
        ax = self.side
        ax.clear()
        ax.axis("off")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        self._side_hits = []

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

        planned = self.plan[
            self.plan["date"].isin(pd.DatetimeIndex(days))
            & (self.plan["bucket"] == "targeted_work")
        ]["minutes"].sum()
        actual = totals["targeted_work"]
        picked = self.sel_bucket()

        y = 0.988

        def rule(gap_before, gap_after):
            nonlocal y
            y -= gap_before
            ax.plot([0, 1], [y, y], color=GRID, linewidth=0.8)
            y -= gap_after

        ax.text(0, y, "TARGETED WORK", fontsize=8, color=MUTED)
        y -= 0.040
        ax.text(0, y, hm(actual) or "0h00", fontsize=22, color=INK, va="top")
        y -= 0.056
        if planned:
            pct = actual / planned * 100
            ax.text(0, y, f"of {hm(planned)} planned  ·  {pct:.0f}%",
                    fontsize=9, color=INK_2)
        else:
            ax.text(0, y, "no plan logged for this range", fontsize=9, color=MUTED)

        rule(0.036, 0.030)

        label = f"{n_logged} OF {n} DAYS LOGGED"
        if n_partial:
            label += f"  ·  {n_partial} IN PROGRESS"
        ax.text(0, y, label, fontsize=8, color=MUTED)
        y -= 0.030

        for bucket in BUCKET_ORDER:
            mins = totals[bucket]
            if mins == 0:
                continue
            on = picked is None or bucket == picked
            ax.add_patch(plt.Rectangle(
                (0, y - 0.012), 0.045, 0.012, clip_on=False,
                color=self.shade_for(BUCKET_COLOR[bucket], True, bucket == picked)))
            ax.text(0.075, y - 0.010, bucket.replace("_", " "), fontsize=9,
                    color=INK_2 if on else blend(MUTED, 0.45),
                    fontweight="bold" if bucket == picked else "normal")
            ax.text(1, y - 0.010, hm(mins), fontsize=9,
                    color=INK if on else blend(MUTED, 0.45),
                    ha="right", fontfamily="monospace")
            ax.text(1, y - 0.027, f"{hm(mins / n_logged)}/day", fontsize=7.5,
                    color=MUTED if on else blend(MUTED, 0.55), ha="right")
            self._side_hits.append((("bucket", bucket), y - 0.046, y))
            y -= 0.046

        if unlogged > 0:
            on = picked is None
            ax.add_patch(plt.Rectangle((0, y - 0.012), 0.045, 0.012,
                                       clip_on=False,
                                       color=self.shade_for(UNLOGGED_COLOR,
                                                            True, False)))
            ax.text(0.075, y - 0.010, "unlogged", fontsize=9,
                    color=MUTED if on else blend(MUTED, 0.45))
            ax.text(1, y - 0.010, hm(unlogged), fontsize=9,
                    color=MUTED if on else blend(MUTED, 0.45),
                    ha="right", fontfamily="monospace")
            y -= 0.046

        self.draw_growth_summary(ax, days, gdata, rule, y)

    def draw_growth_summary(self, ax, days, gdata, rule, y):
        window = self.growth
        if not window.empty:
            window = window[window["date"].isin(pd.DatetimeIndex(days))]
        picked = self.sel_category()

        rule(0.012, 0.028)

        ax.text(0, y - 0.012, "GROWTH", fontsize=8, color=MUTED)
        y -= 0.052

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
                on = picked is None or cat == picked
                ax.add_patch(plt.Rectangle(
                    (0.075, y - 0.010), 0.04, 0.010, clip_on=False,
                    color=self.shade_for(CATEGORY_COLOR[cat], True,
                                         cat == picked)))
                ax.text(0.145, y - 0.009, cat, fontsize=8.5,
                        color=INK_2 if on else blend(MUTED, 0.45),
                        fontweight="bold" if cat == picked else "normal")
                ax.text(1, y - 0.009, hm(per_cat[cat]), fontsize=8.5,
                        color=INK_2 if on else blend(MUTED, 0.45),
                        ha="right", fontfamily="monospace")
                self._side_hits.append((("growth", cat), y - 0.024, y))
                y -= 0.024

    def draw_detail(self, days):
        """What the selected segment is actually made of.

        Few enough rows and you get every one, with its notes. Too many and it
        collapses to one line per day -- a week of `necessities` is twenty-odd
        rows and nobody reads that, but "which days were heavy" is still worth
        seeing.
        """
        ax = self.detail
        ax.clear()
        ax.axis("off")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        if not self.sel:
            ax.text(0, 0.12, "click any segment to break it down  ·  "
                             "click it again or press Esc to clear",
                    fontsize=8.5, color=blend(MUTED, 0.25))
            return

        kind, _ = self.sel
        frame, color, heading = self.selection_frame(days)
        total = int(frame["minutes"].sum()) if not frame.empty else 0
        n_days = frame["date"].nunique() if not frame.empty else 0

        ax.add_patch(plt.Rectangle((0, 0.915), 0.008, 0.062, color=color,
                                   clip_on=False))
        ax.text(0.018, 0.920, heading, fontsize=9, color=INK,
                fontweight="bold")
        ax.text(max(0.15, 0.045 + len(heading) * 0.0092), 0.920,
                f"{hm(total) or '0h00'} across {n_days} day"
                f"{'' if n_days == 1 else 's'}",
                fontsize=8.5, color=MUTED)

        if frame.empty:
            ax.text(0, 0.78, "nothing in this range", fontsize=9, color=MUTED)
            return

        # Every row gets the same treatment, however many there are. Switching
        # format at a row count made a week of necessities look like a
        # different feature from a week of sleep; scrolling is the honest fix.
        rows = list(frame.sort_values(["date", "start"]).iterrows())
        self._detail_total = len(rows)
        first = min(self._detail_offset, max(0, len(rows) - 1))
        self._detail_offset = first

        y = 0.80
        i = first
        while i < len(rows):
            row_id, row = rows[i]
            note = truncate(row.get("notes", ""), 104)
            need = 0.145 if note else 0.092
            if y - need < -0.04:
                break
            if row_id == self._selected_row:
                # The row a click resolved to -- behind the text, not on top.
                ax.add_patch(plt.Rectangle(
                    (0, y - need + 0.018), 1, need, color=blend(color, 0.85),
                    zorder=0, clip_on=False))
            when = (f"{row['start']}–{row['end']}"
                    if row["start"] and row["end"] else "—")
            ax.text(0.0, y, f"{row['date']:%a %b %d}", fontsize=8.5,
                    color=INK_2, fontfamily="monospace")
            ax.text(0.105, y, when, fontsize=8.5, color=MUTED,
                    fontfamily="monospace")
            ax.text(0.20, y, hm(row["minutes"]), fontsize=8.5, color=INK,
                    fontfamily="monospace")
            label = str(row.get("activity", ""))
            project = str(row.get("project", "") or "")
            if project:
                label = f"{project} · {label}"
            if kind == "growth":
                label = f"{label}  [{row['mode']} · {row['bucket']}]"
            ax.text(0.27, y, truncate(label, 68), fontsize=8.5, color=INK)
            if note:
                ax.text(0.27, y - 0.058, note, fontsize=7.5, color=MUTED,
                        style="italic")
            y -= need
            i += 1

        if first > 0 or i < len(rows):
            ax.text(1.0, 0.920, f"{first + 1}–{i} of {len(rows)}  ·  scroll",
                    fontsize=7.5, color=MUTED, ha="right")


def main():
    args = sys.argv[1:]
    mode = "month" if "--month" in args else "week"
    png = select = None
    for flag in ("--png", "--select"):
        if flag in args:
            i = args.index(flag)
            value = args[i + 1] if i + 1 < len(args) else None
            args = args[:i] + args[i + 2:]
            if flag == "--png":
                png = value or "viz.png"
            else:
                select = value
    dates = [a for a in args if not a.startswith("--")]
    anchor = dt.date.fromisoformat(dates[0]) if dates else dt.date.today()

    log, plan, growth = load()
    viz = Viz(log, plan, growth, anchor, mode, select=select)
    if png:
        viz.fig.savefig(png, dpi=110, facecolor=SURFACE)
        print(f"wrote {png}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
