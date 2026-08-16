"""One class per axes.

Each panel owns its axes, the hit geometry it rebuilt on the last draw, and
(for the three charts) its hover tooltip. Nothing here reaches for another
panel or for the app -- everything a draw needs arrives as an argument, which
is what lets the layout rearrange them without any of them noticing.
"""

from .bars import BarsPanel
from .detail import DetailPanel
from .strip import StripPanel
from .summary import SummaryPanel
from .timeline import TimelinePanel

__all__ = ["BarsPanel", "DetailPanel", "StripPanel", "SummaryPanel",
           "TimelinePanel"]
