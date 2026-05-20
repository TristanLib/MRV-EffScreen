#!/usr/bin/env python3
"""Train week-3 baseline classifiers for the MRV efficiency task."""

from __future__ import annotations

import csv
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "processed" / "mrv_modeling_base.csv"
TABLE_DIR = ROOT / "reports" / "tables"
FIGURE_DIR = ROOT / "reports" / "figures"

LABELS = ["efficient", "medium", "inefficient"]
LABEL_TO_INT = {label: idx for idx, label in enumerate(LABELS)}

FEATURE_SETS = {
    "strict_static": {
        "numeric": ["reporting_year", "technical_efficiency_value"],
        "categorical": [
            "ship_type",
            "technical_efficiency_type",
            "technical_efficiency_is_not_applicable",
            "port_of_registry",
            "has_home_port",
            "has_ice_class",
            "monitoring_method_a",
            "monitoring_method_b",
            "monitoring_method_c",
        ],
    },
    "operational_no_emission": {
        "numeric": [
            "reporting_year",
            "technical_efficiency_value",
            "time_spent_at_sea_hours",
            "distance_through_ice_nm",
            "time_spent_at_sea_through_ice_hours",
        ],
        "categorical": [
            "ship_type",
            "technical_efficiency_type",
            "technical_efficiency_is_not_applicable",
            "port_of_registry",
            "has_home_port",
            "has_ice_class",
            "monitoring_method_a",
            "monitoring_method_b",
            "monitoring_method_c",
        ],
    },
}


def parse_float(value: Any) -> float:
    if value is None or value == "":
        return np.nan
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return np.nan
    return parsed if math.isfinite(parsed) else np.nan


def load_rows() -> list[dict[str, str]]:
    with DATA_PATH.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def labeled_main_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row["is_main_experiment"] == "true" and row["efficiency_label_distance"] in LABEL_TO_INT
    ]


def external_2024_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row["temporal_split"] == "external_2024" and row["efficiency_label_distance"] in LABEL_TO_INT
    ]


def make_xy(rows: list[dict[str, str]], feature_set: str) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    numeric = FEATURE_SETS[feature_set]["numeric"]
    categorical = FEATURE_SETS[feature_set]["categorical"]
    features = numeric + categorical
    matrix: list[list[Any]] = []
    targets: list[int] = []

    for row in rows:
        values: list[Any] = []
        for field in numeric:
            values.append(parse_float(row.get(field, "")))
        for field in categorical:
            value = row.get(field, "")
            values.append(value if value != "" else None)
        matrix.append(values)
        targets.append(LABEL_TO_INT[row["efficiency_label_distance"]])

    return np.array(matrix, dtype=object), np.array(targets, dtype=int), numeric, categorical


def make_sparse_preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    numeric_indices = list(range(len(numeric)))
    categorical_indices = list(range(len(numeric), len(numeric) + len(categorical)))
    numeric_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler(with_mean=False)),
        ]
    )
    categorical_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(missing_values=None, strategy="constant", fill_value="Unknown")),
            (
                "onehot",
                OneHotEncoder(handle_unknown="ignore", min_frequency=5, sparse_output=True),
            ),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", numeric_pipeline, numeric_indices),
            ("categorical", categorical_pipeline, categorical_indices),
        ]
    )


def make_ordinal_preprocessor(numeric: list[str], categorical: list[str]) -> ColumnTransformer:
    numeric_indices = list(range(len(numeric)))
    categorical_indices = list(range(len(numeric), len(numeric) + len(categorical)))
    numeric_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ]
    )
    categorical_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(missing_values=None, strategy="constant", fill_value="Unknown")),
            (
                "ordinal",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                    encoded_missing_value=-2,
                ),
            ),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", numeric_pipeline, numeric_indices),
            ("categorical", categorical_pipeline, categorical_indices),
        ],
        sparse_threshold=0.0,
    )


def make_model(model_name: str, numeric: list[str], categorical: list[str]) -> Pipeline:
    if model_name == "logistic_regression":
        return Pipeline(
            [
                ("preprocess", make_sparse_preprocessor(numeric, categorical)),
                (
                    "model",
                    LogisticRegression(
                        class_weight="balanced",
                        max_iter=800,
                        solver="lbfgs",
                        random_state=42,
                    ),
                ),
            ]
        )
    if model_name == "random_forest":
        return Pipeline(
            [
                ("preprocess", make_sparse_preprocessor(numeric, categorical)),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=180,
                        max_depth=16,
                        min_samples_leaf=5,
                        class_weight="balanced_subsample",
                        n_jobs=-1,
                        random_state=42,
                    ),
                ),
            ]
        )
    if model_name == "hist_gradient_boosting":
        return Pipeline(
            [
                ("preprocess", make_ordinal_preprocessor(numeric, categorical)),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        learning_rate=0.05,
                        max_iter=220,
                        max_leaf_nodes=31,
                        l2_regularization=0.05,
                        random_state=42,
                    ),
                ),
            ]
        )
    raise ValueError(f"Unknown model: {model_name}")


