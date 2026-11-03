# Story reference

The full rationale and sources are in the repo's `docs/research.md` and `docs/design.md`. This is
what the agent needs at run time.

## Identity: the ledger

Warm carbon ground `#14120F`, paper ink `#F3EEE4`, muted `#A39B8E`, one signal colour `#FF5B24`,
heat ramp `#6A3A22 #A3431F #D9501F #FF5B24`. Bricolage Grotesque (width 75, weight 800) for
numbers and names, JetBrains Mono for labels. A footer rail on every frame: handle, year, and
52 week ticks that fill as the film plays. The contribution year (12 month rows x 31 days) is
the recurring object: drawn in beat 2, returned as the closing image.

## Beats

| id | Shows | Data | Drops when |
|---|---|---|---|
| hook | name, contributions count, repos and active days | `totals`, `user` | never |
| shape | the year grid, peak month boxed, caption | `calendar`, `rhythm.by_month` | never (caption adapts to thin years) |
| run | longest streak, active days, weekend share | `rhythm.streak` | streak under 3 days |
| clock | 24 hour bars, peak hour, latest commit | `rhythm.by_hour` (automation excluded) | under 40 sampled commits |
| work | top 4 public, non-automated repos, lead repo quote | `repos` | no public repos |
| ship | merged PRs, merge rate, reviews, notable external merge | `pull_requests` | under 5 PRs |
| started | new repos count, top 3 by stars, stars gained | `new_repos`, `stars` | no new repos |
| surprise | automation commits, or busiest single day | `automation`, `rhythm.busiest_day` | never |
| identity | archetype name and the reason | derived in `build.py:archetype` | never |
| close | year grid, handle, CTA | `user` | never |

## story.json fields safe to edit

`label`, `title`, `caption`, `line`, `sub`, `ext`, `unit`, `lead`, identity `name` and `reason`,
close `cta`, `rows[].desc`. Keep `number` fields as collected. Delete a beat object to drop it
(not `hook`, `identity`, `close`). Durations are minimums from `build.py:MIN_DURATION`; if
`check` reports `line_unread` for a line, shorten the line first, lengthen the beat second.
