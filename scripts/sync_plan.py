#!/usr/bin/env python3
"""Work out what Notion needs so it mirrors the desktop.

    python sync_plan.py notion_rows.json            # the time log
    python sync_plan.py --growth notion_rows.json   # the growth ledger

The desktop is the authority. For the time log, `time-log.csv` holds sealed
days and `open-day.csv` holds the day in progress. For the growth ledger it is
just `growth-log.csv` -- nothing there is ever partial, because nothing there
has to add up. Notion should end up containing exactly the desktop's rows and
nothing else, plus whatever the phone added that the desktop has not ingested.

This script only *computes* the plan -- it has no Notion access. Claude runs
it, then carries out the actions through the Notion connector. Doing the diff
here rather than by eye keeps a long log from quietly drifting out of sync.

notion_rows.json is a list of objects dumped from the Notion query:

    [{"url": "...", "date": "2026-08-11", "minutes": 360, "bucket": "sleep",
      "project": "", "activity": "sleep", "start": "", "end": "",
      "confidence": "reconstructed", "sealed": true, "synced": true}, ...]

  --growth expects `tier`, `category`, `mode` and `bucket` in place of
  `project`, and ignores `sealed`.

Output is JSON with four lists:

    create   rows on the desktop that Notion is missing
    delete   Notion rows the desktop no longer has (a rewritten open day)
    reflag   Notion rows whose sealed/synced flags disagree with the desktop
    pull     Notion rows the desktop has never seen -- these came from the
             phone and need ingesting before anything else happens
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csv_io

# The CSVs live one level up -- scripts/ holds code, the tracker root holds
# data, so the data is what you see when you open the folder.
DATA = Path(__file__).resolve().parent.parent
SEALED_FILE = DATA / "time-log.csv"
OPEN_FILE = DATA / "open-day.csv"
GROWTH_FILE = DATA / "growth-log.csv"

# What makes two rows "the same row". Deliberately excludes notes and domain
# so that editing a note on either side is not treated as a different row.
TIME_KEY = ("date", "minutes", "bucket", "project", "activity")
GROWTH_KEY = ("date", "minutes", "tier", "category", "mode", "activity")


def read_csv(path):
    """Tolerates a file last saved by Excel -- see csv_io.py."""
    _, rows = csv_io.read_rows(path)
    return rows


def key_for(fields):
    def key(row):
        return tuple(str(row.get(f, "") or "").strip() for f in fields)
    return key


def diff(desktop, notion, key, track_sealed):
    create, delete, reflag, pull = [], [], [], []

    by_key_desktop = {key(r): r for r in desktop}
    by_key_notion = {key(r): r for r in notion}

    for k, row in by_key_desktop.items():
        if k not in by_key_notion:
            create.append(row)
            continue
        n = by_key_notion[k]
        # Everything the desktop holds is by definition already on the
        # desktop, so `synced` is always true for these.
        stale_seal = track_sealed and bool(n.get("sealed")) != row["sealed"]
        if stale_seal or not n.get("synced"):
            entry = {"url": n["url"], "synced": True,
                     "activity": row.get("activity", ""), "date": row["date"]}
            if track_sealed:
                entry["sealed"] = row["sealed"]
            reflag.append(entry)

    for k, row in by_key_notion.items():
        if k in by_key_desktop:
            continue
        if row.get("synced"):
            # Marked as living on the desktop, but it doesn't. It belonged to
            # an open day that has since been rewritten, so Notion is stale.
            delete.append(row)
        else:
            # Never seen here -- this came from the phone.
            pull.append(row)

    return {"create": create, "delete": delete, "reflag": reflag, "pull": pull}


def main():
    args = sys.argv[1:]
    growth = "--growth" in args
    args = [a for a in args if a != "--growth"]
    if not args:
        print(__doc__)
        return 2

    notion = json.loads(Path(args[0]).read_text(encoding="utf-8"))

    desktop = []
    if growth:
        desktop = read_csv(GROWTH_FILE)
    else:
        for row in read_csv(SEALED_FILE):
            row["sealed"] = True
            desktop.append(row)
        for row in read_csv(OPEN_FILE):
            row["sealed"] = False
            desktop.append(row)

    for row in notion:
        row["minutes"] = str(int(row["minutes"]))
    for row in desktop:
        row["minutes"] = str(int(row["minutes"]))

    key = key_for(GROWTH_KEY if growth else TIME_KEY)
    plan = diff(desktop, notion, key, track_sealed=not growth)

    print(json.dumps(plan, indent=2))
    which = "growth-log" if growth else "time-log"
    summary = (f"{which}: create {len(plan['create'])} | "
               f"delete {len(plan['delete'])} | reflag {len(plan['reflag'])} | "
               f"pull {len(plan['pull'])}")
    print(f"\n// {summary}", file=sys.stderr)
    if plan["pull"]:
        dates = sorted({r["date"] for r in plan["pull"]})
        print(f"// pull first -- phone rows for {', '.join(dates)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
