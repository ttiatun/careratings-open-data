"""
Staffing-standards study: the descriptive tables behind tracker D3.

    tcr-open-data staffing-study --release releases/v2026.08 [--history history] --out analysis/staffing/v2026.08

The federal minimum staffing rule finalized in 2024 (0.55 registered-nurse,
2.45 nurse-aide and 3.48 total nurse hours per resident day, plus an RN on
site around the clock) was rescinded by an interim final rule effective
February 2, 2026. This study asks the counterfactual the rule left behind:
what share of facilities report hours at or above each numeric floor, by
state and ownership, and how that share has moved since 2019.

It uses the *reported* hours per resident day that CMS publishes on
Provider Information (payroll-based journal data averaged over a quarter),
as KFF did in 2024. It does not test the 24/7 RN requirement, which needs
daily payroll data, and it does not adjust for case mix: a facility below a
floor is not thereby found to be understaffed for its residents.

Outputs (CSV unless noted):
  national_summary       one row: shares at or above each floor, averages
  by_state               per-state shares (states under ten facilities flagged suppressed)
  by_ownership           for-profit, non-profit, government
  by_chain_status        in a CMS-identified chain or not
  by_disclosure_group    the ownership study's PECOS disclosure groups
  by_overall_rating      shares by Care Compare overall star rating
  by_bed_size            shares by certified-bed band
  distance_to_total_floor  how far facilities sit from the 3.48 total-hours floor
  trend_by_snapshot      monthly shares and averages since 2019 (history store)
  trend_by_ownership_year  first snapshot of each year by ownership category (history store)
  state_change           each state's share at or above all three floors, first snapshot versus latest (history store)
  summary.md             the headline numbers in prose, with the caveats
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from . import __version__
from .ownership_study import DISCLOSURE_GROUP, _q, _run, _write_csv
from .study_site import write_state_cuts, write_study_site

RN_FLOOR = 0.55
AIDE_FLOOR = 2.45
TOTAL_FLOOR = 3.48
SMALL_STATE = 10

ALL_THREE = (f"CASE WHEN reported_rn_hprd IS NULL OR reported_aide_hprd IS NULL OR reported_total_nurse_hprd IS NULL THEN NULL "
             f"WHEN reported_rn_hprd >= {RN_FLOOR} AND reported_aide_hprd >= {AIDE_FLOOR} AND reported_total_nurse_hprd >= {TOTAL_FLOOR} THEN 1 ELSE 0 END")


def _meets(column: str, floor: float) -> str:
    return f"CASE WHEN {column} IS NULL THEN NULL WHEN {column} >= {floor} THEN 1 ELSE 0 END"


SHARES = f"""
    COUNT(*) AS facilities,
    COUNT(reported_total_nurse_hprd) AS facilities_with_reported_hours,
    ROUND(100.0 * AVG({_meets('reported_rn_hprd', RN_FLOOR)}), 1) AS pct_at_or_above_rn_floor,
    ROUND(100.0 * AVG({_meets('reported_aide_hprd', AIDE_FLOOR)}), 1) AS pct_at_or_above_aide_floor,
    ROUND(100.0 * AVG({_meets('reported_total_nurse_hprd', TOTAL_FLOOR)}), 1) AS pct_at_or_above_total_floor,
    ROUND(100.0 * AVG({ALL_THREE}), 1) AS pct_at_or_above_all_three,
    SUM({ALL_THREE}) AS facilities_at_or_above_all_three,
    ROUND(AVG(reported_total_nurse_hprd), 2) AS avg_total_nurse_hprd,
    ROUND(AVG(reported_rn_hprd), 2) AS avg_rn_hprd,
    ROUND(AVG(reported_aide_hprd), 2) AS avg_aide_hprd
