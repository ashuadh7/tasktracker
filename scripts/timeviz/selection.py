"""What's currently selected, and what follows from it.

Selecting dims everything else, in the bars and in the index at once, so a
category can be compared straight across the week. Three kinds share this
one object rather than three parallel pieces of state -- a bucket, a growth
category, and (see issue #29) a single target -- because a click on any of
them means the same thing: narrow every panel to just this, everywhere at
once.

A selection can hold more than one name from the same kind -- shift-click
adds a second bucket or category to the comparison instead of replacing the
first, so `work` and `targeted_work` can be read as one combined total.
Shift-clicking a name already in the selection removes just that one.
Selecting across kinds has no such combined reading, so a plain or
shift-click on a different kind always replaces rather than merges.

A target selection is a thin third case, not a fully independent one: its
rows always come from the log (`ledger.log`, filtered by the `target`
column) and its bucket is always `targeted_work` -- a target can't be
logged any other way -- so most of what follows treats it as log-sourced
with that one bucket, rather than duplicating the bucket branch.
"""

import pandas as pd

from .theme import (BUCKET_COLOR, BUCKET_ORDER, CATEGORY_COLOR, CATEGORY_TIER,
                    blend)

BUCKET = "bucket"
GROWTH = "growth"
TARGET = "target"


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
    def is_growth(self):
        return self.kind == GROWTH

    @property
    def buckets(self):
        """Names selected, if this is a bucket selection -- empty otherwise.
        Panels check membership here rather than equality, so one bucket or
        several highlight the same way. A target selection reads as its one
        bucket, `targeted_work`, so the stacked bar highlights the same way
        a plain bucket click would."""
        if self.is_bucket:
            return frozenset(self.names)
        if self.kind == TARGET:
            return frozenset({"targeted_work"})
        return frozenset()

    @property
    def categories(self):
        return frozenset(self.names) if self.is_growth else frozenset()

    @property
    def color(self):
        """The accent colour for chrome that can only show one -- the first
        name selected. Panels that draw every row already colour each by its
        own bucket/category and don't need this."""
        if self.is_bucket:
            return BUCKET_COLOR[self.names[0]]
        if self.kind == TARGET:
            return BUCKET_COLOR["targeted_work"]
        return CATEGORY_COLOR[self.names[0]]

    def color_for(self, name):
        """Same idea as `color`, but per name -- what a panel drawing every
        row in the selection colours each one with. A target selection's
        rows are still bucket/category-coloured by their own bucket
        (`row["bucket"]`, always `targeted_work`), not by this -- this exists
        for callers that only have the *selected* name, like the swatch next
        to a heading."""
        if self.is_bucket:
            return BUCKET_COLOR[name]
        if self.kind == TARGET:
            return BUCKET_COLOR["targeted_work"]
        return CATEGORY_COLOR[name]

    @property
    def heading(self):
        if len(self.names) > 1:
            sep = " + "
            return sep.join(n.replace("_", " ").upper() for n in self.names)
        if self.is_bucket:
            return self.names[0].replace("_", " ").upper()
        if self.kind == TARGET:
            # A target's name is a written-out sentence, not an enum value --
            # forcing it to caps like a bucket/category would read as
            # shouting a whole sentence.
            return self.names[0]
        return f"{CATEGORY_TIER[self.names[0]].upper()} · {self.names[0].upper()}"

    @property
    def source(self):
        """Which frame this selection's rows come from -- the tag hit
        registries carry so a hover knows where to look the row up."""
        return "log" if self.kind in (BUCKET, TARGET) else "growth"

    def rows(self, ledger, days):
        """The rows behind the selection, within the window."""
        stamps = pd.DatetimeIndex(days)
        if self.is_growth:
            return ledger.growth[ledger.growth["date"].isin(stamps)
                                 & ledger.growth["category"].isin(self.names)]
        if self.kind == TARGET:
            return ledger.log[ledger.log["date"].isin(stamps)
                              & ledger.log["target"].isin(self.names)]
        return ledger.log[ledger.log["date"].isin(stamps)
                          & ledger.log["bucket"].isin(self.names)]

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
