#!/usr/bin/env python3
"""Week-5 anomaly screening for MRV consistency analysis."""

from __future__ import annotations

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor, IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

sys.path.append(str(Path(__file__).resolve().parent))

from train_mrv_baselines import escape_xml, load_rows, parse_float, truncate, write_csv  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
TABLE_DIR = ROOT / "reports" / "tables"
FIGURE_DIR = ROOT / "reports" / "figures"

RANDOM_STATE = 42
CONTAMINATION = 0.02
MIN_SHIP_TYPE_ROWS = 300
TOP_CANDIDATES = 200

ANOMALY_FEATURES = [
    "technical_efficiency_value",
    "total_fuel_consumption_mt",
    "fuel_per_distance_kg_nm",
    "total_co2_emissions_mt",
    "co2_per_distance_kg_nm",
    "time_spent_at_sea_hours",
]

RESIDUAL_FEATURES = [
    "technical_efficiency_value",
    "total_fuel_consumption_mt",
    "fuel_per_distance_kg_nm",
    "total_co2_emissions_mt",
    "time_spent_at_sea_hours",
]

CORE_REQUIRED_FIELDS = [
    "total_fuel_consumption_mt",
    "fuel_per_distance_kg_nm",
    "total_co2_emissions_mt",
    "co2_per_distance_kg_nm",
    "time_spent_at_sea_hours",
]


def eligible_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    eligible = []
    for row in rows:
        if row.get("report_scope") == "partial_er":
            continue
        if row.get("is_full_year") != "true":
            continue
        if not row.get("ship_type"):
            continue
        if not has_positive_core_values(row):
            continue
        eligible.append(row)
    return eligible


def has_positive_core_values(row: dict[str, str]) -> bool:
    for field in CORE_REQUIRED_FIELDS:
        value = parse_float(row.get(field, ""))
        if not math.isfinite(value) or value <= 0:
            return False
    return True


def group_by_ship_type(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["ship_type"]].append(row)
    return dict(grouped)


def make_matrix(rows: list[dict[str, str]], fields: list[str]) -> np.ndarray:
    matrix = np.empty((len(rows), len(fields)), dtype=float)
    for row_idx, row in enumerate(rows):
        for col_idx, field in enumerate(fields):
            matrix[row_idx, col_idx] = safe_log1p(parse_float(row.get(field, "")))
    return matrix


def safe_log1p(value: float) -> float:
    if not math.isfinite(value):
        return np.nan
    return math.log1p(max(value, 0.0))


