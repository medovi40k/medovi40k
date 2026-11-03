"""Render a GitHub contribution streak card as an SVG.

Runs in GitHub Actions with only the standard library. Reads the token from
GITHUB_TOKEN and writes the card to the path given with --out.
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

API = "https://api.github.com/graphql"

YEARS_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection { contributionYears }
  }
}
"""

CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

# Matches the tokyonight theme used by the other cards.
THEME = {
    "bg": "#1a1b27",
    "stroke": "#38bdae33",
    "ring": "#70a5fd",
    "fire": "#bf91f3",
    "number": "#38bdae",
    "label": "#70a5fd",
    "dates": "#a9b1d6",
}


def graphql(token, query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-streak-card",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"]))
    return data["data"]


def fetch_days(token, login, today):
    years = graphql(token, YEARS_QUERY, {"login": login})["user"][
        "contributionsCollection"
    ]["contributionYears"]
    days = {}
    for year in sorted(years):
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        data = graphql(
            token,
            CALENDAR_QUERY,
            {"login": login, "from": start.isoformat(), "to": end.isoformat()},
        )
        weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for week in weeks:
            for day in week["contributionDays"]:
                d = date.fromisoformat(day["date"])
                if d <= today:
                    days[d] = day["contributionCount"]
    return days


def compute(days, today):
    """Return totals and streaks from a {date: count} map."""
    if not days:
        return {"total": 0, "first": today, "current": (0, None, None), "longest": (0, None, None)}

    first = min(d for d, c in days.items() if c > 0) if any(days.values()) else today
    total = sum(days.values())

    longest = (0, None, None)
    run_len, run_start = 0, None
    d = min(days)
    while d <= today:
        if days.get(d, 0) > 0:
            if run_len == 0:
                run_start = d
            run_len += 1
            if run_len > longest[0]:
                longest = (run_len, run_start, d)
        else:
            run_len = 0
        d += timedelta(days=1)

    # A streak stays alive through today until the day is over.
    end = today if days.get(today, 0) > 0 else today - timedelta(days=1)
    cur_len, d = 0, end
    while days.get(d, 0) > 0:
        cur_len += 1
        d -= timedelta(days=1)
    current = (cur_len, d + timedelta(days=1), end) if cur_len else (0, None, None)

    return {"total": total, "first": first, "current": current, "longest": longest}


def fmt_date(d, today):
    if d is None:
        return ""
    return d.strftime("%b %-d") if d.year == today.year else d.strftime("%b %-d, %Y")


def fmt_range(start, end, today):
    if start is None:
        return "No current streak"
    if start == end:
        return fmt_date(start, today)
    return f"{fmt_date(start, today)} - {fmt_date(end, today)}"


def render(stats, today):
    t = THEME
    total = f"{stats['total']:,}"
    total_range = f"{fmt_date(stats['first'], today)} - Present"
    cur, cs, ce = stats["current"]
    lng, ls, le = stats["longest"]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" role="img" aria-label="GitHub contribution streak">
  <style>
    text {{ font-family: "Segoe UI", Ubuntu, sans-serif; }}
    .num {{ font-size: 28px; font-weight: 700; fill: {t['number']}; }}
    .label {{ font-size: 14px; font-weight: 600; fill: {t['label']}; }}
    .dates {{ font-size: 12px; fill: {t['dates']}; }}
  </style>
  <rect width="495" height="195" rx="4.5" fill="{t['bg']}"/>
  <line x1="165" y1="28" x2="165" y2="170" stroke="{t['stroke']}" stroke-width="1"/>
  <line x1="330" y1="28" x2="330" y2="170" stroke="{t['stroke']}" stroke-width="1"/>

  <g text-anchor="middle">
    <text x="82.5" y="79" class="num">{total}</text>
    <text x="82.5" y="114" class="label">Total Contributions</text>
    <text x="82.5" y="139" class="dates">{total_range}</text>
  </g>

  <g text-anchor="middle">
    <circle cx="247.5" cy="71" r="40" fill="none" stroke="{t['ring']}" stroke-width="5"/>
    <rect x="234" y="24" width="27" height="20" fill="{t['bg']}"/>
    <path transform="translate(237.5 19)" fill="{t['fire']}" d="M10 0C10 6 3 8 3 15a7 7 0 0 0 14 0c0-3-1.5-5-3-6.5 0 2.5-1.5 4-3 4 1-3 1-7-1-12.5Z"/>
    <text x="247.5" y="80" class="num">{cur}</text>
    <text x="247.5" y="138" class="label">Current Streak</text>
    <text x="247.5" y="161" class="dates">{fmt_range(cs, ce, today)}</text>
  </g>

  <g text-anchor="middle">
    <text x="412.5" y="79" class="num">{lng}</text>
    <text x="412.5" y="114" class="label">Longest Streak</text>
    <text x="412.5" y="139" class="dates">{fmt_range(ls, le, today)}</text>
  </g>
</svg>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")

    today = datetime.now(timezone.utc).date()
    stats = compute(fetch_days(token, args.user, today), today)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render(stats, today))
    print(f"Wrote {args.out}: total={stats['total']} current={stats['current'][0]} longest={stats['longest'][0]}")


if __name__ == "__main__":
    main()
