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
- The Special Focus Facility history before 2019 comes from PDFs without CCNs; matches to facilities are by name and ZIP (section 10).
- Ownership disclosure is self-reported. Missing owners or flags reflect what was reported to CMS, not what was verified.

## 9. History store: monthly archive backfill

The Provider Data Catalog keeps a monthly snapshot of the whole nursing-home theme since January 2019 (`/api/1/archive/aggregate/theme/nursing-homes/relative`; 89 monthly zips through August 2026; the annual bundles only re-pack them). `tcr-open-data backfill` (`history.py`) pulls three files out of every snapshot with HTTP range requests, so a run downloads about a tenth of the archive:

| File | Stored as |
| --- | --- |
| Provider Information | `history/raw/provider_info/<snapshot>.parquet` (every CMS column as text) and `history/harmonized/provider_info/<snapshot>.parquet` (typed, canonical names) |
| Penalties | `history/raw/penalties/…`, `history/harmonized/penalties/…` |
| Ownership (Care Compare) | `history/raw/ownership/…`, `history/harmonized/ownership/…` |

The raw file is lossless, so the harmonized layer can be rebuilt without downloading anything (`tcr-open-data reharmonize`) whenever the synonym map gains a column.

### Column eras and the synonym map

CMS renamed the columns twice. The harmonizer maps each canonical column to whichever name the snapshot uses (`FACILITY_COLUMNS`, `PENALTY_COLUMNS`, `OWNERSHIP_COLUMNS` in `history.py`; matching is case-insensitive):

| Era | Snapshots | Example names |
| --- | --- | --- |
| 1 | 2019-01 to 2020-07 (vintages through July 2020) | `PROVNUM`, `PROVNAME`, `OVERALL_RATING`, `FINE_TOT`, `FILEDATE` |
| 2 | 2020-08 to 2023-05 (August 2020 to May 2023 vintages) | `Federal Provider Number`, `Provider City`, `Provider State` |
| 3 | 2023-06 onward (June 2023 vintage and later) | `CMS Certification Number (CCN)`, `City/Town`, `State` |

Columns that a snapshot does not carry are NULL in the harmonized file and listed per snapshot in `history/coverage.csv` (`unmapped_canonical`). Columns the map does not know are kept in the raw file and listed as `unused_source`. Notable gaps and renames:

- The abuse icon starts in late 2019; weekend staffing and turnover in 2022; `urban` in 2026.
- Chain identifiers were published as *Affiliated Entity ID/Name* from 2024 and renamed *Chain ID/Name* in 2026; both map to `chain_id` and `chain_name`.
- `special_focus_status` is `Y`/`N` in era 1 and `SFF`/`SFF Candidate` later.
- The Penalties *Fine ID* appears only in the newest snapshots; earlier penalties are keyed by CCN, date, type and amount.

Besides the release columns, the harmonized facility file carries the case-mix staffing hours, the nursing case-mix index, the phone number, the resident/family council and sprinkler flags, and the rating-cycle-1 survey date, deficiency count and total health score, because the enforcement and staffing analyses need them.

### Snapshot vintages

A snapshot is the archive date; `processing_date` inside the file is the CMS vintage. Some snapshots re-publish the previous month (2020-11/12, 2021-10/11, 2022-10/11, 2023-10/11, 2024-10/11 and 2026-07-29/2026-08-06 share a vintage), and the 2026-08-06 zip carries only Provider Information. `coverage.csv` lists the vintage of every snapshot and table so duplicates can be dropped before counting.

### Stacked tables

- `facilities_history.parquet`: one row per facility per snapshot (`snapshot_date`, `header_era`, then the canonical columns).
- `penalties_history.parquet`: one row per distinct penalty (`ccn`, `penalty_date`, `penalty_type`, `fine_amount`, denial start and length) with `first_seen_snapshot`, `last_seen_snapshot`, `snapshots_seen` and the `fine_id` where CMS published one. Because each monthly file covers a three-year lookback, the union reaches back to penalties imposed in 2016, and a penalty CMS later removed still appears with its last seen date.
- `ownership_history.parquet`: one row per distinct Care Compare owner relationship (`ccn`, `role`, `owner_type`, `owner_name`) with first and last seen snapshots and the latest percentage and association text. The `role` text is the label CMS printed, which changed over time (see *Care Compare role labels* below).
- `coverage.csv` / `coverage.parquet`: snapshot × table presence, row counts, header era, vintage, and unmapped columns.
- `history/manifest.json`: build metadata, file checksums, and any missing files or failed snapshots.

