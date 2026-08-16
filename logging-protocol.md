# Logging Protocol

How a spitball becomes rows in `time-log.csv`.

## Two ways to capture

Ashu logs from his phone — parking lot, bed, between things. Two paths, same protocol:

**1. Remote Control (preferred).** `claude remote-control` on the PC, then the Claude app's Code tab or `claude.ai/code`. Same session, real file access — it reads `open-day.csv` and writes the CSV directly. Requires the PC to be on and the session running.

**2. Claude chat + Notion (fallback, for when the PC is off).** The `log-my-time` skill runs in Claude chat, does the same glean/correct loop, and writes rows to the Notion **Time Log** database (`collection://1ad4daf6-5c68-4902-b08b-4abb434a691e`, under Task Organizer). The correction loop happens live, on the phone, while he still remembers — which is the whole reason this path exists rather than just dumping raw notes for later.

Either way the conversation is identical. Only the destination differs.

### Notion is a mirror, not an inbox

**Every row the desktop holds also lives in Notion.** Not just the unsynced ones — the whole log. That makes Notion an online copy visible from anywhere, the same role the weekly plan pages play, and it removes a whole class of special cases: there is no "stale open day from four days ago" to clean up, because a day the desktop sealed sums to 1440 in Notion too, and therefore reads as finished to the phone automatically.

The desktop is the authority. Notion never overrules it. The only thing Notion knows that the desktop doesn't is a row created on the phone, and that's exactly what `Synced` marks.

**`Synced` means "the desktop has this row"** — it exists in `time-log.csv` or `open-day.csv`. Rows pushed from the desktop are born with it checked. Rows created on the phone start unchecked, and stay that way until the desktop ingests them.

Sync runs at the start of a desktop session, and again after any day is touched:

```bash
python scripts/sync_plan.py notion_rows.json
python scripts/sync_plan.py --growth growth_rows.json
```

Dump the Notion rows to JSON first, then run it. It prints four lists:

1. **pull** — phone rows the desktop has never seen. **Handle these first**, before anything else, or the next step will delete them.
2. **create** — desktop rows missing from Notion.
3. **delete** — Notion rows the desktop no longer has, from an open day that got rewritten.
4. **reflag** — rows whose `sealed`/`Synced` flags disagree with the desktop.

Diffing in a script rather than by eye is what keeps a log that runs for years from drifting a row at a time.

## Three files, one rule

- **`open-day.csv`** — the day currently being logged, however partial. Same schema as the sealed log.
- **`time-log.csv`** — sealed days only. Every date in it reconciles to exactly 1440 minutes.
- **`growth-log.csv`** — the growth ledger. Overlays the same minutes, reconciles to nothing.

Nothing partial ever lands in `time-log.csv`. A half-logged day sitting in there is indistinguishable from a day that genuinely had a lot of unlogged time, and that ambiguity would quietly rot every number built on top of it.

The first two share a schema so one script can reason about both, and **sealing a day is just moving its rows from one file to the other**. `check.py` validates all three — the 1440 rule applies only to the sealed file, the open file is merely checked for not exceeding 24h, and the growth ledger is checked for vocabulary and for agreeing with the time log about which buckets a day contained.

## Editing directly

Ashu sometimes edits `open-day.csv` by hand in Excel rather than through a chat conversation — easier to see and correct on a real grid. That's a legitimate way to log, not a workaround. The scripts tolerate whatever Excel does to the file (see `scripts/csv_io.py`); `check.py` is what recovers it back to canonical form, so it should be run right after such an edit same as after any append. Never revert a hand-edit found on `git status`-equivalent inspection — take it as intentional and validate it, per the usual rule.

## Opening a logging conversation

Claude reads `open-day.csv` **before asking anything**, and opens by stating what's already covered:

> "I have Sat Aug 15 through 4pm — NSERC 2h, lunch, drive to campus. What happened after that?"

Never ask Ashu what's already been logged. He's logging precisely so he doesn't have to hold it himself.

## The loop

