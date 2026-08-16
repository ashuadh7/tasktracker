"""Turning numbers and log rows into the short strings the chart prints.

Leaf module: no pandas, no matplotlib, nothing else in the package. Every
function here is a pure transform, which is what makes them the cheapest
things in the codebase to check.
"""

MINUTES_PER_DAY = 1440


def to_hours(hhmm):
    """'10:33' -> 10.55. For placing a block on the clock."""
    h, m = hhmm.split(":")
    return int(h) + int(m) / 60


def hm(minutes):
    """540 -> '9h00'. Blank for zero."""
    minutes = int(round(minutes))
    if minutes == 0:
        return ""
    return f"{minutes // 60}h{minutes % 60:02d}"


def ampm(hour):
    """15 -> '3pm'. 0 and 24 both -> '12am' -- the axis runs midnight to
    midnight, so both ends of the timeline are the same instant."""
    hour = hour % 24
    period = "am" if hour < 12 else "pm"
    hour12 = hour % 12 or 12
    return f"{hour12}{period}"


def clock_hm(minutes):
    """615 -> '10:15am'. For saying how far into the day the log reaches."""
    minutes = int(round(minutes)) % MINUTES_PER_DAY
    h, m = divmod(minutes, 60)
    period = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d}{period}"


def truncate(text, n):
    text = str(text or "").strip()
    return text if len(text) <= n else text[:n - 1] + "…"


def row_label(row, growth=False):
    """'Planner · viz refactor', or with the growth ledger's extra clause.

    The tooltip and the detail list both name a row this way and then truncate
    to their own width, so the naming lives here and the truncating stays with
    whoever knows how much room there is.
    """
    label = str(row.get("activity", ""))
    project = str(row.get("project", "") or "")
    if project:
        label = f"{project} · {label}"
    if growth:
        label = f"{label}  [{row['mode']} · {row['bucket']}]"
    return label


def tooltip_text(row, growth=False):
    """The three lines a hovered segment shows: what it was, when and how
    long, and the note if there is one."""
    when = (f"{row['start']}–{row['end']}"
            if row["start"] and row["end"] else "untimed")
    lines = [truncate(row_label(row, growth), 60),
             f"{when}   {hm(row['minutes']) or '0h00'}"]
    note = truncate(row.get("notes", ""), 70)
    if note:
        lines.append(note)
    return "\n".join(lines)
