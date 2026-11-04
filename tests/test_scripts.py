"""Offline tests for the collector helpers and the story builder. No network, no gh."""

import datetime as dt
import json
import sys
import re
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

    def test_model_key_folds_variants_and_skips_unversioned(self):
        self.assertEqual(collect.model_key("Claude Opus 4.6 (1M context)"), "Claude Opus 4.6")
        self.assertIsNone(collect.model_key("Claude"))
        self.assertIsNone(collect.model_key("claude[bot]"))

    def test_commit_search_waits_out_a_rate_limit(self):
        from unittest import mock
        calls = []
        def fake(path, **params):
            calls.append(path)
            if len(calls) == 1:
                raise RuntimeError("You have exceeded a secondary rate limit")
            return {"items": []}
        with mock.patch.object(collect, "gh_rest", fake), mock.patch.object(collect.time, "sleep", lambda s: None):
            self.assertEqual(collect.search_commits("q"), {"items": []})
        self.assertEqual(len(calls), 2)

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


def strong_year() -> dict:
    """A busy year where every beat in the catalogue has data."""
    d = year_fixture()
    days = []
    x = dt.date(2025, 1, 1)
    while x.year == 2025:
        days.append([x.isoformat(), 400 if x.isoformat() == "2025-03-21" else (8 if x.weekday() < 6 else 2)])
        x += dt.timedelta(days=1)
    grid = [[2] * 24 for _ in range(7)]
    grid[1][20] = 90  # Tuesday 8 pm owns the evening
    hours = [sum(grid[w][h] for w in range(7)) for h in range(24)]
    d.update(
        calendar=days,
        totals={"contributions": 3200, "commits": 2400, "prs": 600, "reviews": 40, "issues": 30},
        rhythm={"active_days": 365, "weekend_share": 0.2,
                "streak": {"longest": 45, "start": "2025-02-01", "end": "2025-03-17", "current": 0},
                "busiest_day": {"date": "2025-03-21", "count": 400, "prs_merged": 60},
                "by_month": [250] * 12, "peak_hour": 20, "by_hour": hours, "night_share": 0.3, "morning_share": 0.05,
                "latest_night_commit": {"time": "03:10", "date": "2025-05-02"}, "commits_sampled": sum(hours),
                "by_weekday_sampled": [sum(r) for r in grid], "by_weekday_hour": grid},
        repos=[{"name": "me/app", "short": "app", "private": False, "commits": 900, "language": "Python",
                "color": "#3572A5", "description": "An app. It does things."}],
        repo_count=12,
        repo_languages={"repos": 20, "with_language": 18, "by_language": [["Python", 9], ["TypeScript", 6], ["Go", 3]]},
        history=[{"year": 2023, "contributions": 40}, {"year": 2024, "contributions": 100}],
        agents=dict(agents_block(), model_first_seen=[["Claude Opus 4.5", "2025-01-09"], ["Claude Sonnet 4.6", "2025-03-08"],
                                                      ["Claude Opus 4.6", "2025-03-14"], ["Claude Opus 4.8", "2025-05-29"]]),
        pull_requests=dict(year_fixture()["pull_requests"], opened=700, merged=600, merge_rate=0.86, sampled=700,
                           lines_added=250_000, lines_removed=60_000, external_merged=12,
                           external_public=[["big/oss", 12]], external_public_stars={"big/oss": 9000},
                           biggest={"repo": "me/app", "title": "Rewrite the engine", "additions": 9000,
                                    "deletions": 3000, "files": 80, "number": 7}),
        actions={"minutes": 20_000, "runs": 4000, "by_month": [1000] * 12, "estimated": False},
        releases={"total": 30, "repos": [{"repo": "app", "count": 30, "first": "v0.1", "latest": "v3.0",
                                          "latest_date": "2025-12-01", "dates": ["2025-06-01"] * 30}]},
        new_repos=[{"name": "fresh", "created": "2025-02-01", "stars": 30, "language": "Go", "description": "New thing."}] * 3,
        stars={"gained": 40, "by_repo": [], "total_owned": 50},
        automation={"repos": [{"name": "me/cron", "commits": 900}], "commits": 900},
    )
    return d


