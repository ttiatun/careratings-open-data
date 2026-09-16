"""
Command line: download, build, validate, publish, or run the whole release.

    tcr-open-data download --raw raw/next
    tcr-open-data build --raw raw/v2026.08 --out releases
    tcr-open-data validate --release releases/v2026.08 [--strict]
    tcr-open-data publish --release releases/v2026.08 --raw raw/v2026.08 [--live]
    tcr-open-data release [--raw raw/v2026.08] [--publish] [--strict]
    tcr-open-data codebook --out docs/codebook.md
    tcr-open-data backfill --out history [--since --until --retry-failed]
    tcr-open-data reharmonize --out history
    tcr-open-data sff-history --out history
    tcr-open-data publish-history --history history [--live]
    tcr-open-data headers [--prefix releases/] [--live]      # rewrite Content-Type / Cache-Control on stored objects
    tcr-open-data cors [--live]                             # apply infra/r2-cors.json (GET/HEAD only)
    tcr-open-data doi --release releases/v2026.08 [--sandbox] [--publish] [--concept-record-id N]
    tcr-open-data ownership-study --release releases/v2026.08 [--history history] --out analysis/ownership/v2026.08
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
from .history import backfill, consolidate, list_snapshots, reharmonize
from .manifest import write_release_manifest
from .ownership_study import run_study
from .sff import Capture, build_sff_history, fetch_capture, list_captures
from .storage import R2Config, publish, publish_history, put_cors, retag_objects
from .validate import validate_release
from .zenodo import deposit_release, token_from_env

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


def cmd_backfill(args: argparse.Namespace) -> int:
    snapshots = [s for s in list_snapshots() if (not args.since or s.date >= args.since) and (not args.until or s.date <= args.until)]
    if args.limit:
        snapshots = snapshots[: args.limit]
    tables = args.tables.split(",") if args.tables else None
    history = Path(args.out)
    coverage = backfill(history, snapshots, tables=tables, resume=not args.no_resume, retry_failed=args.retry_failed)
    manifest = consolidate(history)
    errors = [r for r in coverage if r.get("error")]
    print(json.dumps({"snapshots": manifest["snapshots"], "tables": manifest["tables"], "errors": len(errors)}, indent=2))
    return 1 if errors and args.strict else 0


def cmd_reharmonize(args: argparse.Namespace) -> int:
    history = Path(args.out)
    tables = args.tables.split(",") if args.tables else None
    coverage = reharmonize(history, tables=tables)
    manifest = consolidate(history)
    print(json.dumps({"snapshots": manifest["snapshots"], "tables": manifest["tables"], "coverage_rows": len(coverage)}, indent=2))
    return 0


def cmd_sff_history(args: argparse.Namespace) -> int:
    history = Path(args.out)
    listing = history / "sff" / "captures.json"
    if args.cached_listing and listing.exists():
        captures = [Capture(**c) for c in json.loads(listing.read_text(encoding="utf-8"))]
    else:
        captures = list_captures()
        listing.parent.mkdir(parents=True, exist_ok=True)
        listing.write_text(json.dumps([c.__dict__ for c in captures], indent=1), encoding="utf-8")
    if args.limit:
        captures = captures[-args.limit:]

    def fetch(capture, cache_dir, session):
        return fetch_capture(capture, cache_dir, session, retries=args.retries, pause=args.pause)

    summary = build_sff_history(captures, history, fetch=fetch, facilities_parquet=history / "facilities_history.parquet")
    print(json.dumps(summary, indent=2))
    return 0


def cmd_publish_history(args: argparse.Namespace) -> int:
    summary = publish_history(Path(args.history), dry_run=not args.live, config=R2Config.from_env())
    print(json.dumps(summary, indent=2))
    return 0


def cmd_headers(args: argparse.Namespace) -> int:
    summary = retag_objects(R2Config.from_env(), prefix=args.prefix, dry_run=not args.live)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_cors(args: argparse.Namespace) -> int:
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    try:
        summary = put_cors(R2Config.from_env(), rules, dry_run=not args.live)
    except Exception as exc:  # noqa: BLE001 - bucket-scoped object tokens cannot change bucket configuration
        if "AccessDenied" not in str(exc):
            raise
        print(f"The API token cannot set bucket configuration ({exc}).", file=sys.stderr)
        print(f"Apply the policy in the Cloudflare dashboard instead: R2 > bucket > Settings > CORS Policy, paste {args.rules}.", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


def cmd_doi(args: argparse.Namespace) -> int:
    token = token_from_env(args.sandbox)
    result = deposit_release(Path(args.release), token, sandbox=args.sandbox, publish=args.publish, concept_record_id=args.concept_record_id)
    print(json.dumps(result, indent=2))
    if not args.publish:
        print("Draft only: check it at the html link above, then re-run with --publish (or press Publish on Zenodo).", file=sys.stderr)
    print("Re-publish the release to the research store so manifest.json carries the DOI: tcr-open-data publish --release <dir> --raw <raw> --live", file=sys.stderr)
    return 0


def cmd_ownership_study(args: argparse.Namespace) -> int:
    history = Path(args.history) if args.history and Path(args.history).exists() else None
    meta = run_study(Path(args.release), Path(args.out), history_dir=history, top_n=args.top)
    print(json.dumps({"release": meta["release"], "history_store": meta["history_store"], "tables": {k: v.get("rows") for k, v in meta["tables"].items()}}, indent=2))
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

    p = sub.add_parser("backfill", help="Pull monthly CMS archive snapshots into the history store (resumable)")
    p.add_argument("--out", default="history")
    p.add_argument("--since", default=None, help="Earliest snapshot date, YYYY-MM-DD")
    p.add_argument("--until", default=None, help="Latest snapshot date, YYYY-MM-DD")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--tables", default=None, help="Comma-separated subset of provider_info,penalties,ownership")
    p.add_argument("--no-resume", action="store_true", help="Reprocess snapshots already recorded in coverage.jsonl")
    p.add_argument("--retry-failed", action="store_true", help="Reprocess snapshots recorded with an error or a missing file")
    p.add_argument("--strict", action="store_true", help="Exit non-zero when any snapshot failed")
    p.set_defaults(func=cmd_backfill)

    p = sub.add_parser("reharmonize", help="Rebuild the harmonized files and history tables from the raw Parquet already on disk")
    p.add_argument("--out", default="history")
    p.add_argument("--tables", default=None, help="Comma-separated subset of provider_info,penalties,ownership")
    p.set_defaults(func=cmd_reharmonize)

    p = sub.add_parser("sff-history", help="Rebuild Special Focus Facility history from archived CMS PDFs")
    p.add_argument("--out", default="history")
    p.add_argument("--limit", type=int, default=None, help="Only the newest N captures")
    p.add_argument("--retries", type=int, default=5, help="Attempts per capture before recording it as unavailable")
    p.add_argument("--pause", type=float, default=2.0, help="Seconds to wait between downloads (the Internet Archive throttles bursts)")
    p.add_argument("--cached-listing", action="store_true", help="Reuse history/sff/captures.json instead of querying the CDX index again")
    p.set_defaults(func=cmd_sff_history)

    p = sub.add_parser("publish-history", help="Upload the history store to R2 under history/ (dry run unless --live)")
    p.add_argument("--history", default="history")
    p.add_argument("--live", action="store_true")
    p.set_defaults(func=cmd_publish_history)

    p = sub.add_parser("headers", help="Rewrite Content-Type and Cache-Control on objects already in the research store (dry run unless --live)")
    p.add_argument("--prefix", default="", help="Only objects under this key prefix, e.g. releases/ or history/")
    p.add_argument("--live", action="store_true")
    p.set_defaults(func=cmd_headers)

    p = sub.add_parser("cors", help="Apply the read-only CORS policy to the research store bucket (dry run unless --live)")
    p.add_argument("--rules", default=str(REPO_ROOT / "infra" / "r2-cors.json"))
    p.add_argument("--live", action="store_true")
    p.set_defaults(func=cmd_cors)

    p = sub.add_parser("doi", help="Archive a release at Zenodo and mint its DOI (draft unless --publish)")
    p.add_argument("--release", required=True, help="Release directory, e.g. releases/v2026.08")
    p.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org (ZENODO_SANDBOX_TOKEN)")
    p.add_argument("--publish", action="store_true", help="Publish the deposition (irreversible)")
    p.add_argument("--concept-record-id", type=int, default=None, help="Record id of the existing Zenodo record to version (later releases)")
    p.set_defaults(func=cmd_doi)

    p = sub.add_parser("ownership-study", help="Write the descriptive tables behind the ownership study from a release (and the history store if present)")
    p.add_argument("--release", required=True, help="Release directory, e.g. releases/v2026.08")
    p.add_argument("--history", default="history", help="History store directory (optional)")
    p.add_argument("--out", required=True, help="Output directory for the CSV tables and summary.md")
    p.add_argument("--top", type=int, default=25, help="Rows in the top-N tables")
    p.set_defaults(func=cmd_ownership_study)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
