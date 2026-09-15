"""
Archive a release at Zenodo and mint its DOI.

Flow (`tcr-open-data doi --release releases/v2026.08 [--sandbox] [--publish]`):

1. Create a deposition (or a new version of the record behind an existing
   concept DOI) and read the DOI Zenodo pre-reserves for it.
2. Write that DOI into the release's manifest.json, so the copy uploaded to
   Zenodo and the copy in the research store both carry it.
3. Upload every release file listed in the manifest (tables, documents,
   manifest.json) through the deposition's bucket.
4. Set the metadata from .zenodo.json plus the release facts.
5. Optionally publish. Publishing is irreversible; leave it off for a dry run
   and press "Publish" on zenodo.org after checking the draft.

The token comes from ZENODO_TOKEN (ZENODO_SANDBOX_TOKEN with --sandbox) and
needs the deposit:write and deposit:actions scopes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from . import __version__

ZENODO_API = "https://zenodo.org/api"
ZENODO_SANDBOX_API = "https://sandbox.zenodo.org/api"
REPO_ROOT = Path(__file__).resolve().parents[2]


def load_template(root: Path = REPO_ROOT) -> dict:
    return json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))


def build_metadata(manifest: dict, template: dict | None = None, page_url: str | None = None) -> dict:
    """Zenodo deposition metadata for one release: the template plus version, date, sources and citation."""
    template = template or load_template()
    release = manifest["release"]
    page_url = page_url or f"https://thecareratings.com/data/releases/{release}/"
    tables = ", ".join(f"{name} ({info['rows']:,} rows)" for name, info in (manifest.get("tables") or {}).items())
    sources = manifest.get("sources") or {}
    related = [{"identifier": s["url"], "relation": "isDerivedFrom", "resource_type": "dataset"} for s in sources.values() if s.get("url")]
    related.append({"identifier": page_url, "relation": "isDescribedBy", "resource_type": "publication-other"})
    repo = (manifest.get("builder") or {}).get("repository")
    if repo:
        related.append({"identifier": repo, "relation": "isSupplementTo", "resource_type": "software"})
    description = (
        f"<p>{template['description']}</p>"
        f"<p>Release {release}: the CMS vintage with processing date {manifest['processing_date']}, built {manifest['built_at'][:10]} by tcr-open-data {(manifest.get('builder') or {}).get('version', __version__)}. "
        f"Tables: {tables}.</p>"
        "<p>License by layer: CMS source values are U.S. government work in the public domain; derived columns, the arrangement of the release and the documentation are CC BY 4.0; the identifier crosswalk is CC0 1.0; the build code is MIT. See LICENSE-DATA.md inside the release.</p>"
        f"<p>Every file is listed with its SHA-256 checksum in manifest.json. Sources, vintages and the validation report: {page_url}</p>"
    )
    return {
        "upload_type": "dataset",
        "publication_date": manifest["built_at"][:10],
        "title": f"{template['title']}, release {release}",
        "creators": template["creators"],
        "description": description,
        "access_right": "open",
        "license": template.get("license", "cc-by-4.0"),
        "keywords": template.get("keywords", []),
        "version": release,
        "language": "eng",
        "related_identifiers": related,
        "notes": template.get("notes", ""),
    }


def _files_to_upload(release_dir: Path, manifest: dict) -> list[Path]:
    names = [f["path"] for f in manifest.get("files", [])] + [d["path"] for d in manifest.get("documents", [])]
    paths = [release_dir / n for n in names if (release_dir / n).exists()]
    paths.append(release_dir / "manifest.json")
    seen: set[Path] = set()
    unique = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _check(response: requests.Response, what: str) -> dict:
    if response.status_code >= 400:
        raise RuntimeError(f"Zenodo {what} failed: HTTP {response.status_code}: {response.text[:400]}")
    return response.json() if response.text.strip() else {}


def deposit_release(release_dir: Path, token: str, sandbox: bool = False, publish: bool = False, concept_record_id: int | None = None,
                    session: requests.Session | None = None, template: dict | None = None, progress=print) -> dict:
    """Create (or version) a Zenodo deposition for a release, upload its files, set metadata, optionally publish."""
    api = ZENODO_SANDBOX_API if sandbox else ZENODO_API
    session = session or requests.Session()
    headers = {"Authorization": f"Bearer {token}"}
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if concept_record_id:
        created = _check(session.post(f"{api}/deposit/depositions/{concept_record_id}/actions/newversion", headers=headers, timeout=120), "new version")
        draft_url = created["links"].get("latest_draft")
        if not draft_url:
            raise RuntimeError("Zenodo did not return a draft for the new version")
        deposition = _check(session.get(draft_url, headers=headers, timeout=120), "draft lookup")
        for existing in deposition.get("files", []):  # a new version starts with the previous files; replace them
            _check(session.delete(existing["links"]["self"], headers=headers, timeout=120), "old file removal")
    else:
        deposition = _check(session.post(f"{api}/deposit/depositions", json={}, headers=headers, timeout=120), "deposition create")

    dep_id = deposition["id"]
    doi = (deposition.get("metadata") or {}).get("prereserve_doi", {}).get("doi") or deposition.get("doi")
    if not doi:
        raise RuntimeError("Zenodo did not pre-reserve a DOI")
    progress(f"deposition {dep_id}: DOI {doi}")

    if manifest.get("doi") != doi:
        manifest["doi"] = doi
        manifest["doi_url"] = f"https://doi.org/{doi}"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        progress(f"wrote doi into {manifest_path}")

    bucket = deposition["links"]["bucket"]
    uploaded = []
    for path in _files_to_upload(release_dir, manifest):
        with path.open("rb") as handle:
            _check(session.put(f"{bucket}/{path.name}", data=handle, headers=headers, timeout=1800), f"upload {path.name}")
        uploaded.append(path.name)
        progress(f"uploaded {path.name}")

    metadata = build_metadata(manifest, template)
    _check(session.put(f"{api}/deposit/depositions/{dep_id}", json={"metadata": metadata}, headers=headers, timeout=120), "metadata")

    result = {"id": dep_id, "doi": doi, "doi_url": f"https://doi.org/{doi}", "files": uploaded, "published": False,
              "html": (deposition.get("links") or {}).get("html"), "sandbox": sandbox}
    if publish:
        published = _check(session.post(f"{api}/deposit/depositions/{dep_id}/actions/publish", headers=headers, timeout=120), "publish")
        result["published"] = True
        result["concept_doi"] = published.get("conceptdoi")
        result["record_url"] = (published.get("links") or {}).get("record_html") or (published.get("links") or {}).get("html")
        progress(f"published: {result.get('record_url')} concept DOI {result.get('concept_doi')}")
    return result


def token_from_env(sandbox: bool) -> str:
    name = "ZENODO_SANDBOX_TOKEN" if sandbox else "ZENODO_TOKEN"
    token = os.environ.get(name) or (os.environ.get("ZENODO_TOKEN") if sandbox else None)
    if not token:
        raise SystemExit(f"{name} is not set; create a personal access token at {'https://sandbox.zenodo.org' if sandbox else 'https://zenodo.org'}/account/settings/applications/ with deposit:write and deposit:actions")
    return token
