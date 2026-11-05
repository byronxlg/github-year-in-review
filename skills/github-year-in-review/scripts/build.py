#!/usr/bin/env python3
"""Turn year.json into story.json and a HyperFrames composition.

    python3 build.py year.json --out <output-dir> [--story story.json] [--music track.mp3]
                     [--cues beats.json] [--cta "Make yours: ..."] [--beats id,id] [--skip id,id]
    python3 build.py --catalogue year.json --out x   # print the beat catalogue

With --music and no --cues, the beat grid comes from `npx hyperframes beats --json <track>`;
if that is unavailable the film is built without beat sync.

Writes <output-dir>/story.json (the beats, copy and timings; edit it and pass it back with
--story to override copy) and <output-dir>/composition/ (index.html, fonts, music).
Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"
CTA = "Make yours: github.com/byronxlg/github-year-in-review"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
# Rough length per beat, used only to decide which beats fit; real timing comes from beat_timing().
EST_DURATION = {"hook": 5.6, "shape": 7.6, "yoy": 6.9, "run": 6.4, "clock": 7.2, "punchcard": 7.2, "work": 7.6,
                "languages": 7.0, "agents": 7.8, "models": 7.4, "ship": 6.9, "diff": 6.9, "lines": 7.0, "actions": 7.0,
                "releases": 7.2, "started": 7.4, "oss": 7.0, "surprise": 6.4, "day": 6.9, "identity": 6.0, "close": 6.8}
# Pacing (seconds). One thing moves at a time; every beat holds still for HOLD before it leaves.
LEAD, GAP, EXIT = 0.3, 0.35, 0.4
TYPE_CPS = 30  # typing speed, characters per second
HERO = {"hook": 1.4, "shape": 1.6, "clock": 1.3, "work": 1.3, "identity": 0.7, "close": 0.8}
SUPPORT_RISE, STAGGER = 0.55, 0.15
HOLD = {"default": 3.0, "close": 3.6, "chapter": 1.2}
# calm: v3-v8. tight (v9, test): more beats, less time between them. No chapter cards, a cut instead
# of a fade out, motion at `speed`, the reading-floor hold. `est` scales EST_DURATION for selection.
PACES = {
    "calm": {"chapters": True, "speed": 1.0, "hold": 1.0, "fade_in": 0.3, "fade_out": 0.35, "lead": LEAD,
             "gap": GAP, "exit": EXIT, "est": 1.0},
    "tight": {"chapters": False, "speed": 0.6, "hold": 2.5 / 3.0, "fade_in": 0.1, "fade_out": 0.0, "lead": 0.08,
              "gap": 0.12, "exit": 0.0, "est": 0.56},
    # suite (test): the picker reel's pace B, with a transition from SUITE on every cut.
    "suite": {"chapters": False, "speed": 0.75, "hold": 2.9 / 3.0, "fade_in": 0.0, "fade_out": 0.0, "lead": 0.12,
              "gap": 0.18, "exit": 0.0, "est": 0.72, "cuts": True},
}
PACE = "calm"
DIRECTION = "b"  # juror pick 2026-11-03; see docs/design.md v3
# Direction B: chapter cards (title, command, beats in the chapter), inserted before the chapter's first beat.
CHAPTERS = [
    ("The rhythm", "git log --since={year}-01-01 --author={user}", ("shape", "yoy", "run", "clock", "punchcard")),
    ("The work", "git shortlog -sn --since={year}-01-01", ("work", "languages", "agents", "models", "ship", "lines", "diff")),
    ("What shipped", "git tag --sort=-creatordate", ("releases", "actions", "started", "oss", "surprise", "day")),
]
MAX_TOTAL = 78.0  # LinkedIn: under a minute and a half; calm pacing over more beats (estimates run long)
# A real command (or pipeline) that would answer each beat's question for a single repo. Kept in
# story.json; only the hook's is drawn (v3: one prompt, static, so it never moves with a stat).
COMMANDS = {
    "hook": "year-in-review --user {user} --year {year}",
    "shape": "git log --since={year}-01-01 --format=%as | uniq -c",
    "run": "git log --format=%as | uniq | longest-run",
    "clock": "git log --date=format:%H --format=%ad | uniq -c",
    "work": "git shortlog -sn",
    "agents": "git log --format='%(trailers:key=Co-authored-by)'",
    "ship": "gh pr list --author @me --state merged",
    "diff": "git diff --shortstat",
    "lines": "git log --shortstat --author={user} --since={year}-01-01",
    "actions": "gh run list --json startedAt,updatedAt",
    "releases": "git tag --sort=-creatordate",
    "started": "gh repo list --source",
    "oss": "gh search prs --author @me --merged",
    "surprise": "crontab -l",
    "yoy": "git log --date=format:%Y --format=%ad | uniq -c",
    "punchcard": "git log --date=format:'%a %H' --format=%ad | sort | uniq -c",
    "languages": "gh repo list --source --json primaryLanguage",
    "models": "git log --format='%(trailers:key=Co-authored-by,valueonly)' | sort -u",
    "day": "git log --format=%as | uniq -c | sort -rn | head -1",
    "identity": "whoami",
    "close": "git commit -m \"{year}, in review\"",
}


def n(x: int | float) -> str:
    return f"{int(round(x)):,}"


def pct(x: float) -> str:
    return f"{round(x * 100)}%"


def short_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}"


def hour_label(h: int) -> str:
    if h == 0:
        return "midnight"
    if h == 12:
        return "noon"
    return f"{h % 12} {'am' if h < 12 else 'pm'}"


def clause(text: str | None, max_words: int = 10) -> str:
    """First clause of a repo description, short enough to read in a beat."""
    if not text:
        return ""
    import re
    first = re.split(r"(?<=[A-Za-z0-9)])[.:;](?:\s|$)| - | -- ", text.strip())[0].strip()
    words = first.split()
    return " ".join(words[:max_words]) + ("..." if len(words) > max_words else "")


def plural(k: int, word: str) -> str:
    return f"{n(k)} {word}{'' if k == 1 else 's'}"


# --------------------------------------------------------------------------- story


def weekend_share(d: dict) -> float:
    """Weekend share of the person's own commits (automation excluded); calendar share as fallback."""
    r = d["rhythm"]
    wk = r.get("by_weekday_sampled") or []
    return (wk[5] + wk[6]) / sum(wk) if sum(wk) >= 40 else r["weekend_share"]


def public_view(d: dict) -> bool:
    """Collected with no token: every list is public work only, the calendar and its private count
    are the whole year. A claim about "you" has to hold with the private part unseen."""
    return (d.get("source") or {}).get("mode") == "public"


def private_share(d: dict) -> float:
    t = d["totals"]
    return (t.get("private_contributions") or 0) / t["contributions"] if t.get("contributions") else 0.0


def archetype(d: dict) -> dict:
    r, pr, t = d["rhythm"], d["pull_requests"], d["totals"]
    weekend = weekend_share(d)
    public = public_view(d)
    # With private work unseen, automation is measured against everything the calendar counts,
    # a thin commit sample says nothing about the clock, and one outside owner may be the same
    # person's second account, so it does not make them a contributor.
    auto_share = d["automation"]["commits"] / ((t["contributions"] if public else t["commits"]) or 1)
    clock_known = not public or r["commits_sampled"] >= 40
    outside_owners = {name.split("/")[0] for name, _ in pr.get("external_public", [])}
    public_external = pr.get("external_public", [])
    new = len(d["new_repos"]) + d.get("new_private_repos", 0)

    if clock_known and r["night_share"] > 0.30:
        adj, why_a = "Night Shift", f"{pct(r['night_share'])} of commits after 10 pm"
    elif clock_known and r["morning_share"] > 0.25:
        adj, why_a = "Early", f"{pct(r['morning_share'])} of commits before 9 am"
    elif weekend > 0.35:
        adj, why_a = "Weekend", f"{pct(weekend)} of {'contributions' if public else 'commits'} on weekends"
    elif r["streak"]["longest"] >= 30:
        adj, why_a = "Relentless", f"a {r['streak']['longest']}-day streak"
    else:
        adj, why_a = "Steady", f"{n(r['active_days'])} active days"

    ag = d.get("agents") or {}
    if public and private_share(d) >= 0.5:
        noun, why_n = "Builder", f"{pct(private_share(d))} of contributions in private repos"
    elif auto_share > 0.25 and new < 6:
        noun, why_n = "Automator", f"{pct(auto_share)} of commits by your own automation"
    elif ag.get("agent_share", 0) >= 0.4 and ag.get("agent_commits_est", 0) >= 100:
        noun, why_n = "Orchestrator", f"{pct(ag['agent_share'])} of commits shipped with agents"
    elif sum(c for _, c in public_external) >= 10 and (not public or len(outside_owners) >= 2):
        noun, why_n = "Contributor", f"{n(sum(c for _, c in public_external))} PRs merged into open source"
    elif t["reviews"] > t["prs"] and t["reviews"] >= 10:
        noun, why_n = "Reviewer", f"{n(t['reviews'])} reviews"
    elif new >= 6:
        noun, why_n = "Builder", f"{n(new)} new repos"
    elif pr["merged"] >= 100:
        noun, why_n = "Shipper", f"{n(pr['merged'])} merged PRs"
    else:
        noun, why_n = "Maker", f"{n(t['commits'])} {'public ' if public else ''}commits"
    return {"name": f"The {adj} {noun}", "reason": f"{why_n[0].upper()}{why_n[1:]}, {why_a}."}


def burst_line(rel: dict) -> str:
    """The biggest three-day burst of releases, when it is most of the story."""
    dates = sorted(dt.date.fromisoformat(x) for r in rel.get("repos", []) for x in r.get("dates") or [])
    best, at = 0, None
    for i, d0 in enumerate(dates):
        k = sum(1 for d in dates[i:] if (d - d0).days < 3)
        if k > best:
            best, at = k, d0
    if at is None or best < 5 or best < 0.4 * len(dates):
        return ""
    span = (max(d for d in dates if 0 <= (d - at).days < 3) - at).days + 1
    when = f"in {span} days in {MONTHS[at.month - 1]}" if span > 1 else f"on {short_date(at.isoformat())}"
    return f"{best} of them {when}."


# Famous codebases to size the year's added lines against. Every figure counts all lines (blank
# and comment lines too), like a PR's additions do. Measured with `wc -l` on a shallow clone
# unless noted; sources and commits in docs/design.md (v7). Ordered small to large.
CODEBASES = [
    # (phrase, short label, lines, source)
    ("git's first commit", "git's first commit", 1_244, "git/git e83c516, all 11 files"),
    ("the Wolfenstein 3D source", "Wolfenstein 3D", 42_178, "id-Software/wolf3d 0516778, .c .h .asm"),
    ("the original Doom source", "Doom", 59_110, "id-Software/DOOM a77dfb9, .c .h"),
    ("the Apollo 11 guidance code", "Apollo 11 guidance", 130_186,
     "chrislgarry/Apollo-11 e7576d5, Comanche055 + Luminary099 .agc"),
    ("SQLite's source", "SQLite", 222_348, "sqlite/sqlite 38b4005, src/*.c *.h"),
    ("the Quake source", "Quake", 237_508, "id-Software/Quake bf4ac42, WinQuake + QuakeWorld .c .h .s"),
    ("the Quake III Arena source", "Quake III Arena", 332_692,
     "id-Software/Quake-III-Arena dbe4ddb, code/ .c .h .s .asm .cpp"),
    ("the Linux kernel", "Linux kernel", 40_000_000,
     "about 40M lines with blanks and comments, Phoronix, April 2026"),
]