class Catalogue(unittest.TestCase):
    MANDATORY = ("hook", "shape", "work", "identity", "close")

    def story(self, d=None, **kw):
        return build.make_story(d or strong_year(), build.CTA, **kw)

    def test_catalogue_is_complete(self):
        self.assertEqual(set(build.BEATS), set(build.EST_DURATION))
        self.assertEqual(set(build.BEATS), set(build.COMMANDS) - {"chapter"})
        self.assertEqual({s for s, b in build.BEATS.items() if b["mandatory"]}, set(self.MANDATORY))
        for sid in build.BEATS:
            self.assertIn("b_" + sid, build.BUILDERS)

    def test_mandatory_always_present_and_order_fixed(self):
        for d in (strong_year(), year_fixture(repos=strong_year()["repos"])):
            ids = [b["id"] for b in self.story(d)["beats"]]
            for sid in self.MANDATORY:
                self.assertIn(sid, ids)
            self.assertEqual(ids, sorted(ids, key=lambda s: build.BEATS[s]["order"]))

    def test_alternatives_are_exclusive_and_the_higher_score_wins(self):
        st = self.story()
        ids = [b["id"] for b in st["beats"]]
        for slot in {b["slot"] for b in build.BEATS.values()}:
            self.assertLessEqual(sum(1 for s in ids if build.BEATS[s]["slot"] == slot), 1, slot)
        left = {x["id"]: x for x in st["selection"]["left_out"]}
        chosen = {x["id"]: x for x in st["selection"]["chosen"]}
        when = "punchcard" if "punchcard" in chosen else "clock"
        other = "clock" if when == "punchcard" else "punchcard"
        self.assertEqual(when, "punchcard")  # Tuesday holds most of the 8 pm hour: the week says more
        self.assertGreaterEqual(chosen[when]["score"], left[other]["score"])
        self.assertIn("alternative", left[other]["reason"])

    def test_budget_respected_and_selection_recorded(self):
        st = self.story()
        used = sum(build.EST_DURATION[b["id"]] for b in st["beats"])
        self.assertLessEqual(used, build.MAX_TOTAL)
        sel = st["selection"]
        self.assertEqual([x["id"] for x in sel["chosen"]], [b["id"] for b in st["beats"]])
        self.assertTrue(any("time budget" in x["reason"] for x in sel["left_out"]))
        for x in sel["left_out"]:
            self.assertTrue(x["reason"])
        # every catalogue beat is accounted for, once
        self.assertEqual(sorted([x["id"] for x in sel["chosen"]] + [x["id"] for x in sel["left_out"]]), sorted(build.BEATS))
        # optional beats are taken best first: nothing left out for time outscores a chosen one that costs as much
        chosen_scores = [x["score"] for x in sel["chosen"] if x["score"] is not None]
        for x in sel["left_out"]:
            if "time budget" in x["reason"]:
                self.assertLessEqual(x["score"], max(chosen_scores))

    def test_force_and_skip(self):
        st = self.story(force=["clock", "models"], skip=["agents"])
        ids = [b["id"] for b in st["beats"]]
        self.assertIn("clock", ids)
        self.assertNotIn("punchcard", ids)
        self.assertIn("models", ids)
        self.assertNotIn("agents", ids)
        self.assertLessEqual(sum(build.EST_DURATION[s] for s in ids), build.MAX_TOTAL)
        with self.assertRaises(ValueError):
            self.story(force=["nope"])
        # forcing a beat with no data leaves it out and says why
        st = build.make_story(year_fixture(), build.CTA, force=["models"])
        self.assertIn("forced, but no data", next(x for x in st["selection"]["left_out"] if x["id"] == "models")["reason"])

    def test_surprise_yields_to_agents(self):
        st = self.story(force=["agents"])
        self.assertNotIn("surprise", [b["id"] for b in st["beats"]])
        d = strong_year()
        d["agents"] = None
        d["rhythm"]["busiest_day"]["count"] = 20  # weak busiest day: the cron is the better surprise
        sel = {x["id"]: x for x in self.story(d)["selection"]["chosen"]}
        self.assertIn("surprise", sel)

    def test_new_beats_drop_on_thin_data(self):
        st = build.make_story(year_fixture(), build.CTA)
        ids = [b["id"] for b in st["beats"]]
        for sid in ("punchcard", "day", "yoy", "languages", "models"):
            self.assertNotIn(sid, ids)
            self.assertIn("no data", next(x for x in st["selection"]["left_out"] if x["id"] == sid)["reason"])
        d = strong_year()
        d["history"] = [{"year": 2024, "contributions": 4}]
        d["agents"]["model_first_seen"] = d["agents"]["model_first_seen"][:2]
        d["repo_languages"] = {"repos": 6, "with_language": 6, "by_language": [["Python", 6]]}
        d["rhythm"]["commits_sampled"] = 120
        d["rhythm"]["busiest_day"]["count"] = 15
        left = {x["id"]: x["reason"] for x in self.story(d)["selection"]["left_out"]}
        for sid in ("punchcard", "day", "yoy", "languages", "models"):
            self.assertIn("no data", left[sid], sid)

    def test_new_beats_on_strong_data(self):
        for sid in ("punchcard", "day", "yoy", "languages", "models"):
            st = self.story(force=[sid])
            b = next(x for x in st["beats"] if x["id"] == sid)
            with tempfile.TemporaryDirectory() as tmp:
                html = build.build(st, Path(tmp), None, None).read_text()
            self.assertIn(f'id="s-{sid}"', html)
            if sid == "punchcard":
                self.assertEqual(b["hero"], "Tue 8 pm")
                self.assertEqual(html.count('class="pr"'), 7)
            if sid == "day":
                self.assertEqual((b["number"], b["sub"]), (400, "A Friday: 60 pull requests merged."))
                self.assertEqual(len(b["week"]), 7)
            if sid == "yoy":
                self.assertEqual((b["hero"], b["unit"]), ("32x", "the contributions of 2024"))
                self.assertEqual(b["sub"], "40, then 100, then 3,200.")
            if sid == "languages":
                self.assertEqual((b["hero"], b["unit"]), ("Python", "primary language of 9 of 20 repos"))
                self.assertEqual(sum(v for _, v in b["rows"]), 20)
            if sid == "models":
                self.assertEqual((b["number"], b["unit"]), (4, "Claude models in your commits"))
                self.assertEqual(b["rows"][-1]["name"], "Opus 4.8")

    def test_yoy_never_shames(self):
        d = strong_year()
        d["history"] = [{"year": 2023, "contributions": 5000}, {"year": 2024, "contributions": 4000}]
        b = next(x for x in self.story(d, force=["yoy"])["beats"] if x["id"] == "yoy")
        self.assertEqual((b["hero"], b["unit"]), ("12,200", "contributions over 3 years"))
        self.assertEqual(build.score_beat("yoy", d, b), 0.1)

    def test_scores_follow_strength(self):
        d = strong_year()
        self.assertGreater(build.ramp(45, 3, 60), 0.8)
        self.assertLess(build.ramp(4, 3, 60), 0.15)
        self.assertGreater(build.score_beat("yoy", d, {"ratio": 56}), 0.85)
        self.assertLess(build.score_beat("yoy", d, {"ratio": 1.3}), 0.05)


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

    def test_tight_pace_fits_more_beats_in_less_time(self):
        """#19364819: no chapter cards, cuts, and the reading-floor hold; calm stays as it was."""
        def film(pace):
            story = build.make_story(year_fixture(), build.CTA, pace=pace)
            with tempfile.TemporaryDirectory() as tmp:
                html = build.build(story, Path(tmp), None, None).read_text()
            return story, json.loads(re.search(r"const TIMING = (\[.*?\]);", html, re.S).group(1)), html
        calm, calm_t, calm_h = film("calm")
        tight, tight_t, tight_h = film("tight")
        self.assertGreaterEqual(len(tight["beats"]), len(calm["beats"]))
        self.assertTrue(any(s["id"] == "chapter" for s in calm_t))
        self.assertFalse(any(s["id"] == "chapter" for s in tight_t))
        self.assertLess(max(s["duration"] for s in tight_t), 5.0)
        self.assertIn('"fadeOut": 0.0', tight_h)
        self.assertNotIn("__PACE__", calm_h + tight_h)
        # every beat still holds still for the reading floor after its last motion
        for beat in tight["beats"]:
            html = build.scene_html(beat, tight, 9, "b")
            b = build.beat_timing(beat["id"], html, None, "tight")
            self.assertGreaterEqual(b["duration"] - b["settle"], 2.5 - 1e-3)

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

    def test_film_has_no_page_or_section_numbers(self):
        """No slide counter (02/10), hash label, "part N of M" or progress ticks in either direction."""
        for direction in ("a", "b"):
            with tempfile.TemporaryDirectory() as tmp:
                story = build.make_story(year_fixture(), build.CTA)
                html = build.build(story, Path(tmp), None, None, direction=direction).read_text()
                self.assertIsNone(re.search(r"\b\d{2}/\d{2}\b", html))
                for mark in ('class="idx"', 'class="ct"', 'id="ticks"', "part 1 of", "__BEATS__"):
                    self.assertNotIn(mark, html)
                self.assertIn("The shape of the year</span>", html)

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


