#!/usr/bin/env python3
"""Collect one GitHub user's year into a JSON file for the year-in-review video.

Stdlib only. Talks to GitHub through the authenticated `gh` CLI (`gh api graphql`),
so it sees whatever the caller's token can see.

    python3 collect.py --user octocat --year 2026 --out year.json [--tz Pacific/Auckland]
                       [--include-private] [--raw-cache raw.json]

Privacy default: private repositories are counted in totals but never named.
The video is made to be posted publicly; a private repo name in a LinkedIn post is a leak.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import time
from zoneinfo import ZoneInfo

HISTORY_REPOS = 6  # repos whose commit history is sampled for time-of-day and messages
HISTORY_PAGES = 5  # 100 commits per page, per repo
STAR_REPOS = 12  # owned repos whose stargazers are scanned for stars gained this year
RUN_PAGES_PER_REPO = 100  # Actions: 100 runs a page, so up to 10,000 runs a repo are timed
RUN_PAGE_BUDGET = 600  # Actions: pages across all repos (one REST call each); past it, estimated
RUN_MAX_MINUTES = 6 * 60  # a run longer than a hosted job's 6 h limit is clipped (stale updated_at)


def gh_graphql(query: str, **variables) -> dict:
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        flag = "-F" if isinstance(value, (int, bool)) else "-f"
        args += [flag, f"{key}={json.dumps(value) if isinstance(value, bool) else value}"]
    for attempt in range(3):  # GitHub answers a heavy search with a 502 now and then; retry
        proc = subprocess.run(args, capture_output=True, text=True)
        if proc.returncode == 0 or not re.search(r"HTTP 5\d\d|timeout", proc.stderr):
            break
        time.sleep(3 * (attempt + 1))
    if proc.returncode != 0:
        raise SystemExit(f"gh api graphql failed: {proc.stderr.strip()[:400]}")
    payload = json.loads(proc.stdout)
    if payload.get("errors"):
        raise SystemExit(f"GraphQL errors: {json.dumps(payload['errors'])[:400]}")
    return payload["data"]


Q_PROFILE = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    id login name avatarUrl createdAt bio company location
    followers{totalCount}
    contributionsCollection(from:$from,to:$to){
      totalCommitContributions totalPullRequestContributions
      totalPullRequestReviewContributions totalIssueContributions
      totalRepositoryContributions restrictedContributionsCount
      contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}
      commitContributionsByRepository(maxRepositories:100){
        contributions{totalCount}
        repository{nameWithOwner name isPrivate isFork stargazerCount description
          owner{login} primaryLanguage{name color}
          languages(first:8,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}
      }
      pullRequestReviewContributionsByRepository(maxRepositories:50){
        contributions{totalCount} repository{nameWithOwner isPrivate owner{login}}
      }
    }
  }
}"""

Q_PRS = """
query($q:String!,$after:String){
  search(query:$q,type:ISSUE,first:100,after:$after){
    issueCount
    pageInfo{hasNextPage endCursor}
    nodes{... on PullRequest{
      title number createdAt mergedAt merged additions deletions changedFiles url headRefName
      repository{nameWithOwner isPrivate owner{login} stargazerCount}
    }}
  }
}"""

Q_REPOS = """
query($login:String!,$after:String){
  user(login:$login){
    repositories(first:100,after:$after,ownerAffiliations:OWNER,orderBy:{field:CREATED_AT,direction:DESC}){
      pageInfo{hasNextPage endCursor}
      nodes{nameWithOwner name createdAt pushedAt isPrivate isFork stargazerCount forkCount description
        primaryLanguage{name color}
        releases(first:50,orderBy:{field:CREATED_AT,direction:DESC}){nodes{createdAt tagName isDraft}}}
    }
  }
}"""

Q_HISTORY = """
query($owner:String!,$name:String!,$author:ID!,$since:GitTimestamp!,$until:GitTimestamp!,$after:String){
  repository(owner:$owner,name:$name){
    defaultBranchRef{target{... on Commit{
      history(first:100,after:$after,since:$since,until:$until,author:{id:$author}){
        totalCount
        pageInfo{hasNextPage endCursor}
        nodes{committedDate authoredDate messageHeadline additions deletions}
      }
    }}}
  }
}"""

