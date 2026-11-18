#!/usr/bin/env python3
"""GTA VI Twitch CCU forecast - round 3.

Forecasts concurrent Twitch viewers of Grand Theft Auto VI for hours 2-24
of release day 2026-11-19 (UTC), five quantiles per hour, from the case
file's hour-1 print and its comparable past launches.

Method (fitted at run time on the case's own comparables, deterministic,
standard library only):

- Training set: the comparables whose unlock notes mark them
  "Tier: comparable" (the kit's own research tier for clean analogues:
  no early-access contamination, a real post-unlock hour 1) and whose
  release-day hour-1 print exceeds 10,000 viewers.
- Two anchors per hour. The level of hour h is regressed, in log space,
  on two different size anchors of each training launch: its hour-1
  print, and its "eve level" - the largest hourly viewer count in the
  24 hours before its release day, which captures how far the launch's
  regional unlock wave had already rolled before the UTC day began.
  Each regression averages an OLS fit and a Theil-Sen fit (the average
  is stabler than either alone). The hour-1 centre is shifted by the
  median in-sample residual, then blended 0.71 / 0.29 with the eve
  line's prediction for this case's own eve level.
- A second stage adjusts the centre for the case's hour-1 channel
  count: the hour-1 line's residuals are regressed on log hour-1
  channels across the training launches, and 0.75 of that slope is
  applied to the case's centred log channel count.
- Spread: the hour-1 line's residual standard deviation, scaled by
  0.69 and clipped to [0.25, 0.65] log units, applied symmetrically in
  log space with normal quantiles.

Validation while building (local scorer, SullyGnome practice answers):
practice mean pinball 0.1550 vs round 2's 0.1639 and the house
baseline's 0.387; leave-one-launch-out over the 18 training launches
0.2661 vs round 2's 0.2725; extrapolation folds (train on hour-1
<= 300k, test on the largest launches) 0.2076 vs 0.2378.
"""

import json
import math
import os
import statistics
from datetime import datetime, timedelta
from pathlib import Path

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.644854, -0.674490, 0.0, 0.674490, 1.644854]
HOURS = list(range(2, 25))

ANCHOR_W = 0.29        # weight of the eve-level line in the centre blend
CHANNELS_C = 0.75      # damping on the channels second stage
SPREAD_MUL = 0.69      # scale on the residual SD
SPREAD_LO = 0.25
SPREAD_HI = 0.65
MIN_TRAIN_H1 = 10000.0  # clean-analogue floor on the hour-1 print

IN_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))