def evaluate(
    scenario: str,
    feature_set: str,
    model_name: str,
    split_name: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    recalls = recall_score(y_true, y_pred, labels=[0, 1, 2], average=None, zero_division=0)
    metric_row = {
        "scenario": scenario,
        "feature_set": feature_set,
        "model": model_name,
        "split": split_name,
        "rows": str(len(y_true)),
        "accuracy": f"{accuracy_score(y_true, y_pred):.6f}",
        "balanced_accuracy": f"{balanced_accuracy_score(y_true, y_pred):.6f}",
        "macro_f1": f"{f1_score(y_true, y_pred, labels=[0, 1, 2], average='macro', zero_division=0):.6f}",
        "weighted_f1": f"{f1_score(y_true, y_pred, labels=[0, 1, 2], average='weighted', zero_division=0):.6f}",
        "recall_efficient": f"{recalls[0]:.6f}",
        "recall_medium": f"{recalls[1]:.6f}",
        "recall_inefficient": f"{recalls[2]:.6f}",
    }

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2])
    cm_rows = []
    for actual_idx, actual_label in enumerate(LABELS):
        cm_rows.append(
            {
                "scenario": scenario,
                "feature_set": feature_set,
                "model": model_name,
                "split": split_name,
                "actual_label": actual_label,
                "pred_efficient": str(int(cm[actual_idx, 0])),
                "pred_medium": str(int(cm[actual_idx, 1])),
                "pred_inefficient": str(int(cm[actual_idx, 2])),
            }
        )
    return metric_row, cm_rows