1. **Ashu dumps.** Unstructured, out of order, vague on times. Claude does not interrupt.
2. **Claude reflects back structured rows** — minutes, bucket, project, activity — with every guess marked as a guess.
3. **Ashu corrects.**
4. Repeat 2–3 until he approves. Usually two passes, sometimes three.

Rules for step 2:

- **Never invent a duration silently.** "Worked on Throughline in the morning" → propose a number, flag it: *(guess — 2h?)*. Never just pick one and move on.
- **Auto-fill the standing baseline** (below) rather than asking. He should only have to mention what was *different*.
- **Ask about anomalies, not routine.** "Did you shower?" is noise. "You got home at 7:30 — did the evening with your wife still happen, or did that get eaten?" is signal.
- **Batch the questions.** All of them in one pass, not one at a time.

## The standing baseline — fill it in, don't ask

| Activity | Bucket | Default | Applies |
|---|---|---|---|
| eating | `necessities` | 2h00 | every day |
| shower | `necessities` | 30m | every day |
| cleaning and cooking | `necessities` | 1h20 | every day |
| wife transport | `necessities` | 40m | days she works |
| evening with wife | `necessities` | 2h15 | days he's home before ~9pm |

Claude fills these silently, then lists them at the end under "assumed defaults" so they're visible and correctable. Skip any that the day's shape rules out — home past midnight means no evening-with-wife block.

**Sleep is not on that list**, because it can't be a single number any more. Days run midnight to midnight, so a night that crosses midnight is two rows on two dates. Ask for the two times he actually knows — *when did you get to bed, when did you get up* — and split at midnight yourself:

- Went to bed 23:40, up at 05:30 → **20m trailing** on the earlier date, **330m leading** on the later one.
- Went to bed 00:20, up at 06:00 → nothing trailing on the earlier date, **340m leading** on the later one.

Leading blocks start `00:00`, trailing blocks end `00:00`, and both need their times filled in — that's what pins them to the floor and ceiling of the bar in the visualizer, so a night can be read off two adjacent days. Naps are `sleep` with ordinary times and stack in the middle.

The bed time belongs to the *previous* day's row, which means a day can rarely be sealed the same evening. In practice the trailing block arrives with the **next morning's first message**: "got up at 5:30, went to bed around 11:40" fills in yesterday's closing row and today's opening one in a single answer. So the natural rhythm is — seal yesterday when he opens today. If a day ever gets sealed without a trailing block, the missing minutes show up as residual; ask about them rather than assuming he never went to bed.

## Sealing a day

A day seals when Ashu says it's done, or automatically when he starts logging a later day.

1. Sum the rows. **Residual = 1440 − total.**
2. **Residual > 0 → that's the slack. Ask what it actually was.**
   Not "you had 2h of slack" — *"what were those two hours?"* Scrolling, YouTube, gaming, lying down, staring at the wall, recovering from a bad night. The answer goes in the `activity` column.
   **`slack / unaccounted` is a logging failure, not a finding.** The original question behind this whole tracker was *what accounts for the slack* — a row that just says "unaccounted" answers nothing.
3. Residual < 0 → something overlaps. Find the overlap; never scale everything down to fit.
4. Show the sealed day. Get approval.
5. Append to `time-log.csv` → run `python scripts/check.py` → clear `open-day.csv`.

Growth rows are written as they come up, not at sealing — they're already final the moment they're entered, because nothing about them has to add up. The one thing sealing changes for them: `check.py` stops treating a mismatched echoed `bucket` as a warning and starts treating it as an error, since the day it points at is now fixed.

## confidence — per row, not per day

- `logged` — entered during the day it describes.
- `reconstructed` — entered the next day or later.

A day logged at 10am, 4pm, and then finished the following morning is a mix. Mark each row for when *it* was captured.

## When he genuinely can't remember

Leave the day out of `time-log.csv` entirely. It renders as a grey unlogged bar, which is honest and shows up as a gap in logging discipline.