def parse_ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def hour_key(day_start, hour):
    return (day_start + timedelta(hours=hour - 1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def release_day(day_start_iso, hourly):
    """{hour: (viewers, channels)} for hours 1..24 of the release day."""
    start = parse_ts(day_start_iso)
    by_from = {p["from"]: p for p in hourly or []}
    day = {}
    for h in range(1, 25):
        point = by_from.get(hour_key(start, h))
        if point is not None and point.get("viewers") is not None:
            day[h] = (point["viewers"], point.get("channels"))
    return day


def eve_level(day_start_iso, hourly):
    """Largest hourly viewer count in the 24 h before the release day."""
    start = parse_ts(day_start_iso)
    low = start - timedelta(hours=24)
    best = None
    for point in hourly or []:
        at = parse_ts(point["from"])
        if low <= at < start and point.get("viewers") is not None:
            if best is None or point["viewers"] > best:
                best = point["viewers"]
    return best


def ols(xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx > 0 else 0.0
    return my - slope * mx, slope


def theil_sen(xs, ys):
    slopes = []
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            if xs[j] != xs[i]:
                slopes.append((ys[j] - ys[i]) / (xs[j] - xs[i]))
    slope = statistics.median(slopes) if slopes else 0.0
    intercept = statistics.median([y - slope * x for x, y in zip(xs, ys)])
    return intercept, slope


def averaged_line(xs, ys):
    a1, b1 = ols(xs, ys)
    a2, b2 = theil_sen(xs, ys)
    return (a1 + a2) / 2.0, (b1 + b2) / 2.0


def build_training(case):
    """Clean comparable launches as log-space rows."""
    rows = []
    for comp in case.get("comparables") or []:
        if "Tier: comparable" not in (comp.get("unlock") or ""):
            continue
        day = release_day(comp["day_start"], comp.get("hourly"))
        if len(day) < 24 or day[1][0] <= MIN_TRAIN_H1:
            continue
        rows.append({
            "x1": math.log(day[1][0]),
            "y": {h: math.log(day[h][0]) for h in range(1, 25)},
            "eve": eve_level(comp["day_start"], comp.get("hourly")),
            "ch1": day[1][1],
        })
    return rows


def case_eve(case):
    """This case's own eve level: the largest hourly viewer count in the
    24 h before its release day. Prefers the hourly history; if that has
    no point inside the window, falls back to the raw history reads."""
    level = eve_level(case["day_start"], case.get("history_hourly"))
    if level is not None:
        return level
    start = parse_ts(case["day_start"])
    low = start - timedelta(hours=24)
    best = None
    for point in case.get("history") or []:
        at = parse_ts(point["at"])
        if low <= at < start and point.get("viewers") is not None:
            if best is None or point["viewers"] > best:
                best = point["viewers"]
    return best


def baseline_forecast(p1):
    """The house baseline: flat at the hour-1 print, widening spread.
    Used only if the training set is unusable, so a case never crashes."""
    out = {}
    for h in HOURS:
        s = 0.15 * math.sqrt(h - 1)
        out[h] = [p1 * math.exp(z * s) for z in Z]
    return out


def forecast(case):
    known = case["known"][0]
    p1 = max(1.0, known["viewers"])
    ch1 = known.get("channels")
    rows = build_training(case)
    if len(rows) < 8:
        return baseline_forecast(p1)
    eve = case_eve(case)
    lp = math.log(p1)
    out = {}
    for h in HOURS:
        xs = [r["x1"] for r in rows]
        ys = [r["y"][h] for r in rows]
        a, b = averaged_line(xs, ys)
        resid = [y - (a + b * x) for x, y in zip(xs, ys)]
        mu = a + b * lp + statistics.median(resid)
        eve_rows = [r for r in rows if r["eve"]]
        if eve and len(eve_rows) >= 8:
            ex = [math.log(r["eve"]) for r in eve_rows]
            ey = [r["y"][h] for r in eve_rows]
            ea, eb = averaged_line(ex, ey)
            mu = (1.0 - ANCHOR_W) * mu + ANCHOR_W * (ea + eb * math.log(eve))
        ch_rows = [r for r in rows if r["ch1"]]
        if ch1 and len(ch_rows) >= 8:
            chx = [math.log(max(1.0, r["ch1"])) for r in ch_rows]
            ch_resid = [r["y"][h] - (a + b * r["x1"]) for r in ch_rows]
            _, cb = ols(chx, ch_resid)
            mu += CHANNELS_C * cb * (math.log(max(1.0, ch1))
                                     - sum(chx) / len(chx))
        spread = min(SPREAD_HI, max(SPREAD_LO,
                                    SPREAD_MUL * statistics.pstdev(resid)))
        out[h] = [math.exp(mu + z * spread) for z in Z]
    return out


def sanitise(row):
    """Quantiles must be finite, in (0, 1e9], and non-decreasing."""
    fixed = []
    prev = 0.0
    for q in row:
        if not math.isfinite(q) or q <= 0:
            q = prev if prev > 0 else 1.0
        q = min(q, 1_000_000_000.0)
        prev = max(prev, q)
        fixed.append(prev)
    return fixed


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(IN_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        try:
            fc = forecast(case)
        except Exception:
            fc = baseline_forecast(max(1.0, case["known"][0]["viewers"]))
        hours = [{"hour": h, "q": sanitise(fc[h])} for h in HOURS]
        target = OUT_DIR / (path.stem + ".out")
        target.write_text(json.dumps({"hours": hours}), encoding="utf-8")


if __name__ == "__main__":
    main()
