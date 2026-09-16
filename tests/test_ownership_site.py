"""Ownership site files: the state layers, the headline tables and the discrepancy register as JSON."""

from __future__ import annotations

import json
from pathlib import Path

from tcr_open_data.ownership_site import DISCREPANCY_ISSUES, SMALL_STATE
from tcr_open_data.ownership_study import run_study
from tcr_open_data.storage import plan_analysis_uploads
from test_release import release  # noqa: F401  (fixture: the built fixture release)


def test_ownership_site_files(release, tmp_path: Path):
    _raw, release_dir = release
    out = tmp_path / "analysis" / "ownership" / release_dir.name
    meta = run_study(release_dir, out, history_dir=None)
    assert meta["tables"]["site/ownership"]["rows"] >= 1
    ownership = json.loads((out / "site" / "ownership.json").read_text(encoding="utf-8"))
    assert ownership["release"] == release_dir.name and ownership["small_state_threshold"] == SMALL_STATE
    assert ownership["national"]["facilities"] == sum(s["facilities"] for s in ownership["states"])
    for s in ownership["states"]:
        assert s["suppressed"] == (s["facilities"] < SMALL_STATE)
        assert 0 <= s["for_profit_pct"] <= 100 and 0 <= s["pe_owner_pct"] <= 100
    assert {r["flag"] for r in ownership["owner_vs_party"]} == {"Private equity", "REIT"}
    assert [c["issue"] for c in ownership["discrepancy_counts"]] == [i["issue"] for i in DISCREPANCY_ISSUES]
    assert sum(c["facilities"] for c in ownership["discrepancy_by_category"]) == sum(c["facilities"] for c in ownership["discrepancy_counts"])
    assert isinstance(ownership["chains_with_disclosures"], list) and isinstance(ownership["carecompare_owner_turnover"], list)

    register = json.loads((out / "site" / "discrepancy_register.json").read_text(encoding="utf-8"))
    counted = {i["issue"]: i["facilities"] for i in register["issues"]}
    for issue in {r["issue"] for r in register["rows"]}:
        assert counted[issue] == sum(1 for r in register["rows"] if r["issue"] == issue)
    assert all(set(r) == {"issue", "ccn", "provider_name", "state", "ownership_category", "chain_name", "detail"} for r in register["rows"])

    # Study-level JSON beside the runs (the state law tracker) is published under analysis/<study>/.
    (out.parent / "state_laws.json").write_text("{}", encoding="utf-8")
    keys = [key for _p, key in plan_analysis_uploads(out)]
    assert "analysis/ownership/state_laws.json" in keys
    assert f"analysis/ownership/{release_dir.name}/site/ownership.json" in keys