Encoding normalization and type casting follow sections 3 and 4. Numeric CCNs shorter than six characters are left-padded.

### Care Compare role labels

The Ownership file renamed its role labels three times, and a relationship keyed on the printed label therefore ends and a new one begins at each rename. The renames, by the first CMS vintage that carries the new label:

| Vintage | Change |
| --- | --- |
| 2024-12 | `DIRECTOR` became `CORPORATE DIRECTOR`; `OFFICER` became `CORPORATE OFFICER` |
| 2025-06 | `MANAGING EMPLOYEE` split into `W-2 MANAGING EMPLOYEE` and `CONTRACTED MANAGING EMPLOYEE`; `PARTNERSHIP INTEREST` split into `GENERAL` and `LIMITED PARTNERSHIP INTEREST` |
| 2026-05 | `DIRECT` and `INDIRECT OWNERSHIP INTEREST` appear beside the `5% OR GREATER` labels, and the 2023 SNF ownership rule adds categories that did not exist before: `ADP OF THE SNF`, `INDIVIDUAL IS AN OWNER, PARTNER OR TRUSTEE OF ANY ADP OF THE SNF`, `TRUSTEE OF THE SNF`, `MANAGING CONTROL - GOVERNING BODY` |

Any count of relationships over time has to work on role *families* (`ROLE_FAMILIES` in `ownership_study.py`: direct ownership, indirect ownership, partnership, operational/managerial control, corporate director, corporate officer, managing employee, security interest, mortgage interest) and leave out the 2026-only categories. Even then the series breaks in the 2025-11 and 2026-02 vintages, when the fuller disclosures filed on the revised Form CMS-855A reach Care Compare: names first seen in the operational/managerial control family are seven times the earlier annual level. That is a reporting change, not turnover; the PECOS Change of Ownership file is the measure of facilities changing hands. `carecompare_first_seen_decomposition.csv` in the study accounts for the raw count row by row: for the 2026 files, 42% of the 143,990 relationships first seen are rows in the added categories for names the facility had already listed, 25% are added-category rows with new names, 3% are relabels, 6% are additional roles for listed names, and 24% are new names in comparable families.

## 10. Special Focus Facility history

CMS publishes the SFF list as a PDF that it overwrites in place, at `cms.gov/Medicare/Provider-Enrollment-and-Certification/CertificationandComplianc/Downloads/SFFList.pdf`. The Internet Archive has captured it since April 2012. `tcr-open-data sff-history` (`sff.py`) lists one capture per month through the CDX API (queried one year at a time, because a single unbounded query dropped six years of captures), fetches the original bytes of each capture with retries and a pause between downloads, records its SHA-256 (identical consecutive captures are marked `duplicate_of_previous`), and parses the text page by page.

