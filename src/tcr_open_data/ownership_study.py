"""
Ownership study: the descriptive tables behind report D1.

    tcr-open-data ownership-study --release releases/v2026.08 [--history history] --out analysis/ownership/v2026.08

Everything is computed with DuckDB from the release tables (facilities,
owners_pecos, owners_carecompare, changes_of_ownership, chains,
state_summary) and, when a history store is present, from
facilities_history and ownership_history. Every output names the release it
came from. The framing is "as disclosed to CMS": a facility with no
private-equity or REIT flag has not reported one, which is not a finding
that it has none (GAO-23-106036; Chen et al., Health Affairs 2024).

Outputs (CSV unless noted):
  national_summary        one row: counts and shares for the whole release
  by_state                counts, shares and averages per state
  owner_vs_party          how the headline changes when landlords/vendors count
  quality_by_disclosure   descriptive quality/enforcement measures per disclosure group
  quality_by_disclosure_for_profit   the same within for-profit facilities only
  top_private_equity_owners, top_reit_parties   organizations by facilities disclosed
  chains_with_disclosures largest chains with their disclosure counts
  chow_by_year, chow_by_state  changes of ownership over time and by state
  ownership_change_trend  monthly share of facilities with an ownership change (history store)
  carecompare_owner_turnover  Care Compare owner names first seen per year, roles harmonized (history store)
  carecompare_owner_turnover_by_family  the same count per year and role family (history store)
  carecompare_role_labels  every Care Compare role label with its family and the vintages it appears in (history store)
  carecompare_first_seen_decomposition  the raw count of relationships first seen per year, split into relabels, added categories, extra roles and new names (history store)
  discrepancy_register    seed rows for the discrepancy register, by type
  summary.md              the headline numbers in prose, with the caveats
  site/chains/            one JSON per CMS-identified chain plus an index, for the /data/chains/ pages (chain_profiles.py)
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from . import __version__
from .chain_profiles import write_chain_profiles

# Care Compare renamed its ownership roles three times (vintages 2024-12, 2025-06 and
# 2026-05) and, with the 2026 disclosure rule, added categories that did not exist
# before. Counting a relabelled row as a new owner relationship would show a wave of
# turnover that never happened, so the history tables work on role *families*.
# Families marked comparable have existed since the first 2019 snapshot.
ROLE_FAMILIES: dict[str, tuple[str, bool]] = {
    "5% OR GREATER DIRECT OWNERSHIP INTEREST": ("Direct ownership interest", True),
    "DIRECT OWNERSHIP INTEREST": ("Direct ownership interest", True),
    "5% OR GREATER INDIRECT OWNERSHIP INTEREST": ("Indirect ownership interest", True),
    "INDIRECT OWNERSHIP INTEREST": ("Indirect ownership interest", True),
    "PARTNERSHIP INTEREST": ("Partnership interest", True),
    "GENERAL PARTNERSHIP INTEREST": ("Partnership interest", True),
    "LIMITED PARTNERSHIP INTEREST": ("Partnership interest", True),
    "OPERATIONAL/MANAGERIAL CONTROL": ("Operational/managerial control", True),
    "DIRECTOR": ("Corporate director", True),
    "CORPORATE DIRECTOR": ("Corporate director", True),
    "OFFICER": ("Corporate officer", True),
    "CORPORATE OFFICER": ("Corporate officer", True),
    "MANAGING EMPLOYEE": ("Managing employee", True),
    "W-2 MANAGING EMPLOYEE": ("Managing employee", True),
    "CONTRACTED MANAGING EMPLOYEE": ("Managing employee", True),
    "5% OR GREATER SECURITY INTEREST": ("Security interest", True),
    "5% OR GREATER MORTGAGE INTEREST": ("Mortgage interest", True),
    "MANAGING CONTROL - GOVERNING BODY": ("Governing body (2026 category)", False),
    "TRUSTEE OF THE SNF": ("Trustee (2026 category)", False),
    "ADP OF THE SNF": ("Additional disclosable party (2026 category)", False),
    "INDIVIDUAL IS AN OWNER, PARTNER OR TRUSTEE OF ANY ADP OF THE SNF": ("Additional disclosable party (2026 category)", False),
}


def role_family(role: str | None) -> tuple[str, bool]:
    """Map a Care Compare role label to (family, comparable_since_2019); unknown labels are their own, non-comparable family."""
    key = (role or "").strip().upper()
    return ROLE_FAMILIES.get(key, (key.title() if key else "Unknown", False))


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


ROLE_FAMILY_SQL = "CASE " + " ".join(
    f"WHEN upper(trim(role)) = {_sql_literal(label)} THEN {_sql_literal(family)}" for label, (family, _c) in ROLE_FAMILIES.items()
) + " ELSE COALESCE(upper(trim(role)), 'UNKNOWN') END"
COMPARABLE_ROLE_SQL = "upper(trim(role)) IN (" + ", ".join(_sql_literal(label) for label, (_f, comparable) in ROLE_FAMILIES.items() if comparable) + ")"


def _q(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def _write_csv(path: Path, columns: list[str], rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["" if v is None else v for v in row])


def _run(con: duckdb.DuckDBPyConnection, sql: str) -> tuple[list[str], list[tuple]]:
    cur = con.execute(sql)
    return [d[0] for d in cur.description], cur.fetchall()


def pct(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if not denominator or numerator is None:
        return None
    return round(100.0 * float(numerator) / float(denominator), 2)


def register_views(con: duckdb.DuckDBPyConnection, release_dir: Path, history_dir: Path | None) -> dict:
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    for table in ("facilities", "owners_pecos", "owners_carecompare", "changes_of_ownership", "chains", "state_summary"):
        con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_parquet('{_q(release_dir / (table + '.parquet'))}')")
    has_history = False
    if history_dir and (history_dir / "facilities_history.parquet").exists():
        con.execute(f"CREATE OR REPLACE VIEW facilities_history AS SELECT * FROM read_parquet('{_q(history_dir / 'facilities_history.parquet')}')")
        has_history = True
    if history_dir and (history_dir / "ownership_history.parquet").exists():
        con.execute(f"CREATE OR REPLACE VIEW ownership_history AS SELECT * FROM read_parquet('{_q(history_dir / 'ownership_history.parquet')}')")
    return {"manifest": manifest, "has_history": has_history}


QUALITY_MEASURES = """
    COUNT(*) AS facilities,
    SUM(certified_beds) AS certified_beds,
    ROUND(AVG(overall_rating), 2) AS avg_overall_rating,
    ROUND(100.0 * AVG(CASE WHEN overall_rating <= 2 THEN 1 WHEN overall_rating IS NULL THEN NULL ELSE 0 END), 1) AS pct_rated_1_or_2_stars,
    ROUND(100.0 * AVG(CASE WHEN overall_rating >= 4 THEN 1 WHEN overall_rating IS NULL THEN NULL ELSE 0 END), 1) AS pct_rated_4_or_5_stars,
    ROUND(AVG(staffing_rating), 2) AS avg_staffing_rating,
    ROUND(AVG(reported_total_nurse_hprd), 2) AS avg_reported_total_nurse_hprd,
    ROUND(AVG(reported_rn_hprd), 2) AS avg_reported_rn_hprd,
    ROUND(AVG(total_nurse_turnover_pct), 1) AS avg_total_nurse_turnover_pct,
    ROUND(100.0 * AVG(CASE WHEN COALESCE(total_penalties, 0) > 0 THEN 1 ELSE 0 END), 1) AS pct_with_any_penalty,
    ROUND(AVG(COALESCE(total_fines_dollars, 0)), 0) AS avg_fines_dollars,
    ROUND(100.0 * AVG(CASE WHEN special_focus_status IS NOT NULL THEN 1 ELSE 0 END), 2) AS pct_sff_or_candidate,
    ROUND(100.0 * AVG(CASE WHEN abuse_icon THEN 1 ELSE 0 END), 2) AS pct_abuse_icon,
    ROUND(100.0 * AVG(CASE WHEN ownership_category = 'For profit' THEN 1 ELSE 0 END), 1) AS pct_for_profit,
    ROUND(100.0 * AVG(CASE WHEN chain_id IS NOT NULL THEN 1 ELSE 0 END), 1) AS pct_in_chain
