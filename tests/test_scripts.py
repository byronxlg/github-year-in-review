"""Offline tests for the collector helpers and the story builder. No network, no gh."""

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "github-year-in-review" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build  # noqa: E402
import collect  # noqa: E402


def year_fixture(**over) -> dict:
    """A small, quiet year: the shape a light GitHub user produces."""
    days = []
    d = dt.date(2025, 1, 1)
    while d.year == 2025:
        days.append([d.isoformat(), 3 if d.day in (1, 2, 3, 15) and d.month in (3, 4) else 0])
        d += dt.timedelta(days=1)
    data = {
        "user": {"login": "quiet", "name": "Quiet Dev", "years_on_github": 3},
        "period": {"year": 2025, "from": "2025-01-01", "to": "2025-12-31", "partial": False},
        "totals": {"contributions": 24, "commits": 20, "prs": 2, "reviews": 0, "issues": 2},
        "calendar": days,
        "rhythm": {
            "active_days": 8, "weekend_share": 0.25,
            "streak": {"longest": 3, "start": "2025-03-01", "end": "2025-03-03", "current": 0},
            "busiest_day": {"date": "2025-03-01", "count": 3},
            "by_month": [0, 0, 12, 12] + [0] * 8,
            "peak_hour": None, "by_hour": [0] * 24, "night_share": 0, "morning_share": 0,
            "latest_night_commit": None, "commits_sampled": 0, "by_weekday_sampled": [0] * 7,
        },
        "automation": {"repos": [], "commits": 0},
        "repos": [],
        "repo_count": 0,
        "languages": [],
        "pull_requests": {"opened": 2, "merged": 1, "merge_rate": 0.5, "external_merged": 0,
                          "external_repos": [], "external_public": [], "most_starred_external": None},
        "new_repos": [],
        "new_private_repos": 0,
        "stars": {"gained": 0, "by_repo": [], "total_owned": 0},
    }
    data.update(over)
    return data


class CollectHelpers(unittest.TestCase):
    def test_streaks(self):
        days = [{"date": f"2025-01-{i:02d}", "contributionCount": c} for i, c in
                enumerate([1, 1, 0, 2, 2, 2, 0, 1], start=1)]
        s = collect.streaks(days)
        self.assertEqual((s["longest"], s["start"], s["end"], s["current"]), (3, "2025-01-04", "2025-01-06", 1))

    def test_template_share_flags_cron(self):
        bot = [{"messageHeadline": f"fleet page: registry changed {i}"} for i in range(80)]
        human = [{"messageHeadline": m} for m in ("add login", "fix typo", "bump deps", "refactor api")] * 20
        self.assertEqual(collect.template_share(bot), 1.0)
        self.assertLess(collect.template_share(human), 0.6)

    def test_commit_verb_skips_conventional_prefix(self):
        self.assertEqual(collect.commit_verb("feat(api): add pagination"), "add")
        self.assertEqual(collect.commit_verb("Fix the thing"), "fix")


class AgentDetection(unittest.TestCase):
    def test_trailers_and_footers(self):
        c = collect.classify_commit("fix login\n\nCo-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>")
        self.assertEqual(c["agents"], ["Claude"])
        self.assertEqual(c["models"], ["Claude Opus 4.5"])
        self.assertEqual(collect.classify_commit("x\n\nCo-authored-by: Copilot <175728472+Copilot@users.noreply.github.com>")["agents"], ["Copilot"])
        self.assertEqual(collect.classify_commit("aider: refactor parser")["agents"], ["Aider"])
        self.assertEqual(collect.classify_commit("x\n\nCo-authored-by: Cursor Agent <cursoragent@cursor.com>")["agents"], ["Cursor"])

    def test_bot_authors(self):
        self.assertEqual(collect.classify_commit("Initial plan", "copilot-swe-agent[bot]")["agents"], ["Copilot"])
        self.assertEqual(collect.classify_commit("wip", "devin-ai-integration[bot]")["agents"], ["Devin"])
        dep = collect.classify_commit("Bump lodash from 4.17.20 to 4.17.21", "dependabot[bot]")
        self.assertEqual((dep["agents"], dep["bot"]), ([], "dependabot"))

    def test_mentions_are_not_agent_work(self):
        for msg in ("fix the codex runner", "docs: how to use Claude", "copilot settings page"):
            c = collect.classify_commit(msg, "someone")
            self.assertEqual((c["agents"], c["bot"]), ([], None), msg)

    def test_branch_prefixes(self):
        self.assertEqual(collect.classify_branch("claude/fix-login-abc"), "Claude Code")
        self.assertEqual(collect.classify_branch("codex/add-tests"), "Codex")
        self.assertEqual(collect.classify_branch("copilot/fix-12"), "Copilot coding agent")
        for ref in ("main", "claude", "claude/", "feature/claude", "", None):
            self.assertIsNone(collect.classify_branch(ref), ref)

    def test_agent_prs_take_the_larger_signal(self):
        prs = [{"headRefName": "claude/a"}, {"headRefName": "claude/b"}, {"headRefName": "codex/c"},
               {"headRefName": "main"}]
        got = collect.merge_agent_prs({"Claude Code": 5, "Devin": 1}, prs)
        self.assertEqual(got, [("Claude Code", 5), ("Codex", 1), ("Devin", 1)])
        self.assertEqual(collect.merge_agent_prs({}, []), [])

    def test_month_ranges(self):
        r = collect.month_ranges(dt.date(2026, 11, 15), dt.date(2027, 1, 3))
        self.assertEqual(r, [(dt.date(2026, 11, 15), dt.date(2026, 11, 30)),
                             (dt.date(2026, 12, 1), dt.date(2026, 12, 31)),
                             (dt.date(2027, 1, 1), dt.date(2027, 1, 3))])