- Each edition carries an "Updated <Month D, YYYY>" line, stored as `edition_date`; the capture date is stored separately.
- Every data page prints its table label once, above or below the rows ("Table A: Facilities Newly Added to the SFF Program", "Table F: SFF Candidate List"). A row takes the nearest label above it, else the first label below it, else the label carried over from the previous page. Table letters changed meaning over the years, so `table_title` is stored with every row.
- 2012 to 2022 editions print no CCN: `Name Street City ST ZIP phone [inspection date] months`. Editions from 2023 print a six-character CCN and a *Met / Not Met* survey column. `layout` records which pattern matched (`rows`, `rows_no_ccn`), and `legacy` marks an edition whose text matched neither.
- The 2015 to 2018 PDFs come out of the text layer column by column (every name, then every address). A page that carries a table label but no row-shaped line is re-extracted in pypdf's layout mode, which keeps each printed row on one line; column spacing and words split after their capital ("W oodley") are repaired before matching.
- Facility name and street address are split at the first street number or "P O Box"; that split is best effort.
- Rows without a printed CCN are matched to `facilities_history` (2019 onward) by normalized name, state and ZIP; then by state and ZIP when only one facility ever had that ZIP; then, among the facilities in that state and ZIP, by the clearly most similar name (Jaccard overlap of distinctive name words of at least 0.5 with no tie). `ccn_match` records `printed`, `name_state_zip`, `state_zip_unique`, `state_zip_name_similar` or `unmatched`. Facilities that closed before 2019 stay unmatched, so the match rate is lowest for the 2012 to 2016 editions.
- Three captures (June 2023, February 2024, December 2024) are exactly 1 MiB in the archive: the crawler cut them off. They are kept with a `.truncated` marker in the raw cache and flagged `truncated` in `sff_editions`; two still parse because their table pages precede the cut, and the December 2024 one is unreadable.
- CMS stopped updating this PDF after the April 24, 2024 edition; later captures carry the same content. Monthly SFF and candidate status from January 2019 onward is available regardless in `facilities_history.special_focus_status`.

## 11. Ownership study tables

`tcr-open-data ownership-study --release releases/<release> --history history --out analysis/ownership/<release>` (`ownership_study.py`) writes the descriptive tables behind the ownership report as CSV, with `summary.md` (the headline numbers in prose, with the caveats) and `study.json` (release, DOI, row counts). Everything is computed with DuckDB from the release tables and, when a history store is present, from `facilities_history` and `ownership_history`; every table names the release it came from, and the tables under `analysis/` in this repository are committed so a reader can check a report against them without rebuilding.

- The framing is *as disclosed to CMS*: the private-equity and REIT flags are the facility's own answers on Form CMS-855A, and the disclosure groups are *discloses a private-equity owner*, *discloses a REIT owner*, *PE or REIT among other disclosable parties only*, *no PECOS enrollment matched* and *no PE or REIT disclosure*. Owner roles follow section 5 (ownership and control role codes); `owner_vs_party.csv` shows how the headline changes when landlords, lenders and vendors count.
- Quality and enforcement comparisons (`quality_by_disclosure.csv`, and the same within for-profit facilities) are descriptive averages of the release columns. They do not control for case mix, size, region or the reasons a facility changes hands, and the report must say so.
- Top-owner tables count facilities per organization name as printed in the PECOS All Owners file. CMS leaves the organization name blank on some rows; those are grouped as *Name not published in the CMS file*.
- `discrepancy_register.csv` is the public discrepancy register: facilities whose CMS files disagree with each other or leave a required disclosure empty. Six checks, all mechanical: no PECOS enrollment matched to the CCN; a current enrollment that lists no ownership-interest party at all (no role code 34, 35, 38, 39, 85 or 86, only officers, directors, managing employees or other parties); ownership-interest owners disclosed with no ownership percentage on any row; a PE or REIT owner in PECOS while Care Compare lists only individuals; a chain id missing from the chain file; and a Care Compare ownership-change flag with no PECOS change of ownership in 36 months. Each row is a statement about two federal files, never a finding about the facility.
- The history tables (`ownership_change_trend.csv`, `carecompare_owner_turnover.csv`, `carecompare_owner_turnover_by_family.csv`, `carecompare_role_labels.csv`) follow the role-family rules in section 9.
- `site/ownership.json` (headline tables, the register counts, and per-state layers for the map: for-profit share, chain share, share disclosing a PE owner, share disclosing a REIT in any role, share that changed hands in 36 months, Care Compare 12-month change flag, share with no PECOS match; states under ten facilities are flagged `suppressed`) and `site/discrepancy_register.json` (the register rows) feed `/data/ownership/` (`ownership_site.py`). `analysis/ownership/state_laws.json`, the state ownership-law tracker, is curated by hand with a primary citation per entry and published beside the study runs.
- `press/state_cuts.md` is a one-section-per-state summary of the state layers with each state's rank among states with at least ten facilities, written for state and regional press; `docs/press/reporters-guide.md` is the reporter's guide to the study (what to quote, how to say it, what the study does not say).
- `site/chains/` holds one JSON per CMS-identified chain and an index (`chain_profiles.py`), which the site renders as `/data/chains/`. Chain identity is CMS's: the id and name come from the Nursing Home Chain Performance Measures file, whose `facility_count` can differ by a few facilities from the number of facilities in the release carrying that chain id (the chain file and Provider Information are cut on different days); a profile shows both. Facility-level fields are the release columns; the disclosure names are the PECOS All Owners rows of each facility's current enrollment, split into owner roles and other disclosable parties. `tcr-open-data publish-analysis` uploads a study run under `analysis/<study>/<release>/` in the store and writes `analysis/<study>/latest.json`, which the site reads to find the newest run; these objects revalidate every five minutes because a study can be corrected.

