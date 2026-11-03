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
- 36-46 s depending on which beats have data.
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

Beats 2 to 8 drop out when their data is thin, and the total shrinks (minimum about 25 s).

## Archetype

Adjective from rhythm, noun from output, each with a one-line reason shown under the name:

- Adjective: night share over 30% "Night Shift"; morning share over 25% "Early"; weekend share
  over 35% "Weekend"; streak over 30 days "Relentless"; else "Steady".
- Noun, first match: automation over 25% of commits "Automator"; external merged PRs at least
  10 "Contributor"; reviews over PRs "Reviewer"; new repos at least 6 "Builder"; merged PRs at
  least 100 "Shipper"; else "Maker".

The agent may override the name and reason in `story.json` if it can write something more specific
from the data; it must stay true to the numbers.

## Truth rules

- Headline total is GitHub's own contribution count (it matches the profile).
- Automation (a repo where at least 60% of sampled commits share one message template) is named
  as such and excluded from rhythm and the "work" beat.
- Private repos are never named; their counts stay in totals.
- Partial years are labelled "so far" (for example "2026 so far").
