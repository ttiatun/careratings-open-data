# Enforcement study tables, release v2026.08

Computed from release v2026.08 (CMS Provider Information vintage 2026-08-01). The public Penalties file lists each fine and payment denial in a three-year lookback with a date and an amount. It does **not** say whether a civil money penalty was per instance or per day, and a fine reaches the file months after it is imposed, so the latest year is always incomplete. Comparisons are descriptive: they do not control for case mix, size, survey practice or region.

## Headline numbers

- Fines in the lookback (2023-08-19 to 2026-07-29): 13,256 totalling $456,752,787; median fine $15,593, mean $34,456.
- 6,514 of 14,690 facilities (44.3%) have at least one fine; 46.1% have a fine or a payment denial. Payment denials: 2,440.
- Per facility: $31,093; per certified bed: $291.
- Concentration: the most-fined 1% of facilities hold 14.8% of fine dollars, the top 5% hold 44.5% and the top 10% hold 65.3%; 895 facilities account for half of all fine dollars.

## By ownership type

| Ownership | Facilities | % fined | Fines per 100 facilities | $ per facility | $ per bed | Denials per 100 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| For profit | 10,877 | 47.0 | 98.3 | $35,263 | $318 | 18.4 |
| Non profit | 2,868 | 35.4 | 64.5 | $17,958 | $201 | 11.0 |
| Government | 945 | 40.4 | 75.3 | $22,959 | $206 | 13.5 |

## States by fine dollars per certified bed (states with at least 10 facilities)

Highest:

- VT: $1,008 per bed, 72.7% of facilities fined, $2,973,183 in all
- IL: $884 per bed, 68.6% of facilities fined, $75,126,367 in all
- AK: $786 per bed, 30.0% of facilities fined, $640,818 in all
- MT: $694 per bed, 68.9% of facilities fined, $3,469,724 in all
- DE: $662 per bed, 72.7% of facilities fined, $3,121,569 in all
- DC: $586 per bed, 64.7% of facilities fined, $1,454,987 in all
- RI: $572 per bed, 73.6% of facilities fined, $4,681,317 in all
- SD: $569 per bed, 74.0% of facilities fined, $3,326,467 in all

Lowest:

- ME: $99 per bed, 35.9% of facilities fined
- AR: $85 per bed, 31.7% of facilities fined
- IN: $85 per bed, 18.1% of facilities fined
- NH: $80 per bed, 30.1% of facilities fined
- AZ: $76 per bed, 27.9% of facilities fined

State differences reflect survey and enforcement practice as much as facility conduct; CMS regional offices and state survey agencies differ in how often they recommend and impose penalties.

## History store tables

- **Reporting lag.** Fines first seen in 2026 appeared a median of 245 days after the penalty date (90th percentile 442 days). Counts for the latest two penalty years will keep rising (`reporting_lag_by_year.csv`, `fines_by_penalty_year.csv`).
- **Trend at equal maturity** (fines visible by August 31 of the following year, `fines_equal_maturity.csv`): 2018: 2,467 fines, $80,649,114, median $13,286; 2019: 2,172 fines, $74,483,724, median $13,905; 2020: 5,121 fines, $77,575,846, median $4,585; 2021: 24,070 fines, $353,201,873, median $2,600; 2022: 19,075 fines, $424,429,272, median $4,580; 2023: 15,834 fines, $469,096,828, median $9,750; 2024: 9,708 fines, $461,159,464, median $22,205; 2025: 7,818 fines, $371,840,455, median $22,925.
- **Fines in the file.** The monthly file held 37,082 fines ($564,246,113) at its peak on 2023-06-27 and holds 13,256 ($456,752,787) on 2026-08-26 (`fines_in_file_by_snapshot.csv`, counted from the rows of each monthly file). The three-year lookback is rolling off the 2021 to 2023 surge.
- **What each file added.** 2026-06-24: 806 distinct fines added, 1,149 dropped, 22.1% of those added were first seen more than a year after the penalty date; 2026-07-29: 926 distinct fines added, 946 dropped, 17.3% of those added were first seen more than a year after the penalty date; 2026-08-26: 1,012 distinct fines added, 1,462 dropped, 19.3% of those added were first seen more than a year after the penalty date (`file_changes_by_snapshot.csv`; a distinct fine is a facility, date and amount, so two equal fines on one day count once).
- **Special Focus Facilities.** 456 facilities carried the SFF flag in at least one monthly file; the median was 15 monthly files and 106 were flagged in 24 or more. Today 84 are still SFFs, 24 are candidates, 266 are certified and no longer flagged (average overall rating 2.18), and 82 are no longer in the file (`sff_tenure.csv`, `sff_monthly.csv`).

## Files

Every table in this directory is a CSV named for its content; `study.json` records the release, DOI and row counts. Reproduce with `tcr-open-data enforcement-study --release releases/v2026.08 --history history --out analysis/enforcement/v2026.08`.