class ChartsTest(unittest.TestCase):
    """v6: each chart takes the shape of its question, and its parts add up to the headline."""

    def test_alloc_adds_up(self):
        self.assertEqual(build.alloc(58, [0.406, 0.336, 0.138, 0.12]), [24, 19, 8, 7])
        for total in (1, 7, 58, 99):
            self.assertEqual(sum(build.alloc(total, [0.5, 0.3, 0.2])), total)

    def test_agents_waffle_is_share_of_all_commits(self):
        b = {"number": 58, "unit": "of your commits co-written with Claude",
             "rows": [{"trailer": "Claude Opus 5.5", "share": 0.406}, {"trailer": "Claude Opus 4.8", "share": 0.336},
                      {"trailer": "Claude Opus 4.6", "share": 0.138}]}
        parts = build.agent_parts(b, "Claude")
        self.assertEqual(parts, [("Opus 5.5", 24), ("Opus 4.8", 19), ("Opus 4.6", 8), ("others", 7)])
        html = build.waffle([v for _, v in parts], 'data-p="2"')
        self.assertEqual(html.count('class="w"'), 58)
        self.assertEqual(html.count('class="w o"'), 42)

    def test_release_burst(self):
        rel = {"repos": [{"dates": ["2026-03-19"] * 10 + ["2026-03-21"] * 5 + ["2026-07-01", "2026-09-08"]}]}
        self.assertEqual(build.burst_line(rel), "15 of them in 3 days in March.")
        self.assertEqual(build.burst_line({"repos": [{"dates": ["2026-01-05", "2026-04-01", "2026-08-01"]}]}), "")

    def test_beats_draw_their_charts(self):
        d = year_fixture()
        d["releases"] = {"total": 4, "repos": [{"repo": "tool", "count": 4, "first": "v0.1.0", "latest": "v0.4.0",
                                                "latest_date": "2026-05-02", "dates": ["2026-02-01", "2026-03-01", "2026-05-01", "2026-05-02"]}]}
        with tempfile.TemporaryDirectory() as tmp:
            story = build.make_story(d, build.CTA)
            html = build.build(story, Path(tmp), None, None).read_text()
        ids = {b["id"] for b in story["beats"]}
        if "run" in ids:
            self.assertIn('class="yline"', html)
        if "ship" in ids:
            self.assertIn('class="rate', html)
        self.assertIn('class="rcols"', html)
        self.assertNotIn('class="trailers"', html)


