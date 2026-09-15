"""Zenodo deposit flow against a fake API, and the header/CORS rules for the research store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tcr_open_data.storage import CACHE_IMMUTABLE, CACHE_MANIFEST, CACHE_REVALIDATE, cache_control, put_cors
from tcr_open_data.zenodo import build_metadata, deposit_release

TEMPLATE = {"title": "The Care Ratings Open Nursing Home Data", "description": "Monthly releases.", "creators": [{"name": "The Care Ratings"}],
            "license": "cc-by-4.0", "keywords": ["nursing homes"], "notes": "CMS values are public domain."}
MANIFEST = {"release": "v2026.08", "built_at": "2026-09-15T03:37:10+00:00", "processing_date": "2026-08-01",
            "builder": {"name": "tcr-open-data", "version": "0.1.0", "repository": "https://github.com/ttiatun/careratings-open-data"},
            "sources": {"provider_info": {"url": "https://data.cms.gov/x/NH_ProviderInfo_Aug2026.csv"}},
            "tables": {"facilities": {"rows": 14690, "columns": ["ccn"]}},
            "files": [{"table": "facilities", "format": "csv", "path": "facilities.csv", "bytes": 3, "sha256": "x"}],
            "documents": [{"path": "codebook.md", "bytes": 2, "sha256": "y"}, {"path": "missing.md", "bytes": 0, "sha256": "z"}]}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        return self._payload


class FakeZenodo:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.uploaded: dict[str, bytes] = {}

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json))
        if url.endswith("/deposit/depositions"):
            return FakeResponse({"id": 42, "metadata": {"prereserve_doi": {"doi": "10.5072/zenodo.42"}},
                                 "links": {"bucket": "https://sandbox.zenodo.org/api/files/abc", "html": "https://sandbox.zenodo.org/deposit/42"}}, 201)
        if url.endswith("/actions/publish"):
            return FakeResponse({"conceptdoi": "10.5072/zenodo.41", "links": {"record_html": "https://sandbox.zenodo.org/records/42"}}, 202)
        return FakeResponse({"message": "unexpected"}, 500)

    def put(self, url, data=None, json=None, headers=None, timeout=None):
        self.calls.append(("PUT", url, json))
        if "/api/files/" in url:
            self.uploaded[url.rsplit("/", 1)[1]] = data.read()
            return FakeResponse({"key": url.rsplit("/", 1)[1]}, 201)
        return FakeResponse({"id": 42}, 200)


@pytest.fixture
def release_dir(tmp_path: Path) -> Path:
    d = tmp_path / "v2026.08"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (d / "facilities.csv").write_text("a,b\n", encoding="utf-8")
    (d / "codebook.md").write_text("# c\n", encoding="utf-8")
    return d


def test_deposit_reserves_doi_writes_it_into_manifest_and_uploads_every_file(release_dir: Path):
    api = FakeZenodo()
    result = deposit_release(release_dir, "tok", sandbox=True, publish=True, session=api, template=TEMPLATE, progress=lambda *_: None)
    assert result["doi"] == "10.5072/zenodo.42" and result["published"] and result["concept_doi"] == "10.5072/zenodo.41"
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["doi"] == "10.5072/zenodo.42" and manifest["doi_url"] == "https://doi.org/10.5072/zenodo.42"
    assert result["files"] == ["facilities.csv", "codebook.md", "manifest.json"], "missing documents are skipped; manifest.json goes last, with the DOI in it"
    assert json.loads(api.uploaded["manifest.json"])["doi"] == "10.5072/zenodo.42"
    metadata_call = next(c for c in api.calls if c[0] == "PUT" and c[1].endswith("/deposit/depositions/42"))
    meta = metadata_call[2]["metadata"]
    assert meta["version"] == "v2026.08" and meta["publication_date"] == "2026-09-15" and meta["upload_type"] == "dataset"
    assert meta["title"] == "The Care Ratings Open Nursing Home Data, release v2026.08"
    assert {r["relation"] for r in meta["related_identifiers"]} == {"isDerivedFrom", "isDescribedBy", "isSupplementTo"}
    assert "public domain" in meta["description"] and "14,690 rows" in meta["description"]
    assert [c[1] for c in api.calls if c[0] == "POST"][-1].endswith("/deposit/depositions/42/actions/publish")


def test_draft_deposit_does_not_publish(release_dir: Path):
    api = FakeZenodo()
    result = deposit_release(release_dir, "tok", sandbox=True, publish=False, session=api, template=TEMPLATE, progress=lambda *_: None)
    assert result["published"] is False and not any(c[1].endswith("/actions/publish") for c in api.calls)


def test_build_metadata_uses_the_template_creators_and_license():
    meta = build_metadata(MANIFEST, TEMPLATE)
    assert meta["creators"] == [{"name": "The Care Ratings"}] and meta["license"] == "cc-by-4.0" and meta["access_right"] == "open"


def test_cache_control_rules():
    assert cache_control("releases/v2026.08/facilities.csv") == CACHE_IMMUTABLE
    assert cache_control("raw/v2026.08/NH_ProviderInfo_Aug2026.csv") == CACHE_IMMUTABLE
    assert cache_control("history/raw/provider_info/2019-01-17.parquet") == CACHE_IMMUTABLE
    assert cache_control("history/sff/raw/SFFList_20120411093613.pdf") == CACHE_IMMUTABLE
    assert cache_control("history/facilities_history.parquet") == CACHE_REVALIDATE
    assert cache_control("manifest.json") == CACHE_MANIFEST
    assert cache_control("releases/v2026.08/manifest.json") == CACHE_MANIFEST
    assert cache_control("history/sff_manifest.json") == CACHE_MANIFEST


class FakeS3:
    def __init__(self):
        self.cors = None

    def put_bucket_cors(self, Bucket, CORSConfiguration):
        self.cors = CORSConfiguration["CORSRules"]

    def get_bucket_cors(self, Bucket):
        return {"CORSRules": self.cors}


def test_put_cors_rejects_write_methods_and_applies_read_only_rules():
    from tcr_open_data.storage import R2Config

    config = R2Config("acct", "key", "secret", "bucket")
    rules = json.loads((Path(__file__).resolve().parents[1] / "infra" / "r2-cors.json").read_text(encoding="utf-8"))
    s3 = FakeS3()
    summary = put_cors(config, rules, dry_run=False, client=s3)
    assert summary["applied"] and s3.cors == rules and rules[0]["AllowedMethods"] == ["GET", "HEAD"]
    with pytest.raises(ValueError):
        put_cors(config, [{"AllowedOrigins": ["*"], "AllowedMethods": ["PUT"]}], dry_run=True, client=s3)
    assert put_cors(config, rules, dry_run=True, client=FakeS3())["applied"] is False