def codebase_match(lines: int) -> dict | None:
    """The famous codebase to compare `lines` with: the largest one no bigger than 1.25x the
    total, so the phrase is "about the size of" or a multiple of at least one. None when the
    total is smaller than all of them."""
    fits = [c for c in CODEBASES if c[2] <= lines * 1.25]
    if not fits or lines <= 0:
        return None
    phrase, short, size, source = max(fits, key=lambda c: c[2])
    return {"name": phrase, "short": short, "lines": size, "source": source, "ratio": round(lines / size, 2)}


def times_phrase(ratio: float) -> str:
    """'about the size of', 'about one and a half times', 'about twice', 'about 3 times'."""
    if ratio < 1.25:
        return "about the size of"
    if ratio < 1.75:
        return "about one and a half times"
    if ratio < 2.5:
        return "about twice"
    return f"about {n(ratio)} times"


def compact(x: int | float) -> str:
    """640123 -> '640k', 1234567 -> '1.2M', 942 -> '942'."""
    if x >= 999_500:
        return f"{x / 1e6:.1f}M".replace(".0M", "M")
    if x >= 1000:
        return f"{round(x / 1000)}k"
    return n(x)


def duration_words(minutes: float) -> str:
    """Minutes as a human span: 'about 23 days', 'about 14 hours', '45 minutes'."""
    if minutes >= 2 * 1440:
        return f"about {n(minutes / 1440)} days"
    if minutes >= 120:
        return f"about {n(minutes / 60)} hours"
    return plural(round(minutes), "minute")


# --------------------------------------------------------------------------- the catalogue
#
# Every beat the film can carry, in film order. Mandatory beats are always in the film when
# their data exists and are never cut for time. Optional beats must pass their eligibility rule
# (thin data drops them), then compete on score: alternatives share a slot and only the higher
# score plays, and the best are taken until MAX_TOTAL is full. The film keeps catalogue order,
# whatever the scores. Scores are 0 to 1: a weight for how much the beat says in general, times
# the strength of this person's number against a baseline, on a log ramp (ramp() below), so a
# 56x year on year scores near the top and a 1.3x one near zero. Mirrored in references/story.md.
CATALOGUE = [
    # id, slot, mandatory, needs, eligible when, score
    ("hook", "hook", True, "totals, user", "always", "-"),
    ("shape", "shape", True, "calendar, rhythm.by_month", "always (caption adapts to thin years)", "-"),
    ("yoy", "yoy", False, "history (contributions of the two years before)",
     "a prior year with 10+ contributions", "0.9 x ramp(growth, 1.25x, 20x); flat or down 0.1"),
    ("run", "run", False, "rhythm.streak", "streak of 3+ days", "0.9 x ramp(streak, 3, 60 days)"),
    ("clock", "when", False, "rhythm.by_hour", "40+ sampled commits",
     "0.7 x off-hours: ramp(night share, 10%, 45%) or ramp(morning share, 10%, 40%), floor 0.2"),
    ("punchcard", "when", False, "rhythm.by_weekday_hour", "150+ sampled commits",
     "clock score x week lift / 2: wins when one weekday holds over 2/7 of the peak hour"),
    ("work", "work", True, "repos", "1+ public repo that is not automation", "-"),
    ("languages", "languages", False, "repo_languages", "5+ repos with a language, 2+ languages",
     "0.5 x ramp(repos, 5, 40)"),
    ("agents", "agents", False, "agents", "10+ signed commits sampled and share 5%+",
     "1.0 x ramp(share, 5%, 60%)"),
    ("models", "models", False, "agents.model_first_seen", "3+ versioned models in trailers",
     "0.75 x ramp(models, 3, 10)"),
    ("ship", "ship", False, "pull_requests", "5+ PRs opened", "0.9 x ramp(merged, 5, 500)"),
    ("lines", "code", False, "pull_requests.lines_added/removed", "1,000+ lines added over 5+ merged PRs",
     "0.85 x ramp(added, 1k, 300k)"),
    ("diff", "code", False, "pull_requests.biggest", "a nameable merged PR of 300+ lines",
     "0.6 x ramp(lines, 300, 20k)"),
    ("actions", "actions", False, "actions", "60+ minutes over 20+ runs", "0.7 x ramp(minutes, 60, 50k)"),
    ("releases", "releases", False, "releases", "3+ releases", "0.8 x ramp(releases, 3, 60)"),
    ("started", "started", False, "new_repos, stars", "1+ new repo", "0.75 x ramp(new repos, 1, 30)"),
    ("oss", "oss", False, "pull_requests.external_public", "3+ PRs merged into others' public repos",
     "1.0 x ramp(PRs, 3, 50)"),
    ("surprise", "surprise", False, "automation", "50+ automation commits; not with agents (it folds in there)",
     "0.8 x ramp(automation share of commits, 5%, 50%)"),
    ("day", "surprise", False, "rhythm.busiest_day, calendar", "busiest day 10+ and 3x+ the mean active day",
     "0.7 x ramp(busiest / mean active day, 3x, 30x)"),
    ("identity", "identity", True, "derived (archetype)", "always", "-"),
    ("close", "close", True, "user", "always", "-"),
]
BEATS = {c[0]: {"id": c[0], "slot": c[1], "mandatory": c[2], "needs": c[3], "rule": c[4], "score": c[5],
                "order": k} for k, c in enumerate(CATALOGUE)}
YIELDS_TO = {"surprise": "agents"}  # surprise is left out when agents plays: the cron is named there


def ramp(x: float, lo: float, hi: float) -> float:
    """0 at lo, 1 at hi, on a log scale, clamped: the strength of a number against its baseline."""
    if x <= lo or hi <= lo:
        return 0.0
    return min(1.0, math.log(x / lo) / math.log(hi / lo))


def ctx_of(d: dict) -> dict:
    p = d["period"]
    auto_names = {a["name"] for a in d["automation"]["repos"]}
    return {"year_label": f"{p['year']} so far" if p["partial"] else str(p["year"]),
            "human_repos": [x for x in d["repos"] if x["name"] not in auto_names and not x["private"]]}


def b_hook(d, c):
    u, t, r = d["user"], d["totals"], d["rhythm"]
    if public_view(d) and t.get("private_contributions"):
        return {"id": "hook", "label": f"GitHub, {c['year_label']}",
                "name": u["name"], "number": t["contributions"], "unit": "contributions",
                "line": f"on GitHub, {n(t['private_contributions'])} of them in private repos, "
                        f"over {plural(r['active_days'], 'active day')}."}
    return {"id": "hook", "label": f"GitHub, {c['year_label']}",
            "name": u["name"], "number": t["contributions"], "unit": "contributions",
            "line": f"on GitHub, across {plural(d['repo_count'], 'repo')} and {plural(r['active_days'], 'active day')}."
            if d["repo_count"] else "on GitHub."}


def b_shape(d, c):
    r = d["rhythm"]
    months = r["by_month"]
    total = sum(months) or 1
    peak_m = max(range(12), key=lambda i: months[i])
    first_active = next((i for i, v in enumerate(months) if v > 0), 0)
    if months[peak_m] / total >= 0.3:
        caption = f"{MONTHS[peak_m]} alone: {n(months[peak_m])}. That is {pct(months[peak_m] / total)} of the year."
    elif r["active_days"] < 30:
        caption = f"{plural(r['active_days'], 'day')} with something to show. Every square counted."
    else:
        caption = f"Busiest month: {MONTHS[peak_m]}, with {n(months[peak_m])}."
    return {"id": "shape", "label": "The shape of the year", "title": "Every day of the year, one square.",
            "peak_month": peak_m, "peak_value": months[peak_m], "caption": caption,
            "busiest": r["busiest_day"], "first_active_month": first_active}


def yoy_base(d: dict) -> tuple[int, int] | None:
    """(year, contributions) of the latest prior year with 10+ contributions, else None."""
    past = [h for h in d.get("history") or [] if h.get("contributions", 0) >= 10]
    return (past[-1]["year"], past[-1]["contributions"]) if past else None


def b_yoy(d, c):
    base = yoy_base(d)
    if not base:
        return "no prior year with 10+ contributions"
    cur = d["totals"]["contributions"]
    years = [h for h in d["history"] if h["year"] >= base[0] - 1 and h.get("contributions", 0) > 0] \
        + [{"year": d["period"]["year"], "contributions": cur, "now": True}]
    ratio = cur / base[1]
    seq = ", then ".join(n(h["contributions"]) for h in years) + (" so far." if d["period"]["partial"] else ".")
    if ratio >= 1.25:
        hero = f"{ratio:.0f}x" if ratio >= 10 else f"{ratio:.1f}x".replace(".0x", "x")
        unit = f"the contributions of {base[0]}"
    else:  # flat or down: say the years, never the drop
        hero = n(sum(h["contributions"] for h in years))
        unit = f"contributions over {len(years)} years"
    return {"id": "yoy", "label": "Year on year", "hero": hero, "unit": unit, "ratio": round(ratio, 2),
            "years": [[h["year"], h["contributions"]] for h in years], "sub": seq[0].upper() + seq[1:]}


def b_run(d, c):
    r, p = d["rhythm"], d["period"]
    s = r["streak"]
    if s["longest"] < 3:
        return f"longest streak {s['longest']} days, under 3"
    still = s["end"] == p["to"] and s["current"] == s["longest"]
    return {"id": "run", "label": "The longest run",
            "number": s["longest"], "unit": "days in a row", "run_from": s["start"], "end": s["end"],
            "sub": f"{short_date(s['start'])} to {short_date(s['end'])}" + (", and still going" if still else ""),
            "facts": [[n(r["active_days"]), f"days with {'contributions' if public_view(d) else 'commits'}"],
                      [pct(weekend_share(d)), f"of {'contributions' if public_view(d) else 'commits'} on weekends"]]}


def b_clock(d, c):
    r = d["rhythm"]
    if r["commits_sampled"] < 40 or r["peak_hour"] is None:
        return f"{r['commits_sampled']} sampled commits, under 40"
    late = r.get("latest_night_commit")
    return {"id": "clock", "label": "When the work happens",
            "hours": r["by_hour"], "peak": r["peak_hour"], "peak_label": hour_label(r["peak_hour"]),
            "sub": f"Latest commit: {late['time']} on {short_date(late['date'])}." if late
            else f"{pct(r['night_share'])} of commits after 10 pm."}


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def week_peak(grid: list[list[int]]) -> tuple[int, int, float]:
    """(weekday, hour, week lift) of the busiest hour of the week. Week lift is how much more of
    that hour's commits fall on its weekday than an even 1/7 would put there (1 = even, 7 = all)."""
    wd, h = max(((w, x) for w in range(7) for x in range(24)), key=lambda k: (grid[k[0]][k[1]], -k[0], -k[1]))
    col = sum(grid[w][h] for w in range(7)) or 1
    return wd, h, 7 * grid[wd][h] / col


def b_punchcard(d, c):
    r = d["rhythm"]
    grid = r.get("by_weekday_hour")
    if not grid or r["commits_sampled"] < 150:
        return "no weekday-by-hour sample" if not grid else f"{r['commits_sampled']} sampled commits, under 150"
    wd, h, lift = week_peak(grid)
    days = [sum(row) for row in grid]
    top = max(range(7), key=lambda k: days[k])
    return {"id": "punchcard", "label": "When, exactly", "grid": grid, "peak": [wd, h], "lift": round(lift, 2),
            "hero": f"{WEEKDAYS[wd]} {hour_label(h)}", "unit": "is the busiest hour of your week",
            "sub": f"{DAY_NAMES[top]}s carry {pct(days[top] / (sum(days) or 1))} of your commits."}


