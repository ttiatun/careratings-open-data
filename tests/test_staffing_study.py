"""The staffing-standards study runs end to end on the fixture release and the fixture history store."""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from tcr_open_data.staffing_study import AIDE_FLOOR, RN_FLOOR, TOTAL_FLOOR, run_study
from test_history import two_snapshots  # noqa: F401  (fixture: a tiny history store)
from test_release import release  # noqa: F401  (fixture: the built fixture release)


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_floors_are_the_rescinded_rule():
    assert (RN_FLOOR, AIDE_FLOOR, TOTAL_FLOOR) == (0.55, 2.45, 3.48)


def test_staffing_tables(release, tmp_path: Path):
    _raw, release_dir = release
    out = tmp_path / "staffing"
    meta = run_study(release_dir, out, history_dir=None)
    assert meta["study"] == "staffing" and meta["floors"] == {"rn": 0.55, "aide": 2.45, "total": 3.48}
    for name in ("national_summary", "by_state", "by_ownership", "by_chain_status", "by_disclosure_group", "by_overall_rating", "by_bed_size", "distance_to_total_floor"):
        assert (out / f"{name}.csv").exists(), name
    national = _read(out / "national_summary.csv")[0]
    states = _read(out / "by_state.csv")
    assert int(national["facilities"]) == sum(int(s["facilities"]) for s in states)
    assert int(national["facilities_at_or_above_all_three"]) == sum(int(s["facilities_at_or_above_all_three"] or 0) for s in states)
    for key in ("pct_at_or_above_rn_floor", "pct_at_or_above_aide_floor", "pct_at_or_above_total_floor", "pct_at_or_above_all_three"):
        assert 0 <= float(national[key]) <= 100
    assert float(national["pct_at_or_above_all_three"]) <= min(float(national["pct_at_or_above_rn_floor"]), float(national["pct_at_or_above_aide_floor"]), float(national["pct_at_or_above_total_floor"]))
    gaps = _read(out / "distance_to_total_floor.csv")
    assert sum(int(g["facilities"]) for g in gaps) == int(national["facilities_with_reported_hours"])
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "rescinded effective February 2, 2026" in summary and "24/7 RN requirement is not tested" in summary
    assert "trend_by_snapshot" not in json.loads((out / "study.json").read_text(encoding="utf-8"))["tables"]
    cuts = (out / "press" / "state_cuts.md").read_text(encoding="utf-8")
    assert cuts.startswith("# State cuts:") and "At or above all three floors" in cuts or "fewer than 10" in cuts
    assert cuts.count("\n## ") == len(states)
    site = json.loads((out / "site" / "staffing.json").read_text(encoding="utf-8"))
    assert site["study"] == "staffing" and site["floors"] == {"rn": 0.55, "aide": 2.45, "total": 3.48}
    assert site["tables"]["national_summary"][0]["facilities"] == int(national["facilities"])


def test_staffing_history_tables(release, two_snapshots, tmp_path: Path):
    from tcr_open_data.history import backfill, consolidate

    _raw, release_dir = release
    history_dir, snapshots, openers = two_snapshots
    backfill(history_dir, snapshots, zip_opener=lambda url: zipfile.ZipFile(openers[url]), progress=lambda *_: None)
    consolidate(history_dir)
    meta = run_study(release_dir, tmp_path / "staffing", history_dir=history_dir)
    assert meta["history_store"] is True
    trend = _read(tmp_path / "staffing" / "trend_by_snapshot.csv")
    assert [r["snapshot_date"] for r in trend] == ["2019-01-17", "2026-08-26"]
    assert (tmp_path / "staffing" / "trend_by_ownership_year.csv").exists() and (tmp_path / "staffing" / "state_change.csv").exists()
