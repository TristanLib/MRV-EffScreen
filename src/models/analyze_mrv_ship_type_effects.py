#!/usr/bin/env python3
"""Week-4 ship-type ablations and error analysis for MRV baselines."""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.inspection import permutation_importance
from sklearn.metrics import f1_score, make_scorer

sys.path.append(str(Path(__file__).resolve().parent))

from train_mrv_baselines import (  # noqa: E402
    FEATURE_SETS,
    LABELS,
    LABEL_TO_INT,
    draw_bar_chart,
    evaluate,
    labeled_main_rows,
    load_rows,
    make_model,
    make_xy,
    write_csv,
)


ROOT = Path(__file__).resolve().parents[2]
TABLE_DIR = ROOT / "reports" / "tables"
FIGURE_DIR = ROOT / "reports" / "figures"
MODEL_NAME = "hist_gradient_boosting"


def top_ship_types(rows: list[dict[str, str]], top_n: int = 5) -> list[str]:
    counter = Counter(row["ship_type"] for row in rows)
    return [ship_type for ship_type, _count in counter.most_common(top_n)]


def metric_for_prediction(
    scenario: str,
    feature_set: str,
    ship_type: str,
    split: str,
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    metric, matrices = evaluate(scenario, feature_set, MODEL_NAME, split, y_true, y_pred)
    metric["ship_type"] = ship_type
    metric["train_scope"] = scenario
    for row in matrices:
        row["ship_type"] = ship_type
        row["train_scope"] = scenario
    return metric, matrices


def run_ship_type_comparison(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    ships = top_ship_types(rows)
    metrics: list[dict[str, str]] = []
    matrices: list[dict[str, str]] = []

    for feature_set in ["strict_static", "operational_no_emission"]:
        train_rows = [row for row in rows if row["temporal_split"] == "train"]
        x_train, y_train, numeric, categorical = make_xy(train_rows, feature_set)
        unified_model = make_model(MODEL_NAME, numeric, categorical)
        unified_model.fit(x_train, y_train)

        for ship_type in ships:
            for split in ["validation", "test"]:
                eval_rows = [
                    row
                    for row in rows
                    if row["ship_type"] == ship_type and row["temporal_split"] == split
                ]
                if not eval_rows:
                    continue
                x_eval, y_eval, _, _ = make_xy(eval_rows, feature_set)
                pred = unified_model.predict(x_eval)
                metric, cm = metric_for_prediction(
                    "unified_model",
                    feature_set,
                    ship_type,
                    split,
                    y_eval,
                    pred,
                )
                metrics.append(metric)
                matrices.extend(cm)

        for ship_type in ships:
            ship_train_rows = [
                row
                for row in rows
                if row["ship_type"] == ship_type and row["temporal_split"] == "train"
            ]
            if len(ship_train_rows) < 300:
                continue
            if len({row["efficiency_label_distance"] for row in ship_train_rows}) < 3:
                continue

            x_ship_train, y_ship_train, ship_numeric, ship_categorical = make_xy(ship_train_rows, feature_set)
            ship_model = make_model(MODEL_NAME, ship_numeric, ship_categorical)
            ship_model.fit(x_ship_train, y_ship_train)

            for split in ["validation", "test"]:
                eval_rows = [
                    row
                    for row in rows
                    if row["ship_type"] == ship_type and row["temporal_split"] == split
                ]
                if not eval_rows:
                    continue
                x_eval, y_eval, _, _ = make_xy(eval_rows, feature_set)
                pred = ship_model.predict(x_eval)
                metric, cm = metric_for_prediction(
                    "ship_type_model",
                    feature_set,
                    ship_type,
                    split,
                    y_eval,
                    pred,
                )
                metrics.append(metric)
                matrices.extend(cm)

    return metrics, matrices, ships


def run_permutation_importance(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    feature_set = "operational_no_emission"
    train_rows = [row for row in rows if row["temporal_split"] == "train"]
    test_rows = [row for row in rows if row["temporal_split"] == "test"]
    x_train, y_train, numeric, categorical = make_xy(train_rows, feature_set)
    x_test, y_test, _, _ = make_xy(test_rows, feature_set)
    features = numeric + categorical

    model = make_model(MODEL_NAME, numeric, categorical)
    model.fit(x_train, y_train)

    # Use a deterministic stratified subset to keep permutation importance quick.
    subset_idx = stratified_subset_indices(y_test, max_n=6000)
    x_subset = x_test[subset_idx]
    y_subset = y_test[subset_idx]
    scoring = make_scorer(f1_score, average="macro", labels=[0, 1, 2], zero_division=0)
    result = permutation_importance(
        model,
        x_subset,
        y_subset,
        n_repeats=5,
        random_state=42,
        scoring=scoring,
        n_jobs=-1,
    )

    rows_out = []
    for idx in np.argsort(result.importances_mean)[::-1]:
        rows_out.append(
            {
                "feature_set": feature_set,
                "model": MODEL_NAME,
                "split": "test_2023_stratified_subset",
                "feature": features[idx],
                "importance_mean_macro_f1_drop": f"{result.importances_mean[idx]:.6f}",
                "importance_std": f"{result.importances_std[idx]:.6f}",
            }
        )
    return rows_out


def stratified_subset_indices(y: np.ndarray, max_n: int) -> np.ndarray:
    if len(y) <= max_n:
        return np.arange(len(y))
    rng = np.random.default_rng(42)
    indices = []
    per_class = max_n // len(LABELS)
    for cls in range(len(LABELS)):
        cls_idx = np.where(y == cls)[0]
        take = min(per_class, len(cls_idx))
        indices.extend(rng.choice(cls_idx, size=take, replace=False).tolist())
    indices = np.array(sorted(indices), dtype=int)
    return indices


def run_medium_error_analysis(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    feature_set = "operational_no_emission"
    train_rows = [row for row in rows if row["temporal_split"] == "train"]
    test_rows = [row for row in rows if row["temporal_split"] == "test"]
    x_train, y_train, numeric, categorical = make_xy(train_rows, feature_set)
    x_test, y_test, _, _ = make_xy(test_rows, feature_set)

    model = make_model(MODEL_NAME, numeric, categorical)
    model.fit(x_train, y_train)
    pred = model.predict(x_test)
    proba = model.predict_proba(x_test)

    aggregate = Counter()
    samples = []
    for row, actual, predicted, probs in zip(test_rows, y_test, pred, proba, strict=True):
        if LABELS[actual] != "medium" or actual == predicted:
            continue
        predicted_label = LABELS[predicted]
        aggregate[(row["ship_type"], predicted_label)] += 1
        confidence = float(np.max(probs))
        samples.append(
            {
                "ship_type": row["ship_type"],
                "imo_number": row["imo_number"],
                "ship_name": row["ship_name"],
                "reporting_year": row["reporting_year"],
                "actual_label": "medium",
                "predicted_label": predicted_label,
                "prediction_confidence": f"{confidence:.6f}",
                "technical_efficiency_type": row["technical_efficiency_type"],
                "technical_efficiency_value": row["technical_efficiency_value"],
                "time_spent_at_sea_hours": row["time_spent_at_sea_hours"],
                "co2_per_distance_kg_nm": row["co2_per_distance_kg_nm"],
                "distance_efficiency_rank_pct": row["distance_efficiency_rank_pct"],
            }
        )

    aggregate_rows = [
        {"ship_type": ship_type, "predicted_label": label, "medium_errors": str(count)}
        for (ship_type, label), count in sorted(aggregate.items(), key=lambda item: (-item[1], item[0]))
    ]
    samples.sort(key=lambda row: float(row["prediction_confidence"]), reverse=True)
    identifier_removed_samples = []
    for rank, row in enumerate(samples[:100], start=1):
        identifier_removed_samples.append(
            {
                "sample_rank": str(rank),
                "ship_type": row["ship_type"],
                "reporting_year": row["reporting_year"],
                "actual_label": row["actual_label"],
                "predicted_label": row["predicted_label"],
                "prediction_confidence": row["prediction_confidence"],
                "technical_efficiency_type": row["technical_efficiency_type"],
                "technical_efficiency_value": row["technical_efficiency_value"],
                "time_spent_at_sea_hours": row["time_spent_at_sea_hours"],
                "co2_per_distance_kg_nm": row["co2_per_distance_kg_nm"],
                "distance_efficiency_rank_pct": row["distance_efficiency_rank_pct"],
            }
        )
    return aggregate_rows, identifier_removed_samples


def make_figures(metrics: list[dict[str, str]], importance_rows: list[dict[str, str]]) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    test_rows = [row for row in metrics if row["split"] == "test"]
    labels = [
        f"{row['ship_type']} | {row['train_scope'].replace('_model', '')} | {row['feature_set'].replace('_', ' ')}"
        for row in test_rows
    ]
    values = [float(row["macro_f1"]) for row in test_rows]
    draw_bar_chart(
        FIGURE_DIR / "mrv_ship_type_macro_f1_comparison.svg",
        labels,
        values,
        "Top ship types: unified vs ship-specific Macro-F1",
        "macro f1",
        1350,
        560,
        True,
    )

    best_operational_test = [
        row
        for row in test_rows
        if row["feature_set"] == "operational_no_emission"
    ]
    labels = [f"{row['ship_type']} | {row['train_scope'].replace('_model', '')}" for row in best_operational_test]
    values = [float(row["balanced_accuracy"]) for row in best_operational_test]
    draw_bar_chart(
        FIGURE_DIR / "mrv_ship_type_balanced_accuracy_operational.svg",
        labels,
        values,
        "Operational feature set: balanced accuracy by ship type",
        "balanced accuracy",
        1180,
        540,
        True,
    )

    top_importance = importance_rows[:12]
    labels = [row["feature"] for row in top_importance]
    values = [float(row["importance_mean_macro_f1_drop"]) for row in top_importance]
    draw_bar_chart(
        FIGURE_DIR / "mrv_permutation_importance_top_features.svg",
        labels,
        values,
        "Permutation importance: Macro-F1 drop",
        "macro f1 drop",
        980,
        520,
        True,
    )


def write_summary(metrics: list[dict[str, str]], ships: list[str], importance_rows: list[dict[str, str]]) -> None:
    test_rows = [row for row in metrics if row["split"] == "test"]
    best = max(test_rows, key=lambda row: float(row["macro_f1"]))
    rows = [
        {"metric": "top_ship_types", "value": "; ".join(ships)},
        {"metric": "best_test_train_scope", "value": best["train_scope"]},
        {"metric": "best_test_ship_type", "value": best["ship_type"]},
        {"metric": "best_test_feature_set", "value": best["feature_set"]},
        {"metric": "best_test_macro_f1", "value": best["macro_f1"]},
        {"metric": "best_test_balanced_accuracy", "value": best["balanced_accuracy"]},
    ]
    if importance_rows:
        rows.append({"metric": "top_permutation_feature", "value": importance_rows[0]["feature"]})
        rows.append(
            {
                "metric": "top_permutation_macro_f1_drop",
                "value": importance_rows[0]["importance_mean_macro_f1_drop"],
            }
        )
    write_csv(TABLE_DIR / "mrv_ship_type_run_summary.csv", rows)


def write_comparison_summary(metrics: list[dict[str, str]]) -> None:
    test_rows = [row for row in metrics if row["split"] == "test"]
    keyed = {
        (row["ship_type"], row["feature_set"], row["train_scope"]): row
        for row in test_rows
    }
    summary = []
    for ship_type in sorted({row["ship_type"] for row in test_rows}):
        for feature_set in sorted({row["feature_set"] for row in test_rows}):
            unified = keyed.get((ship_type, feature_set, "unified_model"))
            ship_specific = keyed.get((ship_type, feature_set, "ship_type_model"))
            if not unified or not ship_specific:
                continue
            unified_f1 = float(unified["macro_f1"])
            ship_f1 = float(ship_specific["macro_f1"])
            unified_ba = float(unified["balanced_accuracy"])
            ship_ba = float(ship_specific["balanced_accuracy"])
            summary.append(
                {
                    "ship_type": ship_type,
                    "feature_set": feature_set,
                    "unified_macro_f1": f"{unified_f1:.6f}",
                    "ship_type_macro_f1": f"{ship_f1:.6f}",
                    "macro_f1_delta_ship_minus_unified": f"{ship_f1 - unified_f1:.6f}",
                    "unified_balanced_accuracy": f"{unified_ba:.6f}",
                    "ship_type_balanced_accuracy": f"{ship_ba:.6f}",
                    "balanced_accuracy_delta_ship_minus_unified": f"{ship_ba - unified_ba:.6f}",
                }
            )
    summary.sort(key=lambda row: (row["ship_type"], row["feature_set"]))
    write_csv(TABLE_DIR / "mrv_ship_type_comparison_summary.csv", summary)


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = load_rows()
    rows = labeled_main_rows(all_rows)

    metrics, matrices, ships = run_ship_type_comparison(rows)
    importance_rows = run_permutation_importance(rows)
    medium_aggregate, medium_samples = run_medium_error_analysis(rows)

    metric_fields = [
        "train_scope",
        "ship_type",
        "scenario",
        "feature_set",
        "model",
        "split",
        "rows",
        "accuracy",
        "balanced_accuracy",
        "macro_f1",
        "weighted_f1",
        "recall_efficient",
        "recall_medium",
        "recall_inefficient",
    ]
    matrix_fields = [
        "train_scope",
        "ship_type",
        "scenario",
        "feature_set",
        "model",
        "split",
        "actual_label",
        "pred_efficient",
        "pred_medium",
        "pred_inefficient",
    ]
    write_csv(TABLE_DIR / "mrv_ship_type_metrics.csv", metrics, metric_fields)
    write_csv(TABLE_DIR / "mrv_ship_type_confusion_matrices.csv", matrices, matrix_fields)
    write_csv(TABLE_DIR / "mrv_permutation_importance.csv", importance_rows)
    write_csv(TABLE_DIR / "mrv_medium_error_aggregate.csv", medium_aggregate)
    write_csv(TABLE_DIR / "mrv_medium_error_samples.csv", medium_samples)
    write_comparison_summary(metrics)
    write_summary(metrics, ships, importance_rows)
    make_figures(metrics, importance_rows)


if __name__ == "__main__":
    main()