def b_work(d, c):
    top = c["human_repos"][:4]
    if not top:
        return "no public repo that is not automation"
    return {"id": "work", "label": "Where the public hours went" if public_view(d) else "Where the hours went",
            "rows": [{"name": x["short"], "commits": x["commits"], "language": x["language"],
                      "color": x["color"] or "#A39B8E"} for x in top],
            "lead": clause(top[0]["description"], 12), "lead_name": top[0]["short"]}


def b_languages(d, c):
    rl = d.get("repo_languages") or {}
    langs = rl.get("by_language") or []
    if rl.get("with_language", 0) < 5 or len(langs) < 2:
        return f"{rl.get('with_language', 0)} repos with a language, {len(langs)} languages"
    top, k = langs[0]
    rows = [[nm, v] for nm, v in langs[:4]]
    rest = rl["repos"] - sum(v for _, v in rows)
    if rest > 0:
        rows.append(["other", rest])
    return {"id": "languages", "label": "What you wrote in", "hero": top,
            "unit": f"primary language of {k} of {plural(rl['repos'], 'repo')}", "rows": rows,
            "repos": rl["repos"]}


def b_agents(d, c):
    ag = d.get("agents") or {}
    auto = d["automation"]
    if not (ag.get("agent_commits_sampled", 0) >= 10 and ag.get("agent_share", 0) >= 0.05):
        return f"{ag.get('agent_commits_sampled', 0)} signed commits sampled, share {pct(ag.get('agent_share', 0))}"
    names = [a for a, _ in ag["by_agent"]]
    team = (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1])
    # One row per agent; with a single agent, one row per model it signed as.
    sampled = sum(k for _, k in ag["by_agent_sampled"]) or 1
    if len(ag["by_agent_sampled"]) > 1 or not ag.get("models"):
        src = ag["by_agent_sampled"]
    else:
        merged_models: dict = {}
        for m, k in ag["models"]:
            key = re.sub(r"\s*\(.*?\)", "", m).strip()
            merged_models[key] = merged_models.get(key, 0) + k
        src = sorted(merged_models.items(), key=lambda kv: -kv[1])
        sampled = sum(merged_models.values()) or 1
    rows = [{"trailer": name, "share": round(k / sampled, 3)} for name, k in src[:3]]
    months = [m for m in ag.get("by_month", []) if m.get("sampled", 0) >= 20]
    trend = ""
    if len(months) >= 4:
        early = months[0]["agent"] / months[0]["sampled"]
        late_m = max(months[-3:], key=lambda m: m["agent"] / m["sampled"])
        late_s = late_m["agent"] / late_m["sampled"]
        if late_s - early >= 0.25:
            trend = f"{pct(early)} in {MONTHS[months[0]['month'] - 1]}, {pct(late_s)} by {MONTHS[late_m['month'] - 1]}."
    prs_line = ""
    if ag.get("prs_total"):
        top = ag["prs"][0]
        prs_line = f"{plural(ag['prs_total'], 'pull request')} opened with {top[0] if len(ag['prs']) == 1 else 'agents'}."
    auto_line = f"Your cron's {n(auto['commits'])} commits are counted separately." if auto["commits"] >= 50 else ""
    return {"id": "agents", "label": "Shipped with a team",
            "number": round(ag["agent_share"] * 100), "unit": f"of your commits co-written with {team}",
            "rows": rows, "trend": trend, "prs": prs_line, "auto": auto_line,
            "sub": (prs_line + " " + trend).strip() or "You wrote the brief, reviewed and merged."}


def b_models(d, c):
    seen = [x for x in (d.get("agents") or {}).get("model_first_seen") or [] if x[1][:4] == str(d["period"]["year"])]
    if len(seen) < 3:
        return f"{len(seen)} versioned models in trailers, under 3"
    seen = sorted(seen, key=lambda x: x[1])
    family = seen[0][0].split()[0]
    same = all(x[0].split()[0] == family and len(x[0].split()) > 1 for x in seen)
    rows = [{"name": " ".join(x[0].split()[1:]) if same else x[0], "date": x[1]} for x in seen]
    return {"id": "models", "label": "Every model, in order", "number": len(rows),
            "unit": f"{family} models in your commits" if same else "coding models in your commits",
            "rows": rows, "sub": f"First trailer of each, {short_date(rows[0]['date'])} to {short_date(rows[-1]['date'])}."}


def b_ship(d, c):
    pr, t = d["pull_requests"], d["totals"]
    if pr["opened"] < 5:
        return f"{pr['opened']} PRs opened, under 5"
    ext = pr.get("most_starred_external")
    ext_line = ""
    if ext and ext["repo"] != "a private repo":
        ext_line = f"Including one into {ext['repo']}, {n(ext['stars'])} stars."
    elif pr["external_merged"]:
        ext_line = f"{n(pr['external_merged'])} of them into other people's repos."
    return {"id": "ship", "label": "What landed",
            "number": pr["merged"], "unit": "pull requests merged", "opened": pr["opened"],
            "sub": f"{pct(pr['merge_rate'])} of the {n(pr['opened'])} {'public ones ' if public_view(d) else ''}opened. "
                   f"{n(t['reviews'])} reviews given.",
            "ext": ext_line}


def b_diff(d, c):
    pr = d["pull_requests"]
    big = pr.get("biggest")
    if not (big and big.get("title") and big["additions"] + big["deletions"] >= 300):
        return "no nameable merged PR of 300+ lines"
    return {"id": "diff", "label": "The biggest change",
            "repo": big["repo"].split("/")[-1], "pr": big.get("number"), "title": clause(big["title"], 9),
            "additions": big["additions"], "deletions": big["deletions"], "files": big["files"],
            "total_added": pr.get("lines_added", 0), "total_removed": pr.get("lines_removed", 0),
            "at_least": pr.get("sampled", 0) < pr.get("merged", 0)}


def b_lines(d, c):
    pr = d["pull_requests"]
    added, removed = pr.get("lines_added", 0), pr.get("lines_removed", 0)
    if not (added >= 1000 and pr.get("merged", 0) >= 5):
        return f"{n(added)} lines added over {pr.get('merged', 0)} merged PRs"
    ref = codebase_match(added)
    partial = pr.get("sampled", 0) < pr.get("opened", 0)
    return {"id": "lines", "label": "Lines changed",
            "added": added, "removed": removed, "net": added - removed,
            "unit": f"lines in {'public ' if public_view(d) else ''}merged pull requests" + (", at least" if partial else ""),
            "ref": ref,
            "sub": f"Added: {times_phrase(ref['ratio'])} {ref['name']}." if ref
            else f"Net: {'+' if added >= removed else '-'}{n(abs(added - removed))} lines."}


def b_actions(d, c):
    act = d.get("actions") or {}
    if not (act.get("minutes", 0) >= 60 and act.get("runs", 0) >= 20):
        return f"{n(act.get('minutes', 0))} Actions minutes over {act.get('runs', 0)} runs" if act else "no Actions data"
    span = duration_words(act["minutes"])
    bm = act.get("by_month") or [0] * 12
    peak = max(range(12), key=lambda m: bm[m])
    share = bm[peak] / (sum(bm) or 1)
    tail = (f", {pct(share)} of it in {MONTHS[peak]}." if share >= 0.5 else f", over {plural(act['runs'], 'run')}.")
    return {"id": "actions", "label": "Machine time",
            "number": act["minutes"], "unit": f"minutes of Actions runs on your {'public ' if public_view(d) else ''}repos",
            "by_month": bm, "runs": act["runs"],
            "sub": (f"{span[0].upper()}{span[1:]} of machine time{tail}"
                    + (" Partly estimated." if act.get("estimated") else ""))}


def b_releases(d, c):
    rel = d.get("releases") or {}
    if rel.get("total", 0) < 3:
        return f"{rel.get('total', 0)} releases, under 3"
    named = [x for x in rel["repos"] if x["repo"]]
    lead = named[0] if named else None
    return {"id": "releases", "label": "Shipped to users",
            "number": rel["total"], "unit": "releases tagged" if rel["total"] != 1 else "release tagged",
            "rows": [{"tag": x["latest"], "repo": x["repo"], "count": x["count"], "dates": x.get("dates") or []}
                     for x in named[:3]],
            "sub": (burst_line(rel) or (f"{lead['repo']} went from {lead['first']} to {lead['latest']}."
                                        if lead and lead["first"] != lead["latest"]
                                        else f"Across {plural(len(rel['repos']), 'project')}."))}


def b_started(d, c):
    new = d["new_repos"]
    total_new = len(new) + d.get("new_private_repos", 0)
    if not total_new:
        return "no new repos"
    starred = sorted([x for x in new if x["stars"] > 0], key=lambda x: -x["stars"])
    picks = (starred + [x for x in new if x["stars"] == 0 and x["description"]])[:3]
    return {"id": "started", "label": "Started this year",
            "number": total_new, "unit": "new repos" if total_new != 1 else "new repo",
            "rows": [{"name": x["name"], "meta": (f"{plural(x['stars'], 'star')}" if x["stars"] else (x["language"] or "")),
                      "desc": clause(x["description"], 8)} for x in picks],
            "sub": (f"{plural(d['stars']['gained'], 'star')} earned this year." if d["stars"]["gained"] else
                    f"{len(new)} public, {d.get('new_private_repos', 0)} private.")}


def b_oss(d, c):
    pr = d["pull_requests"]
    ext = pr.get("external_public") or []
    if sum(k for _, k in ext) < 3:
        return f"{sum(k for _, k in ext)} PRs merged into others' public repos, under 3"
    stars = pr.get("external_public_stars") or {}
    return {"id": "oss", "label": "Open source",
            "number": sum(k for _, k in ext), "unit": "PRs merged into repos outside your account" if public_view(d)
            else "PRs merged into other people's projects",
            "rows": [{"name": r, "count": k, "stars": stars.get(r, 0)} for r, k in ext[:3]]}


def b_surprise(d, c):
    auto, t = d["automation"], d["totals"]
    if auto["commits"] < 50:
        return f"{auto['commits']} automation commits, under 50"
    human_commits = t["commits"] - auto["commits"]
    a = max(auto["repos"], key=lambda x: x["commits"])
    return {"id": "surprise", "label": "One more thing",
            "number": auto["commits"], "unit": "commits were not you",
            "sub": (f"A scheduled job in {a['name'].split('/')[-1]}."
                    + (f" It made more {'public ' if public_view(d) else ''}commits than you did ({n(human_commits)})."
                       if auto["commits"] > human_commits else ""))}


def day_lift(d: dict) -> float:
    r = d["rhythm"]
    b = r.get("busiest_day") or {}
    mean = d["totals"]["contributions"] / (r["active_days"] or 1)
    return b.get("count", 0) / (mean or 1)


def b_day(d, c):
    b = d["rhythm"].get("busiest_day")
    if not b or b["count"] < 10 or day_lift(d) < 3:
        return "busiest day under 10, or under 3x the mean active day" if b else "no busiest day"
    cal = dict(d["calendar"])
    dates = sorted(cal)
    k = dates.index(b["date"]) if b["date"] in cal else 0
    lo = max(0, min(k - 3, len(dates) - 7))
    week = [[x, cal[x]] for x in dates[lo:lo + 7]]
    day = dt.date.fromisoformat(b["date"])
    prs = b.get("prs_merged", 0)
    return {"id": "day", "label": "The biggest day", "number": b["count"],
            "unit": f"contributions on {short_date(b['date'])}", "date": b["date"], "week": week,
            "prs_merged": prs,
            "sub": f"A {day.strftime('%A')}: " + (f"{plural(prs, 'pull request')} merged." if prs >= 2
                                                   else f"{round(day_lift(d))}x your average active day.")}


