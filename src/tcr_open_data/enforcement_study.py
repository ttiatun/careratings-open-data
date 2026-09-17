"""
Enforcement study: the descriptive tables behind brief D2.

    tcr-open-data enforcement-study --release releases/v2026.08 [--history history] --out analysis/enforcement/v2026.08

Computed with DuckDB from the release tables (facilities, penalties) and,
when a history store is present, from penalties_history and
facilities_history. Every output names the release it came from.

What the public Penalties file is, and is not: one row per fine or payment
denial in a three-year lookback, with a date and an amount. It carries no
flag for per-instance versus per-day civil money penalties, and a fine
enters the file months after it is imposed, so the most recent year is
always incomplete. The tables below are built to keep those two limits in
view: recent years carry a maturity note, the trend is also given at equal
maturity, and nothing here infers the type of a penalty.

Outputs (CSV unless noted):
  national_summary          one row: fines, dollars, denials, shares, lookback window
  fine_size_distribution    fines and dollars by size band
  concentration             share of fine dollars held by the most-fined facilities
  by_state                  per-state rates (states under ten facilities flagged suppressed)
  by_ownership              for-profit, non-profit, government
  by_disclosure_group       the ownership study's PECOS disclosure groups
  by_chain_status           in a CMS-identified chain or not
  top_chains_by_fines_per_facility   chains with at least --min-chain facilities
  top_facilities_by_fines   the most-fined facilities in the lookback
  same_day_fines            facility-dates by number of fines imposed that day
  fines_by_penalty_year     every fine seen in any snapshot, by penalty year (history store)
  fines_equal_maturity      the same, counted only if visible by August 31 of the next year (history store)
  reporting_lag_by_year     days from penalty date to first appearance in the file (history store)
  fines_in_file_by_snapshot fines and dollars present in each monthly file (history store)
  denials_by_year           payment denials by year (history store)
  sff_monthly               Special Focus Facilities and candidates per snapshot (history store)
  sff_tenure                how long facilities stay in the program and what became of them (history store)
  summary.md                the headline numbers in prose, with the caveats
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from . import __version__
from .ownership_study import DISCLOSURE_GROUP, _q, _run, _write_csv
from .study_site import write_study_site

SMALL_STATE = 10

RATES = """
    COUNT(*) AS facilities,
    SUM(certified_beds) AS certified_beds,
    SUM(CASE WHEN COALESCE(num_fines, 0) > 0 THEN 1 ELSE 0 END) AS facilities_fined,
    ROUND(100.0 * AVG(CASE WHEN COALESCE(num_fines, 0) > 0 THEN 1 ELSE 0 END), 1) AS pct_facilities_fined,
    SUM(COALESCE(num_fines, 0)) AS fines,
    ROUND(100.0 * SUM(COALESCE(num_fines, 0)) / COUNT(*), 1) AS fines_per_100_facilities,
    ROUND(SUM(COALESCE(total_fines_dollars, 0)), 0) AS total_fines_dollars,
    ROUND(SUM(COALESCE(total_fines_dollars, 0)) / COUNT(*), 0) AS fines_dollars_per_facility,
    ROUND(SUM(COALESCE(total_fines_dollars, 0)) / NULLIF(SUM(certified_beds), 0), 0) AS fines_dollars_per_bed,
    SUM(COALESCE(num_payment_denials, 0)) AS payment_denials,
    ROUND(100.0 * SUM(COALESCE(num_payment_denials, 0)) / COUNT(*), 1) AS denials_per_100_facilities,
    ROUND(100.0 * AVG(CASE WHEN COALESCE(total_penalties, 0) > 0 THEN 1 ELSE 0 END), 1) AS pct_with_any_penalty,
    SUM(CASE WHEN special_focus_status IS NOT NULL THEN 1 ELSE 0 END) AS sff_or_candidate,
    SUM(abuse_icon::INT) AS abuse_icon_facilities,
    ROUND(AVG(overall_rating), 2) AS avg_overall_rating
