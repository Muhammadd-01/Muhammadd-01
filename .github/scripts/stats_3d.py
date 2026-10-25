"""Render a 3D radar of contribution types and a 3D donut of repositories by language.

Usage: python stats_3d.py <username> <output.svg>
Uses the GitHub API with GITHUB_TOKEN when available, otherwise public endpoints.
Standard library only.
"""
import datetime as dt
import json
import math
import os
import sys
import urllib.request
from xml.sax.saxutils import escape

from contrib_3d import FONT, fetch_html

LANG_COLORS = {
    "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Dart": "#00B4AB", "Python": "#3572A5", "HTML": "#e34c26",
    "CSS": "#663399", "C#": "#178600", "C++": "#f34b7d", "PHP": "#4F5D95", "Blade": "#f7523f", "Swift": "#F05138",
    "Kotlin": "#A97BFF", "Java": "#b07219", "Vue": "#41b883", "Other": "#6e7b91",
}
AXES = ["Commit", "Issue", "PullReq", "Review", "Repo"]


def api(url, token=None, body=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-stats-3d"}
    if token:
        headers["Authorization"] = f"bearer {token}"
    data = json.dumps(body).encode() if body else None
    return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers)))


def owned_repos(user, token):
    repos, page = [], 1
    while True:
        batch = api(f"https://api.github.com/users/{user}/repos?type=owner&per_page=100&page={page}", token)
        repos += [r for r in batch if not r["fork"]]
        if len(batch) < 100:
            return repos
        page += 1


def contribution_types(user, token, repos):
    if token:
        q = """query($login:String!){user(login:$login){contributionsCollection{totalCommitContributions
          totalIssueContributions totalPullRequestContributions totalPullRequestReviewContributions totalRepositoryContributions}}}"""
        c = api("https://api.github.com/graphql", token, {"query": q, "variables": {"login": user}})["data"]["user"]["contributionsCollection"]
        return [c["totalCommitContributions"], c["totalIssueContributions"], c["totalPullRequestContributions"],
                c["totalPullRequestReviewContributions"], c["totalRepositoryContributions"]]
    # Public fallback: everything that isn't an issue, PR, review or new repo on the calendar is a commit.
    since = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    search = lambda q: api(f"https://api.github.com/search/issues?q={q}+created:>={since}")["total_count"]
    issues, prs = search(f"author:{user}+type:issue"), search(f"author:{user}+type:pr")
    reviews = search(f"reviewed-by:{user}+type:pr+-author:{user}")
    new_repos = sum(1 for r in repos if r["created_at"][:10] >= since)
    total = fetch_html(user)[1]
    return [max(total - issues - prs - reviews - new_repos, 0), issues, prs, reviews, new_repos]


