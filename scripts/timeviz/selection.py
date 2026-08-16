"""What's currently selected, and what follows from it.

Selecting dims everything else, in the bars and in the index at once, so a
category can be compared straight across the week. Both ledgers can be
selected from, and the two behave the same way -- which is why this is one
object with a `kind` rather than two parallel pieces of state.
"""

import pandas as pd

from .theme import (BUCKET_COLOR, BUCKET_ORDER, CATEGORY_COLOR, CATEGORY_TIER,
                    blend)

BUCKET = "bucket"
GROWTH = "growth"


class Selection:
    def __init__(self, kind, name):
        self.kind = kind
        self.name = name

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
    def bucket(self):
        """The selected bucket, or None if a growth category is selected.

        Panels compare against this rather than asking what kind is selected,
        so a growth selection correctly dims every bucket: nothing equals
        None.
        """
        return self.name if self.kind == BUCKET else None

    @property
    def category(self):
        return self.name if self.kind == GROWTH else None

    @property
    def color(self):
        return (BUCKET_COLOR[self.name] if self.is_bucket
                else CATEGORY_COLOR[self.name])

    @property
    def heading(self):
        if self.is_bucket:
            return self.name.replace("_", " ").upper()
        return f"{CATEGORY_TIER[self.name].upper()} · {self.name.upper()}"

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
                              & (ledger.log["bucket"] == self.name)]
        return ledger.growth[ledger.growth["date"].isin(stamps)
                             & (ledger.growth["category"] == self.name)]

    def __eq__(self, other):
        return (isinstance(other, Selection) and self.kind == other.kind
                and self.name == other.name)

    def __hash__(self):
        return hash((self.kind, self.name))

    def __repr__(self):
        return f"Selection({self.kind!r}, {self.name!r})"


def shade_for(sel, color, matches):
    """Full colour if it matches the selection or nothing is selected; faded
    most of the way to the surface otherwise."""
    if sel is None:
        return color
    return color if matches else blend(color, 0.80)
