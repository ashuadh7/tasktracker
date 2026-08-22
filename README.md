# Time Tracker — Schema Contract

The point of this tracker: answer "how much did I actually slack, what was it, and am I over-packing my weeks?" — comparably, week over week, for years.

## Files

## Layout

```
E:\Planner\
├── tracker\              <- this folder. Data at the root, code in scripts\
│   ├── *.csv
│   ├── scripts\          <- check.py, viz.py, sync_plan.py
│   │   └── timeviz\      <- the visualizer, split by layer; see its __init__
│   └── skill\            <- the phone-side log-my-time skill
└── Weekly Planner\       <- planning workflow and weekly checklists
```

Data sits at the tracker root and code sits one level down, so opening the folder shows you the log rather than the machinery.

**The CSVs are safe to open and edit directly in Excel.** `scripts/csv_io.py` is what every script reads and writes through: it decodes whatever encoding the file is actually in (Excel saves Windows CSV in the system codepage, not UTF-8, so a curly quote or ellipsis you type becomes a byte plain `utf-8` chokes on) and zero-pads times Excel has reformatted (`00:00` → `0:00`). Every clean run of `check.py` rewrites each file to canonical form — UTF-8 with a BOM, zero-padded times — so formatting drift never accumulates regardless of which app touched the file last.

One thing this can't protect against: Excel's live auto-formatting *as you type*, before anything is ever saved. A `notes` cell typed as `10/12` or `1-2` can become a date the moment you leave the cell. If you need to type something that looks like a date or fraction into a text field, prefix it with `'` (apostrophe) to force Excel to treat it as text.

Every script resolves its paths from `__file__`, so run them from anywhere:

```bash
python scripts/check.py
python scripts/viz.py
```

## Reading the chart

**The clock timeline is always on screen, on top** — one row per day, every block placed where it actually happened. Time-of-day patterns (obligations clustering at 08:00 and again at 16:00–19:30) read in one glance here; a stacked bar can't show them at all, because it's cumulative and deliberately says nothing about *when*.

Beneath it, unselected, both ledgers are on screen at once — the 24h bars, then the growth strip. That comparison of *how much* is the second question, once *when* has been answered by the timeline above it.

**Click any segment** — on the timeline, the bars, or the strip — and the view changes to answer a narrower one:

- Everything else fades, in the chart *and* in the index at the same time, so one category reads straight across the week.
- **The ledger you didn't click gets out of the way.** Click a bucket and the growth strip goes; click a growth category and the 24h bars go. It isn't answering the question any more.
- **The panel underneath lists the rows**: day, time of day, duration, project · activity, and the note in italic. Every row gets the same treatment however many there are — scroll the panel for the rest, and the header says where you are (`1–9 of 14`).

Click it again, click a gap, or press Esc to clear.

Rows with no start/end can't be placed on a clock, and guessing would be a fabrication — they're totalled at the right edge of their day instead (`2h00 untimed`).

`python scripts/viz.py --select slack --png out.png` does all of it headlessly.

**`--day-tags path/to/file.csv`** tints the timeline's per-day row by an
arbitrary category from a `date,tag` CSV that lives entirely outside this
repo's own schema — the tracker only ever sees a date and a string, never
what the tag means. A day with no matching row falls back to the ordinary
zebra stripe. This is for whatever varies day-to-day and isn't itself an
activity: which days follow one schedule versus another, a recurring
external constraint, anything you'd otherwise have to remember by looking
elsewhere.

This was one of two arrangements tried behind a toggle in issue #5 — bars-on-top with the timeline conjured only by a selection was the other. Both were used for real; this one won, and the toggle and the losing arrangement are gone.

## Files

| File | What it holds |
|---|---|
| `time-log.csv` | What actually happened. Sealed days only. Append-only. |
| `open-day.csv` | The day currently being logged, however partial. Same schema. |
| `growth-log.csv` | The growth ledger — an overlay on the same minutes. Never reconciled to 24h. |
| `plan.csv` | What was allocated ahead of time. Written when a week is planned. |
| `projects.csv` | Lookup for the project column. The only file that changes when your work changes. |
| `targets.csv` | Lookup for planned work items — one row per item, with its hour estimate. |
| `progress-log.csv` | The progress ledger — a percent-complete trail per target. Append-only. |

Plan vs. actual is a join on `date` + `project`. Keeping them in separate files means the plan stays frozen as written — you can see what you *believed* on Sunday, not a version edited to match reality.

## The progress ledger