## 12. Enforcement study tables

`tcr-open-data enforcement-study --release releases/<release> --history history --out analysis/enforcement/<release>` (`enforcement_study.py`) writes the descriptive tables behind the enforcement brief, with `summary.md` and `study.json`, committed under `analysis/enforcement/<release>/`.

- **What the Penalties file is.** One row per fine or payment denial in a three-year lookback, with a penalty date and, for fines, an amount and (in recent vintages) a fine id. It has no field for per-instance versus per-day civil money penalties, so no table distinguishes them. `same_day_fines.csv` counts facility-dates with more than one fine as a description of the file, not as a proxy for penalty type.
- **Rates.** Per-state, per-ownership and per-chain tables use the Provider Information totals (`num_fines`, `total_fines_dollars`, `num_payment_denials`, `total_penalties`) over facilities and certified beds. States under ten facilities are flagged `suppressed`. State differences reflect survey and enforcement practice as much as facility conduct.
- **Concentration.** Facilities are ranked by fine dollars in the lookback (ties broken by CCN); the table gives the share held by the top 1, 5, 10 and 25 percent of all facilities and the fewest facilities that account for half of all fine dollars.
- **Reporting lag and maturity (history store).** `penalties_history` records when each penalty first appeared in a monthly file. `reporting_lag_by_year.csv` gives the days from penalty date to first appearance; the median is six to eight months, so the latest two penalty years are always incomplete. `fines_by_penalty_year.csv` carries that note, and `fines_equal_maturity.csv` counts, for each penalty year, only the fines visible by August 31 of the following year, which is the fair basis for a trend. `fines_in_file_by_snapshot.csv` counts the fine rows of each monthly Penalties file from the harmonized copy of that file (`counted_from` says so), so its latest value equals the release's own count of fines; only snapshots that carried a Penalties file appear, because the CMS archive sometimes re-publishes Provider Information alone. When the harmonized files are not on disk the table falls back to a reconstruction from first and last seen dates and says that instead.
- **What each file added and dropped (history store).** `file_changes_by_snapshot.csv` lists, for each Penalties file after the first, the days since the previous file, the distinct fines first seen in it, the distinct fines last seen in the previous file, and the median lag and share more than a year late among those added. A distinct fine is a facility, penalty date, penalty type and amount, which is how `penalties_history` identifies a penalty across files: two equal fines imposed on one facility on one day count once, so these counts run about two percent below the rows of the files. The table describes the file; it does not say why a batch arrived late and cannot tell a per-instance penalty from a per-day one.
- **Correction, September 17, 2026.** The first version of `fines_in_file_by_snapshot.csv` was reconstructed from first and last seen dates over the Provider Information snapshot dates. That understated recent files by about two percent (12,968 instead of 13,256 fines for 2026-08-26), overstated some 2021 files where a fine was absent from a file between its first and last appearance, and showed a value for 2026-08-06, a snapshot with no Penalties file. The table is now counted from the files; the peak is 37,082 fines on 2023-06-27 (previously given as 37,105).
- **Special Focus Facilities (history store).** `sff_monthly.csv` counts the SFF and candidate flags in every monthly file; `sff_tenure.csv` counts the monthly files in which each facility carried the SFF flag (era 1 `Y`, later `SFF`) since January 2019 and what became of those facilities in the latest file. A count of monthly files is not a count of months where the archive re-published a vintage (section 9).

