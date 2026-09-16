"""Chain profile files: one JSON per chain plus an index, consistent with the release tables."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from tcr_open_data.chain_profiles import chain_path, chain_slug, write_chain_profiles
from tcr_open_data.ownership_study import register_views, run_study
from tcr_open_data.storage import analysis_pointer, cache_control, plan_analysis_uploads
from test_release import release  # noqa: F401  (fixture: the built fixture release)


def test_chain_slug_and_path():
    assert chain_slug("THE ENSIGN GROUP") == "the-ensign-group"
    assert chain_slug("NEW YORK CITY HEALTH + HOSPITALS") == "new-york-city-health-hospitals"
    long = chain_slug("CONSULATE HEALTH CARE/INDEPENDENCE LIVING CENTERS/NSPIRE HEALTHCARE/RAYDIANT HEALTH CARE")
    assert long.startswith("consulate-health-care-") and len(long) <= 60 and not long.endswith("-")
    assert len(chain_slug("x" * 200)) <= 60 and chain_slug("") == "chain" and chain_slug(None) == "chain"
    assert chain_path("507", "THE ENSIGN GROUP") == "/data/chains/507-the-ensign-group/"


def test_chain_profiles_match_the_release(release, tmp_path: Path):
    _raw, release_dir = release
    con = duckdb.connect()
    ctx = register_views(con, release_dir, None)
    result = write_chain_profiles(con, tmp_path / "site", ctx["manifest"])
    index = json.loads((tmp_path / "site" / "chains" / "index.json").read_text(encoding="utf-8"))
    assert index["release"] == release_dir.name and index["national"]["chain_id"] == "NATIONAL"
    assert result["chains"] == len(index["chains"]) and all(c["chain_id"] != "NATIONAL" for c in index["chains"])
    chained = con.execute("SELECT COUNT(*) FROM facilities WHERE chain_id IS NOT NULL").fetchone()[0]
    assert index["chained_facilities_in_release"] == chained
    for entry in index["chains"]:
        profile = json.loads((tmp_path / "site" / "chains" / f"{entry['chain_id']}.json").read_text(encoding="utf-8"))
        assert profile["chain"]["path"] == entry["path"] == chain_path(entry["chain_id"], entry["chain_name"])
        assert len(profile["facilities"]) == entry["facilities_in_release"]
        assert sum(s["facilities"] for s in profile["states"]) == entry["facilities_in_release"]
        assert profile["disclosures"]["pe_owner_facilities"] == sum(1 for f in profile["facilities"] if f["has_private_equity_owner"])
        assert set(profile["ratings"]) == {"rating_1", "rating_2", "rating_3", "rating_4", "rating_5", "rated_facilities"}
        assert profile["release"] == release_dir.name and profile["national"]["chain_id"] == "NATIONAL"
    con.close()


def test_study_writes_site_files_and_publish_plan(release, tmp_path: Path):
    _raw, release_dir = release
    out = tmp_path / "analysis" / "ownership" / release_dir.name
    meta = run_study(release_dir, out, history_dir=None)
    assert meta["tables"]["site/chains"]["rows"] >= 1
    assert (out / "site" / "chains" / "index.json").exists()
    uploads = plan_analysis_uploads(out)
    keys = [key for _p, key in uploads]
    assert f"analysis/ownership/{release_dir.name}/summary.md" in keys
    assert f"analysis/ownership/{release_dir.name}/site/chains/index.json" in keys
    assert all(key.startswith(f"analysis/ownership/{release_dir.name}/") for key in keys)
    assert cache_control(keys[0]) == "public, max-age=300, must-revalidate"
    pointer_key, pointer = analysis_pointer(out)
    assert pointer_key == "analysis/ownership/latest.json"
    assert pointer["release"] == release_dir.name and pointer["path"] == f"analysis/ownership/{release_dir.name}/"
    assert "site/chains" in pointer["tables"]
