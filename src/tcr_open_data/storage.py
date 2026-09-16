"""
Publish a release to the research store (Cloudflare R2 through the S3 API).

Layout in the bucket:
    raw/<release>/<original CMS filenames> + sources.json
    releases/<release>/<tables>.csv|.parquet, manifest.json, codebook.md, ...
    manifest.json                       (root index of releases, newest first)

Configuration (environment):
    TCR_R2_ACCOUNT_ID, TCR_R2_ACCESS_KEY_ID, TCR_R2_SECRET_ACCESS_KEY, TCR_R2_BUCKET (default careratings-open-data)
"""

from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

from .manifest import update_root_manifest

CONTENT_TYPES = {".csv": "text/csv; charset=utf-8", ".parquet": "application/vnd.apache.parquet", ".json": "application/json",
                 ".md": "text/markdown; charset=utf-8"}


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
CACHE_REVALIDATE = "public, max-age=3600, must-revalidate"
CACHE_MANIFEST = "public, max-age=300, must-revalidate"


def cache_control(key: str) -> str:
    """Release and raw objects never change once published; per-snapshot history files never change either.
    Manifests and the stacked history tables are rebuilt, so they must revalidate."""
    name = key.rsplit("/", 1)[-1]
    if name in ("manifest.json", "sff_manifest.json", "sources.json"):
        return CACHE_MANIFEST
    if key.startswith(("releases/", "raw/")):
        return CACHE_IMMUTABLE
    if key.startswith(("history/raw/", "history/harmonized/", "history/sff/raw/")):
        return CACHE_IMMUTABLE
    if key.startswith("analysis/"):
        return CACHE_MANIFEST  # study tables and site files are regenerated when a study is corrected
    return CACHE_REVALIDATE


def upload_args(key: str, path: Path) -> dict:
    return {"ContentType": content_type(path), "CacheControl": cache_control(key)}


