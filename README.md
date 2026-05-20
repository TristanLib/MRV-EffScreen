# MRV-EffScreen

`MRV-EffScreen` is the abbreviation for this paper and reproducibility package:

> MRV-based Efficiency Stratification and Consistency Screening

GitHub repository:

```text
https://github.com/TristanLib/MRV-EffScreen
```

Paper title:

> MRV-EffScreen: Temporal Generalization and Consistency Screening of Ship Energy-Efficiency Labels from Public THETIS-MRV Emission Reports

## Current Status

This public repository is maintained as the reproducibility package for the paper. It contains the code, metadata, generated paper tables and figures, current English manuscript files, and checked English review PDF.

Current manuscript artifacts:

```text
manuscript/mrv_effscreen_review_draft_v0.3.2.md
manuscript/latex/mrv_effscreen_review_v0.3.2.tex
output/pdf/MRV-EffScreen_internal_review_en_v0.3.2.pdf
output/pdf/MRV-EffScreen_internal_review_en_latest.pdf
```

Repository:

```text
https://github.com/TristanLib/MRV-EffScreen
```

## Repository Scope

The repository intentionally excludes internal planning materials, submission-preparation notes, weekly progress logs, old draft iterations, translated review PDFs, private correspondence drafts, and temporary build outputs. Raw THETIS-MRV Excel workbooks are also not stored in Git; use the download script and SHA256 checksums to reproduce the raw-data snapshot.

## Reproduction

Tested environment:

```text
macOS Darwin 25.4.0 arm64
Python 3.14.5
scikit-learn 1.8.0
```

Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Core workflow:

```bash
src/data/download_mrv_public_reports.sh
.venv/bin/python src/data/audit_mrv_workbooks.py
.venv/bin/python src/data/build_mrv_modeling_base.py
.venv/bin/python src/data/audit_mrv_temporal_overlap.py
.venv/bin/python src/models/train_mrv_baselines.py
.venv/bin/python src/models/analyze_mrv_ship_type_effects.py
.venv/bin/python src/models/detect_mrv_anomalies.py
.venv/bin/python src/models/analyze_mrv_anomaly_sensitivity.py
.venv/bin/python src/reports/compile_mrv_paper_assets.py
```

Expected public outputs include:

```text
reports/tables/mrv_paper_key_numbers.csv
reports/tables/mrv_paper_main_model_results.csv
reports/tables/mrv_paper_class_metrics.csv
reports/tables/mrv_paper_label_diagnostics.csv
reports/tables/mrv_paper_imo_overlap_summary.csv
reports/tables/mrv_anomaly_top_candidates.csv
reports/tables/mrv_anomaly_sensitivity_summary.csv
reports/figures/*.svg
```

Compile the LaTeX draft after installing TeX Live or MacTeX:

```bash
cd manuscript/latex
latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build mrv_effscreen_review_v0.3.2.tex
```

## Public Boundary

The public consistency-review table removes direct vessel identifiers. Identity-bearing intermediate consistency-screening outputs are internal audit aids and must not be committed to public releases. The original THETIS-MRV Excel workbooks are not redistributed in Git; the repository stores retrieval metadata and checksums so users can reproduce the public-data snapshot from the original source.

## License

Code and repository documentation are released under the MIT License. Original THETIS-MRV data remain subject to the terms of their public source.

## Citation

Use the project name `MRV-EffScreen` in the manuscript and repository. Citation metadata currently uses Bo Li and the GitHub repository URL. Add the Zenodo DOI after the first archived release if one is minted.