def run_temporal_experiments(rows: list[dict[str, str]], all_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    metrics: list[dict[str, str]] = []
    matrices: list[dict[str, str]] = []
    external_rows = external_2024_rows(all_rows)

    for feature_set in FEATURE_SETS:
        train_rows = [row for row in rows if row["temporal_split"] == "train"]
        validation_rows = [row for row in rows if row["temporal_split"] == "validation"]
        test_rows = [row for row in rows if row["temporal_split"] == "test"]
        x_train, y_train, numeric, categorical = make_xy(train_rows, feature_set)
        eval_sets = [
            ("validation_2022", validation_rows),
            ("test_2023", test_rows),
            ("external_2024", external_rows),
        ]

        for model_name in ["logistic_regression", "random_forest", "hist_gradient_boosting"]:
            model = make_model(model_name, numeric, categorical)
            model.fit(x_train, y_train)
            for split_name, eval_rows in eval_sets:
                if not eval_rows:
                    continue
                x_eval, y_eval, _, _ = make_xy(eval_rows, feature_set)
                y_pred = model.predict(x_eval)
                metric_row, cm_rows = evaluate(
                    "temporal",
                    feature_set,
                    model_name,
                    split_name,
                    y_eval,
                    y_pred,
                )
                metrics.append(metric_row)
                matrices.extend(cm_rows)
    return metrics, matrices


def run_random_experiments(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    metrics: list[dict[str, str]] = []
    matrices: list[dict[str, str]] = []
    y_all = np.array([LABEL_TO_INT[row["efficiency_label_distance"]] for row in rows], dtype=int)
    train_idx, test_idx = train_test_split(
        np.arange(len(rows)),
        test_size=0.2,
        random_state=42,
        stratify=y_all,
    )
    train_rows = [rows[i] for i in train_idx]
    test_rows = [rows[i] for i in test_idx]

    for feature_set in FEATURE_SETS:
        x_train, y_train, numeric, categorical = make_xy(train_rows, feature_set)
        x_test, y_test, _, _ = make_xy(test_rows, feature_set)
        for model_name in ["logistic_regression", "random_forest", "hist_gradient_boosting"]:
            model = make_model(model_name, numeric, categorical)
            model.fit(x_train, y_train)
            y_pred = model.predict(x_test)
            metric_row, cm_rows = evaluate(
                "random_stratified",
                feature_set,
                model_name,
                "random_test",
                y_test,
                y_pred,
            )
            metrics.append(metric_row)
            matrices.extend(cm_rows)
    return metrics, matrices


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_feature_set_table() -> None:
    rows = []
    for name, spec in FEATURE_SETS.items():
        for field in spec["numeric"]:
            rows.append({"feature_set": name, "field": field, "type": "numeric"})
        for field in spec["categorical"]:
            rows.append({"feature_set": name, "field": field, "type": "categorical"})
    write_csv(TABLE_DIR / "mrv_baseline_feature_sets.csv", rows)


def make_figures(metrics: list[dict[str, str]], matrices: list[dict[str, str]]) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    temporal_test = [
        row for row in metrics if row["scenario"] == "temporal" and row["split"] == "test_2023"
    ]
    draw_metric_bars(
        FIGURE_DIR / "mrv_baseline_macro_f1_temporal_test.svg",
        temporal_test,
        "macro_f1",
        "Temporal test Macro-F1",
    )
    draw_metric_bars(
        FIGURE_DIR / "mrv_baseline_balanced_accuracy_temporal_test.svg",
        temporal_test,
        "balanced_accuracy",
        "Temporal test balanced accuracy",
    )

    paired = []
    for row in metrics:
        if row["split"] not in {"test_2023", "random_test"}:
            continue
        paired.append(row)
    draw_metric_bars(
        FIGURE_DIR / "mrv_random_vs_temporal_macro_f1.svg",
        paired,
        "macro_f1",
        "Temporal vs random Macro-F1",
        width=1100,
        rotate_labels=True,
    )

    best = max(temporal_test, key=lambda row: float(row["macro_f1"]), default=None)
    if best:
        best_matrix = [
            row
            for row in matrices
            if row["scenario"] == best["scenario"]
            and row["feature_set"] == best["feature_set"]
            and row["model"] == best["model"]
            and row["split"] == best["split"]
        ]
        draw_confusion_matrix(
            FIGURE_DIR / "mrv_best_confusion_matrix_temporal_test.svg",
            best_matrix,
            f"Best temporal test confusion matrix: {best['feature_set']} / {best['model']}",
        )


def draw_metric_bars(
    path: Path,
    rows: list[dict[str, str]],
    metric: str,
    title: str,
    width: int = 980,
    height: int = 500,
    rotate_labels: bool = True,
) -> None:
    rows = sorted(rows, key=lambda row: (row["scenario"], row["feature_set"], row["model"], row["split"]))
    labels = [
        f"{row['scenario'].replace('_stratified', '')} | {row['feature_set'].replace('_', ' ')} | {row['model'].replace('_', ' ')}"
        for row in rows
    ]
    values = [float(row[metric]) for row in rows]
    draw_bar_chart(path, labels, values, title, metric.replace("_", " "), width, height, rotate_labels)


def draw_bar_chart(
    path: Path,
    labels: list[str],
    values: list[float],
    title: str,
    y_label: str,
    width: int,
    height: int,
    rotate_labels: bool,
) -> None:
    margin_left, margin_right, margin_top, margin_bottom = 72, 24, 54, 150
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    max_value = max(values, default=1)
    max_value = max(0.05, min(1.0, max_value * 1.12))
    bar_gap = 8
    bar_w = max(8, (plot_w - bar_gap * max(0, len(values) - 1)) / max(1, len(values)))
    colors = ["#2f6f73", "#8f5f2a", "#4f6f9f", "#a64d4d", "#5e6c84", "#6f5e9c"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Arial" font-size="18" fill="#1f2933">{escape_xml(title)}</text>',
        f'<text x="18" y="{margin_top + plot_h / 2}" transform="rotate(-90 18 {margin_top + plot_h / 2})" text-anchor="middle" font-family="Arial" font-size="12" fill="#52606d">{escape_xml(y_label)}</text>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{width - margin_right}" y2="{margin_top + plot_h}" stroke="#9aa5b1" stroke-width="1"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_h}" stroke="#9aa5b1" stroke-width="1"/>',
    ]
    for tick in range(6):
        value = max_value * tick / 5
        y = margin_top + plot_h - (value / max_value) * plot_h
        parts.append(f'<line x1="{margin_left - 4}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#e4e7eb" stroke-width="1"/>')
        parts.append(f'<text x="{margin_left - 8}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#52606d">{value:.2f}</text>')
    for i, value in enumerate(values):
        x = margin_left + i * (bar_w + bar_gap)
        bar_h = (value / max_value) * plot_h
        y = margin_top + plot_h - bar_h
        label_x = x + bar_w / 2
        label_y = margin_top + plot_h + 18
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" fill="{colors[i % len(colors)]}"/>')
        parts.append(f'<text x="{label_x:.2f}" y="{y - 5:.2f}" text-anchor="middle" font-family="Arial" font-size="10" fill="#323f4b">{value:.3f}</text>')
        label = truncate(labels[i], 34)
        if rotate_labels:
            parts.append(f'<text x="{label_x:.2f}" y="{label_y:.2f}" transform="rotate(55 {label_x:.2f} {label_y:.2f})" text-anchor="start" font-family="Arial" font-size="9" fill="#323f4b">{escape_xml(label)}</text>')
        else:
            parts.append(f'<text x="{label_x:.2f}" y="{label_y:.2f}" text-anchor="middle" font-family="Arial" font-size="10" fill="#323f4b">{escape_xml(label)}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def draw_confusion_matrix(path: Path, rows: list[dict[str, str]], title: str) -> None:
    matrix = []
    for row in rows:
        matrix.append(
            [
                int(row["pred_efficient"]),
                int(row["pred_medium"]),
                int(row["pred_inefficient"]),
            ]
        )
    if len(matrix) != 3:
        return
    max_value = max(max(line) for line in matrix) or 1
    cell = 88
    width, height = 520, 430
    x0, y0 = 180, 88
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="30" text-anchor="middle" font-family="Arial" font-size="16" fill="#1f2933">{escape_xml(title)}</text>',
        f'<text x="{x0 + cell * 1.5}" y="64" text-anchor="middle" font-family="Arial" font-size="12" fill="#52606d">Predicted</text>',
        f'<text x="28" y="{y0 + cell * 1.5}" transform="rotate(-90 28 {y0 + cell * 1.5})" text-anchor="middle" font-family="Arial" font-size="12" fill="#52606d">Actual</text>',
    ]
    for j, label in enumerate(LABELS):
        parts.append(f'<text x="{x0 + j * cell + cell / 2}" y="{y0 - 12}" text-anchor="middle" font-family="Arial" font-size="11" fill="#323f4b">{escape_xml(label)}</text>')
        parts.append(f'<text x="{x0 - 12}" y="{y0 + j * cell + cell / 2 + 4}" text-anchor="end" font-family="Arial" font-size="11" fill="#323f4b">{escape_xml(label)}</text>')
    for i in range(3):
        for j in range(3):
            value = matrix[i][j]
            intensity = value / max_value
            color = blend("#edf7f7", "#2f6f73", intensity)
            parts.append(f'<rect x="{x0 + j * cell}" y="{y0 + i * cell}" width="{cell}" height="{cell}" fill="{color}" stroke="#ffffff" stroke-width="2"/>')
            parts.append(f'<text x="{x0 + j * cell + cell / 2}" y="{y0 + i * cell + cell / 2 + 5}" text-anchor="middle" font-family="Arial" font-size="18" fill="#1f2933">{value}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def blend(c1: str, c2: str, t: float) -> str:
    def rgb(hex_color: str) -> tuple[int, int, int]:
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    a, b = rgb(c1), rgb(c2)
    vals = [round(a[i] + (b[i] - a[i]) * t) for i in range(3)]
    return "#" + "".join(f"{value:02x}" for value in vals)


def truncate(value: str, length: int) -> str:
    return value if len(value) <= length else value[: length - 1] + "…"


def escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_run_summary(rows: list[dict[str, str]], metrics: list[dict[str, str]]) -> None:
    main = labeled_main_rows(rows)
    split_counts = Counter(row["temporal_split"] for row in main)
    best_temporal = max(
        (row for row in metrics if row["scenario"] == "temporal" and row["split"] == "test_2023"),
        key=lambda row: float(row["macro_f1"]),
    )
    summary_rows = [
        {"metric": "labeled_main_rows", "value": str(len(main))},
        {"metric": "train_rows", "value": str(split_counts["train"])},
        {"metric": "validation_rows", "value": str(split_counts["validation"])},
        {"metric": "test_rows", "value": str(split_counts["test"])},
        {"metric": "best_temporal_test_feature_set", "value": best_temporal["feature_set"]},
        {"metric": "best_temporal_test_model", "value": best_temporal["model"]},
        {"metric": "best_temporal_test_macro_f1", "value": best_temporal["macro_f1"]},
        {"metric": "best_temporal_test_balanced_accuracy", "value": best_temporal["balanced_accuracy"]},
    ]
    write_csv(TABLE_DIR / "mrv_baseline_run_summary.csv", summary_rows)


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    main_rows = labeled_main_rows(rows)

    temporal_metrics, temporal_matrices = run_temporal_experiments(main_rows, rows)
    random_metrics, random_matrices = run_random_experiments(main_rows)
    metrics = temporal_metrics + random_metrics
    matrices = temporal_matrices + random_matrices

    write_csv(TABLE_DIR / "mrv_baseline_metrics.csv", metrics)
    write_csv(TABLE_DIR / "mrv_baseline_confusion_matrices.csv", matrices)
    write_feature_set_table()
    write_run_summary(rows, metrics)
    make_figures(metrics, matrices)


if __name__ == "__main__":
    main()
