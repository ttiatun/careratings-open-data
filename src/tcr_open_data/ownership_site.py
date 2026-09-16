"""
Site files for the ownership study pages (/data/ownership/): one JSON with
the headline tables and the state layers for the map, and one with the
discrepancy register. Written under `<study>/site/` by `run_study` and
published with `tcr-open-data publish-analysis`.

Every number is a release column or a count of release rows; the framing
is "as disclosed to CMS". States with fewer than SMALL_STATE facilities
are kept in the tables but flagged `suppressed` so the map leaves them
blank, as the editorial standards require.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

from . import __version__

SMALL_STATE = 10

# The register issues, in the order the page lists them. `description` is
# what the site prints; keep it a statement of a file disagreement, never an
# accusation (editorial standards, section 4).
DISCREPANCY_ISSUES: list[dict[str, str]] = [
    {
        "issue": "No PECOS enrollment matched to the CCN",
        "description": "The facility is certified in Care Compare but no Skilled Nursing Facility enrollment in the PECOS files carries its CCN, so none of its ownership disclosures can be read.",
    },
    {
        "issue": "PECOS enrollment lists no ownership-interest party",
        "description": "The facility's current PECOS enrollment names officers, directors, managing employees or other parties, but no direct, indirect or partnership ownership interest (role codes 34, 35, 38, 39, 85, 86). Non-profit and government facilities have no equity owners to list, so most of these rows are expected; the check matters for for-profit facilities.",
    },
    {
        "issue": "Ownership-interest owners disclosed without any ownership percentage",
        "description": "Every ownership-interest row on the facility's current enrollment leaves the percentage blank, so the share each owner holds cannot be read from the file.",
    },
    {
        "issue": "PE or REIT owner disclosed in PECOS, Care Compare lists individuals only",
        "description": "PECOS flags a private-equity company or a REIT in an ownership or control role, while the Care Compare ownership file for the same facility lists only individuals.",
    },
    {
        "issue": "Chain id in Provider Information missing from the chain file",
        "description": "Provider Information carries a chain id that does not appear in the CMS Chain Performance Measures file of the same release.",
    },
    {
        "issue": "Ownership changed in the last 12 months per Care Compare, no PECOS change of ownership in 36 months",
        "description": "Care Compare flags an ownership change in the last twelve months, but the PECOS Change of Ownership file has no record for the facility in the 36 months before the vintage.",
    },
]

STATE_LAYERS_SQL = """
    SELECT state,
           COUNT(*) AS facilities,
           SUM(certified_beds) AS certified_beds,
           ROUND(100.0 * AVG(CASE WHEN ownership_category = 'For profit' THEN 1 ELSE 0 END), 1) AS for_profit_pct,
           ROUND(100.0 * AVG(CASE WHEN chain_id IS NOT NULL THEN 1 ELSE 0 END), 1) AS chain_pct,
           SUM(has_private_equity_owner::INT) AS pe_owner_facilities,
           ROUND(100.0 * AVG(has_private_equity_owner::INT), 2) AS pe_owner_pct,
           SUM(has_reit_owner::INT) AS reit_owner_facilities,
           SUM(CASE WHEN has_reit_owner OR has_reit_party THEN 1 ELSE 0 END) AS reit_any_facilities,
           ROUND(100.0 * AVG(CASE WHEN has_reit_owner OR has_reit_party THEN 1 ELSE 0 END), 2) AS reit_any_pct,
           SUM(CASE WHEN COALESCE(chow_count_36mo, 0) >= 1 THEN 1 ELSE 0 END) AS facilities_with_chow_36mo,
           ROUND(100.0 * AVG(CASE WHEN COALESCE(chow_count_36mo, 0) >= 1 THEN 1 ELSE 0 END), 1) AS chow_36mo_pct,
           SUM(ownership_changed_12mo::INT) AS facilities_ownership_changed_12mo,
           ROUND(100.0 * AVG(ownership_changed_12mo::INT), 2) AS ownership_changed_12mo_pct,
           SUM(CASE WHEN pecos_enrollment_id IS NULL THEN 1 ELSE 0 END) AS facilities_without_pecos,
           ROUND(100.0 * AVG(CASE WHEN pecos_enrollment_id IS NULL THEN 1 ELSE 0 END), 1) AS without_pecos_pct,
           ROUND(AVG(overall_rating), 2) AS avg_overall_rating,
           SUM(CASE WHEN special_focus_status IS NOT NULL THEN 1 ELSE 0 END) AS sff_or_candidate,
           SUM(abuse_icon::INT) AS abuse_icon_facilities
    FROM facilities GROUP BY state ORDER BY state"""


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        return None if value != value else value
    return value


def _records(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    columns = [d[0] for d in cur.description]
    return [{c: _jsonable(v) for c, v in zip(columns, row)} for row in cur.fetchall()]


def _csv_records(path: Path) -> list[dict]:
    import csv

    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _numeric(rows: list[dict]) -> list[dict]:
    """CSV values back to numbers where they parse, so the JSON carries numbers."""
    out = []
    for row in rows:
        fixed = {}
        for key, value in row.items():
            if value is None or value == "":
                fixed[key] = None
                continue
            try:
                fixed[key] = int(value) if value.lstrip("-").isdigit() else float(value)
            except ValueError:
                fixed[key] = value
        out.append(fixed)
    return out


def _category_counts(discrepancies: list[tuple]) -> list[dict]:
    """Rows per (issue, ownership category), so a page can say how many of a check's rows are non-profit or government homes."""
    counts: dict[tuple[str, str], int] = {}
    for row in discrepancies:
        key = (row[0], row[4] if len(row) > 4 and row[4] else "Unknown")
        counts[key] = counts.get(key, 0) + 1
    return [{"issue": issue, "ownership_category": category, "facilities": n} for (issue, category), n in sorted(counts.items())]


STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "GU": "Guam", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "VI": "Virgin Islands", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


def _rank(states: list[dict], key: str, state: str) -> str:
    ranked = sorted((s for s in states if not s.get("suppressed") and s.get(key) is not None), key=lambda s: (-(s[key] or 0), s["state"]))
    for i, s in enumerate(ranked, 1):
        if s["state"] == state:
            return f"{i} of {len(ranked)}"
    return "not ranked"


def write_state_cuts(states: list[dict], national: dict | None, out_dir: Path, release: str, processing_date: str | None) -> Path:
    """One section per state with its figures and its rank among the states with at least SMALL_STATE facilities, for state press."""
    out_dir.mkdir(parents=True, exist_ok=True)
    n = national or {}
    lines = [
        f"# State cuts: nursing home ownership as disclosed to CMS, release {release}",
        "",
        f"One section per state from the ownership study (CMS Provider Information vintage {processing_date}; PECOS files as recorded in the release manifest). "
        "Every figure is a column of `by_state.csv` or the state layers in `site/ownership.json`; ranks are among states with at least "
        f"{SMALL_STATE} certified nursing homes, highest share first. Ownership figures are as disclosed on Form CMS-855A: a facility that discloses no "
        "private-equity or REIT owner has not reported one, which is not a finding that it has none. Comparisons are descriptive.",
        "",
        "National: "
        + (f"{n.get('facilities'):,} facilities; {n.get('pe_owner_facilities'):,} ({n.get('pe_owner_pct')}%) disclose a private-equity owner; "
           f"{n.get('reit_party_facilities'):,} ({n.get('reit_party_pct')}%) disclose a REIT in any role; {n.get('for_profit_pct')}% for-profit; "
           f"{n.get('chain_pct')}% in a CMS-identified chain; {n.get('facilities_with_chow_36mo'):,} changed hands in 36 months." if n else "see national_summary.csv"),
        "",
    ]
    for s in sorted(states, key=lambda r: STATE_NAMES.get(r["state"], r["state"])):
        name = STATE_NAMES.get(s["state"], s["state"])
        lines.append(f"## {name} ({s['state']})")
        lines.append("")
        if s.get("suppressed"):
            lines.append(f"{s['facilities']} certified nursing home(s): fewer than {SMALL_STATE}, so shares are not ranked or mapped.")
            lines.append("")
            continue
        lines += [
            f"- Certified nursing homes: {s['facilities']:,} ({(s.get('certified_beds') or 0):,} certified beds); average overall rating {s.get('avg_overall_rating')}.",
            f"- Disclose a private-equity owner: {s['pe_owner_facilities']} ({s.get('pe_owner_pct')}%), rank {_rank(states, 'pe_owner_pct', s['state'])}.",
            f"- Disclose a REIT in any role: {s['reit_any_facilities']} ({s.get('reit_any_pct')}%), rank {_rank(states, 'reit_any_pct', s['state'])}; as an owner: {s['reit_owner_facilities']}.",
            f"- For-profit: {s.get('for_profit_pct')}% (rank {_rank(states, 'for_profit_pct', s['state'])}); in a CMS-identified chain: {s.get('chain_pct')}% (rank {_rank(states, 'chain_pct', s['state'])}).",
            f"- Changed hands in the 36 months before the vintage (PECOS): {s['facilities_with_chow_36mo']} ({s.get('chow_36mo_pct')}%), rank {_rank(states, 'chow_36mo_pct', s['state'])}; Care Compare 12-month change flag: {s['facilities_ownership_changed_12mo']}.",
            f"- No PECOS enrollment matched (disclosures unreadable): {s['facilities_without_pecos']} ({s.get('without_pecos_pct')}%).",
            f"- Special Focus Facilities or candidates: {s['sff_or_candidate']}; abuse icons: {s['abuse_icon_facilities']}.",
            "",
        ]
    path = out_dir / "state_cuts.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_ownership_site(con: duckdb.DuckDBPyConnection, out_dir: Path, tables_dir: Path, manifest: dict, discrepancies: list[tuple]) -> dict:
    """Write `<out_dir>/ownership.json` and `<out_dir>/discrepancy_register.json` from the study tables and the release views."""
    out_dir.mkdir(parents=True, exist_ok=True)
    header = {
        "release": manifest["release"],
        "processing_date": manifest.get("processing_date"),
        "doi": manifest.get("doi"),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "builder": {"name": "tcr-open-data", "version": __version__},
        "sources": manifest.get("sources", {}),
    }

    states = _records(con, STATE_LAYERS_SQL)
    for row in states:
        row["suppressed"] = (row.get("facilities") or 0) < SMALL_STATE
    national_rows = _numeric(_csv_records(tables_dir / "national_summary.csv"))
    issue_counts: dict[str, int] = {}
    for row in discrepancies:
        issue_counts[row[0]] = issue_counts.get(row[0], 0) + 1

    ownership = {
        **header,
        "small_state_threshold": SMALL_STATE,
        "national": national_rows[0] if national_rows else None,
        "owner_vs_party": _numeric(_csv_records(tables_dir / "owner_vs_party.csv")),
        "quality_by_disclosure": _numeric(_csv_records(tables_dir / "quality_by_disclosure.csv")),
        "quality_by_disclosure_for_profit": _numeric(_csv_records(tables_dir / "quality_by_disclosure_for_profit.csv")),
        "top_private_equity_owners": _numeric(_csv_records(tables_dir / "top_private_equity_owners.csv")),
        "top_reit_parties": _numeric(_csv_records(tables_dir / "top_reit_parties.csv")),
        "chow_by_year": _numeric(_csv_records(tables_dir / "chow_by_year.csv")),
        "ownership_change_trend": _numeric(_csv_records(tables_dir / "ownership_change_trend.csv")),
        "chains_with_disclosures": _numeric(_csv_records(tables_dir / "chains_with_disclosures.csv")),
        "carecompare_owner_turnover": _numeric(_csv_records(tables_dir / "carecompare_owner_turnover.csv")),
        "carecompare_first_seen_decomposition": [r for r in _numeric(_csv_records(tables_dir / "carecompare_first_seen_decomposition.csv")) if (r.get("year") or 0) >= 2023],
        "states": states,
        "discrepancy_counts": [{"issue": i["issue"], "description": i["description"], "facilities": issue_counts.get(i["issue"], 0)} for i in DISCREPANCY_ISSUES],
        "discrepancy_by_category": _category_counts(discrepancies),
    }
    (out_dir / "ownership.json").write_text(json.dumps(ownership, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_state_cuts(states, ownership["national"], tables_dir / "press", manifest["release"], manifest.get("processing_date"))

    known = {i["issue"] for i in DISCREPANCY_ISSUES}
    register = {
        **header,
        "issues": [{"issue": i["issue"], "description": i["description"], "facilities": issue_counts.get(i["issue"], 0)} for i in DISCREPANCY_ISSUES]
        + [{"issue": issue, "description": "", "facilities": count} for issue, count in sorted(issue_counts.items()) if issue not in known],
        "rows": [{"issue": r[0], "ccn": r[1], "provider_name": r[2], "state": r[3], "ownership_category": r[4], "chain_name": r[5], "detail": _jsonable(r[6])} for r in discrepancies],
    }
    (out_dir / "discrepancy_register.json").write_text(json.dumps(register, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"states": len(states), "register_rows": len(register["rows"]), "issues": len(register["issues"])}
