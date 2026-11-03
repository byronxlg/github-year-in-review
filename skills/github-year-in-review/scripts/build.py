#!/usr/bin/env python3
"""Turn year.json into story.json and a HyperFrames composition.

    python3 build.py year.json --out <output-dir> [--story story.json] [--music track.mp3]
                     [--cues track.music-cues.json] [--cta "Make yours: ..."]

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
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"
CTA = "Make yours: github.com/byronxlg/github-year-in-review"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
MIN_DURATION = {"hook": 3.3, "shape": 6.2, "run": 4.4, "clock": 4.9, "work": 6.2, "ship": 4.8,
                "started": 5.4, "surprise": 5.4, "identity": 4.6, "close": 5.0}


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

    if auto_share > 0.25 and new < 6:
        noun, why_n = "Automator", f"{pct(auto_share)} of commits by your own automation"
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

    # 8 surprise
    auto = d["automation"]
    human_commits = t["commits"] - auto["commits"]
    if auto["commits"] >= 50:
        a = max(auto["repos"], key=lambda x: x["commits"])
        beats.append({
            "id": "surprise", "label": "One more thing",
            "number": auto["commits"], "unit": "commits were not you",
            "sub": (f"A scheduled job in {a['name'].split('/')[-1]}."
                    + (f" It made more commits than you did ({n(human_commits)})." if auto["commits"] > human_commits else "")),
        })
    elif r.get("busiest_day"):
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

    for i, b in enumerate(beats):
        b["index"] = i + 1
        b["duration"] = MIN_DURATION[b["id"]]
    return {"user": u["login"], "year": p["year"], "year_label": year_label, "calendar": d["calendar"],
            "beats": beats}


# --------------------------------------------------------------------------- timing


def snap_times(beats: list[dict], beat_grid: list[float]) -> None:
    """Start each beat on the nearest music beat at or after its natural start."""
    t = 0.0
    for b in beats:
        start = t
        if beat_grid and start > 0:
            near = min(beat_grid, key=lambda x: abs(x - start))
            if abs(near - start) < 0.3:
                start = near
        b["start"] = round(start, 3)
        t = start + b["duration"]
    for i, b in enumerate(beats):
        nxt = beats[i + 1]["start"] if i + 1 < len(beats) else b["start"] + b["duration"]
        b["duration"] = round(nxt - b["start"], 3)


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


def scene_html(b: dict, story: dict, total: int) -> str:
    i, sid = b["index"], b["id"]
    head = (f'<div class="label rise" data-at="0.05"><span class="idx">{i:02d}/{total:02d}</span>'
            f'<span>{E(b["label"])}</span></div>')
    body = ""
    if sid == "hook":
        num = n(b["number"])
        body = f"""
      <div class="stack hook">
        <div class="name rise" data-at="0.15">{E(b['name'])}</div>
        <div class="big signal count" data-to="{b['number']}" data-from="{round(b['number'] * 0.62)}" data-at="0" data-dur="1.6" style="font-size:{big_size(num, 540)}px">{num}</div>
        <div class="unit rise" data-at="0.3">{E(b['unit'])}</div>
        <div class="sub rise" data-at="0.9">{E(b['line'])}</div>
      </div>"""
    elif sid == "shape":
        body = f"""
      <div class="stack">
        <div class="title rise" data-at="0.1">{E(b['title'])}</div>
        {year_grid(story, b["peak_month"])}
        <div class="caption rise" data-at="2.5">{E(b['caption'])}</div>
      </div>"""
    elif sid in ("run", "ship", "surprise", "started"):
        num = n(b["number"])
        extra = ""
        if sid == "run":
            extra = '<div class="facts">' + "".join(
                f'<div class="fact rise" data-at="{1.6 + k * 0.5}"><b>{E(v)}</b><span>{E(lbl)}</span></div>'
                for k, (v, lbl) in enumerate(b["facts"])) + "</div>"
        if sid == "ship" and b.get("ext"):
            extra = f'<div class="note rise" data-at="1.5">{E(b["ext"])}</div>'
        if sid == "started":
            extra = '<div class="list">' + "".join(
                f'<div class="li rise" data-at="{1.3 + k * 0.45}"><div class="lin"><b>{E(x["name"])}</b>'
                f'<span>{E(x["meta"])}</span></div><div class="lid">{E(x["desc"])}</div></div>'
                for k, x in enumerate(b["rows"])) + "</div>"
        sub = f'<div class="sub rise" data-at="{0.9 if sid != "started" else 2.8}">{E(b["sub"])}</div>'
        size = big_size(num, 340 if sid == "started" else 500)
        body = f"""
      <div class="stack {sid}">
        <div class="big signal count" data-to="{b['number']}" data-from="0" data-at="0.15" data-dur="1.1" style="font-size:{size}px">{num}</div>
        <div class="unit rise" data-at="0.35">{E(b['unit'])}</div>
        {sub if sid != 'started' else ''}
        {extra}
        {sub if sid == 'started' else ''}
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
        <div class="big signal rise" data-at="0.15" style="font-size:240px">{E(b['peak_label'])}</div>
        <div class="unit rise" data-at="0.35">is when you commit most</div>
        <div class="hours">{bars}</div>
        <div class="ticks">{ticks}</div>
        <div class="sub rise" data-at="2.0">{E(b['sub'])}</div>
      </div>"""
    elif sid == "work":
        mx = max(x["commits"] for x in b["rows"]) or 1
        rows = "".join(
            f'<div class="wr rise" data-at="{0.5 + k * 0.4}"><div class="wl"><b>{E(x["name"])}</b>'
            f'<span>{n(x["commits"])} commits</span></div>'
            f'<div class="track"><i class="bar wbar" style="width:{max(2, 100 * x["commits"] / mx):.1f}%;background:{"#FF5B24" if k == 0 else "#5A5047"}"></i></div>'
            f'<div class="lang"><i style="background:{E(x["color"])}"></i>{E(x["language"] or "")}</div></div>'
            for k, x in enumerate(b["rows"]))
        lead = (f'<div class="quote rise" data-at="2.4"><span>{E(b["lead_name"])}:</span> {E(b["lead"])}</div>'
                if b["lead"] else "")
        body = f"""
      <div class="stack">
        <div class="title rise" data-at="0.1">The projects that took the time.</div>
        <div class="work">{rows}</div>
        {lead}
      </div>"""
    elif sid == "identity":
        body = f"""
      <div class="stack identity">
        <div class="kicker rise" data-at="0.2">You were</div>
        <div class="arch rise" data-at="0.45">{E(b['name'])}</div>
        <div class="sub rise" data-at="1.4">{E(b['reason'])}</div>
      </div>"""
    elif sid == "close":
        body = f"""
      <div class="stack close">
        {year_grid(story, None, "grid mini")}
        <div class="handle rise" data-at="0.5">{E(b['handle'])}</div>
        <div class="unit rise" data-at="0.4">{E(b['year'])}, in review.</div>
        <div class="cta rise" data-at="1.2"><span>{E(b['cta'].split(': ', 1)[0])}</span>{E(b['cta'].split(': ', 1)[-1])}</div>
      </div>"""
    return (f'<section id="s-{sid}" class="clip scene" data-start="{b["start"]}" data-duration="{b["duration"]}" '
            f'data-track-index="1"><div class="inner">{head}{body}</div></section>')


def build(story: dict, out: Path, music: Path | None, cues: Path | None) -> Path:
    beats = story["beats"]
    grid = []
    if cues and cues.exists():
        grid = json.loads(cues.read_text()).get("beats", [])
        grid = [x["time"] if isinstance(x, dict) else x for x in grid]
    snap_times(beats, grid)
    total_dur = round(beats[-1]["start"] + beats[-1]["duration"], 3)
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
    scenes = "\n    ".join(scene_html(b, story, len(beats)) for b in beats)
    timing = [{"id": b["id"], "start": b["start"], "duration": b["duration"]} for b in beats]
    tpl = (ASSETS / "template.html").read_text()
    page = (tpl.replace("__DURATION__", str(total_dur))
            .replace("__HANDLE__", E("@" + story["user"]))
            .replace("__YEAR__", E(story["year_label"]))
            .replace("<!--__SCENES__-->", scenes)
            .replace("<!--__AUDIO__-->", audio)
            .replace("/*__TIMING__*/[]", json.dumps(timing)))
    (comp / "index.html").write_text(page)
    (out / "story.json").write_text(json.dumps(story, indent=2))
    return comp / "index.html"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("year_json")
    p.add_argument("--out", required=True)
    p.add_argument("--story", help="edited story.json to build from instead of regenerating")
    p.add_argument("--music")
    p.add_argument("--cues", help="music cue JSON with a beats array, to start scenes on the beat")
    p.add_argument("--cta", default=CTA)
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(a.year_json).read_text())
    if a.story:
        story = json.loads(Path(a.story).read_text())
        for i, b in enumerate(story["beats"]):  # re-derive numbering and timing; copy edits stay
            b["index"] = i + 1
            b["duration"] = MIN_DURATION[b["id"]]
    else:
        story = make_story(data, a.cta)
    page = build(story, out, Path(a.music) if a.music else None, Path(a.cues) if a.cues else None)
    total = story["beats"][-1]["start"] + story["beats"][-1]["duration"]
    print(f"{len(story['beats'])} beats, {total:.1f}s -> {page}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
