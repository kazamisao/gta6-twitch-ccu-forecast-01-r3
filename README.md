[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/kazamisao/gta6-twitch-ccu-forecast-01-r3/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/kazamisao/gta6-twitch-ccu-forecast-01-r3/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

# GTA VI Twitch CCU forecast — round 3

Forecasts Twitch concurrent viewers of Grand Theft Auto VI for hours 2–24
of release day 2026-11-19 (UTC), as five quantiles per hour, from the
hour-1 print and the comparable past launches shipped in the case file.

Method: fitted at run time on the case's own comparables, restricted to
the kit's clean analogue tier (unlock notes marked "Tier: comparable",
release-day hour-1 print above 10,000). For each hour, the log level is
regressed on two size anchors of every training launch and the two
centres are blended:

- the hour-1 anchor — log viewers on log hour-1 viewers, estimated by
  OLS and by the Theil–Sen median-slope estimator and averaged, then
  shifted by the median in-sample residual;
- the eve anchor — the same averaged regression on the launch's "eve
  level", the largest hourly viewer count in the 24 hours before its
  release day. The eve level measures how far the launch's regional
  unlock wave (New Zealand, then Europe) had already rolled before the
  UTC day began, which is information the hour-1 print alone compresses
  away. The blend weight is 0.29 on the eve line.

A second stage adjusts the centre for the case's hour-1 channel count:
the hour-1 line's residuals are regressed on log hour-1 channels across
the training launches and 0.75 of that slope is applied to the case's
centred log channel count. Spread: the hour-1 line's residual standard
deviation, scaled by 0.69 and clipped to [0.25, 0.65] log units, applied
symmetrically in log space with normal quantiles.

Validation (local scorer on the kit's practice cases, SullyGnome
answers): practice mean pinball **0.1550**, against round 2's 0.1639 and
the house baseline's 0.387. Leave-one-launch-out over the 18 training
launches: 0.2661 (round 2: 0.2725). Extrapolation folds — train only on
launches with hour-1 ≤ 300k, test on the largest launches: 0.2076
(round 2: 0.2378). The program is deterministic (two runs are
byte-identical), standard library only, and runs a case in well under
a second.