`time-log.csv` says where the minutes went. `progress-log.csv` says how much of the planned work is actually done — a different question the minutes can't answer, since hours spent and progress made aren't linear. Two items can eat the same hours and land at very different completion states, so this ledger deliberately carries no time correlation: no rate, no minutes-per-point, nothing that implies progress should track hours logged.

```
targets.csv       target,project,window,minutes,status,notes
progress-log.csv  date,target,percent,basis,notes
```

**A target is a planned work item** — the grain a plan actually lists, one level above a day's scheduled block (`plan.csv`) and one level below a project. `minutes` is its hour estimate; `window` records which planning window it was first committed in, so a later retrospective can compare what was committed against what got finished. `status` is `active` / `done` / `dropped` — a target abandoned partway isn't the same as one still in flight at the same percent.

**`progress-log.csv` is append-only**, dated by when the judgment was made, not when the work happened. The trail — `0 → 40 → 60` — is the point; a mutable percent field would keep today's number and throw the history away. A percent lower than the target's previous entry is allowed (re-scoping is real) but requires a `notes` explanation, so a backwards step reads as a deliberate correction rather than a silent contradiction.

**A project's percent is never entered — it's computed**, hours-weighted across its targets: `sum(minutes × percent) / sum(minutes)`. Where a plan's own section header disagrees with the sum of its items' estimates, the items win.

`basis` is optional — a short anchor for the number ("3 of 7 sections drafted") worth having in three years, but not required on every update. Requiring it is what would stop the updates from happening.

Capture is conversational, not scheduled: a percent gets recorded whenever it's stated, the same opportunistic shape as the `#drift` note in `logging-protocol.md` — never a fixed sweep.

## time-log.csv columns

```
date,start,end,minutes,bucket,domain,project,activity,target,confidence,notes
```

- **date** — ISO `YYYY-MM-DD`, always. Never "Aug 10" (no year, sorts wrong).
- **start**, **end** — `HH:MM` 24h. Leave blank for anything non-contiguous (eating, cleaning). Blank is fine and expected.
- **minutes** — integer. The only field every calculation reads. Never "1 hr 30 mins".
- **bucket** — the analysis axis. **Fixed vocabulary, never extend casually** (see below).
- **domain** — `research` / `teaching` / `personal` / `health` / `admin`. Blank for sleep, necessities, slack.
- **project** — free string, validated against `projects.csv`. Blank when not project-work.
- **activity** — what you actually did, **short — a label, not a sentence**. `formative study analysis`, not `continued working through the formative study analysis, focusing on P07's transcript`. The elaboration belongs in `notes`; see there for why this split matters more than it looks.
- **target** — which `targets.csv` row this was actually toward, exact string match. Only meaningful on a `targeted_work` row; blank everywhere else. This is the join `activity` free text can't safely be, because `activity` is a label like `P03` or `transcription` with nothing pointing at a specific planned item — see the completion index's click-through, which sums this column rather than guessing from `activity`. **Forward-only**: rows before 2026-08-22 predate the tag and stay blank, same as the midnight-crossing sleep rule predating Aug 15. `check.py` requires it on any `targeted_work` row dated on or after that, the same way it requires a named `activity` on `slack`.
- **confidence** — `logged` (recorded same day) or `reconstructed` (rebuilt after the fact). Aug 11–14 2026 is all `reconstructed` and should not be trusted at the same precision as later weeks.
- **notes** — free text, the detail `activity` deliberately leaves out. Quote the field if it contains a comma. **This split is what makes the visualizer's hover tooltip readable**: it shows `activity` as the headline and `notes` wrapped underneath, so a long `activity` and a long `notes` both fighting for the same short line is what used to make tooltips overrun and overlap the panel next to them (see `logging-protocol.md`). Keeping `activity` to a few words isn't just tidiness — it's the label a tooltip, the detail list, and a three-years-later skim all read first.

## The bucket vocabulary — this is the part that must not drift

| Bucket | Means |
|---|---|
| `sleep` | Sleep. |
| `necessities` | Non-negotiable life upkeep: eating, showering, cleaning, cooking, wife transport, evening time together. |
| `obligations` | Logistics that consume time but produce nothing: driving, prep-to-leave, clinic, shopping. |
| `work` | Real work that isn't one of your projects: grading, proctoring, meetings. |
| `targeted_work` | Work on your projects. The number that actually matters. |
| `slack` | Unaccounted time. The residual. |
| `rest` | Deliberate, chosen time off — a planned day off, not drift. |

**`slack` vs `rest` is the whole analysis.** Slack is time that leaked. Rest is time you decided to take. Collapsing them makes every number useless — a 12h day off would read identically to 12h of drift.

