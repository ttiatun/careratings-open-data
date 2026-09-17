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
