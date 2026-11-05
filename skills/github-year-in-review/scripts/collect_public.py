#!/usr/bin/env python3
"""Answer collect.py's queries with no login: a GitHub handle is enough.

GraphQL refuses anonymous callers, so this module stands in for it. Each query collect.py asks
is answered from what GitHub shows anyone: the REST API (60 requests an hour per IP), search (10
a minute) and two profile pages (the contribution calendar and the monthly activity list). The
calendar and the activity list are HTML, so a GitHub redesign can break them: the calendar is
required, the activity list degrades to the commit sample.

No token is ever sent, so the result cannot contain anything private. It also means the hour of
day comes from each commit's own clock, not from the timezone of whoever runs this.

The hourly limit is spent on what the film uses most: profile and top repos first, then every
merged PR's line counts (all or none, a partial sum would be a wrong number), then releases, and
Actions time with what is left. `source.skipped` in year.json says what went without.
"""

from __future__ import annotations

import bisect
import collections
import datetime as dt
import html as htmllib
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import collect as C

API = "https://api.github.com"
WEB = "https://github.com"
AGENT = "github-year-in-review"
SEARCH_GAP = 6.5  # search allows 10 a minute without a token
SEARCH_WAITS = (30, 65, 130)
TOP_REPOS = 6  # repos outside the user's own that get a detail call
LANGUAGE_REPOS = 5  # repos whose byte mix is read
GAP_REPOS = 3  # repos search under-reports (it skips some), read directly for the clock sample
RELEASE_REPOS = 8  # recently pushed repos read for releases
CORE_RESERVE = 2  # requests left alone so a follow-up call in the same hour still works

# GitHub's linguist colours: GraphQL gives them, REST does not. Anything else is drawn neutral.
LANGUAGE_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Go": "#00ADD8",
    "Rust": "#dea584", "Java": "#b07219", "C": "#555555", "C++": "#f34b7d", "C#": "#178600",
    "Ruby": "#701516", "PHP": "#4F5D95", "Swift": "#F05138", "Kotlin": "#A97BFF", "Dart": "#00B4AB",
    "Shell": "#89e051", "HTML": "#e34c26", "CSS": "#663399", "SCSS": "#c6538c", "Vue": "#41b883",
    "Svelte": "#ff3e00", "Jupyter Notebook": "#DA5B0B", "Lua": "#000080", "Scala": "#c22d40",
    "Elixir": "#6e4a7e", "Haskell": "#5e5086", "R": "#198CE7", "HCL": "#844FBA", "Dockerfile": "#384d54",
    "Nix": "#7e7eff", "Zig": "#ec915c", "OCaml": "#ef7a08", "Clojure": "#db5855",
}


# ---------------------------------------------------------------- pages

def parse_calendar(page: str) -> tuple[list[dict], int | None]:
    """The calendar fragment as ([{date, contributionCount}], headline total)."""
    tips = {}
    for m in re.finditer(r'<tool-tip\b[^>]*?\bfor="([^"]+)"[^>]*>(.*?)</tool-tip>', page, re.S):
        count = re.match(r"\s*([\d,]+)\s+contribution", m.group(2))
        tips[m.group(1)] = int(count.group(1).replace(",", "")) if count else 0
    days = []
    for m in re.finditer(r"<td\b[^>]*>", page):
        tag = m.group(0)
        date, cell = re.search(r'data-date="([\d-]+)"', tag), re.search(r'\bid="([^"]+)"', tag)
        if date and cell:
            days.append({"date": date.group(1), "contributionCount": tips.get(cell.group(1), 0)})
    days.sort(key=lambda d: d["date"])
    head = re.search(r"([\d,]+)\s+contributions?\s+in\s+(?:the\s+last\s+year|\d{4})", page)
    return days, int(head.group(1).replace(",", "")) if head else None


