"""Robust CSV read/write for files Ashu edits by hand in Excel.

Excel's "CSV (Comma delimited)" save on Windows writes the system codepage,
not UTF-8 -- so the moment he types a curly quote, em dash, or ellipsis and
saves, that character becomes a byte plain `utf-8` can't decode. Reading
falls back through encodings so that byte becomes real text instead of a
crash or a silent `?`.

Writing always uses UTF-8 **with a BOM** (`utf-8-sig`) -- the encoding Excel
itself expects for CSV on Windows. A file written this way round-trips
correctly: Excel opens it, shows the right characters, and if it saves in
UTF-8 too the next read still works.

Excel also reformats anything it decides looks like a time: `00:00` becomes
`0:00`, `07:30` becomes `7:30`. That silently breaks the `00:00`/`24:00`
sentinel checks the sleep-sandwich logic depends on, so every read here
zero-pads `start`/`end` back before the row is handed to calling code --
the rest of the tracker never has to know which app wrote the file last.
"""

import csv
import io
from pathlib import Path

ENCODINGS = ("utf-8-sig", "cp1252")


def norm_time(value):
    """'0:00' -> '00:00'. Blank stays blank, anything not H:MM passes through
    unchanged rather than being mangled."""
    value = (value or "").strip()
    if not value:
        return value
    parts = value.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return value
    h, m = parts
    return f"{int(h):02d}:{int(m):02d}"


def _decode(path):
    data = path.read_bytes()
    last_err = None
    for enc in ENCODINGS:
        try:
            return data.decode(enc)
        except UnicodeDecodeError as e:
            last_err = e
    raise last_err


def read_rows(path):
    """(fieldnames, rows) from a CSV, decoded leniently and time-normalized.

    Rows are plain dicts, filtered to those with a non-blank first column --
    every CSV in this tracker keys on its first column (`date` for the logs,
    `project` for projects.csv), and Excel is prone to leaving trailing blank
    rows behind. `fieldnames` is returned too so a canonical rewrite can
    preserve the original column order.
    """
    path = Path(path)
    if not path.exists():
        return [], []
    text = _decode(path)
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    key = fieldnames[0] if fieldnames else None
    rows = []
    for row in reader:
        if key is None or not (row.get(key) or "").strip():
            continue
        for time_col in ("start", "end"):
            if time_col in row:
                row[time_col] = norm_time(row[time_col])
        rows.append(row)
    return fieldnames, rows


def normalize_file(path, fieldnames, rows):
    """Rewrite `path` in canonical form if it isn't already: UTF-8 with BOM,
    zero-padded times, `\\n` line endings, minimal quoting.

    Returns True if the file's bytes changed. Safe to call every time --
    a file already in canonical form is left untouched (and unwritten, so it
    doesn't pick up a spurious mtime).
    """
    path = Path(path)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    new_bytes = buf.getvalue().encode("utf-8-sig")

    old_bytes = path.read_bytes() if path.exists() else None
    if new_bytes == old_bytes:
        return False
    path.write_bytes(new_bytes)
    return True
