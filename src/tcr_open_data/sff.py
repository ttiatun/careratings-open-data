"""
Special Focus Facility (SFF) history from archived CMS PDFs.

CMS publishes the SFF list as a PDF that it overwrites in place. The Internet
Archive has captured the file since 2012, so the history is rebuilt from those
captures: list them through the CDX API, fetch the original bytes of each
capture, extract the text page by page, and parse the tables.

Three printed layouts exist:

* 2012-2022: one facility per line without a CCN
  ("Name Street City ST 12345 555-555-5555 [MM/DD/YYYY] months"); the table
  label ("Table A: ...") is printed once per page, above or below the rows.
* 2023-2024: the same, with a six-character CCN at the start of each row and
  a "Met / Not Met" survey column.
* Anything the row patterns do not recognise is recorded in sff_editions with
  layout = 'legacy' and no rows.

Rows without a printed CCN are matched to Care Compare facilities by name,
state and ZIP (see resolve_ccns); the match method is recorded per row.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import __version__

SFF_URL = "https://www.cms.gov/Medicare/Provider-Enrollment-and-Certification/CertificationandComplianc/Downloads/SFFList.pdf"
CDX_URL = "http://web.archive.org/cdx/search/cdx"
USER_AGENT = "tcr-open-data/" + __version__ + " (+https://github.com/ttiatun/careratings-open-data)"

TABLE_LABEL = re.compile(r"^\s*Table\s+([A-H])\s*[:\-–—]\s*(.*?)\s*$")
UPDATED = re.compile(r"Updated\s+([A-Z][a-z]+ \d{1,2}, \d{4})")
PHONE = r"\(?\d{3}\)?[-\s.]?\d{3}[-.]\d{4}"
ROW_TAIL = (
    r"\s+(?P<state>[A-Z]{2})\s+(?P<zip>\d{5})(?:-\d{4})?"
    r"(?:\s+(?P<phone>" + PHONE + r"))%s"
    r"(?:\s+(?P<inspection>\d{1,2}/\d{1,2}/\d{4}))?"
    r"(?:\s+(?P<met>Met|Not Met))?"
    r"(?:\s+(?P<months>\d{1,3}))?\s*$"
)
ROW_CCN = re.compile(r"^\s*(?P<ccn>\d{6})\s+(?P<body>.+?)" + ROW_TAIL % "?")
ROW_NOCCN = re.compile(r"^\s*(?P<body>.+?)" + ROW_TAIL % "")
STREET = re.compile(r"^(?P<name>.*?)\s+(?P<address>(?:\d[\w-]*|P\.?\s?O\.?\s+Box)\s+.*)$", re.IGNORECASE)
RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass
class Capture:
    timestamp: str
    digest: str
    length: int
    original: str = SFF_URL

    @property
    def url(self) -> str:
        return f"http://web.archive.org/web/{self.timestamp}id_/{self.original}"

    @property
    def captured_at(self) -> str:
        return datetime.strptime(self.timestamp, "%Y%m%d%H%M%S").strftime("%Y-%m-%d")


def _session(session: requests.Session | None) -> requests.Session:
    if session is None:
        session = requests.Session()
    session.headers.setdefault("User-Agent", USER_AGENT)
    return session


FIRST_CAPTURE_YEAR = 2012


def _cdx_rows(session: requests.Session, params: dict, retries: int = 4, sleep=time.sleep) -> list:
    delay = 15.0
    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(CDX_URL, params=params, timeout=600)
            if response.status_code in RETRY_STATUS:
                raise requests.HTTPError(f"{response.status_code} from the CDX API", response=response)
            response.raise_for_status()
            return response.json()[1:] if response.text.strip() else []
        except requests.RequestException as exc:
            last = exc
            if attempt + 1 < retries:
                sleep(delay)
                delay = min(delay * 2, 240)
    raise RuntimeError(f"CDX query failed: {type(last).__name__}: {str(last)[:160]}")


def list_captures(session: requests.Session | None = None, cdx_json: list | None = None, original: str = SFF_URL,
                  years=None) -> list[Capture]:
    """One capture per month of the SFF PDF, oldest first (status 200 only). The index is queried one year at a
    time: a single unbounded query silently dropped 2014-2020 when the CDX server was under load."""
    if cdx_json is not None:
        rows = list(cdx_json[1:])
    else:
        session = _session(session)
        rows = []
        for year in years or range(FIRST_CAPTURE_YEAR, datetime.now(timezone.utc).year + 1):
            rows.extend(_cdx_rows(session, {"url": original, "output": "json", "filter": "statuscode:200", "collapse": "timestamp:6",
                                            "fl": "timestamp,digest,length", "from": str(year), "to": str(year)}))
    by_timestamp = {row[0]: Capture(row[0], row[1], int(row[2] or 0), original) for row in rows if row and row[0]}
    return sorted(by_timestamp.values(), key=lambda c: c.timestamp)


def fetch_capture(capture: Capture, cache_dir: Path, session: requests.Session | None = None,
                  retries: int = 5, pause: float = 2.0, sleep=time.sleep) -> Path:
    """Download the original bytes of a capture into the cache (idempotent), backing off on throttling and dropped connections."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"SFFList_{capture.timestamp}.pdf"
    if target.exists() and target.stat().st_size > 0:
        return target
    session = _session(session)
    delay = max(pause, 1.0)
    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(capture.url, timeout=300)
            if response.status_code in RETRY_STATUS:
                raise requests.HTTPError(f"{response.status_code} from web.archive.org", response=response)
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise ValueError("capture is not a PDF")
            target.write_bytes(response.content)
            if pause:
                sleep(pause)
            return target
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt + 1 < retries:
                sleep(delay)
                delay = min(delay * 3, 300)
    raise RuntimeError(f"gave up after {retries} attempts: {type(last).__name__}: {str(last)[:160]}")


