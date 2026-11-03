# github-year-in-review

A Claude Code skill that turns a GitHub user's year into a 45-second video made for LinkedIn:
4:5, readable with the sound off, honest about bots and private repos, and ending on who you
were this year instead of a pile of totals.

Sibling of [`/brag`](https://github.com/latent-spaces/brag) (project launch videos); same
HyperFrames rendering path.

![byronxlg 2026 poster](examples/byronxlg-2026.jpg)

Example: [examples/byronxlg-2026.mp4](examples/byronxlg-2026.mp4) (50 s, 1080x1350, 3 MB).

## What the film shows

1. Your name and the year's contribution count.
2. The year as a grid, one square per day, with the loudest month boxed.
3. Your longest streak, active days, and weekend share.
4. The hour you commit most, and your latest-night commit.
5. The projects that took the time.
6. Pull requests merged, and notable merges into other people's repos.
7. Repos you started, and stars they earned this year.
8. A surprise: commits made by automation you built, or your single busiest day.
9. An archetype ("The Weekend Builder") with the reason in one line.
10. The year grid again, your handle, and a call to make yours.

Beats with thin data drop out, so a quiet year makes a shorter film rather than an empty one.
Design and research: [docs/design.md](docs/design.md), [docs/research.md](docs/research.md).

## Install

With [skillfold](https://github.com/byronxlg/skillfold):

```bash
skillfold add github:byronxlg/github-year-in-review/skills/github-year-in-review -g
```

Or copy `skills/github-year-in-review/` into `~/.claude/skills/`.

Needs: `gh` (authenticated), Python 3.9+, Node 18+ (`npx hyperframes`), ffmpeg. The
HyperFrames skills (`hyperframes-core`, `hyperframes-cli`) help the agent with check and render.

## Use

In Claude Code: `/github-year-in-review` (your account, this year), or
`/github-year-in-review --user octocat --year 2025`.

The scripts also run on their own:

```bash
S=skills/github-year-in-review/scripts
python3 $S/collect.py --user octocat --year 2025 --out out/year.json
python3 $S/build.py out/year.json --out out            # writes out/story.json and out/composition/
cd out/composition && npx hyperframes check && npx hyperframes render --output ../year-in-review.mp4
```

## Privacy and honesty

- Private repositories count toward totals but are never named unless `--include-private`.
- Repos where most commits share one message template (a cron committing as you) are reported as
  automation and kept out of the rhythm stats.
- Partial years are labelled "so far".

## Music

No music ships with this repo. If `/brag` is installed its bundled tracks and cue presets work
with `--music` and `--cues` (scene starts snap to the beat). Without a track the film is silent,
which suits LinkedIn's muted autoplay.

## Tests

```bash
python3 -m unittest discover -s tests
```

MIT. Fonts (Bricolage Grotesque, JetBrains Mono) are SIL OFL.
