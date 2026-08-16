"""Hit-test geometry, rebuilt on every draw.

A chart draws a band as one rectangle but has to answer clicks about the rows
inside it, so every panel keeps a registry of where its rows ended up. Two
shapes cover all four charts:

`LaneHits` is for anything laid out one day per lane -- the stacked bars and
the growth strip put the day on x and stack up y, the timeline puts the day on
y and runs along x. Same structure transposed, so one class serves both:
`across` picks the lane, `along` finds the band inside it. The tolerance is
how far off the lane's centre still counts as a hit, which differs because a
0.62-wide bar and a 0.55-tall row are not the same target.

`BandHits` is the side index: one column of bands in the axes' own 0-1
fraction coordinates, with no lanes to pick between.

Bands whose `row_id` is None have no underlying row -- the unlogged gap is the
only one -- so they can be clicked (which clears the selection) but never
hovered.
"""

from collections import namedtuple

Band = namedtuple("Band", "row_id key lo hi")


class LaneHits:
    def __init__(self, tolerance):
        self.tolerance = tolerance
        self.lanes = {}

    def reset(self, n):
        """Every lane exists even when empty, so an empty day is a miss rather
        than a lookup that falls through to the neighbouring one."""
        self.lanes = {i: [] for i in range(n)}

    def add(self, lane, row_id, key, lo, hi):
        self.lanes[lane].append(Band(row_id, key, lo, hi))

    def find(self, across, along):
        i = int(round(across))
        if i not in self.lanes or abs(across - i) > self.tolerance:
            return None
        for band in self.lanes[i]:
            if band.lo <= along < band.hi:
                return band
        return None


class BandHits:
    def __init__(self):
        self.bands = []

    def reset(self):
        self.bands = []

    def add(self, key, lo, hi):
        self.bands.append(Band(None, key, lo, hi))

    def find(self, along):
        for band in self.bands:
            if band.lo <= along < band.hi:
                return band
        return None
