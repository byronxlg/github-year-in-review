#!/usr/bin/env python3
"""The README's picture of the transition suite: a frame caught mid-transition per card, with the
card it leads into in the corner. Not part of the skill's build. Numbers stay out of the picture;
`build.py --transitions` lists them.

  suite_board.py <reel_dir> <cards_dir> <out.jpg>

reel_dir: `transition_reel.py suite` output, from a story holding every card, with reel.mp4 rendered
from its composition. A card missing from the story leaves its transition blank.
cards_dir: a build holding every card, story.json and `hyperframes snapshot` frames in shots/.
Needs ffmpeg and Google Chrome.
"""
from __future__ import annotations

import glob
import html
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "skills" / "github-year-in-review"
spec = importlib.util.spec_from_file_location("build", SKILL / "scripts" / "build.py")
B = importlib.util.module_from_spec(spec)
sys.modules["build"] = B
spec.loader.exec_module(B)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTH, COLS, PAD, GAP = 1640, 5, 48, 18
TILE_W = (WIDTH - 2 * PAD - (COLS - 1) * GAP) // COLS
TILE_H = TILE_W * 5 // 4 + 112  # the frame, then two lines of caption

# Seconds into each transition where its frame says the most.
AT = {4: .25, 42: .3, 46: .33, 49: .4, 50: .4, 51: .3, 47: .33, 52: .5, 53: .45, 54: .35, 55: .45, 56: .3, 57: .5, 59: .46, 60: .5,
      61: .4, 62: .35, 63: .3, 64: .5, 65: .25, 66: .3, 67: .4, 68: .42, 69: .25, 70: .5, 71: .42, 72: .3, 73: .42,
      75: .34, 76: .4}
CARD = {"shape": "Calendar", "yoy": "Year on year", "run": "Longest run", "clock": "Hours", "punchcard": "Busiest hour",
        "work": "Projects", "languages": "Languages", "agents": "Agents", "models": "Models", "ship": "PRs merged",
        "diff": "Biggest change", "lines": "Lines changed", "actions": "Machine time", "releases": "Releases",
        "started": "New repos", "oss": "Open source", "surprise": "Automation", "day": "Biggest day",
        "identity": "Identity", "close": "Close"}
HOW = {4: "A plain crossfade", 46: "A bar chart wipes across", 49: "The year, day by day", 53: "A streak snake eats the grid",
       54: "Heat ripples from the middle", 59: "A hunk header splits red and green", 60: "All red, then all green",
       62: "The months rise to full height", 64: "The language bar opens", 65: "The punchcard swells",
       66: "Git graph rails", 67: "A branch opens and merges", 68: "A git log rush", 69: "The merge button goes purple",
       70: "CI checks pass", 71: "A run spinner, tick, iris", 72: "An Actions job timeline", 73: "The handle's identicon",
       75: "A release tag sweeps", 76: "A star iris"}
SECOND = [(50, "Calendar", "The year, week by week"), (63, "Hours", "The year's sparkline floods"),
          (57, "Close", "The year's stats as one diff"), (61, "Lines changed", "Added against removed"),
          (47, "Biggest change", "Diff rows")]
NEUTRAL = [(42, "Left to right"), (56, "Heating up, level by level"), (55, "Tiles flip"), (52, "Grid rain"), (51, "GitHub green")]


def still(video: Path, at: float, out: Path) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(round(at, 3)), "-i", str(video), "-frames:v", "1", "-q:v", "2",
                    "-vf", f"crop=iw:iw*1.25:0:ih-iw*1.25,scale={TILE_W * 2}:-1", str(out)], check=True)