**Never fabricate a day to close a gap.** Invented rows are worse than missing ones — once a plausible guess is in the file it is indistinguishable from data, and the entire point of this tracker is finding out what's actually true.

## Bucket decisions — settled once, applied forever

| Thing | Bucket | Note |
|---|---|---|
| Meeting of any kind | `work` | `project` column still names the project |
| Grading, proctoring, email, admin | `work` | |
| Reading / writing / coding on a project | `targeted_work` | the number that matters |
| Driving, prep-to-leave, waiting around | `obligations` | |
| Clinic, appointments | `obligations` | |
| Shopping, errands | `obligations` | |
| Eating, shower, cooking, cleaning | `necessities` | |
| Time with wife | `necessities` | |
| Naps | `sleep` | |
| Exercise, walks, runs | `necessities` | also a `self-care / physical` row in the growth ledger |
| Deliberate day off | `rest` | never `slack` |
| Drift, scrolling, gaming | `slack` | name the activity |

Two things at once → the dominant one wins. No double counting; the day must sum to 1440. **The thing that lost goes in the growth ledger if it belongs there** — see below.

## The growth ledger

The time log answers *where did the day go*. `growth-log.csv` answers *what was he putting into himself*. Same minutes, different question, so it never touches the 1440 arithmetic.

```
date,start,end,minutes,tier,category,mode,bucket,source,activity,confidence,notes
```

| Tier | Categories |
|---|---|
| `reading` | `fiction` · `non-fiction` · `article` |
| `audio` | `podcast` · `audiobook` |
| `self-care` | `self-improvement` · `hobby` · `physical` · `mental` |

- **`mode`** — `concurrent` if it rode along with something else (audiobook over the dishes), `dedicated` if it *was* the activity.
- **`bucket`** — what the time log called that same block. `necessities`, `slack`, `work`, whatever it actually was.
- **`source`** — the book, podcast, or article by name. Worth asking for; it's what makes the ledger readable years later.

**When to write a row.** Any time he mentions an audiobook, podcast, novel, well-written article, exercise, hobby-building, journalling, or a long think-it-through session. He will usually mention these in passing while describing something else — *"did the dishes and listened to my audiobook"* is one time-log row and one growth row.

**Don't ask about it separately.** No "did you listen to anything today?" pass. It rides on the dump he was already giving.

### The two files are allowed to disagree

A novel read while procrastinating is `slack` in the time log and `reading / fiction` in the ledger, both correct. It gets credit as growth and still counts as leaked time. **Never soften the time-log bucket because the ledger looks good** — a slack row that reads `rest` because he was reading something worthy destroys the number he built this to find.

### Minutes here can exceed the clock

A 45-minute run with a podcast on is one time-log row and two growth rows — 45m `physical` `dedicated` plus 45m `podcast` `concurrent`. Ninety growth-minutes in a forty-five-minute window, and that's right. This file does not reconcile.

## Example — the three-pass day

**~10am, Ashu:** *"Got up at 6, did NSERC for a couple hours, then breakfast."*
Claude writes to `open-day.csv`: sleep 6h, NSERC 2h `logged`, eating (partial). Says: *"Have you through ~9am. NSERC 2h — right number?"*

**~4pm, Ashu:** *"Drove to campus, marked all afternoon."*
Claude opens with what it has, adds drive 1h30 + marking (asks: until when?), writes back to `open-day.csv`. Day still open.

**Next morning, Ashu:** *"Forgot to finish yesterday."*
Claude: *"I have you through 4pm — NSERC 2h, drive, marking. What happened after, and what time did you get to bed?"* Ashu dumps the evening. Claude totals, finds a 1h50 residual, asks what it was, gets "YouTube," seals the day, appends, runs `scripts/check.py`.

## Planning sessions feed `plan.csv`

When a planning session produces a schedule, its `targeted_work` allocations get written to `plan.csv` at the same time. That's what makes the planned-vs-actual number in the visualizer work. See [planning-workflow.md](../Weekly%20Planner/planning-workflow.md).
