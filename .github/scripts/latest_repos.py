"""Refresh the "recently updated repositories" table between markers in README.md.

Usage: python latest_repos.py <username> <README.md> [count]
Standard library only; uses GITHUB_TOKEN when set for a higher rate limit.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.request

START, END = "<!-- LATEST-REPOS:START -->", "<!-- LATEST-REPOS:END -->"


def fetch(user, token):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-latest-repos"}
    if token:
        headers["Authorization"] = f"bearer {token}"
    url = f"https://api.github.com/users/{user}/repos?type=owner&sort=pushed&per_page=30"
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=headers)))


def ago(stamp):
    days = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))).days
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"


def is_live(url):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "profile-latest-repos"})
        return urllib.request.urlopen(req, timeout=15).status < 400
    except Exception:
        return False


def table(user, repos, count):
    rows = ["| Project | Stack | Updated | Links |", "|---|---|---|---|"]
    for r in [r for r in repos if not r["fork"] and r["name"] != user][:count]:
        name = r["name"].replace("_", " ").replace("-", " ").strip()
        desc = f"<br><sub>{r['description']}</sub>" if r["description"] else ""
        links = f"[Code]({r['html_url']})" + (f" · [Live]({r['homepage']})" if r["homepage"] and is_live(r["homepage"]) else "")
        rows.append(f"| **[{name}]({r['html_url']})**{desc} | {r['language'] or '—'} | {ago(r['pushed_at'])} | {links} |")
    return "\n".join(rows)


if __name__ == "__main__":
    user, path = sys.argv[1], sys.argv[2]
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    with open(path, encoding="utf-8") as f:
        readme = f.read()
    block = f"{START}\n{table(user, fetch(user, os.environ.get('GITHUB_TOKEN')), count)}\n{END}"
    updated = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, readme, flags=re.S)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)
    print("README latest repos", "updated" if updated != readme else "unchanged")
