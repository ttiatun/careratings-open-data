"""Resolve the current download URL of each CMS source file."""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from .sources import DATA_CMS_GOV_CATALOG, PDC_METASTORE, SOURCES, Source


@dataclass(frozen=True)
class ResolvedSource:
    key: str
    url: str
    filename: str
    modified: str | None


def vintage_from_filename(filename: str) -> str | None:
    """'SNF_All_Owners_2026.07.31.csv' -> '2026-07-31'; 'Chain_Performance_20260909.csv' -> '2026-09-09'; 'NH_Penalties_Aug2026.csv' -> '2026-08-01'."""
    m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{4})(\d{2})(\d{2})", filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"_(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(\d{4})", filename)
    if m:
        month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(m.group(1)) + 1
        return f"{m.group(2)}-{month:02d}-01"
    return None


def _pdc_distribution(item: dict) -> str | None:
    for dist in item.get("distribution") or []:
        url = dist.get("downloadURL") or (dist.get("data") or {}).get("downloadURL")
        if url and url.lower().endswith(".csv"):
            return url
    return None


def _catalog_distribution(dataset: dict) -> str | None:
    for dist in dataset.get("distribution") or []:
        url = dist.get("downloadURL")
        if url and url.lower().endswith(".csv") and (dist.get("format") == "CSV" or dist.get("mediaType") == "text/csv"):
            return url
    return None


def resolve_sources(session: requests.Session | None = None, catalog_json: dict | None = None,
                    metastore: dict[str, dict] | None = None) -> dict[str, ResolvedSource]:
    """Look up every source. `catalog_json` and `metastore` allow offline tests."""
    session = session or requests.Session()
    resolved: dict[str, ResolvedSource] = {}
    catalog = catalog_json
    for key, source in SOURCES.items():
        if source.pdc_id:
            item = (metastore or {}).get(source.pdc_id)
            if item is None:
                response = session.get(PDC_METASTORE.format(id=source.pdc_id), timeout=60)
                response.raise_for_status()
                item = response.json()
            url = _pdc_distribution(item)
            if not url:
                raise RuntimeError(f"No CSV distribution for Provider Data Catalog dataset {source.pdc_id} ({source.title})")
            resolved[key] = ResolvedSource(key, url, url.rsplit("/", 1)[-1], item.get("modified"))
        else:
            if catalog is None:
                response = session.get(DATA_CMS_GOV_CATALOG, timeout=120)
                response.raise_for_status()
                catalog = response.json()
            dataset = next((d for d in catalog.get("dataset", []) if d.get("title") == source.title), None)
            if dataset is None:
                raise RuntimeError(f"data.cms.gov catalog has no dataset titled {source.title!r}")
            url = _catalog_distribution(dataset)
            if not url:
                raise RuntimeError(f"No CSV distribution for {source.title!r}")
            resolved[key] = ResolvedSource(key, url, url.rsplit("/", 1)[-1], dataset.get("modified"))
    return resolved


def source_for(key: str) -> Source:
    return SOURCES[key]
