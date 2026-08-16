"""Which days are on screen, and how you move between them.

An anchor date plus a mode. Every navigation control -- the buttons, the arrow
keys, w/m/d/t -- is a state transition on this object and nothing else, so
what "next" means in month mode is answerable without a figure in the way.
"""

import calendar
import datetime as dt

MODES = ("day", "week", "month")


class Window:
    def __init__(self, anchor, mode="week"):
        self.anchor = anchor
        self.mode = mode

    @property
    def roomy(self):
        """Whether rows and bars are tall enough to write inside.

        A month row is a few pixels tall, nowhere near enough for text between
        neighbours, so the inline duration labels and the weekday tick labels
        are week/day only.
        """
        return self.mode in ("week", "day")

    def days(self):
        if self.mode == "day":
            return [self.anchor]
        if self.mode == "week":
            start = self.anchor - dt.timedelta(days=self.anchor.weekday())
            return [start + dt.timedelta(days=i) for i in range(7)]
        first = self.anchor.replace(day=1)
        n = calendar.monthrange(first.year, first.month)[1]
        return [first + dt.timedelta(days=i) for i in range(n)]

    def title(self):
        days = self.days()
        if self.mode == "day":
            d = days[0]
            return f"{d:%A} {d:%b} {d.day}, {d.year}"
        if self.mode == "week":
            a, b = days[0], days[-1]
            return (f"Week of {a:%a} {a:%b} {a.day} – "
                    f"{b:%a} {b:%b} {b.day}, {b.year}")
        return f"{days[0]:%B %Y}"

    # -- navigation --------------------------------------------------------

    def step(self, direction):
        if self.mode == "week":
            self.anchor += dt.timedelta(days=7 * direction)
        elif self.mode == "day":
            self.anchor += dt.timedelta(days=direction)
        else:
            first = self.anchor.replace(day=1)
            self.anchor = (
                (first + dt.timedelta(days=32)).replace(day=1) if direction > 0
                else (first - dt.timedelta(days=1)).replace(day=1)
            )

    def go_today(self):
        self.anchor = dt.date.today()

    def go_day(self):
        """Enter day mode, always on today -- stepping back through days,
        then toggling to week and back to day, would otherwise be
        disorienting."""
        self.anchor = dt.date.today()
        self.mode = "day"

    def toggle(self):
        if self.mode == "day":
            self.mode = "week"
        else:
            self.mode = "month" if self.mode == "week" else "week"
