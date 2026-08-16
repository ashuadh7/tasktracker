#!/usr/bin/env python3
"""Validate the tracker CSVs. Run after every append.

    python check.py

Checks three files:

  time-log.csv    sealed days, each must total exactly 24h
  open-day.csv    the day in progress, expected to be short
  growth-log.csv  the growth ledger -- an overlay, never reconciled to 24h

Exits 1 if anything is wrong, so a bad append is caught immediately rather
than surfacing as a strange bar three weeks later.

Reads tolerate files last saved by Excel (see csv_io.py for why), and every
run ends by rewriting each file in canonical form -- UTF-8 with a BOM,
zero-padded times -- so formatting drift never accumulates regardless of
which app touched the file last.
"""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csv_io

# The CSVs live one level up -- scripts/ holds code, the tracker root holds
# data, so the data is what you see when you open the folder.
DATA = Path(__file__).resolve().parent.parent
SEALED_FILE = DATA / "time-log.csv"
OPEN_FILE = DATA / "open-day.csv"
GROWTH_FILE = DATA / "growth-log.csv"
PROJECTS_FILE = DATA / "projects.csv"

BUCKETS = {"sleep", "necessities", "obligations", "rest",
           "work", "targeted_work", "slack"}
CONFIDENCE = {"logged", "reconstructed"}
MINUTES_PER_DAY = 1440

# Growth ledger vocabulary. Two tiers deep: the tier is the comparison axis
# that has to survive years, the category is the useful detail underneath.
GROWTH_TIERS = {
    "reading": {"fiction", "non-fiction", "article"},
    "audio": {"podcast", "audiobook"},
    "self-care": {"self-improvement", "hobby", "physical", "mental"},
}
GROWTH_MODES = {"concurrent", "dedicated"}

# A growth row's `bucket` echoes what the time log called the same block.
# These are the buckets you can realistically stack a second activity onto --
# dishes, cooking, driving, waiting. You cannot listen to an audiobook while
# doing focused work, so a `concurrent` row against one of the others is
# almost certainly a mislabel.
STACKABLE = {"necessities", "obligations"}

MIDNIGHT = {"00:00", "24:00"}


def to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def load_projects():
    _, rows = csv_io.read_rows(PROJECTS_FILE)
    return {r["project"].strip() for r in rows if r["project"].strip()}


def field_count_problem(row, where):
    """An unquoted comma in `notes` shifts every field and breaks pandas.

    csv.DictReader shrugs this off by shoving the surplus under a None key,
    so it has to be checked for explicitly or the log validates clean and the
    visualizer dies on it.
    """
    if row.get(None) is not None:
        return (f"{where}: too many fields - unquoted comma in notes? "
                f"(stray: {row[None]!r})")
    missing = [k for k, v in row.items() if v is None]
    if missing:
        return f"{where}: missing field(s) {missing}"
    return None


def sleep_slot(start, end):
    """Where a sleep row sits in the day: leading, trailing, or a nap.

    Days run midnight to midnight, so a night that crosses midnight is two
    rows on two dates. The leading one opens the day, the trailing one closes
    it, and the pair of them sandwiches everything else.
    """
    if end in MIDNIGHT and start:
        return "trailing"
    if start == "00:00":
        return "leading"
    if not start and not end:
        return "leading"  # untimed legacy rows read as opening the day
    return "nap"


