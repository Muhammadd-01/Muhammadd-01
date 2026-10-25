"""Render the last year of GitHub contributions as a straight, front-facing 3D bar calendar.

Usage: python contrib_3d.py <username> <output.svg>
Uses the GraphQL API when GITHUB_TOKEN is set, otherwise the public contributions page.
Standard library only, so it runs on a bare GitHub Actions runner.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from xml.sax.saxutils import escape

FONT = "'Segoe UI', Inter, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif"
TOP = ["#1b2433", "#0d47a1", "#0b62d6", "#1e9bff", "#3fd8ff"]
FRONT = ["#121925", "#082f6b", "#074394", "#136bb3", "#1fa3c7"]
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def fetch_graphql(user, token):
    query = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{
      totalContributions weeks{contributionDays{date contributionCount contributionLevel weekday}}}}}}"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    cal = json.load(urllib.request.urlopen(req))["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [
        {"date": d["date"], "count": d["contributionCount"], "level": LEVELS[d["contributionLevel"]], "row": d["weekday"], "col": c}
        for c, w in enumerate(cal["weeks"]) for d in w["contributionDays"]
    ]
    return days, cal["totalContributions"]


def fetch_html(user):
    html = urllib.request.urlopen(f"https://github.com/users/{user}/contributions").read().decode()
    tips = dict(re.findall(r'for="(contribution-day-component-\d+-\d+)"[^>]*>([^<]*)</tool-tip>', html))
    days = []
    for attrs in re.findall(r"<td[^>]*ContributionCalendar-day[^>]*>", html):
        date = re.search(r'data-date="([^"]+)"', attrs)
        cid = re.search(r'id="(contribution-day-component-(\d+)-(\d+))"', attrs)
        if not (date and cid):
            continue
        m = re.match(r"(\d+) contribution", tips.get(cid.group(1), ""))
        days.append({"date": date.group(1), "count": int(m.group(1)) if m else 0,
                     "level": int(re.search(r'data-level="(\d)"', attrs).group(1)),
                     "row": int(cid.group(2)), "col": int(cid.group(3))})
    return days, sum(d["count"] for d in days)


def streaks(days):
    ordered = sorted(days, key=lambda d: d["date"])
    longest = run = 0
    for d in ordered:
        run = run + 1 if d["count"] else 0
        longest = max(longest, run)
    current = 0
    for i, d in enumerate(reversed(ordered)):
        if d["count"]:
            current += 1
        elif i > 0:  # today without contributions doesn't break the streak yet
            break
    return current, longest


def render(user, days, total):
    W, H = 1200, 430
    X0, PITCH, BW = 80, 20, 16          # column origin, column pitch, bar width
    Y0, PY, DY = 186, 24, 17            # back-row baseline, row pitch, top-face depth
    HMAX, VP = 58, 610                  # tallest bar, vanishing x for perspective
    cols = max(d["col"] for d in days) + 1
    nonzero = sorted(d["count"] for d in days if d["count"])
    cap = nonzero[int(len(nonzero) * 0.95) - 1] if nonzero else 1
    busiest = max(days, key=lambda d: d["count"])
    cur, best = streaks(days)
    last = max(days, key=lambda d: d["date"])

    def sx(x, row):  # rows further back are drawn slightly narrower, converging on VP
        return VP + (x - VP) * (0.90 + 0.0167 * row)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="{total} contributions in the last year, shown as a 3D bar calendar">',
           f'''<style>
.b{{transform-box:fill-box;transform-origin:50% 100%;animation:rise 1.4s cubic-bezier(.2,.8,.2,1) both}}
@keyframes rise{{from{{transform:scaleY(.04)}}to{{transform:scaleY(1)}}}}
.pulse{{animation:pu 2s ease-in-out infinite}}@keyframes pu{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
</style>
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#030a18"/><stop offset="1" stop-color="#07224a"/></linearGradient>
<radialGradient id="spot" cx=".5" cy=".75" r=".6"><stop offset="0" stop-color="#00C9FF" stop-opacity=".16"/><stop offset="1" stop-color="#00C9FF" stop-opacity="0"/></radialGradient>
<linearGradient id="floor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0c1830"/><stop offset="1" stop-color="#0a1426"/></linearGradient>
<linearGradient id="sweep" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#9DDCFF" stop-opacity=".18"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<clipPath id="card"><rect width="{W}" height="{H}" rx="18"/></clipPath>
</defs>
<g clip-path="url(#card)" font-family="{FONT}">
<rect width="{W}" height="{H}" fill="url(#bg)"/><rect width="{W}" height="{H}" fill="url(#spot)"/>''']

    # header: title + real stats
    out.append(f'<text x="40" y="52" font-size="13" font-weight="700" fill="#38BDF8" letter-spacing="3">CONTRIBUTIONS · LAST 12 MONTHS</text>')
    out.append(f'<text x="40" y="86" font-size="28" font-weight="800" fill="#fff">{total:,} contributions</text>')
    chips = [(f"{cur} days", "current streak"), (f"{best} days", "longest streak"),
             (str(busiest["count"]), "busiest day · " + dt.date.fromisoformat(busiest["date"]).strftime("%b %d"))]
    x = W - 40
    for value, label in reversed(chips):
        w = max(len(label) * 7.2, len(value) * 11) + 28
        x -= w
        out.append(f'<rect x="{x:.0f}" y="36" width="{w:.0f}" height="54" rx="12" fill="#0b1a33" stroke="#38BDF8" stroke-opacity=".35"/>'
                   f'<text x="{x+14:.0f}" y="60" font-size="18" font-weight="800" fill="#00C9FF">{escape(value)}</text>'
                   f'<text x="{x+14:.0f}" y="79" font-size="11.5" font-weight="600" fill="#8B9BB4">{escape(label)}</text>')
        x -= 10

    # floor slab (straight, front-facing)
    fl, fr = sx(X0 - 10, 6) - 6, sx(X0 + cols * PITCH + 4, 6) + 6
    bl, br = sx(X0 - 10, 0), sx(X0 + cols * PITCH + 4, 0)
    ytop, ybot = Y0 - 8, Y0 + 6 * PY + DY + 8
    out.append(f'<polygon points="{bl:.1f},{ytop} {br:.1f},{ytop} {fr:.1f},{ybot} {fl:.1f},{ybot}" fill="url(#floor)" stroke="#38BDF8" stroke-opacity=".25"/>')
    out.append(f'<rect x="{fl:.1f}" y="{ybot}" width="{fr-fl:.1f}" height="10" fill="#071226"/>')
    out.append(f'<rect y="{ytop}" width="160" height="{ybot-ytop}" fill="url(#sweep)">'
               f'<animate attributeName="x" values="{fl-160:.0f};{fr:.0f}" dur="6s" repeatCount="indefinite"/></rect>')

    # bars, back row first so nearer rows overlap correctly
    for d in sorted(days, key=lambda d: (d["row"], d["col"])):
        r, c, lv = d["row"], d["col"], d["level"]
        h = 2 if not d["count"] else 5 + (min(d["count"], cap) / cap) ** 0.7 * (HMAX - 5)
        xl, xr = sx(X0 + c * PITCH, r), sx(X0 + c * PITCH + BW, r)
        xlf, xrf = sx(X0 + c * PITCH, r + DY / PY), sx(X0 + c * PITCH + BW, r + DY / PY)
        yb = Y0 + r * PY
        top = f"{xl:.1f},{yb-h:.1f} {xr:.1f},{yb-h:.1f} {xrf:.1f},{yb-h+DY:.1f} {xlf:.1f},{yb-h+DY:.1f}"
        tip = f'<title>{d["count"]} contributions on {d["date"]}</title>'
        if not d["count"]:
            out.append(f'<polygon points="{top}" fill="{TOP[0]}">{tip}</polygon>')
            continue
        delay = c * 0.025 + r * 0.04
        out.append(f'<g class="b" style="animation-delay:{delay:.2f}s">{tip}'
                   f'<rect x="{xlf:.1f}" y="{yb-h+DY:.1f}" width="{xrf-xlf:.1f}" height="{h:.1f}" fill="{FRONT[lv]}"/>'
                   f'<polygon points="{top}" fill="{TOP[lv]}"/></g>')
        if d is last:
            out.append(f'<polygon class="pulse" points="{top}" fill="none" stroke="#fff" stroke-width="1.5"/>')

    # month labels along the front edge, weekday labels on the left
    first_of_col = {}
    for d in days:
        if d["col"] not in first_of_col or d["date"] < first_of_col[d["col"]]:
            first_of_col[d["col"]] = d["date"]
    prev = None
    for c in range(cols - 1):
        month = first_of_col[c][:7]
        if month != prev and c > 0:
            out.append(f'<text x="{sx(X0 + c * PITCH, 6 + DY / PY):.1f}" y="{ybot+30}" font-size="12" font-weight="600" fill="#8B9BB4">'
                       f'{dt.date.fromisoformat(first_of_col[c]).strftime("%b")}</text>')
        prev = month
    for r, name in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        out.append(f'<text x="{sx(X0 - 16, r):.1f}" y="{Y0 + r*PY + DY/2 + 4:.0f}" font-size="11" font-weight="600" fill="#8B9BB4" text-anchor="end">{name}</text>')

    # legend
    lx = W - 210
    out.append(f'<text x="{lx}" y="{H-22}" font-size="11.5" fill="#8B9BB4" text-anchor="end">Less</text>')
    for i in range(5):
        out.append(f'<rect x="{lx+8+i*18}" y="{H-33}" width="13" height="13" rx="2" fill="{TOP[i]}"/>')
    out.append(f'<text x="{lx+104}" y="{H-22}" font-size="11.5" fill="#8B9BB4">More</text>')
    out.append(f'<text x="40" y="{H-22}" font-size="11.5" fill="#5f6f88">@{escape(user)} · updated {dt.date.today():%b %d, %Y}</text>')
    out.append(f'</g><rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="18" fill="none" stroke="#38BDF8" stroke-opacity=".3"/></svg>')
    return "\n".join(out)


if __name__ == "__main__":
    user, path = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN")
    try:
        days, total = fetch_graphql(user, token) if token else fetch_html(user)
    except Exception as err:  # API hiccup or missing scope: the public page has the same data
        print(f"GraphQL failed ({err}), falling back to the contributions page")
        days, total = fetch_html(user)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(user, days, total))
    print(f"wrote {path}: {len(days)} days, {total} contributions")
