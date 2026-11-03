"""Thumbnail options board: renders each option as a 1080x1350 PNG from the example story.

Usage: python3 docs/thumbnail-board/make.py   (needs Google Chrome; writes docs/thumbnail-board/*.png)
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STORY = json.loads((ROOT / "examples/byronxlg-2026.story.json").read_text())
FONTS = (ROOT / "skills/github-year-in-review/assets/fonts").as_uri()
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
B = {b["id"]: b for b in STORY["beats"]}

CSS = f"""
@font-face {{ font-family: Bric; src: url("{FONTS}/BricolageGrotesque.ttf"); font-weight: 200 800; font-stretch: 75% 100%; }}
@font-face {{ font-family: Mono; src: url("{FONTS}/JetBrainsMono.ttf"); font-weight: 100 800; }}
:root {{ --ground:#14120f; --ink:#f3eee4; --muted:#a39b8e; --rule:#2a2622; --signal:#ff5b24;
  --l1:#6a3a22; --l2:#a3431f; --l3:#d9501f; --l4:#ff5b24; --add:#8fd694; }}
* {{ box-sizing: border-box; }}
html, body {{ margin:0; width:1080px; height:1350px; overflow:hidden; }}
body {{ background:var(--ground); color:var(--ink); font-family:Mono, monospace; }}
.f {{ position:absolute; inset:0; padding:96px 84px; display:flex; flex-direction:column; background:var(--ground); color:var(--ink); }}
.disp {{ font-family:Bric; font-weight:800; font-stretch:75%; line-height:.86; letter-spacing:-.02em; }}
.k {{ font-size:30px; color:var(--muted); letter-spacing:.02em; }}
.sp {{ flex:1; }}
.grid {{ display:flex; flex-direction:column; gap:6px; }}
.mrow {{ display:flex; gap:6px; }}
.c {{ flex:1; aspect-ratio:1; border-radius:4px; background:var(--rule); }}
.c.x {{ background:transparent; }} .c.f {{ background:transparent; box-shadow:inset 0 0 0 2px #221f1b; }}
.c.l1 {{ background:var(--l1); }} .c.l2 {{ background:var(--l2); }} .c.l3 {{ background:var(--l3); }} .c.l4 {{ background:var(--l4); }}
.light {{ --ground:#f3eee4; --ink:#14120f; --muted:#6b6358; --rule:#e2dacb; --l1:#f2b99a; --l2:#ec8a5a; --l3:#e5642d; --l4:#d9481a; }}
.light .c.f {{ box-shadow:inset 0 0 0 2px #e2dacb; }}
.orange {{ --ground:#ff5b24; --ink:#14120f; --muted:#3a1a0c; --rule:#ff7a4d; --l1:#e0471a; --l2:#b8360f; --l3:#7a2208; --l4:#14120f; }}
.orange .c.f {{ box-shadow:inset 0 0 0 2px #ff7a4d; }}
"""


def grid(cls="grid"):
    cal = {d: c for d, c in STORY["calendar"]}
    nz = sorted(c for c in cal.values() if c > 0)
    q = [nz[int(len(nz) * f)] for f in (0.25, 0.5, 0.75)]
    rows = []
    for m in range(12):
        cells = []
        for day in range(1, 32):
            try:
                date = dt.date(STORY["year"], m + 1, day).isoformat()
            except ValueError:
                cells.append('<i class="c x"></i>')
                continue
            c = cal.get(date)
            lvl = "f" if c is None else "0" if c == 0 else str(1 + sum(c > k for k in q))
            cells.append(f'<i class="c l{lvl}"></i>')
        rows.append(f'<div class="mrow">{"".join(cells)}</div>')
    return f'<div class="{cls}">{"".join(rows)}</div>'


def months():
    tot = [0] * 12
    for d, c in STORY["calendar"]:
        tot[int(d[5:7]) - 1] += c
    return tot


H = B["close"]["handle"]
HOOK, RUN, AG, SHIP, REL, NEW, ID = (B[k] for k in ("hook", "run", "agents", "ship", "releases", "started", "identity"))

OPTIONS = {
    # what to show (house style, dark ground)
    "a1-current": f"""<div class="f"><div class="sp"></div>{grid()}<div style="height:90px"></div>
      <div class="disp" style="font-size:150px">{H}</div>
      <div class="disp" style="font-size:72px;font-weight:600;margin-top:26px">2026 so far, in review.</div><div class="sp"></div></div>""",
    "a2-big-number": f"""<div class="f"><div class="k">{H} / GitHub, 2026 so far</div><div class="sp"></div>
      <div class="disp" style="font-size:330px;color:var(--signal)">{HOOK['number']:,}</div>
      <div class="disp" style="font-size:96px;margin-top:20px">contributions.</div>
      <div class="k" style="margin-top:36px;font-size:34px;color:var(--ink)">18 repos. 119 active days.</div>
      <div class="sp"></div>{grid()}</div>""",
    "a3-identity": f"""<div class="f"><div class="k">{H} / 2026 so far, in one line</div><div class="sp"></div>
      <div class="disp" style="font-size:190px">The<br>Weekend<br><span style="color:var(--signal)">Orches&shy;trator</span></div>
      <div class="k" style="margin-top:56px;font-size:36px;color:var(--ink);line-height:1.4">57% of commits shipped with agents.<br>38% on weekends.</div><div class="sp"></div></div>""",
    "a4-streak": f"""<div class="f"><div class="k">{H} / the longest run</div><div class="sp"></div>
      <div class="disp" style="font-size:400px;color:var(--signal)">44</div>
      <div class="disp" style="font-size:110px;margin-top:10px">days in a row.</div>
      <div style="display:grid;grid-template-columns:repeat(11,1fr);gap:10px;margin-top:64px">{'<i class="c l4"></i>' * 44}</div>
      <div class="k" style="margin-top:36px">Sep 21 to Nov 3, and still going</div><div class="sp"></div></div>""",
    "a5-with-claude": f"""<div class="f"><div class="k">{H} / shipped with a team</div><div class="sp"></div>
      <div class="disp" style="font-size:380px;color:var(--signal)">57%</div>
      <div class="disp" style="font-size:96px;margin-top:20px">of my commits were<br>co-written with Claude.</div>
      <div class="k" style="margin-top:44px;font-size:34px;color:var(--ink)">330 pull requests opened with Claude Code.</div><div class="sp"></div></div>""",
    "a6-shipped": f"""<div class="f"><div class="k">{H} / what landed in 2026</div><div class="sp"></div>
      {''.join(f'<div style="display:flex;align-items:baseline;gap:32px;border-top:2px solid var(--rule);padding:30px 0"><div class="disp" style="font-size:190px;color:var(--signal);min-width:540px">{n}</div><div class="disp" style="font-size:64px;font-weight:600">{u}</div></div>' for n, u in (("1,191", "PRs<br>merged"), ("44", "releases<br>tagged"), ("30", "new<br>repos")))}
      <div class="sp"></div></div>""",
    "a7-terminal": f"""<div class="f"><div class="sp"></div>
      <div style="border:2px solid #3a352f;border-radius:22px;overflow:hidden;background:#0d0c0a">
        <div style="display:flex;gap:14px;padding:24px 28px;border-bottom:2px solid #2a2622">{'<i style="width:22px;height:22px;border-radius:50%;background:#3a352f"></i>' * 3}</div>
        <div style="padding:44px 40px;font-size:34px;line-height:1.75">
          <div><span style="color:var(--add);font-weight:700">$</span> year-in-review --user byronxlg</div>
          <div style="color:var(--muted)">contributions <span style="color:var(--ink)">4,996</span></div>
          <div style="color:var(--muted)">longest run &nbsp;&nbsp;<span style="color:var(--ink)">44 days</span></div>
          <div style="color:var(--muted)">with Claude &nbsp;&nbsp;<span style="color:var(--ink)">57%</span></div>
          <div style="color:var(--muted)">PRs merged &nbsp;&nbsp;&nbsp;<span style="color:var(--ink)">1,191</span></div>
          <div><span style="color:var(--add);font-weight:700">$</span> <span style="background:var(--ink);color:var(--ground)">&nbsp;</span></div>
        </div></div>
      <div class="disp" style="font-size:110px;margin-top:80px">2026, in review.</div><div class="sp"></div></div>""",
    "a8-october": (lambda t: f"""<div class="f"><div class="k">{H} / the shape of the year</div><div class="sp"></div>
      <div class="disp" style="font-size:150px">October alone:<br><span style="color:var(--signal)">55%</span> of the year.</div>
      <div style="display:flex;align-items:flex-end;gap:14px;height:520px;margin-top:80px">{''.join(f'<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:12px;height:100%"><div style="width:100%;height:{max(6, 470 * v / max(t))}px;border-radius:6px;background:{"var(--signal)" if i == 9 else "var(--l1)" if v else "var(--rule)"}"></div><span class="k" style="font-size:22px">{"JFMAMJJASOND"[i]}</span></div>' for i, v in enumerate(t))}</div>
      <div class="sp"></div></div>""")(months()),
    # how to present (the current content, restyled)
    "b1-light": f"""<div class="f light"><div class="sp"></div>{grid()}<div style="height:90px"></div>
      <div class="disp" style="font-size:150px">{H}</div>
      <div class="disp" style="font-size:72px;font-weight:600;margin-top:26px">2026 so far, in review.</div><div class="sp"></div></div>""",
    "b2-orange": f"""<div class="f orange"><div class="sp"></div>{grid()}<div style="height:90px"></div>
      <div class="disp" style="font-size:150px">{H}</div>
      <div class="disp" style="font-size:72px;font-weight:600;margin-top:26px">2026 so far, in review.</div><div class="sp"></div></div>""",
    "b3-full-bleed": f"""<div style="position:absolute;left:-200px;right:-200px;top:40px;transform:rotate(-8deg) scale(1.15);transform-origin:center top">{grid()}</div>
      <div style="position:absolute;left:0;right:0;bottom:0;padding:70px 84px 96px;background:linear-gradient(transparent,var(--ground) 30%)">
      <div class="disp" style="font-size:150px">{H}</div>
      <div class="disp" style="font-size:72px;font-weight:600;margin-top:26px">2026 so far, in review.</div></div>""",
    "b4-type-only": f"""<div class="f"><div class="k">{H}</div><div class="sp"></div>
      <div class="disp" style="font-size:560px;color:var(--signal);margin-left:-14px">2026</div>
      <div class="disp" style="font-size:120px;margin-top:10px">so far,<br>in review.</div><div class="sp"></div>
      <div class="k">4,996 contributions / 44-day run / 57% with Claude</div></div>""",
    "b5-split": f"""<div class="f" style="padding-bottom:0"><div class="k">{H} / GitHub, 2026 so far</div>
      <div class="disp" style="font-size:300px;color:var(--signal);margin-top:60px">4,996</div>
      <div class="disp" style="font-size:84px">contributions, in review.</div><div class="sp"></div></div>
      <div style="position:absolute;left:0;right:0;bottom:0;height:560px;background:#0d0c0a;border-top:2px solid var(--rule);padding:60px 84px">{grid()}</div>""",
    "b6-avatar": f"""<div class="f"><div style="display:flex;align-items:center;gap:40px"><img src="https://github.com/byronxlg.png?size=400" style="width:220px;height:220px;border-radius:50%;border:6px solid var(--signal)">
      <div><div class="disp" style="font-size:96px">Byron Smith</div><div class="k" style="margin-top:12px">{H}</div></div></div>
      <div class="sp"></div>{grid()}<div class="sp"></div>
      <div class="disp" style="font-size:110px">2026 so far,<br>in review.</div></div>""",
}


def main(only=None):
    for name, body in OPTIONS.items():
        if only and name not in only:
            continue
        html = HERE / f".{name}.html"
        html.write_text(f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}</body></html>')
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--virtual-time-budget=4000", "--window-size=1080,1350", f"--screenshot={HERE / (name + '.png')}",
                        html.as_uri()], check=True, capture_output=True)
        html.unlink()
        print(name)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
