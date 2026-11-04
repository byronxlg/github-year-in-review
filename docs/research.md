# Research: what makes a year-in-review worth posting

Focused desk research, 2026-11-03. Sources are mostly marketing and practitioner blogs, not
studies; the themes below are the ones that repeat across several of them.

## Why people share recaps

- **Identity, not data.** Wrapped works because the result says something about the sharer.
  It balances two needs: belonging (everyone is posting theirs) and standing out (mine is
  different). A recap that only lists numbers is a receipt; one that names a trait ("you code
  at night", "you ship on weekends") is a mirror. [nogood][nogood], [Fortune][fortune],
  [psychologs][psychologs]
- **Self-presentation.** Shared recaps are curated self-presentation (Seidman 2013, cited by
  [psychologs][psychologs]). On LinkedIn that means the recap must flatter credibly: real work,
  real outcomes, nothing that reads as gamed.
- **Personal, shareable, no strings.** The format wins when the sharer does nothing but post it,
  and every frame carries the owner's name. [ADMA][adma]
- **Story over infographic.** Strava's Year in Sport, built by Manual, Stink, and Hello Monday in
  different years, starts from a storyboard of the athlete's year and gives the data a shape
  that is celebratory and specific, with one personal film per athlete.
  [It's Nice That][strava-manual], [Stink][strava-stink], [Hello Monday][strava-hm]

## Developer recaps today

- **GitHub Unwrapped** (Remotion, open source, about 1.3k stars) renders a personal video per
  user from GitHub stats. Its look is a space and game theme. [gittrend][unwrapped]
- **Clones** (GitHub Wrapped 2025, GitStory, Git Wrapped, year-in-code) converge on the same set:
  commits, streaks, top languages, peak hour, and an archetype label ("The Night Owl
  Refactorer"), exported as cards for X and LinkedIn. Some add tiers ("Novice" to "Mythic").
  [dev.to][wrapped25], [himashaherath][devwrapped], [webdesignerdepot][gitwrapped]
- **What they get wrong**:
  - Vanity first. Raw commit counts and streaks are inputs, not outcomes, and are easy to inflate
    (backdated commit generators exist precisely to paint the graph). GitHub itself dropped the
    streak counter in 2016 because it pushed people to commit for the square.
    [hackernoon][gaming], [TNW][tnw], [runsteady][runsteady]
  - Bots counted as the person. A cron that commits as you turns you into a "night owl" and
    inflates every total. None of the tools above separate automation.
  - Private repo names leak into public cards.
  - Score tiers and badges read as a game on LinkedIn, where the audience is colleagues and
    hiring managers.
  - Generic visuals: the recap looks the same for everyone, so it says nothing about you.

## What developer stats are interesting

Interesting (says something about the person, or surprises them):

- The shape of the year: when it got loud, the quiet stretch, the busiest single day.
- Rhythm: when they actually work (hour, weekday vs weekend), the longest run of days.
- What they built: the projects that took the time, with their one-line descriptions.
- Shipping: pull requests merged, and work merged into other people's repos.
- New things started this year and the attention they earned (stars gained this year, not all-time).
- An honest surprise: a bot you wrote that out-committed you; a 4 am commit.
- A trait they would put in a bio (archetype), derived from the data, explained in one line.

Vanity (de-emphasise or drop): lines of code, raw commit count as the headline, follower count,
badges and tiers, language percentages to two decimals.

## LinkedIn native video

- **Aspect ratio**: 4:5 (1080x1350) or 1:1 take the most mobile feed space; 16:9 suits demos.
  4:5 is the most consistent recommendation for feed posts. [Kapwing][kapwing], [quso][quso],
  [captions][captions]
- **Length**: limits are 3 s to 10-15 min, but engagement guides put organic posts under about
  60 s, and most recaps that work are 30-45 s. [opus][opus], [sotrender][sotrender]
- **Sound off**: feed video autoplays muted; captions and on-screen text carry the message.
  Music is a bonus for the few who unmute. [clipchamp][clipchamp], [socialmediatoday][smt]
- **Hook**: the first 2-3 seconds decide the scroll. Put the person's name and the biggest
  number on frame one. [Kapwing][kapwing]
- **File**: MP4, H.264, AAC. Organic limit is far above any short video (5 GB); keep it small
  anyway (under 50 MB) for fast processing. [compresto][compresto]
- **Thumbnail**: LinkedIn's post editor accepts a custom thumbnail; elsewhere frame 0 is the
  thumbnail, so frame 0 should be a finished, postable frame (bake the poster in as frame 0).

## Implications (fed into design.md)

1. Lead with name plus one big number, readable on frame 0.
2. Every beat answers "what does this say about me", not just "how many".
3. Separate automation from the human; report it as a surprise beat, not as the person.
4. Never name private repos.
5. 4:5, 35-45 s, text-first, music optional, mono captions large enough for a phone.
6. Original identity built from GitHub's own artefact (the contribution grid) rather than the
   space, neon, or colour-block looks used by Unwrapped and Wrapped.
7. End with a trait the sharer would claim, then a quiet call to action for viewers to make theirs.

[nogood]: https://nogood.io/blog/spotify-wrapped-marketing-strategy/
[fortune]: https://fortune.com/2025/12/03/why-spotify-wrapped-marketing-genius-individuality-uniqueness-belonging-psychology/
[psychologs]: https://www.psychologs.com/the-psychology-behind-your-spotify-wrapped/
[adma]: https://adma.com.au/resources/personal-shareable-no-strings-attached-the-winning-formula-behind-spotify-wrapped
[strava-manual]: https://www.itsnicethat.com/articles/manual-strava-year-in-sport-graphic-design-150321
[strava-stink]: https://www.stinkstudios.com/work/strava-year-in-sport-2018
[strava-hm]: https://hellomonday.com/work/strava-year-in-sport-2023
[unwrapped]: https://gittrend.io/repo/remotion-dev/github-unwrapped
[wrapped25]: https://dev.to/programmerraja/spotify-wrapped-but-for-developers-introducing-github-wrapped-2025-21lm
[devwrapped]: https://github.com/himashaherath/github-dev-wrapped
[gitwrapped]: https://webdesignerdepot.com/?p=62734
[gaming]: https://hackernoon.com/developers-are-gaming-their-github-profiles
[tnw]: https://thenextweb.com/news/github-streaks-dead-thank-the-sun-god
[runsteady]: https://runsteady.com/blog/the-github-contributions-chart/
[kapwing]: https://www.kapwing.com/resources/linkedin-video-size-guide-aspect-ratios-resolution-length-and-best-practices-3/
[quso]: https://quso.ai/blog/linkedin-video-size
[captions]: https://www.captions.ai/blog-post/linkedin-video-specs
[opus]: https://www.opus.pro/blog/ideal-linkedin-video-length-format-for-retention
[sotrender]: https://www.sotrender.com/blog/2024/05/linkedin-video-content/
[clipchamp]: https://clipchamp.com/en/blog/the-ultimate-guide-to-linkedin-videos/
[smt]: https://www.socialmediatoday.com/news/linkedin-video-posting-tips-specs-2025/746552/
[compresto]: https://compresto.app/blog/compress-video-for-linkedin

## v2: topical and shareable (2026-11)

- **Agents are the 2026 story.** Coding agents sign their work in public metadata: Claude Code
  adds a `Co-Authored-By: Claude ...` trailer and a "Generated with Claude Code" footer, Copilot's
  coding agent opens PRs as `copilot-swe-agent` on `copilot/` branches, Codex and Claude web use
  `codex/` and `claude/` branches, Aider prefixes `aider:`, Cursor signs as `cursoragent@cursor.com`.
  Counting these is cheap and honest (a lower bound), and "shipped with a team of agents" is a
  line people want to post. Shame framing ("only 43% was you") is avoided by design.
- **Flattering, credible extras**: releases tagged (users got something), the biggest change as a
  diff stat, open source merged into other people's projects. Each is an outcome, not activity.
- **Look**: developers recognise the terminal and the diff, not a brand. Typed commands, hash
  labels and `+`/`-` hunks borrow that recognition without copying GitHub's UI.
