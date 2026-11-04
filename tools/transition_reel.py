#!/usr/bin/env python3
"""Picker reels for the film's motion. Not part of the skill's build; a tool to choose with.

  transition_reel.py transitions <story.json> <out> [first]   assets/transitions.js, numbered, from number `first`
  transition_reel.py suite <story.json> <out>         only the suite the film picks from (build.py:SUITE)
  transition_reel.py pace <story.json> <out>          the same four beats at each pace, lettered

The film's own scenes in the film's own CSS, in a frame with a strip above it holding the number,
so nothing a transition does can cover the label. Render <out>/composition with hyperframes.
"""
from __future__ import annotations

import html
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "skills" / "github-year-in-review"
spec = importlib.util.spec_from_file_location("build", SKILL / "scripts" / "build.py")
B = importlib.util.module_from_spec(spec)
sys.modules["build"] = B
spec.loader.exec_module(B)

STRIP = 150  # px above the 1350 film frame
REEL_HOLD = 1.0  # settled seconds before each transition, so the outgoing frame is seen at rest
LABEL_LEAD = 0.85  # the number changes this long before its transition

B.PACES["reel"] = {"chapters": False, "speed": 0.7, "hold": 0.4, "fade_in": 0, "fade_out": 0, "lead": 0.05,
                   "gap": 0.12, "exit": 0.0, "est": 0.5}
PACE_OPTIONS = [
    ("A", "tight", "The tight test", 0.6, 2.5 / 3, 0.08, 0.12),
    ("B", "pace_b", "A little slower", 0.75, 2.9 / 3, 0.12, 0.18),
    ("C", "pace_c", "Medium", 0.85, 3.3 / 3, 0.18, 0.22),
    ("D", "pace_d", "Calm motion, no cards", 1.0, 1.0, B.LEAD, B.GAP),
]
for _, key, _, speed, hold, lead, gap in PACE_OPTIONS:
    if key != "tight":
        B.PACES[key] = {"chapters": False, "speed": speed, "hold": hold, "fade_in": 0.1, "fade_out": 0, "lead": lead,
                        "gap": gap, "exit": 0.0, "est": 0.7}


def page(tpl: str, film: str, badges: str, timing: list, total: float, js_body: str) -> str:
    head, _, rest = tpl.partition("<body>")
    head = head.replace("#root", "#film").replace('height=1350', f'height={1350 + STRIP}')
    # the loop that plays each scene's entrance, without its fades or its hold on the rail
    script = rest[rest.index("<script>") + len("<script>"):rest.index("</script>")]
    script = re.sub(r"\n\s*if \(si > 0 && PACE\.fadeIn > 0\) tl\.fromTo\(inner.*", "", script)
    script = re.sub(r"\n\s*if \(si < TIMING\.length - 1 && PACE\.fadeOut.*", "", script)
    script = re.sub(r"\n\s*if \(s\.id === \"close\"\) tl\.to\(\"#rail\".*", "", script)
    script = script.replace("/*__TIMING__*/[]", json.dumps(timing))
    script = script.replace("/*__PACE__*/{ speed: 1, fadeIn: 0.3, fadeOut: 0.35 }", json.dumps({"speed": js_speed(timing)}))
    script = script.replace('window.__timelines["main"] = tl;', js_body + '\n      window.__timelines["main"] = tl;')
    return head + f"""<body>
    <style>
      html, body {{ width: 1080px; height: {1350 + STRIP}px; overflow: hidden; background: #0b0a08; }}
      #root {{ position: relative; width: 1080px; height: {1350 + STRIP}px; overflow: hidden; background: #0b0a08; }}
      #film {{ position: absolute !important; left: 0; top: {STRIP}px; width: 1080px !important; height: 1350px !important; }}
      .tw {{ position: absolute; inset: 0; background: var(--ground); }}
      #rail {{ z-index: 4000; }}
      .badge {{ position: absolute; left: 0; top: 0; width: 1080px; height: {STRIP}px; display: flex; align-items: center;
                gap: 34px; padding: 0 44px; box-sizing: border-box; color: var(--ink); background: #0b0a08; }}
      .badge b {{ font: 800 112px "Bricolage", sans-serif; font-stretch: 75%; color: var(--signal); line-height: 1; min-width: 130px; }}
      .badge .n {{ font: 600 37px "JBMono", monospace; line-height: 1.15; }}
      .badge .m {{ font: 400 29px "JBMono", monospace; color: var(--muted); margin-top: 6px; }}
    </style>
    <div id="root" data-composition-id="main" data-start="0" data-width="1080" data-height="{1350 + STRIP}" data-duration="{total}">
      <div id="film" class="dir-b">
        {film}
        <div id="rail" class="clip" data-start="0" data-duration="{total}" data-track-index="2">
          <div class="meta"><b>__HANDLE__</b><span>__YEAR__</span></div>
        </div>
      </div>
      {badges}
    </div>
    <script>{script}</script>
  </body>
</html>
"""


def js_speed(timing: list) -> float:
    return timing[0].get("speed", 0.7)


def badge(mark: str, name: str, meta: str, start: float, dur: float) -> str:
    return (f'<div class="clip badge" data-start="{round(start, 3)}" data-duration="{round(dur, 3)}" data-track-index="4">'
            f'<b>{html.escape(mark)}</b><div><div class="n">{html.escape(name)}</div><div class="m">{html.escape(meta)}</div></div></div>')


