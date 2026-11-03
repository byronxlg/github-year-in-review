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


if __name__ == "__main__":
    unittest.main()
