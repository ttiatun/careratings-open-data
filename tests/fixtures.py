"""Tiny synthetic CMS files with the real headers, for end-to-end tests."""

from __future__ import annotations

import csv
from pathlib import Path

from tcr_open_data.sources import (
    ALL_OWNERS_HEADER, CHAIN_HEADER_PREFIX, CHOW_HEADER, ENROLLMENTS_HEADER, OWNERSHIP_HEADER, PENALTIES_HEADER,
    PROVIDER_INFO_HEADER,
)

FILENAMES = {
    "provider_info": "NH_ProviderInfo_Aug2026.csv", "penalties": "NH_Penalties_Aug2026.csv", "ownership": "NH_Ownership_Aug2026.csv",
    "enrollments": "SNF_Enrollments_2026.07.31.csv", "all_owners": "SNF_All_Owners_2026.07.31.csv",
    "chow": "SNF_CHOW_2026.07.17.csv", "chains": "Chain_Performance_20260909.csv",
}


def _write(path: Path, header: tuple[str, ...] | list[str], rows: list[dict[str, str]], encoding: str = "utf-8") -> None:
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(header), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in header})


def provider(ccn: str, name: str, state: str, **over: str) -> dict[str, str]:
    base = {
        "CMS Certification Number (CCN)": ccn, "Provider Name": name, "Provider Address": "1 MAIN ST", "City/Town": "TOWN",
        "State": state, "ZIP Code": "00001", "County/Parish": "County", "Urban": "Y", "Ownership Type": "For profit - Corporation",
        "Number of Certified Beds": "100", "Average Number of Residents per Day": "80.5", "Provider Type": "Medicare and Medicaid",
        "Provider Resides in Hospital": "N", "Legal Business Name": name, "Date First Approved to Provide Medicare and Medicaid Services": "1990-01-01",
        "Chain Name": "", "Chain ID": "", "Number of Facilities in Chain": "", "Continuing Care Retirement Community": "N",
        "Special Focus Status": "", "Abuse Icon": "N", "Most Recent Health Inspection More Than 2 Years Ago": "N",
        "Provider Changed Ownership in Last 12 Months": "N", "Overall Rating": "3", "Health Inspection Rating": "3",
        "Staffing Rating": "4", "QM Rating": "3", "Long-Stay QM Rating": "3", "Short-Stay QM Rating": "3",
        "Reported Nurse Aide Staffing Hours per Resident per Day": "2.5", "Reported LPN Staffing Hours per Resident per Day": "0.9",
        "Reported RN Staffing Hours per Resident per Day": "0.6", "Reported Total Nurse Staffing Hours per Resident per Day": "4.0",
        "Total number of nurse staff hours per resident per day on the weekend": "3.5",
        "Adjusted RN Staffing Hours per Resident per Day": "0.6", "Adjusted Total Nurse Staffing Hours per Resident per Day": "4.0",
        "Total nursing staff turnover": "45.5", "Registered Nurse turnover": "40.0", "Number of administrators who have left the nursing home": "1",
        "Total Weighted Health Survey Score": "20.667", "Number of Citations from Infection Control Inspections": "0",
        "Number of Fines": "0", "Total Amount of Fines in Dollars": "0", "Number of Payment Denials": "0", "Total Number of Penalties": "0",
        "Latitude": "40.0", "Longitude": "-80.0", "Processing Date": "2026-08-01",
    }
    base.update(over)
    return base


def owner_row(enrollment_id: str, org: str, owner_org: str, role_code: str, role_text: str, owner_type: str = "O", **flags: str) -> dict[str, str]:
    row = {
        "ENROLLMENT ID": enrollment_id, "ASSOCIATE ID": "1", "ORGANIZATION NAME": org, "ASSOCIATE ID - OWNER": owner_org[:6],
        "TYPE - OWNER": owner_type, "ROLE CODE - OWNER": role_code, "ROLE TEXT - OWNER": role_text,
        "ASSOCIATION DATE - OWNER": "1/2/2020", "ORGANIZATION NAME - OWNER": owner_org if owner_type == "O" else "",
        "LAST NAME - OWNER": owner_org if owner_type == "I" else "", "PERCENTAGE OWNERSHIP": "",
    }
    for column in ALL_OWNERS_HEADER[20:]:
        if column.endswith("- OWNER") and column != "OTHER TYPE TEXT - OWNER":
            row[column] = "N"
    row.update(flags)
    return row


