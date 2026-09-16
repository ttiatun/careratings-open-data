"""
Chain profile files for the site: one JSON per CMS-identified chain and an index.

Chain identity is CMS's. The Nursing Home Chain Performance Measures file
names each affiliated entity and its facility count, and the Provider
Information file carries the same chain id on every facility. A profile
combines the chain file's averages with the facilities in the release that
carry that chain id, their disclosures on Form CMS-855A (PECOS) and their
changes of ownership. Everything is "as disclosed to CMS"; the files never
claim that a chain has an owner it did not report.

Written under `<study>/site/chains/` by `run_study` and published with
`tcr-open-data publish-analysis`. Both files carry the release, the CMS
vintage and the DOI so a page can say exactly what it is built from.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

from . import __version__

OWNER_NAME_SQL = (
    "COALESCE(NULLIF(trim(owner_organization_name), ''), NULLIF(trim(owner_dba_name), ''), "
    "NULLIF(trim(concat_ws(' ', owner_first_name, owner_last_name)), ''), 'Name not published in the CMS file')"
)
NATIONAL_ID = "NATIONAL"
TOP_NAMES = 12

CHAIN_FILE_COLUMNS = [
    "chain_id", "chain_name", "facility_count", "state_count", "sff_count", "sff_candidate_count", "abuse_icon_count", "abuse_icon_pct",
    "pct_for_profit", "pct_non_profit", "pct_government", "avg_overall_rating", "avg_health_inspection_rating", "avg_staffing_rating",
    "avg_qm_rating", "avg_total_nurse_hprd", "avg_weekend_nurse_hprd", "avg_rn_hprd", "avg_nurse_turnover_pct", "avg_rn_turnover_pct",
    "avg_admin_departures", "total_fines", "avg_fines", "total_fines_dollars", "avg_fines_dollars", "total_payment_denials", "avg_payment_denials",
]

FACILITY_COLUMNS = [
    "ccn", "provider_name", "city", "state", "zip_code", "ownership_category", "certified_beds", "overall_rating", "health_inspection_rating",
    "staffing_rating", "qm_rating", "special_focus_status", "abuse_icon", "reported_total_nurse_hprd", "total_nurse_turnover_pct", "num_fines",
    "total_fines_dollars", "num_payment_denials", "has_private_equity_owner", "has_reit_owner", "has_private_equity_party", "has_reit_party",
    "chow_count_36mo", "last_chow_date", "pecos_enrollment_id",
]


def chain_slug(name: str | None, limit: int = 60) -> str:
    """URL slug for a chain name: lowercase words joined by hyphens, at most `limit` characters, never empty."""
    text = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    if len(text) > limit:
        text = text[:limit].rsplit("-", 1)[0] or text[:limit]
    return text or "chain"


def chain_path(chain_id: str, name: str | None) -> str:
    return f"/data/chains/{chain_id}-{chain_slug(name)}/"


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        return None if value != value else value  # NaN → null
    return value


def _records(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    columns = [d[0] for d in cur.description]
    return [{c: _jsonable(v) for c, v in zip(columns, row)} for row in cur.fetchall()]


def _grouped(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(str(row[key]), []).append({k: v for k, v in row.items() if k != key})
    return out


def write_chain_profiles(con: duckdb.DuckDBPyConnection, out_dir: Path, manifest: dict, top_names: int = TOP_NAMES) -> dict:
    """Write `<out_dir>/chains/index.json` and one `<out_dir>/chains/<chain_id>.json` per chain from the registered release views."""
    chains_dir = out_dir / "chains"
    chains_dir.mkdir(parents=True, exist_ok=True)
    release = manifest["release"]
    built_at = datetime.now(timezone.utc).isoformat()
    header = {
        "release": release,
        "processing_date": manifest.get("processing_date"),
        "doi": manifest.get("doi"),
        "built_at": built_at,
        "builder": {"name": "tcr-open-data", "version": __version__},
        "sources": manifest.get("sources", {}),
    }

    chain_rows = _records(con, f"SELECT {', '.join(CHAIN_FILE_COLUMNS)} FROM chains ORDER BY facility_count DESC NULLS LAST, chain_name")
    national = next((r for r in chain_rows if r["chain_id"] == NATIONAL_ID), None)
    chain_rows = [r for r in chain_rows if r["chain_id"] != NATIONAL_ID]

    aggregates = {r["chain_id"]: r for r in _records(con, """
        SELECT chain_id,
               COUNT(*) AS facilities_in_release,
               SUM(certified_beds) AS certified_beds,
               COUNT(DISTINCT state) AS states_in_release,
               SUM(CASE WHEN pecos_enrollment_id IS NOT NULL THEN 1 ELSE 0 END) AS facilities_with_pecos_enrollment,
               SUM(has_private_equity_owner::INT) AS pe_owner_facilities,
               SUM(has_reit_owner::INT) AS reit_owner_facilities,
               SUM(has_private_equity_party::INT) AS pe_party_facilities,
               SUM(has_reit_party::INT) AS reit_party_facilities,
               SUM(CASE WHEN COALESCE(chow_count_36mo, 0) >= 1 THEN 1 ELSE 0 END) AS facilities_with_chow_36mo,
               SUM(ownership_changed_12mo::INT) AS facilities_ownership_changed_12mo,
               COUNT(overall_rating) AS rated_facilities,
               SUM(CASE WHEN overall_rating = 1 THEN 1 ELSE 0 END) AS rating_1,
               SUM(CASE WHEN overall_rating = 2 THEN 1 ELSE 0 END) AS rating_2,
               SUM(CASE WHEN overall_rating = 3 THEN 1 ELSE 0 END) AS rating_3,
               SUM(CASE WHEN overall_rating = 4 THEN 1 ELSE 0 END) AS rating_4,
               SUM(CASE WHEN overall_rating = 5 THEN 1 ELSE 0 END) AS rating_5,
               ROUND(AVG(overall_rating), 2) AS avg_overall_rating,
               ROUND(AVG(staffing_rating), 2) AS avg_staffing_rating,
               SUM(CASE WHEN special_focus_status = 'SFF' THEN 1 ELSE 0 END) AS sff_facilities,
               SUM(CASE WHEN special_focus_status = 'SFF Candidate' THEN 1 ELSE 0 END) AS sff_candidate_facilities,
               SUM(abuse_icon::INT) AS abuse_icon_facilities,
               SUM(COALESCE(num_fines, 0)) AS fines,
               SUM(COALESCE(total_fines_dollars, 0)) AS total_fines_dollars,
               SUM(COALESCE(num_payment_denials, 0)) AS payment_denials,
               SUM(CASE WHEN COALESCE(total_penalties, 0) > 0 THEN 1 ELSE 0 END) AS facilities_with_any_penalty,
               ROUND(AVG(reported_total_nurse_hprd), 2) AS avg_reported_total_nurse_hprd,
               ROUND(AVG(reported_rn_hprd), 2) AS avg_reported_rn_hprd,
               ROUND(AVG(total_nurse_turnover_pct), 1) AS avg_total_nurse_turnover_pct,
               SUM(CASE WHEN ownership_category = 'For profit' THEN 1 ELSE 0 END) AS for_profit_facilities,
               SUM(CASE WHEN ownership_category = 'Non profit' THEN 1 ELSE 0 END) AS non_profit_facilities,
               SUM(CASE WHEN ownership_category = 'Government' THEN 1 ELSE 0 END) AS government_facilities,
               SUM(meets_all_repealed_floors::INT) AS facilities_meeting_all_repealed_floors
        FROM facilities WHERE chain_id IS NOT NULL GROUP BY 1""")}

    states = _grouped(_records(con, """
        SELECT chain_id, state, COUNT(*) AS facilities, ROUND(AVG(overall_rating), 2) AS avg_overall_rating,
               SUM(CASE WHEN special_focus_status IS NOT NULL THEN 1 ELSE 0 END) AS sff_or_candidate,
               SUM(abuse_icon::INT) AS abuse_icon_facilities,
               SUM(has_private_equity_owner::INT) AS pe_owner_facilities,
               SUM(has_reit_owner::INT) AS reit_owner_facilities,
               SUM(has_reit_party::INT) AS reit_party_facilities,
               SUM(CASE WHEN COALESCE(chow_count_36mo, 0) >= 1 THEN 1 ELSE 0 END) AS facilities_with_chow_36mo,
               SUM(COALESCE(total_fines_dollars, 0)) AS total_fines_dollars
        FROM facilities WHERE chain_id IS NOT NULL GROUP BY 1, 2 ORDER BY 1, facilities DESC, state"""), "chain_id")

    facilities = _grouped(_records(con, f"""
        SELECT chain_id, {', '.join(FACILITY_COLUMNS)} FROM facilities WHERE chain_id IS NOT NULL
        ORDER BY chain_id, state, city, provider_name"""), "chain_id")

    names = _grouped(_records(con, f"""
        WITH current AS (
            SELECT o.*, f.chain_id FROM owners_pecos o
            JOIN facilities f ON f.ccn = o.ccn AND f.pecos_enrollment_id = o.enrollment_id
            WHERE f.chain_id IS NOT NULL),
        tagged AS (
            SELECT chain_id, ccn, 'pe_owner' AS kind, {OWNER_NAME_SQL} AS name FROM current WHERE is_private_equity_company AND is_owner_role
            UNION ALL SELECT chain_id, ccn, 'reit_owner', {OWNER_NAME_SQL} FROM current WHERE is_reit AND is_owner_role
            UNION ALL SELECT chain_id, ccn, 'pe_party', {OWNER_NAME_SQL} FROM current WHERE is_private_equity_company AND NOT is_owner_role
            UNION ALL SELECT chain_id, ccn, 'reit_party', {OWNER_NAME_SQL} FROM current WHERE is_reit AND NOT is_owner_role)
        SELECT chain_id, kind, name, COUNT(DISTINCT ccn) AS facilities FROM tagged
        GROUP BY 1, 2, 3 ORDER BY 1, 2, facilities DESC, name"""), "chain_id")

    chow_years = _grouped(_records(con, """
        SELECT f.chain_id, year(c.effective_date) AS year, COUNT(*) AS changes
        FROM changes_of_ownership c JOIN facilities f ON f.ccn = c.buyer_ccn
        WHERE c.effective_date IS NOT NULL AND f.chain_id IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2"""), "chain_id")

    index_entries: list[dict] = []
    written = 0
    for chain in chain_rows:
        chain_id = str(chain["chain_id"])
        agg = aggregates.get(chain_id, {})
        slug = chain_slug(chain["chain_name"])
        path = chain_path(chain_id, chain["chain_name"])
        by_kind: dict[str, list[dict]] = {"pe_owner": [], "reit_owner": [], "pe_party": [], "reit_party": []}
        for row in names.get(chain_id, []):
            by_kind.setdefault(row["kind"], []).append({"name": row["name"], "facilities": row["facilities"]})
        profile = {
            **header,
            "chain": {**chain, "slug": slug, "path": path},
            "national": national,
            "release_totals": agg,
            "ratings": {f"rating_{n}": agg.get(f"rating_{n}") for n in range(1, 6)} | {"rated_facilities": agg.get("rated_facilities")},
            "disclosures": {
                "facilities_with_pecos_enrollment": agg.get("facilities_with_pecos_enrollment"),
                "pe_owner_facilities": agg.get("pe_owner_facilities"),
                "reit_owner_facilities": agg.get("reit_owner_facilities"),
                "pe_party_facilities": agg.get("pe_party_facilities"),
                "reit_party_facilities": agg.get("reit_party_facilities"),
                "pe_owner_names": by_kind["pe_owner"][:top_names],
                "reit_owner_names": by_kind["reit_owner"][:top_names],
                "pe_party_names": by_kind["pe_party"][:top_names],
                "reit_party_names": by_kind["reit_party"][:top_names],
            },
            "changes_of_ownership": {
                "facilities_with_chow_36mo": agg.get("facilities_with_chow_36mo"),
                "facilities_ownership_changed_12mo": agg.get("facilities_ownership_changed_12mo"),
                "by_year": chow_years.get(chain_id, []),
            },
            "states": states.get(chain_id, []),
            "facilities": facilities.get(chain_id, []),
        }
        (chains_dir / f"{chain_id}.json").write_text(json.dumps(profile, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        written += 1
        index_entries.append({
            "chain_id": chain_id,
            "chain_name": chain["chain_name"],
            "slug": slug,
            "path": path,
            "facility_count": chain["facility_count"],
            "facilities_in_release": agg.get("facilities_in_release", 0),
            "state_count": chain["state_count"],
            "states": [s["state"] for s in states.get(chain_id, [])],
            "avg_overall_rating": chain["avg_overall_rating"],
            "avg_staffing_rating": chain["avg_staffing_rating"],
            "pct_for_profit": chain["pct_for_profit"],
            "sff_count": chain["sff_count"],
            "sff_candidate_count": chain["sff_candidate_count"],
            "abuse_icon_count": chain["abuse_icon_count"],
            "total_fines_dollars": chain["total_fines_dollars"],
            "avg_fines_dollars": chain["avg_fines_dollars"],
            "total_payment_denials": chain["total_payment_denials"],
            "facilities_with_pecos_enrollment": agg.get("facilities_with_pecos_enrollment", 0),
            "pe_owner_facilities": agg.get("pe_owner_facilities", 0),
            "reit_owner_facilities": agg.get("reit_owner_facilities", 0),
            "pe_party_facilities": agg.get("pe_party_facilities", 0),
            "reit_party_facilities": agg.get("reit_party_facilities", 0),
            "facilities_with_chow_36mo": agg.get("facilities_with_chow_36mo", 0),
        })

    index = {
        **header,
        "national": national,
        "chains": index_entries,
        "chained_facilities_in_release": sum(e["facilities_in_release"] for e in index_entries),
    }
    (chains_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"chains": written, "index": str(chains_dir / "index.json")}
