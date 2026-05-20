#!/usr/bin/env python3
"""Audit IMO recurrence across temporal MRV classification splits."""

from __future__ import annotations

import csv
from itertools import combinations
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "processed" / "mrv_modeling_base.csv"
TABLE_DIR = ROOT / "reports" / "tables"
FIGURE_DIR = ROOT / "reports" / "figures"

SPLITS = ["train", "holdout_2022", "test_2023", "external_2024"]
SPLIT_LABELS = {
    "train": "Train 2018-2021",
    "holdout_2022": "Holdout 2022",
    "test_2023": "Test 2023",
    "external_2024": "External 2024",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def split_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    out = {split: [] for split in SPLITS}
    for row in rows:
        split = row.get("temporal_split", "")
        if split not in out:
            continue
        if not row.get("efficiency_label_distance"):
            continue
        out[split].append(row)
    return out


def imo_set(rows: list[dict[str, str]]) -> set[str]:
    return {row["imo_number"] for row in rows if row.get("imo_number")}


def build_split_counts(grouped: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    out = []
    for split in SPLITS:
        rows = grouped[split]
        imos = imo_set(rows)
        out.append(
            {
                "temporal_split": split,
                "display_name": SPLIT_LABELS[split],
                "labeled_rows": str(len(rows)),
                "unique_imo_numbers": str(len(imos)),
                "rows_without_imo": str(sum(1 for row in rows if not row.get("imo_number"))),
            }
        )
    return out


def build_overlap_rows(grouped: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    split_imos = {split: imo_set(rows) for split, rows in grouped.items()}
    out = []
    for split_a, split_b in combinations(SPLITS, 2):
        imos_a = split_imos[split_a]
        imos_b = split_imos[split_b]
        overlap = imos_a & imos_b
        out.append(
            {
                "split_a": split_a,
                "split_b": split_b,
                "display_pair": f"{SPLIT_LABELS[split_a]} vs {SPLIT_LABELS[split_b]}",
                "unique_imo_a": str(len(imos_a)),
                "unique_imo_b": str(len(imos_b)),
                "overlap_imo_numbers": str(len(overlap)),
                "overlap_pct_of_a": f"{len(overlap) / len(imos_a):.6f}" if imos_a else "0.000000",
                "overlap_pct_of_b": f"{len(overlap) / len(imos_b):.6f}" if imos_b else "0.000000",
            }
        )
    return out


def draw_overlap_figure(rows: list[dict[str, str]]) -> None:
    train_rows = [row for row in rows if row["split_a"] == "train"]
    labels = [row["split_b"].replace("_", " ") for row in train_rows]
    values = [float(row["overlap_pct_of_b"]) for row in train_rows]
    width, height = 760, 420
    margin_left, margin_right, margin_top, margin_bottom = 80, 30, 58, 92
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_value = max(1.0, max(values, default=1.0))
    bar_gap = 34
    bar_w = max(42, (plot_w - bar_gap * max(0, len(values) - 1)) / max(1, len(values)))
    colors = ["#2f6f73", "#4f6f9f", "#8f5f2a"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="30" text-anchor="middle" font-family="Arial" font-size="18" fill="#1f2933">Train-set IMO overlap with later-year splits</text>',
        f'<text x="20" y="{margin_top + plot_h / 2}" transform="rotate(-90 20 {margin_top + plot_h / 2})" text-anchor="middle" font-family="Arial" font-size="12" fill="#52606d">overlap fraction of later split</text>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{width - margin_right}" y2="{margin_top + plot_h}" stroke="#9aa5b1" stroke-width="1"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#9aa5b1" stroke-width="1"/>',
    ]
    for tick in range(6):
        value = tick / 5 * max_value
        y = margin_top + plot_h - (value / max_value) * plot_h
        parts.append(f'<line x1="{margin_left - 4}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#e4e7eb" stroke-width="1"/>')
        parts.append(f'<text x="{margin_left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#52606d">{value:.2f}</text>')
    for idx, value in enumerate(values):
        x = margin_left + idx * (bar_w + bar_gap)
        bar_h = (value / max_value) * plot_h
        y = margin_top + plot_h - bar_h
        label_x = x + bar_w / 2
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" fill="{colors[idx % len(colors)]}"/>')
        parts.append(f'<text x="{label_x:.2f}" y="{y - 6:.2f}" text-anchor="middle" font-family="Arial" font-size="11" fill="#1f2933">{value:.3f}</text>')
        parts.append(f'<text x="{label_x:.2f}" y="{margin_top + plot_h + 24}" text-anchor="middle" font-family="Arial" font-size="11" fill="#323f4b">{escape_xml(labels[idx])}</text>')
    parts.append("</svg>")
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIGURE_DIR / "mrv_temporal_imo_overlap.svg").write_text("\n".join(parts), encoding="utf-8")


def escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def main() -> None:
    rows = read_csv(DATA_PATH)
    grouped = split_rows(rows)
    split_counts = build_split_counts(grouped)
    overlap_rows = build_overlap_rows(grouped)
    write_csv(TABLE_DIR / "mrv_temporal_split_imo_counts.csv", split_counts)
    write_csv(TABLE_DIR / "mrv_temporal_imo_overlap.csv", overlap_rows)
    draw_overlap_figure(overlap_rows)


if __name__ == "__main__":
    main()
