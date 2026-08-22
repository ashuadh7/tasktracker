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

### Pushing to Notion happens with every write, not at session close

Not batched, not something Ashu has to ask for. Whenever a session with PC file access (Remote Control, or a chat session that happens to have file tools, like this one) appends to `open-day.csv`, seals a day into `time-log.csv`, or writes to `growth-log.csv`, the matching Notion row is created or updated **in the same step** — not deferred to the end of the conversation. "Logged" means "on the desktop *and* in Notion" the instant it lands, not eventually.

This replaced an end-of-session batch-sync habit (via `scripts/sync_plan.py --since`) that had a failure mode: the whole point was to avoid the desktop and Notion drifting apart, but if the session ended, crashed, or moved on before the batch step ran, they drifted anyway — and on 2026-08-16 that's exactly what happened, two days of silence. Writing to both at the moment of logging removes the step that could get skipped.

`scripts/sync_plan.py --since` still exists and is still useful — for reconciling drift after an Excel edit, a session that didn't have Notion tools, or any time drift is suspected. It's a repair tool now, not the default path.

Dump the relevant Notion rows to JSON and run it. It prints four lists:

1. **pull** — phone rows the desktop has never seen. This is the one thing that stays manual: Ashu fetches from Notion himself when he wants the desktop to ingest phone entries. A non-empty pull list is a prompt to ask him, never something to merge on its own — merging it first would make the next step's `create`/`delete` wrong anyway.
2. **create** — desktop rows missing from Notion. Push these through the Notion connector.
3. **delete** — Notion rows the desktop no longer has, from an open day that got rewritten. Notion has no page-delete tool available here, so in practice this means updating the stale page's properties to match rather than removing and recreating it.
4. **reflag** — rows whose `sealed`/`Synced` flags disagree with the desktop.

Diffing in a script rather than by eye is what keeps a log that runs for years from drifting a row at a time. Run it with the full history (no `--since`) at the start of a fresh desktop session, or any time drift is suspected — the windowed form only stays accurate if every prior session actually pushed when it should have.

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
- **Keep `activity` short; put the elaboration in `notes`.** Ashu talks in full sentences — "continued working through the formative study analysis, focusing on the last participant's transcript" — but the row's `activity` should distill that to a label: `formative study analysis`, with the rest in `notes`. This isn't just tidiness: the visualizer's hover tooltip shows `activity` as the headline and wraps `notes` underneath it, so a long `activity` fighting a long `notes` for the same short line is exactly what made tooltips overrun and overlap in practice (see the wrap fix in the repo history). When reflecting a row back in step 2, split it this way rather than dumping the whole sentence into `activity`.

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

## Tagging a distraction chain — the `#drift` note

Some slack isn't just "did something else instead" — it's starting one specific task and never getting back to it because attention wandered mid-task, one thing pulling into another. That shape is worth telling apart from plain slack, because the pattern (which tasks get dropped, what pulls him away) is closer to the actual question this tracker exists to answer than the raw minutes are.

When a note describes exactly that — an intended task that got derailed by something else, and the intended task never happened — prefix the `notes` field with `#drift:`, then the intended task, an arrow, then what actually consumed the time:

```
#drift: <what he meant to do> -> <what actually happened, in order>
```

Example (2026-08-17, 15:02–15:15, `slack`): `#drift: wife called asking him to file an insurance claim -> opened email looking for it, got pulled into an unrelated email, then checked the citizenship-tracker portal; claim never filed`

It's plain text inside the existing `notes` field, not a new column — deliberately, since this is a lightweight version of parking-lot.md **#4** (log the trigger, not just the activity) and **#9** (typed detail per block), not a schema change. `grep '#drift' tracker/*.csv` (or the same pattern in Excel's find) surfaces every instance across the whole history. Building actual tooling around it — a report of which tasks get dropped most, what pulls him away most often — is a `parking-lot.md` idea, not something to build the moment the tag exists.

### `#email-drift` — when the trigger is specifically an email

A sub-case of `#drift`, worth its own tag because it recurs on its own: opening email to check one specific thing and coming out having read two more, minutes later than intended. Same note format, narrower trigger:

```
#email-drift: <what he opened the email to check> -> <what actually happened>
```

