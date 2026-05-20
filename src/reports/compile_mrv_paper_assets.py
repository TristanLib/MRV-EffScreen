#!/usr/bin/env python3
"""Compile week-6 manuscript-facing result tables and captions."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TABLE_DIR = ROOT / "reports" / "tables"


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


def metric_lookup(path: Path) -> dict[str, str]:
    return {row["metric"]: row["value"] for row in read_csv(path)}


def build_key_numbers() -> list[dict[str, str]]:
    processed = metric_lookup(TABLE_DIR / "mrv_processed_summary.csv")
    baseline = metric_lookup(TABLE_DIR / "mrv_baseline_run_summary.csv")
    ship_type = metric_lookup(TABLE_DIR / "mrv_ship_type_run_summary.csv")
    anomaly = metric_lookup(TABLE_DIR / "mrv_anomaly_run_summary.csv")
    sensitivity = read_csv(TABLE_DIR / "mrv_anomaly_sensitivity_summary.csv")
    sensitivity_2pct = next(row for row in sensitivity if row["contamination"] == "2.00%")

    rows = [
        ("dataset", "total processed MRV rows", processed["total_rows"], "mrv_processed_summary.csv", "Data section"),
        ("dataset", "main 2018-2023 experiment rows", processed["main_experiment_rows"], "mrv_processed_summary.csv", "Data section"),
        ("dataset", "labeled main experiment rows", processed["labeled_main_experiment_rows"], "mrv_processed_summary.csv", "Data section"),
        ("dataset", "external 2024 full-year rows", processed["external_2024_rows"], "mrv_processed_summary.csv", "Data section"),
        ("dataset", "excluded 2024 partial ER rows", processed["partial_er_rows"], "mrv_processed_summary.csv", "Data exclusion note"),
        ("dataset", "unique IMO numbers", processed["unique_imo_numbers"], "mrv_processed_summary.csv", "Data section"),
        ("dataset", "unique ship types", processed["unique_ship_types"], "mrv_processed_summary.csv", "Data section"),
        ("classification", "train rows", baseline["train_rows"], "mrv_baseline_run_summary.csv", "Temporal split description"),
        ("classification", "validation rows", baseline["validation_rows"], "mrv_baseline_run_summary.csv", "Temporal split description"),
        ("classification", "test rows", baseline["test_rows"], "mrv_baseline_run_summary.csv", "Temporal split description"),
        ("classification", "best temporal test feature set", baseline["best_temporal_test_feature_set"], "mrv_baseline_run_summary.csv", "Main results"),
        ("classification", "best temporal test model", baseline["best_temporal_test_model"], "mrv_baseline_run_summary.csv", "Main results"),
        ("classification", "best temporal test Macro-F1", baseline["best_temporal_test_macro_f1"], "mrv_baseline_run_summary.csv", "Main results"),
        ("classification", "best temporal test balanced accuracy", baseline["best_temporal_test_balanced_accuracy"], "mrv_baseline_run_summary.csv", "Main results"),
        ("ship-type ablation", "top ship types", ship_type["top_ship_types"], "mrv_ship_type_run_summary.csv", "Ablation setup"),
        ("ship-type ablation", "best ship-type model Macro-F1", ship_type["best_test_macro_f1"], "mrv_ship_type_run_summary.csv", "Ablation result"),
        ("interpretability", "top permutation feature", ship_type["top_permutation_feature"], "mrv_ship_type_run_summary.csv", "Feature importance"),
        ("interpretability", "top permutation Macro-F1 drop", ship_type["top_permutation_macro_f1_drop"], "mrv_ship_type_run_summary.csv", "Feature importance"),
        ("anomaly screening", "eligible full-year rows", anomaly["eligible_full_year_rows"], "mrv_anomaly_run_summary.csv", "Consistency screening setup"),
        ("anomaly screening", "modeled rows", anomaly["modeled_rows"], "mrv_anomaly_run_summary.csv", "Consistency screening setup"),
        ("anomaly screening", "modeled ship types", anomaly["modeled_ship_types"], "mrv_anomaly_run_summary.csv", "Consistency screening setup"),
        ("anomaly screening", "all-three-method rows at 2%", sensitivity_2pct["all_three_methods"], "mrv_anomaly_sensitivity_summary.csv", "Sensitivity result"),
        ("anomaly screening", "at-least-two-method rows at 2%", sensitivity_2pct["at_least_two_methods"], "mrv_anomaly_sensitivity_summary.csv", "Sensitivity result"),
    ]
    return [
        {
            "result_group": group,
            "metric": metric,
            "value": value,
            "source_table": source,
            "manuscript_use": use,
        }
        for group, metric, value, source, use in rows
    ]


def build_main_model_results() -> list[dict[str, str]]:
    metrics = read_csv(TABLE_DIR / "mrv_baseline_metrics.csv")
    rows = []
    for row in metrics:
        if row["split"] not in {"test_2023", "external_2024", "random_test"}:
            continue
        rows.append(
            {
                "scenario": row["scenario"],
                "split": row["split"],
                "feature_set": row["feature_set"],
                "model": row["model"],
                "rows": row["rows"],
                "accuracy": row["accuracy"],
                "balanced_accuracy": row["balanced_accuracy"],
                "macro_f1": row["macro_f1"],
                "weighted_f1": row["weighted_f1"],
                "recommended_use": recommended_model_use(row),
            }
        )
    rows.sort(key=lambda row: (row["scenario"], row["split"], row["feature_set"], row["model"]))
    return rows


def build_class_metrics() -> list[dict[str, str]]:
    labels = ["efficient", "medium", "inefficient"]
    matrices = read_csv(TABLE_DIR / "mrv_baseline_confusion_matrices.csv")
    selected_splits = ["validation_2022", "test_2023", "external_2024"]
    out = []
    for split in selected_splits:
        rows = [
            row
            for row in matrices
            if row["scenario"] == "temporal"
            and row["feature_set"] == "operational_no_emission"
            and row["model"] == "hist_gradient_boosting"
            and row["split"] == split
        ]
        matrix = {
            row["actual_label"]: {label: int(row[f"pred_{label}"]) for label in labels}
            for row in rows
        }
        for label in labels:
            true_positive = matrix[label][label]
            support = sum(matrix[label].values())
            predicted = sum(matrix[actual][label] for actual in labels)
            precision = true_positive / predicted if predicted else 0.0
            recall = true_positive / support if support else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            out.append(
                {
                    "split": split,
                    "feature_set": "operational_no_emission",
                    "model": "hist_gradient_boosting",
                    "class_label": label,
                    "precision": f"{precision:.6f}",
                    "recall": f"{recall:.6f}",
                    "f1": f"{f1:.6f}",
                    "support": str(support),
                    "predicted_rows": str(predicted),
                }
            )
    return out


def recommended_model_use(row: dict[str, str]) -> str:
    if row["scenario"] == "temporal" and row["split"] == "test_2023":
        return "main temporal generalization result"
    if row["scenario"] == "temporal" and row["split"] == "external_2024":
        return "external-year robustness check"
    if row["scenario"] == "random_stratified":
        return "optimistic random-split comparison"
    return "supporting result"


def build_ship_type_results() -> list[dict[str, str]]:
    rows = read_csv(TABLE_DIR / "mrv_ship_type_comparison_summary.csv")
    out = []
    for row in rows:
        out.append(
            {
                "ship_type": row["ship_type"],
                "feature_set": row["feature_set"],
                "unified_macro_f1": row["unified_macro_f1"],
                "ship_type_macro_f1": row["ship_type_macro_f1"],
                "macro_f1_delta_ship_minus_unified": row["macro_f1_delta_ship_minus_unified"],
                "unified_balanced_accuracy": row["unified_balanced_accuracy"],
                "ship_type_balanced_accuracy": row["ship_type_balanced_accuracy"],
                "balanced_accuracy_delta_ship_minus_unified": row["balanced_accuracy_delta_ship_minus_unified"],
                "interpretation": ship_type_interpretation(float(row["macro_f1_delta_ship_minus_unified"])),
            }
        )
    out.sort(key=lambda row: float(row["macro_f1_delta_ship_minus_unified"]), reverse=True)
    return out


def ship_type_interpretation(delta: float) -> str:
    if delta >= 0.02:
        return "clear gain from ship-type-specific model"
    if delta > 0:
        return "small gain from ship-type-specific model"
    return "no gain over unified model"


def build_interpretability_results() -> list[dict[str, str]]:
    importance = read_csv(TABLE_DIR / "mrv_permutation_importance.csv")[:10]
    medium = read_csv(TABLE_DIR / "mrv_medium_error_aggregate.csv")[:10]
    rows = []
    for rank, row in enumerate(importance, start=1):
        rows.append(
            {
                "analysis": "permutation_importance",
                "rank": str(rank),
                "item": row["feature"],
                "value": row["importance_mean_macro_f1_drop"],
                "secondary_value": row["importance_std"],
                "interpretation": "Macro-F1 drop after feature permutation",
            }
        )
    for rank, row in enumerate(medium, start=1):
        rows.append(
            {
                "analysis": "medium_error",
                "rank": str(rank),
                "item": f"{row['ship_type']} medium -> {row['predicted_label']}",
                "value": row["medium_errors"],
                "secondary_value": "",
                "interpretation": "Most frequent temporal-test medium-class error pattern",
            }
        )
    return rows


def build_table_plan() -> list[dict[str, str]]:
    return [
        {
            "table_id": "Table 1",
            "artifact": "reports/tables/mrv_paper_key_numbers.csv",
            "caption": "Dataset coverage and temporal split statistics for the THETIS-MRV public emission reports.",
            "section": "Data",
            "status": "ready for manuscript condensation",
        },
        {
            "table_id": "Table 2",
            "artifact": "reports/tables/mrv_paper_main_model_results.csv",
            "caption": "Classification performance under temporal, external-year, and random stratified evaluation settings.",
            "section": "Experiments",
            "status": "ready; final manuscript should emphasize temporal 2023 test results",
        },
        {
            "table_id": "Table 3",
            "artifact": "reports/tables/mrv_paper_ship_type_results.csv",
            "caption": "Unified versus ship-type-specific modeling for the five largest ship categories.",
            "section": "Ablation study",
            "status": "ready",
        },
        {
            "table_id": "Table 4",
            "artifact": "reports/tables/mrv_paper_interpretability_results.csv",
            "caption": "Permutation importance and dominant medium-class error patterns.",
            "section": "Interpretability and error analysis",
            "status": "ready for split into two manuscript tables if space permits",
        },
        {
            "table_id": "Table 5",
            "artifact": "reports/tables/mrv_anomaly_sensitivity_summary.csv",
            "caption": "Sensitivity of anomaly-screening candidates under 1%, 2%, and 5% ship-type-specific thresholds.",
            "section": "Consistency screening",
            "status": "ready",
        },
        {
            "table_id": "Supplementary Table S1",
            "artifact": "reports/tables/mrv_paper_class_metrics.csv",
            "caption": "Class-level precision, recall, F1, support, and predicted-row counts for the best temporal classifier.",
            "section": "Main results",
            "status": "ready for supplementary release or condensed in text",
        },
    ]


def build_figure_captions() -> list[dict[str, str]]:
    return [
        {
            "figure_id": "Figure 1",
            "artifact": "reports/figures/mrv_rows_by_year.svg",
            "caption": "Annual coverage of THETIS-MRV public emission reports from 2018 to 2024.",
            "section": "Data",
            "message": "Dataset size is stable across 2018-2023, with 2024 treated as an external-year extension.",
        },
        {
            "figure_id": "Figure 2",
            "artifact": "reports/figures/mrv_label_distribution_by_year.svg",
            "caption": "Distribution of ship-type-year tertile labels for CO2 emissions per distance.",
            "section": "Data",
            "message": "The label construction yields balanced efficient, medium, and inefficient classes within each year.",
        },
        {
            "figure_id": "Figure 3",
            "artifact": "reports/figures/mrv_baseline_macro_f1_temporal_test.svg",
            "caption": "Macro-F1 on the 2023 temporal test set for non-leakage feature sets and baseline classifiers.",
            "section": "Main results",
            "message": "HistGradientBoosting with operational non-emission features is the strongest temporal baseline.",
        },
        {
            "figure_id": "Figure 4",
            "artifact": "reports/figures/mrv_random_vs_temporal_macro_f1.svg",
            "caption": "Comparison between temporal evaluation and random stratified evaluation.",
            "section": "Main results",
            "message": "Random splits give higher estimates and should not be the primary generalization evidence.",
        },
        {
            "figure_id": "Figure 5",
            "artifact": "reports/figures/mrv_ship_type_macro_f1_comparison.svg",
            "caption": "Macro-F1 comparison between unified and ship-type-specific models for the five largest ship types.",
            "section": "Ablation study",
            "message": "Ship-type-specific modeling helps some categories but is not uniformly superior.",
        },
        {
            "figure_id": "Figure 6",
            "artifact": "reports/figures/mrv_permutation_importance_top_features.svg",
            "caption": "Permutation importance of the best non-leakage temporal classifier.",
            "section": "Interpretability",
            "message": "Technical efficiency fields and ship type dominate the non-leakage prediction signal.",
        },
        {
            "figure_id": "Figure 7",
            "artifact": "reports/figures/mrv_anomaly_top_ship_types.svg",
            "caption": "Ship-type distribution of the top 200 anomaly-screening candidates.",
            "section": "Consistency screening",
            "message": "Candidate rows concentrate in large cargo ship categories but include multiple ship types.",
        },
        {
            "figure_id": "Figure 8",
            "artifact": "reports/figures/mrv_anomaly_sensitivity_overlap.svg",
            "caption": "Sensitivity of anomaly-screening overlap under 1%, 2%, and 5% thresholds.",
            "section": "Consistency screening",
            "message": "The all-three-method and at-least-two-method candidate sets scale predictably with the threshold.",
        },
    ]


def build_results_index() -> list[dict[str, str]]:
    return [
        {
            "result_block": "dataset_audit",
            "artifact": "reports/tables/mrv_workbook_inventory.csv",
            "primary_use": "Data source coverage and annual workbook inventory",
            "notes": "Supports data provenance and reproducibility.",
        },
        {
            "result_block": "dataset_summary",
            "artifact": "reports/tables/mrv_paper_key_numbers.csv",
            "primary_use": "Condensed dataset and split statistics for manuscript Table 1",
            "notes": "Generated by src/reports/compile_mrv_paper_assets.py.",
        },
        {
            "result_block": "baseline_temporal",
            "artifact": "reports/tables/mrv_paper_main_model_results.csv",
            "primary_use": "Main temporal, external-year, and random-split classification metrics",
            "notes": "Use temporal 2023 results as the primary predictive benchmark.",
        },
        {
            "result_block": "class_level_metrics",
            "artifact": "reports/tables/mrv_paper_class_metrics.csv",
            "primary_use": "Class-level behavior of the best temporal classifier",
            "notes": "Supports text on medium-class ambiguity and asymmetric efficient/inefficient recall.",
        },
        {
            "result_block": "baseline_figures",
            "artifact": "reports/figures/mrv_baseline_macro_f1_temporal_test.svg",
            "primary_use": "Visual comparison of model Macro-F1 on 2023 temporal test",
            "notes": "Pair with balanced accuracy and random-vs-temporal figures.",
        },
        {
            "result_block": "ship_type_ablation",
            "artifact": "reports/tables/mrv_paper_ship_type_results.csv",
            "primary_use": "Unified vs ship-type-specific model comparison",
            "notes": "Use to support heterogeneous value of ship-type stratification.",
        },
        {
            "result_block": "feature_importance",
            "artifact": "reports/tables/mrv_paper_interpretability_results.csv",
            "primary_use": "Permutation importance and medium-class error analysis",
            "notes": "May be split into two manuscript tables.",
        },
        {
            "result_block": "anomaly_screening",
            "artifact": "reports/tables/mrv_anomaly_top_candidates.csv",
            "primary_use": "Anonymized top MRV consistency-screening candidates",
            "notes": "Describe strictly as anomaly-screening candidates, not violations; public table excludes IMO numbers and ship names.",
        },
        {
            "result_block": "anomaly_sensitivity",
            "artifact": "reports/tables/mrv_anomaly_sensitivity_summary.csv",
            "primary_use": "1%, 2%, and 5% contamination-threshold sensitivity",
            "notes": "Supports robustness of candidate-set construction.",
        },
        {
            "result_block": "caption_plan",
            "artifact": "reports/tables/mrv_paper_figure_captions.csv",
            "primary_use": "Figure captions and manuscript messages",
            "notes": "Use for final figure list and caption polishing.",
        },
        {
            "result_block": "references",
            "artifact": "references/mrv_effscreen_refs.bib",
            "primary_use": "BibTeX seed file for official, MRV, ML, and anomaly-detection references",
            "notes": "Needs final Zotero/EndNote verification before submission.",
        },
    ]


def main() -> None:
    write_csv(TABLE_DIR / "mrv_paper_key_numbers.csv", build_key_numbers())
    write_csv(TABLE_DIR / "mrv_paper_main_model_results.csv", build_main_model_results())
    write_csv(TABLE_DIR / "mrv_paper_class_metrics.csv", build_class_metrics())
    write_csv(TABLE_DIR / "mrv_paper_ship_type_results.csv", build_ship_type_results())
    write_csv(TABLE_DIR / "mrv_paper_interpretability_results.csv", build_interpretability_results())
    write_csv(TABLE_DIR / "mrv_paper_table_plan.csv", build_table_plan())
    write_csv(TABLE_DIR / "mrv_paper_figure_captions.csv", build_figure_captions())
    write_csv(TABLE_DIR / "mrv_paper_results_index.csv", build_results_index())


if __name__ == "__main__":
    main()
