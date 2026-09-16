# Reporter's guide to the ownership study

*The Care Ratings Open Nursing Home Data, ownership study, first edition (release v2026.08, CMS August 2026 vintage). Prepared by the Care Ratings Team. This guide is CC BY 4.0; every number in it can be recomputed from the release.*

## What the study is

Every certified U.S. nursing home files its ownership with CMS on Form CMS-855A. Since the 2023 disclosure rule, that filing has to say whether any owner or other disclosable party is a private-equity company or a real estate investment trust (REIT), and CMS publishes the answers in the PECOS *Skilled Nursing Facility All Owners* file. The study joins that file to Care Compare, the CMS chain file and the CMS change-of-ownership file for one vintage, counts what facilities disclosed, and publishes every table, the code that made them, and a register of the places where the federal files disagree.

Report: https://thecareratings.com/data/ownership/report-2026/
Study pages: https://thecareratings.com/data/ownership/ (state map and table), https://thecareratings.com/data/chains/ (every CMS-identified chain), https://thecareratings.com/data/ownership/discrepancies/ (the register), https://thecareratings.com/data/ownership/state-laws/ (state law tracker)
Data: https://thecareratings.com/data/ (release files with checksums; archived copy with a DOI at Zenodo)
Tables and code: https://github.com/ttiatun/careratings-open-data (folder `analysis/ownership/v2026.08/`)

## The numbers you can quote, and how to say them

The framing matters more than usual here, because the file records what facilities *report*, not what is true. Say "disclose", not "are owned by".

| Right | Wrong |
| --- | --- |
| "65 of 14,690 certified nursing homes (0.44%) disclose a private-equity owner to CMS." | "65 nursing homes are owned by private equity." |
| "577 facilities (3.9%) disclose a REIT in any role, most of them as landlord; 73 (0.5%) disclose a REIT as an owner." | "3.9% of nursing homes are REIT-owned." |
| "Facilities that disclose a private-equity owner have an average rating of 2.30 against 2.99 for those with no such disclosure. The comparison is descriptive." | "Private equity lowers nursing home quality." |
| "1,399 facilities changed hands in the 36 months before the vintage, per the PECOS change-of-ownership file." | "Nursing home turnover is 0.8%" (that is Care Compare's 12-month flag, a different and much narrower measure). |
| "The federal files disagree 2,209 times; 475 certified homes match no PECOS enrollment at all." | "2,209 nursing homes are hiding their owners." |

Key figures, release v2026.08:

- Certified nursing homes: 14,690; matched to a PECOS enrollment: 14,215.
- Disclose a private-equity owner (ownership or control role): 65 (0.44%), 7,404 certified beds. In any role: 97 (0.66%).
- Disclose a REIT owner: 73 (0.5%). In any role: 577 (3.93%), 61,235 beds.
- For-profit: 74.0%. In a CMS-identified chain: 68.9%.
- Changed hands in 36 months (PECOS): 1,399 (9.5%). Care Compare 12-month flag: 113 (0.77%).
- States with at least one facility disclosing a private-equity owner: 13. Pennsylvania 24, Washington 11, South Dakota 6.
- Most-disclosed private-equity owners: EMSIR LLC (7 facilities), LADS Avenue Associates LLC (6), 2020 GSR Dynasty LLC (5), AH Dynasty LLC (5); 28 facilities disclose a private-equity owner whose name is blank in the CMS file.
- Most-disclosed REITs (any role): Welltower (113 facilities), Trilogy Real Estate Investment Trust (72), American Healthcare REIT (68), Sabra Health Care REIT (21).
- Discrepancy register: 2,209 rows across six checks (no PECOS match 475; no ownership-interest party on the enrollment 1,437, of which 1,275 are non-profit or government homes; owners without any percentage 293; PE or REIT in PECOS but individuals only in Care Compare 3; change flag without a PECOS record 1).

## What the study does not say

- It does not estimate how many nursing homes private equity or REITs actually own. GAO put private-equity ownership near 5% in 2022; Chen and colleagues (Health Affairs, 2024) found the CMS file captures about a third of private-equity and under a fifth of REIT investments. The study reports the disclosed share and measures the file's gaps.
- It does not claim any facility or chain has an undisclosed owner. A row in the register means two federal files disagree, or a field is empty. It is not an accusation.
- It does not control for anything. Group averages describe the facilities that disclose; they do not estimate an effect of ownership on care. The private-equity group is 65 facilities.
- It does not harmonize names. Owners and chains are named as CMS prints them.

## Where the numbers come from, so you can check them

- Release v2026.08: CMS Provider Information, Penalties and Ownership files (August 2026); PECOS SNF Enrollments and All Owners (July 31, 2026); Change of Ownership (July 17, 2026); Nursing Home Chain Performance Measures (September 9, 2026). Every file's checksum is in the release manifest.
- Owner versus party: role codes 34, 35, 38, 39, 43, 85 and 86 are owners; every other role is a party. Methodology, section 5 and section 11.
- One command reproduces every table: `tcr-open-data ownership-study --release releases/v2026.08 --history history --out analysis/ownership/v2026.08`.

## State and facility cuts

- Every state's figures: the table under the map at https://thecareratings.com/data/ownership/ and `analysis/ownership/v2026.08/by_state.csv`. A one-page summary per state is in `analysis/ownership/v2026.08/press/state_cuts.md`.
- Every chain: https://thecareratings.com/data/chains/ (facility lists with disclosures, penalties and changes of ownership).
- Every facility in the register: https://thecareratings.com/data/ownership/discrepancies/ (filter by state or chain; CSV download).
- Facility profiles on the site show the PECOS disclosure under "Disclosed to CMS".

## Corrections and contact

Errors are corrected in place and logged at https://thecareratings.com/data/corrections/. Report one through https://thecareratings.com/contact/ naming the page, table and figure. We respond within five business days. A facility that believes its record is wrong should correct it with CMS, the source of every value.

## How to cite

The Care Ratings Team (2026). Who owns America's nursing homes, as disclosed to CMS: Ownership study, first edition (version 1.0, release v2026.08). The Care Ratings. https://thecareratings.com/data/ownership/report-2026/ Data: The Care Ratings Open Nursing Home Data, release v2026.08, https://doi.org/10.5281/zenodo.22780105
