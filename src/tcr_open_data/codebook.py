"""Render the codebook from the release schema so documentation cannot drift from the data."""

from __future__ import annotations

from .schema import load_schema
from .sources import OWNER_ROLE_CODES, REPEALED_AIDE_FLOOR, REPEALED_RN_FLOOR, REPEALED_TOTAL_FLOOR, SOURCES


def render_codebook(chain_measure_columns: list[str] | None = None, release: str | None = None) -> str:
    schema = load_schema()
    lines = ["# Codebook", ""]
    if release:
        lines += [f"Release: **{release}**", ""]
    lines += [
        "Every column carries a provenance tag:",
        "",
        f"- `cms`: {schema['provenance_key']['cms']}",
        f"- `tcr`: {schema['provenance_key']['tcr']}",
        "",
        "## Sources",
        "",
        "| Key | CMS file | Notes |",
        "| --- | --- | --- |",
    ]
    for key, source in SOURCES.items():
        lines.append(f"| `{key}` | {source.title} | {source.notes} |")
    lines += [
        "",
        "## Definitions used in derived columns",
        "",
        f"- Ownership or control roles (CMS-855A role codes): {', '.join(OWNER_ROLE_CODES)}. Additional disclosable parties (role 72), officers, directors and employees are not owners.",
        f"- Rescinded federal staffing minimums tested against reported hours: RN {REPEALED_RN_FLOOR}, nurse aide {REPEALED_AIDE_FLOOR}, total nurse {REPEALED_TOTAL_FLOOR} hours per resident per day.",
        "- Release name: `v` + year and month of the Provider Information Processing Date.",
        "",
    ]
    for table, spec in schema["tables"].items():
        lines += [f"## `{table}`", "", spec["description"], "", f"License: {spec['license']}. Key: {', '.join('`' + k + '`' for k in spec['key'])}.", "",
                  "| Column | Type | Provenance | Source | Description |", "| --- | --- | --- | --- | --- |"]
        for c in spec["columns"]:
            lines.append(f"| `{c['name']}` | {c['type']} | {c['provenance']} | {c['source']} | {c['description']} |")
        if table == "chains":
            if chain_measure_columns:
                lines += ["", "Averaged quality-measure columns in this release (CMS headers normalized to snake_case, provenance `cms`, type number):", ""]
                lines += [f"- `{c}`" for c in chain_measure_columns]
            else:
                lines += ["", "Averaged quality-measure columns follow, named from the CMS headers; see the release manifest for the exact list."]
        lines.append("")
    return "\n".join(lines)