Q_TOTAL = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){contributionsCollection(from:$from,to:$to){contributionCalendar{totalContributions}}}
}"""

Q_STARS = """
query($owner:String!,$name:String!,$after:String){
  repository(owner:$owner,name:$name){
    stargazers(first:100,after:$after,orderBy:{field:STARRED_AT,direction:DESC}){
      pageInfo{hasNextPage endCursor}
      edges{starredAt}
    }
  }
}"""


def gh_rest(path: str, **params) -> dict:
    args = ["gh", "api", "-X", "GET", path]
    for key, value in params.items():
        args += ["-f", f"{key}={value}"]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300])
    return json.loads(proc.stdout)


SEARCH_GAP = 2.2  # seconds between commit searches: the search API allows 30 a minute
_last_search = [0.0]


def search_commits(q: str, waits: tuple = (20, 60, 120), **params) -> dict:
    """REST commit search, paced under the 30-a-minute limit, retried on a rate limit (the
    secondary limit clears in a minute or two). Raises RuntimeError when it never clears."""
    for attempt in range(len(waits) + 1):
        pause = _last_search[0] + SEARCH_GAP - time.time()
        if pause > 0:
            time.sleep(pause)
        _last_search[0] = time.time()
        try:
            return gh_rest("search/commits", q=q, **params)
        except RuntimeError as exc:
            if "rate limit" not in str(exc).lower() or attempt == len(waits):
                raise
            print(f"commit search rate limited; waiting {waits[attempt]} s", file=sys.stderr)
            time.sleep(waits[attempt])
    raise RuntimeError("unreachable")


# Coding agents leave a signature in the commit: a Co-authored-by trailer, a "Generated with"
# footer, a bot author, or a message prefix. Only these marks count; a commit that merely
# mentions an agent ("fix the codex runner") is not agent work, and an unmarked commit is
# counted as the person's own, so every agent number is a lower bound.
AGENT_SIGNATURES: list[tuple[str, re.Pattern]] = [
    ("Claude", re.compile(r"^co-authored-by:\s*claude\b|generated with \[?claude code|noreply@anthropic\.com", re.I | re.M)),
    ("Copilot", re.compile(r"^co-authored-by:\s*copilot\b|copilot-swe-agent|\+copilot@users\.noreply\.github\.com", re.I | re.M)),
    ("Codex", re.compile(r"^co-authored-by:\s*(?:openai\s+)?codex\b|chatgpt-codex-connector|codex@openai\.com", re.I | re.M)),
    ("Cursor", re.compile(r"cursoragent@cursor\.com|^co-authored-by:\s*cursor\b", re.I | re.M)),
    ("Devin", re.compile(r"devin-ai-integration|^co-authored-by:\s*devin\b", re.I | re.M)),
    ("Aider", re.compile(r"\Aaider:|^co-authored-by:\s*aider\b", re.I | re.M)),
    ("Jules", re.compile(r"google-labs-jules|^co-authored-by:\s*jules\b", re.I | re.M)),
    ("Gemini", re.compile(r"^co-authored-by:\s*gemini\b|gemini-code-assist", re.I | re.M)),
    ("Amp", re.compile(r"amp@ampcode\.com|^amp-thread(?:-id)?:", re.I | re.M)),
    ("OpenHands", re.compile(r"openhands@all-hands\.dev", re.I | re.M)),
]
AGENT_LOGINS = {"copilot-swe-agent": "Copilot", "copilot": "Copilot", "devin-ai-integration": "Devin",
                "google-labs-jules": "Jules", "chatgpt-codex-connector": "Codex", "cursor": "Cursor",
                "claude": "Claude"}
# Bots that are not agents: dependency updaters and CI. Neither the person nor an agent.
PLAIN_BOTS = re.compile(r"dependabot|renovate|github-actions|pre-commit-ci|greenkeeper|snyk-bot|mergify", re.I)
MODEL_RE = re.compile(r"^co-authored-by:\s*(claude[^<\n]*?|copilot[^<\n]*?|codex[^<\n]*?|gemini[^<\n]*?)\s*<", re.I | re.M)
# PRs: an agent opened it (bot author) or the body carries the agent's footer.
AGENT_PR_QUERIES = [
    ("Claude Code", '"Generated with Claude Code" in:body'),
    ("Codex", '"chatgpt.com/codex" in:body'),
    ("Copilot coding agent", "author:app/copilot-swe-agent"),
    ("Devin", "author:app/devin-ai-integration"),
    ("Jules", "author:app/google-labs-jules"),
    ("Cursor", '"cursor.com/agents" in:body'),
]


# Agent branches: the coding agents push to their own prefix (claude/fix-x, codex/add-y).
AGENT_BRANCHES = {"claude": "Claude Code", "codex": "Codex", "copilot": "Copilot coding agent",
                  "cursor": "Cursor", "devin": "Devin", "jules": "Jules"}


def classify_branch(ref: str | None) -> str | None:
    """The agent a PR head branch belongs to, from its prefix, else None."""
    head = (ref or "").lower().split("/", 1)
    return AGENT_BRANCHES.get(head[0]) if len(head) == 2 and head[1] else None


def merge_agent_prs(searched: dict, prs: list[dict]) -> list[tuple[str, int]]:
    """Agent PR counts per agent: the larger of the search count and the branch-prefix count.

    The two signals overlap (a claude/ branch usually carries the Claude Code footer too), so
    taking the max per agent never double counts; the result is a lower bound.
    """
    by_branch = collections.Counter(a for a in (classify_branch(p.get("headRefName")) for p in prs) if a)
    out = {k: max(searched.get(k, 0), by_branch.get(k, 0)) for k in set(searched) | set(by_branch)}
    return sorted(((k, v) for k, v in out.items() if v), key=lambda kv: (-kv[1], kv[0]))


def classify_commit(message: str, author_login: str | None = None, author_email: str | None = None) -> dict:
    """Which agents signed a commit, whether a plain bot made it, and any model names in trailers."""
    login = (author_login or "").lower().removesuffix("[bot]")
    agents = {name for name, rx in AGENT_SIGNATURES if rx.search(message or "")}
    if login in AGENT_LOGINS:
        agents.add(AGENT_LOGINS[login])
    if (author_email or "").lower() == "cursoragent@cursor.com":
        agents.add("Cursor")
    bot = None
    if not agents and (PLAIN_BOTS.search(login) or login.endswith("bot") and "[bot]" in (author_login or "")):
        bot = login
    models = [" ".join(m.split()) for m in MODEL_RE.findall(message or "")]
    return {"agents": sorted(agents), "bot": bot, "models": models}


def month_ranges(start: dt.date, end: dt.date) -> list[tuple[dt.date, dt.date]]:
    out = []
    d = start
    while d <= end:
        nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        out.append((d, min(end, nxt - dt.timedelta(days=1))))
        d = nxt
    return out


def agent_sample(user: str, start: dt.date, end: dt.date, exclude: list[str], per_month: int = 100) -> dict:
    """Month-stratified commit search: up to `per_month` commits a month with full messages.

    The search API returns message bodies (trailers included) across every repo the token can
    see, so this works for anyone with gh auth. Automation repos are excluded up front.
    Shares are weighted by each month's total so a busy month counts for what it was.
    """
    skip = " ".join(f"-repo:{r}" for r in exclude)
    months, by_agent, models, first_seen = [], collections.Counter(), collections.Counter(), None
    model_first: dict[str, str] = {}
    total = sampled = agent_hits = bot_hits = 0
    est_agent = est_by = 0.0
    est_by_agent = collections.Counter()
    for a, b in month_ranges(start, end):
        q = f"author:{user} author-date:{a}..{b} {skip}".strip()
        try:
            page = search_commits(q, per_page=per_month, sort="author-date", order="desc")
        except RuntimeError as exc:  # rate limit or a search outage: record and carry on
            months.append({"month": a.month, "total": None, "sampled": 0, "agent": 0, "error": str(exc)[:120]})
            continue
        items = page.get("items", [])
        n_total = page.get("total_count", 0)
        hits = 0
        month_by = collections.Counter()
        for it in items:
            c = classify_commit(it["commit"]["message"], (it.get("author") or {}).get("login"),
                                it["commit"]["author"].get("email"))
            if c["agents"]:
                hits += 1
                for ag in c["agents"]:
                    month_by[ag] += 1
                models.update(c["models"])
                when = it["commit"]["author"]["date"][:10]
                first_seen = min(first_seen or when, when)
                for m in c["models"]:
                    key = model_key(m)
                    if key:
                        model_first[key] = min(model_first.get(key, when), when)
            elif c["bot"]:
                bot_hits += 1
        k = len(items)
        total += n_total
        sampled += k
        agent_hits += hits
        by_agent.update(month_by)
        if k:
            est_agent += n_total * hits / k
            for ag, v in month_by.items():
                est_by_agent[ag] += n_total * v / k
        months.append({"month": a.month, "total": n_total, "sampled": k, "agent": hits})
    share = est_agent / total if total else 0.0
    return {
        "method": ("REST commit search author:<user>, one page of up to "
                   f"{per_month} per month, automation repos excluded; agent = signature in the "
                   "commit (Co-authored-by trailer, Generated-with footer, agent bot author)"),
        "excluded_repos": exclude,
        "commits_total": total,
        "sampled": sampled,
        "coverage": round(sampled / total, 4) if total else 0,
        "agent_commits_sampled": agent_hits,
        "plain_bot_commits_sampled": bot_hits,
        "agent_share": round(share, 4),
        "agent_commits_est": round(est_agent),
        "by_agent": [[ag, round(v)] for ag, v in est_by_agent.most_common()],
        "by_agent_sampled": by_agent.most_common(),
        "models": models.most_common(5),
        "by_month": months,
        "first_seen": first_seen,
        # versioned model name -> earliest date in the sample; refined by model_first_dates()
        "model_first_seen": sorted(([k, v] for k, v in model_first.items()), key=lambda kv: kv[1]),
    }


def model_key(name: str) -> str | None:
    """A trailer's model name as one timeline entry: "Claude Opus 4.6 (1M context)" ->
    "Claude Opus 4.6". Names without a version ("Claude", "claude[bot]") are not models."""
    key = " ".join(re.sub(r"\s*\(.*?\)|\[bot\]", "", name).split())
    return key if re.search(r"\d", key) else None


def model_first_dates(user: str, start: dt.date, end: dt.date, sampled: list, exclude: list[str]) -> list:
    """The first commit of the year each model co-signed. The monthly sample sees at most 100
    commits a month, newest first, so its first-seen date can run late; one search per model,
    oldest first, finds the real first trailer. A hit only counts when the commit's own trailer
    names that model; otherwise the sample's date stands."""
    skip = " ".join(f"-repo:{r}" for r in exclude)
    out = []
    for key, seen in sampled:
        when = seen
        q = f'author:{user} author-date:{start}..{end} "Co-authored-by: {key}" {skip}'.strip()
        try:
            items = search_commits(q, per_page=10, sort="author-date", order="asc").get("items", [])
        except RuntimeError:
            items = []
        for it in items:
            if key in {model_key(m) for m in classify_commit(it["commit"]["message"])["models"]}:
                when = min(when, it["commit"]["author"]["date"][:10])
                break
        out.append([key, when])
    return sorted(out, key=lambda kv: kv[1])