def agents_block(share=0.6, sampled=300, est=600):
    return {"agent_commits_sampled": sampled, "agent_share": share, "agent_commits_est": est,
            "by_agent": [["Claude", est - 50], ["Codex", 50]],
            "by_agent_sampled": [["Claude", sampled - 20], ["Codex", 20]],
            "models": [], "by_month": [], "prs": [["Claude Code", 40]], "prs_total": 40}


class Story(unittest.TestCase):
    def test_quiet_year_drops_thin_beats(self):
        story = build.make_story(year_fixture(), build.CTA)
        ids = [b["id"] for b in story["beats"]]
        self.assertEqual(ids[0], "hook")
        self.assertEqual(ids[-2:], ["identity", "close"])
        for dropped in ("clock", "work", "ship", "started"):
            self.assertNotIn(dropped, ids)
        self.assertIn("so far", build.make_story(year_fixture(period={
            "year": 2025, "from": "2025-01-01", "to": "2025-06-01", "partial": True}), build.CTA)["year_label"])

    def test_archetype_automation_and_builder(self):
        d = year_fixture(automation={"repos": [{"name": "me/site", "commits": 900}], "commits": 900})
        d["totals"]["commits"] = 1000
        self.assertTrue(build.archetype(d)["name"].endswith("Automator"))
        d["new_repos"] = [{"name": f"r{i}", "stars": 0, "description": None, "language": None} for i in range(7)]
        self.assertTrue(build.archetype(d)["name"].endswith("Builder"))

    def test_agents_beat_only_with_signed_commits(self):
        ids = lambda d: [b["id"] for b in build.make_story(d, build.CTA)["beats"]]
        self.assertNotIn("agents", ids(year_fixture()))
        self.assertNotIn("agents", ids(year_fixture(agents=agents_block(share=0.02, sampled=4, est=8))))
        story = build.make_story(year_fixture(agents=agents_block()), build.CTA)
        beat = next(b for b in story["beats"] if b["id"] == "agents")
        self.assertEqual(beat["number"], 60)
        self.assertIn("Claude and Codex", beat["unit"])
        self.assertIn("40 pull requests", beat["sub"])

    def test_orchestrator_archetype(self):
        d = year_fixture(agents=agents_block())
        self.assertTrue(build.archetype(d)["name"].endswith("Orchestrator"))

    def test_diff_and_releases_drop_on_thin_data(self):
        pr = dict(year_fixture()["pull_requests"], biggest={"repo": "me/app", "title": "Tiny fix", "additions": 3,
                  "deletions": 1, "files": 1, "number": 2})
        ids = [b["id"] for b in build.make_story(year_fixture(pull_requests=pr, releases={"total": 1, "repos": []}),
                                                  build.CTA)["beats"]]
        self.assertNotIn("diff", ids)
        self.assertNotIn("releases", ids)
        pr["biggest"].update(additions=4000, deletions=900)
        rel = {"total": 5, "repos": [{"repo": "app", "count": 5, "first": "v0.1.0", "latest": "v1.0.0",
                                      "latest_date": "2025-09-01"}]}
        ids = [b["id"] for b in build.make_story(year_fixture(pull_requests=pr, releases=rel), build.CTA)["beats"]]
        self.assertIn("diff", ids)
        self.assertIn("releases", ids)

    def test_fit_length_caps_the_film(self):
        beats = [{"id": i} for i in ("hook", "shape", "run", "clock", "work", "agents", "ship", "diff",
                                     "releases", "started", "oss", "surprise", "identity", "close")]
        build.fit_length(beats)
        self.assertLessEqual(sum(b["duration"] for b in beats), build.MAX_TOTAL)
        ids = [b["id"] for b in beats]
        self.assertEqual((ids[0], ids[-1]), ("hook", "close"))
        self.assertIn("agents", ids)
        self.assertEqual([b["index"] for b in beats], list(range(1, len(beats) + 1)))

    def test_clause(self):
        self.assertEqual(build.clause("Twenty days of an unattended SDLC: Claude supervises"),
                         "Twenty days of an unattended SDLC")
        self.assertEqual(build.clause("Fast, keyboard-driven client"), "Fast, keyboard-driven client")

    def test_build_writes_composition_and_rebuilds_from_story(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            story = build.make_story(year_fixture(), build.CTA)
            page = build.build(story, out, None, None)
            html = page.read_text()
            self.assertIn('data-composition-id="main"', html)
            self.assertNotIn("__DURATION__", html)
            saved = json.loads((out / "story.json").read_text())
            saved["beats"] = [b for b in saved["beats"] if b["id"] != "run"]
            build.build(saved, out, None, None)
            starts = [b["start"] for b in saved["beats"]]
            self.assertEqual(starts, sorted(starts))

    def test_chapter_commands_are_typed_and_fit(self):
        """v3 regression: chapter cards drew the prompt but never typed the command."""
        with tempfile.TemporaryDirectory() as tmp:
            story = build.make_story(year_fixture(), build.CTA)
            html = build.build(story, Path(tmp), None, None, "b").read_text()
            self.assertIn('class="cmd" data-cmd="git log --since=2025-01-01', html)
            self.assertIn("cmd.textContent = text.slice(", html)  # the typing tween exists
            timing = json.loads(html.split("const TIMING = ")[1].split(";\n")[0])
            chapters = [s for s in timing if s["id"] == "chapter"]
            self.assertTrue(chapters)
            self.assertTrue(all(s["type_dur"] > 0 for s in chapters))
            self.assertNotIn("__ROOT_CLASS__", html)
        for cmd in ("git tag --sort=-creatordate", "git log --since=2026-01-01 --author=a-much-longer-login"):
            size = build.term_size(cmd, 40)
            self.assertLessEqual(0.6 * size * (len(cmd) + 5), 912)

    def test_close_and_thumbnail_have_no_chrome(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            story = build.make_story(year_fixture(), build.CTA)
            html = build.build(story, out, None, None).read_text()
            close = html.split('id="s-close"')[1].split("</section>")[0]
            self.assertNotIn('class="label"', close)
            thumb = (out / "thumbnail" / "index.html").read_text()
            self.assertIn('class="thumb"', thumb)
            self.assertIn('data-duration="1.0"', thumb)
            self.assertNotIn('id="rail"', thumb)
            self.assertNotIn('class="label"', thumb)
            self.assertNotIn('class="cta', thumb)
            self.assertNotIn("__", thumb.replace("window.__timelines", ""))
            self.assertIn("@quiet", thumb)
            self.assertTrue((out / "thumbnail" / "assets" / "fonts" / "JetBrainsMono.ttf").exists())

    def test_thumbnail_is_the_identity(self):
        """Option A: kicker, the archetype name with its last word in signal, the stats."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            story = build.make_story(year_fixture(), build.CTA)
            ident = next(b for b in story["beats"] if b["id"] == "identity")
            ident["name"] = "The Weekend Orchestrator"
            ident["reason"] = "57% of commits shipped with agents, 38% of commits on weekends."
            build.build(story, out, None, None)
            thumb = (out / "thumbnail" / "index.html").read_text()
            self.assertIn('id="s-identity"', thumb)
            self.assertNotIn('id="s-close"', thumb)
            self.assertIn(f'@quiet / {ident["label"]}</div>', thumb)
            self.assertIn('style="font-size:190px">The<br>Weekend<br><span class="signal">Orchestrator</span>', thumb)
            self.assertIn("57% of commits shipped with agents.<br>38% on weekends.", thumb)
            for chrome in ('id="rail"', 'class="label"', 'class="cta', 'class="term"', "__"):
                self.assertNotIn(chrome, thumb.replace("window.__timelines", ""))

    def test_thumbnail_falls_back_to_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            story = build.make_story(year_fixture(), build.CTA)
            story["beats"] = [b for b in story["beats"] if b["id"] != "identity"]
            build.build(story, out, None, None)
            thumb = (out / "thumbnail" / "index.html").read_text()
            self.assertIn('id="s-close"', thumb)
            self.assertNotIn('class="inner tid"', thumb)
            self.assertIn("in review.", thumb)
            self.assertNotIn('class="cta', thumb)

    def test_thumbnail_long_title_fits(self):
        name = "The Extraordinarily Nocturnal Internationalization Superconductor"
        lines = build.title_lines(name)
        self.assertEqual(lines[-1], "Superconductor")
        size = build.title_size(lines)
        self.assertLess(size, build.THUMB_TITLE)
        self.assertLessEqual(build.THUMB_EM * size * max(map(len, lines)), 912)
        self.assertLessEqual(len(lines) * size * 0.86, 700)  # leaves room for kicker and stats
        many = build.title_lines("The Very Quiet Late Night Weekend Open Source Reviewer")
        self.assertLessEqual(len(many), 5)
        self.assertEqual(many[-1], "Reviewer")
        self.assertEqual(build.title_size(build.title_lines("The Weekend Orchestrator")), 190)
        self.assertEqual(build.stat_lines("A 44-day streak."), ["A 44-day streak."])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            story = build.make_story(year_fixture(), build.CTA)
            next(b for b in story["beats"] if b["id"] == "identity")["name"] = name
            build.build(story, out, None, None)
            thumb = (out / "thumbnail" / "index.html").read_text()
            self.assertIn(f'style="font-size:{size}px">The<br>Extraordinarily<br>', thumb)
            self.assertIn('<span class="signal">Superconductor</span>', thumb)


if __name__ == "__main__":
    unittest.main()
