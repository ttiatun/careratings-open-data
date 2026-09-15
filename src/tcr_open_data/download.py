"""Download CMS source files into raw/<release>/ and record what was fetched."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from .catalog import ResolvedSource, resolve_sources, vintage_from_filename
from .sources import SOURCES


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, target: Path, session: requests.Session | None = None) -> None:
    session = session or requests.Session()
    with session.get(url, stream=True, timeout=600) as response:
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        with tmp.open("wb") as handle:
            for chunk in response.iter_content(1 << 20):
                handle.write(chunk)
        tmp.replace(target)


def write_sources_json(raw_dir: Path, entries: dict[str, dict]) -> Path:
    path = raw_dir / "sources.json"
    path.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "sources": entries}, indent=2), encoding="utf-8")
    return path


def load_sources_json(raw_dir: Path) -> dict[str, dict]:
    path = raw_dir / "sources.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run `download` or describe the files in sources.json")
    return json.loads(path.read_text(encoding="utf-8"))["sources"]


def download_all(raw_dir: Path, force: bool = False, session: requests.Session | None = None,
                 resolved: dict[str, ResolvedSource] | None = None) -> dict[str, dict]:
    """Fetch every source into `raw_dir` under its original CMS filename and write sources.json."""
    session = session or requests.Session()
    resolved = resolved or resolve_sources(session)
    raw_dir.mkdir(parents=True, exist_ok=True)
    entries: dict[str, dict] = {}
    for key in SOURCES:
        item = resolved[key]
        target = raw_dir / item.filename
        if force or not target.exists():
            download_file(item.url, target, session)
        entries[key] = {
            "title": SOURCES[key].title,
            "url": item.url,
            "filename": item.filename,
            "bytes": target.stat().st_size,
            "sha256": sha256_of(target),
            "vintage": vintage_from_filename(item.filename),
            "catalog_modified": item.modified,
        }
    write_sources_json(raw_dir, entries)
    return entries


def describe_local_files(raw_dir: Path, filenames: dict[str, str]) -> dict[str, dict]:
    """Build sources.json for files placed by hand (key -> original CMS filename)."""
    entries: dict[str, dict] = {}
    for key, filename in filenames.items():
        target = raw_dir / filename
        if not target.exists():
            raise FileNotFoundError(target)
        entries[key] = {
            "title": SOURCES[key].title, "url": None, "filename": filename, "bytes": target.stat().st_size,
            "sha256": sha256_of(target), "vintage": vintage_from_filename(filename), "catalog_modified": None,
        }
    write_sources_json(raw_dir, entries)
    return entries
