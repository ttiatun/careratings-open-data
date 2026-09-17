"""The state staffing-standards table: shape validation offline, phrase checks against a fetched text."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from tcr_open_data.state_standards import STATES, check_phrases, validate, verify_online

REPO = Path(__file__).resolve().parents[1]


def entry(state: str, **over) -> dict:
    base = {"state": state, "standard_type": "hprd", "total_hprd": 3.5, "rn_hprd": None, "licensed_hprd": None, "aide_hprd": 2.4, "ratios": None,
            "applies_to": "skilled nursing facilities", "citation": "Example Code 1", "source_type": "statute", "official_url": "https://example.gov/code/1",
            "verify_url": "https://example.gov/code/1", "must_contain": ["3.5 direct care service hours", "2.4 hours"], "effective": "2018-07-01",
            "summary": "At least 3.5 direct care hours per resident day, 2.4 of them by aides.", "notes": None, "verified_on": "2026-09-17"}
    base.update(over)
    return base


def table(entries: list[dict]) -> dict:
    return {"updated": "2026-09-17", "scope": "scope", "method": "method", "entries": entries}


def test_a_complete_table_is_valid():
    full = table([entry(s) for s in STATES])
    assert validate(full) == []
    assert len(STATES) == 51 and "DC" in STATES


def test_validation_catches_the_mistakes_that_matter():
    full = [entry(s) for s in STATES]
    missing_state = validate(table(full[:-1]))
    assert any("no entry for: WY" in p for p in missing_state)
    twice = validate(table(full + [entry("CA")]))
    assert any("CA: listed twice" in p for p in twice)
    none_with_hours = validate(table([entry(s) for s in STATES[:-1]] + [entry("WY", standard_type="none")]))
    assert any("WY: standard_type none cannot carry hours" in p for p in none_with_hours)
    ratio_without_text = validate(table([entry(s) for s in STATES[:-1]] + [entry("WY", standard_type="ratio", total_hprd=None, aide_hprd=None)]))
    assert any("WY: standard_type ratio needs the ratios text" in p for p in ratio_without_text)
    silly_hours = validate(table([entry(s) for s in STATES[:-1]] + [entry("WY", total_hprd=35)]))
    assert any("WY: total_hprd must be null or hours" in p for p in silly_hours)
    no_phrases = validate(table([entry(s) for s in STATES[:-1]] + [entry("WY", must_contain=[])]))
    assert any("WY: must_contain needs at least one phrase" in p for p in no_phrases)
    bad = copy.deepcopy(full)
    del bad[0]["verified_on"]
    assert any("AL: missing verified_on" in p for p in validate(table(bad)))


def test_phrases_match_across_spacing_and_punctuation_but_not_across_numbers():
    text = "Facilities shall provide a minimum of 3.5 direct-care  service hours per patient day, of which 2.4 hours shall be by certified nurse assistants."
    assert check_phrases(text, ["3.5 direct care service hours", "2.4 hours shall be"]) == []
    assert check_phrases(text, ["3.2 direct care service hours"]) == ["3.2 direct care service hours"]
    assert check_phrases(text, ["35 direct care service hours"]) == ["35 direct care service hours"]


def test_online_verification_reports_missing_phrases_and_empty_fetches():
    pages = {"https://example.gov/code/1": "minimum of 3.5 direct care service hours, including 2.4 hours by aides", "https://example.gov/gone": ""}
    data = table([entry("CA"), entry("FL", verify_url="https://example.gov/gone"), entry("NY", must_contain=["4.1 hours"])])
    results = {r["state"]: r for r in verify_online(data, fetch=lambda url: pages.get(url, ""))}
    assert results["CA"]["ok"] is True and results["CA"]["missing"] == []
    assert results["FL"]["ok"] is False and results["FL"]["fetched_characters"] == 0
    assert results["NY"]["ok"] is False and results["NY"]["missing"] == ["4.1 hours"]
    only = verify_online(data, states=["CA"], fetch=lambda url: pages.get(url, ""))
    assert [r["state"] for r in only] == ["CA"]


def test_the_committed_table_is_valid():
    path = REPO / "analysis" / "staffing" / "state_standards.json"
    assert path.exists(), "analysis/staffing/state_standards.json is part of the repository"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert validate(data) == []
    # Nothing is inferred: a state recorded as having no numeric minimum carries no figures.
    assert all(all(e[k] is None for k in ("total_hprd", "rn_hprd", "licensed_hprd", "aide_hprd")) for e in data["entries"] if e["standard_type"] == "none")