"""

FINE = "penalty_type ILIKE '%fine%'"
DENIAL = "penalty_type ILIKE '%denial%'"
SFF_FLAG = "special_focus_status IN ('SFF', 'Y')"


def register_views(con: duckdb.DuckDBPyConnection, release_dir: Path, history_dir: Path | None) -> dict:
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    for table in ("facilities", "penalties"):
        con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_parquet('{_q(release_dir / (table + '.parquet'))}')")
    has_history = False
    if history_dir and (history_dir / "penalties_history.parquet").exists() and (history_dir / "facilities_history.parquet").exists():
        con.execute(f"CREATE OR REPLACE VIEW penalties_history AS SELECT * FROM read_parquet('{_q(history_dir / 'penalties_history.parquet')}')")
        con.execute(f"CREATE OR REPLACE VIEW facilities_history AS SELECT * FROM read_parquet('{_q(history_dir / 'facilities_history.parquet')}')")
        has_history = True
    return {"manifest": manifest, "has_history": has_history}


def run_study(release_dir: Path, out_dir: Path, history_dir: Path | None = None, top_n: int = 25, min_chain: int = 20) -> dict:
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
        WITH p AS (
            SELECT COUNT(*) FILTER (WHERE {FINE}) AS fine_rows,
                   ROUND(MEDIAN(fine_amount) FILTER (WHERE {FINE}), 0) AS median_fine_dollars,
                   ROUND(AVG(fine_amount) FILTER (WHERE {FINE}), 0) AS mean_fine_dollars,
                   MIN(penalty_date) AS earliest_penalty_date, MAX(penalty_date) AS latest_penalty_date
            FROM penalties)
        SELECT '{release}' AS release, {RATES},
               p.fine_rows, p.median_fine_dollars, p.mean_fine_dollars, p.earliest_penalty_date, p.latest_penalty_date
        FROM facilities, p GROUP BY ALL""")

    emit("fine_size_distribution", f"""
        WITH banded AS (
            SELECT CASE WHEN fine_amount < 5000 THEN 1 WHEN fine_amount < 10000 THEN 2 WHEN fine_amount < 25000 THEN 3
                        WHEN fine_amount < 100000 THEN 4 WHEN fine_amount < 500000 THEN 5 ELSE 6 END AS band_order, fine_amount
            FROM penalties WHERE {FINE} AND fine_amount IS NOT NULL)
        SELECT band_order,
               CASE band_order WHEN 1 THEN 'Under $5,000' WHEN 2 THEN '$5,000 to $9,999' WHEN 3 THEN '$10,000 to $24,999'
                               WHEN 4 THEN '$25,000 to $99,999' WHEN 5 THEN '$100,000 to $499,999' ELSE '$500,000 or more' END AS band,
               COUNT(*) AS fines, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_fines,
               ROUND(SUM(fine_amount), 0) AS dollars, ROUND(100.0 * SUM(fine_amount) / SUM(SUM(fine_amount)) OVER (), 1) AS pct_of_dollars
        FROM banded GROUP BY 1, 2 ORDER BY 1""")

    emit("concentration", """
        WITH ranked AS (
            SELECT ccn, COALESCE(total_fines_dollars, 0) AS dollars,
                   ROW_NUMBER() OVER (ORDER BY COALESCE(total_fines_dollars, 0) DESC, ccn) AS rn,
                   COUNT(*) OVER () AS n, SUM(COALESCE(total_fines_dollars, 0)) OVER () AS total
            FROM facilities),
        running AS (SELECT *, SUM(dollars) OVER (ORDER BY rn) AS cumulative FROM ranked)
        SELECT 'Top 1% of facilities' AS facility_group, MAX(CASE WHEN rn <= CEIL(n * 0.01) THEN rn END) AS facilities_in_group,
               ROUND(100.0 * SUM(CASE WHEN rn <= CEIL(n * 0.01) THEN dollars ELSE 0 END) / NULLIF(MAX(total), 0), 1) AS pct_of_fine_dollars FROM running
        UNION ALL SELECT 'Top 5% of facilities', MAX(CASE WHEN rn <= CEIL(n * 0.05) THEN rn END), ROUND(100.0 * SUM(CASE WHEN rn <= CEIL(n * 0.05) THEN dollars ELSE 0 END) / NULLIF(MAX(total), 0), 1) FROM running
        UNION ALL SELECT 'Top 10% of facilities', MAX(CASE WHEN rn <= CEIL(n * 0.10) THEN rn END), ROUND(100.0 * SUM(CASE WHEN rn <= CEIL(n * 0.10) THEN dollars ELSE 0 END) / NULLIF(MAX(total), 0), 1) FROM running
        UNION ALL SELECT 'Top 25% of facilities', MAX(CASE WHEN rn <= CEIL(n * 0.25) THEN rn END), ROUND(100.0 * SUM(CASE WHEN rn <= CEIL(n * 0.25) THEN dollars ELSE 0 END) / NULLIF(MAX(total), 0), 1) FROM running
        UNION ALL SELECT 'Fewest facilities holding half of all fine dollars', MIN(CASE WHEN cumulative >= total / 2.0 THEN rn END), 50.0 FROM running""")

    emit("by_state", f"""
        SELECT state, {RATES}, COUNT(*) < {SMALL_STATE} AS suppressed
        FROM facilities GROUP BY state ORDER BY state""")

    emit("by_ownership", f"""
        SELECT ownership_category, {RATES} FROM facilities GROUP BY 1 ORDER BY facilities DESC, ownership_category""")

    emit("by_disclosure_group", f"""
        SELECT {DISCLOSURE_GROUP} AS disclosure_group, {RATES} FROM facilities GROUP BY 1 ORDER BY facilities DESC, disclosure_group""")

    emit("by_chain_status", f"""
        SELECT CASE WHEN chain_id IS NOT NULL THEN 'In a CMS-identified chain' ELSE 'Not in a chain' END AS chain_status, {RATES}
        FROM facilities GROUP BY 1 ORDER BY facilities DESC""")

    emit("top_chains_by_fines_per_facility", f"""
        SELECT chain_id, chain_name, {RATES}
        FROM facilities WHERE chain_id IS NOT NULL GROUP BY 1, 2 HAVING COUNT(*) >= {int(min_chain)}
        ORDER BY fines_dollars_per_facility DESC, chain_name LIMIT {int(top_n)}""")

    emit("top_facilities_by_fines", f"""
        SELECT ccn, provider_name, city, state, ownership_category, chain_name, certified_beds, overall_rating, special_focus_status, abuse_icon,
               num_fines, ROUND(total_fines_dollars, 0) AS total_fines_dollars, num_payment_denials
        FROM facilities WHERE COALESCE(total_fines_dollars, 0) > 0
        ORDER BY total_fines_dollars DESC, ccn LIMIT {int(top_n)}""")

    emit("same_day_fines", f"""
        WITH days AS (SELECT ccn, penalty_date, COUNT(*) AS fines_that_day, SUM(fine_amount) AS dollars FROM penalties WHERE {FINE} GROUP BY 1, 2)
        SELECT LEAST(fines_that_day, 5) AS fines_on_the_same_day, COUNT(*) AS facility_dates, SUM(fines_that_day) AS fines, ROUND(SUM(dollars), 0) AS dollars
        FROM days GROUP BY 1 ORDER BY 1""")

    if ctx["has_history"]:
        emit("fines_by_penalty_year", f"""
            WITH bounds AS (SELECT MAX(last_seen_snapshot) AS last_snapshot FROM penalties_history)
            SELECT year(penalty_date) AS penalty_year, COUNT(*) AS fines, ROUND(SUM(fine_amount), 0) AS dollars,
                   ROUND(MEDIAN(fine_amount), 0) AS median_fine_dollars, ROUND(AVG(fine_amount), 0) AS mean_fine_dollars,
                   CASE WHEN year(penalty_date) >= year(MAX(last_snapshot)) - 1 THEN 'incomplete: fines enter the file months after they are imposed' ELSE '' END AS note
            FROM penalties_history, bounds WHERE {FINE} AND penalty_date IS NOT NULL GROUP BY 1 ORDER BY 1""")

        emit("fines_equal_maturity", f"""
            WITH bounds AS (SELECT MIN(first_seen_snapshot) AS first_snapshot, MAX(last_seen_snapshot) AS last_snapshot FROM penalties_history)
            SELECT year(penalty_date) AS penalty_year, COUNT(*) AS fines_visible_by_aug_31_next_year, ROUND(SUM(fine_amount), 0) AS dollars,
                   ROUND(MEDIAN(fine_amount), 0) AS median_fine_dollars
            FROM penalties_history, bounds
            WHERE {FINE} AND penalty_date IS NOT NULL
              AND first_seen_snapshot <= make_date(year(penalty_date) + 1, 8, 31)
              AND make_date(year(penalty_date) + 1, 8, 31) <= last_snapshot + INTERVAL 5 DAY
              AND year(penalty_date) >= year(first_snapshot) - 1
            GROUP BY 1 ORDER BY 1""")

        emit("reporting_lag_by_year", f"""
            WITH bounds AS (SELECT MIN(first_seen_snapshot) AS first_snapshot FROM penalties_history),
            lagged AS (SELECT year(first_seen_snapshot) AS first_seen_year, date_diff('day', penalty_date, first_seen_snapshot) AS lag_days
                       FROM penalties_history, bounds WHERE {FINE} AND penalty_date IS NOT NULL AND first_seen_snapshot > first_snapshot)
            SELECT first_seen_year, COUNT(*) AS fines_first_seen, ROUND(MEDIAN(lag_days), 0) AS median_lag_days,
                   ROUND(quantile_cont(lag_days, 0.25), 0) AS p25_lag_days, ROUND(quantile_cont(lag_days, 0.75), 0) AS p75_lag_days,
                   ROUND(quantile_cont(lag_days, 0.90), 0) AS p90_lag_days
            FROM lagged GROUP BY 1 ORDER BY 1""")

        emit("fines_in_file_by_snapshot", f"""
            WITH snaps AS (SELECT DISTINCT snapshot_date FROM facilities_history)
            SELECT s.snapshot_date, COUNT(*) AS fines_in_file, ROUND(SUM(p.fine_amount), 0) AS dollars_in_file,
                   COUNT(DISTINCT p.ccn) AS facilities_with_a_fine
            FROM snaps s JOIN penalties_history p ON p.first_seen_snapshot <= s.snapshot_date AND p.last_seen_snapshot >= s.snapshot_date
            WHERE p.{FINE} GROUP BY 1 ORDER BY 1""")

        emit("denials_by_year", f"""
            SELECT year(penalty_date) AS penalty_year, COUNT(*) AS payment_denials, ROUND(AVG(payment_denial_length_days), 0) AS avg_length_days,
                   ROUND(MEDIAN(payment_denial_length_days), 0) AS median_length_days
            FROM penalties_history WHERE {DENIAL} AND penalty_date IS NOT NULL GROUP BY 1 ORDER BY 1""")

        emit("sff_monthly", f"""
            SELECT snapshot_date, COUNT(*) AS facilities,
                   SUM(CASE WHEN {SFF_FLAG} THEN 1 ELSE 0 END) AS special_focus_facilities,
                   SUM(CASE WHEN special_focus_status = 'SFF Candidate' THEN 1 ELSE 0 END) AS sff_candidates
            FROM facilities_history GROUP BY 1 ORDER BY 1""")

        emit("sff_tenure", f"""
            WITH flagged AS (SELECT ccn, COUNT(DISTINCT snapshot_date) AS snapshots_flagged FROM facilities_history WHERE {SFF_FLAG} GROUP BY 1),
            last_snap AS (SELECT MAX(snapshot_date) AS d FROM facilities_history),
            cur AS (SELECT f.ccn, f.special_focus_status, f.overall_rating FROM facilities_history f, last_snap WHERE f.snapshot_date = last_snap.d)
            SELECT COUNT(*) AS facilities_ever_sff,
                   ROUND(MEDIAN(snapshots_flagged), 0) AS median_snapshots_flagged,
                   ROUND(quantile_cont(snapshots_flagged, 0.9), 0) AS p90_snapshots_flagged,
                   MAX(snapshots_flagged) AS max_snapshots_flagged,
                   SUM(CASE WHEN snapshots_flagged >= 24 THEN 1 ELSE 0 END) AS flagged_24_or_more_snapshots,
                   SUM(CASE WHEN c.special_focus_status = 'SFF' THEN 1 ELSE 0 END) AS still_sff,
                   SUM(CASE WHEN c.special_focus_status = 'SFF Candidate' THEN 1 ELSE 0 END) AS now_candidates,
                   SUM(CASE WHEN c.ccn IS NOT NULL AND c.special_focus_status IS NULL THEN 1 ELSE 0 END) AS certified_and_no_longer_flagged,
                   SUM(CASE WHEN c.ccn IS NULL THEN 1 ELSE 0 END) AS no_longer_in_the_file,
                   ROUND(AVG(CASE WHEN c.ccn IS NOT NULL AND c.special_focus_status IS NULL THEN c.overall_rating END), 2) AS avg_rating_of_former_sff
            FROM flagged fl LEFT JOIN cur c USING (ccn)""")

    summary = _summary(release, manifest, con, out_dir, ctx["has_history"])
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    write_study_site("enforcement", out_dir, manifest, list(results), extra={"small_state_threshold": SMALL_STATE, "history_store": ctx["has_history"]})
    results["site/enforcement"] = {"rows": 1, "columns": ["enforcement.json"]}
    meta = {"study": "enforcement", "release": release, "built_at": datetime.now(timezone.utc).isoformat(), "builder": {"name": "tcr-open-data", "version": __version__},
            "processing_date": manifest.get("processing_date"), "doi": manifest.get("doi"), "history_store": ctx["has_history"], "tables": results}
    (out_dir / "study.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    con.close()
    return meta


def _csv(con: duckdb.DuckDBPyConnection, path: Path) -> tuple[list[str], list[tuple]]:
    if not path.exists():
        return [], []
    return _run(con, f"SELECT * FROM read_csv_auto('{_q(path)}', header=true)")


def _money(value) -> str:
    return "n/a" if value is None else f"${float(value):,.0f}"


def _summary(release: str, manifest: dict, con: duckdb.DuckDBPyConnection, out_dir: Path, has_history: bool) -> str:
    cols, rows = _csv(con, out_dir / "national_summary.csv")
    n = dict(zip(cols, rows[0])) if rows else {}
    conc = {r[0]: r for r in _csv(con, out_dir / "concentration.csv")[1]}
    own = _csv(con, out_dir / "by_ownership.csv")
    own_i = {c: i for i, c in enumerate(own[0])}
    states = [r for r in _csv(con, out_dir / "by_state.csv")[1]]
    st_cols = _csv(con, out_dir / "by_state.csv")[0]
    si = {c: i for i, c in enumerate(st_cols)}
    ranked = sorted([r for r in states if not r[si["suppressed"]]], key=lambda r: (-(r[si["fines_dollars_per_bed"]] or 0), r[si["state"]]))
    lines = [
        f"# Enforcement study tables, release {release}",
        "",
        f"Computed from release {release} (CMS Provider Information vintage {manifest.get('processing_date', '')}). The public Penalties file lists each fine and payment denial in a "
        "three-year lookback with a date and an amount. It does **not** say whether a civil money penalty was per instance or per day, and a fine reaches the file "
        "months after it is imposed, so the latest year is always incomplete. Comparisons are descriptive: they do not control for case mix, size, survey practice or region.",
        "",
        "## Headline numbers",
        "",
        f"- Fines in the lookback ({n.get('earliest_penalty_date')} to {n.get('latest_penalty_date')}): {int(n.get('fines') or 0):,} totalling {_money(n.get('total_fines_dollars'))}; "
        f"median fine {_money(n.get('median_fine_dollars'))}, mean {_money(n.get('mean_fine_dollars'))}.",
        f"- {int(n.get('facilities_fined') or 0):,} of {int(n.get('facilities') or 0):,} facilities ({n.get('pct_facilities_fined')}%) have at least one fine; "
        f"{n.get('pct_with_any_penalty')}% have a fine or a payment denial. Payment denials: {int(n.get('payment_denials') or 0):,}.",
        f"- Per facility: {_money(n.get('fines_dollars_per_facility'))}; per certified bed: {_money(n.get('fines_dollars_per_bed'))}.",
    ]
    if conc:
        top1, top5, top10 = conc.get("Top 1% of facilities"), conc.get("Top 5% of facilities"), conc.get("Top 10% of facilities")
        half = conc.get("Fewest facilities holding half of all fine dollars")
        lines.append(f"- Concentration: the most-fined 1% of facilities hold {top1[2]}% of fine dollars, the top 5% hold {top5[2]}% and the top 10% hold {top10[2]}%; "
                     f"{int(half[1]):,} facilities account for half of all fine dollars.")
    lines += ["", "## By ownership type", "", "| Ownership | Facilities | % fined | Fines per 100 facilities | $ per facility | $ per bed | Denials per 100 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in own[1]:
        lines.append(f"| {r[own_i['ownership_category']]} | {int(r[own_i['facilities']]):,} | {r[own_i['pct_facilities_fined']]} | {r[own_i['fines_per_100_facilities']]} | "
                     f"{_money(r[own_i['fines_dollars_per_facility']])} | {_money(r[own_i['fines_dollars_per_bed']])} | {r[own_i['denials_per_100_facilities']]} |")
    lines += ["", f"## States by fine dollars per certified bed (states with at least {SMALL_STATE} facilities)", "", "Highest:", ""]
    lines += [f"- {r[si['state']]}: {_money(r[si['fines_dollars_per_bed']])} per bed, {r[si['pct_facilities_fined']]}% of facilities fined, {_money(r[si['total_fines_dollars']])} in all" for r in ranked[:8]]
    lines += ["", "Lowest:", ""]
    lines += [f"- {r[si['state']]}: {_money(r[si['fines_dollars_per_bed']])} per bed, {r[si['pct_facilities_fined']]}% of facilities fined" for r in ranked[-5:]]
    lines += ["", "State differences reflect survey and enforcement practice as much as facility conduct; CMS regional offices and state survey agencies differ in how often they recommend and impose penalties."]
    if has_history:
        lag = _csv(con, out_dir / "reporting_lag_by_year.csv")[1]
        eq = _csv(con, out_dir / "fines_equal_maturity.csv")[1]
        infile = _csv(con, out_dir / "fines_in_file_by_snapshot.csv")[1]
        tenure = _csv(con, out_dir / "sff_tenure.csv")
        lines += ["", "## History store tables", ""]
        if lag and lag[-1][2] is not None:
            last = lag[-1]
            lines.append(f"- **Reporting lag.** Fines first seen in {last[0]} appeared a median of {int(last[2])} days after the penalty date (90th percentile {int(last[5])} days). "
                         "Counts for the latest two penalty years will keep rising (`reporting_lag_by_year.csv`, `fines_by_penalty_year.csv`).")
        if eq:
            lines.append("- **Trend at equal maturity** (fines visible by August 31 of the following year, `fines_equal_maturity.csv`): "
                         + "; ".join(f"{r[0]}: {int(r[1]):,} fines, {_money(r[2])}, median {_money(r[3])}" for r in eq) + ".")
        if infile:
            peak = max(infile, key=lambda r: r[1])
            lines.append(f"- **Fines in the file.** The monthly file held {int(peak[1]):,} fines ({_money(peak[2])}) at its peak on {peak[0]} and holds {int(infile[-1][1]):,} ({_money(infile[-1][2])}) on {infile[-1][0]} "
                         "(`fines_in_file_by_snapshot.csv`). The three-year lookback is rolling off the 2021 to 2023 surge.")
        if tenure[1] and tenure[1][0][0]:
            t = {k: (v if v is not None else 0) for k, v in zip(tenure[0], tenure[1][0])}
            lines.append(f"- **Special Focus Facilities.** {int(t['facilities_ever_sff']):,} facilities carried the SFF flag in at least one monthly file; the median was {int(t['median_snapshots_flagged'])} monthly files and "
                         f"{int(t['flagged_24_or_more_snapshots'])} were flagged in 24 or more. Today {int(t['still_sff'])} are still SFFs, {int(t['now_candidates'])} are candidates, "
                         f"{int(t['certified_and_no_longer_flagged'])} are certified and no longer flagged (average overall rating {t['avg_rating_of_former_sff']}), and {int(t['no_longer_in_the_file'])} are no longer in the file (`sff_tenure.csv`, `sff_monthly.csv`).")
    lines += ["", "## Files", "", "Every table in this directory is a CSV named for its content; `study.json` records the release, DOI and row counts. Reproduce with "
              f"`tcr-open-data enforcement-study --release releases/{release} --history history --out analysis/enforcement/{release}`.", ""]
    return "\n".join(lines)