def radar(values, cx, cy):
    R, TILT, HGT = 175, 0.5, 34
    top = max(2, math.ceil(math.log10(max(values) + 1)))
    ring = lambda v: R * math.log10(v + 1) / top if v > 0 else 0
    ang = [math.radians(-90 + i * 72) for i in range(5)]
    P = lambda r, a, lift=0: (cx + r * math.cos(a), cy + r * math.sin(a) * TILT - lift)
    # floor: a thick circular slab, then rings at 10, 100, 1K ... seen in perspective
    out = [f'<ellipse cx="{cx}" cy="{cy + 14}" rx="{R}" ry="{R*TILT:.1f}" fill="#061a3a" stroke="#38BDF8" stroke-opacity=".3"/>',
           f'<rect x="{cx - R}" y="{cy}" width="{2*R}" height="14" fill="#061a3a"/>',
           f'<ellipse cx="{cx}" cy="{cy}" rx="{R}" ry="{R*TILT:.1f}" fill="#0b1a33" stroke="#38BDF8" stroke-opacity=".45"/>']
    for k in range(1, top):
        r = R * k / top
        out.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{r:.1f}" ry="{r*TILT:.1f}" fill="none" stroke="#38BDF8" stroke-opacity=".2"/>')
    for k in range(1, top + 1):
        r = R * k / top
        out.append(f'<text x="{cx + r + 4:.1f}" y="{cy + 4}" font-size="10" fill="#5f6f88">{["10","100","1K","10K","100K","1M"][k-1]}</text>')
    for a in ang:
        x, y = P(R, a)
        out.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#38BDF8" stroke-opacity=".25"/>')
    # extruded data prism: base on the floor, top lifted; walls drawn back to front
    base = [P(ring(v), a) for v, a in zip(values, ang)]

    def lifted(h):
        return [(x, y - h) for x, y in base]

    def pts(points):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    out.append(f'<polygon points="{pts(base)}" fill="#00C9FF" fill-opacity=".12"/>')
    edges = sorted(range(5), key=lambda i: (base[i][1] + base[(i + 1) % 5][1]))
    for i in edges:
        j = (i + 1) % 5
        quad = lambda h: pts([base[i], base[j], lifted(h)[j], lifted(h)[i]])
        out.append(f'<polygon points="{quad(HGT)}" fill="#0b62d6" fill-opacity=".55" stroke="#00C9FF" stroke-opacity=".5">'
                   f'<animate attributeName="points" values="{quad(0)};{quad(HGT)}" dur="1.6s" fill="freeze" calcMode="spline" keySplines=".2 .8 .2 1"/></polygon>')
    out.append(f'<polygon points="{pts(lifted(HGT))}" fill="#3fd8ff" fill-opacity=".55" stroke="#E0F7FF" stroke-width="1.5">'
               f'<animate attributeName="points" values="{pts(lifted(0))};{pts(lifted(HGT))}" dur="1.6s" fill="freeze" calcMode="spline" keySplines=".2 .8 .2 1"/></polygon>')
    for (x, y), v in zip(lifted(HGT), values):
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#fff"><animate attributeName="r" values="4;6;4" dur="2.4s" repeatCount="indefinite"/></circle>')
    for name, v, a in zip(AXES, values, ang):
        x, y = P(R + 30, a, lift=HGT + 26 if math.sin(a) < -0.9 else 0)
        anchor = "middle" if abs(math.cos(a)) < .3 else ("start" if math.cos(a) > 0 else "end")
        out.append(f'<text x="{x:.1f}" y="{y - 4:.1f}" font-size="13" font-weight="700" fill="#E6EDF3" text-anchor="{anchor}">{name}</text>'
                   f'<text x="{x:.1f}" y="{y + 12:.1f}" font-size="12" font-weight="800" fill="#00C9FF" text-anchor="{anchor}">{v:,}</text>')
    return out


def donut(langs, cx, cy):
    RX, RY, INNER, DEPTH = 165, 82, 0.56, 30
    total = sum(n for _, n in langs)
    shade = lambda hexc, f: "#" + "".join(f"{int(int(hexc[i:i+2], 16) * f):02x}" for i in (1, 3, 5))
    E = lambda t, k=1.0, dy=0: (cx + RX * k * math.cos(t), cy + RY * k * math.sin(t) + dy)
    pts = lambda points: " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    slices, a = [], -math.pi / 2
    for name, n in langs:
        b = a + 2 * math.pi * n / total
        slices.append((name, n, a, b))
        a = b

    def arc(t0, t1, k, dy=0):
        steps = max(2, int(abs(t1 - t0) / math.radians(3)))
        return [E(t0 + (t1 - t0) * s / steps, k, dy) for s in range(steps + 1)]

    def clip(t0, t1, front):  # part of [t0,t1] on the front (sin>0) or back (sin<0) half
        parts, lo = [], t0
        cuts = sorted(c for c in (math.pi * m for m in range(-2, 5)) if t0 < c < t1)
        for c in cuts + [t1]:
            mid = (lo + c) / 2
            if (math.sin(mid) > 0) == front:
                parts.append((lo, c))
            lo = c
        return parts

    walls, tops = [], []
    for name, n, t0, t1 in slices:
        col = LANG_COLORS.get(name, LANG_COLORS["Other"])
        for p0, p1 in clip(t0, t1, front=False):  # inner wall visible through the hole at the back
            walls.append(f'<polygon points="{pts(arc(p0, p1, INNER) + arc(p1, p0, INNER, DEPTH))}" fill="{shade(col, .45)}"/>')
    for name, n, t0, t1 in slices:
        col = LANG_COLORS.get(name, LANG_COLORS["Other"])
        for p0, p1 in clip(t0, t1, front=True):  # outer wall facing the viewer
            walls.append(f'<polygon points="{pts(arc(p0, p1, 1) + arc(p1, p0, 1, DEPTH))}" fill="{shade(col, .62)}"/>')
        tops.append(f'<polygon points="{pts(arc(t0, t1, 1) + arc(t1, t0, INNER))}" fill="{col}" stroke="#0D1117" stroke-width="1.2">'
                    f'<title>{escape(name)}: {n} repos ({100*n/total:.0f}%)</title></polygon>')
    sheen = (f'<ellipse cx="{cx}" cy="{cy}" rx="{RX}" ry="{RY}" fill="url(#sheen)" pointer-events="none"/>'
             f'<ellipse cx="{cx}" cy="{cy}" rx="{RX*INNER:.1f}" ry="{RY*INNER:.1f}" fill="none" stroke="#0D1117" stroke-width="1.2"/>')
    out = [f'<ellipse cx="{cx}" cy="{cy + DEPTH + 18}" rx="{RX+10}" ry="{RY*0.5:.0f}" fill="#000" opacity=".45" filter="url(#blur)"/>',
           '<g class="float">'] + walls + tops + [sheen,
           f'<text x="{cx}" y="{cy + 4}" font-size="22" font-weight="800" fill="#fff" text-anchor="middle">{total}</text>',
           f'<text x="{cx}" y="{cy + 20}" font-size="10.5" font-weight="600" fill="#8B9BB4" text-anchor="middle">repos</text>', "</g>"]
    return out, total


