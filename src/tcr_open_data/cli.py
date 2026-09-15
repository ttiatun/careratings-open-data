"""
Command line: download, build, validate, publish, or run the whole release.

    tcr-open-data download --raw raw/next
    tcr-open-data build --raw raw/v2026.08 --out releases
    tcr-open-data validate --release releases/v2026.08 [--strict]
    tcr-open-data publish --release releases/v2026.08 --raw raw/v2026.08 [--live]
    tcr-open-data release [--raw raw/v2026.08] [--publish] [--strict]
    tcr-open-data codebook --out docs/codebook.md
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .build import build_release
from .codebook import render_codebook
from .download import download_all, load_sources_json
from .manifest import write_release_manifest
from .storage import R2Config, publish
from .validate import validate_release

REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy_docs(release_dir: Path, chain_measure_columns: list[str], release: str) -> None:
    (release_dir / "codebook.md").write_text(render_codebook(chain_measure_columns, release), encoding="utf-8")
    for name in ("methodology.md",):
        src = REPO_ROOT / "docs" / name
        if src.exists():
            shutil.copyfile(src, release_dir / name)
    for name in ("LICENSE-DATA.md", "CHANGELOG.md"):
        src = REPO_ROOT / name
        if src.exists():
            shutil.copyfile(src, release_dir / name)


def cmd_download(args: argparse.Namespace) -> int:
    entries = download_all(Path(args.raw), force=args.force)
    print(json.dumps({k: {"filename": v["filename"], "bytes": v["bytes"], "vintage": v["vintage"]} for k, v in entries.items()}, indent=2))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    raw = Path(args.raw)
    result = build_release(raw, Path(args.out), load_sources_json(raw), release=args.release)
    _copy_docs(result.release_dir, result.chain_measure_columns, result.release)
    print(json.dumps({"release": result.release, "dir": str(result.release_dir), "tables": {t: i["rows"] for t, i in result.tables.items()}}, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    report = validate_release(Path(args.release), strict=args.strict)
    print(json.dumps(report.to_dict(), indent=2))
    return 1 if report.failed else 0


def cmd_manifest(args: argparse.Namespace) -> int:
    manifest = write_release_manifest(Path(args.release), REPO_ROOT)
    print(json.dumps({"release": manifest["release"], "files": len(manifest["files"]), "validation": (manifest.get("validation") or {}).get("status")}, indent=2))
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    release_dir = Path(args.release)
    if not (release_dir / "manifest.json").exists():
        write_release_manifest(release_dir, REPO_ROOT)
    config = R2Config.from_env()
    summary = publish(release_dir, Path(args.raw) if args.raw else None, dry_run=not args.live, config=config)
    print(json.dumps({k: v for k, v in summary.items() if k != "root_manifest"}, indent=2))
    if summary.get("root_manifest"):
        print(json.dumps(summary["root_manifest"], indent=2))
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    raw = Path(args.raw) if args.raw else Path("raw") / "next"
    if not args.raw:
        download_all(raw, force=args.force)
    sources = load_sources_json(raw)
    result = build_release(raw, Path(args.out), sources)
    if not args.raw and raw.name == "next":
        final_raw = raw.parent / result.release
        if final_raw.exists():
            shutil.rmtree(final_raw)
        raw.rename(final_raw)
        raw = final_raw
    _copy_docs(result.release_dir, result.chain_measure_columns, result.release)
    report = validate_release(result.release_dir, strict=args.strict)
    manifest = write_release_manifest(result.release_dir, REPO_ROOT)
    print(json.dumps({"release": result.release, "validation": report.to_dict()["status"], "files": len(manifest["files"])}, indent=2))
    if report.failed:
        print("Validation failed; not publishing.", file=sys.stderr)
        return 1
    if args.publish:
        summary = publish(result.release_dir, raw, dry_run=not args.live, config=R2Config.from_env())
        print(json.dumps({k: v for k, v in summary.items() if k != "root_manifest"}, indent=2))
    return 0


def cmd_codebook(args: argparse.Namespace) -> int:
    text = render_codebook()
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tcr-open-data", description="Build The Care Ratings open nursing-home data releases from CMS files.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("download", help="Fetch the current CMS files into a raw directory")
    p.add_argument("--raw", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("build", help="Build release tables from a raw directory")
    p.add_argument("--raw", required=True)
    p.add_argument("--out", default="releases")
    p.add_argument("--release", default=None, help="Override the release name (default: v<year>.<month> of the Provider Information Processing Date)")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("validate", help="Validate a built release")
    p.add_argument("--release", required=True)
    p.add_argument("--strict", action="store_true", help="Treat reconciliation warnings as failures")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("manifest", help="Write the release manifest")
    p.add_argument("--release", required=True)
    p.set_defaults(func=cmd_manifest)

    p = sub.add_parser("publish", help="Upload a release to the research store (dry run unless --live)")
    p.add_argument("--release", required=True)
    p.add_argument("--raw", default=None)
    p.add_argument("--live", action="store_true")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("release", help="Download (unless --raw), build, validate, and optionally publish")
    p.add_argument("--raw", default=None)
    p.add_argument("--out", default="releases")
    p.add_argument("--force", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--publish", action="store_true")
    p.add_argument("--live", action="store_true")
    p.set_defaults(func=cmd_release)

    p = sub.add_parser("codebook", help="Render docs/codebook.md from the schema")
    p.add_argument("--out", default=str(REPO_ROOT / "docs" / "codebook.md"))
    p.set_defaults(func=cmd_codebook)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
