# Story reference

The full rationale and sources are in the repo's `docs/research.md` and `docs/design.md`. This is
what the agent needs at run time.

## Identity: the ledger

Warm carbon ground `#14120F`, paper ink `#F3EEE4`, muted `#A39B8E`, one signal colour `#FF5B24`,
heat ramp `#6A3A22 #A3431F #D9501F #FF5B24`. Bricolage Grotesque (width 75, weight 800) for
numbers and names, JetBrains Mono for labels. A footer rail on every frame: handle and year,
nothing else. Each beat opens with a typed `~ $` command and the section name, never a number
(no slide counter, hash label, part numbers or progress ticks); lists are diff hunks (`+` `#8FD694`, `-` `#F2777A`). The contribution year (12 month rows x 31 days) is
the recurring object: drawn in beat 2, returned as the closing image.

## Beats: the catalogue

`build.py:CATALOGUE` is the source of truth (`build.py --catalogue` prints it); this table mirrors
it, in film order. **Mandatory** beats are in every film that has their data and are never cut
for time. **Optional** beats must pass their eligibility rule, then compete on score: beats that
share a slot are alternatives and only the higher score plays; the rest are taken best first
until the estimated beats fill `MAX_TOTAL` (78 s; chapter cards come on top; `--pace tight` has none and
its beats are about 0.56 as long). A score of 0 never plays. The film keeps
this order whatever the scores.

Scores run 0 to 1: a weight for how much the beat says in general, times the strength of this
person's number on a log ramp, `ramp(x, lo, hi)`, which is 0 at the baseline `lo` and 1 at `hi`
(a 45-day streak is 0.81 x 0.9, a 4-day one 0.1 x 0.9).

| id | slot | kind | shows | data | eligible when | score |
|---|---|---|---|---|---|---|
| hook | hook | mandatory | name, contributions, repos and active days | `totals`, `user` | always | - |
| shape | shape | mandatory | the year grid, peak month boxed, caption | `calendar`, `rhythm.by_month` | always (caption adapts to thin years) | - |
| yoy | yoy | optional, new | "56x the contributions of 2025", a column a year | `history` | a prior year with 10+ contributions | 0.9 x ramp(growth, 1.25x, 20x); flat or down: the years' total, 0.1 |
| run | run | optional | longest streak as a block on the year line | `rhythm.streak` | streak of 3+ days | 0.9 x ramp(days, 3, 60) |
| clock | when | optional | 24 hour bars, peak hour labelled | `rhythm.by_hour` | 40+ sampled commits | 0.7 x off-hours (ramp(night share, 10%, 45%) or ramp(morning share, 10%, 40%), floor 0.2) |
| punchcard | when | optional, new | busiest hour of the week as the hero, 7 x 24 dots by commits | `rhythm.by_weekday_hour` | 150+ sampled commits | clock score x week lift / 2 |
| work | work | mandatory | top public, non-automated repos, lead repo quote | `repos` | 1+ public repo that is not automation | - |
| languages | languages | optional, new | top primary language, one bar of every repo split by language | `repo_languages` | 5+ repos with a language, 2+ languages | 0.5 x ramp(repos, 5, 40) |
| agents | agents | optional | share co-written with agents as a 10 x 10 waffle | `agents` | 10+ signed commits sampled, share 5%+ | 1.0 x ramp(share, 5%, 60%) |
| models | models | optional, new | each model on the year line at its first trailer, latest lit | `agents.model_first_seen` | 3+ versioned models this year | 0.75 x ramp(models, 3, 10) |
| ship | ship | optional | merged PRs, merge rate as one filled bar | `pull_requests` | 5+ PRs opened | 0.9 x ramp(merged, 5, 500) |
| lines | code | optional | the year's `+added -removed`, bars against a famous codebase | `pull_requests.lines_added/removed` | 1,000+ lines added over 5+ merged PRs | 0.85 x ramp(added, 1k, 300k) |
| diff | code | optional | biggest nameable merged PR as `+adds -dels` | `pull_requests.biggest` | 300+ lines | 0.6 x ramp(lines, 300, 20k) |
| actions | actions | optional | Actions minutes, by month | `actions` | 60+ minutes over 20+ runs | 0.7 x ramp(minutes, 60, 50k) |
| releases | releases | optional | releases, one square each by month | `releases` | 3+ releases | 0.8 x ramp(releases, 3, 60) |
| started | started | optional | new repos, top ones by stars | `new_repos`, `stars` | 1+ new repo | 0.75 x ramp(new repos, 1, 30) |
| oss | oss | optional | PRs merged into others' public repos | `pull_requests.external_public` | 3+ | 1.0 x ramp(PRs, 3, 50) |
| surprise | surprise | optional | automation commits ("were not you") | `automation` | 50+ automation commits, and agents does not play (the cron is named there) | 0.8 x ramp(automation share, 5%, 50%) |
| day | surprise | optional, new | busiest day as the hero, the week around it as columns, PRs merged that day | `rhythm.busiest_day`, `calendar` | 10+ contributions and 3x+ the mean active day | 0.7 x ramp(busiest / mean active day, 3x, 30x) |
| identity | identity | mandatory | archetype name and the reason | derived in `build.py:archetype` | always | - |
| close | close | mandatory | year grid, handle, CTA | `user` | always | - |

Why these are mandatory: hook is frame 0 (the post), shape is the ledger's recurring object,
work answers the question every year in review is asked (what took the time), identity is the
ending the film is built towards, close is the cover. Ship is optional: plenty of good years are
direct pushes, and a PR-heavy year scores it near the top anyway. Work still needs one public,
non-automated repo; without one it is left out (private names are never shown).

