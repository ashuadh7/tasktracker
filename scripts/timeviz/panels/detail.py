"""What the selected segment is actually made of.

Every row gets the same treatment, however many there are. Switching format at
a row count made a week of necessities look like a different feature from a
week of sleep; scrolling is the honest fix.

"Where did the day go" is usually followed by "yes, but what was that
actually", which is the question this panel exists to answer -- project,
activity, notes, one line each.
"""

from matplotlib.patches import Rectangle

from ..formats import hm, row_label, truncate
from ..theme import BUCKET_COLOR, CATEGORY_COLOR, INK, INK_2, MUTED, blend
from .base import Panel


class DetailPanel(Panel):
    def __init__(self, fig, rect):
        super().__init__(fig, rect, axis_off=True)
        # The list scrolls rather than changing shape when it is long.
        self.offset = 0
        self.total = 0
        # The row a click resolved to. Not the same thing as the selection:
        # side-panel clicks select a whole bucket/category with no specific
        # row.
        self.selected_row = None

    def scroll(self, step):
        """Move the window by a line. True if it actually moved.

        Manual scrolling is allowed even with a row highlighted -- the
        highlight stays where it is, including off screen, rather than
        snapping back. Auto-scroll only happens on selection.
        """
        new = max(0, min(self.offset + step, max(0, self.total - 1)))
        if new == self.offset:
            return False
        self.offset = new
        return True

    def scroll_to_selected(self, ledger, sel, days):
        """Put the newly selected row on screen, with a line or two of context
        above it rather than pinned to the very top."""
        self.offset = 0
        if self.selected_row is None or not sel:
            return
        frame = sel.rows(ledger, days)
        if frame.empty:
            return
        order = list(frame.sort_values(["date", "start"]).index)
        try:
            pos = order.index(self.selected_row)
        except ValueError:
            return
        self.offset = max(0, min(pos - 2, max(0, len(order) - 1)))

    def draw(self, days, ledger, sel):
        ax = self.ax
        ax.clear()
        ax.axis("off")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)

        if not sel:
            ax.text(0, 0.12, "click any segment to break it down  ·  "
                             "click it again or press Esc to clear",
                    fontsize=8.5, color=blend(MUTED, 0.25))
            return

        growth = not sel.is_bucket
        frame = sel.rows(ledger, days)
        heading = sel.heading
        colors = [BUCKET_COLOR[n] if sel.is_bucket else CATEGORY_COLOR[n]
                  for n in sel.names]
        total = int(frame["minutes"].sum()) if not frame.empty else 0
        n_days = frame["date"].nunique() if not frame.empty else 0

        # One name selected draws one accent bar; several draw one stripe
        # each, stacked in the same space -- the heading reads as a
        # combination, not a single colour standing in for two things.
        swatch_h = 0.062 / len(colors)
        for i, c in enumerate(colors):
            ax.add_patch(Rectangle((0, 0.915 + i * swatch_h), 0.008, swatch_h,
                                   color=c, clip_on=False))
        ax.text(0.018, 0.920, heading, fontsize=9, color=INK,
                fontweight="bold")
        ax.text(max(0.15, 0.045 + len(heading) * 0.0092), 0.920,
                f"{hm(total) or '0h00'} across {n_days} day"
                f"{'' if n_days == 1 else 's'}",
                fontsize=8.5, color=MUTED)

        if frame.empty:
            ax.text(0, 0.78, "nothing in this range", fontsize=9, color=MUTED)
            return

        rows = list(frame.sort_values(["date", "start"]).iterrows())
        self.total = len(rows)
        first = min(self.offset, max(0, len(rows) - 1))
        self.offset = first

        y = 0.80
        i = first
        while i < len(rows):
            row_id, row = rows[i]
            note = truncate(row.get("notes", ""), 104)
            need = 0.145 if note else 0.092
            if y - need < -0.04:
                break
            if row_id == self.selected_row:
                # The row a click resolved to -- behind the text, not on
                # top. Its own bucket/category colour, not the selection's:
                # with several names selected they don't share one colour.
                row_color = (BUCKET_COLOR[row["bucket"]] if sel.is_bucket
                            else CATEGORY_COLOR[row["category"]])
                ax.add_patch(Rectangle(
                    (0, y - need + 0.018), 1, need, color=blend(row_color, 0.85),
                    zorder=0, clip_on=False))
            when = (f"{row['start']}–{row['end']}"
                    if row["start"] and row["end"] else "—")
            ax.text(0.0, y, f"{row['date']:%a %b %d}", fontsize=8.5,
                    color=INK_2, fontfamily="monospace")
            ax.text(0.105, y, when, fontsize=8.5, color=MUTED,
                    fontfamily="monospace")
            ax.text(0.20, y, hm(row["minutes"]), fontsize=8.5, color=INK,
                    fontfamily="monospace")
            ax.text(0.27, y, truncate(row_label(row, growth), 68),
                    fontsize=8.5, color=INK)
            if note:
                ax.text(0.27, y - 0.058, note, fontsize=7.5, color=MUTED,
                        style="italic")
            y -= need
            i += 1

        if first > 0 or i < len(rows):
            ax.text(1.0, 0.920, f"{first + 1}–{i} of {len(rows)}  ·  scroll",
                    fontsize=7.5, color=MUTED, ha="right")
