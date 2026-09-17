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
