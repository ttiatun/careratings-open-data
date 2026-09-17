"""
Site file for a study run: every CSV table of the run as one JSON document.

The enforcement and staffing pages on the site read a single
`site/<study>.json` from the research store. It is the study's own tables,
nothing recomputed, so a page can never disagree with the CSVs committed in
this repository. Written under `<run>/site/` (git-ignored build output) and
published with `tcr-open-data publish-analysis`.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from . import __version__


def _value(text: str | None):
    if text is None or text == "":
        return None
    if text in ("true", "True"):
        return True
    if text in ("false", "False"):
        return False
    try:
        return int(text) if text.lstrip("-").isdigit() else float(text)
    except ValueError:
        return text


def read_table(path: Path) -> list[dict]:
    """A study CSV as a list of records with numbers and booleans restored."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [{key: _value(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def write_study_site(study: str, run_dir: Path, manifest: dict, tables: list[str], extra: dict | None = None) -> Path:
    """Write `<run_dir>/site/<study>.json` from the named CSV tables of the run."""
    site_dir = run_dir / "site"
    site_dir.mkdir(parents=True, exist_ok=True)
    document = {
        "study": study,
        "release": manifest["release"],
        "processing_date": manifest.get("processing_date"),
        "doi": manifest.get("doi"),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "builder": {"name": "tcr-open-data", "version": __version__},
        "sources": manifest.get("sources", {}),
        **(extra or {}),
        "tables": {name: read_table(run_dir / f"{name}.csv") for name in tables},
    }
    path = site_dir / f"{study}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def _money(value) -> str:
    return "n/a" if value is None else f"${float(value):,.0f}"


def _rank(states: list[dict], key: str, state: str) -> str:
    """Rank among states that are not suppressed, highest value first."""
    ranked = sorted((r for r in states if not r.get("suppressed") and r.get(key) is not None), key=lambda r: (-(r[key] or 0), r["state"]))
    for i, r in enumerate(ranked, 1):
        if r["state"] == state:
            return f"{i} of {len(ranked)}"
    return "not ranked"


