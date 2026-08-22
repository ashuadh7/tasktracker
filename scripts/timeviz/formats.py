"""Turning numbers and log rows into the short strings the chart prints.

Leaf module: no pandas, no matplotlib, nothing else in the package. Every
function here is a pure transform, which is what makes them the cheapest
things in the codebase to check.
"""

import textwrap

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


def wrap(text, width=25, max_lines=3):
    """A tooltip's box is only ever as wide as its widest line, and a single
    60-char line is wide enough to clip near a figure edge however the box
    is anchored -- so a long field wraps onto several narrow lines instead
    of staying one long one. Word-wrapped at `width` characters (a proxy for
    pixel width, not exact under a proportional font, but close enough at
    this font size to keep every line comfortably short); `max_lines` caps
    it with `…` on the last line if there's still more."""
    text = str(text or "").strip()
    if not text:
        return ""
    lines = textwrap.wrap(text, width=width) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        lines[-1] = (last[:width - 1].rstrip() + "…"
                    if len(last) >= width else last + "…")
    return "\n".join(lines)


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
    """What a hovered segment shows: what it was, when and how long, and the
    note if there is one -- each field wrapped to a narrow column rather
    than run out as one long line, so the box stays short enough not to clip
    near an edge (see Panel.paint())."""
    when = (f"{row['start']}–{row['end']}"
            if row["start"] and row["end"] else "untimed")
    lines = [wrap(row_label(row, growth)),
             f"{when}   {hm(row['minutes']) or '0h00'}"]
    note = wrap(row.get("notes", ""))
    if note:
        lines.append(note)
    return "\n".join(lines)
