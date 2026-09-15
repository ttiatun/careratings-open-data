"""CSV header guards."""

from __future__ import annotations

import csv
from pathlib import Path

from .sources import Source


class HeaderMismatch(Exception):
    def __init__(self, source: Source, missing: list[str], unexpected: list[str], path: Path):
        self.source, self.missing, self.unexpected, self.path = source, missing, unexpected, path
        super().__init__(
            f"{source.title} ({path.name}): CMS header changed. Missing: {missing}. Unexpected: {unexpected}. "
            "Update sources.py and the build before releasing; nothing was written."
        )


def read_header(path: Path) -> list[str]:
    # Headers are ASCII in every CMS file; tolerate Latin-1 bytes further down the first line.
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return [h.strip() for h in next(csv.reader(handle))]


def check_header(source: Source, path: Path) -> list[str]:
    """Return the actual header after confirming it carries every expected column."""
    actual = read_header(path)
    have = set(actual)
    missing = [h for h in source.header if h not in have]
    known = set(source.header)
    unexpected = [] if source.allow_extra_columns else [h for h in actual if h not in known]
    if missing or unexpected:
        raise HeaderMismatch(source, missing, unexpected, path)
    if source.allow_extra_columns and tuple(actual[: len(source.header)]) != tuple(source.header):
        raise HeaderMismatch(source, [], actual[: len(source.header)], path)
    return actual


def snake(name: str) -> str:
    """'Average overall 5-star rating' -> 'average_overall_5_star_rating'."""
    out = []
    prev_underscore = False
    for ch in name.strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_underscore = False
        elif not prev_underscore:
            out.append("_")
            prev_underscore = True
    return "".join(out).strip("_")
