"""Layout-mode text clean-up for column-wise SFF pages."""

from __future__ import annotations

from tcr_open_data.sff import ROW_NOCCN, collapse_layout_line


def test_collapse_layout_line_restores_a_row():
    raw = "          W oodley Manor Health & Rehabilitation      3312 W oodley Road        Montgomery   AL   36116   334‐288‐2780   11/05/2016   14   "
    line = collapse_layout_line(raw)
    assert line == "Woodley Manor Health & Rehabilitation 3312 Woodley Road Montgomery AL 36116 334-288-2780 11/05/2016 14"
    m = ROW_NOCCN.match(line)
    assert m and m.group("state") == "AL" and m.group("inspection") == "11/05/2016" and m.group("months") == "14"


def test_collapse_layout_line_keeps_real_single_letter_words():
    assert collapse_layout_line("Mission Point Nursing A Belding   414 E State St") == "Mission Point Nursing A Belding 414 E State St"
    assert collapse_layout_line("Careage Of Newton   2130 West 18th Street South") == "Careage Of Newton 2130 West 18th Street South"
