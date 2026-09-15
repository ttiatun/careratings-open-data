"""Special Focus Facility PDF parsing."""

from __future__ import annotations

from pathlib import Path

import duckdb

from tcr_open_data.sff import Capture, glue_lines, list_captures, parse_lines, parse_pages, resolve_ccns, split_name_address

MODERN = [
    "Special Focus Facility (SFF) Program",
    "Table A – Current SFF Facilities: Nursing homes that are currently in the SFF",
    "Table D – SFF Candidate list: These are nursing homes that qualify to be selected as",
    "Table A: Current SFF Facilities",
    "Updated March 29, 2023",
    "Provider",
    "Number Facility Name Address City State Zip",
    "345420 Alamance Health Care Center 1987 Hilton Road Burlington NC 27217 336-226-0848 09/19/2022 Not Met 6",
    "315280 Silver Healthcare Center 1417 Brace Road Cherry Hill NJ 08034 856-795-3131 5",
    "045287 Bear Creek Healthcare Llc 322 West Collin Raye Drive De Queen AR 71832 870-642-3562 3",
    "Table D: SFF Candidate List",
] + [f"{100000 + i:06d} Candidate Home {i} 10 Main St Town TX 75001" for i in range(20)]


def test_parse_modern_edition_rows_and_tables():
    parsed = parse_lines(MODERN)
    assert parsed.layout == "rows" and parsed.edition_date == "2023-03-29"
    assert parsed.tables == {"A": "Current SFF Facilities", "D": "SFF Candidate List"}
    a = [r for r in parsed.rows if r["table_code"] == "A"]
    assert len(a) == 3 and len(parsed.rows) == 23
    first = a[0]
    assert first["ccn"] == "345420" and first["facility_name"] == "Alamance Health Care Center"
    assert first["address_city"] == "1987 Hilton Road Burlington" and first["state"] == "NC" and first["zip_code"] == "27217"
    assert first["phone"] == "336-226-0848" and first["most_recent_inspection"] == "2022-09-19" and first["met_survey_criteria"] is False and first["months_as_sff"] == 6
    second = a[1]
    assert second["most_recent_inspection"] is None and second["met_survey_criteria"] is None and second["months_as_sff"] == 5
    assert a[2]["facility_name"] == "Bear Creek Healthcare Llc" and a[2]["address_city"] == "322 West Collin Raye Drive De Queen"


INTRO_PAGE = [
    "Special Focus Facility (SFF) Program",
    "Table A - New Additions:  These are nursing homes newly added to the SFF initiative (but",
    "which have not yet had a standard survey since being added to the list).",
    "B. Table B – Not Improved: Nursing homes that have failed to show significant",
]
PAGE_A_FOOTER = [
    "Updated January 27, 2021",
    "Facility Name Addre ss City State Zip", "Phone ", "Number", "Months as an ", "SFF",
    "Estrella Center 350 East La Canada Avondale AZ 85323 623-932-2282 10",
    "Marshwood Center 33 Roger Street Lewiston ME 04240 207-784-0108 14",
    "Grove At North Huntingdon, The 249 Maus Drive North Huntingdon PA 15642 724-863-4374 3",
    "Table A: Facilities Newly Added to the SFF Program",
    "1",
]
PAGE_B_FOOTER = [
    "Facility Name Address City State Zip", "Phone ", "Number", "Most Recent ", "Inspection", "Months as an ", "SFF",
    "Golden Living Center - Trussville 119 Watterson Parkway Trussville AL 35173 205-655-3226 03/01/2012 7",
    "Haven Home P O Box 10, 100 West Elm Avenue Kenesaw NE 68956 402-752-3212 06/11/2012 6",
    "Table B: Facilities That Have Not Improved",
    "2",
]
PAGE_F_HEADER = [
    "Facility Name Address City State Zip", "Phone ", "Number", "Months as an ", "SFF Candidate",
    "Table F: SFF Candidate List",
    "VAN DUYN CENTER FOR REHABILITATION AND NURSING 5075 WEST SENECA TURNPIKE SYRACUSE NY 13215 315-449-6000 5",
    "WESLEY GARDENS CORPORATION 3 UPTON PARK ROCHESTER NY 14607 585-685-2525 26",
]
PAGE_F_CONTINUED = [
    "Facility Name Address City State Zip", "Phone ", "Number",
    "AMBERWOOD MANOR 245 SOUTH BROADWAY NEW PHILADELPHIA OH 44663 (330) 339-2151 6",
]