"""

DISCLOSURE_GROUP = """
    CASE
      WHEN has_private_equity_owner THEN 'Discloses a private-equity owner'
      WHEN has_reit_owner THEN 'Discloses a REIT owner'
      WHEN has_private_equity_party OR has_reit_party THEN 'PE or REIT among other disclosable parties only'
      WHEN pecos_enrollment_id IS NULL THEN 'No PECOS enrollment matched'
      ELSE 'No PE or REIT disclosure'
    END
"""


def run_study(release_dir: Path, out_dir: Path, history_dir: Path | None = None, top_n: int = 25) -> dict:
    con = duckdb.connect()
    ctx = register_views(con, release_dir, history_dir)
    manifest = ctx["manifest"]
    release = manifest["release"]
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    def emit(name: str, sql: str) -> list[tuple]:
        columns, rows = _run(con, sql)
        _write_csv(out_dir / f"{name}.csv", columns, rows)
        results[name] = {"rows": len(rows), "columns": columns}
        return rows

    national = emit("national_summary", f"""
        SELECT '{release}' AS release,
               COUNT(*) AS facilities,
               SUM(certified_beds) AS certified_beds,
               SUM(CASE WHEN pecos_enrollment_id IS NOT NULL THEN 1 ELSE 0 END) AS facilities_with_pecos_enrollment,
               SUM(has_private_equity_owner::INT) AS pe_owner_facilities,
               ROUND(100.0 * AVG(has_private_equity_owner::INT), 2) AS pe_owner_pct,
               SUM(CASE WHEN has_private_equity_owner THEN certified_beds ELSE 0 END) AS pe_owner_beds,
               SUM(has_reit_owner::INT) AS reit_owner_facilities,
               ROUND(100.0 * AVG(has_reit_owner::INT), 2) AS reit_owner_pct,
               SUM(has_private_equity_party::INT) AS pe_party_facilities,
               ROUND(100.0 * AVG(has_private_equity_party::INT), 2) AS pe_party_pct,
               SUM(has_reit_party::INT) AS reit_party_facilities,
               ROUND(100.0 * AVG(has_reit_party::INT), 2) AS reit_party_pct,
               SUM(CASE WHEN has_reit_party THEN certified_beds ELSE 0 END) AS reit_party_beds,
               ROUND(100.0 * AVG(CASE WHEN ownership_category = 'For profit' THEN 1 ELSE 0 END), 1) AS for_profit_pct,
               ROUND(100.0 * AVG(CASE WHEN chain_id IS NOT NULL THEN 1 ELSE 0 END), 1) AS chain_pct,
               SUM(CASE WHEN chow_count_36mo >= 1 THEN 1 ELSE 0 END) AS facilities_with_chow_36mo,
               SUM(CASE WHEN chow_count_36mo >= 2 THEN 1 ELSE 0 END) AS facilities_with_2plus_chow_36mo,
               SUM(ownership_changed_12mo::INT) AS facilities_ownership_changed_12mo
        FROM facilities""")

    emit("by_state", """
        SELECT state,
               COUNT(*) AS facilities,
               SUM(certified_beds) AS certified_beds,
               SUM(has_private_equity_owner::INT) AS pe_owner_facilities,
               ROUND(100.0 * AVG(has_private_equity_owner::INT), 2) AS pe_owner_pct,
               SUM(has_reit_owner::INT) AS reit_owner_facilities,
               SUM(has_private_equity_party::INT) AS pe_party_facilities,
               SUM(has_reit_party::INT) AS reit_party_facilities,
               ROUND(100.0 * AVG(has_reit_party::INT), 2) AS reit_party_pct,
               ROUND(100.0 * AVG(CASE WHEN ownership_category = 'For profit' THEN 1 ELSE 0 END), 1) AS for_profit_pct,
               ROUND(100.0 * AVG(CASE WHEN chain_id IS NOT NULL THEN 1 ELSE 0 END), 1) AS chain_pct,
               SUM(CASE WHEN chow_count_36mo >= 1 THEN 1 ELSE 0 END) AS facilities_with_chow_36mo,
               ROUND(100.0 * AVG(CASE WHEN chow_count_36mo >= 1 THEN 1 ELSE 0 END), 1) AS pct_with_chow_36mo,
               ROUND(AVG(overall_rating), 2) AS avg_overall_rating,
               ROUND(AVG(CASE WHEN has_private_equity_owner THEN overall_rating END), 2) AS avg_overall_rating_pe_owner,
               ROUND(AVG(CASE WHEN NOT has_private_equity_owner THEN overall_rating END), 2) AS avg_overall_rating_others
        FROM facilities GROUP BY state ORDER BY state""")

    emit("owner_vs_party", """
        SELECT 'Private equity' AS flag,
               SUM(has_private_equity_owner::INT) AS owner_role_facilities,
               SUM((has_private_equity_party AND NOT has_private_equity_owner)::INT) AS party_only_facilities,
               SUM(has_private_equity_party::INT) AS any_role_facilities,
               ROUND(100.0 * AVG(has_private_equity_owner::INT), 2) AS owner_role_pct,
               ROUND(100.0 * AVG(has_private_equity_party::INT), 2) AS any_role_pct
        FROM facilities
        UNION ALL
        SELECT 'REIT',
               SUM(has_reit_owner::INT), SUM((has_reit_party AND NOT has_reit_owner)::INT), SUM(has_reit_party::INT),
               ROUND(100.0 * AVG(has_reit_owner::INT), 2), ROUND(100.0 * AVG(has_reit_party::INT), 2)
        FROM facilities""")

    emit("quality_by_disclosure", f"""
        SELECT {DISCLOSURE_GROUP} AS disclosure_group, {QUALITY_MEASURES}
        FROM facilities GROUP BY 1 ORDER BY facilities DESC""")

    emit("quality_by_disclosure_for_profit", f"""
        SELECT {DISCLOSURE_GROUP} AS disclosure_group, {QUALITY_MEASURES}
        FROM facilities WHERE ownership_category = 'For profit' GROUP BY 1 ORDER BY facilities DESC""")

    emit("top_private_equity_owners", f"""
        SELECT COALESCE(NULLIF(trim(owner_organization_name), ''), NULLIF(trim(owner_dba_name), ''), NULLIF(trim(concat_ws(' ', owner_first_name, owner_last_name)), ''), 'Name not published in the CMS file') AS owner,
               COUNT(DISTINCT ccn) AS facilities,
               COUNT(DISTINCT f.state) AS states,
               string_agg(DISTINCT f.state, ' ' ORDER BY f.state) AS state_list,
               ROUND(AVG(f.overall_rating), 2) AS avg_overall_rating,
               string_agg(DISTINCT p.role_text, '; ') AS roles
        FROM owners_pecos p JOIN facilities f USING (ccn)
        WHERE p.is_private_equity_company AND p.is_owner_role
        GROUP BY 1 ORDER BY facilities DESC, owner LIMIT {top_n}""")

    emit("top_reit_parties", f"""
        SELECT COALESCE(NULLIF(trim(owner_organization_name), ''), NULLIF(trim(owner_dba_name), ''), NULLIF(trim(concat_ws(' ', owner_first_name, owner_last_name)), ''), 'Name not published in the CMS file') AS organization,
               COUNT(DISTINCT ccn) AS facilities,
               COUNT(DISTINCT f.state) AS states,
               SUM(CASE WHEN p.is_owner_role THEN 1 ELSE 0 END) AS owner_role_rows,
               SUM(CASE WHEN NOT p.is_owner_role THEN 1 ELSE 0 END) AS other_party_rows,
               string_agg(DISTINCT p.role_text, '; ') AS roles
        FROM owners_pecos p JOIN facilities f USING (ccn)
        WHERE p.is_reit
        GROUP BY 1 ORDER BY facilities DESC, organization LIMIT {top_n}""")

    emit("chains_with_disclosures", f"""
        SELECT c.chain_id, c.chain_name, c.facility_count AS chain_facilities_cms, c.state_count, c.avg_overall_rating, c.avg_staffing_rating,
               c.sff_count, c.sff_candidate_count, c.abuse_icon_count, c.total_fines_dollars,
               COUNT(f.ccn) AS facilities_in_release,
               SUM(f.has_private_equity_owner::INT) AS pe_owner_facilities,
               SUM(f.has_reit_owner::INT) AS reit_owner_facilities,
               SUM(f.has_reit_party::INT) AS reit_party_facilities,
               SUM(CASE WHEN f.chow_count_36mo >= 1 THEN 1 ELSE 0 END) AS facilities_with_chow_36mo
        FROM chains c LEFT JOIN facilities f ON f.chain_id = c.chain_id
        GROUP BY ALL ORDER BY c.facility_count DESC LIMIT {top_n * 2}""")

    emit("chow_by_year", """
        SELECT year(effective_date) AS year, chow_type_text, COUNT(*) AS changes_of_ownership,
               COUNT(DISTINCT buyer_ccn) AS facilities
        FROM changes_of_ownership WHERE effective_date IS NOT NULL
        GROUP BY 1, 2 ORDER BY 1, 2""")

    emit("chow_by_state", """
        SELECT s.state, s.facility_count, s.chow_count_12mo,
               ROUND(100.0 * s.chow_count_12mo / NULLIF(s.facility_count, 0), 2) AS chow_12mo_per_100_facilities,
               f.facilities_with_chow_36mo
        FROM state_summary s
        LEFT JOIN (SELECT state, SUM(CASE WHEN chow_count_36mo >= 1 THEN 1 ELSE 0 END) AS facilities_with_chow_36mo FROM facilities GROUP BY state) f USING (state)
        WHERE s.state <> 'US' ORDER BY chow_12mo_per_100_facilities DESC NULLS LAST""")

    decomposition_rows: list[tuple] = []
    if ctx["has_history"]:
        emit("ownership_change_trend", """
            SELECT snapshot_date, processing_date AS cms_vintage, COUNT(*) AS facilities,
                   SUM(ownership_changed_12mo::INT) AS facilities_ownership_changed_12mo,
                   ROUND(100.0 * AVG(ownership_changed_12mo::INT), 2) AS pct_ownership_changed_12mo
            FROM facilities_history GROUP BY 1, 2 ORDER BY 1""")
        try:
            # A name is "first seen" at a facility the first time it appears in any
            # comparable role family, so a relabelled role is not a new relationship
            # and the 2026-only categories are left out of the comparison.
            emit("carecompare_owner_turnover", f"""
                WITH bounds AS (SELECT MIN(first_seen_snapshot) AS first_snapshot, MAX(last_seen_snapshot) AS last_snapshot FROM ownership_history),
                names AS (
                    SELECT ccn, owner_name, owner_type, MIN(first_seen_snapshot) AS first_seen
                    FROM ownership_history WHERE {COMPARABLE_ROLE_SQL}
                    GROUP BY 1, 2, 3)
                SELECT year(first_seen) AS year,
                       COUNT(*) AS owner_names_first_seen,
                       SUM(CASE WHEN owner_type = 'Organization' THEN 1 ELSE 0 END) AS organizations,
                       SUM(CASE WHEN owner_type = 'Individual' THEN 1 ELSE 0 END) AS individuals,
                       COUNT(DISTINCT ccn) AS facilities_with_a_new_name,
                       CASE WHEN year(first_seen) = year(MAX(last_snapshot)) THEN 'partial year' ELSE '' END AS note
                FROM names, bounds
                WHERE first_seen > first_snapshot
                GROUP BY 1 ORDER BY 1""")
            emit("carecompare_owner_turnover_by_family", f"""
                WITH bounds AS (SELECT MIN(first_seen_snapshot) AS first_snapshot FROM ownership_history),
                rows AS (SELECT ccn, owner_name, first_seen_snapshot, {ROLE_FAMILY_SQL} AS role_family FROM ownership_history WHERE {COMPARABLE_ROLE_SQL}),
                names AS (SELECT ccn, owner_name, MIN(first_seen_snapshot) AS first_seen FROM rows GROUP BY 1, 2),
                first_rows AS (
                    SELECT DISTINCT n.ccn, n.owner_name, n.first_seen, r.role_family
                    FROM names n JOIN rows r ON r.ccn = n.ccn AND r.owner_name = n.owner_name AND r.first_seen_snapshot = n.first_seen)
                SELECT year(first_seen) AS year, role_family, COUNT(*) AS owner_names_first_seen
                FROM first_rows, bounds WHERE first_seen > first_snapshot
                GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
            # The raw count keyed on the printed label, accounted for row by row, so a
            # reader can see exactly why 2024 and 2026 look like waves of new owners.
            decomposition_rows = emit("carecompare_first_seen_decomposition", f"""
                WITH bounds AS (SELECT MIN(first_seen_snapshot) AS first_snapshot FROM ownership_history),
                rows AS (SELECT ccn, owner_name, first_seen_snapshot, {ROLE_FAMILY_SQL} AS role_family, {COMPARABLE_ROLE_SQL} AS comparable FROM ownership_history),
                fam AS (SELECT ccn, owner_name, role_family, MIN(first_seen_snapshot) AS family_first FROM rows GROUP BY 1, 2, 3),
                nm AS (SELECT ccn, owner_name, MIN(first_seen_snapshot) AS name_first FROM rows WHERE comparable GROUP BY 1, 2),
                classified AS (
                    SELECT r.*, r.first_seen_snapshot > f.family_first AS prior_same_family,
                           r.first_seen_snapshot > COALESCE(n.name_first, r.first_seen_snapshot) AS prior_any_comparable
                    FROM rows r JOIN fam f USING (ccn, owner_name, role_family) LEFT JOIN nm n USING (ccn, owner_name), bounds
                    WHERE r.first_seen_snapshot > bounds.first_snapshot)
                SELECT year(first_seen_snapshot) AS year,
                       CASE WHEN NOT comparable AND prior_any_comparable THEN 'Category added by the 2023 disclosure rule, name already listed at the facility'
                            WHEN NOT comparable THEN 'Category added by the 2023 disclosure rule, new name'
                            WHEN prior_same_family THEN 'Same name and role family, new CMS label'
                            WHEN prior_any_comparable THEN 'Name already listed at the facility, additional role family'
                            ELSE 'New name at the facility' END AS component,
                       COUNT(*) AS relationships,
                       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY year(first_seen_snapshot)), 1) AS share_of_year_pct
                FROM classified GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
            emit("carecompare_role_labels", f"""
                SELECT role AS cms_role_label, {ROLE_FAMILY_SQL} AS role_family,
                       {COMPARABLE_ROLE_SQL} AS comparable_since_2019,
                       MIN(first_seen_snapshot) AS first_vintage, MAX(last_seen_snapshot) AS last_vintage,
                       COUNT(*) AS relationships
                FROM ownership_history GROUP BY 1 ORDER BY first_vintage, relationships DESC""")
        except duckdb.Error as exc:  # the view is optional
            results["carecompare_owner_turnover"] = {"error": str(exc)[:200]}

    discrepancies = emit("discrepancy_register", """
        SELECT 'No PECOS enrollment matched to the CCN' AS issue, ccn, provider_name, state, NULL AS detail
        FROM facilities WHERE pecos_enrollment_id IS NULL
        UNION ALL
        SELECT 'PE or REIT owner disclosed in PECOS, Care Compare lists individuals only', f.ccn, f.provider_name, f.state,
               concat_ws(' | ', f.private_equity_owner_names, f.reit_owner_names)
        FROM facilities f
        WHERE (f.has_private_equity_owner OR f.has_reit_owner)
          AND NOT EXISTS (SELECT 1 FROM owners_carecompare o WHERE o.ccn = f.ccn AND o.owner_type = 'Organization')
        UNION ALL
        SELECT 'Chain id in Provider Information missing from the chain file', f.ccn, f.provider_name, f.state, f.chain_id
        FROM facilities f LEFT JOIN chains c ON c.chain_id = f.chain_id
        WHERE f.chain_id IS NOT NULL AND c.chain_id IS NULL
        UNION ALL
        SELECT 'Ownership changed in the last 12 months per Care Compare, no PECOS change of ownership in 36 months', f.ccn, f.provider_name, f.state, f.last_chow_date::VARCHAR
        FROM facilities f WHERE f.ownership_changed_12mo AND COALESCE(f.chow_count_36mo, 0) = 0
        ORDER BY 1, 4, 2""")

    site = write_chain_profiles(con, out_dir / "site", manifest)
    results["site/chains"] = {"rows": site["chains"], "columns": ["index.json", "<chain_id>.json"]}
    summary = _summary(release, manifest, national[0] if national else None, con, discrepancies, ctx["has_history"], decomposition_rows)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    meta = {"release": release, "built_at": datetime.now(timezone.utc).isoformat(), "builder": {"name": "tcr-open-data", "version": __version__},
            "processing_date": manifest.get("processing_date"), "doi": manifest.get("doi"), "history_store": ctx["has_history"], "tables": results}
    (out_dir / "study.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    con.close()
    return meta


def _summary(release: str, manifest: dict, national: tuple | None, con: duckdb.DuckDBPyConnection, discrepancies: list[tuple], has_history: bool,
             decomposition: list[tuple] | None = None) -> str:
    n = dict(zip([
        "release", "facilities", "certified_beds", "facilities_with_pecos_enrollment", "pe_owner_facilities", "pe_owner_pct", "pe_owner_beds",
        "reit_owner_facilities", "reit_owner_pct", "pe_party_facilities", "pe_party_pct", "reit_party_facilities", "reit_party_pct", "reit_party_beds",
        "for_profit_pct", "chain_pct", "facilities_with_chow_36mo", "facilities_with_2plus_chow_36mo", "facilities_ownership_changed_12mo"], national or []))
    groups = _run(con, f"SELECT {DISCLOSURE_GROUP} AS g, COUNT(*), ROUND(AVG(overall_rating), 2), ROUND(100.0 * AVG(CASE WHEN COALESCE(total_penalties,0) > 0 THEN 1 ELSE 0 END), 1), ROUND(AVG(reported_total_nurse_hprd), 2) FROM facilities GROUP BY 1 ORDER BY 2 DESC")[1]
    top_pe = _run(con, "SELECT COALESCE(NULLIF(trim(owner_organization_name), ''), NULLIF(trim(owner_dba_name), ''), NULLIF(trim(concat_ws(' ', owner_first_name, owner_last_name)), ''), 'Name not published in the CMS file') o, COUNT(DISTINCT ccn) n FROM owners_pecos WHERE is_private_equity_company AND is_owner_role GROUP BY 1 ORDER BY n DESC LIMIT 5")[1]
    top_reit = _run(con, "SELECT COALESCE(NULLIF(trim(owner_organization_name), ''), NULLIF(trim(owner_dba_name), ''), NULLIF(trim(concat_ws(' ', owner_first_name, owner_last_name)), ''), 'Name not published in the CMS file') o, COUNT(DISTINCT ccn) n FROM owners_pecos WHERE is_reit GROUP BY 1 ORDER BY n DESC LIMIT 5")[1]
    chow_years = _run(con, "SELECT year(effective_date), COUNT(*) FROM changes_of_ownership WHERE effective_date IS NOT NULL GROUP BY 1 ORDER BY 1")[1]
    top_states = _run(con, "SELECT state, SUM(has_private_equity_owner::INT) n, ROUND(100.0*AVG(has_private_equity_owner::INT),1) p FROM facilities GROUP BY 1 HAVING n > 0 ORDER BY n DESC LIMIT 8")[1]
    issue_counts: dict[str, int] = {}
    for row in discrepancies:
        issue_counts[row[0]] = issue_counts.get(row[0], 0) + 1
    vintage = manifest.get("processing_date", "")
    lines = [
        f"# Ownership study tables, release {release}",
        "",
        f"Computed from release {release} (CMS Provider Information vintage {vintage}; PECOS files as recorded in the release manifest). "
        "All ownership figures are **as disclosed to CMS** on Form CMS-855A. A facility without a private-equity or REIT flag has not reported one; "
        "that is not a finding that it has none. Quality and enforcement comparisons are descriptive: they do not control for case mix, size, region or the "
        "reasons a facility changes hands.",
        "",
        "## Headline numbers",
        "",
        f"- Facilities: {n.get('facilities'):,} with {n.get('certified_beds'):,} certified beds; {n.get('facilities_with_pecos_enrollment'):,} matched to a PECOS enrollment.",
        f"- Disclose a **private-equity owner** (ownership or control roles): {n.get('pe_owner_facilities'):,} facilities ({n.get('pe_owner_pct')}%), {n.get('pe_owner_beds'):,} beds.",
        f"- Disclose a **REIT owner**: {n.get('reit_owner_facilities'):,} facilities ({n.get('reit_owner_pct')}%).",
        f"- Counting every disclosable party (landlords, lenders, vendors): private equity appears for {n.get('pe_party_facilities'):,} facilities ({n.get('pe_party_pct')}%) and a REIT for {n.get('reit_party_facilities'):,} ({n.get('reit_party_pct')}%, {n.get('reit_party_beds'):,} beds). Most REIT disclosures are landlords, not operators.",
        f"- For-profit: {n.get('for_profit_pct')}% of facilities; in a CMS-identified chain: {n.get('chain_pct')}%.",
        f"- Changes of ownership: {n.get('facilities_with_chow_36mo'):,} facilities changed hands in the 36 months before the vintage ({n.get('facilities_with_2plus_chow_36mo'):,} more than once); Care Compare flags {n.get('facilities_ownership_changed_12mo'):,} as changed in the last 12 months.",
        "",
        "## Quality and enforcement by disclosure group (descriptive)",
        "",
        "| Group | Facilities | Avg overall rating | % with any penalty | Avg reported nurse hours/resident/day |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for g, count, rating, pen, hprd in groups:
        lines.append(f"| {g} | {count:,} | {rating} | {pen} | {hprd} |")
    lines += ["", "## Most-disclosed private-equity owners (ownership or control roles)", "", "CMS leaves the organization name blank on some rows; those are grouped as *Name not published in the CMS file* and are listed in the register by associate id.", ""]
    lines += [f"- {o}: {c} facilities" for o, c in top_pe] or ["- none"]
    lines += ["", "## Most-disclosed REITs (any role, mostly landlords)", ""]
    lines += [f"- {o}: {c} facilities" for o, c in top_reit] or ["- none"]
    lines += ["", "## States with the most facilities disclosing a private-equity owner", ""]
    lines += [f"- {s}: {c} ({p}% of the state's facilities)" for s, c, p in top_states] or ["- none"]
    lines += ["", "## Changes of ownership by effective year (PECOS)", "", "| Year | Changes |", "| --- | ---: |"]
    lines += [f"| {y} | {c:,} |" for y, c in chow_years]
    lines += ["", "## Discrepancy register seeds", ""]
    lines += [f"- {issue}: {count:,} facilities" for issue, count in sorted(issue_counts.items())] or ["- none"]
    if has_history:
        lines += [
            "",
            "## History store tables",
            "",
            "`ownership_change_trend.csv` is the monthly share of facilities Care Compare flags as changed in the last 12 months, since 2019. "
            "`carecompare_owner_turnover.csv` counts owner names first seen at a facility per year. Care Compare renamed its role labels in the "
            "2024-12, 2025-06 and 2026-05 vintages (for example DIRECTOR became CORPORATE DIRECTOR, MANAGING EMPLOYEE split into W-2 and "
            "CONTRACTED) and the 2026 disclosure rule added categories such as additional disclosable parties, trustees and governing-body members. "
            "The turnover table therefore works on role families and only on families that have existed since 2019; a name first appearing "
            "under a new label is not a new relationship, and the 2026-only categories are excluded. `carecompare_role_labels.csv` lists every "
            "label, its family and the vintages it appears in. The latest year is partial.",
            "",
            "Even on that basis the series breaks in 2025: names first seen jump in the 2025-11 and 2026-02 vintages, almost all of them in the "
            "operational/managerial control family (`carecompare_owner_turnover_by_family.csv`). That is the arrival of the fuller disclosures "
            "required by the 2023 SNF ownership rule on the revised Form CMS-855A, not a wave of facilities changing hands, so counts before "
            "and after 2025 are not comparable and no report should describe the rise as turnover. The PECOS change-of-ownership file "
            "(`chow_by_year.csv`) is the measure of facilities changing hands.",
        ]
        decomposition = [row for row in (decomposition or []) if int(row[0]) >= 2024]
        if decomposition:
            lines += ["", "### Where the raw counts come from", "",
                      "Counted on the label CMS printed, the relationships first seen per year look like this (`carecompare_first_seen_decomposition.csv`). "
                      "Only *New name at the facility* is a candidate for a new owner relationship, and even that row carries the 2025 disclosure wave.", "",
                      "| Year | Component | Relationships | Share of year |", "| --- | --- | ---: | ---: |"]
            lines += [f"| {y} | {c} | {int(r):,} | {s}% |" for y, c, r, s in decomposition]
    lines += ["", "## Files", "", "Every table in this directory is a CSV named for its content; `study.json` records the release, DOI and row counts. Reproduce with `tcr-open-data ownership-study --release releases/" + release + " --history history --out analysis/ownership/" + release + "`.", ""]
    return "\n".join(lines)