def b_identity(d, c):
    a = archetype(d)
    return {"id": "identity", "label": f"{c['year_label']}, in one line", "name": a["name"], "reason": a["reason"]}


def b_close(d, c):
    return {"id": "close", "label": "Year in review", "handle": f"@{d['user']['login']}", "year": c["year_label"]}


BUILDERS = {k: v for k, v in globals().items() if k.startswith("b_")}


def score_beat(sid: str, d: dict, b: dict) -> float:
    """How interesting this beat is for this person, 0 to 1 (rules in CATALOGUE)."""
    r, pr = d["rhythm"], d["pull_requests"]
    if sid == "yoy":
        return 0.9 * ramp(b["ratio"], 1.25, 20) if b["ratio"] >= 1.25 else 0.1
    if sid == "run":
        return 0.9 * ramp(b["number"], 3, 60)
    if sid in ("clock", "punchcard"):
        off = max(ramp(r["night_share"], 0.10, 0.45), ramp(r["morning_share"], 0.10, 0.40), 0.2)
        base = 0.7 * off
        return base if sid == "clock" else min(1.0, base * b["lift"] / 2)
    if sid == "languages":
        return 0.5 * ramp(b["repos"], 5, 40)
    if sid == "agents":
        return 1.0 * ramp(b["number"] / 100, 0.05, 0.60)
    if sid == "models":
        return 0.75 * ramp(b["number"], 3, 10)
    if sid == "ship":
        return 0.9 * ramp(b["number"], 5, 500)
    if sid == "lines":
        return 0.85 * ramp(b["added"], 1000, 300_000)
    if sid == "diff":
        return 0.6 * ramp(b["additions"] + b["deletions"], 300, 20_000)
    if sid == "actions":
        return 0.7 * ramp(b["number"], 60, 50_000)
    if sid == "releases":
        return 0.8 * ramp(b["number"], 3, 60)
    if sid == "started":
        return 0.75 * ramp(b["number"], 1, 30)
    if sid == "oss":
        return 1.0 * ramp(b["number"], 3, 50)
    if sid == "surprise":
        return 0.8 * ramp(d["automation"]["commits"] / (d["totals"]["commits"] or 1), 0.05, 0.5)
    if sid == "day":
        return 0.7 * ramp(day_lift(d), 3, 30)
    return 1.0


def select_beats(cands: dict, scores: dict, reasons: dict, force=(), skip=(),
                 max_total: float = MAX_TOTAL, est: float = 1.0) -> tuple[list[str], dict]:
    """Pick the film's beats from the eligible candidates. Mandatory and forced beats first; then
    optional beats by score, one per slot, while they fit the time budget. Returns the chosen ids
    in catalogue order and the selection record for story.json."""
    left: dict[str, str] = {}
    for sid in BEATS:
        if sid in skip and not BEATS[sid]["mandatory"]:
            left[sid] = "skipped (--skip)"
        elif sid not in cands:
            left[sid] = ("forced, but " if sid in force else "") + "no data: " + reasons.get(sid, "")
    must = [s for s in BEATS if s in cands and s not in left and (BEATS[s]["mandatory"] or s in force)]
    yielded: set[str] = set()
    while True:
        chosen = list(must)
        slots = {BEATS[s]["slot"]: s for s in chosen}
        used = sum(EST_DURATION[s] * est for s in chosen)
        why: dict[str, str] = {}
        opt = sorted((s for s in cands if s not in left and s not in chosen and s not in yielded),
                     key=lambda s: (-scores[s], BEATS[s]["order"]))
        for s in opt:
            slot = BEATS[s]["slot"]
            if YIELDS_TO.get(s) in chosen:
                why[s] = f"{YIELDS_TO[s]} plays, and the automation is named there"
            elif slot in slots:
                why[s] = f"alternative {slots[slot]} scored higher" if slots[slot] not in force \
                    else f"alternative {slots[slot]} was forced"
            elif scores[s] <= 0:
                why[s] = "score 0: this number is not strong enough to spend a beat on"
            elif used + EST_DURATION[s] * est > max_total:
                why[s] = f"over the time budget ({used:.0f} of {max_total:.0f} s used, needs {EST_DURATION[s] * est:.0f})"
            else:
                chosen.append(s)
                slots[slot] = s
                used += EST_DURATION[s] * est
        clash = [s for s, other in YIELDS_TO.items() if s in chosen and other in chosen and s not in must]
        if not clash:
            break
        yielded.update(clash)
    for s in yielded:
        why[s] = f"{YIELDS_TO[s]} plays, and the automation is named there"
    left.update(why)
    chosen.sort(key=lambda s: BEATS[s]["order"])
    rec = {
        "budget": max_total, "used": round(used, 1),
        "chosen": [{"id": s, "slot": BEATS[s]["slot"], "mandatory": BEATS[s]["mandatory"],
                    "forced": s in force and not BEATS[s]["mandatory"],
                    "score": None if BEATS[s]["mandatory"] else round(scores[s], 3)} for s in chosen],
        "left_out": [{"id": s, "slot": BEATS[s]["slot"],
                      "score": round(scores[s], 3) if s in scores else None, "reason": left[s]}
                     for s in sorted(left, key=lambda s: BEATS[s]["order"])],
    }
    return chosen, rec


def make_story(d: dict, cta: str, force=(), skip=(), pace: str = PACE) -> dict:
    """story.json from year.json: build every eligible beat, score the optional ones, select."""
    unknown = [s for s in (*force, *skip) if s not in BEATS]
    if unknown:
        raise ValueError(f"unknown beat ids: {', '.join(unknown)} (catalogue: {', '.join(BEATS)})")
    u, p = d["user"], d["period"]
    c = ctx_of(d)
    cands, reasons, scores = {}, {}, {}
    for sid in BEATS:
        got = BUILDERS["b_" + sid](d, c)
        if isinstance(got, dict):
            cands[sid] = got
            scores[sid] = round(score_beat(sid, d, got), 3)
        else:
            reasons[sid] = got
    if "close" in cands:
        cands["close"]["cta"] = cta
    chosen, rec = select_beats(cands, scores, reasons, set(force), set(skip), est=PACES[pace]["est"])
    beats = [cands[s] for s in chosen]
    number_beats(beats)
    for b in beats:
        b["cmd"] = COMMANDS[b["id"]].format(user=u["login"], year=p["year"])
    return {"user": u["login"], "year": p["year"], "year_label": c["year_label"], "calendar": d["calendar"],
            "period_to": p.get("to"), "pace": pace, "selection": rec, "beats": beats}


# --------------------------------------------------------------------------- transitions

TRANSITIONS_JS = ASSETS / "transitions.js"
CUT_OVERLAP = 0.6  # the incoming scene's entrance starts this far through the transition
# The suite, by number in transitions.js. Each card lists the transitions that say something about
# its stat, best first; a used one falls to the next. No transition shows a card's hero number
# before the card lands, so 61 is listed but not first for lines. Mirrored in references/story.md.
PAIRS = {
    "shape": (49, 50),          # the real calendar, day by day, into the calendar
    "yoy": (62,),               # this year's real months
    "run": (53,),               # the streak snake
    "clock": (46, 63),          # bars, into the hour bars
    "punchcard": (65,),         # the real punchcard
    "work": (68, 66),           # the year's weeks as a log
    "languages": (64,),         # the real language bar
    "agents": (66, 67),         # parallel rails, the team
    "models": (72,),            # a timeline, into a timeline
    "ship": (69,),              # the merge button
    "diff": (59, 47, 58),       # a hunk, into the biggest change
    "lines": (60, 61, 47),      # all red then all green; 61 carries the real numbers
    "actions": (70, 71, 72),    # the checks pass
    "releases": (75,),          # a release tag, v<year>
    "started": (67, 74),        # a branch opens
    "oss": (76,),               # a star
    "surprise": (71, 74),       # a run finishes on its own
    "day": (54, 56),            # heat from one point
    "identity": (73,),          # the handle's own identicon
    "close": (4, 57, 58, 76),   # the last card arrives quietly: a plain crossfade; 57 and 58 are the stats as one diff
}
NEUTRAL = (42, 43, 56, 55, 52, 51)  # for a card whose own have gone; contribution squares, no stat
NEEDS_BEAT = {61: "lines", 64: "languages", 65: "punchcard"}
NEEDS_STATS = {57: 4, 58: 4}  # rows a stat diff needs to fill the frame
SUITE = sorted({n for ns in PAIRS.values() for n in ns} | set(NEUTRAL))


def transition_list() -> list[dict]:
    """Number, name, duration and z order of every transition, read from the JS so they cannot disagree."""
    found = re.findall(r'^  \{ name: "([^"]+)", d: ([\d.]+)(, aTop: true)?', TRANSITIONS_JS.read_text(), re.M)
    return [{"n": i + 1, "name": name, "d": float(d), "aTop": bool(top)} for i, (name, d, top) in enumerate(found)]


def cut_data(story: dict) -> dict:
    """The story's real numbers, for the transitions drawn from them. Only what the film already
    shows: no commit messages, which could name private work."""
    beat = {b["id"]: b for b in story["beats"]}
    cal = story["calendar"]
    months = [0] * 12
    for d, v in cal:
        months[int(d[5:7]) - 1] += v
    weeks = [sum(v for _, v in cal[i:i + 7]) for i in range(0, len(cal), 7)]
    busiest = sorted(sorted(range(len(weeks)), key=lambda k: -weeks[k])[:24])
    stats = [(key, f"{beat[sid][field]:,}") for key, sid, field in (
        ("contributions", "hook", "number"), ("longest_run_days", "run", "number"), ("prs_merged", "ship", "number"),
        ("prs_opened", "ship", "opened"), ("lines_added", "lines", "added"), ("lines_removed", "lines", "removed"),
        ("actions_minutes", "actions", "number"), ("actions_runs", "actions", "runs"), ("repos", "languages", "repos"))
        if isinstance(beat.get(sid, {}).get(field), int)]
    return {"user": story["user"], "year": story["year"], "calendar": cal, "months": months, "weeks": weeks, "stats": stats,
            "added": beat.get("lines", {}).get("added", 0), "removed": beat.get("lines", {}).get("removed", 0),
            "punchcard": beat.get("punchcard", {}).get("grid", []), "languages": beat.get("languages", {}).get("rows", []),
            "log": [[f"week {k + 1:02}", f"{weeks[k]:,} contributions"] for k in busiest],
            "jobs": [b.get("label", b["id"]) for b in story["beats"]][:10]}


