"""Argument parsing and the two ways this ends: a window, or a PNG."""

import datetime as dt
import sys

import matplotlib.pyplot as plt

from .app import Viz
from .model import Ledger
from .theme import SURFACE


def parse(argv):
    """(anchor, mode, png, select) from the command line.

    Hand-rolled rather than argparse because the only positional is an
    optional ISO date and the flags are three -- and because `viz.bat` passes
    whatever it was given straight through, so an unrecognised argument
    should be ignored rather than turned into a usage error and an exit.
    """
    args = list(argv)
    mode = "day" if "--day" in args else "month" if "--month" in args else "week"
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
    return anchor, mode, png, select


def main(argv=None):
    anchor, mode, png, select = parse(sys.argv[1:] if argv is None else argv)
    viz = Viz(Ledger.load(), anchor, mode, select=select)
    if png:
        viz.fig.savefig(png, dpi=110, facecolor=SURFACE)
        print(f"wrote {png}")
    else:
        plt.show()
