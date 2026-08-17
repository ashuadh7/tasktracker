"""What's currently selected, and what follows from it.

Selecting dims everything else, in the bars and in the index at once, so a
category can be compared straight across the week. Both ledgers can be
selected from, and the two behave the same way -- which is why this is one
object with a `kind` rather than two parallel pieces of state.

A selection can hold more than one name from the same ledger -- shift-click
adds a second bucket or category to the comparison instead of replacing the
first, so `work` and `targeted_work` can be read as one combined total.
Shift-clicking a name already in the selection removes just that one.
Selecting across ledgers has no such combined reading, so a plain or
shift-click on the other kind always replaces rather than merges.
"""

import pandas as pd

from .theme import (BUCKET_COLOR, BUCKET_ORDER, CATEGORY_COLOR, CATEGORY_TIER,
                    blend)

BUCKET = "bucket"
GROWTH = "growth"


class Selection:
    def __init__(self, kind, names):
        self.kind = kind
        self.names = (names,) if isinstance(names, str) else tuple(names)

    @classmethod
    def parse(cls, name):
        """A `--select` argument, or None if it names neither ledger."""
        if name in BUCKET_ORDER:
            return cls(BUCKET, name)
        if name in CATEGORY_COLOR:
            return cls(GROWTH, name)
        return None

    @property
    def is_bucket(self):
        return self.kind == BUCKET

    @property
    def buckets(self):
        """Names selected, if this is a bucket selection -- empty otherwise.
        Panels check membership here rather than equality, so one bucket or
        several highlight the same way."""
        return frozenset(self.names) if self.is_bucket else frozenset()

    @property
    def categories(self):
        return frozenset(self.names) if not self.is_bucket else frozenset()

    @property
    def color(self):
        """The accent colour for chrome that can only show one -- the first
        name selected. Panels that draw every row already colour each by its
        own bucket/category and don't need this."""
        return (BUCKET_COLOR[self.names[0]] if self.is_bucket
                else CATEGORY_COLOR[self.names[0]])

    @property
    def heading(self):
        if len(self.names) > 1:
            sep = " + "
            return sep.join(n.replace("_", " ").upper() for n in self.names)
        if self.is_bucket:
            return self.names[0].replace("_", " ").upper()
        return f"{CATEGORY_TIER[self.names[0]].upper()} · {self.names[0].upper()}"

    @property
    def source(self):
        """Which frame this selection's rows come from -- the tag hit
        registries carry so a hover knows where to look the row up."""
        return "log" if self.is_bucket else "growth"

    def rows(self, ledger, days):
        """The rows behind the selection, within the window."""
        stamps = pd.DatetimeIndex(days)
        if self.is_bucket:
            return ledger.log[ledger.log["date"].isin(stamps)
                              & ledger.log["bucket"].isin(self.names)]
        return ledger.growth[ledger.growth["date"].isin(stamps)
                             & ledger.growth["category"].isin(self.names)]

    def toggled(self, kind, name):
        """The selection after shift-clicking `name`.

        A name already in the selection drops out; a new name of the same
        kind joins it. A name from the other ledger replaces the selection
        outright -- there's no single total that combines a bucket with a
        growth category. Returns None if the toggle empties the selection.
        """
        if self.kind != kind:
            return Selection(kind, name)
        if name in self.names:
            remaining = tuple(n for n in self.names if n != name)
            return Selection(kind, remaining) if remaining else None
        return Selection(kind, self.names + (name,))

    def __eq__(self, other):
        return (isinstance(other, Selection) and self.kind == other.kind
                and frozenset(self.names) == frozenset(other.names))

    def __hash__(self):
        return hash((self.kind, frozenset(self.names)))

    def __repr__(self):
        return f"Selection({self.kind!r}, {self.names!r})"


def shade_for(sel, color, matches):
    """Full colour if it matches the selection or nothing is selected; faded
    most of the way to the surface otherwise."""
    if sel is None:
        return color
    return color if matches else blend(color, 0.80)
