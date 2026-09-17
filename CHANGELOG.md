# Changelog

All notable changes to the build and to the release format. Data releases are listed by name; the CMS files behind each one are recorded in that release's `manifest.json`.

## v2026.08 (built September 14, 2026; published September 15, 2026)

First release built by `tcr-open-data` 0.1.0. Archived at Zenodo: DOI 10.5281/zenodo.22780105 (concept DOI 10.5281/zenodo.22780104). Served from https://data.thecareratings.com/releases/v2026.08/.

- Sources: Care Compare Provider Information, Penalties and Ownership (August 2026); PECOS Skilled Nursing Facility Enrollments and All Owners (July 31, 2026); Change of Ownership (July 17, 2026); Nursing Home Chain Performance Measures (September 9, 2026).
- Tables: `facilities`, `penalties`, `owners_carecompare`, `owners_pecos`, `changes_of_ownership`, `chains`, `state_summary`, `crosswalk`, each as CSV and Parquet.
- Not yet included: Special Focus Facility history (needs archived CMS PDFs), payroll-based journal daily staffing, and any historical vintages. Those arrive with the archive backfill.

## Build 0.1.0

- Initial build pipeline: exact header guards for every CMS file, DuckDB projections, schema-driven typing, validation against the national row of the CMS chain file, manifests with SHA-256 checksums, generated codebook, and R2 publishing.

## Enforcement and staffing study tables (September 2026)

- `tcr-open-data enforcement-study`: fines and payment denials by state, ownership, disclosure group and chain, fine sizes, concentration of fine dollars, and, from the history store, the reporting lag, the trend at equal maturity, fines present in each monthly file and Special Focus Facility tenure. The Penalties file has no per-instance flag and nothing here infers one.
- `tcr-open-data staffing-study`: the share of facilities reporting hours at or above the rescinded federal floors (0.55 RN, 2.45 aide, 3.48 total), by state, ownership, chain, rating and size, with the monthly trend since 2019. Reported hours, not case-mix adjusted; the 24/7 RN requirement is not tested.

## Ownership study tables (September 16, 2026)

- `tcr-open-data ownership-study`: the descriptive tables behind the ownership report from a release and the history store, committed under `analysis/ownership/<release>/` with `summary.md` and `study.json`.
- Care Compare role labels are mapped to role families (`ROLE_FAMILIES`) so the three CMS relabels (2024-12, 2025-06, 2026-05) and the 2026-only disclosure categories do not count as owner turnover; `carecompare_role_labels.csv` documents every label and its vintages.
- Chain profiles: the study writes `site/chains/index.json` and one JSON per CMS-identified chain (`chain_profiles.py`) for the `/data/chains/` pages; `tcr-open-data publish-analysis` uploads a study run to `analysis/<study>/<release>/` and points `analysis/<study>/latest.json` at it.
- Discrepancy register widened to six checks (adds: current enrollment with no ownership-interest party; ownership-interest owners with no percentage on any row). `site/ownership.json` and `site/discrepancy_register.json` (`ownership_site.py`) feed `/data/ownership/`; study-level JSON beside the runs (`analysis/ownership/state_laws.json`) is published with `publish-analysis`.

## History store (built September 15, 2026)

- `tcr-open-data backfill`: monthly Provider Information, Penalties and Ownership snapshots from the CMS archive (January 2019 onward) as raw and harmonized Parquet, stacked into `facilities_history`, `penalties_history`, `ownership_history`, with a coverage table (including each snapshot's CMS vintage) and a manifest. Resumable; records failed snapshots instead of stopping; `--retry-failed` reprocesses them.
- `tcr-open-data reharmonize`: rebuilds the harmonized layer and the stacked tables from the raw Parquet on disk after a synonym-map change.
- `tcr-open-data sff-history`: Special Focus Facility editions from Internet Archive captures of the CMS PDF (April 2012 to April 2024), parsed page by page for the three printed layouts; rows without a printed CCN are matched to facilities by name, state and ZIP.
- `tcr-open-data publish-history`: uploads the history store under `history/` in the research bucket.
