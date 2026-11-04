#!/usr/bin/env python3
"""Turn year.json into story.json and a HyperFrames composition.

    python3 build.py year.json --out <output-dir> [--story story.json] [--music track.mp3]
                     [--cues beats.json] [--cta "Make yours: ..."]

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
EST_DURATION = {"hook": 5.6, "shape": 7.6, "run": 6.4, "clock": 7.2, "work": 7.6, "agents": 7.8,
                "ship": 6.9, "diff": 6.9, "releases": 7.2, "started": 7.4, "oss": 7.0, "surprise": 6.4,
                "identity": 6.0, "close": 6.8}
# Pacing (seconds). One thing moves at a time; every beat holds still for HOLD before it leaves.
LEAD, GAP, EXIT = 0.3, 0.35, 0.4
TYPE_CPS = 30  # typing speed, characters per second
HERO = {"hook": 1.4, "shape": 1.6, "clock": 1.3, "work": 1.3, "identity": 0.7, "close": 0.8}
SUPPORT_RISE, STAGGER = 0.55, 0.15
HOLD = {"default": 3.0, "close": 3.6, "chapter": 1.2}
DIRECTION = "b"  # juror pick 2026-11-03; see docs/design.md v3
# Direction B: chapter cards (title, command, beats in the chapter), inserted before the chapter's first beat.
CHAPTERS = [
    ("The rhythm", "git log --since={year}-01-01 --author={user}", ("shape", "run", "clock")),
    ("The work", "git shortlog -sn --since={year}-01-01", ("work", "agents", "ship", "diff")),
    ("What shipped", "git tag --sort=-creatordate", ("releases", "started", "oss", "surprise")),
]
MAX_TOTAL = 70.0  # LinkedIn: about a minute; calm pacing over more beats
# Beats dropped first when the film runs long; the last ones go last. hook, identity and close
# are never dropped. The optional beats that flatter (agents, diff, releases) outlast rhythm detail.
DROP_ORDER = ["surprise", "oss", "diff", "started", "run", "clock", "releases", "ship", "agents", "work", "shape"]
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
    "releases": "git tag --sort=-creatordate",
    "started": "gh repo list --source",
    "oss": "gh search prs --author @me --merged",
    "surprise": "crontab -l",
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


def archetype(d: dict) -> dict:
    r, pr, t = d["rhythm"], d["pull_requests"], d["totals"]
    weekend = weekend_share(d)
    auto_share = d["automation"]["commits"] / t["commits"] if t["commits"] else 0
    public_external = pr.get("external_public", [])
    new = len(d["new_repos"]) + d.get("new_private_repos", 0)

    if r["night_share"] > 0.30:
        adj, why_a = "Night Shift", f"{pct(r['night_share'])} of commits after 10 pm"
    elif r["morning_share"] > 0.25:
        adj, why_a = "Early", f"{pct(r['morning_share'])} of commits before 9 am"
    elif weekend > 0.35:
        adj, why_a = "Weekend", f"{pct(weekend)} of commits on weekends"
    elif r["streak"]["longest"] >= 30:
        adj, why_a = "Relentless", f"a {r['streak']['longest']}-day streak"
    else:
        adj, why_a = "Steady", f"{n(r['active_days'])} active days"

    ag = d.get("agents") or {}
    if auto_share > 0.25 and new < 6:
        noun, why_n = "Automator", f"{pct(auto_share)} of commits by your own automation"
    elif ag.get("agent_share", 0) >= 0.4 and ag.get("agent_commits_est", 0) >= 100:
        noun, why_n = "Orchestrator", f"{pct(ag['agent_share'])} of commits shipped with agents"
    elif sum(c for _, c in public_external) >= 10:
        noun, why_n = "Contributor", f"{n(sum(c for _, c in public_external))} PRs merged into open source"
    elif t["reviews"] > t["prs"] and t["reviews"] >= 10:
        noun, why_n = "Reviewer", f"{n(t['reviews'])} reviews"
    elif new >= 6:
        noun, why_n = "Builder", f"{n(new)} new repos"
    elif pr["merged"] >= 100:
        noun, why_n = "Shipper", f"{n(pr['merged'])} merged PRs"
    else:
        noun, why_n = "Maker", f"{n(t['commits'])} commits"
    return {"name": f"The {adj} {noun}", "reason": f"{why_n[0].upper()}{why_n[1:]}, {why_a}."}


def make_story(d: dict, cta: str) -> dict:
    u, p, t, r, pr = d["user"], d["period"], d["totals"], d["rhythm"], d["pull_requests"]
    year_label = f"{p['year']} so far" if p["partial"] else str(p["year"])
    auto_names = {a["name"] for a in d["automation"]["repos"]}
    human_repos = [x for x in d["repos"] if x["name"] not in auto_names and not x["private"]]
    beats: list[dict] = []

    # 1 hook
    beats.append({
        "id": "hook", "label": f"GitHub, {year_label}",
        "name": u["name"], "number": t["contributions"], "unit": "contributions",
        "line": f"on GitHub, across {plural(d['repo_count'], 'repo')} and {plural(r['active_days'], 'active day')}."
        if d["repo_count"] else "on GitHub.",
    })

    # 2 shape
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
    beats.append({
        "id": "shape", "label": "The shape of the year", "title": "Every day of the year, one square.",
        "peak_month": peak_m, "peak_value": months[peak_m], "caption": caption,
        "busiest": r["busiest_day"], "first_active_month": first_active,
    })

    # 3 run
    s = r["streak"]
    if s["longest"] >= 3:
        still = s["end"] == p["to"] and s["current"] == s["longest"]
        beats.append({
            "id": "run", "label": "The longest run",
            "number": s["longest"], "unit": "days in a row",
            "sub": f"{short_date(s['start'])} to {short_date(s['end'])}" + (", and still going" if still else ""),
            "facts": [[n(r["active_days"]), "days with commits"],
                      [pct(weekend_share(d)), "of commits on weekends"]],
        })

    # 4 clock
    if r["commits_sampled"] >= 40 and r["peak_hour"] is not None:
        late = r.get("latest_night_commit")
        beats.append({
            "id": "clock", "label": "When the work happens",
            "hours": r["by_hour"], "peak": r["peak_hour"], "peak_label": hour_label(r["peak_hour"]),
            "sub": f"Latest commit: {late['time']} on {short_date(late['date'])}." if late
            else f"{pct(r['night_share'])} of commits after 10 pm.",
        })

    # 5 work
    if human_repos:
        top = human_repos[:4]
        beats.append({
            "id": "work", "label": "Where the hours went",
            "rows": [{"name": x["short"], "commits": x["commits"], "language": x["language"],
                      "color": x["color"] or "#A39B8E"} for x in top],
            "lead": clause(top[0]["description"], 12),
            "lead_name": top[0]["short"],
        })

    # optional: agents. Shown only when signed agent commits are really there.
    ag = d.get("agents") or {}
    auto = d["automation"]
    agents_beat = None
    if ag.get("agent_commits_sampled", 0) >= 10 and ag.get("agent_share", 0) >= 0.05:
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
        auto_line = ""
        if auto["commits"] >= 50:
            auto_line = f"Your cron's {n(auto['commits'])} commits are counted separately."
        agents_beat = {
            "id": "agents", "label": "Shipped with a team",
            "number": round(ag["agent_share"] * 100), "unit": f"of your commits co-written with {team}",
            "rows": rows, "trend": trend, "prs": prs_line, "auto": auto_line,
            "sub": (prs_line + " " + trend).strip() or "You wrote the brief, reviewed and merged.",
        }
        beats.append(agents_beat)

    # 6 ship
    if pr["opened"] >= 5:
        ext = pr.get("most_starred_external")
        ext_line = ""
        if ext and ext["repo"] != "a private repo":
            ext_line = f"Including one into {ext['repo']}, {n(ext['stars'])} stars."
        elif pr["external_merged"]:
            ext_line = f"{n(pr['external_merged'])} of them into other people's repos."
        beats.append({
            "id": "ship", "label": "What landed",
            "number": pr["merged"], "unit": "pull requests merged",
            "sub": f"{pct(pr['merge_rate'])} of the {n(pr['opened'])} opened. {n(t['reviews'])} reviews given.",
            "ext": ext_line,
        })

    # optional: the biggest change, as a diff stat
    big = pr.get("biggest")
    if big and big.get("title") and big["additions"] + big["deletions"] >= 300:
        beats.append({
            "id": "diff", "label": "The biggest change",
            "repo": big["repo"].split("/")[-1], "pr": big.get("number"), "title": clause(big["title"], 9),
            "additions": big["additions"], "deletions": big["deletions"], "files": big["files"],
            "total_added": pr.get("lines_added", 0), "total_removed": pr.get("lines_removed", 0),
            "at_least": pr.get("sampled", 0) < pr.get("merged", 0),
        })

    # optional: releases shipped
    rel = d.get("releases") or {}
    if rel.get("total", 0) >= 3:
        named = [x for x in rel["repos"] if x["repo"]]
        lead = named[0] if named else None
        beats.append({
            "id": "releases", "label": "Shipped to users",
            "number": rel["total"], "unit": "releases tagged" if rel["total"] != 1 else "release tagged",
            "rows": [{"tag": x["latest"], "repo": x["repo"], "count": x["count"]} for x in named[:3]],
            "sub": (f"{lead['repo']} went from {lead['first']} to {lead['latest']}." if lead and lead["first"] != lead["latest"]
                    else f"Across {plural(len(rel['repos']), 'project')}."),
        })

    # 7 started
    new = d["new_repos"]
    total_new = len(new) + d.get("new_private_repos", 0)
    if total_new:
        starred = sorted([x for x in new if x["stars"] > 0], key=lambda x: -x["stars"])
        picks = (starred + [x for x in new if x["stars"] == 0 and x["description"]])[:3]
        beats.append({
            "id": "started", "label": "Started this year",
            "number": total_new, "unit": "new repos" if total_new != 1 else "new repo",
            "rows": [{"name": x["name"], "meta": (f"{plural(x['stars'], 'star')}" if x["stars"] else (x["language"] or "")),
                      "desc": clause(x["description"], 8)} for x in picks],
            "sub": (f"{plural(d['stars']['gained'], 'star')} earned this year." if d["stars"]["gained"] else
                    f"{len(new)} public, {d.get('new_private_repos', 0)} private."),
        })

    # optional: open source, merged into other people's public repos
    ext = pr.get("external_public") or []
    if sum(k for _, k in ext) >= 3:
        stars = pr.get("external_public_stars") or {}
        beats.append({
            "id": "oss", "label": "Open source",
            "number": sum(k for _, k in ext), "unit": "PRs merged into other people's projects",
            "rows": [{"name": r, "count": k, "stars": stars.get(r, 0)} for r, k in ext[:3]],
        })

    # 8 surprise (the automation goes into the agents beat when that beat exists)
    human_commits = t["commits"] - auto["commits"]
    if auto["commits"] >= 50 and not agents_beat:
        a = max(auto["repos"], key=lambda x: x["commits"])
        beats.append({
            "id": "surprise", "label": "One more thing",
            "number": auto["commits"], "unit": "commits were not you",
            "sub": (f"A scheduled job in {a['name'].split('/')[-1]}."
                    + (f" It made more commits than you did ({n(human_commits)})." if auto["commits"] > human_commits else "")),
        })
    elif r.get("busiest_day") and not (auto["commits"] >= 50 and agents_beat):
        b = r["busiest_day"]
        beats.append({
            "id": "surprise", "label": "One more thing",
            "number": b["count"], "unit": f"contributions on {short_date(b['date'])}",
            "sub": "Your busiest single day of the year.",
        })

    # 9 identity
    a = archetype(d)
    beats.append({"id": "identity", "label": f"{year_label}, in one line", "name": a["name"], "reason": a["reason"]})

    # 10 close
    beats.append({"id": "close", "label": "Year in review", "handle": f"@{u['login']}",
                  "year": year_label, "cta": cta})

    fit_length(beats)
    for b in beats:
        b["cmd"] = COMMANDS[b["id"]].format(user=u["login"], year=p["year"])
    return {"user": u["login"], "year": p["year"], "year_label": year_label, "calendar": d["calendar"],
            "beats": beats}


# --------------------------------------------------------------------------- timing


def fit_length(beats: list[dict], max_total: float = MAX_TOTAL) -> None:
    """Drop the least important beats until the film fits, then number and time them."""
    while sum(EST_DURATION[b["id"]] for b in beats) > max_total:
        ids = [b["id"] for b in beats]
        victim = next((x for x in DROP_ORDER if x in ids), None)
        if victim is None:
            break
        beats[:] = [b for b in beats if b["id"] != victim]
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
        rows = "".join(
            f'<div class="tr rise" {P2}><span class="tk">Co-authored-by:</span>'
            f'<b>{E(x["trailer"])}</b><i class="tb"><i class="bar tbar" style="width:{max(3, 100 * x["share"]):.1f}%"></i></i>'
            f'<em>{pct(x["share"])}</em></div>'
            for x in b["rows"][:3])
        note = b.get("prs") or b.get("auto") or b.get("sub")
        num = f'{b["number"]}%'
        body = f"""
      <div class="stack agents">
        <div class="big signal count pct" {P1} data-to="{b['number']}" data-from="0" style="font-size:{big_size(num, 320)}px">{num}</div>
        <div class="unit rise" {P1}>{E(b['unit'])}</div>
        <div class="trailers">{rows}</div>
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
    elif sid in ("run", "ship", "surprise", "started", "releases", "oss"):
        num = n(b["number"])
        extra = ""
        if sid == "ship":
            first = [x.strip() for x in re.split(r"(?<=\.)\s+", b["sub"]) if x.strip()][:1]
            lines = [("+", E(x)) for x in first + ([b["ext"]] if b.get("ext") else [])]
            extra = diff_lines(lines)
        if sid in ("releases", "oss"):
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
            f'<div class="hb{" peak" if h == b["peak"] else ""}"><i class="bar" style="height:{max(4, round(100 * v / mx))}%"></i></div>'
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


