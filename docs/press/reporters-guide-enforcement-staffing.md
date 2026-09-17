# Reporter's guide to the enforcement and staffing briefs

*The Care Ratings Open Nursing Home Data, enforcement brief and staffing brief, first editions (release v2026.08, CMS August 2026 vintage). Prepared by the Care Ratings Team. This guide is CC BY 4.0; every number in it is read from the tables committed under `analysis/enforcement/v2026.08/` and `analysis/staffing/v2026.08/` by the script that wrote this file.*

## What the two briefs are

**Enforcement.** CMS publishes every federal fine and denial of payment against a certified nursing home in a monthly Penalties file that covers about three years. The brief reads the current file and all 88 monthly files since January 2019: how much, how concentrated, who, where, and how the count has moved when every year is measured at the same age.

**Staffing.** A federal rule published May 10, 2024 set minimum nurse staffing hours. Congress barred its enforcement in July 2025 and CMS repealed the hour floors effective February 2, 2026, before any of them applied. The brief asks how many facilities report hours at or above those floors anyway, and sets that beside what each state requires.

Briefs: https://thecareratings.com/data/enforcement/brief-2026/ and https://thecareratings.com/data/staffing/brief-2026/
Study pages: https://thecareratings.com/data/enforcement/ and https://thecareratings.com/data/staffing/ (state maps and tables), https://thecareratings.com/data/staffing/state-standards/ (what each state requires)
Tables and code: https://github.com/ttiatun/careratings-open-data (folders `analysis/enforcement/v2026.08/` and `analysis/staffing/v2026.08/`)

## The numbers you can quote, and how to say them

| Right | Wrong |
| --- | --- |
| "13,256 federal fines worth $456,752,787 stand against U.S. nursing homes in the CMS file, which covers about three years." | "Nursing homes were fined $456,752,787 this year." |
| "The most-fined 5% of facilities account for 44.5% of fine dollars." | "A few bad actors cause nearly half of violations." (Dollars, not violations; and a fine is not a count of harm.) |
| "For-profit facilities carry $318 in fines per bed against $201 for non-profits. The comparison controls for nothing." | "For-profit ownership causes more violations." |
| "Counted like for like, there were 2,467 fines for 2018, 24,070 for 2021 and 7,818 for 2025." | "Fines have collapsed" or "fines have tripled" (either picks one baseline; give the series). |
| "The public file does not say whether a fine was per instance or per day." | Any count of per-instance or per-day penalties from this file. |
| "21.8% of nursing homes report hours at or above all three repealed federal floors." | "78.2% of nursing homes are understaffed" or "are violating the staffing rule" (no hour floor ever applied, and hours are not adjusted for resident acuity). |
| "35 of 51 jurisdictions set a numeric staffing minimum in law; the figures are not interchangeable, because states count different staff over different periods." | "State X requires more staff than state Y" on the numbers alone. |

Key figures, enforcement, release v2026.08:

- Fines: 13,256 totalling $456,752,787; median $15,593, mean $34,456. Penalties dated 2023-08-19 to 2026-07-29.
- Facilities with at least one fine: 6,514 of 14,690 (44.3%). Payment denials: 2,440.
- Per certified bed: $291; for-profit $318, non-profit $201, government $206.
- Concentration: top 1% of facilities 14.8% of dollars, top 5% 44.5%, top 10% 65.3%; 895 facilities account for half.
- Facilities disclosing a private-equity owner (65 facilities): $457 per bed, 61.5% fined. Small group, incomplete disclosure, descriptive only.
- Highest fine dollars per bed (states with at least 10 facilities): VT $1,008, IL $884, AK $786, MT $694, DE $662.
- Like for like (fines visible by August 31 of the next year): 2018: 2,467 (median $13,286); 2019: 2,172 (median $13,905); 2020: 5,121 (median $4,585); 2021: 24,070 (median $2,600); 2022: 19,075 (median $4,580); 2023: 15,834 (median $9,750); 2024: 9,708 (median $22,205); 2025: 7,818 (median $22,925). The 2025 count is 3.2 times the 2018 count.
- Reporting lag, fines first seen in 2026: median 245 days, 90th percentile 442.
- Fine rows in the monthly file: peak 37,082 (2023-06-27); 2026-05-27: 14,058; 2026-06-24: 13,710; 2026-07-29: 13,687; 2026-08-26: 13,256.
- Special Focus Facilities: 456 facilities flagged in at least one monthly file since 2019; median 15 files; 106 flagged in 24 or more.

