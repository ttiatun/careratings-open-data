"""
Validate a built release: schema conformance, row counts, and reconciliation
against the national row of the CMS chain file.

The chain file and the Provider Information file are usually different
vintages, so the reconciliation carries tolerances. A gap past tolerance is a
warning for a human; `strict` turns warnings into failures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from .build import TABLE_ORDER
from .schema import DUCKDB_TYPES, load_schema


@dataclass
class Check:
    name: str
    status: str  # pass | warn | fail
    detail: dict = field(default_factory=dict)


@dataclass
class ValidationReport:
    release: str
    checks: list[Check]

    @property
    def failed(self) -> bool:
        return any(c.status == "fail" for c in self.checks)

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == "warn"]

    def to_dict(self) -> dict:
        return {"release": self.release, "status": "fail" if self.failed else ("warn" if self.warnings else "pass"),
                "checks": [{"name": c.name, "status": c.status, **c.detail} for c in self.checks]}


TOLERANCES_PCT = {
    "facilities": 1.0, "sff": 15.0, "sff_candidates": 15.0, "abuse_icons": 10.0,
    "total_fines_dollars": 3.0, "total_fines": 3.0, "payment_denials": 5.0,
}


def reconcile(ours: dict[str, float], cms: dict[str, float]) -> list[Check]:
    checks = []
    for metric, tolerance in TOLERANCES_PCT.items():
        a, b = float(ours.get(metric) or 0), float(cms.get(metric) or 0)
        diff_pct = 0.0 if a == b else (100.0 if b == 0 else abs(a - b) / b * 100)
        checks.append(Check(f"reconcile:{metric}", "pass" if diff_pct <= tolerance else "warn",
                            {"ours": a, "cms_national_row": b, "diff_pct": round(diff_pct, 2), "tolerance_pct": tolerance}))
    return checks


def validate_release(release_dir: Path, strict: bool = False) -> ValidationReport:
    schema = load_schema()
    build = json.loads((release_dir / "build.json").read_text(encoding="utf-8"))
    checks: list[Check] = []
    con = duckdb.connect()
    q = lambda p: p.resolve().as_posix().replace("'", "''")

    for table in TABLE_ORDER:
        parquet = release_dir / f"{table}.parquet"
        csv = release_dir / f"{table}.csv"
        if not parquet.exists() or not csv.exists():
            checks.append(Check(f"files:{table}", "fail", {"error": "missing csv or parquet"}))
            continue
        described = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{q(parquet)}')").fetchall()
        actual = [(r[0], r[1]) for r in described]
        expected = [(c["name"], DUCKDB_TYPES[c["type"]]) for c in schema["tables"][table]["columns"]]
        if table == "chains":
            expected += [(c, "DOUBLE") for c in build.get("chain_measure_columns", [])]
        ok = actual == expected
        checks.append(Check(f"schema:{table}", "pass" if ok else "fail",
                            {} if ok else {"expected": expected, "actual": actual}))
        rows_parquet = con.execute(f"SELECT COUNT(*) FROM read_parquet('{q(parquet)}')").fetchone()[0]
        rows_csv = con.execute(f"SELECT COUNT(*) FROM read_csv('{q(csv)}', header=true, all_varchar=true)").fetchone()[0]
        recorded = build["tables"][table]["rows"]
        consistent = rows_parquet == rows_csv == recorded and rows_parquet > 0
        checks.append(Check(f"rows:{table}", "pass" if consistent else "fail",
                            {"parquet": rows_parquet, "csv": rows_csv, "build_json": recorded}))
        key = schema["tables"][table]["key"]
        key_sql = ", ".join(f'"{k}"' for k in key)
        dupes = con.execute(f"SELECT COUNT(*) FROM (SELECT {key_sql}, COUNT(*) AS n FROM read_parquet('{q(parquet)}') GROUP BY ALL HAVING n > 1)").fetchone()[0]
        checks.append(Check(f"key:{table}", "pass" if dupes == 0 else ("warn" if table in ("owners_carecompare", "penalties", "owners_pecos", "changes_of_ownership") else "fail"),
                            {"key": key, "duplicate_groups": dupes}))

    fac = q(release_dir / "facilities.parquet")
    ours_row = con.execute(f"""
        SELECT COUNT(*)::INTEGER, COUNT(*) FILTER (WHERE special_focus_status = 'SFF')::INTEGER,
               COUNT(*) FILTER (WHERE special_focus_status = 'SFF Candidate')::INTEGER, COUNT(*) FILTER (WHERE abuse_icon)::INTEGER,
               COALESCE(SUM(total_fines_dollars), 0), COALESCE(SUM(num_fines), 0)::INTEGER, COALESCE(SUM(num_payment_denials), 0)::INTEGER
        FROM read_parquet('{fac}')""").fetchone()
    ours = dict(zip(["facilities", "sff", "sff_candidates", "abuse_icons", "total_fines_dollars", "total_fines", "payment_denials"], ours_row))
    national = con.execute(f"""
        SELECT facility_count, sff_count, sff_candidate_count, abuse_icon_count, total_fines_dollars, total_fines, total_payment_denials
        FROM read_parquet('{q(release_dir / "chains.parquet")}') WHERE chain_id = 'NATIONAL'""").fetchone()
    if national is None:
        checks.append(Check("reconcile:national_row", "fail", {"error": "chains has no NATIONAL row"}))
    else:
        cms = dict(zip(["facilities", "sff", "sff_candidates", "abuse_icons", "total_fines_dollars", "total_fines", "payment_denials"], national))
        checks.extend(reconcile(ours, cms))

    coverage = con.execute(f"""
        SELECT COUNT(*)::INTEGER AS facilities, COUNT(pecos_enrollment_id)::INTEGER AS with_enrollment,
               COUNT(*) FILTER (WHERE pecos_owner_rows > 0)::INTEGER AS with_owner_rows,
               COUNT(DISTINCT chain_id)::INTEGER AS chain_ids
        FROM read_parquet('{fac}')""").fetchone()
    facilities, with_enrollment, with_owner_rows, chain_ids = coverage
    matched = con.execute(f"""
        SELECT COUNT(DISTINCT f.chain_id)::INTEGER FROM read_parquet('{fac}') f
        JOIN read_parquet('{q(release_dir / "chains.parquet")}') c ON c.chain_id = f.chain_id""").fetchone()[0]
    unresolved_owner_rows = con.execute(f"SELECT COUNT(*) FROM read_parquet('{q(release_dir / 'owners_pecos.parquet')}') WHERE ccn IS NULL").fetchone()[0]
    enrollment_share = with_enrollment / facilities if facilities else 0
    chain_share = matched / chain_ids if chain_ids else 1
    checks.append(Check("coverage:pecos_enrollment", "pass" if enrollment_share >= 0.9 else "fail",
                        {"facilities": facilities, "with_enrollment": with_enrollment, "with_owner_rows": with_owner_rows, "share": round(enrollment_share, 4)}))
    checks.append(Check("coverage:chain_ids", "pass" if chain_share >= 0.9 else "fail",
                        {"chain_ids_in_facilities": chain_ids, "matched_in_chain_file": matched, "share": round(chain_share, 4)}))
    checks.append(Check("coverage:owner_rows_unresolved", "pass" if unresolved_owner_rows == 0 else "warn", {"rows_without_ccn": unresolved_owner_rows}))
    con.close()

    if strict:
        for c in checks:
            if c.status == "warn":
                c.status = "fail"
    report = ValidationReport(build["release"], checks)
    (release_dir / "validation.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report