def validate_time(path, known_projects, require_full_days):
    """Returns (problems, warnings, n_rows, n_days, per_day_bucket, fields, rows)."""
    problems, warnings = [], []
    per_day = defaultdict(int)
    per_day_bucket = defaultdict(int)
    sleep_slots = defaultdict(list)

    fieldnames, rows = csv_io.read_rows(path)

    for n, row in enumerate(rows, start=2):  # +2: header is line 1
        where = f"{path.name} line {n}"

        bad_shape = field_count_problem(row, where)
        if bad_shape:
            problems.append(bad_shape)
            continue

        try:
            mins = int(row["minutes"])
            if mins <= 0:
                problems.append(f"{where}: minutes must be positive, got {mins}")
                continue
        except (ValueError, KeyError):
            problems.append(f"{where}: minutes is not an integer: "
                            f"{row.get('minutes')!r}")
            continue

        per_day[row["date"]] += mins
        per_day_bucket[(row["date"], row["bucket"])] += mins

        if row["bucket"] not in BUCKETS:
            problems.append(f"{where}: unknown bucket {row['bucket']!r}")

        if row["confidence"] not in CONFIDENCE:
            problems.append(f"{where}: confidence must be one of "
                            f"{sorted(CONFIDENCE)}, got {row['confidence']!r}")

        project = row["project"].strip()
        if project and project not in known_projects:
            problems.append(f"{where}: project {project!r} is not in projects.csv")

        # If both ends are given they must agree with minutes (midnight wraps).
        start, end = row["start"].strip(), row["end"].strip()
        if start and end:
            span = to_minutes(end) - to_minutes(start)
            if span <= 0:
                span += MINUTES_PER_DAY
            if span != mins:
                problems.append(f"{where}: {start}-{end} is {span}min "
                                f"but minutes says {mins}")

        if row["bucket"] == "sleep":
            sleep_slots[row["date"]].append((sleep_slot(start, end), where))

        # Naming the slack is the point, so an unnamed slack row is an error
        # when logged live. Reconstructed days get a warning instead -- you
        # sometimes genuinely cannot recall last Tuesday evening.
        if row["bucket"] == "slack" and row["activity"].strip() in ("", "unaccounted"):
            msg = (f"{where} ({row['date']}): slack row has no named activity - "
                   f"what was that time spent on?")
            (problems if row["confidence"] == "logged" else warnings).append(msg)

    # A calendar day opens with at most one sleep block and closes with at
    # most one. More than that means a night got split wrong.
    for date, slots in sleep_slots.items():
        for slot in ("leading", "trailing"):
            hits = [w for s, w in slots if s == slot]
            if len(hits) > 1:
                problems.append(f"{path.name} {date}: {len(hits)} {slot} sleep "
                                f"rows, expected at most 1 ({', '.join(hits)})")

    for date in sorted(per_day):
        total = per_day[date]
        if require_full_days and total != MINUTES_PER_DAY:
            delta = total - MINUTES_PER_DAY
            problems.append(f"{path.name} {date}: sums to {total}min, not 1440 "
                            f"({delta:+d} - "
                            f"{'overlap' if delta > 0 else 'missing time'})")
        elif not require_full_days and total > MINUTES_PER_DAY:
            problems.append(f"{path.name} {date}: sums to {total}min, over 1440 "
                            f"- something overlaps")

    return problems, warnings, len(rows), len(per_day), per_day_bucket, fieldnames, rows