Both Phase 6 studies also write `site/<study>.json` (`study_site.py`): the run's own CSV tables as one JSON document, nothing recomputed, which the site's `/data/enforcement/` and `/data/staffing/` pages read from the research store after `tcr-open-data publish-analysis`.

## 13. Staffing-standards study tables

`tcr-open-data staffing-study --release releases/<release> --history history --out analysis/staffing/<release>` (`staffing_study.py`) writes the tables behind the staffing-standards tracker.

- **Floors.** 0.55 registered-nurse, 2.45 nurse-aide and 3.48 total nurse hours per resident day: the numeric minimums of the federal rule finalized in 2024 and rescinded by an interim final rule effective February 2, 2026. A facility is *at or above* a floor when its reported hours are greater than or equal to it; *all three* requires all three columns to be present.
- **Hours.** The reported hours per resident day on Provider Information (payroll-based journal data averaged over a quarter), not the case-mix adjusted hours, following KFF's 2024 analysis. The rule's 24/7 RN requirement is not tested: it needs daily payroll data.
- **What the shares mean.** They are a counterfactual description of the rescinded rule, not a finding about adequacy: reported hours are not adjusted for resident acuity, and the denominators exclude facilities with no reported hours (`facilities_with_reported_hours`).
- **History.** `trend_by_snapshot.csv` applies the same test to every monthly file since January 2019; the pandemic years raise hours per resident because resident counts fell faster than staff. `trend_by_ownership_year.csv` derives the ownership category from the ownership type text of each file, and `state_change.csv` compares each state's first and latest file.

## 14. State staffing standards

`analysis/staffing/state_standards.json` is a hand-curated table of the minimum nursing staff that each state and the District of Columbia require of nursing homes by statute or regulation. It is published beside the staffing study runs by `tcr-open-data publish-analysis` and feeds `/data/staffing/state-standards/`.

- **What counts.** A numeric minimum that scales with the number of residents: hours per resident day, a staff-to-resident ratio, or both. Requirements that only repeat the federal rule (a registered nurse 8 consecutive hours a day, licensed nurse coverage around the clock, sufficient staff) are recorded as `standard_type: "none"`, as are rules that fix coverage by a bed-count threshold (Alaska) or count all personnel for fire safety (Missouri); the entry says so.
- **What is recorded.** `total_hprd`, `rn_hprd`, `licensed_hprd` and `aide_hprd` hold only figures the legal text states; a figure the law does not state is null, and nothing is derived from a ratio. Where a rule states period minimums that cover the day (Connecticut), the daily figure is their sum and the note says so. `ratios` restates any ratio rule in plain words. `effective` is filled only when the text or its history note dates the figures themselves.
- **How each entry is checked.** `must_contain` holds short phrases copied from the legal text that carry the figures. `tcr-open-data verify-standards` fetches each entry's `verify_url`, strips it to text (PDFs are parsed in memory) and confirms every phrase is present, comparing on letters, digits and decimal points only so that spacing and punctuation differences between publishers do not matter. `verified_on` is the date of the last passing check. Where the official publisher refuses automated requests or serves a JavaScript application, `verify_url` is another complete copy of the same text (the agency's own compilation, the interface behind the official page, or the Cornell LII copy) and the entry links both.
- **What the check does and does not prove.** A passing check proves the phrases are in the text today. It does not prove that the reading of the law is right, that no other provision modifies it, or that the law will not change tomorrow; each entry was also read by a person, and the notes record conditional tiers, waivers and annual provisos (South Carolina's figure rests on a budget proviso re-enacted each year). A failing check is a prompt to re-read the law, not proof that it changed.
- **What the table is not.** State rules differ in which staff count, over what period hours are averaged, and what may be waived, so figures are not interchangeable across states or with the repealed federal floors. The page sets each state's standard beside the hours its facilities report to CMS; those columns describe the state and do not measure compliance with its law. The summaries restate the law and are not legal advice.