def beat_timing(sid: str, html_: str, typed: str | None) -> dict:
    """Times, relative to the scene start, for the phases of one scene. Never two phases at once:
    type the command, stop; then the hero lands; then the supporting group; then hold."""
    t = LEAD if sid != "hook" else 0.0
    type_at = type_dur = 0.0
    if typed:
        type_at, type_dur = t, min(1.6, 0.3 + len(typed) / TYPE_CPS)
        t = type_at + type_dur + GAP
    t1 = t
    hero = HERO.get(sid, 1.2) if 'data-p="1"' in html_ or sid in ("shape", "close") else 0.0
    t2 = t1 + hero + (GAP if hero else 0)
    n2 = html_.count('data-p="2"')
    settle = t2 + (SUPPORT_RISE + STAGGER * (n2 - 1) if n2 else 0)
    hold = HOLD.get(sid, HOLD["default"])
    return {"type_at": round(type_at, 3), "type_dur": round(type_dur, 3), "t1": round(t1, 3),
            "t2": round(t2, 3), "settle": round(settle, 3), "duration": round(settle + hold + EXIT, 3)}


def plan_scenes(story: dict, direction: str) -> list[dict]:
    """The beats, plus chapter cards for direction B, each with its html and phase timing."""
    beats = story["beats"]
    scenes = []
    parts = [c for c in CHAPTERS if any(b["id"] in c[2] for b in beats)]
    for b in beats:
        if direction == "b":
            for k, (title, cmd, ids) in enumerate(parts):
                first = next(x for x in beats if x["id"] in ids)
                if first is b:
                    ch = {"part": k + 1, "parts": len(parts), "title": title,
                          "cmd": cmd.format(user=story["user"], year=story["year"])}
                    h = chapter_html(ch)
                    scenes.append({"key": f"ch{k + 1}", "id": "chapter", "html": h, "beat": None,
                                   **beat_timing("chapter", h, ch["cmd"])})
        h = scene_html(b, story, len(beats), direction)
        typed = b.get("cmd") if direction == "a" and b["id"] != "hook" else None
        scenes.append({"key": b["id"], "id": b["id"], "html": h, "beat": b, **beat_timing(b["id"], h, typed)})
    return scenes


