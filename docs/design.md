# Design: the story arc

## Idea

**The year, drawn as a ledger.** GitHub's own artefact, the contribution grid, is the spine of
the film. It is drawn on screen in beat 2 and stays as the texture behind every later beat, so
the whole video reads as one object: your year, annotated. The look is an annual report crossed
with a terminal: a warm carbon ground, paper-white ink, one vermillion signal colour, a heavy
condensed grotesk for numbers and a monospace for labels. No space themes, no neon, no
colour-block cards, no tiers or badges.

One question per beat, one focal point per beat (usually one number or one shape).

## Format

- 1080x1350 (4:5), 30 fps, H.264 + AAC, under 50 MB.
- 36-80 s depending on which beats have data; the beats are chosen from a catalogue by score
  within a time budget (v8, below).
- Text-first: everything that matters is on screen, large enough to read on a phone (labels
  at least 34 px, numbers 160-360 px). Music is optional and sits under the edit.
- Every frame carries the owner's handle and the year in a footer rail, with a beat counter,
  so a frame screenshotted or scrolled into mid-way still says whose year it is.
- Frame 0 is the poster: name, year, headline number, already settled.

## Palette and type

| Role | Value | Use |
|---|---|---|
| ground | `#14120F` | background |
| ink | `#F3EEE4` | primary text |
| muted | `#A39B8E` | labels, secondary text (contrast 6.9:1 on ground) |
| rule | `#2E2A25` | grid empty cells, rules |
| signal | `#FF5B24` | the one accent: focal number, peak cell, highlight bar |
| add | `#8FD694` | diff `+` lines and the added-lines number (own green, not GitHub's) |
| del | `#F2777A` | diff `-` lines and removed-lines number |
| heat ramp | `#3A2A20` `#7A3A1E` `#C2481F` `#FF5B24` | contribution cells by quartile |

Display: Bricolage Grotesque (variable, width 75, weight 800). Labels and captions: JetBrains
Mono 500. Both OFL, bundled in `assets/fonts/`.

## Beats

| # | Beat | Question | Focal point | Data | Length | Fallback |
|---|---|---|---|---|---|---|
| 1 | Hook | Whose year, how big? | headline number counting up | `totals.contributions`, name, year | 3.5 s | always present |
| 2 | The shape | When did it happen? | calendar grid drawn week by week, peak month bracketed | `calendar`, `rhythm.by_month` | 6 s | under 30 active days: show the grid anyway, caption "every square counted" |
| 3 | The run | How consistent? | longest streak number | `rhythm.streak`, `active_days`, `weekend_share` | 5 s | streak under 3: lead with active days instead |
| 4 | The clock | When do you work? | 24-bar hour chart, peak hour lit | `rhythm.by_hour`, `peak_hour`, `latest_night_commit` | 5.5 s | under 40 commits sampled: drop beat |
| 5 | The work | What took the time? | top repo bar with its own description | `repos` minus automation, top 4 | 7 s | no public repos: show languages only |
| 6 | Shipping | What landed? | merged PR count and merge rate | `pull_requests` | 5 s | under 5 PRs: drop beat |
| 7 | Started | What did you start? | count of new repos, most starred one | `new_repos`, `stars.gained` | 5 s | none: drop beat |
| 8 | The surprise | What did you not expect? | automation commits | `automation` | 4.5 s | no automation: use busiest day or latest-night commit |
| 9 | Identity | Who were you this year? | archetype name | derived (see below) | 5 s | always present ("The Builder") |
| 10 | Close | Whose was this, and can I make mine? | handle + year, CTA line | user, repo URL | 4 s | always present |

### v2: terminal and diff language

Every beat opens with a prompt (`~ $`) typing a real git or gh command that would answer the
beat's question, with a blinking block cursor; content enters as the typing finishes. Below it a
7-character hash (stable sha1 of user, year, beat) labels the beat like a commit. Lists render as
diff hunks: `@@` headers, `+` lines on a faint green wash, `-` lines on a faint red one; the
agents beat renders its rows as `Co-authored-by:` trailers. These are associations with git, not
GitHub's UI: no octocat, no GitHub greens, no Primer components.

### Optional beats (v2)

| id | Question | Focal point | Data | Shows when |
|---|---|---|---|---|
| agents | Who did you ship with? | share of commits co-written with agents | `agents` | 10+ signed commits sampled and share 5%+ |
| diff | What was the biggest change? | `+adds -dels` of the largest nameable merged PR | `pull_requests.biggest` | 300+ lines changed |
| releases | What reached users? | releases tagged this year | `releases` | 3+ releases |
| oss | What did you give back? | PRs merged into others' public repos | `pull_requests.external_public` | 3+ PRs |

Framing is always positive ("Shipped with a team", "co-written with"): agents are collaborators
the person directed, never a discount on their work. When agents fire, the automation note moves
into that beat and the surprise beat is skipped.

Beats 2 to 8 drop out when their data is thin, and the total shrinks (minimum about 25 s).

## v3: one thing moving at a time (2026-11-03)

Feedback on v2: "a little busy and too fast; the command-line animation at the same time as the
stats animations is too much."

### What v2 did (measured from frames at 2 fps and the template)

- 12 beats in 59.8 s, 5.0 s a beat on average.
- Content started 0.25 s before the command finished typing, so the typed line and the count-up
  always overlapped. The cursor blinked for the whole beat and the 52-tick footer rail filled
  continuously: three things in motion on every frame.
- Supporting lines entered on a staggered clock from 0.9 s to 2.8 s, so the beat was still moving
  when it left. Settled hold before the exit: run 0.8 s, started 1.0 s, agents 2.1 s.
- On-screen words per second (labels, command, copy): run 7.0, agents 7.2, started 8.5; a
  comfortable reading rate for muted autoplay is about 3.

### The rules for v3

- **One idea per beat, one focal point per moment.** A beat is a question and one answer.
  Supporting copy is at most one line plus at most three rows.
- **Sequential motion.** Phase order inside a beat is fixed: the command types and the cursor
  stops; 0.35 s of stillness; the hero (number, grid, bars) lands; 0.3 s; the supporting group
  enters as one stagger; then nothing moves. Never two phases at once.
- **Hold.** At least 3.0 s of stillness after the last motion of a beat (2.5 s is the floor for
  reading a number and a line at LinkedIn autoplay); the close holds 3.5 s.
- **Motion budget.** One count-up or one draw per beat. No blinking cursor during the hold. The
  footer rail steps once per beat at the cut, not continuously. Exits are a 0.4 s fade.
- **Fewer beats.** 8 to 10 beats in 50 to 75 s. Durations are derived from the content
  (`build.py:beat_timing`), not fixed, so the hold rule holds whatever the copy.
- **Reading rate.** Target 3 words per second of beat or less, counted over everything on screen.

Pacing references: Spotify Wrapped (one stat per card, the number lands then holds, the next
card waits for a tap), GitHub Unwrapped (one stat per scene, about 4 to 6 s each), Apple keynote
stat slides (a single number full-frame, silent hold of several seconds before the next slide).

### Two directions tried

- **A, sequential terminal.** Every beat keeps its typed command at the top; the command types
  and settles, then the stat lands, then the hold. Calmer v2.
- **B, chapters.** The terminal appears only as a full-frame chapter card between three sections
  (rhythm, work, output). Stat beats are clean slides with no prompt: one number, one line.

Blind juror (2026-11-03, frames of v2, A and B unlabelled, against Spotify Wrapped, GitHub
Unwrapped and Apple stat slides) ranked B first on calm, phone readability and shareability, A
second, v2 last ("the cursor is still typing while the bars grow"). B is the default
(`--direction b`); A stays available. Juror's open defects in B: small grey secondary lines at
phone size, chapter cards are sparse, and the cut runs about 72 s.

## v4: readable commands, a clean thumbnail (2026-11-03)

Feedback on v3: "I can't see the commands, are they black on black" and "figure out the
thumbnail, maybe the final screen but cleaner so no slide numbers".

- **Cause.** Not colour. v3 removed the typing tween (and the cursor CSS) from the template when
  it moved the terminal onto chapter cards, but the cards still render an empty `.cmd` span and
  `build.py` still budgets typing time. The cards showed `~ $`, then nothing.
- **Fix.** The template types every `.cmd` whose scene has `type_dur > 0`, from `beat_timing`;
  the command is ink on the ground (16:1), the prompt `--add` (10.9:1); the block cursor fades
  once typing ends (no blinking in the hold). Chapter commands are 40 px, shrunk by
  `term_size` so the longest still fits one line. Every other text colour on the ground or a
  diff tint is at least 5.4:1 (muted on the add tint is the floor).
- **Last frame.** The close drops its hash and `10/10` label and the footer rail fades out, so the
  film ends on the grid, the handle and the CTA only.
- **Thumbnail.** `build.py` writes `thumbnail/`, a motionless one-second composition of the
  close with no label, rail or CTA, centred in the full frame; `hyperframes snapshot` turns it
  into `thumbnail.png` (1080x1350, the video's 4:5 for LinkedIn's custom thumbnail). Frame 0 of
  the video stays the hook (the post when it autoplays).

## v5: the thumbnail is the identity (2026-11-04)

Byron picked option A ("The Weekend Orchestrator", `a3-identity` on the thumbnail board) over
the close. `build.py:build_thumbnail` now renders the identity beat: kicker "@<user> / <year>,
in one line" in mono muted at the top, the name in Bricolage 800 at 75% stretch, one word a line
(names past five words pack two a line before the last), the last word in `--signal`, then the
reason split into one sentence a stat in mono ink, with a repeated "of commits" dropped after
the first. Title size is 190 px, shrunk so the longest line fits 912 px at about 0.36 em a
character (`title_size`). Everything comes from `story.json`, so edits to the name or reason
carry through. A story with no identity beat falls back to the v4 close still.

## v6: each chart takes the shape of its question (2026-11-04)

Feedback on v5: "the chart choice could be more varied and better given what it is showing.
Eg. Claude percentages."

- **What was wrong.** Four of the chart beats were the same mark, a horizontal or vertical bar,
  and the agents bars were misleading: 41/34/14% were shares of Claude's commits, drawn under a
  58% headline, so they read as shares of all commits. The run, ship and releases beats had no
  chart at all, only a number and text.
- **The rule.** Pick the form from the question: a part of a whole is a waffle, a run is a
  stretch of the year, a rate is one filled bar, a cadence is counts on a time axis, a ranking is
  bars. Every part adds up to the headline on screen.
- **agents.** A 10 x 10 waffle, one square per percent of all commits (the ledger's own unit),
  filled per model in signal, light, dark and taupe (told apart by lightness, not hue), the rest
  "you, solo". `alloc` splits by largest remainder so 24 + 19 + 8 + 7 = 58 exactly.
- **run.** The year as one tick a day: active days stand up in grey, the run is a solid signal
  block, with a two-item key.
- **ship.** One bar of PRs opened, filled to the merged share; "90% merged / of 1,344 opened".
- **releases.** One square per release stacked in its month (unit columns), lead project in
  signal; caption is the largest three-day burst when it is 40%+ of the year (`burst_line`).
  Needs `releases.repos[].dates`, collected since v6; older `year.json` keeps the tag list.
- **clock.** Stays a 24-bar histogram, with the peak bar labelled.
- **work.** Stays ranked bars: it is a ranking.

Two directions were built: "fit" (above, with a 24-hour radial dial for the clock) and "units"
(every chart in squares: a stacked bar for agents, a 24-cell heat strip, 45 day squares, a
100-square merge waffle, 44 release squares). A blind juror saw v5, fit and units unlabelled
against Spotify Wrapped, Pudding/NYT unit charts and Apple Screen Time: fit first on four of
five beats, v5's linear histogram over the dial for the clock ("radial is hard to compare on
a phone"), units second (its squares said nothing about when). Fixed from the juror's list:
the clock keeps bars, the "others" legend fits, empty squares and the solo swatch lifted to
read, the run's grey ticks have a key, hyphenated repo names and orphan words no longer break.

## v7: lines against a famous codebase, and machine time (2026-11-04)

Feedback on v6: "I like lines added vs removed. Maybe compare lines total to some famous software
number of lines. Also action run time total minutes would be cool."

- **lines.** Question: how much code moved, and how big is that? Hero: `+added` in `--add`, big,
  beside `-removed` in `--del`. Chart: three bars on one scale, added, removed, and the chosen
  codebase hatched in taupe so it never reads as the person's own. Line: "Added: about one and a
  half times the Quake III Arena source." The unit says what is counted: merged pull requests.
- **actions.** Question: how long did the machines work for you? Hero: total minutes in signal.
  Chart: twelve monthly columns (a cadence is counts on a time axis), the peak month lit and
  labelled. Line: the total as days or hours, and the peak month's share when it is half or more.
- **Collection fixes found on the way.** PRs are fetched a month at a time (one search caps at
  1,000 results; byronxlg's 1,345 PRs had been cut to 1,000, so lines were 474k, not 541k).
  GraphQL calls retry on a 5xx.
- **Length.** Both beats sit in chapters (lines in "The work", actions in "What shipped"); the cap
  is 78 s of estimated beats, which drops the run before them for a busy year (about 79 s with
  chapter cards).

Reference codebases (`build.py:CODEBASES`). All lines counted, blank and comment lines too, as a
PR's additions are. Measured on 2026-11-04 with `wc -l` over a shallow clone unless noted:

| Codebase | Lines | Source |
|---|---|---|
| git's first commit | 1,244 | git/git `e83c516` "Initial revision of git", all 11 files |
| Wolfenstein 3D | 42,178 | github.com/id-Software/wolf3d `0516778`, .c .h .asm |
| Doom | 59,110 | github.com/id-Software/DOOM `a77dfb9` (linuxdoom-1.10, sndserv, ipx, sersrc), .c .h |
| Apollo 11 guidance | 130,186 | github.com/chrislgarry/Apollo-11 `e7576d5`, Comanche055 + Luminary099 .agc |
| SQLite | 222,348 | github.com/sqlite/sqlite `38b4005`, src/ .c .h |
| Quake | 237,508 | github.com/id-Software/Quake `bf4ac42`, WinQuake + QuakeWorld .c .h .s .asm |
| Quake III Arena | 332,692 | github.com/id-Software/Quake-III-Arena `dbe4ddb`, code/ .c .h .s .asm .cpp |
| Linux kernel | about 40,000,000 | Phoronix, "The Linux Kernel Tree About To Hit 40 Million Lines" (April 2026), all lines including blanks and comments; not measured here |

## v8: a catalogue of beats, chosen by score (2026-11-04)

Feedback on the 36-tile idea board: "2, 5, 7, 18, 19 should be added. In the skill it should have
a whole list of options and the best or most appropriate should be chosen. Maybe some are
mandatory and some are optional."

- **What was wrong.** Beats were in or out by thresholds, then cut in a fixed `DROP_ORDER` when
  the film ran long. Every year lost the same beats first, whatever was strong for that person,
  and nothing recorded why a beat was missing.
- **The catalogue.** `build.py:CATALOGUE` lists every beat in film order with its slot,
  mandatory or optional, the data it needs, its eligibility rule and its score rule (the table
  is in `references/story.md`). Mandatory: hook, shape, work, identity, close. Optional beats
  are scored 0 to 1 (a weight for the beat times a log ramp of the person's number against a
  baseline), alternatives in one slot keep only the best, and the best are taken until 78 s.
  `story.json:selection` records what was chosen and what was left out with scores and reasons;
  `--beats` and `--skip` override.
- **Slots with alternatives.** when: clock or punchcard (the punchcard wins when one weekday
  holds over 2/7 of the peak hour); code: lines or the biggest change (both say how much code
  moved; v7 already cut the biggest change first); surprise: the automation or the biggest day.
- **New beats.** Year on year (a column a year, growth as the hero, the years' total when flat
  or down, never the drop); the punchcard (7 x 24 dots, the busiest hour of the week lit); the
  biggest day (the week around it as columns, PRs merged that day); languages by repo (one bar
  split by primary language in signal and the muted ramp, not GitHub's colours); the model
  timeline (each model on the year line at its first trailer, a dated list, the latest lit).
- **Collection.** Two prior-year totals, the weekday-by-hour grid, PRs merged on the busiest day,
  primary language counts, and a first-trailer date per model. Commit search is now paced under
  30 a minute and retried on the secondary rate limit, which had silently emptied the agents
  sample for September to November.

## Archetype

Adjective from rhythm, noun from output, each with a one-line reason shown under the name:

- Adjective: night share over 30% "Night Shift"; morning share over 25% "Early"; weekend share
  over 35% "Weekend"; streak over 30 days "Relentless"; else "Steady".
- Noun, first match: automation over 25% of commits "Automator"; external merged PRs at least
  10 "Contributor"; agent share at least 40% and 100+ agent commits "Orchestrator"; reviews over PRs "Reviewer"; new repos at least 6 "Builder"; merged PRs at
  least 100 "Shipper"; else "Maker".

The agent may override the name and reason in `story.json` if it can write something more specific
from the data; it must stay true to the numbers.

## Truth rules

- Headline total is GitHub's own contribution count (it matches the profile).
- Automation (a repo where at least 60% of sampled commits share one message template) is named
  as such and excluded from rhythm and the "work" beat.
- Private repos are never named; their counts stay in totals.
- Partial years are labelled "so far" (for example "2026 so far").