def plan_cuts(story: dict) -> list[dict]:
    """One transition per cut, keyed by the card it enters: story["cut_force"] {beat: number}, else
    the card's first free pair, else the next neutral one. Nothing plays twice unless the neutrals
    run out. Recorded in story["cuts"]."""
    beats = story["beats"]
    index = {t["n"]: t for t in transition_list()}
    force = story.get("cut_force") or {}
    skip = set(story.get("cut_skip") or [])
    data = cut_data(story)
    have = {b["id"] for b in beats}

    def missing(n: int) -> str | None:
        if n not in index:
            return f"no transition {n}: the list runs 1 to {len(index)}"
        if n in NEEDS_BEAT and NEEDS_BEAT[n] not in have:
            return f"transition {n} draws on the {NEEDS_BEAT[n]} beat, which is not in this film"
        if len(data["stats"]) < NEEDS_STATS.get(n, 0):
            return f"transition {n} needs {NEEDS_STATS[n]} stats, this film has {len(data['stats'])}"
        return None

    used = set(force.values())
    usable = lambda n: n not in used and n not in skip and missing(n) is None
    cuts = []
    neutral_at = 0
    for a, b in zip(beats, beats[1:]):
        sid = b["id"]
        if sid in force:
            n, why = force[sid], "--cut"
            if missing(n):
                raise ValueError(missing(n))
        else:
            n = next((x for x in PAIRS.get(sid, ()) if usable(x)), None)
            why = f"pair for {sid}"
            if n is None:
                free = [x for x in NEUTRAL if x not in skip] or list(NEUTRAL)
                n = next((x for x in free if x not in used), free[neutral_at % len(free)])
                neutral_at += 1
                why = "neutral"
        used.add(n)
        cuts.append({"from": a["id"], "to": sid, "n": n, "name": index[n]["name"], "d": index[n]["d"],
                     "aTop": index[n]["aTop"], "why": why})
    return cuts


def cut_runner(data: dict, flow: list[dict]) -> str:
    """The JS that schedules the transitions on the page's timeline. flow: {T, k, n}, the scene
    index k leaving at time T through transition n."""
    safe = lambda x: json.dumps(x).replace("</", "<\\/")
    return "const DATA = " + safe(data) + ";\n" + TRANSITIONS_JS.read_text() + """
      const FLOW = """ + safe(flow) + """;
      FLOW.forEach(({T, k, n}) => {
        const t = TRANSITIONS[n - 1];
        const A = document.getElementById("s-" + TIMING[k].key).querySelector(".tw");
        const B = document.getElementById("s-" + TIMING[k + 1].key).querySelector(".tw");
        const c = ctx(tl, T, t.d, A, B);
        const bg = t.opaque === false ? "rgba(20,18,15,0)" : "rgba(20,18,15,1)";
        tl.set([A, B], { backgroundColor: bg }, T);
        t.fn(c);
      });
"""


# --------------------------------------------------------------------------- timing


def number_beats(beats: list[dict]) -> None:
    for i, b in enumerate(beats):
        b["index"] = i + 1
        b["duration"] = EST_DURATION[b["id"]]

def snap_times(beats: list[dict], beat_grid: list[float]) -> None:
    """Start each beat on the nearest music beat at or after its natural start."""
    t = 0.0
    for b in beats:
        start = t
        if beat_grid and start > 0:
            near = min(beat_grid, key=lambda x: abs(x - start))
            if 0 <= near - start < 0.3:  # later only: never cut the previous hold
                start = near
        b["start"] = round(start, 3)
        t = start + b["duration"]
    for i, b in enumerate(beats):
        nxt = beats[i + 1]["start"] if i + 1 < len(beats) else b["start"] + b["duration"]
        b["duration"] = round(nxt - b["start"], 3)


def parse_beats(data: dict) -> list[float]:
    """Beat times from `hyperframes beats --json` (beatTimes) or a cue file with a beats array."""
    grid = data.get("beatTimes") or data.get("beats") or []
    return [float(x["time"] if isinstance(x, dict) else x) for x in grid]


def beat_grid(music: Path | None, cues: Path | None) -> list[float]:
    if cues and cues.exists():
        return parse_beats(json.loads(cues.read_text()))
    if not (music and music.exists()):
        return []
    try:
        r = subprocess.run(["npx", "--no-install", "hyperframes", "beats", "--json", str(music)],
                           capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            return parse_beats(json.loads(r.stdout))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    print("beat detection unavailable; building without beat sync", file=sys.stderr)
    return []


# --------------------------------------------------------------------------- html

E = html.escape


def big_size(text: str, max_px: int, width: int = 900) -> int:
    # Bricolage at wdth 75 / wght 800: digits are about 0.50em, commas about 0.22em.
    em = sum(0.18 if ch in ",." else 0.39 for ch in text) or 1
    return int(min(max_px, width / em))


def year_grid(story: dict, peak_month: int | None, cls: str = "grid") -> str:
    """One row per month, one cell per day, shaded by quartile of the user's active days."""
    cal = {date: c for date, c in story["calendar"]}
    nz = sorted(c for c in cal.values() if c > 0)
    q = [nz[int(len(nz) * f)] for f in (0.25, 0.5, 0.75)] if nz else [1, 2, 3]
    rows = []
    year = story["year"]
    for m in range(12):
        cells = []
        for day in range(1, 32):
            try:
                date = dt.date(year, m + 1, day).isoformat()
            except ValueError:
                cells.append('<i class="c x"></i>')
                continue
            c = cal.get(date)
            if c is None:
                lvl = "f"  # future, or outside the period
            elif c == 0:
                lvl = "0"
            else:
                lvl = str(1 + sum(c > k for k in q))
            cells.append(f'<i class="c l{lvl}"></i>')
        peak = " peak" if m == peak_month else ""
        rows.append(f'<div class="mrow{peak}" data-m="{m}"><span class="ml">{MONTHS[m][:3]}</span>'
                    f'<div class="cells">{"".join(cells)}</div></div>')
    return f'<div class="{cls}">{"".join(rows)}</div>'


def diff_lines(lines: list[tuple[str, str]], cls: str = "hunk") -> str:
    """A unified-diff style block: ('+'|'-'|'@'|' ', text) per line. Lines are supporting motion."""
    kind = {"+": "add", "-": "del", "@": "hdr", " ": "ctx"}
    out = []
    for sign, text in lines:
        mark = "" if sign == "@" else f'<span class="sg">{E(sign)}</span>'
        out.append(f'<div class="dl {kind[sign]} rise" data-p="2">{mark}{text}</div>')
    return f'<div class="{cls}">{"".join(out)}</div>'


# v6 charts. Each beat's chart takes the shape of its question: a part of a whole is a waffle
# (one square, one percent: the ledger's own unit), a run is a stretch of the year line, a rate
# is one filled bar, a cadence is squares stacked by month. The hours stay a 24-bar histogram:
# the juror read it faster than a 24-hour dial.
FILLS = ["var(--signal)", "#ffb08c", "#a3431f", "#8f7b6c"]  # signal, then light, dark, taupe: told apart by lightness
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def alloc(total: int, shares: list[float]) -> list[int]:
    """Split total whole units by shares (largest remainder), so the parts add up exactly."""
    tot = sum(shares) or 1
    raw = [total * x / tot for x in shares]
    base = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: base[i] - raw[i])[: total - sum(base)]:
        base[i] += 1
    return base


def agent_parts(b: dict, team: str = "Claude") -> list[tuple[str, int]]:
    """The agents share as whole percents of all commits, per model (top 3 and the rest)."""
    rows = b["rows"][:3]
    names = [x["trailer"] for x in rows]
    shares = [x["share"] for x in rows]
    rest = 1 - sum(shares)
    if rest >= 0.01:
        names.append("others")
        shares.append(rest)
    prefix = team + " "
    if all(x.startswith(prefix) or x == "others" for x in names):
        names = [x[len(prefix):] if x.startswith(prefix) else x for x in names]
    return [(nm, k) for nm, k in zip(names, alloc(b["number"], shares)) if k > 0]


def legend(parts: list[tuple[str, int]], P2: str, rest: str | None = None) -> str:
    rows = "".join(f'<div class="lg"><i style="background:{FILLS[min(k, 3)]}"></i><b>{E(nm)}</b><em>{v}%</em></div>'
                   for k, (nm, v) in enumerate(parts))
    if rest:
        rows += f'<div class="lg rest"><i></i><b>{E(rest)}</b><em>{100 - sum(v for _, v in parts)}%</em></div>'
    return f'<div class="legend rise" {P2}>{rows}</div>'


def waffle(lit: list[int], P2: str, cls: str = "waffle") -> str:
    """10 x 10 squares, one per percent, filled row by row in the order of lit (counts per fill)."""
    cells = []
    for k, cnt in enumerate(lit):
        cells += [f'<i class="w" style="background:{FILLS[min(k, 3)]}"></i>'] * cnt
    cells += ['<i class="w o"></i>'] * (100 - len(cells))
    return f'<div class="{cls}" {P2}>{"".join(cells[:100])}</div>'


def year_line(story: dict, start: str, end: str, P2: str) -> str:
    """Every day of the year as one tick: active days stand up, the run is one solid block."""
    cal = {date: c for date, c in story["calendar"]}
    year = story["year"]
    ticks = []
    d0 = dt.date(year, 1, 1)
    for k in range(366 if (year % 4 == 0 and year % 100) or year % 400 == 0 else 365):
        date = (d0 + dt.timedelta(days=k)).isoformat()
        c = cal.get(date)
        cls = "f" if c is None else ("r" if start <= date <= end else ("a" if c > 0 else "z"))
        ticks.append(f'<i class="t {cls}"></i>')
    months = "".join(f'<span style="flex:{DAYS[k]}">{m[:1]}</span>' for k, m in enumerate(MONTHS))
    key = ('<div class="ykey"><span><i class="kr"></i>the run</span><span><i class="ka"></i>other days with commits</span></div>')
    return f'<div class="yline">{"".join(ticks)}</div><div class="ymonths">{months}</div>{key}'


def rate_bar(merged: int, opened: int, P2: str) -> str:
    w = 100 * merged / (opened or 1)
    return (f'<div class="rate rise" {P2}><div class="rtrack"><i class="bar rbar" style="width:{w:.1f}%"></i></div>'
            f'<div class="rlab"><span><b>{round(w)}%</b> merged</span><span>of {n(opened)} opened</span></div></div>')


