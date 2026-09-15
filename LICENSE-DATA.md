# Data license notice

A release mixes public-domain federal data with work by The Care Ratings. The terms differ by layer, and every column in a release is tagged with its layer in `codebook.md` (`cms` or `tcr`).

| Layer | What it covers | Terms |
| --- | --- | --- |
| CMS source values | Every value taken from a Centers for Medicare & Medicaid Services file: ratings, staffing hours, fines, owner names, disclosure flags, and so on (columns tagged `cms`). | Work of the United States government, in the public domain. CMS declares <https://www.usa.gov/government-works> for these datasets. No attribution to The Care Ratings is required to reuse these values. |
| Derived data | Columns computed or curated by The Care Ratings (tagged `tcr`) and the selection and arrangement of each release: harmonized identifiers, ownership and staffing flags, state summaries, the Care Quality Index. | [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/), applying only to those contributions. Facts are not copyrightable in the United States; this notice records an attribution request for our work and never claims rights over federal data. |
| Identifier crosswalk | The `crosswalk` table (CCN, PECOS enrollment id, NPI, affiliation entity id, chain id). | [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/), so it can be reused in public knowledge bases without attribution. |
| Documentation | `codebook.md`, `methodology.md`, release notes, and the reports built on the data. | CC BY 4.0. |
| Code | The build scripts, schema, and tests in this repository. | [MIT](LICENSE). |

## Attribution

When you reuse `tcr` columns or a release as a whole, please cite:

> The Care Ratings. Open Nursing Home Data, release vYYYY.MM. Built from Centers for Medicare & Medicaid Services public files. https://thecareratings.com/data/

Each release carries a `manifest.json` with checksums and the exact CMS files it was built from; cite the release name so readers can retrieve the same files.

## What the data is not

The disclosure flags in `owners_pecos` and the `has_*` columns in `facilities` are the facility's own answers on Form CMS-855A. A facility that does not disclose a private-equity or REIT owner has not reported one; that is not a finding that it has none. The Government Accountability Office (2023) and Chen et al. (Health Affairs, 2024) documented that CMS ownership data captures only part of private-equity and REIT investment.
