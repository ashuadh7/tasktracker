"""Reading the CSVs and reshaping them into what the charts want.

pandas in, pandas out. Nothing here imports matplotlib or knows a figure
exists, which is the point: the parts where a wrong answer is silent rather
than visible -- which slot a sleep row belongs in, whether a day's minutes add
to 1440 -- can be exercised without opening a window.
"""

import sys
from pathlib import Path

import pandas as pd

from .theme import BUCKET_ORDER, GROWTH_KEYS, SLOTS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import csv_io  # noqa: E402  -- sibling of the package, not inside it

# The CSVs live two levels up -- scripts/ holds code, the tracker root holds
# data, so the data is what you see when you open the folder.
DATA = Path(__file__).resolve().parents[2]
LOG_FILE = DATA / "time-log.csv"
OPEN_FILE = DATA / "open-day.csv"
PLAN_FILE = DATA / "plan.csv"
GROWTH_FILE = DATA / "growth-log.csv"
TARGETS_FILE = DATA / "targets.csv"
PROGRESS_FILE = DATA / "progress-log.csv"

MIDNIGHT = {"00:00", "24:00"}


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


def read_day_tags(path):
    """date -> tag, from an optional two-column `date,tag` CSV that lives
    outside the tracker's own schema entirely -- see --day-tags in cli.py.
    A missing path (the common case: nobody passed the flag) reads as no
    tags at all, the same way OPEN_FILE/GROWTH_FILE degrade when absent."""
    if not path:
        return {}
    _, rows = csv_io.read_rows(path)
    return {pd.Timestamp(row["date"]).date(): row["tag"]
            for row in rows if row.get("tag")}


def row_order(frame, days, column_field):
    """day index -> column value -> ordered list of row ids (frame index),
    in the same order the detail list shows them (`["date", "start"]`). This
    is what lets a stacked bar's hit registry point at a row instead of just
    the slot/key it belongs to."""
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


class Ledger:
    """The three CSVs, loaded and kept together.

    Everything drawn comes from here, and the two frames are deliberately
    allowed to disagree: a novel read while procrastinating is `slack` in the
    time log *and* `reading/fiction` in the growth ledger. Reconciling them
    would destroy the comparison the chart exists to make.
    """

    def __init__(self, log, plan, growth, targets, progress):
        self.log, self.plan, self.growth = log, plan, growth
        self.targets, self.progress = targets, progress

    @classmethod
    def load(cls):
        """Read the log, plan and growth ledger. Missing optional files are
        fine.

        The open day is drawn alongside the sealed ones -- it shows as a
        partly filled bar with grey on top, which is what a day in progress
        actually is. It stays out of the per-day averages, though: dividing a
        week's sleep by a day that is only logged to 10am would understate
        every one of them.
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

        # No `date` column -- one row per planned work item, not a log entry --
        # so it goes through csv_io directly rather than read_log.
        fieldnames, rows = csv_io.read_rows(TARGETS_FILE)
        targets = pd.DataFrame(rows, columns=fieldnames) if fieldnames else \
            pd.DataFrame(columns=["target", "project", "window", "minutes",
                                  "status", "notes"])
        if not targets.empty:
            targets["minutes"] = targets["minutes"].astype(int)

        progress = read_log(PROGRESS_FILE)
        if not progress.empty:
            progress["percent"] = progress["percent"].astype(int)
        else:
            progress = pd.DataFrame(columns=["date", "target", "percent",
                                             "basis", "notes"])

        return cls(log, plan, growth, targets, progress)

    # -- reshaped for the charts -------------------------------------------

    def day_matrix(self, days):
        return matrix(self.log, days, SLOTS, "slot")

    def growth_matrix(self, days):
        return matrix(self.growth, days, GROWTH_KEYS, "key")

    def rows_by_slot(self, days):
        return row_order(self.log, days, "slot")

    def rows_by_key(self, days):
        return row_order(self.growth, days, "key")

    # -- lookups -----------------------------------------------------------

    def frame_for(self, source):
        """The frame a hit registry's `source` tag refers to."""
        return self.log if source == "log" else self.growth

    def log_in(self, days):
        return self.log[self.log["date"].isin(pd.DatetimeIndex(days))]

    def planned(self, days, bucket):
        return self.plan[
            self.plan["date"].isin(pd.DatetimeIndex(days))
            & (self.plan["bucket"] == bucket)
        ]["minutes"].sum()

    def target_progress(self):
        """project -> (rollup percent, total minutes) across active targets.

        Not scoped to a window -- a target lives across many days and its
        percent is a current state, not a per-day quantity, so this always
        reflects the open set regardless of what's on screen. The rollup is
        hours-weighted: a target with no progress-log.csv entry yet counts as
        0%, and a target with a 0-minute estimate drops out on its own (zero
        weight contributes to neither side of the ratio).
        """
        if self.targets.empty:
            return {}
        active = self.targets[self.targets["status"] == "active"]
        if active.empty:
            return {}

        latest = {}
        if not self.progress.empty:
            last = self.progress.drop_duplicates("target", keep="last")
            latest = dict(zip(last["target"], last["percent"]))

        out = {}
        for project, group in active.groupby("project"):
            weight = int(group["minutes"].sum())
            if weight == 0:
                continue
            weighted = sum(latest.get(t, 0) * m
                          for t, m in zip(group["target"], group["minutes"]))
            out[project] = (weighted / weight, weight)
        return out

    def growth_in(self, days):
        if self.growth.empty:
            return self.growth
        return self.growth[self.growth["date"].isin(pd.DatetimeIndex(days))]
