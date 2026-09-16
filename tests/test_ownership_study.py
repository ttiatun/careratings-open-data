"""The ownership study runs end to end on the fixture release and writes every table."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from tcr_open_data.ownership_study import ROLE_FAMILIES, pct, role_family, run_study
from test_history import two_snapshots  # noqa: F401  (fixture: a tiny history store)
from test_release import release  # noqa: F401  (fixture: the built fixture release)


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_pct():
    assert pct(1, 4) == 25.0 and pct(0, 4) == 0.0 and pct(None, 4) is None and pct(3, 0) is None


def test_role_families_absorb_cms_relabels():
    assert role_family("DIRECTOR") == role_family("Corporate Director ") == ("Corporate director", True)
    assert role_family("MANAGING EMPLOYEE")[0] == role_family("W-2 MANAGING EMPLOYEE")[0] == role_family("CONTRACTED MANAGING EMPLOYEE")[0]
    assert role_family("5% OR GREATER DIRECT OWNERSHIP INTEREST") == role_family("DIRECT OWNERSHIP INTEREST")
    assert role_family("ADP OF THE SNF")[1] is False, "2026-only categories are not comparable with 2019"
    assert role_family("SOMETHING NEW") == ("Something New", False) and role_family(None) == ("Unknown", False)
    families = {family for family, _c in ROLE_FAMILIES.values()}
    assert {"Direct ownership interest", "Indirect ownership interest", "Corporate director", "Corporate officer", "Managing employee"} <= families


def test_study_writes_tables_and_summary(release, tmp_path: Path):
    _raw, release_dir = release
    out = tmp_path / "study"
    meta = run_study(release_dir, out, history_dir=None)
    assert meta["release"] == release_dir.name and meta["history_store"] is False
    for name in ("national_summary", "by_state", "owner_vs_party", "quality_by_disclosure", "quality_by_disclosure_for_profit",
                 "top_private_equity_owners", "top_reit_parties", "chains_with_disclosures", "chow_by_year", "chow_by_state", "discrepancy_register"):
        assert (out / f"{name}.csv").exists(), name
        assert name in meta["tables"]
    national = _read(out / "national_summary.csv")[0]
    assert national["release"] == release_dir.name
    assert int(national["facilities"]) > 0
    assert int(national["pe_owner_facilities"]) <= int(national["pe_party_facilities"]), "owner roles are a subset of all parties"
    owner_vs_party = {r["flag"]: r for r in _read(out / "owner_vs_party.csv")}
    assert set(owner_vs_party) == {"Private equity", "REIT"}
    for row in owner_vs_party.values():
        assert int(row["owner_role_facilities"]) + int(row["party_only_facilities"]) == int(row["any_role_facilities"])
    groups = {r["disclosure_group"] for r in _read(out / "quality_by_disclosure.csv")}
    assert groups <= {"Discloses a private-equity owner", "Discloses a REIT owner", "PE or REIT among other disclosable parties only", "No PECOS enrollment matched", "No PE or REIT disclosure"}
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert summary.startswith(f"# Ownership study tables, release {release_dir.name}")
    assert "as disclosed to CMS" in summary and "Discrepancy register seeds" in summary
    study = json.loads((out / "study.json").read_text(encoding="utf-8"))
    assert study["tables"]["by_state"]["rows"] >= 1
    assert "ownership_change_trend" not in study["tables"], "history tables only when a history store is given"


def test_study_uses_the_history_store_when_present(release, two_snapshots, tmp_path: Path):
    import zipfile

    from tcr_open_data.history import backfill, consolidate

    _raw, release_dir = release
    history_dir, snapshots, openers = two_snapshots
    backfill(history_dir, snapshots, zip_opener=lambda url: zipfile.ZipFile(openers[url]), progress=lambda *_: None)
    consolidate(history_dir)
    meta = run_study(release_dir, tmp_path / "study", history_dir=history_dir)
    assert meta["history_store"] is True
    trend = _read(tmp_path / "study" / "ownership_change_trend.csv")
    assert [r["snapshot_date"] for r in trend] == ["2019-01-17", "2026-08-26"]
    turnover = _read(tmp_path / "study" / "carecompare_owner_turnover.csv")
    assert turnover and set(turnover[0]) == {"year", "owner_names_first_seen", "organizations", "individuals", "facilities_with_a_new_name", "note"}
    by_family = _read(tmp_path / "study" / "carecompare_owner_turnover_by_family.csv")
    assert sum(int(r["owner_names_first_seen"]) for r in by_family) == sum(int(r["owner_names_first_seen"]) for r in turnover), "a name counts once per family it first appears in"
    labels = _read(tmp_path / "study" / "carecompare_role_labels.csv")
    assert labels and all(r["comparable_since_2019"] in {"true", "false", "True", "False"} for r in labels)
    assert "Care Compare renamed its role labels" in (tmp_path / "study" / "summary.md").read_text(encoding="utf-8")