Week lift (punchcard): the share of the peak hour's commits that fall on its weekday, against
an even 1/7 (1 = even, 7 = all on that day). Over 2, the week says something the hours alone
do not, and the punchcard outscores the clock. The punchcard and clock use the same commit
sample (top repos' history, local time, automation excluded).

### story.json `selection`

`build.py` records the choice: `selection.chosen` (id, slot, mandatory, forced, score) and
`selection.left_out` (id, slot, score or null when there was no data, and the reason: no data,
the alternative scored higher, over the time budget, skipped, or the agents beat names the
automation). Read it before writing copy. To change the choice, rebuild from `year.json`:

```bash
python3 build.py year.json --out <out> --beats models,day --skip run
```

`--beats` forces optional beats in (counted against the budget first; an alternative in the same
slot makes way); `--skip` leaves optional beats out. Mandatory beats cannot be skipped. A forced
beat with no data stays out and the reason says so. Deleting a beat object from `story.json`
and rebuilding with `--story` also drops it; adding one needs `--beats`, since its data comes
from `year.json`.

### story.json `cuts`

`--pace suite` only. One row per cut: `from`, `to`, `n` (number in `assets/transitions.js`), `name`, `d`
seconds, `why` (`pair for <beat>`, `neutral` or `--cut`). Derived on every build: to change one, set
`cut_force` (`{"lines": 61}`) or `cut_skip` (`[51, 52]`), or pass `--cut` and `--cut-skip`. Pairs, best first,
from `build.py:PAIRS` (`build.py --transitions` prints them with names): shape 49, 50; yoy 62; run 53;
clock 46, 63; punchcard 65; work 68, 66; languages 64; agents 66, 67; models 72; ship 69; diff 59, 47, 58;
lines 60, 61, 47; actions 70, 71, 72; releases 75; started 67, 74; oss 76; surprise 71, 74; day 54, 56;
identity 73; close 57, 58, 76. Neutral: 42, 43, 56, 55, 52, 51.

## story.json fields safe to edit

`label`, `title`, `caption`, `line`, `sub`, `ext`, `unit`, `lead`, identity `name` and `reason`,
close `cta`, `rows[].desc`, lines and actions `sub`, `cmd` (the typed command; keep it a real command), agents `sub`/`auto`. Keep `number` fields as collected. Delete a beat object to drop it
(not `hook`, `identity`, `close`). Durations are derived by `build.py:beat_timing`; if
`check` reports `line_unread` for a line, shorten the line first, lengthen the beat second.

## Agents: how it is counted

`collect.py:agent_sample` searches `author:<user>` commits month by month (up to 100 a month,
automation repos excluded) and `classify_commit` looks for signatures only: `Co-authored-by`
trailers, "Generated with" footers, agent bot authors, agent emails. Monthly hit rates are
weighted by each month's total. Agent PRs: search counts per agent (body footer or app author)
combined with head-branch prefixes (`claude/`, `codex/`, `copilot/`) by taking the larger per
agent. Everything is a lower bound; say "co-written with", never "written by".

## Lines: how it is counted

`pull_requests.lines_added` and `lines_removed` sum `additions` and `deletions` over the user's
merged PRs created this year (direct pushes are not counted; generated files and lockfiles are,
as GitHub counts them). The unit says "lines in merged pull requests", with ", at least" when
fewer PRs were fetched than were opened. `build.py:codebase_match` compares lines added with the
largest codebase in `CODEBASES` no bigger than 1.25x the total, so the line reads "about the size
of", "about one and a half times", "about twice" or "about N times". Every figure there counts all
lines, like a PR diff; sources in `docs/design.md` (v7). Below 1,000 lines there is no comparison.

## Actions: how it is counted

`collect.py:actions_time` lists every workflow run (REST `actions/runs`, 100 a page, unfiltered
because a `created` filter caps at 1,000) on the user's own non-fork repos pushed this year,
private ones included and never named. A run's minutes are `run_started_at` to `updated_at` of a
completed run, clipped at 6 h: wall clock, parallel jobs once, so it is time waited, not billable
minutes. 100 pages a repo and 600 pages in total; past either, the rest of that repo's runs for
the year (from `total_count`) are estimated at the mean minutes per run and listed in
`estimated_repos`, and the beat says "Partly estimated." `by_month` is measured runs only, by
the local month the run started. `actions` is null when no repo could be read; the beat drops.

## The new beats: how they are counted (v8)

- **yoy**: `history` is `contributionsCollection` totals for each of the two years before (one
  GraphQL call each, skipped before the account existed). Compared with the latest prior year
  with 10+ contributions. A partial year is compared as it stands ("so far" in the sub).
- **punchcard**: `rhythm.by_weekday_hour`, the clock's commit sample as weekday (Monday first)
  by local hour. Dot area is proportional to commits.
- **day**: `rhythm.busiest_day.prs_merged` counts merged PRs whose `mergedAt` falls on that date
  (UTC, like the calendar). The columns are the seven calendar days around it.
- **languages**: `repo_languages` counts the primary language of each owned, non-fork repo
  pushed this year, private ones included (counted, never named). Drawn in the ledger ramp,
  never GitHub's language colours.
- **models**: `agents.model_first_seen` lists each versioned model name in a `Co-authored-by`
  trailer of the sampled commits ("(1M context)" and the like folded in), dated by one
  oldest-first commit search per model, confirmed against the found commit's own trailer. A
  model that never appears in the monthly sample is missed, so the count is a lower bound.
