"""CCN matching for SFF rows that print no CCN."""

from __future__ import annotations

from pathlib import Path

import duckdb

from tcr_open_data.sff import name_tokens, resolve_ccns, similar_name


def test_name_tokens_drop_generic_words():
    assert name_tokens("The Gardens At West Shore Nursing & Rehab Center, LLC") == {"GARDENS", "WEST", "SHORE"}


def test_similar_name_requires_a_clear_winner():
    candidates = {"1": {"GARDENS AT WEST SHORE"}, "2": {"CAMP HILL REHABILITATION CENTER"}}
    assert similar_name("The Gardens At West Shore", candidates) == "1"
    assert similar_name("Camp Hill Gardens", candidates) == "2"
    assert similar_name("West Shore", {"1": {"WEST SHORE GARDENS"}, "2": {"WEST SHORE MANOR"}}) is None, "an exact tie between two candidates is not a match"
    assert similar_name("Sunrise Manor", candidates) is None


def test_resolve_ccns_falls_back_to_similar_name_within_zip(tmp_path: Path):
    parquet = tmp_path / "facilities_history.parquet"
    con = duckdb.connect()
    con.execute(f"""COPY (SELECT * FROM (VALUES ('395001', 'GARDENS AT WEST SHORE', 'PA', '17011'), ('395002', 'CAMP HILL REHABILITATION CENTER', 'PA', '17011'),
                    ('395003', 'WEST SHORE HOSPITAL SNF', 'PA', '17011')) t(ccn, provider_name, state, zip_code)) TO '{parquet.as_posix()}' (FORMAT PARQUET)""")
    con.close()
    rows = [{"ccn": None, "facility_name": "The Gardens At West Shore", "state": "PA", "zip_code": "17011"},
            {"ccn": None, "facility_name": "Willow Terrace", "state": "PA", "zip_code": "17011"}]
    counts = resolve_ccns(rows, parquet)
    assert rows[0]["ccn"] == "395001" and rows[0]["ccn_match"] == "state_zip_name_similar"
    assert rows[1]["ccn"] is None and rows[1]["ccn_match"] == "unmatched"
    assert counts["state_zip_name_similar"] == 1 and counts["unmatched"] == 1
