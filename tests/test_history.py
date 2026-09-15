"""Historical backfill: synonym mapping across CMS column eras, member selection, and consolidation."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import duckdb
import pytest

from tcr_open_data.history import (
    FACILITY_COLUMNS, OWNERSHIP_COLUMNS, PENALTY_COLUMNS, Snapshot, backfill, consolidate, header_era, list_snapshots,
    resolve_columns, select_member,
)

ERA1_PROVIDER = ["PROVNUM", "PROVNAME", "ADDRESS", "CITY", "STATE", "ZIP", "PHONE", "COUNTY_SSA", "COUNTY_NAME", "OWNERSHIP", "BEDCERT", "RESTOT",
                 "CERTIFICATION", "INHOSP", "LBN", "PARTICIPATION_DATE", "CCRC_FACIL", "SFF", "OLDSURVEY", "CHOW_LAST_12MOS", "RESFAMCOUNCIL",
                 "SPRINKLER_STATUS", "OVERALL_RATING", "overall_rating_fn", "SURVEY_RATING", "survey_rating_fn", "QUALITY_RATING", "quality_rating_fn",
                 "STAFFING_RATING", "staffing_rating_fn", "RN_STAFFING_RATING", "RN_staffing_rating_fn", "AIDHRD", "VOCHRD", "RNHRD", "TOTLICHRD", "TOTHRD",
                 "PTHRD", "ADJ_AIDE", "ADJ_LPN", "ADJ_RN", "ADJ_TOTAL", "WEIGHTED_ALL_CYCLES_SCORE", "INCIDENT_CNT", "CMPLNT_CNT", "FINE_CNT", "FINE_TOT",
                 "PAYDEN_CNT", "TOT_PENLTY_CNT", "FILEDATE"]
ERA2_PROVIDER = ["Federal Provider Number", "Provider Name", "Provider Address", "Provider City", "Provider State", "Provider Zip Code", "Ownership Type",
                 "Number of Certified Beds", "Special Focus Status", "Abuse Icon", "Overall Rating", "Health Inspection Rating", "QM Rating", "Staffing Rating",
                 "Reported RN Staffing Hours per Resident per Day", "Reported Total Nurse Staffing Hours per Resident per Day", "Number of Fines",
                 "Total Amount of Fines in Dollars", "Total Number of Penalties", "Processing Date"]
ERA3_PROVIDER = ["CMS Certification Number (CCN)", "Provider Name", "Provider Address", "City/Town", "State", "ZIP Code", "Ownership Type",
                 "Number of Certified Beds", "Chain ID", "Chain Name", "Special Focus Status", "Abuse Icon", "Overall Rating", "Health Inspection Rating",
                 "QM Rating", "Staffing Rating", "Reported RN Staffing Hours per Resident per Day", "Reported Total Nurse Staffing Hours per Resident per Day",
                 "Number of Fines", "Total Amount of Fines in Dollars", "Total Number of Penalties", "Processing Date"]


def test_header_era_detection():
    assert header_era(ERA1_PROVIDER) == 1 and header_era(ERA2_PROVIDER) == 2 and header_era(ERA3_PROVIDER) == 3


def test_resolve_columns_across_eras_is_case_insensitive():
    for header, expect_ccn in ((ERA1_PROVIDER, "PROVNUM"), (ERA2_PROVIDER, "Federal Provider Number"), (ERA3_PROVIDER, "CMS Certification Number (CCN)")):
        mapping, unmapped, unused = resolve_columns(header, FACILITY_COLUMNS)
        assert mapping["ccn"] == expect_ccn and mapping["overall_rating"] and mapping["total_fines_dollars"]
        assert "processing_date" in mapping
    era1_mapping, era1_unmapped, _ = resolve_columns(ERA1_PROVIDER, FACILITY_COLUMNS)
    assert era1_mapping["special_focus_status"] == "SFF" and "abuse_icon" in era1_unmapped and "chain_id" in era1_unmapped
    mixed_case = [h.title() for h in ERA1_PROVIDER]
    assert resolve_columns(mixed_case, FACILITY_COLUMNS)[0]["ccn"] == "Provnum"
    pen_mapping, _, _ = resolve_columns(["provnum", "pnlty_date", "pnlty_type", "fine_amt", "payden_strt_dt", "payden_days", "filedate"], PENALTY_COLUMNS)
    assert pen_mapping["penalty_date"] == "pnlty_date" and "fine_id" not in pen_mapping
    own_mapping, _, _ = resolve_columns(["PROVNUM", "ROLE_DESC", "OWNER_TYPE", "OWNER_NAME", "OWNER_PERCENTAGE", "ASSOCIATION_DATE", "filedate"], OWNERSHIP_COLUMNS)
    assert own_mapping["role"] == "ROLE_DESC"


def test_select_member_handles_old_and_new_names_and_folders():
    old = ["DataMedicareGov_MetadataAllTabs_v18.xlsx", "Ownership_Download.csv", "Penalties_Download.csv", "ProviderInfo_Download.csv"]
    new = ["nursing-homes_2026-07-29/", "__MACOSX/nursing-homes_2026-07-29/._4pq5-n9py_2026-07-01_NH_ProviderInfo_Jul2026.csv",
           "nursing-homes_2026-07-29/4pq5-n9py_2026-07-01_NH_ProviderInfo_Jul2026.csv", "nursing-homes_2026-07-29/g6vv-u9sr_2026-07-01_NH_Penalties_Jul2026.csv",
           "nursing-homes_2026-07-29/y2hd-n93e_2026-07-01_NH_Ownership_Jul2026.csv", "nursing-homes_2026-07-29/NH_Data_Dictionary.pdf"]
    mid = ["nursing_homes_including_rehab_services_12_2021/NH_ProviderInfo_Nov2021.csv", "nursing_homes_including_rehab_services_12_2021/NH_Penalties_Nov2021.csv"]
    assert select_member(old, "provider_info") == "ProviderInfo_Download.csv" and select_member(old, "ownership") == "Ownership_Download.csv"
    assert select_member(new, "provider_info") == "nursing-homes_2026-07-29/4pq5-n9py_2026-07-01_NH_ProviderInfo_Jul2026.csv"
    assert select_member(new, "penalties").endswith("NH_Penalties_Jul2026.csv")
    assert select_member(mid, "provider_info").endswith("NH_ProviderInfo_Nov2021.csv") and select_member(mid, "ownership") is None


def test_list_snapshots_skips_annual_bundles_and_sorts():
    index = {"data": [
        {"date": "2026-08-26", "type": "theme", "url": "/a/nursing-homes_2026-08-26.zip", "size": "1", "name": "Theme: nursing-homes (2026-08-26)"},
        {"date": "2026-08-26", "type": "annual_theme", "url": "/a/nursing-homes_annual_2026.zip", "size": "9", "name": "Annual"},
        {"date": "2019-01-17", "type": "theme", "url": "/a/nursing-homes_2019-01-17.zip", "size": "2", "name": "Theme: nursing-homes (2019-01-17) Snapshot"},
    ]}
    snaps = list_snapshots(index_json=index)
    assert [s.date for s in snaps] == ["2019-01-17", "2026-08-26"] and snaps[0].url.startswith("https://data.cms.gov/a/")


def _csv_bytes(header: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header)
    writer.writeheader()
    for r in rows:
        writer.writerow({h: r.get(h, "") for h in header})
    return buf.getvalue().encode("utf-8")


def _make_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


@pytest.fixture
def two_snapshots(tmp_path: Path) -> tuple[Path, list[Snapshot], dict]:
    era1 = _csv_bytes(ERA1_PROVIDER, [
        {"PROVNUM": "15009", "PROVNAME": "BURNS NURSING HOME", "STATE": "AL", "OWNERSHIP": "For profit - Corporation", "BEDCERT": "57", "SFF": "N",
         "OVERALL_RATING": "5", "STAFFING_RATING": "4", "RNHRD": "0.5", "TOTHRD": "3.1", "FINE_CNT": "1", "FINE_TOT": "6,500", "TOT_PENLTY_CNT": "1", "FILEDATE": "2019-01-01"},
        {"PROVNUM": "015010", "PROVNAME": "CLOSED HOME", "STATE": "AL", "OVERALL_RATING": "1", "FILEDATE": "2019-01-01"},
    ])
    era1_pen = _csv_bytes(["provnum", "provname", "pnlty_date", "pnlty_type", "fine_amt", "payden_strt_dt", "payden_days", "filedate"], [
        {"provnum": "15009", "pnlty_date": "2018-06-01", "pnlty_type": "Fine", "fine_amt": "6500", "filedate": "2019-01-01"},
    ])
    era1_own = _csv_bytes(["PROVNUM", "ROLE_DESC", "OWNER_TYPE", "OWNER_NAME", "OWNER_PERCENTAGE", "ASSOCIATION_DATE", "filedate"], [
        {"PROVNUM": "15009", "ROLE_DESC": "5% OR GREATER DIRECT OWNERSHIP INTEREST", "OWNER_TYPE": "Individual", "OWNER_NAME": "DEARMAN, MARTHA", "OWNER_PERCENTAGE": "81%", "ASSOCIATION_DATE": "since 09/01/1969", "filedate": "2019-01-01"},
    ])
    era3 = _csv_bytes(ERA3_PROVIDER, [
        {"CMS Certification Number (CCN)": "015009", "Provider Name": "BURNS NURSING HOME, INC.", "State": "AL", "Ownership Type": "For profit - Corporation",
         "Number of Certified Beds": "57", "Chain ID": "", "Special Focus Status": "SFF Candidate", "Abuse Icon": "N", "Overall Rating": "2", "Staffing Rating": "3",
         "Reported RN Staffing Hours per Resident per Day": "0.7", "Reported Total Nurse Staffing Hours per Resident per Day": "3.6",
         "Number of Fines": "2", "Total Amount of Fines in Dollars": "19000", "Total Number of Penalties": "2", "Processing Date": "2026-08-01"},
    ])
    era3_pen = _csv_bytes(["CMS Certification Number (CCN)", "Penalty Date", "Penalty Type", "Fine ID", "Fine Amount", "Payment Denial Start Date", "Payment Denial Length in Days", "Processing Date"], [
        {"CMS Certification Number (CCN)": "015009", "Penalty Date": "2018-06-01", "Penalty Type": "Fine", "Fine ID": "77", "Fine Amount": "6500", "Processing Date": "2026-08-01"},
        {"CMS Certification Number (CCN)": "015009", "Penalty Date": "2025-03-01", "Penalty Type": "Fine", "Fine ID": "78", "Fine Amount": "12500", "Processing Date": "2026-08-01"},
    ])
    era3_own = _csv_bytes(["CMS Certification Number (CCN)", "Role played by Owner or Manager in Facility", "Owner Type", "Owner Name", "Ownership Percentage", "Association Date", "Processing Date"], [
        {"CMS Certification Number (CCN)": "015009", "Role played by Owner or Manager in Facility": "5% OR GREATER DIRECT OWNERSHIP INTEREST", "Owner Type": "Individual",
         "Owner Name": "DEARMAN, MARTHA", "Ownership Percentage": "81%", "Association Date": "since 09/01/1969", "Processing Date": "2026-08-01"},
        {"CMS Certification Number (CCN)": "015009", "Role played by Owner or Manager in Facility": "MANAGING EMPLOYEE", "Owner Type": "Individual",
         "Owner Name": "NEW, ADMIN", "Ownership Percentage": "NO PERCENTAGE PROVIDED", "Association Date": "since 01/01/2025", "Processing Date": "2026-08-01"},
    ])
    zips = {"2019-01-17": tmp_path / "old.zip", "2026-08-26": tmp_path / "new.zip"}
    _make_zip(zips["2019-01-17"], {"ProviderInfo_Download.csv": era1, "Penalties_Download.csv": era1_pen, "Ownership_Download.csv": era1_own, "Other.csv": b"a\n1\n"})
    _make_zip(zips["2026-08-26"], {"4pq5-n9py_2026-08-01_NH_ProviderInfo_Aug2026.csv": era3, "g6vv-u9sr_2026-08-01_NH_Penalties_Aug2026.csv": era3_pen,
                                   "y2hd-n93e_2026-08-01_NH_Ownership_Aug2026.csv": era3_own, "manifest.json": b"{}"})
    snapshots = [Snapshot(d, f"file://{p}", p.stat().st_size, d) for d, p in zips.items()]
    openers = {f"file://{p}": p for p in zips.values()}
    return tmp_path / "history", snapshots, openers


def test_backfill_and_consolidate_across_eras(two_snapshots):
    history_dir, snapshots, openers = two_snapshots
    opener = lambda url: zipfile.ZipFile(openers[url])
    coverage = backfill(history_dir, snapshots, zip_opener=opener, progress=lambda *_: None)
    assert {(r["snapshot_date"], r["table"]) for r in coverage} == {(s.date, t) for s in snapshots for t in ("provider_info", "penalties", "ownership")}
    era1 = next(r for r in coverage if r["snapshot_date"] == "2019-01-17" and r["table"] == "provider_info")
    assert era1["header_era"] == 1 and "abuse_icon" in era1["unmapped_canonical"] and era1["rows"] == 2
    manifest = consolidate(history_dir)
    assert manifest["snapshots"] == {"count": 2, "first": "2019-01-17", "last": "2026-08-26"}

    con = duckdb.connect()
    q = lambda name: (history_dir / name).as_posix()
    fac = con.execute(f"SELECT snapshot_date, ccn, overall_rating, total_fines_dollars, special_focus_status, header_era FROM read_parquet('{q('facilities_history.parquet')}') ORDER BY snapshot_date, ccn").fetchall()
    assert [(str(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in fac] == [
        ("2019-01-17", "015009", 5, 6500.0, "N", 1), ("2019-01-17", "015010", 1, None, None, 1), ("2026-08-26", "015009", 2, 19000.0, "SFF Candidate", 3)]
    pen = con.execute(f"SELECT ccn, penalty_date, fine_amount, fine_id, first_seen_snapshot, last_seen_snapshot, snapshots_seen FROM read_parquet('{q('penalties_history.parquet')}') ORDER BY penalty_date").fetchall()
    assert [(r[0], str(r[1]), r[2], r[3], str(r[4]), str(r[5]), r[6]) for r in pen] == [
        ("015009", "2018-06-01", 6500.0, "77", "2019-01-17", "2026-08-26", 2), ("015009", "2025-03-01", 12500.0, "78", "2026-08-26", "2026-08-26", 1)]
    own = con.execute(f"SELECT owner_name, first_seen_snapshot, last_seen_snapshot, snapshots_seen, latest_ownership_percentage_raw FROM read_parquet('{q('ownership_history.parquet')}') ORDER BY owner_name").fetchall()
    assert [(r[0], str(r[1]), str(r[2]), r[3], r[4]) for r in own] == [("DEARMAN, MARTHA", "2019-01-17", "2026-08-26", 2, "81%"), ("NEW, ADMIN", "2026-08-26", "2026-08-26", 1, "NO PERCENTAGE PROVIDED")]
    raw_cols = [d[0] for d in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{q('raw/provider_info/2019-01-17.parquet')}')").fetchall()]
    assert raw_cols[:3] == ["snapshot_date", "PROVNUM", "PROVNAME"], "raw copies keep the original CMS headers"
    coverage_csv = (history_dir / "coverage.csv").read_text(encoding="utf-8")
    assert "2019-01-17,provider_info,True,2,1" in coverage_csv
    assert (history_dir / "manifest.json").exists() and json.loads((history_dir / "manifest.json").read_text())["tables"]["penalties_history"]["earliest_penalty_date"] == "2018-06-01"


def test_backfill_is_resumable_and_records_failures(two_snapshots):
    history_dir, snapshots, openers = two_snapshots
    calls = []

    def opener(url):
        calls.append(url)
        if url.endswith("new.zip"):
            raise OSError("network down")
        return zipfile.ZipFile(openers[url])

    coverage = backfill(history_dir, snapshots, zip_opener=opener, progress=lambda *_: None)
    failed = [r for r in coverage if r.get("error")]
    assert len(failed) == 3 and all(r["snapshot_date"] == "2026-08-26" for r in failed)
    calls.clear()
    backfill(history_dir, snapshots, zip_opener=lambda url: zipfile.ZipFile(openers[url]), progress=lambda *_: None)
    assert calls == [], "snapshots recorded in coverage.jsonl are not reopened when resuming"