def test_parse_edition_without_ccns_uses_page_labels_above_or_below_rows():
    parsed = parse_pages([INTRO_PAGE, PAGE_A_FOOTER, PAGE_B_FOOTER, PAGE_F_HEADER, PAGE_F_CONTINUED])
    assert parsed.layout == "rows_no_ccn" and parsed.edition_date == "2021-01-27"
    assert parsed.tables == {"A": "Facilities Newly Added to the SFF Program", "B": "Facilities That Have Not Improved", "F": "SFF Candidate List"}, \
        "descriptive labels on pages without rows are ignored"
    codes = [r["table_code"] for r in parsed.rows]
    assert codes == ["A", "A", "A", "B", "B", "F", "F", "F"], "a page without a label continues the previous table"
    estrella = parsed.rows[0]
    assert estrella["ccn"] is None and estrella["facility_name"] == "Estrella Center" and estrella["address_city"] == "350 East La Canada Avondale"
    assert estrella["state"] == "AZ" and estrella["zip_code"] == "85323" and estrella["phone"] == "623-932-2282" and estrella["months_as_sff"] == 10
    assert parsed.rows[2]["facility_name"] == "Grove At North Huntingdon, The"
    golden = parsed.rows[3]
    assert golden["most_recent_inspection"] == "2012-03-01" and golden["months_as_sff"] == 7 and golden["met_survey_criteria"] is None
    assert parsed.rows[4]["facility_name"] == "Haven Home" and parsed.rows[4]["address_city"].startswith("P O Box 10")
    assert parsed.rows[-1]["phone"] == "(330) 339-2151" and parsed.rows[-1]["table_title"] == "SFF Candidate List"


def test_legacy_edition_has_no_rows_but_keeps_tables_and_date():
    legacy = ["Table A: Facilities Newly Added to the SFF Program", "Updated May 16, 2019", "Ahava Healthcare Of Alabaster", "Diamond Cove, Llc",
              "015217 Only One Row 1 Main St Town AL 35214"]
    parsed = parse_lines(legacy)
    assert parsed.layout == "legacy" and parsed.rows == [] and parsed.edition_date == "2019-05-16"
    assert parsed.tables == {"A": "Facilities Newly Added to the SFF Program"}


def test_glue_lines_rejoins_split_words_only_when_the_result_is_a_row():
    raw = ["M", "ountain City Nursing And Rehabilitation Center 403 Hazle Township Boulevard Hazleton PA 18202 570-454-8888 1", "PA", "Phone "]
    assert glue_lines(raw) == ["Mountain City Nursing And Rehabilitation Center 403 Hazle Township Boulevard Hazleton PA 18202 570-454-8888 1", "PA", "Phone "]


def test_split_name_address():
    assert split_name_address("Peak Resources - Shelby 1101 North Morgan Street Shelby") == ("Peak Resources - Shelby", "1101 North Morgan Street Shelby")
    assert split_name_address("Home With No Street Number") == ("Home With No Street Number", None)


def test_list_captures_from_cdx_json():
    cdx = [["timestamp", "digest", "length"], ["20230415000000", "AAA", "1123316"], ["20120411093613", "BBB", "128638"], ["20120411093613", "BBB", "128638"]]
    captures = list_captures(cdx_json=cdx)
    assert [c.timestamp for c in captures] == ["20120411093613", "20230415000000"], "duplicates collapse, oldest first"
    assert captures[0].captured_at == "2012-04-11" and captures[0].url.startswith("http://web.archive.org/web/20120411093613id_/https://www.cms.gov/")
    assert isinstance(captures[0], Capture)


def test_resolve_ccns_by_name_then_unique_zip(tmp_path: Path):
    parquet = tmp_path / "facilities_history.parquet"
    con = duckdb.connect()
    con.execute(f"""COPY (SELECT * FROM (VALUES ('035123', 'ESTRELLA CENTER', 'AZ', '85323'), ('205050', 'MARSHWOOD CENTER', 'ME', '04240'),
                    ('205051', 'OTHER HOME', 'ME', '04240'), ('395555', 'GROVE AT NORTH HUNTINGDON', 'PA', '15642-1234')) t(ccn, provider_name, state, zip_code))
                    TO '{parquet.as_posix()}' (FORMAT PARQUET)""")
    con.close()
    rows = [
        {"ccn": "345420", "facility_name": "Alamance", "state": "NC", "zip_code": "27217"},
        {"ccn": None, "facility_name": "Estrella Center", "state": "AZ", "zip_code": "85323"},
        {"ccn": None, "facility_name": "Marshwood Ctr", "state": "ME", "zip_code": "04240"},
        {"ccn": None, "facility_name": "Grove At North Huntingdon, The", "state": "PA", "zip_code": "15642"},
    ]
    counts = resolve_ccns(rows, parquet)
    assert counts == {"printed": 1, "name_state_zip": 1, "state_zip_unique": 1, "state_zip_name_similar": 1, "unmatched": 0}
    assert rows[1]["ccn"] == "035123" and rows[1]["ccn_match"] == "name_state_zip"
    assert rows[2]["ccn"] == "205050" and rows[2]["ccn_match"] == "state_zip_name_similar", "two facilities share the ZIP; the abbreviated name still points at one"
    assert rows[3]["ccn"] == "395555" and rows[3]["ccn_match"] == "state_zip_unique"