def rank_percentiles(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = (np.arange(len(values), dtype=float) + 1.0) / max(1, len(values))
    return ranks


def robust_signed_z(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    median = float(np.nanmedian(values))
    mad = float(np.nanmedian(np.abs(values - median)))
    scale = 1.4826 * mad
    if not math.isfinite(scale) or scale < 1e-9:
        scale = float(np.nanstd(values))
    if not math.isfinite(scale) or scale < 1e-9:
        scale = 1.0
    return (values - median) / scale


def score_ship_type(ship_type: str, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    anomaly_matrix = make_matrix(rows, ANOMALY_FEATURES)
    scaled_matrix = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", RobustScaler()),
        ]
    ).fit_transform(anomaly_matrix)

    isolation = IsolationForest(
        n_estimators=300,
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    isolation.fit(scaled_matrix)
    isolation_score = -isolation.score_samples(scaled_matrix)
    isolation_pct = rank_percentiles(isolation_score)

    n_neighbors = min(35, max(5, len(rows) - 1))
    lof = LocalOutlierFactor(
        n_neighbors=n_neighbors,
        contamination=CONTAMINATION,
        n_jobs=-1,
    )
    lof.fit_predict(scaled_matrix)
    lof_score = -lof.negative_outlier_factor_
    lof_pct = rank_percentiles(lof_score)

    residual_matrix = make_matrix(rows, RESIDUAL_FEATURES)
    target = np.array([safe_log1p(parse_float(row["co2_per_distance_kg_nm"])) for row in rows], dtype=float)
    residual_model = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            (
                "model",
                HistGradientBoostingRegressor(
                    learning_rate=0.06,
                    max_iter=140,
                    max_leaf_nodes=31,
                    l2_regularization=0.05,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )
    folds = min(3, len(rows))
    cv = KFold(n_splits=folds, shuffle=True, random_state=RANDOM_STATE)
    predicted_log = cross_val_predict(residual_model, residual_matrix, target, cv=cv)
    signed_residual = target - predicted_log
    residual_abs_z = np.abs(robust_signed_z(signed_residual))
    residual_pct = rank_percentiles(residual_abs_z)
    predicted_target = np.expm1(predicted_log)

    feature_signed_z = {
        field: robust_signed_z(make_matrix(rows, [field]).reshape(-1))
        for field in ANOMALY_FEATURES
    }

    scored_rows = []
    for idx, row in enumerate(rows):
        method_flags = {
            "isolation_top2pct": isolation_pct[idx] >= 1.0 - CONTAMINATION,
            "lof_top2pct": lof_pct[idx] >= 1.0 - CONTAMINATION,
            "residual_top2pct": residual_pct[idx] >= 1.0 - CONTAMINATION,
        }
        flag_count = sum(1 for value in method_flags.values() if value)
        consensus = float(np.mean([isolation_pct[idx], lof_pct[idx], residual_pct[idx]]))
        dominant_fields = dominant_deviation_fields(feature_signed_z, idx)
        scored_rows.append(
            {
                "ship_type": ship_type,
                "reporting_year": row["reporting_year"],
                "report_scope": row["report_scope"],
                "temporal_split": row["temporal_split"],
                "imo_number": row["imo_number"],
                "ship_name": row["ship_name"],
                "technical_efficiency_type": row["technical_efficiency_type"],
                "technical_efficiency_value": row["technical_efficiency_value"],
                "total_fuel_consumption_mt": row["total_fuel_consumption_mt"],
                "fuel_per_distance_kg_nm": row["fuel_per_distance_kg_nm"],
                "total_co2_emissions_mt": row["total_co2_emissions_mt"],
                "co2_per_distance_kg_nm": row["co2_per_distance_kg_nm"],
                "time_spent_at_sea_hours": row["time_spent_at_sea_hours"],
                "efficiency_label_distance": row["efficiency_label_distance"],
                "distance_efficiency_rank_pct": row["distance_efficiency_rank_pct"],
                "isolation_score": isolation_score[idx],
                "isolation_rank_pct_ship_type": isolation_pct[idx],
                "lof_score": lof_score[idx],
                "lof_rank_pct_ship_type": lof_pct[idx],
                "predicted_co2_per_distance_kg_nm": max(0.0, float(predicted_target[idx])),
                "residual_signed_log": signed_residual[idx],
                "residual_abs_z": residual_abs_z[idx],
                "residual_rank_pct_ship_type": residual_pct[idx],
                "consensus_score": consensus,
                "method_flags_count": flag_count,
                "isolation_top2pct": method_flags["isolation_top2pct"],
                "lof_top2pct": method_flags["lof_top2pct"],
                "residual_top2pct": method_flags["residual_top2pct"],
                "dominant_deviation_fields": dominant_fields,
                "screening_explanation": screening_explanation(
                    method_flags,
                    signed_residual[idx],
                    dominant_fields,
                ),
            }
        )
    return scored_rows


def dominant_deviation_fields(feature_signed_z: dict[str, np.ndarray], idx: int) -> str:
    candidates = []
    for field, values in feature_signed_z.items():
        z_value = float(values[idx])
        if not math.isfinite(z_value):
            continue
        direction = "high" if z_value >= 0 else "low"
        candidates.append((abs(z_value), f"{field}:{direction}:z={abs(z_value):.2f}"))
    candidates.sort(reverse=True)
    if not candidates:
        return "no finite robust deviations among screening fields"
    return "; ".join(label for _score, label in candidates[:3])


def screening_explanation(flags: dict[str, bool], signed_residual: float, dominant_fields: str) -> str:
    parts = []
    if flags["isolation_top2pct"] and flags["lof_top2pct"]:
        parts.append("Isolation Forest and LOF both place this row in the ship-type top 2% multivariate outliers")
    elif flags["isolation_top2pct"]:
        parts.append("Isolation Forest places this row in the ship-type top 2% multivariate outliers")
    elif flags["lof_top2pct"]:
        parts.append("LOF places this row in the ship-type top 2% local-density outliers")

    if flags["residual_top2pct"]:
        direction = "above" if signed_residual > 0 else "below"
        parts.append(f"reported CO2 per distance is {direction} the residual model expectation")

    if dominant_fields:
        parts.append(f"largest robust deviations are {dominant_fields}")

    return "; ".join(parts)


def format_scored_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    formatted = []
    for row in rows:
        formatted.append(
            {
                "ship_type": row["ship_type"],
                "reporting_year": row["reporting_year"],
                "report_scope": row["report_scope"],
                "temporal_split": row["temporal_split"],
                "imo_number": row["imo_number"],
                "ship_name": row["ship_name"],
                "technical_efficiency_type": row["technical_efficiency_type"],
                "technical_efficiency_value": row["technical_efficiency_value"],
                "total_fuel_consumption_mt": row["total_fuel_consumption_mt"],
                "fuel_per_distance_kg_nm": row["fuel_per_distance_kg_nm"],
                "total_co2_emissions_mt": row["total_co2_emissions_mt"],
                "co2_per_distance_kg_nm": row["co2_per_distance_kg_nm"],
                "time_spent_at_sea_hours": row["time_spent_at_sea_hours"],
                "efficiency_label_distance": row["efficiency_label_distance"],
                "distance_efficiency_rank_pct": row["distance_efficiency_rank_pct"],
                "isolation_score": f"{float(row['isolation_score']):.6f}",
                "isolation_rank_pct_ship_type": f"{float(row['isolation_rank_pct_ship_type']):.6f}",
                "lof_score": f"{float(row['lof_score']):.6f}",
                "lof_rank_pct_ship_type": f"{float(row['lof_rank_pct_ship_type']):.6f}",
                "predicted_co2_per_distance_kg_nm": f"{float(row['predicted_co2_per_distance_kg_nm']):.6f}",
                "residual_signed_log": f"{float(row['residual_signed_log']):.6f}",
                "residual_abs_z": f"{float(row['residual_abs_z']):.6f}",
                "residual_rank_pct_ship_type": f"{float(row['residual_rank_pct_ship_type']):.6f}",
                "consensus_score": f"{float(row['consensus_score']):.6f}",
                "consensus_rank_pct_global": f"{float(row['consensus_rank_pct_global']):.6f}",
                "method_flags_count": str(int(row["method_flags_count"])),
                "isolation_top2pct": str(row["isolation_top2pct"]).lower(),
                "lof_top2pct": str(row["lof_top2pct"]).lower(),
                "residual_top2pct": str(row["residual_top2pct"]).lower(),
                "dominant_deviation_fields": row["dominant_deviation_fields"],
                "screening_explanation": row["screening_explanation"],
            }
        )
    return formatted


def method_overlap_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    total = len(rows)
    rules = [
        ("isolation_top2pct", lambda row: row["isolation_top2pct"]),
        ("lof_top2pct", lambda row: row["lof_top2pct"]),
        ("residual_top2pct", lambda row: row["residual_top2pct"]),
        ("isolation_and_lof", lambda row: row["isolation_top2pct"] and row["lof_top2pct"]),
        ("isolation_and_residual", lambda row: row["isolation_top2pct"] and row["residual_top2pct"]),
        ("lof_and_residual", lambda row: row["lof_top2pct"] and row["residual_top2pct"]),
        (
            "all_three_methods",
            lambda row: row["isolation_top2pct"] and row["lof_top2pct"] and row["residual_top2pct"],
        ),
    ]
    out = []
    for name, predicate in rules:
        count = sum(1 for row in rows if predicate(row))
        out.append(
            {
                "overlap_rule": name,
                "rows": str(count),
                "share_of_modeled_rows": f"{count / total:.6f}" if total else "0.000000",
            }
        )
    count = min(TOP_CANDIDATES, total)
    out.append(
        {
            "overlap_rule": "consensus_global_top200",
            "rows": str(count),
            "share_of_modeled_rows": f"{count / total:.6f}" if total else "0.000000",
        }
    )
    return out


def ship_type_candidate_counts(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    top_rows = sorted(rows, key=lambda row: float(row["consensus_score"]), reverse=True)[:TOP_CANDIDATES]
    counter = Counter(row["ship_type"] for row in top_rows)
    return [
        {
            "ship_type": ship_type,
            "top_candidate_rows": str(count),
            "share_of_top_candidates": f"{count / max(1, len(top_rows)):.6f}",
        }
        for ship_type, count in counter.most_common()
    ]


def write_run_summary(
    all_rows: list[dict[str, str]],
    eligible: list[dict[str, str]],
    modeled: list[dict[str, Any]],
    skipped: list[dict[str, str]],
) -> None:
    top = max(modeled, key=lambda row: float(row["consensus_score"]))
    rows = [
        {"metric": "all_processed_rows", "value": str(len(all_rows))},
        {"metric": "eligible_full_year_rows", "value": str(len(eligible))},
        {"metric": "modeled_rows", "value": str(len(modeled))},
        {"metric": "minimum_ship_type_rows", "value": str(MIN_SHIP_TYPE_ROWS)},
        {"metric": "contamination_per_method", "value": f"{CONTAMINATION:.4f}"},
        {"metric": "top_candidates_written", "value": str(TOP_CANDIDATES)},
        {"metric": "modeled_ship_types", "value": str(len({row["ship_type"] for row in modeled}))},
        {"metric": "skipped_ship_types", "value": str(len(skipped))},
        {"metric": "highest_consensus_ship_type", "value": top["ship_type"]},
        {"metric": "highest_consensus_year", "value": top["reporting_year"]},
        {"metric": "highest_consensus_score", "value": f"{float(top['consensus_score']):.6f}"},
    ]
    write_csv(TABLE_DIR / "mrv_anomaly_run_summary.csv", rows)


def paper_results_index_rows() -> list[dict[str, str]]:
    return [
        {
            "result_block": "dataset_audit",
            "artifact": "reports/tables/mrv_workbook_inventory.csv",
            "primary_use": "Data source coverage and annual workbook inventory",
            "notes": "Supports the data section and reproducibility statement.",
        },
        {
            "result_block": "baseline_temporal",
            "artifact": "reports/tables/mrv_baseline_metrics.csv",
            "primary_use": "Main temporal, external-year, and random-split classification metrics",
            "notes": "Use temporal 2023 results as the main predictive benchmark.",
        },
        {
            "result_block": "baseline_figures",
            "artifact": "reports/figures/mrv_baseline_macro_f1_temporal_test.svg",
            "primary_use": "Visual comparison of model Macro-F1 on 2023 temporal test",
            "notes": "Pair with balanced accuracy and random-vs-temporal figures.",
        },
        {
            "result_block": "ship_type_ablation",
            "artifact": "reports/tables/mrv_ship_type_comparison_summary.csv",
            "primary_use": "Unified vs ship-type-specific model comparison",
            "notes": "Use to support heterogeneous value of ship-type stratification.",
        },
        {
            "result_block": "feature_importance",
            "artifact": "reports/tables/mrv_permutation_importance.csv",
            "primary_use": "Permutation importance for non-leakage operational model",
            "notes": "Use as interpretability evidence.",
        },
        {
            "result_block": "medium_error_analysis",
            "artifact": "reports/tables/mrv_medium_error_aggregate.csv",
            "primary_use": "Main source of middle-class confusion",
            "notes": "Use to explain boundary ambiguity of tertile labels.",
        },
        {
            "result_block": "anomaly_screening",
            "artifact": "reports/tables/mrv_anomaly_top_candidates.csv",
            "primary_use": "Top MRV consistency-screening candidates",
            "notes": "Describe strictly as anomaly-screening candidates, not violations.",
        },
        {
            "result_block": "anomaly_figures",
            "artifact": "reports/figures/mrv_anomaly_score_distribution.svg",
            "primary_use": "Distribution of consensus anomaly scores",
            "notes": "Pair with top-candidate ship-type distribution.",
        },
    ]


def draw_histogram(path: Path, values: list[float], title: str, x_label: str) -> None:
    width, height = 860, 460
    margin_left, margin_right, margin_top, margin_bottom = 72, 28, 58, 62
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    bins = np.linspace(0, 1, 31)
    counts, edges = np.histogram(values, bins=bins)
    max_count = max(int(counts.max()), 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="30" text-anchor="middle" font-family="Arial" font-size="18" fill="#1f2933">{escape_xml(title)}</text>',
        f'<text x="{width / 2}" y="{height - 16}" text-anchor="middle" font-family="Arial" font-size="12" fill="#52606d">{escape_xml(x_label)}</text>',
        f'<text x="18" y="{margin_top + plot_h / 2}" transform="rotate(-90 18 {margin_top + plot_h / 2})" text-anchor="middle" font-family="Arial" font-size="12" fill="#52606d">rows</text>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{width - margin_right}" y2="{margin_top + plot_h}" stroke="#9aa5b1" stroke-width="1"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#9aa5b1" stroke-width="1"/>',
    ]
    for tick in range(6):
        value = max_count * tick / 5
        y = margin_top + plot_h - (value / max_count) * plot_h
        parts.append(f'<line x1="{margin_left - 4}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#e4e7eb" stroke-width="1"/>')
        parts.append(f'<text x="{margin_left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#52606d">{value:.0f}</text>')
    bar_gap = 2
    bar_w = (plot_w - bar_gap * (len(counts) - 1)) / len(counts)
    for idx, count in enumerate(counts):
        x = margin_left + idx * (bar_w + bar_gap)
        bar_h = (count / max_count) * plot_h
        y = margin_top + plot_h - bar_h
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" fill="#2f6f73"/>')
    for tick in range(6):
        x_value = tick / 5
        x = margin_left + x_value * plot_w
        parts.append(f'<text x="{x:.2f}" y="{margin_top + plot_h + 18}" text-anchor="middle" font-family="Arial" font-size="11" fill="#52606d">{x_value:.1f}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def draw_count_bar_chart(path: Path, labels: list[str], values: list[int], title: str, y_label: str) -> None:
    width, height = 980, 520
    margin_left, margin_right, margin_top, margin_bottom = 76, 26, 58, 150
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_value = max(values, default=1)
    max_value = max(1, math.ceil(max_value * 1.15))
    colors = ["#2f6f73", "#8f5f2a", "#4f6f9f", "#a64d4d", "#5e6c84", "#6f5e9c"]
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
    bar_gap = 12
    bar_w = max(12, (plot_w - bar_gap * max(0, len(values) - 1)) / max(1, len(values)))
    for idx, value in enumerate(values):
        x = margin_left + idx * (bar_w + bar_gap)
        bar_h = (value / max_value) * plot_h
        y = margin_top + plot_h - bar_h
        label_x = x + bar_w / 2
        label_y = margin_top + plot_h + 18
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" fill="{colors[idx % len(colors)]}"/>')
        parts.append(f'<text x="{label_x:.2f}" y="{y - 5:.2f}" text-anchor="middle" font-family="Arial" font-size="10" fill="#323f4b">{value}</text>')
        label = truncate(labels[idx], 32)
        parts.append(f'<text x="{label_x:.2f}" y="{label_y:.2f}" transform="rotate(50 {label_x:.2f} {label_y:.2f})" text-anchor="start" font-family="Arial" font-size="10" fill="#323f4b">{escape_xml(label)}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def make_figures(rows: list[dict[str, Any]], ship_counts: list[dict[str, str]], overlaps: list[dict[str, str]]) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    draw_histogram(
        FIGURE_DIR / "mrv_anomaly_score_distribution.svg",
        [float(row["consensus_score"]) for row in rows],
        "MRV anomaly-screening consensus score distribution",
        "consensus score",
    )

    top_ship_counts = ship_counts[:12]
    draw_count_bar_chart(
        FIGURE_DIR / "mrv_anomaly_top_ship_types.svg",
        [row["ship_type"] for row in top_ship_counts],
        [int(row["top_candidate_rows"]) for row in top_ship_counts],
        f"Top {TOP_CANDIDATES} anomaly-screening candidates by ship type",
        "candidate rows",
    )

    selected_overlaps = [
        row
        for row in overlaps
        if row["overlap_rule"]
        in {"isolation_top2pct", "lof_top2pct", "residual_top2pct", "all_three_methods", "consensus_global_top200"}
    ]
    draw_count_bar_chart(
        FIGURE_DIR / "mrv_anomaly_method_overlap.svg",
        [row["overlap_rule"] for row in selected_overlaps],
        [int(row["rows"]) for row in selected_overlaps],
        "Anomaly-screening method overlap",
        "rows",
    )


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    all_rows = load_rows()
    eligible = eligible_rows(all_rows)
    grouped = group_by_ship_type(eligible)

    scored: list[dict[str, Any]] = []
    skipped = []
    for ship_type, group_rows in sorted(grouped.items()):
        if len(group_rows) < MIN_SHIP_TYPE_ROWS:
            skipped.append({"ship_type": ship_type, "eligible_rows": str(len(group_rows)), "reason": "below_min_ship_type_rows"})
            continue
        scored.extend(score_ship_type(ship_type, group_rows))

    consensus_percentiles = rank_percentiles(np.array([float(row["consensus_score"]) for row in scored], dtype=float))
    for row, pct in zip(scored, consensus_percentiles, strict=True):
        row["consensus_rank_pct_global"] = pct

    scored.sort(key=lambda row: float(row["consensus_score"]), reverse=True)
    formatted_all = format_scored_rows(scored)
    formatted_top = format_scored_rows(scored[:TOP_CANDIDATES])
    overlaps = method_overlap_rows(scored)
    ship_counts = ship_type_candidate_counts(scored)

    write_csv(TABLE_DIR / "mrv_anomaly_scores.csv", formatted_all)
    write_csv(TABLE_DIR / "mrv_anomaly_top_candidates.csv", formatted_top)
    write_csv(TABLE_DIR / "mrv_anomaly_method_overlap.csv", overlaps)
    write_csv(TABLE_DIR / "mrv_anomaly_ship_type_counts.csv", ship_counts)
    write_csv(TABLE_DIR / "mrv_anomaly_skipped_ship_types.csv", skipped)
    write_run_summary(all_rows, eligible, scored, skipped)
    write_csv(TABLE_DIR / "mrv_paper_results_index.csv", paper_results_index_rows())
    make_figures(scored, ship_counts, overlaps)


if __name__ == "__main__":
    main()