class LinesAndActionsTest(unittest.TestCase):
    """v7: the year's lines against a famous codebase, and GitHub Actions time."""

    def test_codebase_match_picks_largest_within_reach(self):
        m = build.codebase_match(540_853)
        self.assertEqual((m["short"], m["ratio"]), ("Quake III Arena", 1.63))
        self.assertEqual(build.codebase_match(60_000)["short"], "Doom")
        self.assertEqual(build.codebase_match(50_000)["short"], "Doom")  # 59k is within 1.25x
        self.assertEqual(build.codebase_match(1_000)["short"], "git's first commit")
        self.assertIsNone(build.codebase_match(900))
        self.assertEqual(build.codebase_match(60_000_000)["short"], "Linux kernel")
        sizes = [c[2] for c in build.CODEBASES]
        self.assertEqual(sizes, sorted(sizes))
        self.assertTrue(all(c[3] for c in build.CODEBASES))  # every figure has a source

    def test_times_phrase(self):
        self.assertEqual(build.times_phrase(0.9), "about the size of")
        self.assertEqual(build.times_phrase(1.63), "about one and a half times")
        self.assertEqual(build.times_phrase(2.2), "about twice")
        self.assertEqual(build.times_phrase(3.4), "about 3 times")
        self.assertEqual(build.compact(540_853), "541k")
        self.assertEqual(build.compact(1_234_567), "1.2M")
        self.assertEqual(build.duration_words(33_843), "about 24 days")
        self.assertEqual(build.duration_words(300), "about 5 hours")

    def test_run_minutes(self):
        run = {"status": "completed", "run_started_at": "2026-10-01T10:00:00Z", "updated_at": "2026-10-01T10:04:30Z"}
        self.assertEqual(collect.run_minutes(run), 4.5)
        self.assertEqual(collect.run_minutes(dict(run, status="in_progress")), 0.0)
        self.assertEqual(collect.run_minutes(dict(run, updated_at="2026-10-03T10:00:00Z")), collect.RUN_MAX_MINUTES)
        self.assertEqual(collect.run_minutes(dict(run, updated_at="2026-10-01T09:00:00Z")), 0.0)

    def test_summarise_runs_keeps_the_year_by_local_month(self):
        from zoneinfo import ZoneInfo
        runs = [{"status": "completed", "run_started_at": "2026-03-31T20:00:00Z", "updated_at": "2026-03-31T20:10:00Z"},
                {"status": "completed", "run_started_at": "2026-05-02T00:00:00Z", "updated_at": "2026-05-02T00:02:00Z"},
                {"status": "completed", "run_started_at": "2025-12-31T01:00:00Z", "updated_at": "2025-12-31T02:00:00Z"}]
        s = collect.summarise_runs(runs, 2026, ZoneInfo("Pacific/Auckland"))
        self.assertEqual(s["runs"], 2)
        self.assertEqual(s["minutes"], 12)
        self.assertEqual(s["by_month"][3], 10)  # 31 Mar 20:00 UTC is April in Auckland
        self.assertEqual(s["by_month"][4], 2)

    def test_actions_time_pages_until_the_year_starts_and_estimates_past_the_cap(self):
        def run(day):
            return {"status": "completed", "created_at": f"{day}T00:00:00Z", "run_started_at": f"{day}T00:00:00Z",
                    "updated_at": f"{day}T00:05:00Z"}
        calls = []

        def fake(path, **params):
            calls.append((path, params))
            if "created" in params:
                return {"total_count": 250}
            if path.startswith("repos/me/busy"):
                return {"workflow_runs": [run("2026-06-01")] * 100}
            if path.startswith("repos/me/fail"):
                raise RuntimeError("HTTP 404")
            page = params["page"]
            return {"workflow_runs": [run("2026-06-01")] * 100 if page == 1 else [run("2025-12-01")] * 100}
        owned = [{"nameWithOwner": "me/app", "isPrivate": False, "isFork": False, "pushedAt": "2026-06-01"},
                 {"nameWithOwner": "me/busy", "isPrivate": True, "isFork": False, "pushedAt": "2026-06-01"},
                 {"nameWithOwner": "me/fail", "isPrivate": False, "isFork": False, "pushedAt": "2026-06-01"},
                 {"nameWithOwner": "me/fork", "isPrivate": False, "isFork": True, "pushedAt": "2026-06-01"},
                 {"nameWithOwner": "me/old", "isPrivate": False, "isFork": False, "pushedAt": "2024-01-01"}]
        from unittest import mock
        from zoneinfo import ZoneInfo
        start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        with mock.patch.object(collect, "gh_rest", fake), mock.patch.object(collect, "RUN_PAGES_PER_REPO", 2), \
                mock.patch.object(collect.time, "sleep", lambda s: None):
            a = collect.actions_time(owned, "me", 2026, start, ZoneInfo("UTC"), False)
        self.assertEqual(a["minutes_measured"], 300 * 5)  # app: 100 runs; busy: 200 runs before the cap
        self.assertEqual(a["runs"], 100 + 250)  # busy's 250 runs this year, 50 of them estimated
        self.assertEqual(a["minutes"], 300 * 5 + 50 * 5)
        self.assertTrue(a["estimated"])
        self.assertEqual(a["estimated_repos"], [["a private repo", 50]])
        self.assertEqual(a["unreadable_repos"], 1)
        self.assertFalse(any("fork" in p or "old" in p for p, _ in calls))
        self.assertEqual(a["by_month"][5], 1500)
        with mock.patch.object(collect, "gh_rest", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))), \
                mock.patch.object(collect.time, "sleep", lambda s: None):
            self.assertIsNone(collect.actions_time(owned[:1], "me", 2026, start, ZoneInfo("UTC"), False))

    def test_lines_and_actions_beats(self):
        pr = dict(year_fixture()["pull_requests"], opened=40, merged=30, sampled=40,
                  lines_added=540_853, lines_removed=166_863)
        act = {"minutes": 33_843, "runs": 10_716, "by_month": [12, 1, 237, 0, 520, 324, 569, 1120, 1390, 28422, 1249, 0],
               "estimated": False}
        d = year_fixture(pull_requests=pr, actions=act)
        story = build.make_story(d, build.CTA)
        beats = {b["id"]: b for b in story["beats"]}
        self.assertEqual(beats["lines"]["sub"], "Added: about one and a half times the Quake III Arena source.")
        self.assertIn("merged pull requests", beats["lines"]["unit"])
        self.assertEqual(beats["actions"]["number"], 33_843)
        self.assertEqual(beats["actions"]["sub"], "About 24 days of machine time, 84% of it in October.")
        with tempfile.TemporaryDirectory() as tmp:
            html = build.build(story, Path(tmp), None, None).read_text()
        self.assertEqual(html.count('class="lrow'), 3)
        self.assertEqual(html.count('class="mc'), 12)
        # thin or missing data: no beat
        ids = [b["id"] for b in build.make_story(year_fixture(), build.CTA)["beats"]]
        self.assertNotIn("lines", ids)
        self.assertNotIn("actions", ids)
        ids = [b["id"] for b in build.make_story(year_fixture(actions=None), build.CTA)["beats"]]
        self.assertNotIn("actions", ids)


class BeatGridTest(unittest.TestCase):
    def test_parses_hyperframes_beats_and_cue_files(self):
        self.assertEqual(build.parse_beats({"bpm": 110, "beatTimes": [0.555, 1.105]}), [0.555, 1.105])
        self.assertEqual(build.parse_beats({"beats": [{"time": 0.5}, {"time": 1.0}]}), [0.5, 1.0])
        self.assertEqual(build.parse_beats({}), [])

    def test_no_music_means_no_grid(self):
        self.assertEqual(build.beat_grid(None, None), [])

    def test_cue_file_wins(self):
        with tempfile.TemporaryDirectory() as d:
            cues = Path(d) / "beats.json"
            cues.write_text(json.dumps({"beatTimes": [0.4, 0.9]}))
            self.assertEqual(build.beat_grid(None, cues), [0.4, 0.9])


if __name__ == "__main__":
    unittest.main()
