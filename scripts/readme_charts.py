"""
Regenerate the README figures from the history store.

    python scripts/readme_charts.py                 # reads ./history (build it with `tcr-open-data backfill` and `sff-history`)
    python scripts/readme_charts.py --source /path/to/history

Writes docs/images/certified-nursing-homes.svg, docs/images/sff-status.svg and
docs/images/history-coverage.svg as plain SVG (no plotting library), so the
figures render on GitHub in light and dark themes and stay reproducible.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"

# Reference palette from the dataviz method: categorical slot 1 (blue) and slot 2 (orange),
# light chart surface and ink tokens. Validated for colour-vision separation and contrast.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
SURFACE = "#fcfcfb"
BORDER = "#e6e5e1"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#ecebe7"
FONT = "font-family='ui-sans-serif, system-ui, -apple-system, Segoe UI, Helvetica, Arial, sans-serif'"


def load(source: str) -> tuple[list[tuple[dt.date, int, int, int, int]], list[dt.date]]:
    con = duckdb.connect()
    if source.startswith("http"):
        con.execute("INSTALL httpfs; LOAD httpfs;")
    base = source.rstrip("/")
    facilities = f"{base}/history/facilities_history.parquet" if source.startswith("http") else str(Path(source) / "facilities_history.parquet")
    editions = f"{base}/history/sff_editions.parquet" if source.startswith("http") else str(Path(source) / "sff_editions.parquet")
    snapshots = con.execute(f"""
        SELECT snapshot_date, header_era,
               COUNT(*) FILTER (WHERE special_focus_status IN ('SFF', 'Y')) AS sff,
               COUNT(*) FILTER (WHERE special_focus_status = 'SFF Candidate') AS candidate,
               COUNT(*) AS facilities
        FROM read_parquet('{facilities}') GROUP BY 1, 2 ORDER BY 1""").fetchall()
    dates = [r[0] for r in con.execute(f"SELECT DISTINCT edition_date FROM read_parquet('{editions}') WHERE edition_date IS NOT NULL ORDER BY 1").fetchall()]
    con.close()
    return snapshots, dates


def fmt(n: float) -> str:
    return f"{n:,.0f}"


def x_scale(d: dt.date, d0: dt.date, d1: dt.date, x0: float, x1: float) -> float:
    return x0 + (d - d0).days / max(1, (d1 - d0).days) * (x1 - x0)


def year_ticks(d0: dt.date, d1: dt.date) -> list[dt.date]:
    return [dt.date(y, 1, 1) for y in range(d0.year + (d0 != dt.date(d0.year, 1, 1)), d1.year + 1)]


def svg_open(width: int, height: int, title: str, subtitle: str) -> list[str]:
    return [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}' role='img' aria-labelledby='t d'>",
        f"<title id='t'>{title}</title><desc id='d'>{subtitle}</desc>",
        f"<rect x='0.5' y='0.5' width='{width - 1}' height='{height - 1}' rx='10' fill='{SURFACE}' stroke='{BORDER}'/>",
        f"<text x='24' y='34' {FONT} font-size='17' font-weight='700' fill='{INK}'>{title}</text>",
        f"<text x='24' y='54' {FONT} font-size='12.5' fill='{INK2}'>{subtitle}</text>",
    ]


def line_chart(path: Path, series: list[tuple[str, str, list[tuple[dt.date, float]]]], title: str, subtitle: str, note: str,
               y_min: float, y_max: float, y_step: float, width: int = 880, height: int = 360) -> None:
    left, right, top, bottom = 64, 176, 76, 60
    x0, x1, y0, y1 = left, width - right, height - bottom, top
    d0 = min(p[0] for _, _, pts in series for p in pts)
    d1 = max(p[0] for _, _, pts in series for p in pts)

    def sy(v: float) -> float:
        return y0 - (v - y_min) / (y_max - y_min) * (y0 - y1)

    out = svg_open(width, height, title, subtitle)
    v = y_min
    while v <= y_max + 1e-9:
        out.append(f"<line x1='{x0}' x2='{x1}' y1='{sy(v):.1f}' y2='{sy(v):.1f}' stroke='{GRID}'/>")
        out.append(f"<text x='{x0 - 8}' y='{sy(v) + 4:.1f}' {FONT} font-size='11' fill='{MUTED}' text-anchor='end'>{fmt(v)}</text>")
        v += y_step
    for tick in year_ticks(d0, d1):
        x = x_scale(tick, d0, d1, x0, x1)
        out.append(f"<line x1='{x:.1f}' x2='{x:.1f}' y1='{y0}' y2='{y0 + 4}' stroke='{MUTED}'/>")
        out.append(f"<text x='{x:.1f}' y='{y0 + 18}' {FONT} font-size='11' fill='{MUTED}' text-anchor='middle'>{tick.year}</text>")
    out.append(f"<line x1='{x0}' x2='{x1}' y1='{y0}' y2='{y0}' stroke='{MUTED}'/>")
    for name, colour, pts in series:
        d = " ".join(f"{'M' if i == 0 else 'L'}{x_scale(p[0], d0, d1, x0, x1):.1f},{sy(p[1]):.1f}" for i, p in enumerate(pts))
        out.append(f"<path d='{d}' fill='none' stroke='{colour}' stroke-width='2' stroke-linejoin='round' stroke-linecap='round'/>")
        first, last = pts[0], pts[-1]
        for p in (first, last):
            out.append(f"<circle cx='{x_scale(p[0], d0, d1, x0, x1):.1f}' cy='{sy(p[1]):.1f}' r='4' fill='{colour}' stroke='{SURFACE}' stroke-width='2'/>")
        end_label = f"{fmt(last[1])} {name}" if len(series) > 1 else f"{fmt(last[1])} in {last[0].strftime('%b %Y')}"
        out.append(f"<text x='{x1 + 10}' y='{sy(last[1]) + 4:.1f}' {FONT} font-size='12' font-weight='600' fill='{INK}'>{end_label}</text>")
        out.append(f"<text x='{x_scale(first[0], d0, d1, x0, x1) + 8:.1f}' y='{sy(first[1]) - 8:.1f}' {FONT} font-size='11' fill='{INK2}'>{fmt(first[1])} in {first[0].strftime('%b %Y')}</text>")
    if len(series) > 1:
        lx = x0
        for name, colour, _ in series:
            out.append(f"<rect x='{lx}' y='{height - 26}' width='14' height='4' rx='2' fill='{colour}'/>")
            out.append(f"<text x='{lx + 20}' y='{height - 21}' {FONT} font-size='11.5' fill='{INK2}'>{name}</text>")
            lx += 20 + 7 * len(name) + 24
    out.append(f"<text x='{width - 24}' y='{height - 21}' {FONT} font-size='11' fill='{MUTED}' text-anchor='end'>{note}</text>")
    out.append("</svg>")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def coverage_chart(path: Path, snapshots: list[dt.date], editions: list[dt.date], release_date: dt.date, release: str, doi: str,
                   width: int = 880, height: int = 250) -> None:
    left, right = 262, 40
    x0, x1 = left, width - right
    d0, d1 = dt.date(2012, 1, 1), dt.date(2027, 1, 1)
    rows = [
        ("Monthly CMS snapshots", f"{len(snapshots)} snapshots, {snapshots[0].strftime('%b %Y')} to {snapshots[-1].strftime('%b %Y')}", snapshots, BLUE),
        ("Special Focus Facility editions", f"{len(editions)} editions, {editions[0].strftime('%b %Y')} to {editions[-1].strftime('%b %Y')}", editions, ORANGE),
        ("Release " + release, f"{release_date.strftime('%d %b %Y')} · DOI {doi}", [release_date], INK2),
    ]
    out = svg_open(width, height, "What the research store covers",
                   "Every tick is one archived CMS file or PDF edition that was parsed into the history tables.")
    base_y = 100
    for tick in range(2012, 2028):
        x = x_scale(dt.date(tick, 1, 1), d0, d1, x0, x1)
        out.append(f"<line x1='{x:.1f}' x2='{x:.1f}' y1='{base_y - 14}' y2='{base_y + 3 * 40 - 20}' stroke='{GRID}'/>")
        if tick < 2027:
            out.append(f"<text x='{x + 2:.1f}' y='{base_y + 3 * 40 - 8}' {FONT} font-size='11' fill='{MUTED}'>{tick}</text>")
    for i, (label, sub, dates, colour) in enumerate(rows):
        y = base_y + i * 40
        out.append(f"<text x='{x0 - 12}' y='{y - 2}' {FONT} font-size='12' font-weight='600' fill='{INK}' text-anchor='end'>{label}</text>")
        out.append(f"<text x='{x0 - 12}' y='{y + 12}' {FONT} font-size='10.5' fill='{INK2}' text-anchor='end'>{sub}</text>")
        for d in dates:
            x = x_scale(d, d0, d1, x0, x1)
            out.append(f"<rect x='{x - 1:.1f}' y='{y - 10}' width='2' height='16' rx='1' fill='{colour}'/>")
    out.append("</svg>")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(ROOT / "history") if (ROOT / "history").exists() else "https://data.thecareratings.com")
    parser.add_argument("--release", default="v2026.08")
    parser.add_argument("--release-date", default="2026-09-15")
    parser.add_argument("--doi", default="10.5281/zenodo.22780105")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    snapshots, editions = load(args.source)
    dates = [r[0] for r in snapshots]

    line_chart(OUT / "certified-nursing-homes.svg",
               [("certified nursing homes", BLUE, [(r[0], r[4]) for r in snapshots])],
               "Certified nursing homes in the United States, monthly",
               "Facilities in the CMS Provider Information file, one point per archived monthly snapshot.",
               "Source: CMS Care Compare archive via facilities_history", 14_400, 15_800, 200)

    sff_pts = [(r[0], r[2]) for r in snapshots]
    cand_pts = [(r[0], r[3]) for r in snapshots if r[1] >= 2]  # the candidate flag exists from the October 2020 file format on
    line_chart(OUT / "sff-status.svg",
               [("SFFs", BLUE, sff_pts), ("candidates", ORANGE, cand_pts)],
               "Special Focus Facilities and candidates, monthly",
               f"Facilities flagged in each snapshot. The candidate flag first appears in the {cand_pts[0][0].strftime('%B %Y')} file format.",
               "Source: facilities_history.special_focus_status", 0, 500, 100)

    coverage_chart(OUT / "history-coverage.svg", dates, editions, dt.date.fromisoformat(args.release_date), args.release, args.doi)
    for name in ("certified-nursing-homes.svg", "sff-status.svg", "history-coverage.svg"):
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