def build(story: dict, out: Path, music: Path | None, cues: Path | None, direction: str = DIRECTION) -> Path:
    beats = story["beats"]
    for i, b in enumerate(beats):
        b["index"] = i + 1
        b.setdefault("cmd", COMMANDS[b["id"]].format(user=story["user"], year=story["year"]))
    scenes = plan_scenes(story, direction)
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
    html_scenes = "\n    ".join(
        f'<section id="s-{s["key"]}" class="clip scene" data-start="{s["start"]}" data-duration="{s["duration"]}" '
        f'data-track-index="1">{s["html"]}</section>' for s in scenes)
    keys = ("type_at", "type_dur", "t1", "t2", "start", "duration")
    timing = [{"key": s["key"], "id": s["id"], "beat": s["beat"]["index"] if s["beat"] else 0,
               **{k: s[k] for k in keys}} for s in scenes]
    tpl = (ASSETS / "template.html").read_text()
    page = (tpl.replace("__DURATION__", str(total_dur))
            .replace("__ROOT_CLASS__", "dir-" + direction)
            .replace("__HANDLE__", E("@" + story["user"]))
            .replace("__YEAR__", E(story["year_label"]))
            .replace("<!--__SCENES__-->", html_scenes)
            .replace("<!--__AUDIO__-->", audio)
            .replace("/*__TIMING__*/[]", json.dumps(timing)))
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
            .replace("/*__TIMING__*/[]", "[]"))
    (comp / "index.html").write_text(page)
    return comp / "index.html"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("year_json")
    p.add_argument("--out", required=True)
    p.add_argument("--story", help="edited story.json to build from instead of regenerating")
    p.add_argument("--music")
    p.add_argument("--cues", help="beat JSON (hyperframes beats --json output, or a beats array) to start scenes on the beat; detected from --music when omitted")
    p.add_argument("--cta", default=CTA)
    p.add_argument("--direction", choices=["a", "b"], default=DIRECTION)
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.story:
        story = json.loads(Path(a.story).read_text())  # copy edits stay; timing is re-derived
    else:
        story = make_story(json.loads(Path(a.year_json).read_text()), a.cta)
    page = build(story, out, Path(a.music) if a.music else None, Path(a.cues) if a.cues else None, a.direction)
    total = story["beats"][-1]["start"] + story["beats"][-1]["duration"]
    print(f"{len(story['beats'])} beats, {total:.1f}s -> {page}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