def iso_time(x: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(x.replace("Z", "+00:00")) if x else None


def run_minutes(run: dict) -> float:
    """Wall-clock minutes of one completed workflow run: run_started_at (the latest attempt)
    to updated_at (when it finished), clipped to [0, RUN_MAX_MINUTES]. Not billable minutes:
    parallel jobs count once, so this is how long you waited, not what a bill would say."""
    if run.get("status") != "completed":
        return 0.0
    a, b = iso_time(run.get("run_started_at") or run.get("created_at")), iso_time(run.get("updated_at"))
    if not a or not b:
        return 0.0
    return min(RUN_MAX_MINUTES, max(0.0, (b - a).total_seconds() / 60))


def summarise_runs(runs: list[dict], year: int, zone: ZoneInfo) -> dict:
    """Minutes, run count and minutes by month for the runs that started in `year`."""
    by_month = [0.0] * 12
    count = 0
    for r in runs:
        when = iso_time(r.get("run_started_at") or r.get("created_at"))
        if not when:
            continue
        when = when.astimezone(zone)
        if when.year != year:
            continue
        count += 1
        by_month[when.month - 1] += run_minutes(r)
    return {"runs": count, "minutes": sum(by_month), "by_month": by_month}


def repo_runs(full: str, start: dt.datetime, pages: int, budget: list | None = None,
              lock: threading.Lock | None = None) -> tuple[list[dict], bool]:
    """Workflow runs of one repo, newest first, back to `start`. Unfiltered listing (a `created`
    filter caps at 1,000 results). Stops at `pages`, or when the shared page `budget` ([n]) is
    spent; returns (runs, capped)."""
    runs = []
    cutoff = start.isoformat().replace("+00:00", "Z")
    for page in range(1, pages + 1):
        if budget is not None:
            with lock or threading.Lock():
                if budget[0] <= 0:
                    return runs, True
                budget[0] -= 1
        data = gh_rest(f"repos/{full}/actions/runs", per_page=100, page=page)
        batch = data.get("workflow_runs") or []
        runs += [{k: r.get(k) for k in ("status", "created_at", "run_started_at", "updated_at")} for r in batch]
        if len(batch) < 100 or (batch[-1].get("created_at") or "") < cutoff:
            return runs, False
    return runs, True


def actions_time(owned: list[dict], user: str, year: int, start: dt.datetime, zone: ZoneInfo,
                 include_private: bool, budget: int = RUN_PAGE_BUDGET, workers: int = 6) -> dict | None:
    """Total GitHub Actions run time on the user's own (non-fork) repos pushed this year.

    One REST page per 100 runs, repos read in parallel. A repo past RUN_PAGES_PER_REPO pages,
    or cut off when the page budget is spent, has the rest of its year estimated from its run
    count times the mean minutes per run seen, and is listed in `estimated_repos`.
    None when no repo could be read."""
    year_s = str(year)
    repos = [r for r in owned if not r.get("isFork") and (r.get("pushedAt") or r.get("createdAt") or "")[:4] >= year_s]
    left, lock = [budget], threading.Lock()

    errors: list[str] = []

    def one(r):
        for attempt in range(2):  # one retry: a secondary rate limit clears in seconds
            try:
                return r, repo_runs(r["nameWithOwner"], start, RUN_PAGES_PER_REPO, left, lock)
            except RuntimeError as exc:  # Actions disabled, no access, or an outage
                if attempt:
                    errors.append(str(exc)[:120])
                else:
                    time.sleep(5)
        return r, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, repos))
    by_month = [0.0] * 12
    runs = read = 0
    minutes = 0.0
    by_repo, estimated, pending, timed = collections.Counter(), [], [], {}
    for r, got in results:
        if got is None:
            continue
        got_runs, capped = got
        read += 1
        s = summarise_runs(got_runs, year, zone)
        if capped:
            pending.append(r)
        runs += s["runs"]
        minutes += s["minutes"]
        by_month = [a + b for a, b in zip(by_month, s["by_month"])]
        timed[r["nameWithOwner"]] = s["runs"]
        by_repo[public_name(r, include_private)] += s["minutes"]
    mean = minutes / runs if runs else 0.0
    est_minutes = 0.0
    for r in pending:  # count the runs we did not time; estimate their minutes from the mean
        try:
            total = gh_rest(f"repos/{r['nameWithOwner']}/actions/runs", per_page=1,
                            created=f"{year}-01-01..{year}-12-31").get("total_count", 0)
        except RuntimeError:
            continue
        extra = max(0, total - timed.get(r["nameWithOwner"], 0))
        if not extra:
            continue
        est_minutes += extra * mean
        runs += extra
        estimated.append([public_name(r, include_private), extra])
    print(f"actions: {read} of {len(repos)} repos read, {len(pending)} past the page cap, "
          f"{len(errors)} unreadable {errors[:1]}", file=sys.stderr)
    if not read:
        return None
    total_minutes = minutes + est_minutes
    return {
        "method": (f"REST actions/runs on owned non-fork repos pushed this year, every run listed (up to {budget} pages, "
                   f"{RUN_PAGES_PER_REPO} a repo; the rest estimated from the mean); "
                   "minutes = run_started_at to updated_at of completed runs (wall clock, parallel "
                   f"jobs once), clipped at {RUN_MAX_MINUTES} min a run; not billable minutes"),
        "minutes": round(total_minutes),
        "minutes_measured": round(minutes),
        "runs": runs,
        "repos": sum(1 for k in timed.values() if k),
        "by_month": [round(x) for x in by_month],  # measured runs only, by local start month
        "by_repo": [[name, round(m)] for name, m in by_repo.most_common(6) if m >= 1],
        "estimated_repos": estimated,
        "estimated": bool(estimated),
        "unreadable_repos": len(errors),
    }


