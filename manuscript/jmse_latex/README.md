# JMSE LaTeX Submission Draft

This folder contains the MDPI ACS LaTeX template package and the MRV-EffScreen JMSE draft.

Main file:

```text
mrv_effscreen_jmse_v0.2.tex
```

Official template support files:

```text
Definitions/
```

Submission figure assets:

```text
figures/*.pdf
figures/*.png
```

The draft has been compiled locally with TeX Live. The checked English PDF copy is stored at:

```text
output/pdf/MRV-EffScreen_JMSE_en_v0.2.pdf
output/pdf/MRV-EffScreen_JMSE_en_latest.pdf
```

Suggested compile command:

```bash
cd manuscript/jmse_latex
latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build mrv_effscreen_jmse_v0.2.tex
```

The `build/` directory is a local build cache and is intentionally ignored by Git. Use the PDF copies under `output/pdf/` for review.
