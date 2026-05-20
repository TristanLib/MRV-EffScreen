# MRV-EffScreen LaTeX Review Draft

This folder contains the LaTeX source, template support files, and figure assets used to build the current MRV-EffScreen English review draft.

Main file:

```text
mrv_effscreen_review_v0.3.2.tex
```

Template support files:

```text
Definitions/
```

Figure assets:

```text
figures/*.pdf
figures/*.png
```

The draft has been compiled locally with TeX Live. The checked English PDF copy is stored at:

```text
output/pdf/MRV-EffScreen_internal_review_en_v0.3.2.pdf
output/pdf/MRV-EffScreen_internal_review_en_latest.pdf
```

Suggested compile command:

```bash
cd manuscript/latex
latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build mrv_effscreen_review_v0.3.2.tex
```

The `build/` directory is a local build cache and is intentionally ignored by Git. Use the PDF copies under `output/pdf/` for review.