Key figures, staffing, release v2026.08:

- At or above all three floors: 21.8% (3,110 of 14,288 facilities with reported hours). RN floor 55.0%, aide floor 32.7%, total floor 64.0%.
- By ownership: for-profit 13.0%, non-profit 49.0%, government 42.2%.
- By star rating: 8.8% of 1-star facilities, 43.2% of 5-star facilities (staffing is an input to the rating).
- Within a quarter hour of the 3.48 total floor, either side: 35.2% of facilities.
- Highest states: AK 87.5%, ME 79.5%, ND 77.1%, HI 70.7%, OR 64.0%. Lowest: LA 1.6%, TX 4.9%, OK 5.0%, TN 7.6%, GA 8.5%.
- Since 2019: 23.0% (2019-01-17), peak 28.9% (2020-10-09), low 18.0% (2023-04-26), now 21.8%.
- Replication: KFF reported 19% on the April 2024 file; the same test on our copy of that file gives 19.3%.
- State law (checked 2026-09-17): 35 of 51 jurisdictions set a numeric minimum; 29 state a total in hours per resident day; 7 of those are at or above 3.48; the highest is DC at 4.1.

## What the briefs do not say

- Neither brief estimates an effect. Differences by ownership, chain, size or disclosure group are descriptions of the facilities in each group.
- The enforcement brief does not separate per-instance from per-day penalties. CMS memo QSO-26-03-NH (revised April 3, 2026) says per-instance penalties "will be displayed on Nursing Home Care Compare beginning June 24, 2026"; the downloadable file shows no added batch at that date and still has no field for penalty type.
- The enforcement brief does not describe appeals, reductions or payment. The file gives one amount per fine.
- The staffing brief does not find any facility understaffed or out of compliance. No federal hour floor ever applied, the hours are not adjusted for resident acuity, and the rule's around-the-clock registered nurse requirement cannot be tested from these files.
- The state table does not rank states. State rules count different staff over different periods and allow different waivers.

## Where the numbers come from, so you can check them

- Release v2026.08: CMS Provider Information and Penalties files (August 2026); the history is every monthly snapshot in the CMS archive since January 2019.
- One command per study reproduces every table: `tcr-open-data enforcement-study` and `tcr-open-data staffing-study` with `--release releases/v2026.08 --history history`.
- The state table is `analysis/staffing/state_standards.json`; `tcr-open-data verify-standards` re-checks every entry against the legal text.
- Methodology sections 12, 13 and 14.

## State cuts

One section per state with ranks: `analysis/enforcement/v2026.08/press/state_cuts.md` and `analysis/staffing/v2026.08/press/state_cuts.md`. The staffing cuts quote each state's own minimum with its citation.

## Corrections and contact

Errors are corrected in place and logged at https://thecareratings.com/data/corrections/. Report one through https://thecareratings.com/contact/ naming the page, table and figure. A facility that believes its record is wrong should correct it with CMS, the source of every value; a state whose law is misstated should tell us, and the entry will be re-checked against the text.

## How to cite

The Care Ratings Team (2026). Where the fines fall: federal penalties against U.S. nursing homes. Enforcement brief, first edition (release v2026.08). The Care Ratings. https://thecareratings.com/data/enforcement/brief-2026/

The Care Ratings Team (2026). The floor that never took effect: nursing home staffing against the repealed federal minimums. Staffing brief, first edition (release v2026.08). The Care Ratings. https://thecareratings.com/data/staffing/brief-2026/

Data: The Care Ratings Open Nursing Home Data, release v2026.08, https://doi.org/10.5281/zenodo.22780105
