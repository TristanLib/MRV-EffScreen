#!/usr/bin/env python3
"""Week-6 sensitivity analysis for MRV consistency-review thresholds."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
TABLE_DIR = ROOT / "reports" / "tables"
FIGURE_DIR = ROOT / "reports" / "figures"
SCORES_PATH = TABLE_DIR / "mrv_anomaly_scores.csv"

CONTAMINATIONS = [0.01, 0.02, 0.05]
TOP_K = 200


def load_score_rows() -> list[dict[str, str]]:
    with SCORES_PATH.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def row_id(row: dict[str, str]) -> str:
    return "|".join(
        [
            row["ship_type"],
            row["reporting_year"],
            row["report_scope"],
            row["imo_number"],
            row["ship_name"],
        ]
    )


def method_flags(row: dict[str, str], contamination: float) -> dict[str, bool]:
    threshold = 1.0 - contamination
    return {
        "isolation": float(row["isolation_rank_pct_ship_type"]) >= threshold,
        "lof": float(row["lof_rank_pct_ship_type"]) >= threshold,
        "residual": float(row["residual_rank_pct_ship_type"]) >= threshold,
    }


def make_sets(rows: list[dict[str, str]], contamination: float) -> dict[str, set[str]]:
    sets = {
        "isolation": set(),
        "lof": set(),
        "residual": set(),
        "isolation_and_lof": set(),
        "isolation_and_residual": set(),
        "lof_and_residual": set(),
        "all_three": set(),
        "at_least_two": set(),
        "any_method": set(),
    }
    for row in rows:
        rid = row_id(row)
        flags = method_flags(row, contamination)
        positives = {name for name, value in flags.items() if value}
        for name in positives:
            sets[name].add(rid)
        if {"isolation", "lof"} <= positives:
            sets["isolation_and_lof"].add(rid)
        if {"isolation", "residual"} <= positives:
            sets["isolation_and_residual"].add(rid)
        if {"lof", "residual"} <= positives:
            sets["lof_and_residual"].add(rid)
        if len(positives) == 3:
            sets["all_three"].add(rid)
        if len(positives) >= 2:
            sets["at_least_two"].add(rid)
        if positives:
            sets["any_method"].add(rid)
    return sets


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_summary(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[float, dict[str, set[str]]]]:
    top_rows = sorted(rows, key=lambda row: float(row["consensus_score"]), reverse=True)[:TOP_K]
    top_ids = {row_id(row) for row in top_rows}
    sets_by_threshold = {contamination: make_sets(rows, contamination) for contamination in CONTAMINATIONS}
    baseline = sets_by_threshold[0.02]
    summary = []
    for contamination in CONTAMINATIONS:
        sets = sets_by_threshold[contamination]
        summary.append(
            {
                "contamination": f"{contamination:.2%}",
                "isolation_top_rows": str(len(sets["isolation"])),
                "lof_top_rows": str(len(sets["lof"])),
                "residual_top_rows": str(len(sets["residual"])),
                "isolation_lof_overlap": str(len(sets["isolation_and_lof"])),
                "isolation_residual_overlap": str(len(sets["isolation_and_residual"])),
                "lof_residual_overlap": str(len(sets["lof_and_residual"])),
                "all_three_methods": str(len(sets["all_three"])),
                "at_least_two_methods": str(len(sets["at_least_two"])),
                "any_method": str(len(sets["any_method"])),
                "top200_at_least_two_methods": str(len(top_ids & sets["at_least_two"])),
                "top200_all_three_methods": str(len(top_ids & sets["all_three"])),
                "jaccard_at_least_two_vs_2pct": f"{jaccard(sets['at_least_two'], baseline['at_least_two']):.6f}",
                "jaccard_all_three_vs_2pct": f"{jaccard(sets['all_three'], baseline['all_three']):.6f}",
            }
        )
    return summary, sets_by_threshold


def build_top200_membership(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    top_rows = sorted(rows, key=lambda row: float(row["consensus_score"]), reverse=True)[:TOP_K]
    out = []
    for rank, row in enumerate(top_rows, start=1):
        item = {
            "consensus_rank": str(rank),
            "ship_type": row["ship_type"],
            "reporting_year": row["reporting_year"],
            "report_scope": row["report_scope"],
            "efficiency_label_distance": row["efficiency_label_distance"],
            "consensus_score": row["consensus_score"],
        }
        for contamination in CONTAMINATIONS:
            flags = method_flags(row, contamination)
            positives = sum(1 for value in flags.values() if value)
            label = f"{int(contamination * 100)}pct"
            item[f"flags_{label}"] = str(positives)
            item[f"at_least_two_{label}"] = str(positives >= 2).lower()
            item[f"all_three_{label}"] = str(positives == 3).lower()
        out.append(item)
    return out


def build_ship_type_counts(rows: list[dict[str, str]], sets_by_threshold: dict[float, dict[str, set[str]]]) -> list[dict[str, str]]:
    row_by_id = {row_id(row): row for row in rows}
    out = []
    for contamination in CONTAMINATIONS:
        for definition in ["all_three", "at_least_two"]:
            counter = Counter(row_by_id[rid]["ship_type"] for rid in sets_by_threshold[contamination][definition])
            total = sum(counter.values()) or 1
            for ship_type, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
                out.append(
                    {
                        "contamination": f"{contamination:.2%}",
                        "candidate_definition": definition,
                        "ship_type": ship_type,
                        "rows": str(count),
                        "share": f"{count / total:.6f}",
                    }
                )
    return out


def escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def draw_grouped_bar_chart(
    path: Path,
    labels: list[str],
    series: dict[str, list[int]],
    title: str,
    y_label: str,
) -> None:
    width, height = 860, 480
    margin_left, margin_right, margin_top, margin_bottom = 80, 28, 58, 82
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_value = max(max(values) for values in series.values())
    max_value = max(1, int(max_value * 1.15))
    colors = {"all_three_methods": "#2f6f73", "at_least_two_methods": "#8f5f2a", "any_method": "#4f6f9f"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="30" text-anchor="middle" font-family="Arial" font-size="18" fill="#1f2933">{escape_xml(title)}</text>',
        f'<text x="18" y="{margin_top + plot_h / 2}" transform="rotate(-90 18 {margin_top + plot_h / 2})" text-anchor="middle" font-family="Arial" font-size="12" fill="#52606d">{escape_xml(y_label)}</text>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{width - margin_right}" y2="{margin_top + plot_h}" stroke="#9aa5b1" stroke-width="1"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#9aa5b1" stroke-width="1"/>',
    ]
    for tick in range(6):
        value = max_value * tick / 5
        y = margin_top + plot_h - (value / max_value) * plot_h
        parts.append(f'<line x1="{margin_left - 4}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#e4e7eb" stroke-width="1"/>')
        parts.append(f'<text x="{margin_left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#52606d">{value:.0f}</text>')
    group_w = plot_w / len(labels)
    names = list(series)
    bar_w = min(54, group_w / (len(names) + 1))
    for idx, label in enumerate(labels):
        group_x = margin_left + idx * group_w
        for jdx, name in enumerate(names):
            value = series[name][idx]
            x = group_x + (group_w - bar_w * len(names)) / 2 + jdx * bar_w
            bar_h = (value / max_value) * plot_h
            y = margin_top + plot_h - bar_h
            parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w - 4:.2f}" height="{bar_h:.2f}" fill="{colors[name]}"/>')
            parts.append(f'<text x="{x + (bar_w - 4) / 2:.2f}" y="{y - 5:.2f}" text-anchor="middle" font-family="Arial" font-size="10" fill="#323f4b">{value}</text>')
        parts.append(f'<text x="{group_x + group_w / 2:.2f}" y="{margin_top + plot_h + 22}" text-anchor="middle" font-family="Arial" font-size="12" fill="#323f4b">{escape_xml(label)}</text>')
    legend_x = margin_left
    for idx, name in enumerate(names):
        x = legend_x + idx * 210
        y = height - 24
        parts.append(f'<rect x="{x}" y="{y - 10}" width="12" height="12" fill="{colors[name]}"/>')
        parts.append(f'<text x="{x + 18}" y="{y}" font-family="Arial" font-size="11" fill="#323f4b">{escape_xml(name.replace("_", " "))}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def make_figures(summary: list[dict[str, str]]) -> None:
    labels = [row["contamination"] for row in summary]
    series = {
        "all_three_methods": [int(row["all_three_methods"]) for row in summary],
        "at_least_two_methods": [int(row["at_least_two_methods"]) for row in summary],
        "any_method": [int(row["any_method"]) for row in summary],
    }
    draw_grouped_bar_chart(
        FIGURE_DIR / "mrv_anomaly_sensitivity_overlap.svg",
        labels,
        series,
        "Consistency-review sensitivity across contamination thresholds",
        "candidate rows",
    )


def main() -> None:
    rows = load_score_rows()
    summary, sets_by_threshold = build_summary(rows)
    write_csv(TABLE_DIR / "mrv_anomaly_sensitivity_summary.csv", summary)
    write_csv(TABLE_DIR / "mrv_anomaly_sensitivity_top200_membership.csv", build_top200_membership(rows))
    write_csv(TABLE_DIR / "mrv_anomaly_sensitivity_ship_type_counts.csv", build_ship_type_counts(rows, sets_by_threshold))
    make_figures(summary)


if __name__ == "__main__":
    main()