@dataclass
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str

    @classmethod
    def from_env(cls) -> "R2Config | None":
        account = os.environ.get("TCR_R2_ACCOUNT_ID")
        key = os.environ.get("TCR_R2_ACCESS_KEY_ID")
        secret = os.environ.get("TCR_R2_SECRET_ACCESS_KEY")
        if not (account and key and secret):
            return None
        return cls(account, key, secret, os.environ.get("TCR_R2_BUCKET", "careratings-open-data"))

    @property
    def endpoint(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"


def plan_uploads(release_dir: Path, raw_dir: Path | None, release: str) -> list[tuple[Path, str]]:
    """Local path -> object key for everything a release publishes."""
    uploads: list[tuple[Path, str]] = []
    for path in sorted(release_dir.iterdir()):
        if path.is_file():
            uploads.append((path, f"releases/{release}/{path.name}"))
    if raw_dir and raw_dir.exists():
        for path in sorted(raw_dir.iterdir()):
            if path.is_file() and not path.name.endswith(".part"):
                uploads.append((path, f"raw/{release}/{path.name}"))
    return uploads


def plan_history_uploads(history_dir: Path) -> list[tuple[Path, str]]:
    """Every file under the history directory, keyed under history/ in the bucket (temporary CSVs excluded)."""
    uploads: list[tuple[Path, str]] = []
    for path in sorted(history_dir.rglob("*")):
        if not path.is_file() or path.suffix == ".part" or path.name.endswith(".jsonl"):
            continue
        if path.suffix == ".csv" and path.parent != history_dir:
            continue
        uploads.append((path, "history/" + path.relative_to(history_dir).as_posix()))
    return uploads


def plan_analysis_uploads(analysis_dir: Path) -> list[tuple[Path, str]]:
    """Every file of one study run (`analysis/<study>/<release>/`), keyed under the same path in the bucket."""
    analysis_dir = analysis_dir.resolve()
    study, release = analysis_dir.parent.name, analysis_dir.name
    if analysis_dir.parent.parent.name != "analysis" or not study or not release:
        raise ValueError(f"expected analysis/<study>/<release>, got {analysis_dir}")
    prefix = f"analysis/{study}/{release}/"
    return [(path, prefix + path.relative_to(analysis_dir).as_posix()) for path in sorted(analysis_dir.rglob("*"))
            if path.is_file() and path.suffix in (".csv", ".json", ".md", ".parquet")]


def analysis_pointer(analysis_dir: Path) -> tuple[str, dict]:
    """The `analysis/<study>/latest.json` object the site reads to find the newest study run."""
    analysis_dir = analysis_dir.resolve()
    study, release = analysis_dir.parent.name, analysis_dir.name
    meta = json.loads((analysis_dir / "study.json").read_text(encoding="utf-8")) if (analysis_dir / "study.json").exists() else {}
    pointer = {"study": study, "release": release, "path": f"analysis/{study}/{release}/", "built_at": meta.get("built_at"),
               "processing_date": meta.get("processing_date"), "doi": meta.get("doi"), "tables": sorted(meta.get("tables", {}))}
    return f"analysis/{study}/latest.json", pointer


def publish_analysis(analysis_dir: Path, dry_run: bool = True, config: R2Config | None = None, client=None) -> dict:
    """Upload one study run and point `analysis/<study>/latest.json` at it."""
    uploads = plan_analysis_uploads(analysis_dir)
    pointer_key, pointer = analysis_pointer(analysis_dir)
    summary = {"bucket": config.bucket if config else None, "objects": len(uploads), "bytes": sum(p.stat().st_size for p, _ in uploads),
               "pointer": pointer_key, "release": pointer["release"], "dry_run": dry_run, "sample": [k for _, k in uploads[:12]]}
    if dry_run:
        return summary
    if config is None:
        raise RuntimeError("R2 configuration is missing (TCR_R2_ACCOUNT_ID, TCR_R2_ACCESS_KEY_ID, TCR_R2_SECRET_ACCESS_KEY)")
    s3 = client or _client(config)
    for path, key in uploads:
        s3.upload_file(str(path), config.bucket, key, ExtraArgs=upload_args(key, path))
    s3.put_object(Bucket=config.bucket, Key=pointer_key, Body=json.dumps(pointer, indent=2).encode("utf-8"),
                  ContentType="application/json", CacheControl=CACHE_MANIFEST)
    return summary


def publish_history(history_dir: Path, dry_run: bool = True, config: R2Config | None = None, client=None) -> dict:
    uploads = plan_history_uploads(history_dir)
    summary = {"bucket": config.bucket if config else None, "objects": len(uploads), "bytes": sum(p.stat().st_size for p, _ in uploads), "dry_run": dry_run,
               "sample": [k for _, k in uploads[:12]]}
    if dry_run:
        return summary
    if config is None:
        raise RuntimeError("R2 configuration is missing (TCR_R2_ACCOUNT_ID, TCR_R2_ACCESS_KEY_ID, TCR_R2_SECRET_ACCESS_KEY)")
    s3 = client or _client(config)
    for path, key in uploads:
        s3.upload_file(str(path), config.bucket, key, ExtraArgs=upload_args(key, path))
    return summary


def _client(config: R2Config):
    import boto3
    from botocore.config import Config

    return boto3.client("s3", endpoint_url=config.endpoint, aws_access_key_id=config.access_key_id,
                        aws_secret_access_key=config.secret_access_key, region_name="auto", config=Config(signature_version="s3v4"))


def publish(release_dir: Path, raw_dir: Path | None, dry_run: bool = True, config: R2Config | None = None, client=None) -> dict:
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    release = manifest["release"]
    uploads = plan_uploads(release_dir, raw_dir, release)
    summary = {"release": release, "bucket": config.bucket if config else None, "objects": [k for _, k in uploads], "dry_run": dry_run}
    if dry_run:
        return summary
    if config is None:
        raise RuntimeError("R2 configuration is missing (TCR_R2_ACCOUNT_ID, TCR_R2_ACCESS_KEY_ID, TCR_R2_SECRET_ACCESS_KEY)")
    s3 = client or _client(config)
    for path, key in uploads:
        s3.upload_file(str(path), config.bucket, key, ExtraArgs=upload_args(key, path))
    existing = None
    try:
        body = s3.get_object(Bucket=config.bucket, Key="manifest.json")["Body"].read()
        existing = json.loads(body)
    except Exception:  # noqa: BLE001 - first release, or the root manifest is unreadable; start fresh
        existing = None
    root = update_root_manifest(existing, manifest)
    s3.put_object(Bucket=config.bucket, Key="manifest.json", Body=json.dumps(root, indent=2).encode("utf-8"), ContentType=CONTENT_TYPES[".json"],
                  CacheControl=CACHE_MANIFEST)
    summary["root_manifest"] = root
    return summary


def list_keys(config: R2Config, prefix: str = "", client=None) -> list[str]:
    s3 = client or _client(config)
    keys: list[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=config.bucket, Prefix=prefix):
        keys.extend(o["Key"] for o in page.get("Contents", []))
    return keys


def retag_objects(config: R2Config, prefix: str = "", dry_run: bool = True, client=None) -> dict:
    """Rewrite Content-Type and Cache-Control on every object under a prefix (copy onto itself with replaced metadata)."""
    s3 = client or _client(config)
    keys = list_keys(config, prefix, client=s3)
    plan = [(key, content_type(Path(key)), cache_control(key)) for key in keys]
    if not dry_run:
        for key, ctype, cache in plan:
            s3.copy_object(Bucket=config.bucket, Key=key, CopySource={"Bucket": config.bucket, "Key": key},
                           MetadataDirective="REPLACE", ContentType=ctype, CacheControl=cache)
    by_cache: dict[str, int] = {}
    for _key, _ctype, cache in plan:
        by_cache[cache] = by_cache.get(cache, 0) + 1
    return {"bucket": config.bucket, "prefix": prefix, "objects": len(plan), "by_cache_control": by_cache, "dry_run": dry_run}


def put_cors(config: R2Config, rules: list[dict], dry_run: bool = True, client=None) -> dict:
    """Apply a CORS policy (S3 PutBucketCors). Read-only rules: GET and HEAD from any origin."""
    s3 = client or _client(config)
    for rule in rules:
        bad = [m for m in rule.get("AllowedMethods", []) if m not in ("GET", "HEAD")]
        if bad:
            raise ValueError(f"CORS rule allows {bad}; the research store is read-only for browsers")
    if not dry_run:
        s3.put_bucket_cors(Bucket=config.bucket, CORSConfiguration={"CORSRules": rules})
    current = None
    if not dry_run:
        current = s3.get_bucket_cors(Bucket=config.bucket).get("CORSRules")
    return {"bucket": config.bucket, "rules": rules, "applied": not dry_run, "current": current}
