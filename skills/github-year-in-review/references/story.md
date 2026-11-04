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

## Beats

| id | Shows | Data | Drops when |
|---|---|---|---|
| hook | name, contributions count, repos and active days | `totals`, `user` | never |
| shape | the year grid, peak month boxed, caption | `calendar`, `rhythm.by_month` | never (caption adapts to thin years) |
| run | longest streak drawn as a block on the year line (one tick a day) | `rhythm.streak` | streak under 3 days |
| clock | 24 hour bars, peak hour labelled, latest commit | `rhythm.by_hour` (automation excluded) | under 40 sampled commits |
| work | top 4 public, non-automated repos, lead repo quote | `repos` | no public repos |
| ship | merged PRs, merge rate as one filled bar of PRs opened, notable external merge | `pull_requests` | under 5 PRs |
| started | new repos count, top 3 by stars, stars gained | `new_repos`, `stars` | no new repos |
| agents | share co-written with agents as a 10 x 10 waffle of all commits, split by agent (by model when one agent), agent PRs | `agents` | under 10 signed commits sampled or share under 5% |
| diff | biggest nameable merged PR as `+adds -dels`, year's lines as a hunk | `pull_requests.biggest` | under 300 lines |
| lines | the year's `+added -removed` as two numbers, then added, removed and a famous codebase as bars on one scale; "Added: about twice the ..." | `pull_requests.lines_added/removed`, `build.py:CODEBASES` | under 1,000 lines added or 5 merged PRs |
| actions | GitHub Actions minutes on your repos, minutes by month (peak month lit and labelled), the total in days | `actions` | missing, under 60 minutes or 20 runs |
| releases | releases tagged, one square per release stacked by month, the biggest burst as caption | `releases` | under 3 |
| oss | PRs merged into others' public repos | `pull_requests.external_public` | under 3 |
| surprise | automation commits, or busiest single day | `automation`, `rhythm.busiest_day` | when the agents beat is present |
| identity | archetype name and the reason | derived in `build.py:archetype` | never |
| close | year grid, handle, CTA | `user` | never |

## story.json fields safe to edit

`label`, `title`, `caption`, `line`, `sub`, `ext`, `unit`, `lead`, identity `name` and `reason`,
close `cta`, `rows[].desc`, lines and actions `sub`, `cmd` (the typed command; keep it a real command), agents `sub`/`auto`. Keep `number` fields as collected. Delete a beat object to drop it
(not `hook`, `identity`, `close`). Durations are minimums from `build.py:MIN_DURATION`; if
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