def render(user, values, langs):
    W, H = 1200, 440
    donut_svg, total = donut(langs, 780, 215)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="3D charts: contribution types in the last year, and public repositories by language">',
           f'''<style>
.float{{animation:fl 6s ease-in-out infinite}}@keyframes fl{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-8px)}}}}
</style>
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#030a18"/><stop offset="1" stop-color="#07224a"/></linearGradient>
<radialGradient id="spot" cx=".25" cy=".55" r=".5"><stop offset="0" stop-color="#00C9FF" stop-opacity=".14"/><stop offset="1" stop-color="#00C9FF" stop-opacity="0"/></radialGradient>
<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
<animateTransform attributeName="gradientTransform" type="translate" values="-1 0;1.2 0" dur="5s" repeatCount="indefinite"/></linearGradient>
<filter id="blur" x="-30%" y="-80%" width="160%" height="260%"><feGaussianBlur stdDeviation="10"/></filter>
<clipPath id="card"><rect width="{W}" height="{H}" rx="18"/></clipPath>
</defs>
<g clip-path="url(#card)" font-family="{FONT}">
<rect width="{W}" height="{H}" fill="url(#bg)"/><rect width="{W}" height="{H}" fill="url(#spot)"/>
<line x1="560" y1="40" x2="560" y2="{H-40}" stroke="#38BDF8" stroke-opacity=".15"/>''']
    out.append('<text x="40" y="52" font-size="13" font-weight="700" fill="#38BDF8" letter-spacing="3">CONTRIBUTION TYPES · LAST 12 MONTHS</text>')
    out.append('<text x="600" y="52" font-size="13" font-weight="700" fill="#38BDF8" letter-spacing="3">PUBLIC REPOSITORIES BY LANGUAGE</text>')
    out += radar(values, 290, 250)
    out += donut_svg
    y = 120
    for name, n in langs:
        col = LANG_COLORS.get(name, LANG_COLORS["Other"])
        out.append(f'<rect x="985" y="{y-11}" width="14" height="14" rx="3" fill="{col}"/>'
                   f'<text x="1008" y="{y}" font-size="13.5" font-weight="600" fill="#E6EDF3">{escape(name)}</text>'
                   f'<text x="1165" y="{y}" font-size="13" font-weight="700" fill="#8B9BB4" text-anchor="end">{100*n/total:.0f}%</text>')
        y += 30
    out.append(f'<text x="40" y="{H-22}" font-size="11.5" fill="#5f6f88">@{escape(user)} · log scale · updated {dt.date.today():%b %d, %Y}</text>')
    out.append(f'</g><rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="18" fill="none" stroke="#38BDF8" stroke-opacity=".3"/></svg>')
    return "\n".join(out)


if __name__ == "__main__":
    user, path = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN")
    try:
        repos = owned_repos(user, token)
        values = contribution_types(user, token, repos)
    except Exception as err:
        print(f"Authenticated API failed ({err}), using public endpoints")
        token = None
        repos = owned_repos(user, None)
        values = contribution_types(user, None, repos)
    counts = {}
    for r in repos:
        if r["name"] != user and r["language"]:
            counts[r["language"]] = counts.get(r["language"], 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    langs = ranked[:7] + ([("Other", sum(n for _, n in ranked[7:]))] if len(ranked) > 7 else [])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(user, values, langs))
    print(f"wrote {path}: types={dict(zip(AXES, values))} langs={langs}")
