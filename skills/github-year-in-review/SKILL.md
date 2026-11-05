---
name: github-year-in-review
description: Turn someone's GitHub year into a short, postable year-in-review video (4:5, about 45 s, made for LinkedIn) using HyperFrames. Use when someone says "/github-year-in-review", "/year-in-review", "make my GitHub wrapped", "my year in code", "GitHub recap video", or wants to share what they shipped this year. Pulls real data with the gh CLI, or with no login at all from a public handle; no screenshots or uploads.
---

# /github-year-in-review

Your year on GitHub, as a 45-second film you can post.

Rendered with HyperFrames, delivered with the poster baked as frame 0, a cover thumbnail and
share copy. The story is data, so the data and the beat logic ship as scripts and the agent's
job is to check the numbers, sharpen the copy, look at the frames, and deliver.

## Invocation

```
/github-year-in-review
/github-year-in-review --user octocat --year 2025
/github-year-in-review --include-private --no-music
```

| Option | Default |
|---|---|
| `--user` | the authenticated `gh` user; any other handle runs on public data, no login needed |
| `--year` | the current year (labelled "so far" until Dec 31) |
| `--tz` | this machine's timezone (used for the hour-of-day beat); on public data, each commit's own clock |
| `--public` | off: public data only, no token, even for your own account |
| `--include-private` | off: private repos are counted, never named |
| `--no-music` | music on if a track is available |
| `--format` | `portrait` 1080x1350 (only format shipped) |

Output goes to `year-in-review-<user>-<year>/` in the current directory (add a timestamp if it
exists). `<skill-dir>` is the directory holding this file.

## Requirements

Python 3.9+, Node 18+ with `npx hyperframes`, ffmpeg. `gh` authenticated (`gh auth status`) only for
your own account's full numbers; a handle alone works without it.
The HyperFrames domain skills (`hyperframes-core`, `hyperframes-cli`) for check and render.

## Step 1: Collect

```bash
python3 <skill-dir>/scripts/collect.py --user <login> --year <year> --out <out>/year.json
```

About two minutes for a busy account (commit history is sampled for the clock beat). It writes
totals, the daily calendar, rhythm (streak, hours, weekdays), top repos, languages, pull
requests, new repos, stars gained this year, and **automation**: repos where at least 60% of
sampled commits share one message template (a cron committing as the user), the contribution
totals of the two years before (year on year), and the primary language of each owned repo. Automation is kept
out of the rhythm and "work" beats and becomes its own surprise beat.

It also collects the optional, topical data: **agents** (commits co-written with coding agents,
detected from signatures only, plus agent PRs by footer, app author and `claude/`-style branch
prefixes), **releases** tagged this year, the biggest merged PR, the year's **lines** added and
removed (summed over merged PRs; PRs are fetched a month at a time so the search's 1,000-result
cap does not cut them), and **actions**: GitHub Actions run time on the user's own repos (every
workflow run listed, wall clock from start to finish; a page budget caps very busy accounts and
the rest is estimated and flagged). These become beats only
when the numbers are there (thresholds in [references/story.md](references/story.md)).

**No login.** With `--public`, with no `gh` login, or with a `--user` who is not you, it answers the
same queries from public data with no token (`scripts/collect_public.py`): about four minutes and at
most 60 API requests, the hourly limit per IP. A token would count that person's private work you
happen to share, so `--include-private` is the only way to run a token on someone else's account.
`year.json` gets `source.mode: public`, and the film then claims only what public data can back:
it says "public" on lists and leaves commit-share claims out. `source.skipped` says what ran out or
failed: tell the user, and rerun after the hour if a beat they want depends on it. "No requests
left" means another run or tool used the IP's hour; wait for it.

**Gate:** read `year.json` and sanity-check it before building. Headline total should match the
number on the user's GitHub profile for that year. If something looks wrong (a bot the detector
missed, a repo that should not be named), fix the collector or use `story.json` overrides; never
hand-edit numbers into the composition.

## Step 2: Story

```bash
python3 <skill-dir>/scripts/build.py <out>/year.json --out <out> \
  [--music <track.mp3>]
```

This writes `<out>/story.json` (beats, copy, timings), `<out>/composition/` (the film) and
`<out>/thumbnail/` (a one-second still of the identity for the cover, see step 4).

The beats come from a catalogue ([references/story.md](references/story.md), `build.py
--catalogue`): mandatory beats (hook, shape, work, identity, close) are always in when their data
exists; optional beats need their data to pass a threshold, then are scored for this person (how
strong their number is against a baseline), alternatives in one slot (clock or punchcard,
surprise or busiest day, lines or biggest change) keep only the higher score, and the best are
taken until the time budget is full. The film's order is fixed by the catalogue, not the scores.
A quiet year makes a shorter film, not an empty one.

**Pace.** `--pace tight` (test, not yet the default) drops the chapter cards, cuts between beats,
runs motion at 0.6 speed and holds 2.5 s, so about 17 beats fit where calm fits 11. `--story`
rebuilds keep the pace unless you pass it again.

**Transitions.** `--pace suite` (test, not yet the default) adds a transition on every cut, from
the suite in `assets/transitions.js` (`build.py --transitions` lists it). Each card has its own,
drawn from what the card is about: the real calendar into the shape, the streak snake into the
run, the merge button into the merged PRs, the checks passing into machine time, the handle's
identicon into the identity. The close is the exception, a plain crossfade: the last card arrives quietly. None shows a card's hero
number before the card lands. A card whose own are used takes the next, then a neutral grid; nothing
repeats while there are others. `story.json:cuts` records each choice. Change them with
`--cut lines=61,ship=1` (any number in the file) and `--cut-skip 51,52`; `--story` rebuilds keep them.