def write_state_cuts(study: str, run_dir: Path, manifest: dict, small_state: int, standards: dict | None = None) -> Path | None:
    """One section per state with its figures and ranks, for state press. Reads the run's own CSV tables; returns None for an unknown study."""
    from .ownership_site import STATE_NAMES

    states = read_table(run_dir / "by_state.csv")
    national = (read_table(run_dir / "national_summary.csv") or [{}])[0]
    release, vintage = manifest["release"], manifest.get("processing_date")
    if study == "enforcement":
        lines = [
            f"# State cuts: nursing home fines and payment denials, release {release}",
            "",
            f"One section per state from the enforcement study (CMS Provider Information and Penalties vintage {vintage}). Every figure is a column of `by_state.csv`; ranks are among states with at least "
            f"{small_state} certified nursing homes, highest value first. The file covers about three years, does not say whether a penalty was per instance or per day, and a fine reaches it months after it is imposed. "
            "State differences reflect survey and enforcement practice as much as facility conduct, and the comparisons are descriptive.",
            "",
            f"National: {int(national.get('fines') or 0):,} fines totalling {_money(national.get('total_fines_dollars'))}; {national.get('pct_facilities_fined')}% of {int(national.get('facilities') or 0):,} facilities fined; "
            f"{_money(national.get('fines_dollars_per_bed'))} per certified bed; {int(national.get('payment_denials') or 0):,} payment denials.",
            "",
        ]

        def bullets(r: dict) -> list[str]:
            return [
                f"- Certified nursing homes: {int(r['facilities']):,} ({int(r.get('certified_beds') or 0):,} certified beds); average overall rating {r.get('avg_overall_rating')}.",
                f"- Fines in the file: {int(r.get('fines') or 0):,} totalling {_money(r.get('total_fines_dollars'))}; {int(r.get('facilities_fined') or 0):,} facilities ({r.get('pct_facilities_fined')}%) have at least one, rank {_rank(states, 'pct_facilities_fined', r['state'])}.",
                f"- Fine dollars per certified bed: {_money(r.get('fines_dollars_per_bed'))}, rank {_rank(states, 'fines_dollars_per_bed', r['state'])}; per facility: {_money(r.get('fines_dollars_per_facility'))}.",
                f"- Payment denials: {int(r.get('payment_denials') or 0):,} ({r.get('denials_per_100_facilities')} per 100 facilities, rank {_rank(states, 'denials_per_100_facilities', r['state'])}); facilities with any penalty: {r.get('pct_with_any_penalty')}%.",
                f"- Special Focus Facilities or candidates: {int(r.get('sff_or_candidate') or 0)}; abuse icons: {int(r.get('abuse_icon_facilities') or 0)}.",
            ]
    elif study == "staffing":
        change = {r["state"]: r for r in read_table(run_dir / "state_change.csv")}
        law = {e["state"]: e for e in (standards or {}).get("entries", [])}
        lines = [
            f"# State cuts: nursing home staffing against the repealed federal minimums, release {release}",
            "",
            f"One section per state from the staffing-standards study (CMS Provider Information vintage {vintage}). Every figure is a column of `by_state.csv` or `state_change.csv`; ranks are among states with at least "
            f"{small_state} certified nursing homes, highest share first. The floors are 0.55 registered-nurse, 2.45 nurse-aide and 3.48 total nurse hours per resident day, from the federal rule published in 2024 and repealed "
            "effective February 2, 2026 before any hour floor applied. Hours are as reported, not adjusted for resident acuity; a facility below a floor is not thereby found to be understaffed. "
            "The state minimum, where shown, is from `analysis/staffing/state_standards.json`; reported hours are not a state's compliance measure.",
            "",
            f"National: {national.get('pct_at_or_above_all_three')}% of {int(national.get('facilities_with_reported_hours') or 0):,} facilities with reported hours are at or above all three floors "
            f"({national.get('pct_at_or_above_rn_floor')}% RN, {national.get('pct_at_or_above_aide_floor')}% aide, {national.get('pct_at_or_above_total_floor')}% total); average total hours {national.get('avg_total_nurse_hprd')}.",
            "",
        ]

        def bullets(r: dict) -> list[str]:
            out = [
                f"- Facilities with reported hours: {int(r.get('facilities_with_reported_hours') or 0):,} of {int(r['facilities']):,}.",
                f"- At or above all three floors: {r.get('pct_at_or_above_all_three')}% ({int(r.get('facilities_at_or_above_all_three') or 0):,} facilities), rank {_rank(states, 'pct_at_or_above_all_three', r['state'])}.",
                f"- By floor: RN {r.get('pct_at_or_above_rn_floor')}%, aide {r.get('pct_at_or_above_aide_floor')}%, total {r.get('pct_at_or_above_total_floor')}% (rank {_rank(states, 'pct_at_or_above_total_floor', r['state'])}).",
                f"- Average reported hours per resident day: total {r.get('avg_total_nurse_hprd')} (rank {_rank(states, 'avg_total_nurse_hprd', r['state'])}), RN {r.get('avg_rn_hprd')}, aide {r.get('avg_aide_hprd')}.",
            ]
            c = change.get(r["state"])
            if c and c.get("change_in_pct_all_three") is not None:
                out.append(f"- All-three share in the {c.get('first_snapshot')} file: {c.get('pct_all_three_first')}%; change to the latest file: {float(c['change_in_pct_all_three']):+.1f} points.")
            e = law.get(r["state"])
            if e:
                if e.get("standard_type") == "none":
                    out.append(f"- State minimum: no numeric minimum beyond the federal requirements ({e.get('citation')}).")
                else:
                    hours = ", ".join(f"{label} {e[key]}" for key, label in (("total_hprd", "total"), ("rn_hprd", "RN"), ("licensed_hprd", "licensed nurse"), ("aide_hprd", "aide")) if e.get(key) is not None)
                    parts = [p for p in (f"{hours} hours per resident day" if hours else "", "staff-to-resident ratios" if e.get("ratios") else "") if p]
                    out.append(f"- State minimum: {' and '.join(parts)} ({e.get('citation')}; checked {e.get('verified_on')}).")
            return out
    else:
        return None

    for r in sorted(states, key=lambda row: STATE_NAMES.get(row["state"], row["state"])):
        lines += [f"## {STATE_NAMES.get(r['state'], r['state'])} ({r['state']})", ""]
        if r.get("suppressed"):
            lines += [f"{int(r['facilities'])} certified nursing home(s): fewer than {small_state}, so shares are not ranked or mapped.", ""]
            continue
        lines += bullets(r) + [""]
    press = run_dir / "press"
    press.mkdir(parents=True, exist_ok=True)
    path = press / "state_cuts.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path

