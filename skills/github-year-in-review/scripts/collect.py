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
import datetime as dt
import json
import os
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

HISTORY_REPOS = 6  # repos whose commit history is sampled for time-of-day and messages
HISTORY_PAGES = 5  # 100 commits per page, per repo
STAR_REPOS = 12  # owned repos whose stargazers are scanned for stars gained this year


def gh_graphql(query: str, **variables) -> dict:
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        flag = "-F" if isinstance(value, (int, bool)) else "-f"
        args += [flag, f"{key}={json.dumps(value) if isinstance(value, bool) else value}"]
    proc = subprocess.run(args, capture_output=True, text=True)
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
      nodes{nameWithOwner name createdAt isPrivate isFork stargazerCount forkCount description
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
    total = sampled = agent_hits = bot_hits = 0
    est_agent = est_by = 0.0
    est_by_agent = collections.Counter()
    for a, b in month_ranges(start, end):
        q = f"author:{user} author-date:{a}..{b} {skip}".strip()
        try:
            page = gh_rest("search/commits", q=q, per_page=per_month, sort="author-date", order="desc")
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
    q = f"author:{user} type:pr created:{start.date()}..{end.date()}"
    prs, after = [], None
    for _ in range(10):
        page = gh_graphql(Q_PRS, q=q, after=after)["search"]
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
            "busiest_day": {"date": busiest["date"], "count": busiest["contributionCount"]} if busiest else None,
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
