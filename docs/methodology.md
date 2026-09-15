# Methodology

This document describes how a release is built, in enough detail to rebuild it from the same CMS files and get the same bytes.

## 1. Sources

A release is built from seven files published by the Centers for Medicare & Medicaid Services (CMS):

| File | Publisher page | Cadence |
| --- | --- | --- |
| Provider Information (Care Compare, dataset `4pq5-n9py`) | data.cms.gov Provider Data Catalog | Monthly |
| Penalties (`g6vv-u9sr`) | Provider Data Catalog | Monthly |
| Ownership (`y2hd-n93e`) | Provider Data Catalog | Monthly |
| Skilled Nursing Facility Enrollments | data.cms.gov (PECOS) | Monthly |
| Skilled Nursing Facility All Owners | data.cms.gov (PECOS) | Monthly |
| Skilled Nursing Facility Change of Ownership | data.cms.gov (PECOS) | Monthly |
| Nursing Home Chain Performance Measures | data.cms.gov | Monthly |

The current URL of each file is resolved from the CMS catalogs at build time (`catalog.py`). Files are stored under `raw/<release>/` exactly as downloaded, with their original names and SHA-256 checksums in `sources.json`. The release name is `v` plus the year and month of the Provider Information *Processing Date*; the other files carry their own vintages, which the manifest records.

## 2. Header guards

Before any row is mapped, each file's header is compared with the header recorded in `sources.py`. A missing or renamed column stops the build and names the columns involved. The chain performance file may gain averaged quality-measure columns over time; its fixed prefix must match and any additional columns are carried through as measures.

## 3. Encoding

CMS files are UTF-8. Some PECOS exports contain lines with Windows-1252 bytes; those lines are re-decoded as Windows-1252 before reading so that no character is lost or replaced. The raw archive keeps the original bytes; `build.json` lists which sources were normalized.

## 4. Typing

All values are read as text and cast by rule (`build.py`):

- Booleans: `Y`, `YES`, `TRUE` → true; `N`, `NO`, `FALSE` → false; anything else → null.
- Numbers: commas, dollar signs and percent signs are removed, then cast; unparseable values → null.
- Dates: ISO `YYYY-MM-DD` or `MM/DD/YYYY`; the Care Compare "since MM/DD/YYYY" association dates are parsed after the word *since*.
- CCNs: numeric CCNs shorter than six characters are left-padded with zeros; alphanumeric CCNs are kept as published.

## 5. Tables and derived columns

Every column is tagged `cms` (value taken from a CMS file, cast only) or `tcr` (computed by The Care Ratings). The codebook lists the source of each column. The derivations are:

### Current PECOS enrollment for a facility

A CCN can appear under several PECOS enrollments after a change of ownership. PECOS enrollment ids embed their creation date (`O` + YYYYMMDD + sequence), so the highest id for a CCN is taken as the current enrollment. `facilities.pecos_enrollment_id`, the affiliation entity and the owner summary use that enrollment.

### Owner versus party

Form CMS-855A rows are not all owners. The disclosure flags (private equity company, REIT, holding company, and so on) are set on owners, officers, managing employees and *additional disclosable parties* such as landlords, lenders and staffing vendors.

- **Owner** flags (`has_private_equity_owner`, `has_reit_owner`) consider only ownership and control roles: role codes 34, 35, 85, 86 (direct or indirect ownership interest), 38, 39 (partnership interest) and 43 (operational/managerial control).
- **Party** flags (`has_private_equity_party`, `has_reit_party`) consider every reported row.

In the July 2026 file, most REIT-flagged rows are additional disclosable parties (a REIT that owns the building is usually reported that way), and a share of PE-flagged rows are staffing vendors. Reporting both levels keeps "owner" claims narrow while still surfacing REIT landlords.

### Changes of ownership

`last_chow_date` is the latest effective date where the facility's CCN is the buyer. `chow_count_36mo` and the state-level `chow_count_12mo` count events relative to the Provider Information processing date, not the build date, so a rebuild months later gives the same numbers.

### Rescinded federal staffing minimums

The May 2024 federal rule set minimums of 0.55 registered-nurse, 2.45 nurse-aide and 3.48 total nurse hours per resident per day; the interim final rule of December 3, 2025 (effective February 2, 2026) rescinded them. `meets_repealed_*` compare the *reported* (not case-mix adjusted) hours in Provider Information with those floors, as KFF did in its 2024 analysis. The rule's 24/7 registered-nurse requirement is not tested; it needs daily payroll-based journal data.

### State summary and the Care Quality Index

`state_summary` aggregates `facilities` per state and for the nation (`US`). The Care Quality Index is the composite used on thecareratings.com, reproduced exactly:

```
normalized_rating = (avg_overall_rating - 1) / 4 * 100        # avg rounded to 2 decimals
pct_zero_penalty  = facilities with total_penalties = 0 or missing / all facilities * 100   # 1 decimal
pct_staffing_4plus = facilities with staffing_rating >= 4 / facilities with a staffing rating * 100   # 1 decimal
care_quality_index = round(0.40 * normalized_rating + 0.35 * pct_zero_penalty + 0.25 * pct_staffing_4plus)
```

States and territories with fewer than 10 facilities get a null index. The index is a descriptive composite with weights chosen by The Care Ratings; the components are published beside it so anyone can reweight.

## 6. Validation

`validate.py` checks every release before it is published:

- Each table's columns and types match `schema/release_schema.json`; CSV and Parquet row counts agree with `build.json`.
- Keys are unique where the schema declares a unique key; multi-row tables (owners, penalties) only warn on duplicates.
- Totals from `facilities` are reconciled with the national row of the CMS chain file: facility count (tolerance 1%), Special Focus Facilities and candidates (15%), abuse icons (10%), fines and fine dollars (3%), payment denials (5%). The two files are usually different vintages, so small gaps are expected; anything past tolerance is a warning, and `--strict` turns warnings into failures.
- At least 90% of facilities must have a PECOS enrollment, and at least 90% of chain ids in Provider Information must exist in the chain file.

The report is stored as `validation.json` in the release and copied into `manifest.json`.

## 7. Manifest and storage

`manifest.json` lists every file with size, SHA-256 checksum and row count, the CMS sources with their checksums and vintages, the builder version and git commit, the validation report and the license layers. Releases are stored under `releases/<release>/`, raw files under `raw/<release>/`, and a root `manifest.json` indexes all releases with a `latest` pointer.

## 8. Known limitations

- Care Compare's penalties cover CMS's three-year lookback, and the public file does not distinguish per-instance from per-day civil money penalties.
- Special Focus Facility history is not yet included; the current SFF and candidate flags come from Provider Information.
- Ownership disclosure is self-reported. Missing owners or flags reflect what was reported to CMS, not what was verified.