def public_name(repo: dict, include_private: bool) -> str:
    if repo.get("isPrivate") and not include_private:
        return "a private repo"
    return repo["nameWithOwner"]


def template_share(commits: list[dict]) -> float:
    """Share of commits whose headline matches the most common normalised template."""
    if not commits:
        return 0.0
    norm = collections.Counter(
        " ".join(re.sub(r"[0-9a-f]{7,}|\d+", "#", c["messageHeadline"].lower()).split()[:4]) for c in commits
    )
    return norm.most_common(1)[0][1] / len(commits)


def search_count(q: str) -> int:
    return gh_graphql("query($q:String!){search(query:$q,type:ISSUE,first:1){issueCount}}", q=q)["search"]["issueCount"]


def streaks(days: list[dict]) -> dict:
    longest = cur = 0
    longest_end = None
    for d in days:
        if d["contributionCount"] > 0:
            cur += 1
            if cur > longest:
                longest, longest_end = cur, d["date"]
        else:
            cur = 0
    start = None
    if longest_end:
        start = (dt.date.fromisoformat(longest_end) - dt.timedelta(days=longest - 1)).isoformat()
    return {"longest": longest, "start": start, "end": longest_end, "current": cur}


VERB_RE = re.compile(r"^(?:[\w-]+(?:\([^)]*\))?!?:\s*)?([A-Za-z]+)")


