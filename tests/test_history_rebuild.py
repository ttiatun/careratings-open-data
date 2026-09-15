"""History store: member-name variants, synonym additions, re-harmonizing from raw Parquet, coverage merging."""

from __future__ import annotations

import json
import shutil
import zipfile

import duckdb

from tcr_open_data.history import FACILITY_COLUMNS, backfill, consolidate, load_coverage, reharmonize, resolve_columns, select_member


def test_select_member_accepts_names_without_a_month_suffix():
    names = ["NH_Ownership.csv", "NH_Penalties.csv", "NH_ProviderInfo.csv", "Skilled_Nursing_Facility_Quality_Reporting_Program_Provider_Data_Oct2020.csv"]
    assert select_member(names, "provider_info") == "NH_ProviderInfo.csv"
    assert select_member(names, "penalties") == "NH_Penalties.csv"
    assert select_member(names, "ownership") == "NH_Ownership.csv"
    assert select_member(["4pq5-n9py_2026-07-29_NH_ProviderInfo_Jul2026.csv"], "penalties") is None, "a partial re-publication has no penalties file"


def test_affiliated_entity_and_case_mix_synonyms():
    header = ["CMS Certification Number (CCN)", "Affiliated Entity Name", "Affiliated Entity ID", "Telephone Number",
              "Case-Mix Total Nurse Staffing Hours per Resident per Day", "Rating Cycle 1 Total Health Score", "Processing Date"]
    mapping, _unmapped, unused = resolve_columns(header, FACILITY_COLUMNS)
    assert mapping["chain_id"] == "Affiliated Entity ID" and mapping["chain_name"] == "Affiliated Entity Name" and mapping["phone"] == "Telephone Number"
    assert mapping["case_mix_total_nurse_hprd"].startswith("Case-Mix Total") and mapping["cycle1_total_health_score"] == "Rating Cycle 1 Total Health Score"
    assert unused == []
    era1, _, _ = resolve_columns(["PROVNUM", "CM_TOTAL", "cycle_1_defs", "CYCLE_1_SURVEY_DATE", "FILEDATE"], FACILITY_COLUMNS)
    assert era1["case_mix_total_nurse_hprd"] == "CM_TOTAL" and era1["cycle1_health_deficiencies"] == "cycle_1_defs" and era1["cycle1_survey_date"] == "CYCLE_1_SURVEY_DATE"


def test_reharmonize_rebuilds_from_raw_and_merges_coverage(two_snapshots):
    history_dir, snapshots, openers = two_snapshots
    backfill(history_dir, snapshots, zip_opener=lambda url: zipfile.ZipFile(openers[url]), progress=lambda *_: None)
    shutil.rmtree(history_dir / "harmonized")
    with (history_dir / "coverage.jsonl").open("a", encoding="utf-8") as handle:  # a stale duplicate record, as a re-run would leave
        handle.write(json.dumps({"snapshot_date": "2019-01-17", "table": "provider_info", "rows": 999, "header_era": 1, "source_columns": 0,
                                 "mapped": 0, "unmapped_canonical": [], "unused_source": [], "member": "ProviderInfo_Download.csv"}) + "\n")

    coverage = reharmonize(history_dir, progress=lambda *_: None)
    assert len(coverage) == 6 and len(load_coverage(history_dir)) == 6, "coverage.jsonl is rewritten with one record per snapshot and table"
    era1 = next(r for r in coverage if r["snapshot_date"] == "2019-01-17" and r["table"] == "provider_info")
    assert era1["rows"] == 2 and era1["processing_date"] == "2019-01-01" and era1["member"] == "ProviderInfo_Download.csv"

    manifest = consolidate(history_dir)
    assert manifest["tables"]["facilities_history"]["rows"] == 3 and manifest["coverage"]["missing_files"] == []
    con = duckdb.connect()
    cols = [d[0] for d in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{(history_dir / 'facilities_history.parquet').as_posix()}')").fetchall()]
    assert "phone" in cols and "case_mix_total_nurse_hprd" in cols and cols[-1] == "processing_date"
    lines = (history_dir / "coverage.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].endswith(",error,processing_date") and sum(1 for l in lines if l.startswith("2019-01-17,provider_info,")) == 1
    assert next(l for l in lines if l.startswith("2019-01-17,provider_info,")).endswith(",2019-01-01")

from test_history import two_snapshots  # noqa: E402,F401  (fixture shared with test_history.py)
