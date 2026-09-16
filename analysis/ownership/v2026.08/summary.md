# Ownership study tables, release v2026.08

Computed from release v2026.08 (CMS Provider Information vintage 2026-08-01; PECOS files as recorded in the release manifest). All ownership figures are **as disclosed to CMS** on Form CMS-855A. A facility without a private-equity or REIT flag has not reported one; that is not a finding that it has none. Quality and enforcement comparisons are descriptive: they do not control for case mix, size, region or the reasons a facility changes hands.

## Headline numbers

- Facilities: 14,690 with 1,567,504 certified beds; 14,215 matched to a PECOS enrollment.
- Disclose a **private-equity owner** (ownership or control roles): 65 facilities (0.44%), 7,404 beds.
- Disclose a **REIT owner**: 73 facilities (0.5%).
- Counting every disclosable party (landlords, lenders, vendors): private equity appears for 97 facilities (0.66%) and a REIT for 577 (3.93%, 61,235 beds). Most REIT disclosures are landlords, not operators.
- For-profit: 74.0% of facilities; in a CMS-identified chain: 68.9%.
- Changes of ownership: 1,399 facilities changed hands in the 36 months before the vintage (0 more than once); Care Compare flags 113 as changed in the last 12 months.

## Quality and enforcement by disclosure group (descriptive)

| Group | Facilities | Avg overall rating | % with any penalty | Avg reported nurse hours/resident/day |
| --- | ---: | ---: | ---: | ---: |
| No PE or REIT disclosure | 13,552 | 2.99 | 46.1 | 3.86 |
| PE or REIT among other disclosable parties only | 529 | 2.74 | 53.9 | 3.56 |
| No PECOS enrollment matched | 475 | 3.07 | 37.7 | 4.23 |
| Discloses a REIT owner | 69 | 3.22 | 42.0 | 3.94 |
| Discloses a private-equity owner | 65 | 2.3 | 63.1 | 3.84 |

## Most-disclosed private-equity owners (ownership or control roles)

CMS leaves the organization name blank on some rows; those are grouped as *Name not published in the CMS file* and are listed in the register by associate id.

- Name not published in the CMS file: 28 facilities
- EMSIR LLC: 7 facilities
- LADS AVENUE ASSOCIATES LLC: 6 facilities
- 2020 GSR DYNASTY LLC: 5 facilities
- AH DYNASTY LLC: 5 facilities

## Most-disclosed REITs (any role, mostly landlords)

- Name not published in the CMS file: 168 facilities
- WELLTOWER INC: 114 facilities
- TRILOGY REAL ESTATE INVESTMENT TRUST: 72 facilities
- AMERICAN HEALTHCARE REIT INC: 68 facilities
- SABRA HEALTH CARE REIT INC: 21 facilities

## States with the most facilities disclosing a private-equity owner

- PA: 24 (3.7% of the state's facilities)
- WA: 11 (5.7% of the state's facilities)
- SD: 6 (6.3% of the state's facilities)
- CA: 4 (0.3% of the state's facilities)
- OH: 4 (0.4% of the state's facilities)
- OR: 4 (3.1% of the state's facilities)
- IA: 3 (0.8% of the state's facilities)
- NV: 3 (4.5% of the state's facilities)

## Changes of ownership by effective year (PECOS)

| Year | Changes |
| --- | ---: |
| 2016 | 240 |
| 2017 | 341 |
| 2018 | 387 |
| 2019 | 547 |
| 2020 | 405 |
| 2021 | 573 |
| 2022 | 722 |
| 2023 | 873 |
| 2024 | 741 |
| 2025 | 395 |
| 2026 | 3 |

## Discrepancy register seeds

- No PECOS enrollment matched to the CCN: 475 facilities
- Ownership changed in the last 12 months per Care Compare, no PECOS change of ownership in 36 months: 1 facilities
- Ownership-interest owners disclosed without any ownership percentage: 293 facilities
- PE or REIT owner disclosed in PECOS, Care Compare lists individuals only: 3 facilities
- PECOS enrollment lists no ownership-interest party: 1,437 facilities

## History store tables

`ownership_change_trend.csv` is the monthly share of facilities Care Compare flags as changed in the last 12 months, since 2019. `carecompare_owner_turnover.csv` counts owner names first seen at a facility per year. Care Compare renamed its role labels in the 2024-12, 2025-06 and 2026-05 vintages (for example DIRECTOR became CORPORATE DIRECTOR, MANAGING EMPLOYEE split into W-2 and CONTRACTED) and the 2026 disclosure rule added categories such as additional disclosable parties, trustees and governing-body members. The turnover table therefore works on role families and only on families that have existed since 2019; a name first appearing under a new label is not a new relationship, and the 2026-only categories are excluded. `carecompare_role_labels.csv` lists every label, its family and the vintages it appears in. The latest year is partial.

Even on that basis the series breaks in 2025: names first seen jump in the 2025-11 and 2026-02 vintages, almost all of them in the operational/managerial control family (`carecompare_owner_turnover_by_family.csv`). That is the arrival of the fuller disclosures required by the 2023 SNF ownership rule on the revised Form CMS-855A, not a wave of facilities changing hands, so counts before and after 2025 are not comparable and no report should describe the rise as turnover. The PECOS change-of-ownership file (`chow_by_year.csv`) is the measure of facilities changing hands.

### Where the raw counts come from

Counted on the label CMS printed, the relationships first seen per year look like this (`carecompare_first_seen_decomposition.csv`). Only *New name at the facility* is a candidate for a new owner relationship, and even that row carries the 2025 disclosure wave.

| Year | Component | Relationships | Share of year |
| --- | --- | ---: | ---: |
| 2024 | Same name and role family, new CMS label | 54,832 | 72.8% |
| 2024 | New name at the facility | 19,129 | 25.4% |
| 2024 | Name already listed at the facility, additional role family | 1,317 | 1.7% |
| 2025 | New name at the facility | 37,325 | 57.1% |
| 2025 | Same name and role family, new CMS label | 18,353 | 28.1% |
| 2025 | Name already listed at the facility, additional role family | 9,649 | 14.8% |
| 2026 | Category added by the 2023 disclosure rule, name already listed at the facility | 60,701 | 42.2% |
| 2026 | Category added by the 2023 disclosure rule, new name | 35,666 | 24.8% |
| 2026 | New name at the facility | 34,714 | 24.1% |
| 2026 | Name already listed at the facility, additional role family | 7,955 | 5.5% |
| 2026 | Same name and role family, new CMS label | 4,954 | 3.4% |

## Files

Every table in this directory is a CSV named for its content; `study.json` records the release, DOI and row counts. Reproduce with `tcr-open-data ownership-study --release releases/v2026.08 --history history --out analysis/ownership/v2026.08`.
