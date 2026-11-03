"""Render a weekly contribution activity graph (last 12 months) as an SVG.

Uses the same GraphQL fetch as streak_card.py. Reads GITHUB_TOKEN and writes
the card to --out.
"""

import argparse
import math
import os
import sys
from datetime import datetime, timedelta, timezone

from streak_card import THEME, fetch_days

W, H = 900, 300
PAD_L, PAD_R, PAD_T, PAD_B = 56, 28, 70, 46
WEEKS = 52


def weekly_counts(days, today):
    """Sum contributions per week (Sunday-Saturday) for the last WEEKS weeks."""
    this_sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    starts = [this_sunday - timedelta(weeks=i) for i in range(WEEKS - 1, -1, -1)]
    counts = [sum(days.get(s + timedelta(days=k), 0) for k in range(7)) for s in starts]
    return starts, counts


def nice_max(v):
    """Round the axis top up so the 4 gridline steps are round numbers."""
    if v <= 4:
        return 4
    raw = v / 4
    if raw <= 5:
        return math.ceil(raw) * 4
    mag = 10 ** math.floor(math.log10(raw))
    steps = (1, 2, 5, 10) if mag == 1 else (1, 2, 2.5, 5, 10)
    return int(next(s * mag for s in steps if s * mag >= raw) * 4)


def monotone_path(pts):
    """Smooth path through points without overshooting (Fritsch-Carlson)."""
    n = len(pts)
    if n < 2:
        return ""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0] * (n - 2) + [d[-1]]
    for i in range(1, n - 1):
        m[i] = 0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        s = a * a + b * b
        if s > 9:
            t = 3 / math.sqrt(s)
            m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    out = [f"M{xs[0]:.1f},{ys[0]:.1f}"]
    for i in range(n - 1):
        h = xs[i + 1] - xs[i]
        out.append(
            f"C{xs[i] + h / 3:.1f},{ys[i] + m[i] * h / 3:.1f} "
            f"{xs[i + 1] - h / 3:.1f},{ys[i + 1] - m[i + 1] * h / 3:.1f} "
            f"{xs[i + 1]:.1f},{ys[i + 1]:.1f}"
        )
    return " ".join(out)


def render(starts, counts, today):
    t = THEME
    total = sum(counts)
    active = sum(1 for c in counts if c)
    best_i = max(range(len(counts)), key=lambda i: counts[i])
    top = nice_max(max(counts))

    x0, x1 = PAD_L, W - PAD_R
    y0, y1 = H - PAD_B, PAD_T
    step = (x1 - x0) / (len(counts) - 1)
    pts = [(x0 + i * step, y0 - (c / top) * (y0 - y1)) for i, c in enumerate(counts)]
    line = monotone_path(pts)
    area = f"{line} L{pts[-1][0]:.1f},{y0} L{pts[0][0]:.1f},{y0} Z"

    grid = []
    for k in range(5):
        v = top * k / 4
        y = y0 - (v / top) * (y0 - y1)
        label = f"{v:g}"
        grid.append(
            f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>'
            f'<text x="{x0 - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{label}</text>'
        )

    months = []
    last = None
    for i, s in enumerate(starts):
        m = (s + timedelta(days=6)).strftime("%b")
        if m != last and 0 < i < len(starts) - 2:
            months.append(f'<text x="{x0 + i * step:.1f}" y="{y0 + 24}" text-anchor="middle" class="axis">{m}</text>')
        last = m

    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" class="dot"/>'
        for (x, y), c in zip(pts, counts)
        if c
    )
    bx, by = pts[best_i]
    best_week = starts[best_i].strftime("%b %-d" if starts[best_i].year == today.year else "%b %-d, %Y")
    if total:
        num, fire = t["number"], t["fire"]
        summary = (
            f'<tspan fill="{num}" font-weight="700">{total:,}</tspan> contributions · '
            f'<tspan fill="{num}" font-weight="700">{active}</tspan> active weeks · '
            f'best week <tspan fill="{num}" font-weight="700">{counts[best_i]}</tspan> ({best_week})'
        )
        marker = f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="6" fill="none" stroke="{fire}" stroke-width="2"/>'
    else:
        summary, marker = "No contributions in the last 12 months", ""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Weekly contribution activity over the last 12 months">
  <style>
    text {{ font-family: "Segoe UI", Ubuntu, sans-serif; }}
    .title {{ font-size: 18px; font-weight: 600; fill: {t['label']}; }}
    .sub {{ font-size: 13px; fill: {t['dates']}; }}
    .axis {{ font-size: 11px; fill: {t['dates']}; opacity: .8; }}
    .grid {{ stroke: {t['dates']}; stroke-opacity: .12; stroke-width: 1; }}
    .line {{ fill: none; stroke: {t['ring']}; stroke-width: 2.5; stroke-linejoin: round; }}
    .dot {{ fill: {t['fire']}; }}
  </style>
  <defs>
    <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{t['ring']}" stop-opacity=".45"/>
      <stop offset="1" stop-color="{t['ring']}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" rx="4.5" fill="{t['bg']}"/>
  <text x="{PAD_L - 30}" y="36" class="title">Contribution activity · last 12 months</text>
  <text x="{W - PAD_R}" y="36" text-anchor="end" class="sub">{summary}</text>
  {''.join(grid)}
  {''.join(months)}
  <path d="{area}" fill="url(#fill)"/>
  <path d="{line}" class="line"/>
  {dots}
  {marker}
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
    starts, counts = weekly_counts(fetch_days(token, args.user, today), today)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render(starts, counts, today))
    print(f"Wrote {args.out}: weekly={counts}")


if __name__ == "__main__":
    main()
