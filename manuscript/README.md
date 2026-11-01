# Reproducing the manuscript

This directory contains the Quarto source for *Beyond Stimulus Sampling: A Harness for Designing and Auditing Experimental Stimuli*, the bibliography, vendored APAquarto extension, figure assets, an example audit, and the minimal data needed for the reported analyses. The illustrative experiments were conducted with earlier study-specific workflows. Rebuilding the paper does not call a model or generate a new corpus.

## Requirements

- Quarto with its R/knitr engine.
- R with `knitr`, `rmarkdown`, and `papaja`.
- A LaTeX installation with XeLaTeX and the APA 7 class. Quarto's TinyTeX installation is one option: `quarto install tinytex`.
- The Tinos font (provided by `fonts-croscore` on Debian/Ubuntu).
- Python 3.10 or later and `pikepdf` for generating the blinded source and removing PDF author metadata.

The checked environment used Quarto 1.9.38, R 4.6.2, knitr 1.52, rmarkdown 2.32, papaja 0.1.5, and pikepdf 8.7.1. Other compatible versions may work; line and page breaks can differ. The checked environment is recorded in `build-environment.json`.

Install the R dependencies if necessary:

```r
install.packages(c("knitr", "rmarkdown", "papaja"), repos = "https://cloud.r-project.org")
```

Install the Python metadata utility into your chosen environment:

```sh
python -m pip install -r manuscript/requirements.txt
```

## Build

From the repository root:

```sh
python scripts/check_manuscript_data.py
cd manuscript
quarto render beyond_stimulus_sampling.qmd --to apaquarto-pdf
python prepare_blinded.py --render
```

The outputs are `beyond_stimulus_sampling.pdf` and `beyond_stimulus_sampling_blinded.pdf`. The source loads the included analysis files when they are present. Its original raw-export preprocessing remains as a fallback for the authors' local research project; those raw files are not needed or included here. The APAquarto extension is vendored under `_extensions/` so its modified table-numbering behavior is preserved.

The blinded source removes author and correspondence metadata, suppresses author/affiliation display, and uses an audit PDF without author metadata. The compiled PDF's document metadata are also removed. **The requested GitHub footnote still names the `dhagmann` account.** Anyone needing complete anonymity should account for that identifying link when preparing a review artifact.

The main source is the editable version. Regenerate the blinded source with `prepare_blinded.py` after editing it; do not edit both copies independently.

## Submission files and technical supplement

The two-file submission package consists of:

- `beyond_stimulus_sampling_submission_blinded.pdf`: the main manuscript without the full-message and audit appendices.
- `beyond_stimulus_sampling_technical_supplement_blinded.pdf`: three pages of harness documentation followed by Appendices A–C, including the six complete messages and the one-page audit.

The manuscript's prose is unchanged when the appendices are moved to the supplement. Main-copy appendix links point to named destinations in the companion PDF; keep the filenames together when viewing locally. The original complete manuscript remains available for internal review.

Both submission files use 12-point text, one-inch margins, and double spacing. The main manuscript's reference spacing is slightly reduced so its references fit on one page. The audit is a full-page graphic sized to fit the supplement's text area. Its data and ratings are unchanged.

From the repository root, build both submission files with:

```sh
python manuscript/build_technical_supplement.py --render
```

Edit the technical narrative in `beyond_stimulus_sampling_technical_supplement_blinded.qmd` above the `BEGIN SUPPORTING MATERIALS` marker. The helper regenerates material below that marker from the current main manuscript, preserves the messages, prepares the main-only copy, and removes PDF author metadata. Its output includes the manuscript's requested GitHub link, which identifies the repository owner.

## Data and assets

See [data/README.md](data/README.md) for variable definitions, sample selection, and the fields intentionally omitted from the research exports. Only three small CSV files are needed. `scripts/prepare_manuscript_data.py` can regenerate them when the original exports are available locally; it does not preserve response order or copy survey identifiers.

The figure assets and example audit PDFs are included, so rendering needs no model account, raw survey export, or external research directory. `figures/harness_workflow.py` optionally redraws the workflow diagram with Matplotlib. The example audit is a frozen illustration containing archived LLM ratings; compiling the paper does not rerate it. Its warmth, competence, and trust scores are separate, descriptive GPT-6.1-Sol assessments and were not used to change the original screening decisions.

The repository is public. It includes only the reduced analysis data described above. Raw participant-level exports and private model execution logs are excluded.
