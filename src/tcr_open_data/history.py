"""
Historical backfill from the CMS Provider Data Catalog archive.

CMS keeps a monthly snapshot of the whole nursing-home theme since January
2019 (``/api/1/archive/aggregate/theme/nursing-homes/relative``). For every
snapshot this module pulls only the three files the research program needs
(Provider Information, Penalties, Ownership) straight out of the zip with
HTTP range requests, stores a lossless all-text Parquet copy of each, and
projects a harmonized, typed copy through a synonym map that follows the
three column-name eras CMS has used:

  era 1  2019-01 .. 2020-09  uppercase codes   PROVNUM, PROVNAME, FINE_TOT, FILEDATE ...
  era 2  2020-10 .. 2023-09  long names        Federal Provider Number, Provider City ...
  era 3  2023-10 ..          current names     CMS Certification Number (CCN), City/Town ...

The harmonized files are then stacked into facilities_history (one row per
facility per snapshot), penalties_history and ownership_history (one row per
distinct event or relationship with first/last seen snapshot), plus a
coverage table that says which snapshot carried which file and how many
columns could not be mapped. Everything lives in the research store; nothing
touches the production database.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests

from . import __version__
from .build import file_encoding, normalized_copy
from .download import sha256_of

ARCHIVE_INDEX = "https://data.cms.gov/provider-data/api/1/archive/aggregate/theme/nursing-homes/relative"
ARCHIVE_BASE = "https://data.cms.gov"

# Member-name patterns inside a snapshot zip, oldest style first.
MEMBER_PATTERNS = {
    "provider_info": [r"(^|/)ProviderInfo_Download\.csv$", r"NH_ProviderInfo(_[A-Za-z]{3}\d{4})?\.csv$"],
    "penalties": [r"(^|/)Penalties_Download\.csv$", r"NH_Penalties(_[A-Za-z]{3}\d{4})?\.csv$"],
    "ownership": [r"(^|/)Ownership_Download\.csv$", r"NH_Ownership(_[A-Za-z]{3}\d{4})?\.csv$"],
}

# canonical column -> (type, synonyms across eras). Matching is case-insensitive.
FACILITY_COLUMNS: dict[str, tuple[str, list[str]]] = {
    "ccn": ("string", ["PROVNUM", "Federal Provider Number", "CMS Certification Number (CCN)"]),
    "provider_name": ("string", ["PROVNAME", "Provider Name"]),
    "address": ("string", ["ADDRESS", "Provider Address"]),
    "city": ("string", ["CITY", "Provider City", "City/Town"]),
    "state": ("string", ["STATE", "Provider State", "State"]),
    "zip_code": ("string", ["ZIP", "Provider Zip Code", "ZIP Code"]),
    "county": ("string", ["COUNTY_NAME", "Provider County Name", "County/Parish"]),
    "ownership_type": ("string", ["OWNERSHIP", "Ownership Type"]),
    "certified_beds": ("integer", ["BEDCERT", "Number of Certified Beds"]),
    "avg_residents_per_day": ("number", ["RESTOT", "Average Number of Residents per Day"]),
    "provider_type": ("string", ["CERTIFICATION", "Provider Type"]),
    "resides_in_hospital": ("boolean", ["INHOSP", "Provider Resides in Hospital"]),
    "legal_business_name": ("string", ["LBN", "Legal Business Name"]),
    "date_first_certified": ("date", ["PARTICIPATION_DATE", "Date First Approved to Provide Medicare and Medicaid Services"]),
    "continuing_care_retirement_community": ("boolean", ["CCRC_FACIL", "Continuing Care Retirement Community"]),
    "special_focus_status": ("string", ["SFF", "SFFStatus", "Special Focus Status", "Special Focus Facility"]),
    "abuse_icon": ("boolean", ["ABUSE_ICON", "Abuse Icon"]),
    "inspection_over_2_years": ("boolean", ["OLDSURVEY", "Most Recent Health Inspection More Than 2 Years Ago"]),
    "ownership_changed_12mo": ("boolean", ["CHOW_LAST_12MOS", "Provider Changed Ownership in Last 12 Months"]),
    "overall_rating": ("integer", ["OVERALL_RATING", "Overall Rating"]),
    "health_inspection_rating": ("integer", ["SURVEY_RATING", "Health Inspection Rating"]),
    "qm_rating": ("integer", ["QUALITY_RATING", "QM Rating"]),
    "long_stay_qm_rating": ("integer", ["LS_Quality_Rating", "Long-Stay QM Rating"]),
    "short_stay_qm_rating": ("integer", ["SS_Quality_Rating", "Short-Stay QM Rating"]),
    "staffing_rating": ("integer", ["STAFFING_RATING", "Staffing Rating"]),
    "rn_staffing_rating": ("integer", ["RN_STAFFING_RATING", "RN Staffing Rating"]),
    "reported_aide_hprd": ("number", ["AIDHRD", "Reported Nurse Aide Staffing Hours per Resident per Day"]),
    "reported_lpn_hprd": ("number", ["VOCHRD", "Reported LPN Staffing Hours per Resident per Day"]),
    "reported_rn_hprd": ("number", ["RNHRD", "Reported RN Staffing Hours per Resident per Day"]),
    "reported_licensed_hprd": ("number", ["TOTLICHRD", "Reported Licensed Staffing Hours per Resident per Day"]),
    "reported_total_nurse_hprd": ("number", ["TOTHRD", "Reported Total Nurse Staffing Hours per Resident per Day"]),
    "reported_pt_hprd": ("number", ["PTHRD", "Reported Physical Therapist Staffing Hours per Resident Per Day"]),
    "weekend_total_nurse_hprd": ("number", ["Total number of nurse staff hours per resident per day on the weekend"]),
    "weekend_rn_hprd": ("number", ["Registered Nurse hours per resident per day on the weekend"]),
    "adjusted_aide_hprd": ("number", ["ADJ_AIDE", "Adjusted Nurse Aide Staffing Hours per Resident per Day"]),
    "adjusted_lpn_hprd": ("number", ["ADJ_LPN", "Adjusted LPN Staffing Hours per Resident per Day"]),
    "adjusted_rn_hprd": ("number", ["ADJ_RN", "Adjusted RN Staffing Hours per Resident per Day"]),
    "adjusted_total_nurse_hprd": ("number", ["ADJ_TOTAL", "Adjusted Total Nurse Staffing Hours per Resident per Day"]),
    "total_nurse_turnover_pct": ("number", ["Total nursing staff turnover"]),
    "rn_turnover_pct": ("number", ["Registered Nurse turnover"]),
    "administrator_departures": ("integer", ["Number of administrators who have left the nursing home"]),
    "total_weighted_health_survey_score": ("number", ["WEIGHTED_ALL_CYCLES_SCORE", "Total Weighted Health Survey Score"]),
    "facility_reported_incidents": ("integer", ["INCIDENT_CNT", "Number of Facility Reported Incidents"]),
    "substantiated_complaints": ("integer", ["CMPLNT_CNT", "Number of Substantiated Complaints"]),
    "infection_control_citations": ("integer", ["Number of Citations from Infection Control Inspections"]),
    "num_fines": ("integer", ["FINE_CNT", "Number of Fines"]),
    "total_fines_dollars": ("number", ["FINE_TOT", "Total Amount of Fines in Dollars"]),
    "num_payment_denials": ("integer", ["PAYDEN_CNT", "Number of Payment Denials"]),
    "total_penalties": ("integer", ["TOT_PENLTY_CNT", "Total Number of Penalties"]),
    "chain_id": ("string", ["Chain ID", "Affiliated Entity ID"]),
    "chain_name": ("string", ["Chain Name", "Affiliated Entity Name"]),
    "chain_facility_count": ("integer", ["Number of Facilities in Chain"]),
    "urban": ("boolean", ["Urban"]),
    "latitude": ("number", ["Latitude"]),
    "longitude": ("number", ["Longitude"]),
    "phone": ("string", ["PHONE", "Provider Phone Number", "Telephone Number"]),
    "county_ssa_code": ("string", ["COUNTY_SSA", "Provider SSA County Code"]),
    "resident_family_council": ("string", ["RESFAMCOUNCIL", "With a Resident and Family Council"]),
    "sprinkler_status": ("string", ["SPRINKLER_STATUS", "Automatic Sprinkler Systems in All Required Areas"]),
    "case_mix_aide_hprd": ("number", ["CM_AIDE", "Case-Mix Nurse Aide Staffing Hours per Resident per Day"]),
    "case_mix_lpn_hprd": ("number", ["CM_LPN", "Case-Mix LPN Staffing Hours per Resident per Day"]),
    "case_mix_rn_hprd": ("number", ["CM_RN", "Case-Mix RN Staffing Hours per Resident per Day"]),
    "case_mix_total_nurse_hprd": ("number", ["CM_TOTAL", "Case-Mix Total Nurse Staffing Hours per Resident per Day"]),
    "case_mix_weekend_total_nurse_hprd": ("number", ["Case-Mix Weekend Total Nurse Staffing Hours per Resident per Day"]),
    "adjusted_weekend_total_nurse_hprd": ("number", ["Adjusted Weekend Total Nurse Staffing Hours per Resident per Day"]),
    "nursing_case_mix_index": ("number", ["Nursing Case-Mix Index"]),
    "cycle1_survey_date": ("date", ["CYCLE_1_SURVEY_DATE", "Rating Cycle 1 Standard Survey Health Date"]),
    "cycle1_health_deficiencies": ("integer", ["cycle_1_defs", "Rating Cycle 1 Total Number of Health Deficiencies"]),
    "cycle1_total_health_score": ("number", ["cycle_1_Total_Score", "Rating Cycle 1 Total Health Score"]),
    "cycle2_survey_date": ("date", ["CYCLE_2_SURVEY_DATE", "Rating Cycle 2 Standard Health Survey Date"]),
    "processing_date": ("date", ["FILEDATE", "Processing Date"]),
}

PENALTY_COLUMNS: dict[str, tuple[str, list[str]]] = {
    "ccn": ("string", ["provnum", "Federal Provider Number", "CMS Certification Number (CCN)"]),
    "penalty_date": ("date", ["pnlty_date", "Penalty Date"]),
    "penalty_type": ("string", ["pnlty_type", "Penalty Type"]),
    "fine_id": ("string", ["Fine ID"]),
    "fine_amount": ("number", ["fine_amt", "Fine Amount"]),
    "payment_denial_start_date": ("date", ["payden_strt_dt", "Payment Denial Start Date"]),
    "payment_denial_length_days": ("integer", ["payden_days", "Payment Denial Length in Days"]),
    "processing_date": ("date", ["filedate", "Processing Date"]),
}

OWNERSHIP_COLUMNS: dict[str, tuple[str, list[str]]] = {
    "ccn": ("string", ["PROVNUM", "Federal Provider Number", "CMS Certification Number (CCN)"]),
    "role": ("string", ["ROLE_DESC", "Role played by Owner or Manager in Facility"]),
    "owner_type": ("string", ["OWNER_TYPE", "Owner Type"]),
    "owner_name": ("string", ["OWNER_NAME", "Owner Name"]),
    "ownership_percentage_raw": ("string", ["OWNER_PERCENTAGE", "Ownership Percentage"]),
    "association_date_raw": ("string", ["ASSOCIATION_DATE", "Association Date"]),
    "processing_date": ("date", ["filedate", "Processing Date"]),
}

TABLE_COLUMNS = {"provider_info": FACILITY_COLUMNS, "penalties": PENALTY_COLUMNS, "ownership": OWNERSHIP_COLUMNS}
TYPE_SQL = {"string": "VARCHAR", "integer": "INTEGER", "number": "DOUBLE", "boolean": "BOOLEAN", "date": "DATE"}


@dataclass(frozen=True)
class Snapshot:
    date: str
    url: str
    size: int
    name: str


def list_snapshots(session: requests.Session | None = None, index_json: dict | None = None) -> list[Snapshot]:
    """Monthly theme snapshots, oldest first. Annual bundles are skipped (they only re-pack the monthly zips)."""
    if index_json is None:
        session = session or requests.Session()
        response = session.get(ARCHIVE_INDEX, timeout=120)
        response.raise_for_status()
        index_json = response.json()
    snapshots = [Snapshot(d["date"], ARCHIVE_BASE + d["url"], int(d.get("size") or 0), d.get("name", ""))
                 for d in index_json.get("data", []) if d.get("type") == "theme" and d.get("url")]
    return sorted(snapshots, key=lambda s: s.date)


def header_era(header: list[str]) -> int:
    lowered = {h.strip().lower() for h in header}
    if "cms certification number (ccn)" in lowered:
        return 3
    if "federal provider number" in lowered:
        return 2
    return 1


def resolve_columns(header: list[str], spec: dict[str, tuple[str, list[str]]]) -> tuple[dict[str, str], list[str], list[str]]:
    """Map canonical -> actual header name. Returns (mapping, unmapped canonicals, unused source columns)."""
    by_lower = {h.strip().lower(): h for h in header}
    mapping: dict[str, str] = {}
    for canonical, (_type, synonyms) in spec.items():
        for synonym in synonyms:
            actual = by_lower.get(synonym.lower())
            if actual is not None:
                mapping[canonical] = actual
                break
    unmapped = [c for c in spec if c not in mapping]
    used = set(mapping.values())
    unused = [h for h in header if h not in used]
    return mapping, unmapped, unused


def select_member(names: list[str], table: str) -> str | None:
    for pattern in MEMBER_PATTERNS[table]:
        for name in names:
            if name.startswith("__MACOSX") or name.endswith("/"):
                continue
            if re.search(pattern, name):
                return name
    return None


def _q(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def _cast(expr: str, type_name: str) -> str:
    if type_name == "boolean":
        return f"CASE WHEN upper(trim({expr})) IN ('Y','YES','TRUE') THEN TRUE WHEN upper(trim({expr})) IN ('N','NO','FALSE') THEN FALSE END"
    if type_name == "integer":
        return f"TRY_CAST(TRY_CAST(replace(replace(trim({expr}), ',', ''), '$', '') AS DOUBLE) AS INTEGER)"
    if type_name == "number":
        return f"TRY_CAST(replace(replace(replace(trim({expr}), ',', ''), '$', ''), '%', '') AS DOUBLE)"
    if type_name == "date":
        return f"COALESCE(TRY_CAST(trim({expr}) AS DATE), CAST(TRY_STRPTIME(trim({expr}), '%m/%d/%Y') AS DATE))"
    return f"NULLIF(trim({expr}), '')"


def read_header_bytes(raw: bytes) -> list[str]:
    text = raw.decode("utf-8-sig", errors="replace").splitlines()[0]
    return [h.strip() for h in next(csv.reader(io.StringIO(text)))]


def _write_harmonized(con: duckdb.DuckDBPyConnection, header: list[str], table: str, snapshot_date: str, harmonized_out: Path) -> dict:
    """Project the src view (all text, original CMS names) onto the canonical columns; return coverage facts."""
    spec = TABLE_COLUMNS[table]
    mapping, unmapped, unused = resolve_columns(header, spec)
    era = header_era(header)
    selects = [f"DATE '{snapshot_date}' AS snapshot_date", f"{era} AS header_era"]
    for canonical, (type_name, _syn) in spec.items():
        if canonical in mapping:
            source = '"' + mapping[canonical].replace('"', '""') + '"'
            expr = _cast(source, type_name)
            if canonical == "ccn":
                expr = f"CASE WHEN regexp_matches(trim({source}), '^[0-9]{{1,5}}$') THEN lpad(trim({source}), 6, '0') ELSE NULLIF(trim({source}), '') END"
        else:
            expr = f"CAST(NULL AS {TYPE_SQL[type_name]})"
        selects.append(f'{expr} AS "{canonical}"')
    harmonized_out.parent.mkdir(parents=True, exist_ok=True)
    where = ""
    if "ccn" in mapping:
        ccn_source = '"' + mapping["ccn"].replace('"', '""') + '"'
        where = f" WHERE {_cast(ccn_source, 'string')} IS NOT NULL"
    con.execute(f"COPY (SELECT {', '.join(selects)} FROM src{where}) TO '{_q(harmonized_out)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    rows, processing_date = con.execute(f"SELECT COUNT(*), MIN(processing_date) FROM read_parquet('{_q(harmonized_out)}')").fetchone()
    return {"snapshot_date": snapshot_date, "table": table, "rows": int(rows), "header_era": era, "source_columns": len(header),
            "mapped": len(mapping), "unmapped_canonical": unmapped, "unused_source": unused,
            "processing_date": processing_date.isoformat() if processing_date else None}


def harmonize_csv(con: duckdb.DuckDBPyConnection, csv_path: Path, table: str, snapshot_date: str,
                  raw_out: Path, harmonized_out: Path) -> dict:
    """Write the lossless raw Parquet and the harmonized Parquet for one file; return coverage facts."""
    with csv_path.open("rb") as handle:
        header = read_header_bytes(handle.read(64_000))
    con.execute(f"""CREATE OR REPLACE VIEW src AS SELECT * FROM read_csv('{_q(csv_path)}', header=true, all_varchar=true,
                    quote='"', escape='"', strict_mode=false, encoding='utf-8')""")
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""COPY (SELECT DATE '{snapshot_date}' AS snapshot_date, * FROM src)
                    TO '{_q(raw_out)}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    return _write_harmonized(con, header, table, snapshot_date, harmonized_out)


def reharmonize_snapshot(con: duckdb.DuckDBPyConnection, raw_parquet: Path, table: str, snapshot_date: str, harmonized_out: Path) -> dict:
    """Rebuild one harmonized file from its raw Parquet (no download), e.g. after the synonym map changes."""
    con.execute(f"CREATE OR REPLACE VIEW src AS SELECT * EXCLUDE (snapshot_date) FROM read_parquet('{_q(raw_parquet)}')")
    header = [row[0] for row in con.execute("DESCRIBE src").fetchall()]
    return _write_harmonized(con, header, table, snapshot_date, harmonized_out)


def process_snapshot(snapshot: Snapshot, history_dir: Path, tables: list[str], con: duckdb.DuckDBPyConnection,
                     zip_opener=None) -> list[dict]:
    """Extract the wanted members of one snapshot zip and write raw + harmonized Parquet. Returns coverage rows."""
    from remotezip import RemoteZip  # imported lazily so tests can inject a local zip opener

    opener = zip_opener or (lambda url: RemoteZip(url))
    coverage: list[dict] = []
    with opener(snapshot.url) as zf:
        names = [i.filename for i in zf.infolist()]
        with tempfile.TemporaryDirectory(prefix="tcr-history-") as tmp:
            for table in tables:
                member = select_member(names, table)
                if member is None:
                    coverage.append({"snapshot_date": snapshot.date, "table": table, "rows": 0, "header_era": None, "source_columns": 0,
                                     "mapped": 0, "unmapped_canonical": list(TABLE_COLUMNS[table]), "unused_source": [], "member": None})
                    continue
                target = Path(tmp) / f"{table}.csv"
                with zf.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
                usable, _ = normalized_copy(target, Path(tmp))
                facts = harmonize_csv(con, usable, table, snapshot.date,
                                      history_dir / "raw" / table / f"{snapshot.date}.parquet",
                                      history_dir / "harmonized" / table / f"{snapshot.date}.parquet")
                facts["member"] = member
                coverage.append(facts)
    return coverage


def load_coverage(history_dir: Path) -> dict[tuple[str, str], dict]:
    """coverage.jsonl keyed by (snapshot_date, table); the last record for a key wins."""
    path = history_dir / "coverage.jsonl"
    rows: dict[tuple[str, str], dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[(row["snapshot_date"], row["table"])] = row
    return rows


def write_coverage(history_dir: Path, rows: dict[tuple[str, str], dict]) -> list[dict]:
    ordered = [rows[k] for k in sorted(rows)]
    history_dir.mkdir(parents=True, exist_ok=True)
    with (history_dir / "coverage.jsonl").open("w", encoding="utf-8") as handle:
        for row in ordered:
            handle.write(json.dumps(row) + "\n")
    return ordered


def backfill(history_dir: Path, snapshots: list[Snapshot], tables: list[str] | None = None, resume: bool = True,
             progress=print, zip_opener=None, retry_failed: bool = False) -> list[dict]:
    """Process every snapshot and return the coverage rows. With resume=True, (snapshot, table) pairs already in
    coverage.jsonl are skipped; retry_failed=True reprocesses pairs recorded with an error or without a member."""
    tables = tables or list(MEMBER_PATTERNS)
    con = duckdb.connect()
    coverage = load_coverage(history_dir)
    history_dir.mkdir(parents=True, exist_ok=True)

    def is_done(key: tuple[str, str]) -> bool:
        if not resume or key not in coverage:
            return False
        row = coverage[key]
        return not (retry_failed and (row.get("error") or row.get("member") is None))

    for snapshot in snapshots:
        pending = [t for t in tables if not is_done((snapshot.date, t))]
        if not pending:
            continue
        progress(f"{snapshot.date}: {', '.join(pending)}")
        try:
            rows = process_snapshot(snapshot, history_dir, pending, con, zip_opener=zip_opener)
        except Exception as exc:  # noqa: BLE001 - record and continue; the coverage table shows the gap
            progress(f"{snapshot.date}: FAILED {type(exc).__name__}: {str(exc)[:160]}")
            rows = [{"snapshot_date": snapshot.date, "table": t, "rows": 0, "header_era": None, "source_columns": 0, "mapped": 0,
                     "unmapped_canonical": [], "unused_source": [], "member": None, "processing_date": None,
                     "error": f"{type(exc).__name__}: {str(exc)[:300]}"} for t in pending]
        with (history_dir / "coverage.jsonl").open("a", encoding="utf-8") as handle:
            for row in rows:
                coverage[(row["snapshot_date"], row["table"])] = row
                handle.write(json.dumps(row) + "\n")
    con.close()
    return write_coverage(history_dir, coverage)


def reharmonize(history_dir: Path, tables: list[str] | None = None, progress=print) -> list[dict]:
    """Rebuild every harmonized file from the raw Parquet files on disk and refresh their coverage rows."""
    tables = tables or list(MEMBER_PATTERNS)
    con = duckdb.connect()
    coverage = load_coverage(history_dir)
    for table in tables:
        for raw in sorted((history_dir / "raw" / table).glob("*.parquet")):
            snapshot_date = raw.stem
            facts = reharmonize_snapshot(con, raw, table, snapshot_date, history_dir / "harmonized" / table / f"{snapshot_date}.parquet")
            previous = coverage.get((snapshot_date, table), {})
            facts["member"] = previous.get("member")
            coverage[(snapshot_date, table)] = facts
            progress(f"{snapshot_date}: {table} rows={facts['rows']} unmapped={len(facts['unmapped_canonical'])}")
    con.close()
    return write_coverage(history_dir, coverage)


def consolidate(history_dir: Path) -> dict:
    """Stack the harmonized snapshots into the history tables and write coverage + manifest."""
    con = duckdb.connect()
    out: dict[str, dict] = {}

    def glob(table: str) -> str:
        return _q(history_dir / "harmonized" / table) + "/*.parquet"

    fac = history_dir / "facilities_history.parquet"
    con.execute(f"COPY (SELECT * FROM read_parquet('{glob('provider_info')}', union_by_name=true) ORDER BY snapshot_date, ccn) TO '{_q(fac)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    out["facilities_history"] = {"rows": con.execute(f"SELECT COUNT(*) FROM read_parquet('{_q(fac)}')").fetchone()[0]}

    pen = history_dir / "penalties_history.parquet"
    con.execute(f"""COPY (
        SELECT ccn, penalty_date, penalty_type, fine_amount, payment_denial_start_date, payment_denial_length_days,
               MAX(fine_id) AS fine_id, MIN(snapshot_date) AS first_seen_snapshot, MAX(snapshot_date) AS last_seen_snapshot,
               COUNT(DISTINCT snapshot_date)::INTEGER AS snapshots_seen, MIN(processing_date) AS first_processing_date
        FROM read_parquet('{glob('penalties')}', union_by_name=true)
        WHERE ccn IS NOT NULL AND penalty_date IS NOT NULL
        GROUP BY ALL ORDER BY ccn, penalty_date, penalty_type) TO '{_q(pen)}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    out["penalties_history"] = {"rows": con.execute(f"SELECT COUNT(*) FROM read_parquet('{_q(pen)}')").fetchone()[0],
                                "earliest_penalty_date": str(con.execute(f"SELECT MIN(penalty_date) FROM read_parquet('{_q(pen)}')").fetchone()[0])}

    own = history_dir / "ownership_history.parquet"
    con.execute(f"""COPY (
        SELECT ccn, role, owner_type, owner_name,
               MIN(snapshot_date) AS first_seen_snapshot, MAX(snapshot_date) AS last_seen_snapshot,
               COUNT(DISTINCT snapshot_date)::INTEGER AS snapshots_seen,
               arg_max(ownership_percentage_raw, snapshot_date) AS latest_ownership_percentage_raw,
               arg_max(association_date_raw, snapshot_date) AS latest_association_date_raw
        FROM read_parquet('{glob('ownership')}', union_by_name=true)
        WHERE ccn IS NOT NULL AND owner_name IS NOT NULL
        GROUP BY ALL ORDER BY ccn, role, owner_name) TO '{_q(own)}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    out["ownership_history"] = {"rows": con.execute(f"SELECT COUNT(*) FROM read_parquet('{_q(own)}')").fetchone()[0]}

    coverage_rows = write_coverage(history_dir, load_coverage(history_dir))
    cov_csv = history_dir / "coverage.csv"
    with cov_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["snapshot_date", "table", "present", "rows", "header_era", "source_columns", "mapped_columns", "unmapped_canonical", "unused_source", "member", "error", "processing_date"])
        for r in coverage_rows:
            writer.writerow([r["snapshot_date"], r["table"], r.get("member") is not None, r["rows"], r.get("header_era"), r["source_columns"],
                             r["mapped"], ";".join(r.get("unmapped_canonical", [])), ";".join(r.get("unused_source", [])), r.get("member") or "", r.get("error", ""),
                             r.get("processing_date") or ""])
    con.execute(f"COPY (SELECT * FROM read_csv('{_q(cov_csv)}', header=true, all_varchar=true)) TO '{_q(history_dir / 'coverage.parquet')}' (FORMAT PARQUET)")
    con.close()

    snapshots = sorted({r["snapshot_date"] for r in coverage_rows})
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(), "builder": {"name": "tcr-open-data", "version": __version__},
        "source": ARCHIVE_INDEX, "snapshots": {"count": len(snapshots), "first": snapshots[0] if snapshots else None, "last": snapshots[-1] if snapshots else None},
        "tables": out,
        "files": [{"path": p.relative_to(history_dir).as_posix(), "bytes": p.stat().st_size, "sha256": sha256_of(p)}
                  for p in sorted(history_dir.rglob("*.parquet")) if p.parent == history_dir],
        "coverage": {"missing_files": [(r["snapshot_date"], r["table"]) for r in coverage_rows if r.get("member") is None],
                     "errors": [(r["snapshot_date"], r["table"], r["error"]) for r in coverage_rows if r.get("error")]},
        "notes": [
            "Raw per-snapshot files (history/raw/<table>/<date>.parquet) keep every CMS column as text; harmonized files apply the synonym map in history.py.",
            "penalties_history and ownership_history are unions across snapshots with first/last seen dates; a penalty that CMS later removed still appears with its last_seen_snapshot.",
            "Some snapshots re-publish the previous month's file (same processing_date); coverage.csv lists the processing_date of every snapshot so duplicates can be dropped.",
        ],
    }
    (history_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