def validate_growth(per_day_bucket, open_dates):
    """The growth ledger. Deliberately not reconciled against 1440.

    A run with a podcast on is one row in the time log and two here, so these
    minutes can and should exceed the wall clock. What is checked is that the
    `bucket` each row echoes actually exists in the time log that day -- that
    is the only thing that can silently drift between the two files.
    """
    problems, warnings = [], []
    per_day_growth = defaultdict(int)
    fieldnames, rows = csv_io.read_rows(GROWTH_FILE)

    for n, row in enumerate(rows, start=2):
        where = f"{GROWTH_FILE.name} line {n}"

        bad_shape = field_count_problem(row, where)
        if bad_shape:
            problems.append(bad_shape)
            continue

        try:
            mins = int(row["minutes"])
            if mins <= 0:
                problems.append(f"{where}: minutes must be positive, got {mins}")
                continue
        except (ValueError, KeyError):
            problems.append(f"{where}: minutes is not an integer: "
                            f"{row.get('minutes')!r}")
            continue

        tier, category = row["tier"].strip(), row["category"].strip()
        if tier not in GROWTH_TIERS:
            problems.append(f"{where}: unknown tier {tier!r}, expected one of "
                            f"{sorted(GROWTH_TIERS)}")
        elif category not in GROWTH_TIERS[tier]:
            problems.append(f"{where}: {category!r} is not a category of "
                            f"{tier!r} - expected {sorted(GROWTH_TIERS[tier])}")

        if row["mode"].strip() not in GROWTH_MODES:
            problems.append(f"{where}: mode must be one of {sorted(GROWTH_MODES)}, "
                            f"got {row['mode']!r}")

        if row["confidence"].strip() not in CONFIDENCE:
            problems.append(f"{where}: confidence must be one of "
                            f"{sorted(CONFIDENCE)}, got {row['confidence']!r}")

        start, end = row["start"].strip(), row["end"].strip()
        if start and end:
            span = to_minutes(end) - to_minutes(start)
            if span <= 0:
                span += MINUTES_PER_DAY
            if span != mins:
                problems.append(f"{where}: {start}-{end} is {span}min "
                                f"but minutes says {mins}")

        date, bucket = row["date"].strip(), row["bucket"].strip()
        per_day_growth[date] += mins

        if bucket not in BUCKETS:
            problems.append(f"{where}: unknown bucket {bucket!r}")
            continue

        # The echoed bucket has to be backed by real time in the log, or the
        # two files have drifted and every number built on the join is wrong.
        available = per_day_bucket.get((date, bucket), 0)
        if available == 0:
            msg = (f"{where} ({date}): echoes bucket {bucket!r}, but the time "
                   f"log has no {bucket} on that date")
            (warnings if date in open_dates else problems).append(msg)
        elif mins > available:
            msg = (f"{where} ({date}): {mins}min against {bucket}, but the time "
                   f"log only has {available}min of it that day")
            (warnings if date in open_dates else problems).append(msg)

        if row["mode"].strip() == "concurrent" and bucket not in STACKABLE:
            warnings.append(f"{where} ({date}): concurrent against {bucket!r} - "
                            f"you can stack listening onto "
                            f"{'/'.join(sorted(STACKABLE))}, not focused time. "
                            f"Should this be dedicated?")

    return problems, warnings, len(rows), len(per_day_growth), fieldnames, rows


def main():
    known_projects = load_projects()

    sealed = validate_time(SEALED_FILE, known_projects, require_full_days=True)
    opened = validate_time(OPEN_FILE, known_projects, require_full_days=False)

    # The time log's bucket totals, across both files, are what the growth
    # ledger's echoed buckets are checked against.
    per_day_bucket = defaultdict(int)
    for source in (sealed[4], opened[4]):
        for key, mins in source.items():
            per_day_bucket[key] += mins
    open_dates = {d for d, _ in opened[4]}

    growth = validate_growth(per_day_bucket, open_dates)

    problems = sealed[0] + opened[0] + growth[0]
    warnings = sealed[1] + opened[1] + growth[1]

    for w in warnings:
        print(f"  warn: {w}")
    if warnings:
        print()

    if problems:
        print(f"{len(problems)} problem(s):\n")
        for p in problems:
            print(f"  {p}")
        return 1

    print(f"OK - time-log.csv: {sealed[2]} rows across {sealed[3]} days, "
          f"every day sums to 24h")
    if opened[2]:
        print(f"     open-day.csv: {opened[2]} rows across {opened[3]} day(s), "
              f"still open")
    else:
        print("     open-day.csv: empty, no day in progress")
    if growth[2]:
        print(f"     growth-log.csv: {growth[2]} rows across {growth[3]} day(s)")
    else:
        print("     growth-log.csv: empty")

    # Only normalize once everything checks out clean -- rewriting a file that
    # has a real problem in it would make the problem harder to spot in a
    # diff, for no benefit.
    touched = []
    for path, fields, rows in ((SEALED_FILE, sealed[5], sealed[6]),
                               (OPEN_FILE, opened[5], opened[6]),
                               (GROWTH_FILE, growth[4], growth[5])):
        if fields and csv_io.normalize_file(path, fields, rows):
            touched.append(path.name)
    if touched:
        print(f"     normalized {', '.join(touched)} -- UTF-8, zero-padded times")
    return 0


if __name__ == "__main__":
    sys.exit(main())