def write_fixture_raw(raw_dir: Path) -> dict[str, str]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    providers = [
        provider("100001", "ALPHA CARE", "PA", **{"Chain ID": "154", "Chain Name": "COMMUNITY CARE CENTERS"}),
        provider("100002", "BETA NONPROFIT", "PA", **{"Ownership Type": "Non profit - Corporation", "Overall Rating": "5", "Staffing Rating": "5",
                                                   "Total Number of Penalties": "2", "Number of Fines": "2", "Total Amount of Fines in Dollars": "12000",
                                                   "Special Focus Status": "SFF Candidate", "Reported RN Staffing Hours per Resident per Day": "0.4"}),
        provider("100003", "GAMMA HOME", "OH", **{"Overall Rating": "1", "Staffing Rating": "1", "Abuse Icon": "Y", "Special Focus Status": "SFF",
                                               "Reported RN Staffing Hours per Resident per Day": ""}),
    ]
    # Seven plain Texas facilities with enrollments keep PECOS coverage above the 90% validation floor.
    providers += [provider(f"20000{i}", f"DELTA HOME {i}", "TX") for i in range(1, 8)]
    _write(raw_dir / FILENAMES["provider_info"], PROVIDER_INFO_HEADER, providers)
    _write(raw_dir / FILENAMES["penalties"], PENALTIES_HEADER, [
        {"CMS Certification Number (CCN)": "100002", "Provider Name": "BETA NONPROFIT", "Penalty Date": "2025-03-01", "Penalty Type": "Fine",
         "Fine ID": "1", "Fine Amount": "7000", "Processing Date": "2026-08-01"},
        {"CMS Certification Number (CCN)": "100002", "Provider Name": "BETA NONPROFIT", "Penalty Date": "2025-06-01", "Penalty Type": "Fine",
         "Fine ID": "2", "Fine Amount": "5000", "Processing Date": "2026-08-01"},
    ])
    _write(raw_dir / FILENAMES["ownership"], OWNERSHIP_HEADER, [
        {"CMS Certification Number (CCN)": "100001", "Provider Name": "ALPHA CARE", "Role played by Owner or Manager in Facility": "5% OR GREATER DIRECT OWNERSHIP INTEREST",
         "Owner Type": "Organization", "Owner Name": "ALPHA HOLDINGS LLC", "Ownership Percentage": "60%", "Association Date": "since 01/25/2012", "Processing Date": "2026-08-01"},
        {"CMS Certification Number (CCN)": "100001", "Provider Name": "ALPHA CARE", "Role played by Owner or Manager in Facility": "MANAGING EMPLOYEE",
         "Owner Type": "Individual", "Owner Name": "DOE, JANE", "Ownership Percentage": "NO PERCENTAGE PROVIDED", "Association Date": "since 02/02/2020", "Processing Date": "2026-08-01"},
    ])
    _write(raw_dir / FILENAMES["enrollments"], ENROLLMENTS_HEADER, [
        {"ENROLLMENT ID": "O20100101000001", "CCN": "100001", "NPI": "1111111111", "ORGANIZATION NAME": "ALPHA CARE OPCO LLC", "AFFILIATION ENTITY ID": "AE1", "AFFILIATION ENTITY NAME": "ALPHA GROUP"},
        {"ENROLLMENT ID": "O20200101000002", "CCN": "100001", "NPI": "1111111111", "ORGANIZATION NAME": "ALPHA CARE OPCO II LLC", "AFFILIATION ENTITY ID": "AE1", "AFFILIATION ENTITY NAME": "ALPHA GROUP"},
        {"ENROLLMENT ID": "O20050101000003", "CCN": "100002", "NPI": "2222222222", "ORGANIZATION NAME": "BETA NONPROFIT INC", "AFFILIATION ENTITY ID": "", "AFFILIATION ENTITY NAME": ""},
        # Written as Windows-1252 with a non-ASCII byte, the way some PECOS exports arrive.
        *[{"ENROLLMENT ID": f"O2015010100001{i}", "CCN": f"20000{i}", "NPI": f"33333333{i:02d}", "ORGANIZATION NAME": f"DELTA CAFÉ CARE {i} LLC"} for i in range(1, 8)],
    ], encoding="cp1252")
    _write(raw_dir / FILENAMES["all_owners"], ALL_OWNERS_HEADER, [
        owner_row("O20200101000002", "ALPHA CARE OPCO II LLC", "BUYOUT FUND IV LP", "35", "5% OR GREATER INDIRECT OWNERSHIP INTEREST", **{"PRIVATE EQUITY COMPANY - OWNER": "Y", "PERCENTAGE OWNERSHIP": "60"}),
        owner_row("O20200101000002", "ALPHA CARE OPCO II LLC", "PROPCO REIT INC", "72", "ADP OF THE SNF", **{"REIT - OWNER": "Y"}),
        owner_row("O20200101000002", "ALPHA CARE OPCO II LLC", "SMITH", "40", "CORPORATE OFFICER", owner_type="I"),
        owner_row("O20100101000001", "ALPHA CARE OPCO LLC", "OLD OWNER LLC", "34", "5% OR GREATER DIRECT OWNERSHIP INTEREST", **{"PERCENTAGE OWNERSHIP": "100"}),
        owner_row("O20050101000003", "BETA NONPROFIT INC", "STAFFING VENDOR INC", "72", "ADP OF THE SNF", **{"PRIVATE EQUITY COMPANY - OWNER": "Y", "MEDICAL STAFFING COMPANY - OWNER": "Y"}),
    ])
    _write(raw_dir / FILENAMES["chow"], CHOW_HEADER, [
        {"ENROLLMENT ID - BUYER": "O20200101000002", "CCN - BUYER": "100001", "ORGANIZATION NAME - BUYER": "ALPHA CARE OPCO II LLC", "CHOW TYPE CODE": "CH",
         "CHOW TYPE TEXT": "CHANGE OF OWNERSHIP", "EFFECTIVE DATE": "3/1/2025", "ENROLLMENT ID - SELLER": "O20100101000001", "CCN - SELLER": "100001",
         "ORGANIZATION NAME - SELLER": "ALPHA CARE OPCO LLC"},
    ])
    chain_header = list(CHAIN_HEADER_PREFIX) + ["Average percentage of long-stay residents who received an antipsychotic medication"]
    _write(raw_dir / FILENAMES["chains"], chain_header, [
        {"Chain": "National", "Chain ID": "", "Number of facilities": "10", "Number of states and territories with operations": "3",
         "Number of Special Focus Facilities (SFF)": "1", "Number of SFF candidates": "1", "Number of facilities with an abuse icon": "1",
         "Percentage of facilities with an abuse icon": "33.3", "Percent of facilities classified as for-profit": "66.7",
         "Percent of facilities classified as non-profit": "33.3", "Percent of facilities classified as government-owned": "0.0",
         "Average overall 5-star rating": "3.0", "Total number of fines": "2", "Total amount of fines in dollars": "12000",
         "Total number of payment denials": "0", "Average percentage of long-stay residents who received an antipsychotic medication": "15.4"},
        {"Chain": "COMMUNITY CARE CENTERS", "Chain ID": "154", "Number of facilities": "1", "Number of states and territories with operations": "1",
         "Number of Special Focus Facilities (SFF)": "0", "Number of SFF candidates": "0", "Number of facilities with an abuse icon": "0",
         "Average overall 5-star rating": "3.0", "Total number of fines": "0", "Total amount of fines in dollars": "0",
         "Total number of payment denials": "0", "Average percentage of long-stay residents who received an antipsychotic medication": "22.1"},
    ])
    return dict(FILENAMES)
