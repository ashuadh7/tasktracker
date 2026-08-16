"""The chart's vocabulary: what the categories are, and what colour each is.

This is the module with the longest half-life. The bucket names are the
comparison axis that has to mean the same thing in 2029, and the palette is an
argument rather than a decoration -- so a change here changes what the chart
says, not just how it looks. Nothing in this file imports matplotlib or knows
what a figure is.

Only targeted work is saturated. Everything you cannot not do is a
desaturated blue-grey that recedes. The ranking IS the palette.
"""

# One hue, ranked by how much attention the category deserves. Targeted work
# is the only saturated colour on the chart. Changing a hex changes what the
# chart argues, so change them deliberately.
BUCKETS = [
    ("sleep", "#AAB8C5"),          # background   - pale blue-grey
    ("necessities", "#C2CFD9"),    # background   - palest blue-grey
    ("obligations", "#536578"),    # background   - dark muted navy-grey
    ("rest", "#9DB6CF"),           # tertiary     - soft dusty blue
    ("work", "#5B7DB1"),           # secondary    - medium slate-blue
    ("targeted_work", "#2563EB"),  # PRIMARY      - vivid cobalt
    ("slack", "#7C72B8"),          # secondary    - muted blue-violet
]
BUCKET_COLOR = dict(BUCKETS)
BUCKET_ORDER = [b for b, _ in BUCKETS]

# Stack order, bottom -> top. Sleep appears three times: the block that opens
# the day, naps in among everything else, and the block that closes it.
SLOTS = [
    "sleep_leading",
    "necessities", "obligations", "rest", "work", "targeted_work", "slack",
    "sleep_nap",
    "sleep_trailing",
]
SLOT_BUCKET = {s: ("sleep" if s.startswith("sleep_") else s) for s in SLOTS}

# Growth ledger. Each category carries its own colour, related within a tier
# but distinguishable -- so the strip reads as nine nameable things rather
# than three blocks you have to hover to identify.
TIERS = [
    ("reading", [("fiction", "#4F6F8F"),
                 ("non-fiction", "#7895AE"),
                 ("article", "#A9BDCD")]),
    ("audio", [("podcast", "#5F8583"),
               ("audiobook", "#91AAA7")]),
    ("self-care", [("self-improvement", "#786F8D"),
                   ("hobby", "#9B92AA"),
                   ("physical", "#718673"),
                   ("mental", "#9AAA9B")]),
]
TIER_ORDER = [t for t, _ in TIERS]
# The tier's darkest category stands in for it wherever one swatch is needed.
TIER_COLOR = {t: cats[0][1] for t, cats in TIERS}
GROWTH_MODES = ["concurrent", "dedicated"]

# Not a bucket - this is absent data, so it gets the faintest neutral there is.
UNLOGGED_COLOR = "#E5E7EB"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

GROWTH_KEYS = []          # stack order for the strip
GROWTH_COLOR = {}
CATEGORY_COLOR = {}
CATEGORY_TIER = {}
for _tier, _cats in TIERS:
    for _cat, _hex in _cats:
        CATEGORY_COLOR[_cat] = _hex
        CATEGORY_TIER[_cat] = _tier
        for _mode in GROWTH_MODES:
            _key = f"{_tier}|{_cat}|{_mode}"
            GROWTH_KEYS.append(_key)
            GROWTH_COLOR[_key] = _hex


def blend(hex_color, amount, toward=SURFACE):
    """Move a colour toward another. 0 = unchanged, 1 = fully `toward`."""
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(toward[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(
        round(x + (y - x) * amount) for x, y in zip(a, b))


def ink_on(hex_color):
    """Readable text colour for a fill. Half this palette is pale enough that
    white labels disappear into it, so the choice has to be computed."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return INK if luminance > 0.55 else "white"
