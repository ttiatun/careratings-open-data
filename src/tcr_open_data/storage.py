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
        s3.upload_file(str(path), config.bucket, key, ExtraArgs={"ContentType": content_type(path)})
    existing = None
    try:
        body = s3.get_object(Bucket=config.bucket, Key="manifest.json")["Body"].read()
        existing = json.loads(body)
    except Exception:  # noqa: BLE001 - first release, or the root manifest is unreadable; start fresh
        existing = None
    root = update_root_manifest(existing, manifest)
    s3.put_object(Bucket=config.bucket, Key="manifest.json", Body=json.dumps(root, indent=2).encode("utf-8"), ContentType=CONTENT_TYPES[".json"])
    summary["root_manifest"] = root
    return summary