def page_text(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def parse_activity(page: str) -> dict | None:
    """One month of the profile's activity list; None when the page is not the list we know."""
    text = page_text(page)
    if "Contribution activity" not in text and "contributions in private" not in text:
        return None
    number = lambda s: int(s.replace(",", ""))
    return {
        "commits": {m.group(1): number(m.group(2))
                    for m in re.finditer(r"([\w.-]+/[\w.-]+) ([\d,]+) commits?\b", text)},
        "private": sum(number(x) for x in re.findall(r"([\d,]+) contributions? in private repositor", text)),
        "reviews": sum(number(x) for x in re.findall(r"Reviewed ([\d,]+) pull requests? in", text)),
        "issues": sum(number(x) for x in re.findall(r"Opened ([\d,]+)(?: other)? issues? in", text))
        + len(re.findall(r"Opened an issue in", text)),
    }


def fill_offsets(stamps: list[str]) -> list[str]:
    """A commit made through GitHub's web UI or a bot says UTC, whatever the person's clock said.
    Give each UTC stamp the offset of the nearest commit that has a real one; with none, leave it."""
    def utc(s):
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))

    known = sorted((utc(s), utc(s).utcoffset()) for s in stamps if utc(s).utcoffset())
    if not known:
        return stamps
    times = [t for t, _ in known]
    out = []
    for s in stamps:
        when = utc(s)
        if when.utcoffset():
            out.append(s)
            continue
        i = bisect.bisect_left(times, when)
        near = min((known[j] for j in (i - 1, i) if 0 <= j < len(known)), key=lambda k: abs(k[0] - when))
        out.append(when.astimezone(dt.timezone(near[1])).isoformat())
    return out


# ---------------------------------------------------------------- the source