"""

OWNERSHIP_FROM_TYPE = ("CASE WHEN ownership_type ILIKE 'For profit%' THEN 'For profit' WHEN ownership_type ILIKE 'Non profit%' THEN 'Non profit' "
                       "WHEN ownership_type ILIKE 'Government%' THEN 'Government' ELSE 'Unknown' END")


def register_views(con: duckdb.DuckDBPyConnection, release_dir: Path, history_dir: Path | None) -> dict:
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    con.execute(f"CREATE OR REPLACE VIEW facilities AS SELECT * FROM read_parquet('{_q(release_dir / 'facilities.parquet')}')")
    has_history = False
    if history_dir and (history_dir / "facilities_history.parquet").exists():
        con.execute(f"CREATE OR REPLACE VIEW facilities_history AS SELECT * FROM read_parquet('{_q(history_dir / 'facilities_history.parquet')}')")
        has_history = True
    return {"manifest": manifest, "has_history": has_history}


def run_study(release_dir: Path, out_dir: Path, history_dir: Path | None = None) -> dict:
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

    emit("national_summary", f"""
        SELECT '{release}' AS release, {SHARES},
               ROUND(AVG(reported_lpn_hprd), 2) AS avg_lpn_hprd,
               ROUND(AVG(weekend_total_nurse_hprd), 2) AS avg_weekend_total_nurse_hprd,
               ROUND(AVG(total_nurse_turnover_pct), 1) AS avg_total_nurse_turnover_pct,
               ROUND(AVG(rn_turnover_pct), 1) AS avg_rn_turnover_pct,
               {RN_FLOOR} AS rn_floor, {AIDE_FLOOR} AS aide_floor, {TOTAL_FLOOR} AS total_floor
        FROM facilities""")

    emit("by_state", f"SELECT state, {SHARES}, COUNT(*) < {SMALL_STATE} AS suppressed FROM facilities GROUP BY state ORDER BY state")
    emit("by_ownership", f"SELECT ownership_category, {SHARES} FROM facilities GROUP BY 1 ORDER BY facilities DESC, ownership_category")
    emit("by_chain_status", f"""
        SELECT CASE WHEN chain_id IS NOT NULL THEN 'In a CMS-identified chain' ELSE 'Not in a chain' END AS chain_status, {SHARES}
        FROM facilities GROUP BY 1 ORDER BY facilities DESC""")
    emit("by_disclosure_group", f"SELECT {DISCLOSURE_GROUP} AS disclosure_group, {SHARES} FROM facilities GROUP BY 1 ORDER BY facilities DESC, disclosure_group")
    emit("by_overall_rating", f"SELECT overall_rating, {SHARES} FROM facilities WHERE overall_rating IS NOT NULL GROUP BY 1 ORDER BY 1")
    emit("by_bed_size", f"""
        WITH banded AS (
            SELECT *, CASE WHEN certified_beds < 50 THEN 1 WHEN certified_beds < 100 THEN 2 WHEN certified_beds < 150 THEN 3 WHEN certified_beds < 200 THEN 4 ELSE 5 END AS band_order
            FROM facilities WHERE certified_beds IS NOT NULL)
        SELECT band_order, CASE band_order WHEN 1 THEN 'Under 50 beds' WHEN 2 THEN '50 to 99 beds' WHEN 3 THEN '100 to 149 beds' WHEN 4 THEN '150 to 199 beds' ELSE '200 beds or more' END AS bed_band,
               {SHARES}
        FROM banded GROUP BY 1, 2 ORDER BY 1""")

    emit("distance_to_total_floor", f"""
        WITH gaps AS (SELECT reported_total_nurse_hprd - {TOTAL_FLOOR} AS gap FROM facilities WHERE reported_total_nurse_hprd IS NOT NULL),
        banded AS (
            SELECT gap, CASE WHEN gap < -1.0 THEN 1 WHEN gap < -0.5 THEN 2 WHEN gap < -0.25 THEN 3 WHEN gap < 0 THEN 4
                             WHEN gap < 0.25 THEN 5 WHEN gap < 0.5 THEN 6 WHEN gap < 1.0 THEN 7 ELSE 8 END AS band_order FROM gaps)
        SELECT band_order,
               CASE band_order WHEN 1 THEN 'More than 1.00 hours below' WHEN 2 THEN '0.50 to 1.00 hours below' WHEN 3 THEN '0.25 to 0.50 hours below'
                               WHEN 4 THEN 'Less than 0.25 hours below' WHEN 5 THEN 'At the floor to 0.25 hours above' WHEN 6 THEN '0.25 to 0.50 hours above'
                               WHEN 7 THEN '0.50 to 1.00 hours above' ELSE 'More than 1.00 hours above' END AS distance_from_total_floor,
               COUNT(*) AS facilities, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_facilities
        FROM banded GROUP BY 1, 2 ORDER BY 1""")

    if ctx["has_history"]:
        emit("trend_by_snapshot", f"""
            SELECT snapshot_date, processing_date AS cms_vintage, {SHARES}
            FROM facilities_history GROUP BY 1, 2 ORDER BY 1""")
        emit("trend_by_ownership_year", f"""
            WITH firsts AS (SELECT year(snapshot_date) AS snapshot_year, MIN(snapshot_date) AS snapshot_date FROM facilities_history GROUP BY 1)
            SELECT f.snapshot_year, f.snapshot_date, {OWNERSHIP_FROM_TYPE} AS ownership_category, {SHARES}
            FROM firsts f JOIN facilities_history h USING (snapshot_date) GROUP BY 1, 2, 3 ORDER BY 1, facilities DESC, ownership_category""")
        emit("state_change", f"""
            WITH bounds AS (SELECT MIN(snapshot_date) AS first_snapshot, MAX(snapshot_date) AS last_snapshot FROM facilities_history),
            per AS (
                SELECT h.state, h.snapshot_date, COUNT(*) AS facilities, ROUND(100.0 * AVG({ALL_THREE}), 1) AS pct_all_three,
                       ROUND(AVG(h.reported_total_nurse_hprd), 2) AS avg_total_nurse_hprd
                FROM facilities_history h, bounds b WHERE h.snapshot_date IN (b.first_snapshot, b.last_snapshot) GROUP BY 1, 2)
            SELECT a.state, a.snapshot_date AS first_snapshot, a.facilities AS facilities_first, a.pct_all_three AS pct_all_three_first, a.avg_total_nurse_hprd AS avg_total_first,
                   z.snapshot_date AS latest_snapshot, z.facilities AS facilities_latest, z.pct_all_three AS pct_all_three_latest, z.avg_total_nurse_hprd AS avg_total_latest,
                   ROUND(z.pct_all_three - a.pct_all_three, 1) AS change_in_pct_all_three,
                   LEAST(a.facilities, z.facilities) < {SMALL_STATE} AS suppressed
            FROM per a JOIN per z USING (state), bounds b
            WHERE a.snapshot_date = b.first_snapshot AND z.snapshot_date = b.last_snapshot ORDER BY a.state""")

    summary = _summary(release, manifest, con, out_dir, ctx["has_history"])
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    write_study_site("staffing", out_dir, manifest, list(results), extra={"small_state_threshold": SMALL_STATE, "history_store": ctx["has_history"],
                                                                       "floors": {"rn": RN_FLOOR, "aide": AIDE_FLOOR, "total": TOTAL_FLOOR}})
    results["site/staffing"] = {"rows": 1, "columns": ["staffing.json"]}
    # The hand-curated state standards sit beside the study runs (analysis/staffing/state_standards.json); the cuts quote them when present.
    standards_path = out_dir.parent / "state_standards.json"
    standards = json.loads(standards_path.read_text(encoding="utf-8")) if standards_path.exists() else None
    write_state_cuts("staffing", out_dir, manifest, SMALL_STATE, standards=standards)
    results["press/state_cuts"] = {"rows": 1, "columns": ["state_cuts.md"]}
    meta = {"study": "staffing", "release": release, "built_at": datetime.now(timezone.utc).isoformat(), "builder": {"name": "tcr-open-data", "version": __version__},
            "processing_date": manifest.get("processing_date"), "doi": manifest.get("doi"), "history_store": ctx["has_history"],
            "floors": {"rn": RN_FLOOR, "aide": AIDE_FLOOR, "total": TOTAL_FLOOR}, "tables": results}
    (out_dir / "study.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    con.close()
    return meta


def _csv(con: duckdb.DuckDBPyConnection, path: Path) -> tuple[list[str], list[tuple]]:
    if not path.exists():
        return [], []
    return _run(con, f"SELECT * FROM read_csv_auto('{_q(path)}', header=true)")


def _summary(release: str, manifest: dict, con: duckdb.DuckDBPyConnection, out_dir: Path, has_history: bool) -> str:
    cols, rows = _csv(con, out_dir / "national_summary.csv")
    n = dict(zip(cols, rows[0])) if rows else {}
    own_cols, own_rows = _csv(con, out_dir / "by_ownership.csv")
    oi = {c: i for i, c in enumerate(own_cols)}
    st_cols, st_rows = _csv(con, out_dir / "by_state.csv")
    si = {c: i for i, c in enumerate(st_cols)}
    ranked = sorted([r for r in st_rows if not r[si["suppressed"]] and r[si["pct_at_or_above_all_three"]] is not None],
                    key=lambda r: (-(r[si["pct_at_or_above_all_three"]] or 0), r[si["state"]]))
    lines = [
        f"# Staffing-standards study tables, release {release}",
        "",
        f"Computed from release {release} (CMS Provider Information vintage {manifest.get('processing_date', '')}). The floors are those of the federal minimum staffing rule "
        f"finalized in 2024 and rescinded effective February 2, 2026: {RN_FLOOR} registered-nurse, {AIDE_FLOOR} nurse-aide and {TOTAL_FLOOR} total nurse hours per resident day. "
        "Hours are the **reported** payroll-based hours CMS publishes, not adjusted for case mix, and the rule's 24/7 RN requirement is not tested because it needs daily payroll data. "
        "A facility below a floor is not thereby found to be understaffed for its residents; a facility above one is not thereby found to be adequately staffed.",
        "",
        "## Headline numbers",
        "",
        f"- Facilities with reported hours: {int(n.get('facilities_with_reported_hours') or 0):,} of {int(n.get('facilities') or 0):,}.",
        f"- At or above the RN floor: {n.get('pct_at_or_above_rn_floor')}%; the aide floor: {n.get('pct_at_or_above_aide_floor')}%; the total floor: {n.get('pct_at_or_above_total_floor')}%.",
        f"- At or above **all three**: {n.get('pct_at_or_above_all_three')}% ({int(n.get('facilities_at_or_above_all_three') or 0):,} facilities).",
        f"- Average reported hours per resident day: total {n.get('avg_total_nurse_hprd')}, RN {n.get('avg_rn_hprd')}, aide {n.get('avg_aide_hprd')}; nurse turnover {n.get('avg_total_nurse_turnover_pct')}%.",
        "",
        "## By ownership type",
        "",
        "| Ownership | Facilities with hours | RN floor | Aide floor | Total floor | All three | Avg total hours |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in own_rows:
        lines.append(f"| {r[oi['ownership_category']]} | {int(r[oi['facilities_with_reported_hours']]):,} | {r[oi['pct_at_or_above_rn_floor']]}% | {r[oi['pct_at_or_above_aide_floor']]}% | "
                     f"{r[oi['pct_at_or_above_total_floor']]}% | {r[oi['pct_at_or_above_all_three']]}% | {r[oi['avg_total_nurse_hprd']]} |")
    lines += ["", f"## States by share at or above all three floors (states with at least {SMALL_STATE} facilities)", "", "Highest:", ""]
    lines += [f"- {r[si['state']]}: {r[si['pct_at_or_above_all_three']]}% (total floor {r[si['pct_at_or_above_total_floor']]}%)" for r in ranked[:8]]
    lines += ["", "Lowest:", ""]
    lines += [f"- {r[si['state']]}: {r[si['pct_at_or_above_all_three']]}% (total floor {r[si['pct_at_or_above_total_floor']]}%)" for r in ranked[-8:]]
    if has_history:
        t_cols, t_rows = _csv(con, out_dir / "trend_by_snapshot.csv")
        ti = {c: i for i, c in enumerate(t_cols)}
        if t_rows:
            first, last = t_rows[0], t_rows[-1]
            peak = max(t_rows, key=lambda r: r[ti["pct_at_or_above_all_three"]] or 0)
            low = min(t_rows, key=lambda r: r[ti["pct_at_or_above_all_three"]] if r[ti["pct_at_or_above_all_three"]] is not None else 999)
            lines += ["", "## Since 2019 (history store)", "",
                      f"The share at or above all three floors was {first[ti['pct_at_or_above_all_three']]}% in the {first[ti['snapshot_date']]} file, peaked at {peak[ti['pct_at_or_above_all_three']]}% "
                      f"({peak[ti['snapshot_date']]}, when resident counts fell during the pandemic and hours per resident rose), reached a low of {low[ti['pct_at_or_above_all_three']]}% ({low[ti['snapshot_date']]}) "
                      f"and stands at {last[ti['pct_at_or_above_all_three']]}% in the {last[ti['snapshot_date']]} file (`trend_by_snapshot.csv`). `state_change.csv` compares each state's first and latest file; "
                      "`trend_by_ownership_year.csv` gives the yearly series by ownership type."]
    lines += ["", "## Files", "", "Every table in this directory is a CSV named for its content; `study.json` records the release, DOI, floors and row counts. Reproduce with "
              f"`tcr-open-data staffing-study --release releases/{release} --history history --out analysis/staffing/{release}`.", ""]
    return "\n".join(lines)