def release_rug(rows: list[dict], year: int, P2: str, per_row: int = 3, sq: int = 20, gap: int = 4) -> str:
    """One square per release, stacked in the month it shipped, coloured by project: a unit
    column chart on a year axis, so a burst of releases reads as a tall column, not one tick."""
    months: dict[int, list[int]] = {}
    for k, x in enumerate(rows):
        for d in x["dates"]:
            months.setdefault(int(d[5:7]) - 1, []).append(k)
    tall = max((-(-len(v) // per_row) for v in months.values()), default=1)
    cols = []
    for m in range(12):
        cells = "".join(f'<i class="w" style="background:{FILLS[0] if k == 0 else FILLS[1]}"></i>'
                        for k in sorted(months.get(m, [])))
        cols.append(f'<div class="rc"><div class="rs" style="grid-template-columns:repeat({per_row},{sq}px);gap:{gap}px">{cells}</div>'
                    f'<span>{MONTHS[m][:1]}</span></div>')
    keys = "".join(f'<div class="lg"><i style="background:{FILLS[0] if k == 0 else FILLS[1]}"></i><b>{E(x["repo"])}</b>'
                   f'<em>{plural(x["count"], "release")}</em></div>' for k, x in enumerate(rows))
    return (f'<div class="rugs rise" {P2}><div class="rcols" style="height:{tall * (sq + gap) + 44}px">{"".join(cols)}</div>'
            f'<div class="legend rkeys">{keys}</div></div>')


def line_bars(adds: int, dels: int, ref: dict | None, P2: str) -> str:
    """Added, removed and the reference codebase as bars on one scale: the comparison is drawn,
    not only said. The reference bar is hatched taupe so it never reads as the person's own."""
    rows = [("added", adds, "var(--add)", ""), ("removed", dels, "var(--del)", "")]
    if ref:
        rows.append((ref["short"], ref["lines"], "#8f7b6c", " ref"))
    mx = max(v for _, v, _, _ in rows) or 1
    out = "".join(
        f'<div class="lrow{cls}"><div class="ll"><b>{E(lab)}</b><span>{compact(v)}</span></div>'
        f'<div class="ltrack"><i class="bar rbar" style="width:{max(0.6, 100 * v / mx):.1f}%;background:{col}"></i></div></div>'
        for lab, v, col, cls in rows)
    return f'<div class="lbars rise" {P2}>{out}</div>'


def month_bars(by_month: list[float], story: dict, P2: str) -> str:
    """Twelve monthly columns, the peak month in signal and labelled; months after the period are
    an empty baseline."""
    mx = max(by_month) or 1
    peak = max(range(12), key=lambda m: by_month[m])
    last = int(story.get("period_to", f"{story['year']}-12-31")[5:7]) if story.get("period_to") else 12
    cols = []
    for m in range(12):
        v = by_month[m]
        lab = f"<span>{compact(v)}</span>" if m == peak else ""
        h = 0 if m >= last and not v else max(1.5, 100 * v / mx)
        cols.append(f'<div class="mc{" peak" if m == peak else ""}"><div class="mt"><i class="bar cbar" style="height:{h:.1f}%">{lab}</i></div>'
                    f'<em>{MONTHS[m][:1]}</em></div>')
    return f'<div class="mbars rise" {P2}>{"".join(cols)}</div>'



def col_bars(cols: list[tuple[str, int]], lit: int | None, P2: str, cls: str) -> str:
    """A few labelled columns on one scale, the lit one in signal with its value on top; every
    column carries its value so the small ones still read."""
    mx = max((v for _, v in cols), default=1) or 1
    out = "".join(
        f'<div class="mc{" peak" if k == lit else ""}"><div class="mt"><i class="bar cbar" style="height:{max(1.2, 100 * v / mx):.1f}%">'
        f'<span>{n(v) if v < 100_000 else compact(v)}</span></i></div><em>{E(lab)}</em></div>'
        for k, (lab, v) in enumerate(cols))
    return f'<div class="mbars {cls} rise" {P2}>{out}</div>'


def punchcard(grid: list[list[int]], peak: list[int], P2: str) -> str:
    """Seven weekday rows of 24 hour dots, dot area by commits, the busiest hour of the week lit."""
    mx = max(max(r) for r in grid) or 1
    rows = []
    for w in range(7):
        dots = "".join(
            f'<span class="pc"><i class="w pd" style="width:{d:.1f}px;height:{d:.1f}px;background:{"var(--signal)" if [w, h] == list(peak) else "#8f7b6c"}"></i></span>'
            if (d := 5 + 31 * (grid[w][h] / mx) ** 0.5) and grid[w][h] else '<span class="pc"><i class="pz"></i></span>'
            for h in range(24))
        rows.append(f'<div class="pr"><b{" class=on" if w == peak[0] else ""}>{WEEKDAYS[w]}</b>{dots}</div>')
    ticks = "".join(f'<span style="left:{h / 24 * 100:.3f}%">{h:02d}</span>' for h in (0, 6, 12, 18))
    return f'<div class="punchc rise" {P2}>{"".join(rows)}<div class="pticks">{ticks}</div></div>'


LANG_FILLS = ["var(--signal)", "#8f7b6c", "#6e6258", "#5a5047", "#3a3530"]  # signal, then the muted ramp


def lang_bar(rows: list[list], P2: str) -> str:
    """One bar of every repo, split by primary language: the top one in signal, the rest a muted
    ramp (not GitHub's language colours), then a key with the counts."""
    tot = sum(v for _, v in rows) or 1
    segs = "".join(f'<i class="bar rbar" style="width:{100 * v / tot:.2f}%;background:{LANG_FILLS[min(k, 4)]}"></i>'
                   for k, (_, v) in enumerate(rows))
    keys = "".join(f'<div class="lg{" rest" if nm == "other" else ""}"><i style="background:{LANG_FILLS[min(k, 4)]}"></i>'
                   f'<b>{E(nm)}</b><em>{v}</em></div>' for k, (nm, v) in enumerate(rows))
    return f'<div class="lstack rise" {P2}><div class="lsbar">{segs}</div><div class="legend lkeys">{keys}</div></div>'


def model_timeline(rows: list[dict], year: int, P2: str) -> str:
    """Each model on the year line at the date of its first trailer, then the dated list; the
    latest model lit. At most eight rows (the latest eight)."""
    rows = rows[-8:]
    def x(iso):
        d = dt.date.fromisoformat(iso)
        return 100 * (d.timetuple().tm_yday - 1) / (365 + (d.year % 4 == 0))
    dots, prev, lift = [], -99.0, 0
    for k, r in enumerate(rows):  # a dot within a few days of the one before stands on top of it
        at = x(r["date"])
        lift = lift + 1 if at - prev < 3.5 else 0
        prev = at
        dots.append(f'<i class="md{" on" if k == len(rows) - 1 else ""}" style="left:{at:.2f}%;bottom:{-14 + 30 * lift}px"></i>')
    dots = "".join(dots)
    months = "".join(f'<span style="flex:{DAYS[k]}">{m[:1]}</span>' for k, m in enumerate(MONTHS))
    items = "".join(f'<div class="mi{" on" if k == len(rows) - 1 else ""}"><span>{short_date(r["date"])}</span><b>{E(r["name"])}</b></div>'
                    for k, r in enumerate(rows))
    return (f'<div class="mtl rise" {P2}><div class="mline">{dots}</div><div class="ymonths">{months}</div></div>'
            f'<div class="mlist rise" {P2}>{items}</div>')


def scene_html(b: dict, story: dict, total: int, direction: str = "a", thumb: bool = False) -> str:
    """One beat as HTML. Motion is marked, not timed: data-p="1" is the hero (lands first),
    data-p="2" is the supporting group (enters after the hero settles). beat_timing() turns
    the marks into times so the phases never overlap. thumb=True is the chrome-free still."""
    i, sid = b["index"], b["id"]
    cmd = b.get("cmd") or COMMANDS[sid].format(user=story["user"], year=story["year"])
    # The section name only: no slide counter, no hash, no part numbers anywhere in the film.
    label = f'<div class="label"><span>{E(b["label"])}</span></div>'
    if sid == "close":
        label = ""  # the last frame is the cover: no label
    if thumb:
        head = ""
    elif direction == "a":
        typed = sid == "hook"  # the hook's command is already run: frame 0 is the poster
        head = (f'<div class="term" style="font-size:{term_size(cmd, 28)}px"><span class="ps">~ $</span><span class="cmd" data-cmd="{E(cmd)}">'
                f'{E(cmd) if typed else ""}</span><i class="cur"></i></div>' + label)
    else:
        head = label
    P1, P2 = 'data-p="1"', 'data-p="2"'
    body = ""
    if sid == "hook":
        num = n(b["number"])
        body = f"""
      <div class="stack hook">
        <div class="name">{E(b['name'])}</div>
        <div class="big signal count" {P1} data-to="{b['number']}" data-from="{round(b['number'] * 0.62)}" style="font-size:{big_size(num, 540)}px">{num}</div>
        <div class="unit">{E(b['unit'])}</div>
        <div class="sub rise" {P2}>{E(b['line'])}</div>
      </div>"""
    elif sid == "shape":
        body = f"""
      <div class="stack">
        <div class="title rise" {P1}>{E(b['title'])}</div>
        {year_grid(story, b["peak_month"])}
        <div class="caption rise" {P2}>{E(b['caption'])}</div>
      </div>"""
    elif sid == "agents":
        team = b["unit"].rsplit(" with ", 1)[-1] if " with " in b["unit"] else "Claude"
        parts = agent_parts(b, team)
        note = b.get("prs") or b.get("auto") or b.get("sub")
        num = f'{b["number"]}%'
        chart = f'<div class="wrow">{waffle([v for _, v in parts], P2)}{legend(parts, P2, rest="you, solo")}</div>'
        body = f"""
      <div class="stack agents">
        <div class="big signal count pct" {P1} data-to="{b['number']}" data-from="0" style="font-size:{big_size(num, 250)}px">{num}</div>
        <div class="unit rise" {P1}>{E(b['unit'])}</div>
        {chart}
        {f'<div class="sub ink rise" {P2}>{E(note)}</div>' if note else ''}
      </div>"""
    elif sid == "diff":
        ref = f'{b["repo"]} #{b["pr"]}' if b.get("pr") else b["repo"]
        adds, dels = b["additions"], b["deletions"]
        tot = adds + dels or 1
        n_add = max(1, round(40 * adds / tot)) if adds else 0
        stat = ('<span class="add">' + "+" * n_add + '</span><span class="del">' + "-" * max(0 if not dels else 1, 40 - n_add) + "</span>")
        body = f"""
      <div class="stack diff">
        <div class="ref">{E(ref)} <span>{plural(b['files'], 'file')} changed</span></div>
        <div class="title">{E(b['title'])}</div>
        <div class="dnum"><b class="add big count" {P1} data-to="{adds}" data-from="0" data-sign="+">+{n(adds)}</b><b class="del big rise" {P2}>-{n(dels)}</b></div>
        <div class="dstat rise" {P2}>{stat}</div>
      </div>"""
    elif sid == "lines":
        adds, dels = b["added"], b["removed"]
        body = f"""
      <div class="stack lines">
        <div class="dnum"><b class="add big count" {P1} data-to="{adds}" data-from="0" data-sign="+" style="font-size:{big_size("+" + n(adds), 230, 560)}px">+{n(adds)}</b><b class="del big rise" {P1} style="font-size:{big_size("-" + n(dels), 120, 340)}px">-{n(dels)}</b></div>
        <div class="unit rise" {P1}>{E(b['unit'])}</div>
        {line_bars(adds, dels, b.get("ref"), P2)}
        {f'<div class="sub ink rise" {P2}>{E(b["sub"])}</div>' if b.get("sub") else ''}
      </div>"""
    elif sid == "actions":
        num = n(b["number"])
        body = f"""
      <div class="stack actions">
        <div class="big signal count" {P1} data-to="{b['number']}" data-from="0" style="font-size:{big_size(num, 340)}px">{num}</div>
        <div class="unit rise" {P1}>{E(b['unit'])}</div>
        {month_bars(b["by_month"], story, P2)}
        <div class="sub ink rise" {P2}>{E(b['sub'])}</div>
      </div>"""
    elif sid == "yoy":
        body = f"""
      <div class="stack yoy">
        <div class="big signal rise" {P1} style="font-size:{big_size(b['hero'], 400)}px">{E(b['hero'])}</div>
        <div class="unit rise" {P1}>{E(b['unit'])}</div>
        {col_bars([(str(y), v) for y, v in b["years"]], len(b["years"]) - 1, P2, "yb")}
        <div class="sub ink rise" {P2}>{E(b['sub'])}</div>
      </div>"""
    elif sid == "day":
        num = n(b["number"])
        week = [(f'{dt.date.fromisoformat(x).strftime("%a")} {int(x[8:])}', v) for x, v in b["week"]]
        lit = next((k for k, (x, _) in enumerate(b["week"]) if x == b["date"]), None)
        body = f"""
      <div class="stack day">
        <div class="big signal count" {P1} data-to="{b['number']}" data-from="0" style="font-size:{big_size(num, 400)}px">{num}</div>
        <div class="unit rise" {P1}>{E(b['unit'])}</div>
        {col_bars(week, lit, P2, "db")}
        <div class="sub ink rise" {P2}>{E(b['sub'])}</div>
      </div>"""
    elif sid == "punchcard":
        body = f"""
      <div class="stack punch">
        <div class="big signal rise" {P1} style="font-size:{big_size(b['hero'], 220)}px">{E(b['hero'])}</div>
        <div class="unit rise" {P1}>{E(b['unit'])}</div>
        {punchcard(b["grid"], b["peak"], P2)}
        <div class="sub ink rise" {P2}>{E(b['sub'])}</div>
      </div>"""
    elif sid == "languages":
        body = f"""
      <div class="stack langs">
        <div class="big signal rise" {P1} style="font-size:{big_size(b['hero'], 300)}px">{E(b['hero'])}</div>
        <div class="unit rise" {P1}>{E(b['unit'])}</div>
        {lang_bar(b["rows"], P2)}
      </div>"""
    elif sid == "models":
        num = n(b["number"])
        body = f"""
      <div class="stack models">
        <div class="mhead"><div class="big signal count" {P1} data-to="{b['number']}" data-from="0" style="font-size:260px">{num}</div>
        <div class="unit rise" {P1}>{E(b['unit'])}</div></div>
        {model_timeline(b["rows"], story["year"], P2)}
      </div>"""
    elif sid in ("run", "ship", "surprise", "started", "releases", "oss"):
        num = n(b["number"])
        extra = ""
        if sid == "ship":
            first = [x.strip() for x in re.split(r"(?<=\.)\s+", b["sub"]) if x.strip()][:1]
            # one text box per line (the line is a flex row); hyphenated names never break
            lines = [("+", "<span>" + re.sub(r"(\S+-\S+)", r'<span class="nw">\1</span>', E(x)) + "</span>")
                     for x in first + ([b["ext"]] if b.get("ext") else [])]
            extra = diff_lines(lines)
        if sid == "ship" and b.get("opened"):
            extra = rate_bar(b["number"], b["opened"], P2) + (diff_lines(lines[1:]) if len(lines) > 1 else "")  # the rate is drawn
        if sid == "run" and b.get("run_from"):  # not "start": that key is the beat's time in the film
            extra = f'<div class="runline rise" {P2}>{year_line(story, b["run_from"], b["end"], P2)}</div>'
        if sid == "releases" and all(x.get("dates") for x in b["rows"][:3]) and b["rows"]:
            extra = release_rug(b["rows"][:3], story["year"], P2)
        elif sid in ("releases", "oss"):
            if sid == "releases":
                rows = [(" ", f'<b class="tag">{E(x["tag"])}</b><span>{E(x["repo"])}</span>'
                         f'<em>{plural(x["count"], "release")}</em>') for x in b["rows"][:2]]
            else:
                rows = [("+", f'<b>{E(x["name"])}</b><em>{plural(x["stars"], "star")}</em>') for x in b["rows"][:3]]
            extra = diff_lines(rows, cls="hunk rows")
        if sid == "started":
            extra = '<div class="list">' + "".join(
                f'<div class="li rise" {P2}><div class="lin"><b><i class="plus">+</i>{E(x["name"])}</b>'
                f'<span>{E(x["meta"])}</span></div><div class="lid">{E(x["desc"])}</div></div>'
                for x in b["rows"][:2]) + "</div>"
        sub = f'<div class="sub rise" {P2}>{E(b["sub"])}</div>' if b.get("sub") and sid != "ship" else ""
        size = big_size(num, 340 if sid in ("started", "releases", "oss") else 500)
        body = f"""
      <div class="stack {sid}">
        <div class="big signal count" {P1} data-to="{b['number']}" data-from="0" style="font-size:{size}px">{num}</div>
        <div class="unit rise" {P1}>{E(b['unit'])}</div>
        {extra}
        {sub}
      </div>"""
    elif sid == "clock":
        hours = b["hours"]
        mx = max(hours) or 1
        bars = "".join(
            f'<div class="hb{" peak" if h == b["peak"] else ""}"><i class="bar" style="height:{max(4, round(100 * v / mx))}%">'
            f'{f"<span>{h:02d}:00</span>" if h == b["peak"] else ""}</i></div>'
            for h, v in enumerate(hours))
        ticks = "".join(f'<span style="left:{h / 24 * 100:.3f}%">{h:02d}</span>' for h in (0, 6, 12, 18))
        body = f"""
      <div class="stack">
        <div class="big signal rise" {P1} style="font-size:240px">{E(b['peak_label'])}</div>
        <div class="unit rise" {P1}>is when you commit most</div>
        <div class="hours">{bars}</div>
        <div class="ticks">{ticks}</div>
        <div class="sub rise" {P2}>{E(b['sub'])}</div>
      </div>"""
    elif sid == "work":
        rows = b["rows"][:3]
        mx = max(x["commits"] for x in rows) or 1
        rows = "".join(
            f'<div class="wr rise" {P1}><div class="wl"><b>{E(x["name"])}</b>'
            f'<span>{n(x["commits"])} commits</span></div>'
            f'<div class="track"><i class="bar wbar" style="width:{max(2, 100 * x["commits"] / mx):.1f}%;background:{"#FF5B24" if k == 0 else "#5A5047"}"></i></div>'
            f'<div class="lang"><i style="background:{E(x["color"])}"></i>{E(x["language"] or "")}</div></div>'
            for k, x in enumerate(rows))
        lead = (f'<div class="quote rise" {P2}><span>{E(b["lead_name"])}:</span> {E(b["lead"])}</div>'
                if b["lead"] else "")
        body = f"""
      <div class="stack">
        <div class="title rise" {P1}>The projects that took the time.</div>
        <div class="work">{rows}</div>
        {lead}
      </div>"""
    elif sid == "identity":
        body = f"""
      <div class="stack identity">
        <div class="kicker rise" {P1}>You were</div>
        <div class="arch rise" {P1}>{E(b['name'])}</div>
        <div class="sub rise" {P2}>{E(b['reason'])}</div>
      </div>"""
    elif sid == "close":
        body = f"""
      <div class="stack close">
        {year_grid(story, None, "grid mini")}
        <div class="handle rise" {P1}>{E(b['handle'])}</div>
        <div class="unit rise" {P1}>{E(b['year'])}, in review.</div>
        {"" if thumb else f'<div class="cta rise" {P2}><span>{E(b["cta"].split(": ", 1)[0])}</span>{E(b["cta"].split(": ", 1)[-1])}</div>'}
      </div>"""
    return f'<div class="inner">{head}{body}</div>'


def term_size(cmd: str, base: int, width: int = 912) -> int:
    """Font size (px) that fits '~ $ <cmd>' plus the cursor on one line; JetBrains Mono is 0.6 em a glyph."""
    return max(24, min(base, int(width / (0.6 * (len(cmd) + 6)))))


def chapter_html(ch: dict) -> str:
    """Direction B: the terminal as a chapter card between sections."""
    return (f'<div class="inner chapter">'
            f'<div class="stack"><div class="term" style="font-size:{term_size(ch["cmd"], 40)}px"><span class="ps">~ $</span><span class="cmd" data-cmd="{E(ch["cmd"])}">'
            f'</span><i class="cur"></i></div><div class="arch rise" data-p="2">{E(ch["title"])}</div></div></div>')


def beat_timing(sid: str, html_: str, typed: str | None, pace: str = PACE) -> dict:
    """Times, relative to the scene start, for the phases of one scene. Never two phases at once:
    type the command, stop; then the hero lands; then the supporting group; then hold."""
    P = PACES[pace]
    speed, gap = P["speed"], P["gap"]
    t = P["lead"] if sid != "hook" else 0.0
    type_at = type_dur = 0.0
    if typed:
        type_at, type_dur = t, min(1.6, 0.3 + len(typed) / TYPE_CPS)
        t = type_at + type_dur + gap
    t1 = t
    hero = speed * HERO.get(sid, 1.2) if 'data-p="1"' in html_ or sid in ("shape", "close") else 0.0
    t2 = t1 + hero + (gap if hero else 0)
    n2 = html_.count('data-p="2"')
    settle = t2 + (speed * (SUPPORT_RISE + STAGGER * (n2 - 1)) if n2 else 0)
    if any(k in html_ for k in ('class="w', 'class="t r')):
        settle += speed * 0.45  # a unit chart fills one square at a time (0.8 s at most), then holds
    hold = HOLD.get(sid, HOLD["default"]) * P["hold"]
    if pace != "calm":  # a shorter hold still has to read: hyperframes line_unread floor, 0.75 (0.5 + 0.3 a word)
        lines = re.findall(r'<div class="sub[^"]*"[^>]*>(.*?)</div>', html_, re.S)
        words = max((len(re.sub(r"<[^>]+>", " ", x).split()) for x in lines), default=0)
        hold = max(hold, 0.75 * (0.5 + 0.3 * words) + 0.1)
    return {"type_at": round(type_at, 3), "type_dur": round(type_dur, 3), "t1": round(t1, 3),
            "t2": round(t2, 3), "settle": round(settle, 3), "duration": round(settle + hold + P["exit"], 3)}


def plan_scenes(story: dict, direction: str, pace: str = PACE) -> list[dict]:
    """The beats, plus chapter cards for direction B, each with its html and phase timing."""
    beats = story["beats"]
    scenes = []
    parts = [c for c in CHAPTERS if any(b["id"] in c[2] for b in beats)]
    for b in beats:
        if direction == "b" and PACES[pace]["chapters"]:
            for k, (title, cmd, ids) in enumerate(parts):
                first = next(x for x in beats if x["id"] in ids)
                if first is b:
                    ch = {"part": k + 1, "parts": len(parts), "title": title,
                          "cmd": cmd.format(user=story["user"], year=story["year"])}
                    h = chapter_html(ch)
                    scenes.append({"key": f"ch{k + 1}", "id": "chapter", "html": h, "beat": None,
                                   **beat_timing("chapter", h, ch["cmd"], pace)})
        h = scene_html(b, story, len(beats), direction)
        typed = b.get("cmd") if direction == "a" and b["id"] != "hook" else None
        scenes.append({"key": b["id"], "id": b["id"], "html": h, "beat": b, **beat_timing(b["id"], h, typed, pace)})
    return scenes


def build(story: dict, out: Path, music: Path | None, cues: Path | None, direction: str = DIRECTION) -> Path:
    beats = story["beats"]
    for i, b in enumerate(beats):
        b["index"] = i + 1
        b.setdefault("cmd", COMMANDS[b["id"]].format(user=story["user"], year=story["year"]))
    pace = story.get("pace", PACE)
    scenes = plan_scenes(story, direction, pace)
    cuts = plan_cuts(story) if PACES[pace].get("cuts") else []
    story["cuts"] = cuts
    for s, c in zip(scenes, cuts):  # a scene holds on until the next one's entrance starts
        s["duration"] = round(s["duration"] + c["d"] * CUT_OVERLAP, 3)
    grid = beat_grid(music, cues)
    snap_times(scenes, grid)
    for s in scenes:
        if s["beat"] is not None:
            s["beat"]["start"], s["beat"]["duration"] = s["start"], s["duration"]
    total_dur = round(scenes[-1]["start"] + scenes[-1]["duration"], 3)
    comp = out / "composition"
    (comp / "assets" / "fonts").mkdir(parents=True, exist_ok=True)
    for f in (ASSETS / "fonts").glob("*.ttf"):
        shutil.copy(f, comp / "assets" / "fonts" / f.name)
    audio = ""
    if music and music.exists():
        (comp / "assets" / "music").mkdir(parents=True, exist_ok=True)
        shutil.copy(music, comp / "assets" / "music" / music.name)
        fade = {"version": 1, "lanes": [{"target": "volume", "points": [
            {"t": 0, "v": 0.5}, {"t": max(0, total_dur - 2.2), "v": 0.5}, {"t": total_dur, "v": 0}]}]}
        audio = (f'<audio id="music" src="assets/music/{E(music.name)}" data-start="0" data-duration="{total_dur}" '
                 f'data-track-index="9" data-volume="0.5" data-automation=\'{json.dumps(fade)}\'></audio>')
    flow = [{"T": round(scenes[i + 1]["start"] - c["d"] * CUT_OVERLAP, 3), "k": i, "n": c["n"]} for i, c in enumerate(cuts)]
    if cuts:
        # both clips play through the transition, so they sit on alternate tracks; a scene stacks
        # above the one before it unless the transition lifts the outgoing one off
        spans, z = [], 1000
        for i, s in enumerate(scenes):
            if i:
                z += -1 if cuts[i - 1]["aTop"] else 1
            start = flow[i - 1]["T"] if i else s["start"]
            end = flow[i]["T"] + cuts[i]["d"] if i < len(cuts) else s["start"] + s["duration"]
            spans.append(f'<section id="s-{s["key"]}" class="clip scene" data-start="{start}" data-duration="{round(end - start, 3)}" '
                         f'data-track-index="{1 + 2 * (i % 2)}" style="z-index:{z}"><div class="tw">{s["html"]}</div></section>')
        html_scenes = "\n    ".join(spans)
    else:
        html_scenes = "\n    ".join(
            f'<section id="s-{s["key"]}" class="clip scene" data-start="{s["start"]}" data-duration="{s["duration"]}" '
            f'data-track-index="1">{s["html"]}</section>' for s in scenes)
    keys = ("type_at", "type_dur", "t1", "t2", "start", "duration")
    timing = [{"key": s["key"], "id": s["id"], "beat": s["beat"]["index"] if s["beat"] else 0,
               **{k: s[k] for k in keys}} for s in scenes]
    tpl = (ASSETS / "template.html").read_text()
    page = (tpl.replace("__DURATION__", str(total_dur))
            .replace("__ROOT_CLASS__", "dir-" + direction + (" cuts" if cuts else ""))
            .replace("/*__CUTS__*/", cut_runner(cut_data(story), flow) if cuts else "")
            .replace("__HANDLE__", E("@" + story["user"]))
            .replace("__YEAR__", E(story["year_label"]))
            .replace("<!--__SCENES__-->", html_scenes)
            .replace("<!--__AUDIO__-->", audio)
            .replace("/*__TIMING__*/[]", json.dumps(timing))
            .replace("/*__PACE__*/{ speed: 1, fadeIn: 0.3, fadeOut: 0.35 }", json.dumps(
                {"speed": PACES[pace]["speed"], "fadeIn": PACES[pace]["fade_in"], "fadeOut": PACES[pace]["fade_out"]})))
    (comp / "index.html").write_text(page)
    build_thumbnail(story, out, tpl)
    story["direction"] = direction
    (out / "story.json").write_text(json.dumps(story, indent=2))
    return comp / "index.html"


THUMB_SECONDS = 1.0
THUMB_TITLE = 190      # display size of the identity title on the thumbnail, px
THUMB_WIDTH = 912      # 1080 less 84 px each side
THUMB_EM = 0.36        # Bricolage 800 at 75% stretch: average advance per character, em (measured 0.33)


def title_lines(name: str, max_lines: int = 5) -> list[str]:
    """The identity name as display lines: one word a line ("The / Weekend / Orchestrator").
    Past max_lines, the words before the last are packed two to a line; the last word always
    stands alone so it can carry the signal colour."""
    words = name.split()
    if len(words) <= max_lines:
        return words
    head, last = words[:-1], words[-1]
    return [" ".join(head[i:i + 2]) for i in range(0, len(head), 2)] + [last]


def title_size(lines: list[str], base: int = THUMB_TITLE, width: int = THUMB_WIDTH) -> int:
    """Largest size up to base at which the longest line fits width on one line."""
    longest = max((len(x) for x in lines), default=1)
    return min(base, int(width / (THUMB_EM * longest)))


def stat_lines(reason: str) -> list[str]:
    """The identity reason as one sentence a stat: "57% of commits shipped with agents, 38% of
    commits on weekends." -> ["57% of commits shipped with agents.", "38% on weekends."]
    (a repeated "of commits" is dropped after the first line)."""
    parts = [x.strip().rstrip(".") for x in reason.split(", ") if x.strip().rstrip(".")]
    out, seen = [], False
    for x in parts:
        if seen:
            x = x.replace(" of commits", "", 1)
        seen = seen or " of commits" in x
        out.append(x[0].upper() + x[1:] + ".")
    return out


def thumb_identity_html(b: dict, story: dict) -> str:
    """The thumbnail cover from the identity beat: mono kicker at the top ("@user / <year>, in
    one line"), the name huge in condensed Bricolage with its last word in --signal, then the
    stats behind it in mono ink, vertically centred. No label, counter, rail or CTA."""
    lines = title_lines(b["name"])
    title = "<br>".join(E(x) for x in lines[:-1])
    title += ("<br>" if title else "") + f'<span class="signal">{E(lines[-1])}</span>'
    stats = "<br>".join(E(x) for x in stat_lines(b.get("reason", "")))
    return (f'<div class="inner tid"><div class="tk">{E("@" + story["user"])} / {E(b["label"])}</div>'
            f'<div class="sp"></div><div class="tt" style="font-size:{title_size(lines)}px">{title}</div>'
            + (f'<div class="ts">{stats}</div>' if stats else "") + '<div class="sp"></div></div>')


def build_thumbnail(story: dict, out: Path, tpl: str) -> Path:
    """<out>/thumbnail/: a one-second, motionless cover with no label, slide counter, rail or
    CTA. Made from the identity beat ("The Weekend Orchestrator" and the stats behind it); a
    story without one falls back to the close (year grid, handle, "<year>, in review.").
    Snapshot it to thumbnail.png."""
    ident = next((b for b in story["beats"] if b["id"] == "identity" and b.get("name")), None)
    close = next((b for b in story["beats"] if b["id"] == "close"), None)
    if ident is None and close is None:
        raise ValueError("story has no identity or close beat to make a thumbnail from")
    comp = out / "thumbnail"
    (comp / "assets" / "fonts").mkdir(parents=True, exist_ok=True)
    for f in (ASSETS / "fonts").glob("*.ttf"):
        shutil.copy(f, comp / "assets" / "fonts" / f.name)
    if ident is not None:
        sid, body = "identity", thumb_identity_html(ident, story)
    else:
        sid, body = "close", scene_html(close, story, len(story["beats"]), thumb=True)
    scene = (f'<section id="s-{sid}" class="clip scene" data-start="0" data-duration="{THUMB_SECONDS}" '
             f'data-track-index="1">{body}</section>')
    page = re.sub(r"<!--rail-->.*?<!--/rail-->", "", tpl, flags=re.S)
    page = (page.replace("__DURATION__", str(THUMB_SECONDS))
            .replace("__ROOT_CLASS__", "thumb")
            .replace("<title>GitHub year in review</title>", "<title>GitHub year in review: thumbnail</title>")
            .replace("<!--__SCENES__-->", scene)
            .replace("<!--__AUDIO__-->", "")
            .replace("/*__TIMING__*/[]", "[]")
            .replace("/*__CUTS__*/", "")
            .replace("/*__PACE__*/", ""))
    (comp / "index.html").write_text(page)
    return comp / "index.html"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("year_json", nargs="?")
    p.add_argument("--out")
    p.add_argument("--story", help="edited story.json to build from instead of regenerating")
    p.add_argument("--music")
    p.add_argument("--cues", help="beat JSON (hyperframes beats --json output, or a beats array) to start scenes on the beat; detected from --music when omitted")
    p.add_argument("--cta", default=CTA)
    p.add_argument("--direction", choices=["a", "b"], default=DIRECTION)
    p.add_argument("--pace", choices=list(PACES), help="calm (default): chapter cards, fades, 3 s holds. tight: "
                   "no cards, cuts, faster motion, 2.5 s holds, so more beats fit the budget. suite: no cards, a "
                   "transition from the suite on every cut. --story keeps its own")
    p.add_argument("--cut", default="", help="suite pace: the transition into a card, beat=number, comma separated "
                   "(lines=61,ship=1); any number in transitions.js. --story keeps these")
    p.add_argument("--cut-skip", default="", help="suite pace: transition numbers never to pick, comma separated")
    p.add_argument("--transitions", action="store_true", help="print the transition suite and exit")
    p.add_argument("--beats", default="", help="optional beat ids to force in, comma separated (an alternative "
                   "in the same slot makes way; forced beats count against the time budget first)")
    p.add_argument("--skip", default="", help="optional beat ids to leave out, comma separated")
    p.add_argument("--catalogue", action="store_true", help="print the beat catalogue and exit")
    a = p.parse_args(argv)
    if a.catalogue:
        for sid, slot, must, needs, rule, score in CATALOGUE:
            print(f"{sid:10} {slot:10} {'mandatory' if must else 'optional ':9}  {rule}; score: {score}")
        return 0
    if a.transitions:
        by_n = {t["n"]: t for t in transition_list()}
        for sid, ns in PAIRS.items():
            print(f"{sid:10} " + ", ".join(f"{n} {by_n[n]['name']} ({by_n[n]['d']:g} s)" for n in ns))
        print("neutral    " + ", ".join(f"{n} {by_n[n]['name']}" for n in NEUTRAL))
        return 0
    if not a.out or not (a.year_json or a.story):
        p.error("a year.json (or --story) and --out are needed to build")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.story:
        story = json.loads(Path(a.story).read_text())  # copy edits stay; timing is re-derived
        if a.pace:
            story["pace"] = a.pace
    else:
        ids = lambda x: [k.strip() for k in x.split(",") if k.strip()]
        story = make_story(json.loads(Path(a.year_json).read_text()), a.cta, ids(a.beats), ids(a.skip), a.pace or PACE)
    if a.cut:
        story["cut_force"] = {k.strip(): int(v) for k, v in (x.split("=") for x in a.cut.split(","))}
    if a.cut_skip:
        story["cut_skip"] = [int(x) for x in a.cut_skip.split(",")]
    page = build(story, out, Path(a.music) if a.music else None, Path(a.cues) if a.cues else None, a.direction)
    total = story["beats"][-1]["start"] + story["beats"][-1]["duration"]
    print(f"{len(story['beats'])} beats, {total:.1f}s -> {page}", file=sys.stderr)
    if story.get("cuts"):
        print("cuts:     " + ", ".join(f"{c['to']} {c['n']}" for c in story["cuts"]), file=sys.stderr)
    sel = story.get("selection")
    if sel:
        print("chosen:   " + ", ".join(f"{x['id']}" + ("" if x["score"] is None else f" {x['score']:.2f}")
                                       for x in sel["chosen"]), file=sys.stderr)
        print("left out: " + "; ".join(f"{x['id']}" + ("" if x["score"] is None else f" {x['score']:.2f}") + f" ({x['reason']})"
                                       for x in sel["left_out"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