Example (2026-08-19, two back-to-back instances): checked email for TAship status (5m), then got pulled into an unrelated email about a CSGSA presidency offer (15m).

`grep '#email-drift' tracker/*.csv` isolates these from the wider `#drift` set. parking-lot.md **#10** already flagged email as a suspected recurring trigger before this tag existed; this makes that hypothesis directly queryable instead of requiring a text search inside `#drift` notes. Doesn't replace `#drift` — a block can still just be `#drift` if the trigger wasn't email-shaped.

## Unit counts on generalizable tasks — precision now, structure later

Most of what gets logged doesn't transfer: one meeting's prep time says nothing about the next one. A small set of tasks are the exception — their *per-unit* rate is roughly stable across contexts, so "how long does one of these actually take me" is a question worth being able to answer from history, someday. That day isn't today: no new column, no new file, no extra logging step. What changes is precision inside the `notes` field on exactly this list, when one of these is what got logged:

- reading one research paper
- prepping one meal
- cleaning the room
- writing one paragraph/page of academic writing
- qualitative-coding one hour of recording
- grading one assignment
- prepping for one meeting
- prepping for one presentation

(Open list — add to it as more generalizable ones surface. Don't add something whose rate wouldn't actually transfer.)

When a logged block is one of these, get the count into the note, not just the duration — `read 3 papers` rather than `read papers`, `graded 5 assignments` rather than `graded for a while`. If Ashu logs one of these vaguely — a duration with no count — ask once for the count rather than letting it pass; don't turn every log into an interrogation over anything off this list.

This is deliberately not a schema change. The point is that once enough precise entries accumulate in plain notes, a future session designing a feature around this has real instances to look at — grep-able the same way `#drift` is — and can decide then whether a structured field is actually earned. Deciding that now, with no data yet, would be guessing.

## Capturing progress — conversational, not scheduled

`progress-log.csv` (see `README.md`) tracks percent-complete per target, and it's captured the same way `#drift` is: whenever Ashu says it, not on a fixed cadence. No sweep through every open target at the start or end of a session — that's a ritual he never asked for and it's exactly the kind of friction that kills a habit.

Two shapes this shows up in:

- **Volunteered, mid-dump.** A logging session that includes "...and I got through about 60% of the formative study analysis" appends a `progress-log.csv` row for that target at that percent, right then — no different from any other fact in the dump.
- **Asked for.** Ashu asking "where am I on X" is answered by reading the current trail back, not by prompting him to re-estimate everything open.

**Never solicited on every `targeted_work` row.** A day full of project work doesn't mean a day full of percent updates — only write a row when Ashu actually states one.

`basis` is optional. Ask for it if it's natural in the moment; a shrug is a fine answer, and forcing one on every update is what would stop the updates happening at all. A percent lower than the target's last entry does need a note explaining the re-scope — `check.py` enforces that one.

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

## Tagging targeted_work to a target

`activity` was never enough to tell which planned item a `targeted_work` row was actually for — `P03`, `reading and writing`, `Throughline work` are labels, not a pointer at a specific row in `targets.csv`. That gap is what made the completion index's click-through (see the visualizer) unable to show more than a project-wide guess. The `target` column fixes it: **every `targeted_work` row gets the exact `targets.csv` `target` string it was toward**, filled in the same pass as everything else in step 2 of the loop, not asked about separately.

- **Ask, don't guess, when it's not obvious.** If exactly one active target for that project fits what he described, fill it in and say so rather than asking. If several could fit, ask which one — batched with the rest of that pass's questions, same as any other ambiguity.
- **Blank is a real answer.** Not every hour of project work maps to something on the plan — ad hoc work, a target not yet in `targets.csv`, cleanup that doesn't belong to any listed item. Leave `target` blank rather than forcing a mismatch; `check.py` only requires it when a fit actually exists and wasn't named.
- **One target per row.** A row that genuinely served two targets should be split into two rows (same as any other bucket-mixing case), not tagged with both.
- **Never retag history.** This rule took effect 2026-08-22; rows before that predate the column and stay blank forever, same as the midnight-crossing sleep rule predating Aug 15. `check.py` only enforces the tag on rows dated on or after the cutover — see `README.md`'s `time-log.csv` columns for the exact rule.

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
| `networking` | `networking` (single category for now — split later if instances show a real pattern, e.g. by relationship type) |

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
