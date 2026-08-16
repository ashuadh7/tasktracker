"""Time tracker visualiser.

Stacked 24h bars, one per day, coloured by bucket, with the growth ledger
drawn as a companion strip beneath them. Run it through `scripts/viz.py`,
which is where the usage and key bindings are documented.

The package is layered, and the layers only ever import downward:

    theme       the vocabulary -- buckets, tiers, the palette. No dependencies.
    formats     numbers and rows -> the short strings the chart prints.
    model       the CSVs -> DataFrames the charts can stack. pandas, no pyplot.
    window      which days are on screen, and how you move between them.
    selection   what's selected, and what follows from it.
    hits        where each row ended up, so a click can find it again.
    panels/     one class per axes: bars, strip, timeline, summary, detail.
    app         the figure: layout, event routing, redraw.
    cli         arguments in, a window or a PNG out.

The first three know nothing about matplotlib, which is the point -- the parts
where a wrong answer is silent rather than visible can be checked without
opening a window.
"""