class PublicSource:
    def __init__(self, user: str, year: int):
        self.user, self.year = user, year
        self.today = dt.datetime.now(dt.timezone.utc).date()
        self.core_left = 60
        self.lock = threading.Lock()
        self.last_search = 0.0
        self.calls = collections.Counter()
        self.skipped: list[str] = []
        self.memo: dict = {}
        self.owned: list[dict] | None = None
        self.sample: dict | None = None
        self.activity: dict | None = None
        self.prs_by_month: dict | None = None
        self.notes: list[str] = []

    # transport ----------------------------------------------------------

    def _request(self, url: str, accept: str, **extra) -> tuple[bytes, dict]:
        headers = {"User-Agent": AGENT, "Accept": accept, **extra}  # never an Authorization header
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
            return resp.read(), dict(resp.headers)

    def api(self, path: str, accept: str = "application/vnd.github+json", **params) -> tuple[object, dict]:
        url = f"{API}/{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        with self.lock:
            if url in self.memo:
                return self.memo[url]
        try:
            body, headers = self._request(url, accept)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "replace")
            try:
                detail = json.loads(detail).get("message", detail)
            except ValueError:
                pass
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from None
        except OSError as exc:
            raise RuntimeError(f"network: {exc}") from None
        with self.lock:
            self.calls["search" if path.startswith("search/") else "core"] += 1
            if not path.startswith("search/") and headers.get("X-RateLimit-Remaining"):
                self.core_left = int(headers["X-RateLimit-Remaining"])
            self.memo[url] = (json.loads(body), headers)
            return self.memo[url]

    def rest(self, path: str, **params) -> dict:
        """collect.py's gh_rest, anonymous. Search goes through the paced path."""
        return self.search(path, **params) if path.startswith("search/") else self.api(path, **params)[0]

    def search(self, path: str, **params) -> dict:
        url_key = f"{path}?{urllib.parse.urlencode(params)}"
        if f"{API}/{url_key}" in self.memo:
            return self.memo[f"{API}/{url_key}"][0]
        for attempt in range(len(SEARCH_WAITS) + 1):
            pause = self.last_search + SEARCH_GAP - time.time()
            if pause > 0:
                time.sleep(pause)
            self.last_search = time.time()
            try:
                return self.api(path, **params)[0]
            except RuntimeError as exc:
                if "rate limit" not in str(exc).lower() or attempt == len(SEARCH_WAITS):
                    raise
                print(f"search rate limited; waiting {SEARCH_WAITS[attempt]} s", file=sys.stderr)
                time.sleep(SEARCH_WAITS[attempt])
        raise RuntimeError("unreachable")

    def web(self, url: str) -> str:
        self.calls["web"] += 1
        time.sleep(0.3)  # a person's pace, these are pages rather than an API
        # the XHR header gets the fragment the profile loads; without it, a page with no activity list
        return self._request(url, "text/html", **{"X-Requested-With": "XMLHttpRequest"})[0].decode("utf-8", "replace")

    def can_spend(self, cost: int = 1) -> bool:
        return self.core_left - cost >= CORE_RESERVE

    def skip(self, what: str) -> None:
        if what not in self.skipped:
            self.skipped.append(what)
            print(f"public: skipped {what}", file=sys.stderr)

    # data the queries share ---------------------------------------------

    def calendar(self, year: int) -> tuple[list[dict], int]:
        key = f"calendar{year}"
        if key not in self.memo:
            page = self.web(f"{WEB}/users/{self.user}/contributions?from={year}-01-01&to={year}-12-31")
            days, total = parse_calendar(page)
            if not days:
                raise SystemExit("GitHub's contribution calendar page has changed: no days found")
            self.memo[key] = (days, total if total is not None else sum(d["contributionCount"] for d in days))
        return self.memo[key]

    def own_repos(self) -> list[dict]:
        if self.owned is None:
            rows, page = [], 1
            while True:
                batch = self.api(f"users/{self.user}/repos", type="owner", per_page=100, sort="pushed",
                                 page=page)[0]
                rows += batch
                if len(batch) < 100 or not self.can_spend():
                    break
                page += 1
            self.owned = rows
        return self.owned

    def months(self) -> list[tuple[dt.date, dt.date]]:
        end = min(dt.date(self.year, 12, 31), self.today)
        return C.month_ranges(dt.date(self.year, 1, 1), end)

    def activity_months(self) -> dict:
        """Commit counts by repo, private contributions, reviews and issues, summed over the year."""
        if self.activity is None:
            out = {"commits": collections.Counter(), "private": 0, "reviews": 0, "issues": 0, "read": 0}
            for a, b in self.months():
                try:
                    got = parse_activity(self.web(f"{WEB}/{self.user}?tab=overview&from={a}&to={b}"))
                except (OSError, urllib.error.URLError):
                    got = None
                if not got:
                    continue
                out["read"] += 1
                out["commits"].update(got["commits"])
                for k in ("private", "reviews", "issues"):
                    out[k] += got[k]
            if out["read"] < len(self.months()):
                self.skip(f"activity list ({out['read']} of {len(self.months())} months read)")
            self.activity = out
        return self.activity

    def commits(self) -> dict[str, list[dict]]:
        """Up to 100 commits a month with full messages, by repo, in the shape of history nodes."""
        if self.sample is None:
            items = []
            for a, b in self.months():
                q = f"author:{self.user} author-date:{a}..{b}"
                try:
                    items += self.search("search/commits", q=q, per_page=100, sort="author-date",
                                         order="desc").get("items", [])
                except RuntimeError as exc:
                    self.skip(f"commit sample for {a:%b} ({str(exc)[:80]})")
            items += self.commits_search_missed(items)
            stamps = fill_offsets([it["commit"]["author"]["date"].replace(".000", "") for it in items])
            by_repo = collections.defaultdict(list)
            for it, when in zip(items, stamps):
                by_repo[it["repository"]["full_name"]].append(
                    {"committedDate": when, "authoredDate": when, "additions": 0, "deletions": 0,
                     "messageHeadline": (it["commit"]["message"] or "").split("\n", 1)[0]})
            self.sample = dict(by_repo)
        return self.sample

    def commits_search_missed(self, items: list[dict]) -> list[dict]:
        """Commit search leaves some repos out while the activity list counts them. Read the
        biggest gaps directly. These stamps say UTC, fill_offsets gives them the person's clock."""
        seen = collections.Counter(it["repository"]["full_name"] for it in items)
        have = {it["sha"] for it in items}
        gaps = sorted(((n - seen[full], full) for full, n in self.activity_months()["commits"].items()
                       if n > seen[full] and seen[full] < 50), reverse=True)  # 50+: a cron, or sampled enough
        out = []
        for _, full in gaps[:GAP_REPOS]:
            if not self.can_spend():
                self.skip(f"commits in {full} for the clock sample")
                continue
            try:
                rows = self.api(f"repos/{full}/commits", author=self.user, per_page=100,
                                since=f"{self.year}-01-01T00:00:00Z", until=f"{self.year}-12-31T23:59:59Z")[0]
            except RuntimeError as exc:
                self.skip(f"commits in {full} ({str(exc)[:80]})")
                continue
            out += [{**r, "repository": {"full_name": full}} for r in rows if r["sha"] not in have]
        return out

    def repo_node(self, full: str, count: int, detail: bool) -> dict:
        """One commitContributionsByRepository row."""
        owner, name = full.split("/", 1)
        row = next((r for r in self.own_repos() if r["full_name"].lower() == full.lower()), None)
        if row is None and detail and self.can_spend():
            try:
                row = self.api(f"repos/{full}")[0]
            except RuntimeError:
                row = None
        row = row or {}
        language = row.get("language")
        edges = []
        if detail and row and self.can_spend():
            try:
                edges = [{"size": size, "node": {"name": lang, "color": LANGUAGE_COLORS.get(lang)}}
                         for lang, size in self.api(f"repos/{full}/languages")[0].items()][:8]
            except RuntimeError:
                pass
        return {
            "contributions": {"totalCount": count},
            "repository": {
                "nameWithOwner": full, "name": name, "isPrivate": False, "isFork": bool(row.get("fork")),
                "stargazerCount": row.get("stargazers_count", 0), "description": row.get("description"),
                "owner": {"login": owner},
                "primaryLanguage": {"name": language, "color": LANGUAGE_COLORS.get(language)} if language else None,
                "languages": {"edges": edges},
            },
        }

    # the queries --------------------------------------------------------

    def q_profile(self) -> dict:
        try:
            prof = self.api(f"users/{self.user}")[0]
        except RuntimeError as exc:
            if "404" in str(exc):
                return {"user": None}
            raise SystemExit(f"GitHub refused the anonymous profile read: {exc}. "
                             "The limit is 60 requests an hour per IP, so try again within the hour.")
        days, total = self.calendar(self.year)
        act = self.activity_months()
        sample = self.commits()
        counts = collections.Counter(act["commits"]) or collections.Counter(
            {k: len(v) for k, v in sample.items()})
        rows = [self.repo_node(full, n, i < max(TOP_REPOS, LANGUAGE_REPOS))
                for i, (full, n) in enumerate(counts.most_common())]
        year_s = str(self.year)
        return {"user": {
            "id": str(prof["id"]), "login": prof["login"], "name": (prof.get("name") or "").strip() or None,
            "avatarUrl": prof["avatar_url"], "createdAt": prof["created_at"], "bio": prof.get("bio"),
            "company": prof.get("company"), "location": prof.get("location"),
            "followers": {"totalCount": prof.get("followers", 0)},
            "contributionsCollection": {
                "totalCommitContributions": sum(counts.values()),
                "totalPullRequestContributions": self.pr_total(),
                "totalPullRequestReviewContributions": act["reviews"],
                "totalIssueContributions": act["issues"],
                "totalRepositoryContributions": sum(1 for r in self.own_repos() if r["created_at"][:4] == year_s),
                "restrictedContributionsCount": act["private"],
                "contributionCalendar": {"totalContributions": total, "weeks": [{"contributionDays": days}]},
                "commitContributionsByRepository": rows,
                "pullRequestReviewContributionsByRepository": [],
            },
        }}

    def pr_total(self) -> int:
        self.load_prs()
        return sum(len(v) for v in self.prs_by_month.values())

    def load_prs(self) -> None:
        """The year's PRs in one search, cut into months for collect.py's monthly asks."""
        if self.prs_by_month is not None:
            return
        end = min(dt.date(self.year, 12, 31), self.today)
        items, page, total = [], 1, 0
        while page <= 10:
            got = self.search("search/issues", q=f"author:{self.user} type:pr created:{self.year}-01-01..{end}",
                              per_page=100, page=page)
            total = got.get("total_count", 0)
            items += got.get("items", [])
            if len(items) >= total or not got.get("items"):
                break
            page += 1
        if total > len(items):
            self.skip(f"{total - len(items)} PRs past search's 1,000 result cap")
        merged = [i for i in items if (i.get("pull_request") or {}).get("merged_at")]
        # all or none: the film sums these into a lines number
        budget = self.core_left - CORE_RESERVE - self.reserved_for_repos()
        detailed = len(merged) <= budget
        if not detailed:
            self.skip(f"line counts ({len(merged)} merged PRs, {budget} requests to spare)")
        by_month = collections.defaultdict(list)
        for it in items:
            full = it["repository_url"].split("/repos/", 1)[1]
            merged_at = (it.get("pull_request") or {}).get("merged_at")
            pull = {}
            if merged_at and detailed:
                try:
                    pull = self.api(f"repos/{full}/pulls/{it['number']}")[0]
                except RuntimeError as exc:
                    self.skip(f"line counts ({str(exc)[:80]})")
            by_month[it["created_at"][:7]].append({
                "title": it["title"], "number": it["number"], "createdAt": it["created_at"],
                "mergedAt": merged_at, "merged": bool(merged_at), "url": it["html_url"],
                "additions": pull.get("additions", 0), "deletions": pull.get("deletions", 0),
                "changedFiles": pull.get("changed_files", 0),
                "headRefName": (pull.get("head") or {}).get("ref"),
                "repository": {"nameWithOwner": full, "isPrivate": False,
                               "owner": {"login": full.split("/")[0]},
                               "stargazerCount": (pull.get("base") or {}).get("repo", {}).get("stargazers_count", 0)},
            })
        self.prs_by_month = dict(by_month)

    def reserved_for_repos(self) -> int:
        """Requests the later queries need: releases."""
        year_s = str(self.year)
        rows = self.own_repos()
        live = sum(1 for r in rows if not r.get("fork") and (r.get("pushed_at") or "")[:4] >= year_s)
        return min(live, RELEASE_REPOS)

    def q_prs(self, q: str) -> dict:
        self.load_prs()
        when = re.search(r"created:(\d{4}-\d{2})", q).group(1)
        return {"search": {"issueCount": len(self.prs_by_month.get(when, [])),
                           "pageInfo": {"hasNextPage": False, "endCursor": None},
                           "nodes": self.prs_by_month.get(when, [])}}

    def q_count(self, q: str) -> dict:
        try:
            return {"search": {"issueCount": self.search("search/issues", q=q, per_page=1).get("total_count", 0)}}
        except RuntimeError as exc:
            raise SystemExit(f"search failed: {exc}")

    def q_repos(self) -> dict:
        year_s = str(self.year)
        nodes, releases_read = [], 0
        for r in self.own_repos():
            tags = []
            live = not r.get("fork") and (r.get("pushed_at") or "")[:4] >= year_s
            if live:
                if releases_read < RELEASE_REPOS and self.can_spend():
                    releases_read += 1
                    try:
                        tags = self.api(f"repos/{r['full_name']}/releases", per_page=50)[0]
                    except RuntimeError:
                        self.skip(f"releases of {r['name']}")
                else:
                    self.skip(f"releases of {r['name']}")
            language = r.get("language")
            nodes.append({
                "nameWithOwner": r["full_name"], "name": r["name"], "createdAt": r["created_at"],
                "pushedAt": r.get("pushed_at"), "isPrivate": False, "isFork": bool(r.get("fork")),
                "stargazerCount": r.get("stargazers_count", 0), "forkCount": r.get("forks_count", 0),
                "description": r.get("description"),
                "primaryLanguage": {"name": language, "color": LANGUAGE_COLORS.get(language)} if language else None,
                "releases": {"nodes": [{"createdAt": t["created_at"], "tagName": t["tag_name"], "isDraft": t["draft"]}
                                       for t in tags]},
            })
        nodes.sort(key=lambda n: n["createdAt"], reverse=True)
        return {"user": {"repositories": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}

    def q_history(self, owner: str, name: str) -> dict:
        nodes = self.commits().get(f"{owner}/{name}", [])
        return {"repository": {"defaultBranchRef": {"target": {"history": {
            "totalCount": len(nodes), "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}}}

    def q_total(self, year: int) -> dict:
        return {"user": {"contributionsCollection": {"contributionCalendar": {"totalContributions": self.calendar(year)[1]}}}}

    def q_stars(self) -> dict:
        """When a star landed needs a login (the timestamps answer 401), so stars gained this year
        stay unknown. The film falls back on total stars, which build.py already does at zero."""
        self.skip("stars gained this year (GitHub needs a login for star dates)")
        return {"repository": {"stargazers": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "edges": []}}}

    def graphql(self, query: str, **v) -> dict:
        """collect.py's gh_graphql, answered without GraphQL."""
        if query is C.Q_PROFILE:
            return self.q_profile()
        if query is C.Q_PRS:
            return self.q_prs(v["q"])
        if query is C.Q_REPOS:
            return self.q_repos()
        if query is C.Q_HISTORY:
            return self.q_history(v["owner"], v["name"])
        if query is C.Q_TOTAL:
            return self.q_total(int(v["from"][:4]))
        if query is C.Q_STARS:
            return self.q_stars()
        if "issueCount" in query:
            return self.q_count(v["q"])
        raise SystemExit("collect_public: a query it does not know; add it here")


def run(user: str, year: int, tz: str | None, source: PublicSource | None = None) -> tuple[dict, dict]:
    """collect.collect() over the public source. tz None keeps each commit's own clock."""
    src = source or PublicSource(user, year)
    C.use_source(src.graphql, src.rest, search_gap=0.0, actions_budget=lambda: max(0, src.core_left - CORE_RESERVE),
                 actions_workers=2)
    data, raw = C.collect(user, year, tz, False)
    if data["actions"] is None or data["actions"].get("incomplete"):
        data["actions"] = None  # a partial total would read as a true, smaller number
        src.skip("Actions time (out of requests)")
    data["source"] = {
        "mode": "public",
        "method": "no token: REST, search and the public profile pages; private work is a count at most",
        "requests": dict(src.calls),
        "core_requests_left": src.core_left,
        "skipped": src.skipped,
    }
    return data, raw