def commit_verb(message: str) -> str | None:
    """First word of a commit headline, skipping a conventional-commit prefix."""
    m = VERB_RE.match(message.strip())
    if not m:
        return None
    word = m.group(1).lower()
    return word if len(word) > 1 else None


def collect(user: str, year: int, tz: str, include_private: bool) -> tuple[dict, dict]:
    zone = ZoneInfo(tz)
    today = dt.datetime.now(dt.timezone.utc)
    start = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
    end = min(dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc), today)
    is_partial = end < dt.datetime(year, 12, 31, tzinfo=dt.timezone.utc)
    raw: dict = {}

    prof = gh_graphql(Q_PROFILE, login=user, **{"from": start.isoformat(), "to": end.isoformat()})["user"]
    if prof is None:
        raise SystemExit(f"No GitHub user {user!r}")
    raw["profile"] = prof
    cc = prof["contributionsCollection"]

    # Calendar: only days inside the year (the calendar pads to whole weeks).
    days = [
        d
        for w in cc["contributionCalendar"]["weeks"]
        for d in w["contributionDays"]
        if d["date"].startswith(str(year)) and d["date"] <= end.date().isoformat()
    ]
    active = [d for d in days if d["contributionCount"] > 0]
    busiest = max(days, key=lambda d: d["contributionCount"]) if days else None
    by_month = collections.Counter()
    by_weekday = collections.Counter()
    for d in days:
        date = dt.date.fromisoformat(d["date"])
        by_month[date.month] += d["contributionCount"]
        by_weekday[date.weekday()] += d["contributionCount"]
    weekend = by_weekday[5] + by_weekday[6]
    total_cal = sum(d["contributionCount"] for d in days)

    # Repositories committed to.
    repos = []
    for item in cc["commitContributionsByRepository"]:
        r = item["repository"]
        repos.append(
            {
                "name": public_name(r, include_private),
                "short": r["name"] if (include_private or not r["isPrivate"]) else "private",
                "private": r["isPrivate"],
                "owner": r["owner"]["login"],
                "commits": item["contributions"]["totalCount"],
                "stars": r["stargazerCount"],
                "language": (r["primaryLanguage"] or {}).get("name"),
                "color": (r["primaryLanguage"] or {}).get("color"),
                "description": r["description"] if (include_private or not r["isPrivate"]) else None,
                "_owner": r["owner"]["login"],
                "_name": r["name"],
                "_langs": r["languages"]["edges"],
            }
        )
    repos.sort(key=lambda r: -r["commits"])

    # Languages: each repo's byte mix, weighted by the user's commits to it.
    lang_weight = collections.Counter()
    lang_color = {}
    for r in repos:
        total = sum(e["size"] for e in r["_langs"]) or 0
        if total:
            for e in r["_langs"]:
                lang_weight[e["node"]["name"]] += r["commits"] * e["size"] / total
                lang_color[e["node"]["name"]] = e["node"]["color"]
        elif r["language"]:
            lang_weight[r["language"]] += r["commits"]
            lang_color[r["language"]] = r["color"]
    lw_total = sum(lang_weight.values()) or 1
    languages = [
        {"name": n, "share": round(w / lw_total, 4), "color": lang_color.get(n)}
        for n, w in lang_weight.most_common(8)
    ]

    # Pull requests authored this year.
    # Search returns at most 1,000 results a query, so the year is fetched a month at a time;
    # a month past 1,000 PRs is still capped, and `sampled` < `opened` says so.
    q = f"author:{user} type:pr created:{start.date()}..{end.date()}"
    prs = []
    for a, b in month_ranges(start.date(), end.date()):
        after = None
        for _ in range(10):
            page = gh_graphql(Q_PRS, q=f"author:{user} type:pr created:{a}..{b}", after=after)["search"]
            prs += [n for n in page["nodes"] if n]
            if not page["pageInfo"]["hasNextPage"]:
                break
            after = page["pageInfo"]["endCursor"]
    raw["prs"] = prs
    pr_opened = search_count(q)
    pr_merged = search_count(q + " is:merged")
    merged = [p for p in prs if p["merged"]]
    external = [p for p in merged if p["repository"]["owner"]["login"].lower() != user.lower()]
    ext_repos = collections.Counter(public_name(p["repository"], include_private) for p in external)
    # Biggest merged PR by lines changed; a nameable one first, so the film can show its title.
    nameable = [p for p in merged if include_private or not p["repository"]["isPrivate"]]
    biggest = max(nameable or merged, key=lambda p: p["additions"] + p["deletions"], default=None)
    lines_added = sum(p["additions"] for p in merged)
    lines_removed = sum(p["deletions"] for p in merged)
    merged_by_day = collections.Counter((p.get("mergedAt") or "")[:10] for p in merged)  # UTC, like the calendar
    pr_by_repo = collections.Counter(public_name(p["repository"], include_private) for p in merged)
    # Open-source contributions: merged PRs into public repos owned by someone else.
    external_public = collections.Counter(
        p["repository"]["nameWithOwner"] for p in external if not p["repository"]["isPrivate"]
    )
    ext_stars = {p["repository"]["nameWithOwner"]: p["repository"]["stargazerCount"] for p in external}
    biggest_external = max([p for p in external if not p["repository"]["isPrivate"] or include_private], key=lambda p: p["repository"]["stargazerCount"], default=None)

    # Owned repositories: which were born this year.
    owned, after = [], None
    for _ in range(10):
        page = gh_graphql(Q_REPOS, login=user, after=after)["user"]["repositories"]
        owned += page["nodes"]
        if not page["pageInfo"]["hasNextPage"] or page["nodes"][-1]["createdAt"] < start.isoformat():
            break
        after = page["pageInfo"]["endCursor"]
    raw["owned"] = owned
    born = [
        r
        for r in owned
        if r["createdAt"][:4] == str(year) and not r["isFork"] and (include_private or not r["isPrivate"])
    ]
    born_private = sum(1 for r in owned if r["createdAt"][:4] == str(year) and not r["isFork"] and r["isPrivate"])

    # Stars gained this year on owned public repos.
    stars_gained = collections.Counter()
    starrable = sorted(
        [r for r in owned if not r["isPrivate"] and r["stargazerCount"] > 0], key=lambda r: -r["stargazerCount"]
    )[:STAR_REPOS]
    for r in starrable:
        owner, name = r["nameWithOwner"].split("/")
        after = None
        for _ in range(20):
            page = gh_graphql(Q_STARS, owner=owner, name=name, after=after)["repository"]["stargazers"]
            stamps = [e["starredAt"] for e in page["edges"]]
            stars_gained[r["nameWithOwner"]] += sum(1 for s in stamps if s[:4] == str(year))
            if not page["pageInfo"]["hasNextPage"] or (stamps and stamps[-1][:4] < str(year)):
                break
            after = page["pageInfo"]["endCursor"]

    # Commit history sample: time of day, weekday, commit verbs.
    # Repos whose commits are mostly one repeated message are automation (a cron, a bot
    # committing as the user). They are reported separately and kept out of the rhythm stats,
    # so "night owl" describes the person, not their scheduler.
    hours = collections.Counter()
    weekdays = collections.Counter()
    week_hours = collections.Counter()  # (weekday, hour): the punchcard
    verbs = collections.Counter()
    sampled = 0
    late = None  # latest-night commit (by local clock between 00:00 and 04:00, latest wins)
    first_commit = None
    automated = []
    automated_full = []  # real nameWithOwner, used only to exclude them from searches
    for r in repos[:HISTORY_REPOS]:
        after = None
        commits = []
        for _ in range(HISTORY_PAGES):
            data = gh_graphql(
                Q_HISTORY,
                owner=r["_owner"],
                name=r["_name"],
                author=prof["id"],
                since=start.isoformat(),
                until=end.isoformat(),
                after=after,
            )
            ref = (data["repository"] or {}).get("defaultBranchRef")
            if not ref:
                break
            hist = ref["target"]["history"]
            commits += hist["nodes"]
            if not hist["pageInfo"]["hasNextPage"]:
                break
            after = hist["pageInfo"]["endCursor"]
        share = template_share(commits)
        if len(commits) >= 50 and share >= 0.6:
            automated.append({"name": r["name"], "commits": r["commits"], "template_share": round(share, 3)})
            automated_full.append(f"{r['_owner']}/{r['_name']}")
            continue
        for c in commits:
            when = dt.datetime.fromisoformat(c["committedDate"].replace("Z", "+00:00")).astimezone(zone)
            hours[when.hour] += 1
            weekdays[when.weekday()] += 1
            week_hours[(when.weekday(), when.hour)] += 1
            sampled += 1
            v = commit_verb(c["messageHeadline"])
            if v:
                verbs[v] += 1
            if when.hour < 4 and (late is None or when.time() > late["_t"]):
                late = {"_t": when.time(), "time": when.strftime("%H:%M"), "date": when.date().isoformat(),
                        "repo": r["name"]}
            if first_commit is None or c["committedDate"] < first_commit["at"]:
                first_commit = {"at": c["committedDate"], "repo": r["name"], "message": c["messageHeadline"]
                                if not r["private"] or include_private else None}
    if late:
        late.pop("_t")
    peak_hour = max(hours, key=hours.get) if hours else None
    night_share = sum(hours[h] for h in (22, 23, 0, 1, 2, 3, 4)) / sampled if sampled else 0
    morning_share = sum(hours[h] for h in (5, 6, 7, 8)) / sampled if sampled else 0

    years_on_github = year - int(prof["createdAt"][:4])

    # Agents: commit signatures from a month-stratified search sample, and PRs agents opened
    # or co-wrote. Optional in the film: the beat only shows when agents were actually there.
    agents = agent_sample(user, start.date(), end.date(), automated_full)
    agents["model_first_seen"] = model_first_dates(user, start.date(), end.date(), agents["model_first_seen"],
                                                   automated_full)
    pr_range = f"created:{start.date()}..{end.date()}"
    agent_prs = {}
    for name, sig in AGENT_PR_QUERIES:
        scope = f"type:pr user:{user} {sig}" if sig.startswith("author:app/") else f"author:{user} type:pr {sig}"
        try:
            k = search_count(f"{scope} {pr_range}")
        except SystemExit:
            k = 0
        if k:
            agent_prs[name] = agent_prs.get(name, 0) + k
    agents["prs"] = merge_agent_prs(agent_prs, prs)
    agents["prs_total"] = sum(k for _, k in agents["prs"])

    # Year on year: the two years before, one cheap call each (0 before the account existed).
    history = []
    for y in (year - 2, year - 1):
        if y < int(prof["createdAt"][:4]):
            continue
        a = dt.datetime(y, 1, 1, tzinfo=dt.timezone.utc)
        b = dt.datetime(y, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)
        tot = gh_graphql(Q_TOTAL, login=user, **{"from": a.isoformat(), "to": b.isoformat()})["user"]
        history.append({"year": y, "contributions": tot["contributionsCollection"]["contributionCalendar"]["totalContributions"]})

    # Primary language of each owned, non-fork repo pushed this year (private ones counted, never named).
    live = [r for r in owned if not r.get("isFork") and (r.get("pushedAt") or r.get("createdAt") or "")[:4] >= str(year)]
    by_lang = collections.Counter((r.get("primaryLanguage") or {}).get("name") for r in live)
    repo_languages = {"repos": len(live), "with_language": sum(v for k, v in by_lang.items() if k),
                      "by_language": [[k, v] for k, v in by_lang.most_common() if k]}

    # Releases published this year on owned repos (private ones counted, never named).
    releases = []
    for r in owned:
        tags = [x for x in (r.get("releases") or {}).get("nodes", []) if x["createdAt"][:4] == str(year) and not x["isDraft"]]
        if tags:
            named = include_private or not r["isPrivate"]
            releases.append({"repo": r["name"] if named else None, "count": len(tags),
                             "first": tags[-1]["tagName"] if named else None,
                             "latest": tags[0]["tagName"] if named else None,
                             "latest_date": tags[0]["createdAt"][:10],
                             "dates": sorted(x["createdAt"][:10] for x in tags) if named else []})
    releases.sort(key=lambda x: -x["count"])

    # GitHub Actions time on the user's own repos (optional beat; None when unreadable).
    actions = actions_time(owned, user, year, start, zone, include_private)

    for r in repos:
        for k in [k for k in r if k.startswith("_")]:
            r.pop(k)

    out = {
        "schema": 2,
        "user": {
            "login": prof["login"],
            "name": prof["name"] or prof["login"],
            "avatar_url": prof["avatarUrl"],
            "joined": prof["createdAt"][:10],
            "years_on_github": years_on_github,
            "followers": prof["followers"]["totalCount"],
        },
        "period": {
            "year": year,
            "from": start.date().isoformat(),
            "to": end.date().isoformat(),
            "partial": is_partial,
            "days": len(days),
            "timezone": tz,
        },
        "totals": {
            "contributions": cc["contributionCalendar"]["totalContributions"],
            "calendar_sum": total_cal,
            "commits": cc["totalCommitContributions"],
            "prs": cc["totalPullRequestContributions"],
            "reviews": cc["totalPullRequestReviewContributions"],
            "issues": cc["totalIssueContributions"],
            "repos_created": cc["totalRepositoryContributions"],
            "private_contributions": cc["restrictedContributionsCount"],
        },
        "calendar": [[d["date"], d["contributionCount"]] for d in days],
        "rhythm": {
            "active_days": len(active),
            "active_share": round(len(active) / len(days), 4) if days else 0,
            "streak": streaks(days),
            "busiest_day": ({"date": busiest["date"], "count": busiest["contributionCount"],
                             "prs_merged": merged_by_day.get(busiest["date"], 0)} if busiest else None),
            "by_month": [by_month[m] for m in range(1, 13)],
            "by_weekday": [by_weekday[i] for i in range(7)],  # Monday first
            "weekend_share": round(weekend / total_cal, 4) if total_cal else 0,
            "peak_hour": peak_hour,
            "by_hour": [hours[h] for h in range(24)],
            "night_share": round(night_share, 4),
            "morning_share": round(morning_share, 4),
            "latest_night_commit": late,
            "commits_sampled": sampled,
            "by_weekday_sampled": [weekdays[i] for i in range(7)],
            "by_weekday_hour": [[week_hours[(w, h)] for h in range(24)] for w in range(7)],  # Monday first, local
        },
        "automation": {
            "repos": automated,
            "commits": sum(a["commits"] for a in automated),
        },
        "repos": repos[:12],
        "repo_count": len(repos),
        "languages": languages,
        "pull_requests": {
            "opened": pr_opened,
            "merged": pr_merged,
            "merge_rate": round(pr_merged / pr_opened, 4) if pr_opened else 0,
            "sampled": len(prs),
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "biggest": (
                {
                    "title": biggest["title"] if (include_private or not biggest["repository"]["isPrivate"]) else None,
                    "repo": public_name(biggest["repository"], include_private),
                    "additions": biggest["additions"],
                    "deletions": biggest["deletions"],
                    "files": biggest["changedFiles"],
                    "number": biggest["number"] if (include_private or not biggest["repository"]["isPrivate"]) else None,
                    "private": biggest["repository"]["isPrivate"],
                }
                if biggest
                else None
            ),
            "by_repo": pr_by_repo.most_common(6),
            "external_merged": len(external),
            "external_repos": ext_repos.most_common(6),
            "external_public": external_public.most_common(6),
            "external_public_stars": {k: ext_stars[k] for k, _ in external_public.most_common(6)},
            "most_starred_external": (
                {
                    "repo": public_name(biggest_external["repository"], include_private),
                    "stars": biggest_external["repository"]["stargazerCount"],
                    "title": biggest_external["title"],
                }
                if biggest_external
                else None
            ),
        },
        "new_repos": [
            {
                "name": r["name"],
                "created": r["createdAt"][:10],
                "stars": r["stargazerCount"],
                "language": (r["primaryLanguage"] or {}).get("name"),
                "description": r["description"],
            }
            for r in sorted(born, key=lambda r: (-r["stargazerCount"], r["createdAt"]))
        ],
        "new_private_repos": born_private,
        "stars": {
            "gained": sum(stars_gained.values()),
            "by_repo": stars_gained.most_common(5),
            "total_owned": sum(r["stargazerCount"] for r in owned if not r["isPrivate"]),
        },
        "agents": agents,
        "actions": actions,
        "history": history,
        "repo_languages": repo_languages,
        "releases": {"total": sum(x["count"] for x in releases), "repos": releases[:6]},
        "commit_verbs": verbs.most_common(8),
        "first_commit": first_commit,
    }
    return out, raw


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--user", help="GitHub login (default: the authenticated gh user)")
    p.add_argument("--year", type=int, default=dt.date.today().year)
    p.add_argument("--tz", default=None, help="IANA timezone for time-of-day stats (default: this machine's)")
    p.add_argument("--include-private", action="store_true", help="name private repos (off by default)")
    p.add_argument("--out", default="year.json")
    p.add_argument("--raw-cache", help="also write the raw API payloads here")
    a = p.parse_args(argv)
    user = a.user or subprocess.run(["gh", "api", "user", "-q", ".login"], capture_output=True, text=True).stdout.strip()
    if not user:
        raise SystemExit("No --user and gh is not authenticated")
    tz = a.tz or local_tz()
    data, raw = collect(user, a.year, tz, a.include_private)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(data, fh, indent=2)
    if a.raw_cache:
        with open(a.raw_cache, "w") as fh:
            json.dump(raw, fh)
    t = data["totals"]
    print(
        f"{user} {a.year}: {t['contributions']} contributions, {t['commits']} commits, "
        f"{data['pull_requests']['merged']} merged PRs, {data['rhythm']['active_days']} active days -> {a.out}",
        file=sys.stderr,
    )
    return 0


def local_tz() -> str:
    try:
        import os

        link = os.readlink("/etc/localtime")
        return link.split("zoneinfo/", 1)[1]
    except (OSError, IndexError):
        return "UTC"


if __name__ == "__main__":
    sys.exit(main())