def glue_lines(raw: list[str]) -> list[str]:
    """Re-join a word the PDF text layer split across lines ("M" / "ountain City ...") when the joined line is a facility row."""
    lines: list[str] = []
    skip = False
    for index, line in enumerate(raw):
        if skip:
            skip = False
            continue
        stripped = line.strip()
        if len(stripped) <= 2 and stripped.isalpha() and index + 1 < len(raw) and _match_row(stripped + raw[index + 1]):
            lines.append(stripped + raw[index + 1])
            skip = True
            continue
        lines.append(line)
    return lines


def pdf_pages(path: Path) -> list[list[str]]:
    """Non-empty text lines per page."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [glue_lines([l.rstrip() for l in (page.extract_text() or "").splitlines() if l.strip()]) for page in reader.pages]


def pdf_lines(path: Path) -> list[str]:
    return [line for page in pdf_pages(path) for line in page]


def split_name_address(body: str) -> tuple[str, str | None]:
    m = STREET.match(body)
    if m and m.group("name").strip():
        return m.group("name").strip(), m.group("address").strip()
    return body.strip(), None


@dataclass
class ParsedEdition:
    edition_date: str | None
    layout: str
    tables: dict[str, str] = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)


def _match_row(line: str) -> re.Match | None:
    return ROW_CCN.match(line) or ROW_NOCCN.match(line)


def parse_pages(pages: list[list[str]]) -> ParsedEdition:
    """Parse an edition page by page. Rows take the nearest table label above them on the page, else the first
    label below them (footer layout), else the label carried over from the previous page."""
    edition_date = None
    for line in (l for page in pages for l in page):
        m = UPDATED.search(line)
        if m:
            try:
                edition_date = datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
            except ValueError:
                edition_date = None
            break
    tables: dict[str, str] = {}
    rows: list[dict] = []
    carried: str | None = None
    for page in pages:
        labels = [(i, TABLE_LABEL.match(line)) for i, line in enumerate(page) if TABLE_LABEL.match(line)]
        matches = [(i, _match_row(line)) for i, line in enumerate(page) if _match_row(line)]
        if not matches:
            continue
        for i, m in matches:
            above = [lab for lab in labels if lab[0] < i]
            below = [lab for lab in labels if lab[0] > i]
            label = above[-1][1] if above else below[0][1] if below else None
            code = label.group(1) if label else carried
            if label:
                tables.setdefault(code, label.group(2)[:120])
            if code is None:
                continue
            name, address = split_name_address(m.group("body"))
            groups = m.groupdict()
            rows.append({
                "table_code": code, "table_title": tables.get(code), "ccn": groups.get("ccn"), "facility_name": name,
                "address_city": address, "state": m.group("state"), "zip_code": m.group("zip"), "phone": m.group("phone"),
                "most_recent_inspection": _iso(m.group("inspection")), "met_survey_criteria": _met(m.group("met")),
                "months_as_sff": int(m.group("months")) if m.group("months") else None,
            })
        if labels:
            carried = labels[-1][1].group(1)
    if len(rows) < 5:
        return ParsedEdition(edition_date, "legacy", tables, [])
    with_ccn = sum(1 for r in rows if r["ccn"])
    layout = "rows" if with_ccn * 2 >= len(rows) else "rows_no_ccn"
    return ParsedEdition(edition_date, layout, tables, rows)


def parse_lines(lines: list[str]) -> ParsedEdition:
    return parse_pages([lines])


def _iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _met(value: str | None) -> bool | None:
    if value == "Met":
        return True
    if value == "Not Met":
        return False
    return None


def normalize_name(name: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]+", " ", (name or "").upper())).strip()


def resolve_ccns(rows: list[dict], facilities_parquet: Path) -> dict:
    """Fill ccn for rows without a printed CCN using facilities_history (name + state + ZIP, then unique state + ZIP)."""
    import duckdb

    con = duckdb.connect()
    path = facilities_parquet.resolve().as_posix().replace("'", "''")
    by_name: dict[tuple[str, str, str], set[str]] = {}
    by_zip: dict[tuple[str, str], set[str]] = {}
    for ccn, name, state, zip_code in con.execute(
            f"SELECT DISTINCT ccn, provider_name, state, left(zip_code, 5) FROM read_parquet('{path}') WHERE ccn IS NOT NULL AND state IS NOT NULL").fetchall():
        by_name.setdefault((normalize_name(name), state, zip_code or ""), set()).add(ccn)
        by_zip.setdefault((state, zip_code or ""), set()).add(ccn)
    con.close()
    counts = {"printed": 0, "name_state_zip": 0, "state_zip_unique": 0, "unmatched": 0}
    for row in rows:
        if row.get("ccn"):
            row["ccn_match"] = "printed"
        else:
            key = (normalize_name(row.get("facility_name")), row.get("state") or "", (row.get("zip_code") or "")[:5])
            hits = by_name.get(key, set())
            if len(hits) == 1:
                row["ccn"], row["ccn_match"] = next(iter(hits)), "name_state_zip"
            else:
                hits = by_zip.get(key[1:], set())
                if len(hits) == 1:
                    row["ccn"], row["ccn_match"] = next(iter(hits)), "state_zip_unique"
                else:
                    row["ccn_match"] = "unmatched"
        counts[row["ccn_match"]] += 1
    return counts


ROW_COLUMNS = ["capture_timestamp", "captured_at", "edition_date", "table_code", "table_title", "ccn", "ccn_match", "facility_name", "address_city",
               "state", "zip_code", "phone", "most_recent_inspection", "met_survey_criteria", "months_as_sff", "source_url"]
EDITION_COLUMNS = ["capture_timestamp", "captured_at", "edition_date", "layout", "pages", "row_count", "tables", "sha256", "duplicate_of_previous", "error"]


def _csv_columns(columns: list[str]) -> str:
    return "{" + ", ".join(f"'{c}': 'VARCHAR'" for c in columns) + "}"


def build_sff_history(captures: list[Capture], history_dir: Path, session: requests.Session | None = None,
                      progress=print, fetch=fetch_capture, facilities_parquet: Path | None = None) -> dict:
    """Fetch and parse every capture; write sff_history.parquet, sff_editions.parquet, and sff_manifest.json."""
    import duckdb

    cache_dir = history_dir / "sff" / "raw"
    editions: list[dict] = []
    rows: list[dict] = []
    seen_digest: set[str] = set()
    for capture in captures:
        try:
            path = fetch(capture, cache_dir, session)
        except Exception as exc:  # noqa: BLE001
            progress(f"{capture.timestamp}: fetch failed {type(exc).__name__}: {str(exc)[:120]}")
            editions.append({"capture_timestamp": capture.timestamp, "captured_at": capture.captured_at, "edition_date": None, "layout": "unavailable",
                             "pages": 0, "row_count": 0, "tables": "", "sha256": None, "duplicate_of_previous": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        duplicate = digest in seen_digest
        seen_digest.add(digest)
        try:
            pages = pdf_pages(path)
            parsed = parse_pages(pages)
        except Exception as exc:  # noqa: BLE001
            progress(f"{capture.timestamp}: parse failed {type(exc).__name__}")
            editions.append({"capture_timestamp": capture.timestamp, "captured_at": capture.captured_at, "edition_date": None, "layout": "unreadable",
                             "pages": 0, "row_count": 0, "tables": "", "sha256": digest, "duplicate_of_previous": duplicate, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        editions.append({"capture_timestamp": capture.timestamp, "captured_at": capture.captured_at, "edition_date": parsed.edition_date,
                         "layout": parsed.layout, "pages": len(pages), "row_count": len(parsed.rows),
                         "tables": ";".join(f"{k}={v}" for k, v in sorted(parsed.tables.items())), "sha256": digest,
                         "duplicate_of_previous": duplicate, "error": ""})
        if not duplicate:
            for r in parsed.rows:
                rows.append({"capture_timestamp": capture.timestamp, "captured_at": capture.captured_at, "edition_date": parsed.edition_date, **r,
                             "source_url": capture.url})
        progress(f"{capture.timestamp}: {parsed.layout} edition {parsed.edition_date} rows={len(parsed.rows)}{' (duplicate)' if duplicate else ''}")

    ccn_matches = None
    if facilities_parquet is not None and facilities_parquet.exists():
        ccn_matches = resolve_ccns(rows, facilities_parquet)
        progress(f"ccn matching: {ccn_matches}")

    history_dir.mkdir(parents=True, exist_ok=True)
    rows_csv = history_dir / "sff_history.csv"
    editions_csv = history_dir / "sff_editions.csv"
    _write_csv(rows_csv, rows, ROW_COLUMNS)
    _write_csv(editions_csv, editions, EDITION_COLUMNS)
    con = duckdb.connect()
    q = lambda p: p.resolve().as_posix().replace("'", "''")
    con.execute(f"""COPY (SELECT capture_timestamp, CAST(captured_at AS DATE) AS captured_at, TRY_CAST(edition_date AS DATE) AS edition_date, table_code, table_title,
                    ccn, ccn_match, facility_name, address_city, state, zip_code, phone, TRY_CAST(most_recent_inspection AS DATE) AS most_recent_inspection,
                    TRY_CAST(met_survey_criteria AS BOOLEAN) AS met_survey_criteria, TRY_CAST(months_as_sff AS INTEGER) AS months_as_sff, source_url
                    FROM read_csv('{q(rows_csv)}', header=true, columns={_csv_columns(ROW_COLUMNS)}))
                    TO '{q(history_dir / 'sff_history.parquet')}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    con.execute(f"""COPY (SELECT capture_timestamp, CAST(captured_at AS DATE) AS captured_at, TRY_CAST(edition_date AS DATE) AS edition_date, layout,
                    TRY_CAST(pages AS INTEGER) AS pages, TRY_CAST(row_count AS INTEGER) AS row_count, tables, sha256,
                    TRY_CAST(duplicate_of_previous AS BOOLEAN) AS duplicate_of_previous, error
                    FROM read_csv('{q(editions_csv)}', header=true, columns={_csv_columns(EDITION_COLUMNS)}))
                    TO '{q(history_dir / 'sff_editions.parquet')}' (FORMAT PARQUET)""")
    con.close()
    parsed_layouts = ("rows", "rows_no_ccn")
    summary = {
        "built_at": datetime.now(timezone.utc).isoformat(), "builder": {"name": "tcr-open-data", "version": __version__},
        "source": SFF_URL, "captures": len(captures),
        "editions": {"rows_layout": sum(1 for e in editions if e["layout"] == "rows"), "rows_no_ccn_layout": sum(1 for e in editions if e["layout"] == "rows_no_ccn"),
                     "legacy_layout": sum(1 for e in editions if e["layout"] == "legacy"),
                     "unavailable": sum(1 for e in editions if e["layout"] in ("unavailable", "unreadable")), "duplicates": sum(1 for e in editions if e["duplicate_of_previous"])},
        "rows": len(rows), "ccn_matches": ccn_matches,
        "first_parsed_edition": min((e["edition_date"] for e in editions if e["layout"] in parsed_layouts and e["edition_date"]), default=None),
        "last_parsed_edition": max((e["edition_date"] for e in editions if e["layout"] in parsed_layouts and e["edition_date"]), default=None),
        "unavailable_captures": [e["capture_timestamp"] for e in editions if e["layout"] in ("unavailable", "unreadable")],
    }
    (history_dir / "sff_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: ("" if row.get(c) is None else row.get(c)) for c in columns})
