"""
Build the release tables from raw CMS files with DuckDB.

Every table is a SQL projection of the raw files; nothing is hand-edited. The
SQL is deliberately plain so that a reader of the methodology can follow each
derived column back to its source.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from . import __version__
from .headers import check_header, snake
from .schema import DUCKDB_TYPES, load_schema
from .sources import (
    MIN_FACILITIES_FOR_STATE_INDEX, OWNER_ROLE_CODES, REPEALED_AIDE_FLOOR, REPEALED_RN_FLOOR, REPEALED_TOTAL_FLOOR,
    SOURCES,
)

TABLE_ORDER = ["facilities", "penalties", "owners_carecompare", "owners_pecos", "changes_of_ownership", "chains", "state_summary", "crosswalk"]


@dataclass
class BuildResult:
    release: str
    release_dir: Path
    tables: dict[str, dict]
    sources: dict[str, dict]
    chain_measure_columns: list[str]
    built_at: str


def _q(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def _raw_path(raw_dir: Path, sources: dict[str, dict], key: str) -> Path:
    return raw_dir / sources[key]["filename"]


def _install_macros(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE OR REPLACE MACRO yn(x) AS CASE WHEN upper(trim(x)) IN ('Y','YES','TRUE') THEN TRUE WHEN upper(trim(x)) IN ('N','NO','FALSE') THEN FALSE END")
    con.execute("CREATE OR REPLACE MACRO num(x) AS TRY_CAST(replace(replace(replace(trim(x), ',', ''), '$', ''), '%', '') AS DOUBLE)")
    con.execute("CREATE OR REPLACE MACRO int_(x) AS TRY_CAST(num(x) AS INTEGER)")
    con.execute("CREATE OR REPLACE MACRO txt(x) AS NULLIF(trim(x), '')")
    con.execute("CREATE OR REPLACE MACRO dt(x) AS COALESCE(TRY_CAST(trim(x) AS DATE), CAST(TRY_STRPTIME(trim(x), '%m/%d/%Y') AS DATE))")
    con.execute("CREATE OR REPLACE MACRO since_dt(x) AS CAST(TRY_STRPTIME(regexp_replace(trim(x), '^since\\s+', ''), '%m/%d/%Y') AS DATE)")
    con.execute("CREATE OR REPLACE MACRO ccn6(x) AS CASE WHEN regexp_matches(trim(x), '^[0-9]{1,5}$') THEN lpad(trim(x), 6, '0') ELSE txt(x) END")


def file_encoding(path: Path) -> str:
    """CMS publishes most files as UTF-8, but some PECOS files carry Latin-1 bytes."""
    with path.open("rb") as handle:
        decoder = __import__("codecs").getincrementaldecoder("utf-8")()
        try:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                decoder.decode(chunk)
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return "latin-1"
    return "utf-8"


def normalized_copy(path: Path, work_dir: Path) -> tuple[Path, bool]:
    """
    Return a UTF-8 file to read. CMS files are UTF-8 except for stray Windows-1252
    bytes in some PECOS exports; those lines are re-decoded as Windows-1252 so no
    character is lost. The raw archive keeps the original bytes untouched.
    """
    if file_encoding(path) == "utf-8":
        return path, False
    target = work_dir / f"{path.stem}.utf8{path.suffix}"
    with path.open("rb") as src, target.open("wb") as dst:
        for line in src:
            try:
                text = line.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text = line.decode("cp1252")
                except UnicodeDecodeError:
                    text = line.decode("latin-1")
            dst.write(text.encode("utf-8"))
    return target, True


def _read(con: duckdb.DuckDBPyConnection, name: str, path: Path) -> None:
    con.execute(
        f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_csv('{_q(path)}', header=true, all_varchar=true, "
        f"quote='\"', escape='\"', strict_mode=false, encoding='utf-8')"
    )


def build_release(raw_dir: Path, out_root: Path, sources: dict[str, dict], release: str | None = None) -> BuildResult:
    """Build every release table into out_root/<release>/ as CSV and Parquet."""
    schema = load_schema()
    for key, source in SOURCES.items():
        check_header(source, _raw_path(raw_dir, sources, key))

    con = duckdb.connect()
    _install_macros(con)
    work = tempfile.TemporaryDirectory(prefix="tcr-open-data-")
    work_dir = Path(work.name)
    normalized: dict[str, bool] = {}
    for key in SOURCES:
        path, was_normalized = normalized_copy(_raw_path(raw_dir, sources, key), work_dir)
        normalized[key] = was_normalized
        _read(con, f"raw_{key}", path)

    processing_date = con.execute('SELECT MAX(dt("Processing Date")) FROM raw_provider_info').fetchone()[0]
    if processing_date is None:
        raise RuntimeError("Provider Information has no Processing Date; cannot name the release")
    release = release or f"v{processing_date:%Y.%m}"
    release_dir = out_root / release
    release_dir.mkdir(parents=True, exist_ok=True)
    owner_roles = ", ".join(f"'{code}'" for code in OWNER_ROLE_CODES)

    # ── Staging views ────────────────────────────────────────────────────────
    con.execute("""
        CREATE OR REPLACE VIEW enrollments AS
        SELECT txt("ENROLLMENT ID") AS enrollment_id, ccn6("CCN") AS ccn, txt("NPI") AS npi,
               txt("ORGANIZATION NAME") AS organization_name, txt("AFFILIATION ENTITY ID") AS affiliation_entity_id,
               txt("AFFILIATION ENTITY NAME") AS affiliation_entity_name
        FROM raw_enrollments WHERE txt("ENROLLMENT ID") IS NOT NULL
    """)
    # Enrollment ids embed their creation date (O + YYYYMMDD + sequence): the highest id is the current one.
    con.execute("""
        CREATE OR REPLACE VIEW current_enrollment AS
        SELECT * FROM enrollments WHERE ccn IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY ccn ORDER BY enrollment_id DESC) = 1
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE owners_pecos AS
        SELECT txt(o."ENROLLMENT ID") AS enrollment_id,
               e.ccn AS ccn,
               txt(o."ORGANIZATION NAME") AS organization_name,
               txt(o."ASSOCIATE ID - OWNER") AS owner_associate_id,
               txt(o."TYPE - OWNER") AS owner_type,
               txt(o."ROLE CODE - OWNER") AS role_code,
               txt(o."ROLE TEXT - OWNER") AS role_text,
               txt(o."ROLE CODE - OWNER") IN ({owner_roles}) AS is_owner_role,
               dt(o."ASSOCIATION DATE - OWNER") AS association_date,
               txt(o."FIRST NAME - OWNER") AS owner_first_name, txt(o."MIDDLE NAME - OWNER") AS owner_middle_name,
               txt(o."LAST NAME - OWNER") AS owner_last_name, txt(o."TITLE - OWNER") AS owner_title,
               txt(o."ORGANIZATION NAME - OWNER") AS owner_organization_name, txt(o."DOING BUSINESS AS NAME - OWNER") AS owner_dba_name,
               txt(o."CITY - OWNER") AS owner_city, txt(o."STATE - OWNER") AS owner_state, txt(o."ZIP CODE - OWNER") AS owner_zip_code,
               num(o."PERCENTAGE OWNERSHIP") AS percentage_ownership,
               yn(o."CREATED FOR ACQUISITION - OWNER") AS created_for_acquisition,
               yn(o."CORPORATION - OWNER") AS is_corporation, yn(o."LLC - OWNER") AS is_llc,
               yn(o."MEDICAL PROVIDER SUPPLIER - OWNER") AS is_medical_provider_supplier,
               yn(o."MANAGEMENT SERVICES COMPANY - OWNER") AS is_management_services_company,
               yn(o."MEDICAL STAFFING COMPANY - OWNER") AS is_medical_staffing_company,
               yn(o."HOLDING COMPANY - OWNER") AS is_holding_company, yn(o."INVESTMENT FIRM - OWNER") AS is_investment_firm,
               yn(o."FINANCIAL INSTITUTION - OWNER") AS is_financial_institution, yn(o."CONSULTING FIRM - OWNER") AS is_consulting_firm,
               yn(o."FOR PROFIT - OWNER") AS is_for_profit, yn(o."NON PROFIT - OWNER") AS is_non_profit,
               yn(o."PRIVATE EQUITY COMPANY - OWNER") AS is_private_equity_company, yn(o."REIT - OWNER") AS is_reit,
               yn(o."CHAIN HOME OFFICE - OWNER") AS is_chain_home_office, yn(o."TRUST OR TRUSTEE - OWNER") AS is_trust_or_trustee,
               yn(o."OTHER TYPE - OWNER") AS is_other_type, txt(o."OTHER TYPE TEXT - OWNER") AS other_type_text,
               yn(o."PARENT COMPANY - OWNER") AS is_parent_company, yn(o."OWNED BY ANOTHER ORG OR IND - OWNER") AS owned_by_another_org_or_ind
        FROM raw_all_owners o
        LEFT JOIN enrollments e ON e.enrollment_id = txt(o."ENROLLMENT ID")
        WHERE txt(o."ENROLLMENT ID") IS NOT NULL
    """)
    con.execute("""
        CREATE OR REPLACE VIEW owner_summary AS
        SELECT enrollment_id,
               COUNT(*)::INTEGER AS pecos_owner_rows,
               COALESCE(bool_or(is_private_equity_company) FILTER (WHERE is_owner_role), FALSE) AS has_private_equity_owner,
               COALESCE(bool_or(is_reit) FILTER (WHERE is_owner_role), FALSE) AS has_reit_owner,
               COALESCE(bool_or(is_private_equity_company), FALSE) AS has_private_equity_party,
               COALESCE(bool_or(is_reit), FALSE) AS has_reit_party,
               array_to_string(list_sort(list_distinct(list(owner_organization_name) FILTER (WHERE is_private_equity_company AND is_owner_role AND owner_organization_name IS NOT NULL))), '; ') AS private_equity_owner_names,
               array_to_string(list_sort(list_distinct(list(owner_organization_name) FILTER (WHERE is_reit AND is_owner_role AND owner_organization_name IS NOT NULL))), '; ') AS reit_owner_names,
               array_to_string(list_sort(list_distinct(list(owner_organization_name) FILTER (WHERE is_reit AND owner_organization_name IS NOT NULL))), '; ') AS reit_party_names
        FROM owners_pecos GROUP BY enrollment_id
    """)
    con.execute("""
        CREATE OR REPLACE TABLE changes_of_ownership AS
        SELECT txt("ENROLLMENT ID - BUYER") AS buyer_enrollment_id, ccn6("CCN - BUYER") AS buyer_ccn, txt("NPI - BUYER") AS buyer_npi,
               txt("ORGANIZATION NAME - BUYER") AS buyer_organization_name, txt("DOING BUSINESS AS NAME - BUYER") AS buyer_dba_name,
               txt("ENROLLMENT STATE - BUYER") AS buyer_state, txt("CHOW TYPE CODE") AS chow_type_code, txt("CHOW TYPE TEXT") AS chow_type_text,
               dt("EFFECTIVE DATE") AS effective_date, txt("ENROLLMENT ID - SELLER") AS seller_enrollment_id, ccn6("CCN - SELLER") AS seller_ccn,
               txt("NPI - SELLER") AS seller_npi, txt("ORGANIZATION NAME - SELLER") AS seller_organization_name,
               txt("DOING BUSINESS AS NAME - SELLER") AS seller_dba_name, txt("ENROLLMENT STATE - SELLER") AS seller_state
        FROM raw_chow WHERE txt("ENROLLMENT ID - BUYER") IS NOT NULL
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW chow_summary AS
        SELECT buyer_ccn AS ccn, MAX(effective_date) AS last_chow_date,
               COUNT(*) FILTER (WHERE effective_date >= DATE '{processing_date:%Y-%m-%d}' - INTERVAL 36 MONTH)::INTEGER AS chow_count_36mo,
               COUNT(*) FILTER (WHERE effective_date >= DATE '{processing_date:%Y-%m-%d}' - INTERVAL 12 MONTH)::INTEGER AS chow_count_12mo
        FROM changes_of_ownership WHERE buyer_ccn IS NOT NULL GROUP BY buyer_ccn
    """)

    # ── facilities ───────────────────────────────────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TABLE facilities AS
        SELECT ccn6(p."CMS Certification Number (CCN)") AS ccn,
               txt(p."Provider Name") AS provider_name, txt(p."Provider Address") AS address, txt(p."City/Town") AS city,
               txt(p."State") AS state, txt(p."ZIP Code") AS zip_code, txt(p."County/Parish") AS county, yn(p."Urban") AS urban,
               txt(p."Ownership Type") AS ownership_type,
               txt(split_part(p."Ownership Type", ' - ', 1)) AS ownership_category,
               txt(p."Provider Type") AS provider_type, yn(p."Provider Resides in Hospital") AS resides_in_hospital,
               txt(p."Legal Business Name") AS legal_business_name,
               dt(p."Date First Approved to Provide Medicare and Medicaid Services") AS date_first_certified,
               txt(p."Chain ID") AS chain_id, txt(p."Chain Name") AS chain_name, int_(p."Number of Facilities in Chain") AS chain_facility_count,
               yn(p."Continuing Care Retirement Community") AS continuing_care_retirement_community,
               txt(p."Special Focus Status") AS special_focus_status, yn(p."Abuse Icon") AS abuse_icon,
               yn(p."Most Recent Health Inspection More Than 2 Years Ago") AS inspection_over_2_years,
               yn(p."Provider Changed Ownership in Last 12 Months") AS ownership_changed_12mo,
               int_(p."Overall Rating") AS overall_rating, int_(p."Health Inspection Rating") AS health_inspection_rating,
               int_(p."Staffing Rating") AS staffing_rating, int_(p."QM Rating") AS qm_rating,
               int_(p."Long-Stay QM Rating") AS long_stay_qm_rating, int_(p."Short-Stay QM Rating") AS short_stay_qm_rating,
               int_(p."Number of Certified Beds") AS certified_beds, num(p."Average Number of Residents per Day") AS avg_residents_per_day,
               num(p."Reported RN Staffing Hours per Resident per Day") AS reported_rn_hprd,
               num(p."Reported LPN Staffing Hours per Resident per Day") AS reported_lpn_hprd,
               num(p."Reported Nurse Aide Staffing Hours per Resident per Day") AS reported_aide_hprd,
               num(p."Reported Total Nurse Staffing Hours per Resident per Day") AS reported_total_nurse_hprd,
               num(p."Total number of nurse staff hours per resident per day on the weekend") AS weekend_total_nurse_hprd,
               num(p."Adjusted RN Staffing Hours per Resident per Day") AS adjusted_rn_hprd,
               num(p."Adjusted Total Nurse Staffing Hours per Resident per Day") AS adjusted_total_nurse_hprd,
               num(p."Total nursing staff turnover") AS total_nurse_turnover_pct, num(p."Registered Nurse turnover") AS rn_turnover_pct,
               int_(p."Number of administrators who have left the nursing home") AS administrator_departures,
               num(p."Total Weighted Health Survey Score") AS total_weighted_health_survey_score,
               int_(p."Number of Citations from Infection Control Inspections") AS infection_control_citations,
               int_(p."Number of Fines") AS num_fines, num(p."Total Amount of Fines in Dollars") AS total_fines_dollars,
               int_(p."Number of Payment Denials") AS num_payment_denials, int_(p."Total Number of Penalties") AS total_penalties,
               num(p."Latitude") AS latitude, num(p."Longitude") AS longitude, dt(p."Processing Date") AS processing_date,
               e.enrollment_id AS pecos_enrollment_id, e.affiliation_entity_id, e.affiliation_entity_name,
               COALESCE(s.pecos_owner_rows, 0) AS pecos_owner_rows,
               COALESCE(s.has_private_equity_owner, FALSE) AS has_private_equity_owner,
               COALESCE(s.has_reit_owner, FALSE) AS has_reit_owner,
               COALESCE(s.has_private_equity_party, FALSE) AS has_private_equity_party,
               COALESCE(s.has_reit_party, FALSE) AS has_reit_party,
               NULLIF(s.private_equity_owner_names, '') AS private_equity_owner_names,
               NULLIF(s.reit_owner_names, '') AS reit_owner_names,
               NULLIF(s.reit_party_names, '') AS reit_party_names,
               c.last_chow_date, COALESCE(c.chow_count_36mo, 0) AS chow_count_36mo,
               CASE WHEN num(p."Reported RN Staffing Hours per Resident per Day") IS NULL THEN NULL
                    ELSE num(p."Reported RN Staffing Hours per Resident per Day") >= {REPEALED_RN_FLOOR} END AS meets_repealed_rn_floor,
               CASE WHEN num(p."Reported Nurse Aide Staffing Hours per Resident per Day") IS NULL THEN NULL
                    ELSE num(p."Reported Nurse Aide Staffing Hours per Resident per Day") >= {REPEALED_AIDE_FLOOR} END AS meets_repealed_aide_floor,
               CASE WHEN num(p."Reported Total Nurse Staffing Hours per Resident per Day") IS NULL THEN NULL
                    ELSE num(p."Reported Total Nurse Staffing Hours per Resident per Day") >= {REPEALED_TOTAL_FLOOR} END AS meets_repealed_total_floor,
               CASE WHEN num(p."Reported RN Staffing Hours per Resident per Day") IS NULL
                      OR num(p."Reported Nurse Aide Staffing Hours per Resident per Day") IS NULL
                      OR num(p."Reported Total Nurse Staffing Hours per Resident per Day") IS NULL THEN NULL
                    ELSE num(p."Reported RN Staffing Hours per Resident per Day") >= {REPEALED_RN_FLOOR}
                     AND num(p."Reported Nurse Aide Staffing Hours per Resident per Day") >= {REPEALED_AIDE_FLOOR}
                     AND num(p."Reported Total Nurse Staffing Hours per Resident per Day") >= {REPEALED_TOTAL_FLOOR} END AS meets_all_repealed_floors
        FROM raw_provider_info p
        LEFT JOIN current_enrollment e ON e.ccn = ccn6(p."CMS Certification Number (CCN)")
        LEFT JOIN owner_summary s ON s.enrollment_id = e.enrollment_id
        LEFT JOIN chow_summary c ON c.ccn = ccn6(p."CMS Certification Number (CCN)")
        WHERE txt(p."CMS Certification Number (CCN)") IS NOT NULL
    """)

    # ── penalties, owners_carecompare ────────────────────────────────────────
    con.execute("""
        CREATE OR REPLACE TABLE penalties AS
        SELECT ccn6("CMS Certification Number (CCN)") AS ccn, dt("Penalty Date") AS penalty_date, txt("Penalty Type") AS penalty_type,
               txt("Fine ID") AS fine_id, num("Fine Amount") AS fine_amount, dt("Payment Denial Start Date") AS payment_denial_start_date,
               int_("Payment Denial Length in Days") AS payment_denial_length_days, dt("Processing Date") AS processing_date
        FROM raw_penalties WHERE txt("CMS Certification Number (CCN)") IS NOT NULL
    """)
    con.execute("""
        CREATE OR REPLACE TABLE owners_carecompare AS
        SELECT ccn6("CMS Certification Number (CCN)") AS ccn, txt("Role played by Owner or Manager in Facility") AS role,
               txt("Owner Type") AS owner_type, txt("Owner Name") AS owner_name,
               txt("Ownership Percentage") AS ownership_percentage_raw,
               CASE WHEN regexp_matches(trim("Ownership Percentage"), '^[0-9.]+%?$') THEN num("Ownership Percentage") END AS ownership_pct,
               txt("Association Date") AS association_date_raw, since_dt("Association Date") AS association_date,
               dt("Processing Date") AS processing_date
        FROM raw_ownership WHERE txt("CMS Certification Number (CCN)") IS NOT NULL
    """)

    # ── chains (fixed columns + every measure column CMS publishes) ──────────
    chain_header = check_header(SOURCES["chains"], _raw_path(raw_dir, sources, "chains"))
    measure_headers = chain_header[len(SOURCES["chains"].header):]
    measure_columns = [snake(h) for h in measure_headers]
    measure_sql = "".join(f',\n               num("{h.replace(chr(34), chr(34) * 2)}") AS "{c}"' for h, c in zip(measure_headers, measure_columns))
    con.execute(f"""
        CREATE OR REPLACE TABLE chains AS
        SELECT CASE WHEN txt("Chain ID") IS NULL AND lower(trim("Chain")) = 'national' THEN 'NATIONAL' ELSE txt("Chain ID") END AS chain_id,
               txt("Chain") AS chain_name, int_("Number of facilities") AS facility_count,
               int_("Number of states and territories with operations") AS state_count,
               int_("Number of Special Focus Facilities (SFF)") AS sff_count, int_("Number of SFF candidates") AS sff_candidate_count,
               int_("Number of facilities with an abuse icon") AS abuse_icon_count, num("Percentage of facilities with an abuse icon") AS abuse_icon_pct,
               num("Percent of facilities classified as for-profit") AS pct_for_profit, num("Percent of facilities classified as non-profit") AS pct_non_profit,
               num("Percent of facilities classified as government-owned") AS pct_government,
               num("Average overall 5-star rating") AS avg_overall_rating, num("Average health inspection rating") AS avg_health_inspection_rating,
               num("Average staffing rating") AS avg_staffing_rating, num("Average quality rating") AS avg_qm_rating,
               num("Average total nurse hours per resident day") AS avg_total_nurse_hprd,
               num("Average total weekend nurse hours per resident day") AS avg_weekend_nurse_hprd,
               num("Average total Registered Nurse hours per resident day") AS avg_rn_hprd,
               num("Average total nursing staff turnover percentage") AS avg_nurse_turnover_pct,
               num("Average Registered Nurse turnover percentage") AS avg_rn_turnover_pct,
               num("Average number of administrators who have left the nursing home") AS avg_admin_departures,
               int_("Total number of fines") AS total_fines, num("Average number of fines") AS avg_fines,
               num("Total amount of fines in dollars") AS total_fines_dollars, num("Average amount of fines in dollars") AS avg_fines_dollars,
               int_("Total number of payment denials") AS total_payment_denials, num("Average number of payment denials") AS avg_payment_denials{measure_sql}
        FROM raw_chains WHERE txt("Chain") IS NOT NULL
    """)

    # ── state_summary (per state + national 'US') ────────────────────────────
    con.execute(f"""
        CREATE OR REPLACE TABLE state_summary AS
        WITH base AS (
            SELECT f.*, c.chow_count_12mo FROM facilities f LEFT JOIN chow_summary c ON c.ccn = f.ccn
        ), grouped AS (
            SELECT state, * EXCLUDE (state) FROM base
            UNION ALL
            SELECT 'US' AS state, * EXCLUDE (state) FROM base
        ), agg AS (
            SELECT state,
                   COUNT(*)::INTEGER AS facility_count,
                   COUNT(overall_rating)::INTEGER AS rated_facility_count,
                   ROUND(AVG(overall_rating), 2) AS avg_overall_rating,
                   ROUND(COUNT(*) FILTER (WHERE COALESCE(total_penalties, 0) = 0) * 100.0 / COUNT(*), 1) AS pct_zero_penalty,
                   CASE WHEN COUNT(staffing_rating) > 0
                        THEN ROUND(COUNT(*) FILTER (WHERE staffing_rating >= 4) * 100.0 / COUNT(staffing_rating), 1) ELSE 0 END AS pct_staffing_4plus,
                   ROUND(COUNT(*) FILTER (WHERE ownership_category = 'For profit') * 100.0 / COUNT(*), 1) AS pct_for_profit,
                   ROUND(COUNT(*) FILTER (WHERE chain_id IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_chain,
                   COUNT(*) FILTER (WHERE has_private_equity_owner)::INTEGER AS facilities_pe_owner,
                   COUNT(*) FILTER (WHERE has_reit_owner)::INTEGER AS facilities_reit_owner,
                   COUNT(*) FILTER (WHERE has_private_equity_party)::INTEGER AS facilities_pe_party,
                   COUNT(*) FILTER (WHERE has_reit_party)::INTEGER AS facilities_reit_party,
                   COUNT(*) FILTER (WHERE special_focus_status = 'SFF')::INTEGER AS sff_count,
                   COUNT(*) FILTER (WHERE special_focus_status = 'SFF Candidate')::INTEGER AS sff_candidate_count,
                   COUNT(*) FILTER (WHERE abuse_icon)::INTEGER AS abuse_icon_count,
                   COALESCE(SUM(total_fines_dollars), 0) AS total_fines_dollars,
                   ROUND(COALESCE(SUM(total_fines_dollars), 0) / COUNT(*), 0) AS avg_fines_per_facility,
                   ROUND(AVG(reported_total_nurse_hprd), 2) AS avg_reported_total_nurse_hprd,
                   CASE WHEN COUNT(meets_repealed_total_floor) > 0
                        THEN ROUND(COUNT(*) FILTER (WHERE meets_repealed_total_floor) * 100.0 / COUNT(meets_repealed_total_floor), 1) END AS pct_meeting_repealed_total_floor,
                   CASE WHEN COUNT(meets_all_repealed_floors) > 0
                        THEN ROUND(COUNT(*) FILTER (WHERE meets_all_repealed_floors) * 100.0 / COUNT(meets_all_repealed_floors), 1) END AS pct_meeting_all_repealed_floors,
                   COALESCE(SUM(chow_count_12mo), 0)::INTEGER AS chow_count_12mo
            FROM grouped GROUP BY state
        )
        SELECT state, facility_count, rated_facility_count, avg_overall_rating, pct_zero_penalty, pct_staffing_4plus,
               CASE WHEN facility_count >= {MIN_FACILITIES_FOR_STATE_INDEX} AND avg_overall_rating IS NOT NULL
                    THEN ROUND(((avg_overall_rating - 1) / 4 * 100) * 0.40 + pct_zero_penalty * 0.35 + pct_staffing_4plus * 0.25)::INTEGER END AS care_quality_index,
               pct_for_profit, pct_chain, facilities_pe_owner, facilities_reit_owner, facilities_pe_party, facilities_reit_party,
               sff_count, sff_candidate_count, abuse_icon_count, total_fines_dollars, avg_fines_per_facility,
               avg_reported_total_nurse_hprd, pct_meeting_repealed_total_floor, pct_meeting_all_repealed_floors, chow_count_12mo
        FROM agg ORDER BY (state = 'US') DESC, state
    """)

    # ── crosswalk (CC0) ──────────────────────────────────────────────────────
    con.execute("""
        CREATE OR REPLACE TABLE crosswalk AS
        SELECT f.ccn, f.provider_name, f.state, f.pecos_enrollment_id, e.npi, f.affiliation_entity_id, f.chain_id, f.chain_name
        FROM facilities f LEFT JOIN current_enrollment e ON e.enrollment_id = f.pecos_enrollment_id ORDER BY f.ccn
    """)

    # ── Write each table in schema column order, cast to schema types ────────
    tables: dict[str, dict] = {}
    for table in TABLE_ORDER:
        columns = schema["tables"][table]["columns"]
        select = ", ".join(f'CAST("{c["name"]}" AS {DUCKDB_TYPES[c["type"]]}) AS "{c["name"]}"' for c in columns)
        if table == "chains":
            select += "".join(f', CAST("{c}" AS DOUBLE) AS "{c}"' for c in measure_columns)
        order = ", ".join(f'"{k}"' for k in schema["tables"][table]["key"]) if table != "state_summary" else "(state = 'US') DESC, state"
        con.execute(f'CREATE OR REPLACE TABLE out_{table} AS SELECT {select} FROM {table} ORDER BY {order} NULLS LAST')
        csv_path = release_dir / f"{table}.csv"
        parquet_path = release_dir / f"{table}.parquet"
        con.execute(f"COPY out_{table} TO '{_q(csv_path)}' (HEADER, DELIMITER ',')")
        con.execute(f"COPY out_{table} TO '{_q(parquet_path)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        rows = con.execute(f"SELECT COUNT(*) FROM out_{table}").fetchone()[0]
        out_columns = [r[0] for r in con.execute(f"DESCRIBE out_{table}").fetchall()]
        tables[table] = {"rows": int(rows), "columns": out_columns, "csv": csv_path.name, "parquet": parquet_path.name}

    con.close()
    work.cleanup()
    built_at = datetime.now(timezone.utc).isoformat()
    (release_dir / "build.json").write_text(json.dumps({
        "release": release, "built_at": built_at, "builder_version": __version__, "processing_date": processing_date.isoformat(),
        "tables": tables, "chain_measure_columns": measure_columns, "sources": sources,
        "encoding_normalized": [key for key, flag in normalized.items() if flag],
    }, indent=2), encoding="utf-8")
    return BuildResult(release, release_dir, tables, sources, measure_columns, built_at)