def scene_markup(key: str, h: str, start: float, dur: float, track: int, z: int) -> str:
    return (f'<section id="s-{key}" class="clip scene" data-start="{round(start, 3)}" data-duration="{round(dur, 3)}" '
            f'data-track-index="{track}" style="z-index:{z}"><div class="tw">{h}</div></section>')


def prepared(story: dict) -> dict:
    for i, b in enumerate(story["beats"]):
        b["index"] = i + 1
        b.setdefault("cmd", B.COMMANDS[b["id"]].format(user=story["user"], year=story["year"]))
    return story


def finish(story: dict, out: Path, page_html: str) -> None:
    page_html = page_html.replace("__HANDLE__", html.escape("@" + story["user"])).replace("__YEAR__", html.escape(story["year_label"]))
    comp = out / "composition"
    (comp / "assets" / "fonts").mkdir(parents=True, exist_ok=True)
    for f in (B.ASSETS / "fonts").glob("*.ttf"):
        shutil.copy(f, comp / "assets" / "fonts" / f.name)
    (comp / "index.html").write_text(page_html)


def transitions_reel(story: dict, out: Path, first: int = 1, only: list[int] | None = None) -> None:
    meta = B.transition_list()
    (out).mkdir(parents=True, exist_ok=True)
    (out / "list.json").write_text(json.dumps(meta, indent=1))
    meta = [m for m in meta if m["n"] in only] if only else meta[first - 1:]
    base = B.plan_scenes(story, "b", "reel")
    n = len(meta)
    scenes, film, badges, timing = [], [], [], []
    enter = 0.0
    z = 1000
    for i in range(n + 1):
        s = base[i % len(base)]
        settle = s["settle"]
        key = f'{s["id"]}-{i}'
        prev = meta[i - 1] if i else None
        clip_start = enter - (prev["d"] * 0.6 if prev else 0)
        leave = enter + settle + REEL_HOLD + (0.6 if i == n else 0)
        d = meta[i]["d"] if i < n else 0
        if prev:
            z += -1 if prev["aTop"] else 1
        film.append(scene_markup(key, s["html"], clip_start, leave + d - clip_start, 1 + 2 * (i % 2), z))
        timing.append({"key": key, "id": s["id"], "beat": s["beat"]["index"], "speed": 0.7,
                       **{k: s[k] for k in ("type_at", "type_dur", "t1", "t2")}, "start": round(enter, 3), "duration": round(leave - enter, 3)})
        scenes.append({"T": leave, "d": d})
        if i < n:
            b_start = leave - LABEL_LEAD if i else 0.0
            next_settle = base[(i + 1) % len(base)]["settle"]
            b_end = leave + d * 0.6 + next_settle + REEL_HOLD - LABEL_LEAD
            if i + 1 == n:
                b_end += 0.6 + LABEL_LEAD
            meta_line = "no transition time" if d == 0 else f"{d:g} s"
            badges.append(badge(str(meta[i]["n"]), meta[i]["name"], meta_line, b_start, b_end - b_start))
        enter = leave + d * 0.6
    total = round(scenes[-1]["T"], 3)
    runner = B.cut_runner(B.cut_data(story), [{"T": round(x["T"], 3), "k": i, "n": meta[i]["n"]} for i, x in enumerate(scenes[:-1])])
    finish(story, out, page((B.ASSETS / "template.html").read_text(), "\n".join(film), "\n".join(badges), timing, total, runner))
    print(f"{n} transitions, {total} s")


def pace_reel(story: dict, out: Path, ids=("work", "languages", "agents", "models")) -> None:
    film, badges, timing = [], [], []
    t = 0.0
    whole = {}
    for mark, key, name, speed, hold, lead, gap in PACE_OPTIONS:
        whole[mark] = sum(s["duration"] for s in B.plan_scenes(story, "b", key))
        sel = [s for s in B.plan_scenes(story, "b", key) if s["id"] in ids]
        start = t
        for s in sel:
            k = f'{mark}-{s["id"]}'
            film.append(scene_markup(k, s["html"], t, s["duration"], 1, 1000))
            timing.append({"key": k, "id": s["id"], "beat": s["beat"]["index"], "speed": speed,
                           **{x: s[x] for x in ("type_at", "type_dur", "t1", "t2")}, "start": round(t, 3), "duration": s["duration"]})
            t = round(t + s["duration"], 3)
        badges.append(badge(mark, name, f"holds {hold * 3:.1f} s, motion {speed:g}x, 17 beats = {whole[mark]:.0f} s", start, t - start))
    # per-scene speed: the template's single PACE.speed is replaced by the scene's own
    tpl = (B.ASSETS / "template.html").read_text().replace("const d = (x) => x * PACE.speed;", "let d = (x) => x * PACE.speed;")
    tpl = tpl.replace("TIMING.forEach((s, si) => {", "TIMING.forEach((s, si) => {\n        d = (x) => x * s.speed;")
    finish(story, out, page(tpl, "\n".join(film), "\n".join(badges), timing, t, ""))
    (out / "whole.json").write_text(json.dumps(whole, indent=1))
    print(whole, t)


if __name__ == "__main__":
    mode, story_path, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    story = prepared(json.loads(story_path.read_text()))
    if mode == "suite":
        transitions_reel(story, out, only=B.SUITE)
    else:
        {"transitions": transitions_reel, "pace": pace_reel}[mode](story, out, *map(int, sys.argv[4:]))
