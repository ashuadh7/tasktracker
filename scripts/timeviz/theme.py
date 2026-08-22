"""The chart's vocabulary: what the categories are, and what colour each is.

This is the module with the longest half-life. The bucket names are the
comparison axis that has to mean the same thing in 2029, and the palette is an
argument rather than a decoration -- so a change here changes what the chart
says, not just how it looks. Nothing in this file imports matplotlib or knows
what a figure is.

Three independent rankings share the chart, not one flat scale:
  - work axis: targeted_work > work > obligations > necessities -- one blue
    hue, saturation and lightness moving together so it reads as one ramp.
  - flag axis: slack > rest -- a second hue (amber), since slack is a thing
    to notice and address, not a quieter shade of the same blue.
  - background axis: sleep > unlogged -- barely distinguishable; position in
    the stack already carries the meaning, colour is just a tiebreaker.
"""

# Ranked ascending -- least attention-grabbing first, so this list doubles as
# the chart's bottom-to-top stacking order. Changing a hex changes what the
# chart argues, so change them deliberately.
BUCKETS = [
    ("sleep", "#B1B8C4"),          # background   - pale blue-grey
    ("rest", "#D0C1AF"),           # flag, low    - soft dusty amber
    ("slack", "#C2822E"),          # flag, HIGH   - vivid amber
    ("necessities", "#C9CFD9"),    # work, lowest - palest blue
    ("obligations", "#7591BD"),    # work         - muted mid blue
    ("work", "#4175C8"),           # work         - medium blue
    ("targeted_work", "#1B58BB"),  # work, HIGHEST- vivid cobalt
]
BUCKET_COLOR = dict(BUCKETS)
BUCKET_ORDER = [b for b, _ in BUCKETS]

# Stack order, bottom -> top, matching the ranking above. Sleep appears three
# times: the block that opens the day, naps in among everything else, and the
# block that closes it.
SLOTS = [
    "sleep_leading",
    "rest", "slack", "necessities", "obligations", "work", "targeted_work",
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
    ("audio", [("audiobook", "#498D84"),
               ("podcast", "#95B2AE")]),
    ("self-care", [("self-improvement", "#665393"),
                   ("hobby", "#A9A2B9"),
                   ("physical", "#4F7E4E"),
                   ("mental", "#93AA92")]),
]
TIER_ORDER = [t for t, _ in TIERS]
# The tier's darkest category stands in for it wherever one swatch is needed.
TIER_COLOR = {t: cats[0][1] for t, cats in TIERS}
GROWTH_MODES = ["concurrent", "dedicated"]

# Not a bucket - this is absent data, so it gets the faintest neutral there is.
UNLOGGED_COLOR = "#E6E8EA"

# Colours for an optional, schema-external per-day tag (see --day-tags in
# cli.py) -- the tracker never knows what a tag means, only how many distinct
# values showed up, so this stays a plain rotation rather than a vocabulary.
DAY_TAG_PALETTE = ["#C9A66B", "#6E8FAE", "#8FA67B", "#AE6E8F"]

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


def day_tag_colors(tags):
    """tag value -> hex, stable within a run and deterministic across runs
    (sorted, not first-seen), drawn from DAY_TAG_PALETTE."""
    names = sorted(set(tags))
    return {name: DAY_TAG_PALETTE[i % len(DAY_TAG_PALETTE)]
            for i, name in enumerate(names)}


def ink_on(hex_color):
    """Readable text colour for a fill. Half this palette is pale enough that
    white labels disappear into it, so the choice has to be computed."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return INK if luminance > 0.55 else "white"
