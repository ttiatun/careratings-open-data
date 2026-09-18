"""
State minimum staffing standards for nursing homes: the hand-curated table
behind /data/staffing/state-standards/.

    tcr-open-data verify-standards [--file analysis/staffing/state_standards.json] [--state CA ...]

The table lives at analysis/staffing/state_standards.json and is published
beside the staffing study runs by `publish-analysis`. Each entry restates
one state's statute or regulation and carries `must_contain`: short phrases
copied from the legal text that hold the figures. `validate` checks the
shape of the file offline (it runs in the test suite); `verify_online`
fetches each entry's `verify_url`, strips it to text and confirms every
phrase is still there, which is how an entry is re-checked when a law may
have changed. A phrase that has gone missing is a prompt to re-read the
law, not proof that it changed: publishers re-format pages.

Nothing is inferred. A state with no numeric minimum beyond the federal
requirements is recorded as `standard_type: "none"`, and a figure the law
does not state is null.
"""

from __future__ import annotations

import html
import io
import json
import re
import subprocess
from pathlib import Path

STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
STANDARD_TYPES = {"hprd", "ratio", "hprd_and_ratio", "none"}
SOURCE_TYPES = {"statute", "regulation"}
HOUR_FIELDS = ("total_hprd", "rn_hprd", "licensed_hprd", "aide_hprd")
REQUIRED = ("state", "standard_type", *HOUR_FIELDS, "ratios", "applies_to", "citation", "source_type", "official_url", "verify_url", "must_contain", "effective", "summary", "notes", "verified_on")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(table: dict) -> list[str]:
    """Problems with the shape of the table; an empty list means it is publishable."""
    problems: list[str] = []
    for key in ("updated", "scope", "method", "entries"):
        if key not in table:
            problems.append(f"missing top-level key {key}")
    if not _DATE.match(str(table.get("updated", ""))):
        problems.append("updated must be YYYY-MM-DD")
    entries = table.get("entries") or []
    seen: set[str] = set()
    for e in entries:
        state = e.get("state", "?")
        where = f"{state}: "
        for key in REQUIRED:
            if key not in e:
                problems.append(where + f"missing {key}")
        if state not in STATES:
            problems.append(where + "unknown state code")
        if state in seen:
            problems.append(where + "listed twice")
        seen.add(state)
        if e.get("standard_type") not in STANDARD_TYPES:
            problems.append(where + "standard_type must be one of " + ", ".join(sorted(STANDARD_TYPES)))
        if e.get("source_type") not in SOURCE_TYPES:
            problems.append(where + "source_type must be statute or regulation")
        hours = [e.get(k) for k in HOUR_FIELDS]
        for key, value in zip(HOUR_FIELDS, hours):
            if value is not None and not (isinstance(value, (int, float)) and 0 < value < 12):
                problems.append(where + f"{key} must be null or hours per resident day between 0 and 12")
        kind = e.get("standard_type")
        if kind == "none" and (any(v is not None for v in hours) or e.get("ratios")):
            problems.append(where + "standard_type none cannot carry hours or ratios")
        if kind == "hprd" and all(v is None for v in hours):
            problems.append(where + "standard_type hprd needs at least one hours figure")
        if kind == "ratio" and not e.get("ratios"):
            problems.append(where + "standard_type ratio needs the ratios text")
        if kind == "hprd_and_ratio" and (all(v is None for v in hours) or not e.get("ratios")):
            problems.append(where + "standard_type hprd_and_ratio needs both hours and ratios")
        for key in ("official_url", "verify_url"):
            if not str(e.get(key, "")).startswith(("https://", "http://")):
                problems.append(where + f"{key} must be a URL")
        phrases = e.get("must_contain")
        if not isinstance(phrases, list) or not phrases or not all(isinstance(p, str) and p.strip() for p in phrases):
            problems.append(where + "must_contain needs at least one phrase from the legal text")
        if not _DATE.match(str(e.get("verified_on", ""))):
            problems.append(where + "verified_on must be YYYY-MM-DD")
        if e.get("effective") is not None and not _DATE.match(str(e.get("effective"))):
            problems.append(where + "effective must be null or YYYY-MM-DD")
        for key in ("citation", "summary", "applies_to"):
            if not str(e.get(key, "")).strip():
                problems.append(where + f"{key} is empty")
    missing = [s for s in STATES if s not in seen]
    if entries and missing:
        problems.append("no entry for: " + ", ".join(missing))
    return problems


def fetch_text(url: str, timeout: int = 60) -> str:
    """The text of a web page or PDF, fetched into memory. Empty when the fetch fails."""
    out = subprocess.run(["curl", "-s", "-L", "--max-time", str(timeout), "-A", USER_AGENT, "-H", "Accept-Language: en-US,en;q=0.9", url], capture_output=True, check=False)
    raw = out.stdout
    if not raw:
        return ""
    if raw[:5] == b"%PDF-":
        from pypdf import PdfReader

        return "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(raw)).pages)
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    return html.unescape(re.sub(r"(?s)<[^>]+>", " ", text))


def _flat(text: str) -> str:
    """Compare on letters and digits only: publishers differ in spacing, hyphens and quotation marks."""
    return re.sub(r"[^0-9a-z.]+", "", text.lower())


def check_phrases(text: str, phrases: list[str]) -> list[str]:
    """The phrases that are NOT in the text."""
    flat = _flat(text)
    return [p for p in phrases if _flat(p) not in flat]


def verify_online(table: dict, states: list[str] | None = None, fetch=fetch_text) -> list[dict]:
    results = []
    for e in table.get("entries", []):
        if states and e["state"] not in states:
            continue
        text = fetch(e["verify_url"])
        missing = check_phrases(text, e["must_contain"]) if text else list(e["must_contain"])
        results.append({"state": e["state"], "verify_url": e["verify_url"], "fetched_characters": len(text), "missing": missing, "ok": bool(text) and not missing})
    return results