Every date's rows should sum to **1440 minutes**. Slack is what's left after everything else is entered — derive it, don't estimate it.

## The growth ledger

`time-log.csv` answers *where did my day go*. `growth-log.csv` answers *what was I putting into myself* — and those are different questions about the same minutes, so they get different files.

An audiobook during the dishes is `necessities / dishes` in the time log **and** `audio / audiobook` here. No double-counting problem, because only one of the two files is required to sum to 1440. This one is never reconciled against anything.

```
date,start,end,minutes,tier,category,mode,bucket,source,activity,confidence,notes
```

| Tier | Categories |
|---|---|
| `reading` | `fiction` · `non-fiction` · `article` |
| `audio` | `podcast` · `audiobook` |
| `self-care` | `self-improvement` · `hobby` · `physical` · `mental` |

Same discipline as buckets: the **tier** is the comparison axis that has to mean the same thing in 2029, the category is the useful detail underneath. `article` means genuinely well-written long-form, not hot takes. `mental` covers diary, note-keeping, rambling at an AI to think something through. `physical` is exercise, walks, runs.

Three fields carry the design:

- **`mode`** — `concurrent` (rode along with something else, cost zero extra minutes) or `dedicated` (this *was* the activity). Without it the ledger says "3h of growth" and you can't tell what was free.
- **`bucket`** — echoes what the time log called the same block. This is the interesting one, below.
- **`source`** — the actual book, podcast, or article. What makes this worth reading back in three years instead of just a number.

### The two files are allowed to disagree

A novel read while procrastinating is `slack` in the time log and `reading / fiction` here, **both correct at once**. It earns its credit as growth and still counts against you as leaked time. That tension is real and the tracker should hold it rather than resolve it.

The echoed `bucket` is what turns that into a number: *6h of growth this week, 4h of it slack-shaped.* The visualizer prints exactly that line. `check.py` verifies each echoed bucket is backed by real minutes in the time log that day, which is the only thing that can silently drift between the two files.

### Minutes here can exceed the clock

A 45-minute run with a podcast on is **one** row in the time log (45m `necessities`) and **two** here — 45m `physical` `dedicated`, 45m `podcast` `concurrent`. Ninety growth-minutes inside a forty-five-minute window. That is correct and intended. The growth strip can and sometimes will overshoot the bar above it.

Exercise, incidentally, sits in `necessities` in the time log. It's life upkeep in the same sense a shower is, and giving it its own bucket would grow the one vocabulary that must not grow.

## Why this survives your work changing

Projects end, get renamed, get absorbed. Org structure shifts. Three rules keep history intact:

1. **One row = one block of time. Never one column per project.** A wide table (a `Throughline` column, a `Vibecoding` column) breaks the moment a project is added or dropped, and every past row has to be rewritten. Long format never does.
2. **Buckets are stable, projects churn.** The bucket vocabulary is the comparison axis — it has to mean the same thing in 2029 as it does today. Project names are just labels attached to rows.
3. **History is never rewritten.** When a project ends or is renamed, edit `projects.csv` — set `status` to `archived`, put the new name in `successor`. The log keeps saying `Throughline` forever, and the lookup explains what that became.

Reorganizing your work should touch one small lookup file, never 3,000 rows of history.

## Day boundary

A day runs **midnight to midnight**. Plain calendar days, no cleverness.

The consequence is that a night crossing midnight is **two rows on two dates** — a trailing block closing one day, a leading block opening the next. A day therefore holds up to two sleep rows, plus naps.

That looks like extra work and buys something specific. The visualizer pins the leading block to the floor of the bar and the trailing block to the very top, above the unlogged grey, so a night reads as **the top of Monday plus the bottom of Tuesday** — recoverable by eye, off two adjacent bars, without arithmetic. Wake-to-wake days can't do that: they hide the boundary inside a single row and you lose when you actually went to bed.

Sleep rows need `start` and `end` for this to work. A leading block starts `00:00`, a trailing block ends `00:00`. Anything else with times is a nap and stacks in the middle; an untimed sleep row falls to the floor.

**Aug 11–14 2026 predate this rule** — they carry flat untimed 6h blocks from the wake-to-wake era, and they stay that way. History is never rewritten to match a new rule; the rule applies going forward, and those days are `reconstructed` anyway.

## When to stop using CSV

When you have several years of data and want relational queries across it, migrate to SQLite. That's a one-way trip that takes about ten minutes and loses nothing. Don't do it early — CSV is hand-editable, diffable, and every plotting library reads it directly. The format is not the risk; inconsistent strings and free-text durations are.
