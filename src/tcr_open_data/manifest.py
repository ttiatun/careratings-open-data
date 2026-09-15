"""Release manifest and the root manifest that indexes every release."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .download import sha256_of
from .schema import load_schema

LICENSES = {
    "cms_columns": {"name": "U.S. government work, public domain", "url": "https://www.usa.gov/government-works"},
    "tcr_columns": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"},
    "crosswalk": {"name": "CC0 1.0", "url": "https://creativecommons.org/publicdomain/zero/1.0/"},
    "code": {"name": "MIT", "url": "https://opensource.org/license/mit"},
}

DOC_FILES = ["codebook.md", "methodology.md", "LICENSE-DATA.md", "CHANGELOG.md", "validation.json", "build.json"]


def git_commit(repo: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - no git, no commit
        return None


def write_release_manifest(release_dir: Path, repo_root: Path | None = None) -> dict:
    build = json.loads((release_dir / "build.json").read_text(encoding="utf-8"))
    validation = json.loads((release_dir / "validation.json").read_text(encoding="utf-8")) if (release_dir / "validation.json").exists() else None
    schema = load_schema()
    files = []
    for table, info in build["tables"].items():
        for fmt in ("csv", "parquet"):
            path = release_dir / info[fmt]
            files.append({"table": table, "format": fmt, "path": info[fmt], "bytes": path.stat().st_size, "sha256": sha256_of(path),
                          "rows": info["rows"], "columns": len(info["columns"]),
                          "license": "CC0 1.0" if table == "crosswalk" else schema["tables"][table]["license"]})
    docs = [{"path": name, "bytes": (release_dir / name).stat().st_size, "sha256": sha256_of(release_dir / name)}
            for name in DOC_FILES if (release_dir / name).exists()]
    manifest = {
        "release": build["release"],
        "built_at": build["built_at"],
        "processing_date": build["processing_date"],
        "builder": {"name": "tcr-open-data", "version": __version__, "commit": git_commit(repo_root) if repo_root else None,
                    "repository": "https://github.com/ttiatun/careratings-open-data"},
        "publisher": {"name": "The Care Ratings", "url": "https://thecareratings.com/"},
        "sources": build["sources"],
        "tables": {t: {"rows": i["rows"], "columns": i["columns"]} for t, i in build["tables"].items()},
        "chain_measure_columns": build.get("chain_measure_columns", []),
        "files": files,
        "documents": docs,
        "validation": validation,
        "licenses": LICENSES,
        "citation": f"The Care Ratings. {build['release']} Open Nursing Home Data. Built from CMS public files. https://thecareratings.com/data/",
    }
    (release_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def update_root_manifest(existing: dict | None, release_manifest: dict, prefix: str = "releases") -> dict:
    """Merge a release into the root manifest (newest first, latest pointer)."""
    root = existing or {"format": 1, "publisher": release_manifest["publisher"], "releases": []}
    entry = {
        "release": release_manifest["release"], "built_at": release_manifest["built_at"],
        "processing_date": release_manifest["processing_date"], "path": f"{prefix}/{release_manifest['release']}/",
        "manifest": f"{prefix}/{release_manifest['release']}/manifest.json",
        "validation_status": (release_manifest.get("validation") or {}).get("status"),
    }
    releases = [r for r in root.get("releases", []) if r["release"] != entry["release"]]
    releases.append(entry)
    releases.sort(key=lambda r: r["release"], reverse=True)
    root["releases"] = releases
    root["latest"] = releases[0]["release"]
    root["updated_at"] = datetime.now(timezone.utc).isoformat()
    return root
