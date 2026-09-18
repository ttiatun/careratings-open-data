"""The enforcement study runs end to end on the fixture release and the fixture history store."""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from tcr_open_data.enforcement_study import run_study
from test_history import two_snapshots  # noqa: F401  (fixture: a tiny history store)
from test_release import release  # noqa: F401  (fixture: the built fixture release)


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_enforcement_tables(release, tmp_path: Path):
    _raw, release_dir = release
    out = tmp_path / "enforcement"
    meta = run_study(release_dir, out, history_dir=None, min_chain=1)
    assert meta["study"] == "enforcement" and meta["history_store"] is False
    for name in ("national_summary", "fine_size_distribution", "concentration", "by_state", "by_ownership", "by_disclosure_group",
                 "by_chain_status", "top_chains_by_fines_per_facility", "top_facilities_by_fines", "same_day_fines"):
        assert (out / f"{name}.csv").exists(), name
    national = _read(out / "national_summary.csv")[0]
    states = _read(out / "by_state.csv")
    assert int(national["facilities"]) == sum(int(s["facilities"]) for s in states)
    assert int(national["fines"]) == sum(int(s["fines"]) for s in states)
    assert float(national["total_fines_dollars"]) == sum(float(s["total_fines_dollars"]) for s in states)
    assert all(s["suppressed"] in {"true", "false", "True", "False"} for s in states)
    bands = _read(out / "fine_size_distribution.csv")
    assert sum(int(b["fines"]) for b in bands) == int(national["fine_rows"])
    conc = {r["facility_group"]: r for r in _read(out / "concentration.csv")}
    assert float(conc["Top 25% of facilities"]["pct_of_fine_dollars"]) >= float(conc["Top 1% of facilities"]["pct_of_fine_dollars"])
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert summary.startswith(f"# Enforcement study tables, release {release_dir.name}") and "per instance or per day" in summary
    assert "fines_by_penalty_year" not in json.loads((out / "study.json").read_text(encoding="utf-8"))["tables"]
    cuts = (out / "press" / "state_cuts.md").read_text(encoding="utf-8")
    assert cuts.startswith("# State cuts:") and "Fine dollars per certified bed" in cuts or "fewer than 10" in cuts
    assert cuts.count("\n## ") == len(states)
    site = json.loads((out / "site" / "enforcement.json").read_text(encoding="utf-8"))
    assert site["study"] == "enforcement" and site["release"] == release_dir.name and site["small_state_threshold"] == 10
    assert site["tables"]["national_summary"][0]["facilities"] == int(national["facilities"])
    assert len(site["tables"]["by_state"]) == len(states) and isinstance(site["tables"]["by_state"][0]["suppressed"], bool)


def test_enforcement_history_tables(release, two_snapshots, tmp_path: Path):
    from tcr_open_data.history import backfill, consolidate

    _raw, release_dir = release
    history_dir, snapshots, openers = two_snapshots
    backfill(history_dir, snapshots, zip_opener=lambda url: zipfile.ZipFile(openers[url]), progress=lambda *_: None)
    consolidate(history_dir)
    meta = run_study(release_dir, tmp_path / "enforcement", history_dir=history_dir, min_chain=1)
    assert meta["history_store"] is True
    for name in ("fines_by_penalty_year", "fines_equal_maturity", "reporting_lag_by_year", "fines_in_file_by_snapshot", "denials_by_year", "sff_monthly", "sff_tenure"):
        assert (tmp_path / "enforcement" / f"{name}.csv").exists(), name
    monthly = _read(tmp_path / "enforcement" / "sff_monthly.csv")
    assert [r["snapshot_date"] for r in monthly] == ["2019-01-17", "2026-08-26"]
    in_file = _read(tmp_path / "enforcement" / "fines_in_file_by_snapshot.csv")
    assert all(int(r["fines_in_file"]) >= 1 for r in in_file)
    # Counted from the rows of each monthly Penalties file, so the dates are penalties snapshots only.
    assert {r["counted_from"] for r in in_file} == {"rows of the monthly file"}
    assert meta["tables"]["fines_in_file_by_snapshot"]["rows"] == len(in_file)
    import duckdb

    con = duckdb.connect()
    literal = dict(con.execute(
        f"SELECT CAST(snapshot_date AS VARCHAR), COUNT(*) FROM read_parquet('{(history_dir / 'harmonized' / 'penalties').as_posix()}/*.parquet') "
        "WHERE penalty_type ILIKE '%fine%' GROUP BY 1").fetchall())
    assert {r["snapshot_date"]: int(r["fines_in_file"]) for r in in_file} == {k[:10]: v for k, v in literal.items()}
    changes = _read(tmp_path / "enforcement" / "file_changes_by_snapshot.csv")
    assert [r["snapshot_date"] for r in changes] == [r["snapshot_date"] for r in in_file][1:]
    assert all(int(r["days_since_previous_file"]) > 0 and int(r["distinct_fines_added"]) >= 0 and int(r["distinct_fines_dropped"]) >= 0 for r in changes)
    site = json.loads((tmp_path / "enforcement" / "site" / "enforcement.json").read_text(encoding="utf-8"))
    assert site["fines_in_file_counted_from_files"] is True and "file_changes_by_snapshot" in site["tables"]


def test_fines_in_file_never_uses_a_snapshot_without_a_penalties_file(release, two_snapshots, tmp_path: Path):
    """A snapshot that re-publishes Provider Information only must not appear as a Penalties file."""
    import duckdb

    from tcr_open_data.history import backfill, consolidate

    _raw, release_dir = release
    history_dir, snapshots, openers = two_snapshots
    backfill(history_dir, snapshots, zip_opener=lambda url: zipfile.ZipFile(openers[url]), progress=lambda *_: None)
    consolidate(history_dir)
    # Add a provider-only snapshot to facilities_history, as the CMS archive did on 2026-08-06.
    con = duckdb.connect()
    fac = (history_dir / "facilities_history.parquet").as_posix()
    con.execute(f"CREATE TABLE f AS SELECT * FROM read_parquet('{fac}')")
    con.execute("INSERT INTO f SELECT * REPLACE (CAST('2026-08-06' AS DATE) AS snapshot_date) FROM f WHERE CAST(snapshot_date AS VARCHAR) LIKE '2026-08-26%'")
    con.execute(f"COPY f TO '{fac}' (FORMAT PARQUET)")
    con.close()
    run_study(release_dir, tmp_path / "enforcement", history_dir=history_dir, min_chain=1)
    dates = [r["snapshot_date"] for r in _read(tmp_path / "enforcement" / "fines_in_file_by_snapshot.csv")]
    assert "2026-08-06" not in dates and dates == ["2019-01-17", "2026-08-26"]
    assert "2026-08-06" not in [r["snapshot_date"] for r in _read(tmp_path / "enforcement" / "file_changes_by_snapshot.csv")]
    # The reconstruction fallback (no harmonized files on disk) keeps to penalties dates as well.
    import shutil

    shutil.rmtree(history_dir / "harmonized" / "penalties")
    run_study(release_dir, tmp_path / "fallback", history_dir=history_dir, min_chain=1)
    fallback = _read(tmp_path / "fallback" / "fines_in_file_by_snapshot.csv")
    assert "2026-08-06" not in [r["snapshot_date"] for r in fallback]
    assert {r["counted_from"] for r in fallback} == {"reconstructed from first and last seen dates"}
