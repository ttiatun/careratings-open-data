# Changelog

All notable changes to the build and to the release format. Data releases are listed by name; the CMS files behind each one are recorded in that release's `manifest.json`.

## v2026.08 (internal, built September 14, 2026)

First release built by `tcr-open-data` 0.1.0.

- Sources: Care Compare Provider Information, Penalties and Ownership (August 2026); PECOS Skilled Nursing Facility Enrollments and All Owners (July 31, 2026); Change of Ownership (July 17, 2026); Nursing Home Chain Performance Measures (September 9, 2026).
- Tables: `facilities`, `penalties`, `owners_carecompare`, `owners_pecos`, `changes_of_ownership`, `chains`, `state_summary`, `crosswalk`, each as CSV and Parquet.
- Not yet included: Special Focus Facility history (needs archived CMS PDFs), payroll-based journal daily staffing, and any historical vintages. Those arrive with the archive backfill.

## Build 0.1.0

- Initial build pipeline: exact header guards for every CMS file, DuckDB projections, schema-driven typing, validation against the national row of the CMS chain file, manifests with SHA-256 checksums, generated codebook, and R2 publishing.

## History store (built September 15, 2026)

- `tcr-open-data backfill`: monthly Provider Information, Penalties and Ownership snapshots from the CMS archive (January 2019 onward) as raw and harmonized Parquet, stacked into `facilities_history`, `penalties_history`, `ownership_history`, with a coverage table (including each snapshot's CMS vintage) and a manifest. Resumable; records failed snapshots instead of stopping; `--retry-failed` reprocesses them.
- `tcr-open-data reharmonize`: rebuilds the harmonized layer and the stacked tables from the raw Parquet on disk after a synonym-map change.
- `tcr-open-data sff-history`: Special Focus Facility editions from Internet Archive captures of the CMS PDF (April 2012 to April 2024), parsed page by page for the three printed layouts; rows without a printed CCN are matched to facilities by name, state and ZIP.
- `tcr-open-data publish-history`: uploads the history store under `history/` in the research bucket.
