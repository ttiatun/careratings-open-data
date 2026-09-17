# Staffing-standards study tables, release v2026.08

Computed from release v2026.08 (CMS Provider Information vintage 2026-08-01). The floors are those of the federal minimum staffing rule finalized in 2024 and rescinded effective February 2, 2026: 0.55 registered-nurse, 2.45 nurse-aide and 3.48 total nurse hours per resident day. Hours are the **reported** payroll-based hours CMS publishes, not adjusted for case mix, and the rule's 24/7 RN requirement is not tested because it needs daily payroll data. A facility below a floor is not thereby found to be understaffed for its residents; a facility above one is not thereby found to be adequately staffed.

## Headline numbers

- Facilities with reported hours: 14,288 of 14,690.
- At or above the RN floor: 55.0%; the aide floor: 32.7%; the total floor: 64.0%.
- At or above **all three**: 21.8% (3,110 facilities).
- Average reported hours per resident day: total 3.86, RN 0.69, aide 2.32; nurse turnover 45.8%.

## By ownership type

| Ownership | Facilities with hours | RN floor | Aide floor | Total floor | All three | Avg total hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| For profit | 10,643 | 48.5% | 24.6% | 57.9% | 13.0% | 3.69 |
| Non profit | 2,752 | 78.0% | 58.0% | 85.4% | 49.0% | 4.4 |
| Government | 893 | 61.7% | 51.7% | 70.3% | 42.2% | 4.28 |

## States by share at or above all three floors (states with at least 10 facilities)

Highest:

- AK: 87.5% (total floor 100.0%)
- ME: 79.5% (total floor 97.4%)
- ND: 77.1% (total floor 88.6%)
- HI: 70.7% (total floor 97.6%)
- OR: 64.0% (total floor 99.2%)
- DC: 60.0% (total floor 93.3%)
- MN: 53.0% (total floor 82.3%)
- VT: 51.6% (total floor 100.0%)

Lowest:

- MO: 11.3% (total floor 42.4%)
- OH: 10.7% (total floor 57.2%)
- AR: 10.6% (total floor 85.3%)
- GA: 8.5% (total floor 45.8%)
- TN: 7.6% (total floor 66.2%)
- OK: 5.0% (total floor 68.0%)
- TX: 4.9% (total floor 28.7%)
- LA: 1.6% (total floor 64.0%)

## Since 2019 (history store)

The share at or above all three floors was 23.0% in the 2019-01-17 file, peaked at 28.9% (2020-10-09, when resident counts fell during the pandemic and hours per resident rose), reached a low of 18.0% (2023-04-26) and stands at 21.8% in the 2026-08-26 file (`trend_by_snapshot.csv`). `state_change.csv` compares each state's first and latest file; `trend_by_ownership_year.csv` gives the yearly series by ownership type.

## Files

Every table in this directory is a CSV named for its content; `study.json` records the release, DOI, floors and row counts. Reproduce with `tcr-open-data staffing-study --release releases/v2026.08 --history history --out analysis/staffing/v2026.08`.