def main(reel: Path, cards: Path, out: Path) -> int:
    composition = (reel / "composition" / "index.html").read_text()
    flow = {f["n"]: f for f in json.loads(re.search(r"const FLOW = (\[.*?\]);", composition).group(1))}
    story = json.loads((cards / "story.json").read_text())
    shots = sorted(glob.glob(str(cards / "shots" / "frame-*")))
    work = Path(tempfile.mkdtemp(prefix="suite-board-"))
    for b, shot in zip(story["beats"], shots):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", shot, "-vf", f"scale={TILE_W}:-1", "-q:v", "2",
                        str(work / f"c-{b['id']}.jpg")], check=True)

    e = html.escape

    def tile(n: int, title: str, how: str, card: str | None = None) -> str:
        still(reel / "reel.mp4", flow[n]["T"] + AT[n], work / f"t{n}.jpg")
        inset = f'<img class="ins" src="c-{card}.jpg">' if card else ""
        return (f'<div class="t"><div class="im"><img src="t{n}.jpg">{inset}</div>'
                f'<div class="to">{e(title)}</div><div class="nm">{e(how)}</div></div>')

    own = "".join(tile(ns[0], CARD[c], HOW[ns[0]], c) for c, ns in B.PAIRS.items())
    second = "".join(tile(n, title, how) for n, title, how in SECOND)
    neutral = "".join(tile(n, "Contribution grid", how) for n, how in NEUTRAL)
    fonts = SKILL / "assets" / "fonts"
    rows = (len(B.PAIRS) + COLS - 1) // COLS + 2
    height = 2 * PAD + 210 + 3 * 130 + rows * (TILE_H + 26)
    (work / "board.html").write_text(f"""<!doctype html><meta charset=utf-8><style>
@font-face{{font-family:Br;src:url(file://{fonts}/BricolageGrotesque.ttf);font-weight:200 800;font-stretch:75% 100%}}
@font-face{{font-family:JB;src:url(file://{fonts}/JetBrainsMono.ttf);font-weight:100 800}}
*{{box-sizing:border-box}}html,body{{margin:0;background:#14120f}}
body{{width:{WIDTH}px;color:#f3eee4;font-family:JB;padding:{PAD}px}}
h1{{font:800 104px/1 Br;font-stretch:75%;margin:0 0 20px}}h1 i{{color:#ff5b24;font-style:normal}}
.lede{{font-size:32px;color:#a39b8e;margin:0 0 56px;line-height:1.35}}
h2{{font:800 56px/1 Br;font-stretch:75%;margin:44px 0 8px}}.s{{font-size:27px;color:#a39b8e;margin:0 0 24px}}
.g{{display:grid;grid-template-columns:repeat({COLS},{TILE_W}px);gap:26px {GAP}px}}.t{{height:{TILE_H}px}}
.im{{position:relative;aspect-ratio:4/5;overflow:hidden;background:#000;outline:1px solid #2e2a25}}
.im>img:first-child{{width:100%;display:block}}.ins{{position:absolute;right:8px;bottom:8px;width:37%;outline:3px solid #f3eee4;display:block}}
.to{{font:800 36px/1.1 Br;font-stretch:75%;margin-top:10px}}.nm{{font-size:21px;color:#a39b8e;margin-top:4px;line-height:1.25}}
</style>
<h1>A transition for <i>every card.</i></h1>
<p class=lede>Each frame is caught mid-transition. The inset is the card it leads into.</p>
<h2>Each card's own</h2><p class=s>What it does says something about the stat that follows.</p><div class=g>{own}</div>
<h2>Second choices</h2><p class=s>Swap one in for a card.</p><div class=g>{second}</div>
<h2>Neutral</h2><p class=s>Contribution squares, no stat, for a card whose own has gone.</p><div class=g>{neutral}</div>""")
    png = work / "board.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--allow-file-access-from-files", "--hide-scrollbars",
                    "--force-device-scale-factor=1", f"--screenshot={png}", f"--window-size={WIDTH},{height}",
                    "--virtual-time-budget=4000", f"file://{work}/board.html"], check=False, capture_output=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(png), "-q:v", "4", str(out)], check=True)
    print(f"{out} {out.stat().st_size // 1024} KB, {work}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
