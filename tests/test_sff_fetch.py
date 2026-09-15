"""SFF capture downloads: cut-off responses are retried, archive-truncated captures kept and marked, dashes normalized."""

from __future__ import annotations

from pathlib import Path

import pytest

from tcr_open_data.sff import CRAWL_CAP, DASHES, Capture, ROW_NOCCN, fetch_capture, is_complete_pdf, looks_truncated

GOOD = b"%PDF-1.4\n1 0 obj\nendobj\ntrailer\n%%EOF\n"
CUT = b"%PDF-1.4\n1 0 obj\n" + b"x" * 100
CUT_WITH_EARLY_EOF = b"%PDF-1.6\nlinearized\n%%EOF\n" + b"x" * 4000


class FakeResponse:
    def __init__(self, content: bytes, status: int = 200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls, self.headers = list(responses), [], {}

    def get(self, url, timeout=None):
        self.calls.append(url)
        return self.responses.pop(0)


def test_cut_off_download_is_retried_then_cached(tmp_path: Path):
    capture = Capture("20241203082645", "X", 1)
    session = FakeSession([FakeResponse(CUT), FakeResponse(GOOD)])
    sleeps = []
    path = fetch_capture(capture, tmp_path, session, retries=3, pause=0, sleep=sleeps.append)
    assert path.read_bytes() == GOOD and len(session.calls) == 2 and sleeps == [1.0]
    assert fetch_capture(capture, tmp_path, FakeSession([]), pause=0) == path, "a complete cached file is not downloaded again"


def test_archive_truncated_capture_is_kept_and_marked(tmp_path: Path):
    capture = Capture("20230609151532", "X", 1)
    session = FakeSession([FakeResponse(CUT_WITH_EARLY_EOF)] * 3)
    path = fetch_capture(capture, tmp_path, session, retries=3, pause=0, sleep=lambda *_: None)
    assert path.read_bytes() == CUT_WITH_EARLY_EOF and len(session.calls) == 3
    assert path.with_suffix(".truncated").exists()
    assert fetch_capture(capture, tmp_path, FakeSession([]), pause=0) == path, "the marker stops later runs from fetching it again"


def test_cut_off_cache_file_without_marker_is_replaced(tmp_path: Path):
    capture = Capture("20241203082645", "X", 1)
    (tmp_path / "SFFList_20241203082645.pdf").write_bytes(CUT)
    session = FakeSession([FakeResponse(GOOD)])
    fetch_capture(capture, tmp_path, session, pause=0, sleep=lambda *_: None)
    assert session.calls and (tmp_path / "SFFList_20241203082645.pdf").read_bytes() == GOOD


def test_non_pdf_responses_give_up(tmp_path: Path):
    session = FakeSession([FakeResponse(b"<html>")] * 2)
    with pytest.raises(RuntimeError, match="gave up after 2 attempts"):
        fetch_capture(Capture("20120411093613", "X", 1), tmp_path, session, retries=2, pause=0, sleep=lambda *_: None)


def test_pdf_checks_and_dash_normalization():
    assert is_complete_pdf(GOOD) and not is_complete_pdf(CUT) and not is_complete_pdf(b"<html>")
    assert not looks_truncated(GOOD) and looks_truncated(CUT) and looks_truncated(CUT_WITH_EARLY_EOF)
    assert looks_truncated(GOOD + b" " * (CRAWL_CAP - len(GOOD))), "a capture of exactly 1 MiB hit the crawl cap"
    line = "Estrella Center 350 East La Canada Avondale AZ 85323 623‐932‑2282 10".translate(DASHES)
    assert ROW_NOCCN.match(line).group("phone") == "623-932-2282"