**Review the selection.** `story.json` has `selection.chosen` and `selection.left_out`, each
with its score and, for those left out, the reason. Ask whether the film is the best one for this
person: a left-out beat may say more about them than a chosen one (a new maintainer's open
source PRs, a model timeline for someone who writes about agents). Swap with:

```bash
python3 <skill-dir>/scripts/build.py <out>/year.json --out <out> --beats <id,id> --skip <id,id>
```

`--beats` forces optional beats in (an alternative in their slot makes way), `--skip` drops
optional beats; mandatory beats stay. Say what you swapped and why when you deliver.

Then read `story.json` and improve the copy where you can be more specific than the defaults
(captions, the archetype name and reason, the work-beat quote). Rules:

- Every claim must be true to `year.json`. No invented numbers, no superlatives the data does
  not back.
- Short lines. The type is large on purpose; anything over about 12 words will not hold long enough.
- No private repo names unless `--include-private`.
- No emojis, no em dashes, no "crushing it" register. It is going on LinkedIn.
- Frame agents and automation as a team the person led ("shipped with", "co-written with").
  Never shame, never imply the work was less theirs; agent counts are lower bounds.

Rebuild from the edited story with `--story <out>/story.json` (timings are re-derived).

Music: no track ships with the skill; bring one the user has the rights to post (an mp3 or
m4a, ideally at least as long as the film). With `--music`, build.py detects the beat grid with
`npx hyperframes beats --json <track>` and starts each scene on the nearest beat (later only,
under 0.3 s). To reuse a grid, save that JSON and pass `--cues <beats.json>`; any file with a
`beatTimes` or `beats` array works. If detection fails the film builds without beat sync.
Without a track the film is silent, which is fine: LinkedIn autoplays muted.

## Step 3: Check, render, look

```bash
cd <out>/composition
npx hyperframes check                       # gate: zero errors; fix line_unread and type-floor warnings too
npx hyperframes render --quality draft --output ../draft.mp4
```

Extract one settled frame per beat and look at every one yourself before rendering final.
Also look at each chapter card after its command has typed (about 2.5 s into the card): the
full command must be on screen, one line, ink on the dark ground.

```bash
for t in $(jq -r '.beats[]|.start+.duration-0.5' ../story.json); do
  ffmpeg -loglevel error -ss $t -i ../draft.mp4 -frames:v 1 ../frame-$t.png; done
```

Look for: overflow or clipped text, a number that does not match `year.json`, an empty or
boring beat, text that would not read at phone size (scale a frame to 540 px wide), a weak
first frame. Fix the cause in `story.json` (copy) or report it as a skill bug; then:

```bash
npx hyperframes render --quality high --output ../year-in-review.mp4
```

## Step 4: Deliver

Poster: the hook's settled frame (about 2.9 s) is the thumbnail. Bake it as frame 0 so every
platform that uses the first frame as the preview shows a finished frame, not a fade-in:

```bash
cd <out>
ffmpeg -ss 2.9 -i year-in-review.mp4 -frames:v 1 -q:v 2 poster.jpg
ffmpeg -y -i year-in-review.mp4 -i poster.jpg \
  -filter_complex "[0:v][1:v]overlay=0:0:enable='eq(n,0)'[v]" \
  -map "[v]" -map '0:a?' -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p \
  -c:a aac -b:a 160k -movflags +faststart tmp.mp4 && mv tmp.mp4 year-in-review.mp4
```

Thumbnail: the identity as a cover. A mono kicker at the top ("@<user> / <year>, in one line"),
the archetype name huge in condensed Bricolage, one word a line with the last word in signal
orange, then the stats behind it in mono ink ("57% of commits shipped with agents." / "38% on
weekends."), all from `story.json`; no slide counter, hash label, footer rail or CTA. Long names
shrink to fit 1080 px. A story with no identity beat gets the close (year grid, handle,
"<year>, in review.") instead. Upload it as the video's custom thumbnail on LinkedIn
(it matches the video's 4:5 aspect ratio, which LinkedIn expects) and use it anywhere a cover
image is asked for:

```bash
cd <out>
npx hyperframes check thumbnail
npx hyperframes snapshot thumbnail --at 0.5 --no-end -o thumbnail/shots
cp thumbnail/shots/frame-00-at-0.5s.png thumbnail.png
```

**Gate:** `year-in-review.mp4` is H.264, 1080x1350, under 50 MB, 25-85 s (build caps the beats at 78 s estimated, plus chapter cards); `poster.jpg` exists; `thumbnail.png` is 1080x1350 and you have looked at it (no counters, no rail, the name on its lines and nothing clipped).

Write `<out>/share-copy.txt`: two or three plain sentences in the user's voice, built from the
strongest true facts (the archetype, one number, one project). No hashtag wall; at most two.
Example: "My 2026 on GitHub, so far: 30 new repos, a 44-day streak, and a bot that out-committed
me. Made with github-year-in-review."

Tell the user where the video, thumbnail, poster and share copy are, and one line on what the film says.

## Creative laws

- **Frame 0 is the post.** Name, year and the headline number, settled.
- **One question, one focal point per beat.** Big number or one shape; everything else is a label.
- **Identity over inventory.** The film ends on who they were (archetype), not on a total.
- **Honest.** Automation is named, private names are hidden, partial years say "so far".
- **Readable muted.** Every beat makes sense with the sound off.
- **Nothing numbered.** No slide counter, hash label, part numbers or progress ticks; a beat
  carries its section name only.
- **Git, not GitHub.** Typed prompts, diff hunks and trailers; no logos, no
  GitHub greens or UI chrome.
- **Original look.** The ledger identity in [references/story.md](references/story.md); do not
  restyle it into Wrapped or Unwrapped.
