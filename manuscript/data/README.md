# Analysis-only data

These files are the deliberately reduced inputs needed to compile the manuscript. They contain no Prolific IDs, Qualtrics response IDs, IP addresses, latitude/longitude or other locations, start/end/recorded timestamps, demographics, comments, or participant-specific message text. Original response order is shuffled. There is no participant key or cross-file linking identifier.

| File | Rows | Included variables |
| --- | ---: | --- |
| `study1_analysis.csv` | 600 | `certainty`, `persuasion`, `perceived_certainty` |
| `study2_analysis.csv` | 3,185 | `certainty`, `brashness`, `persuasion` |
| `sample_flow.csv` | 2 | Study label and completed, no-message, and analyzed counts |

`certainty` and `brashness` are the assigned `low`/`high` conditions. `persuasion` is the posterior estimate minus the prior estimate, multiplied by the argument direction: +1 when the message argues for a higher estimate and −1 when it argues for a lower one. Positive values therefore indicate belief movement toward the message's position. The scale is percentage points.

Study 1's `perceived_certainty` converts the author's certainty rating to 1–5: Not at all, Slightly, Somewhat, Very, Extremely. Study 2 has no corresponding certainty-check variable in the manuscript's analysis.

Both studies retain completed survey responses with the Qualtrics `Status` category recorded as `IP Address`. That category is used locally to distinguish actual survey responses from previews; the IP address itself is neither needed nor exported. Study 1 contributes 600 observations. Study 2 has 3,200 completed responses; 15 without a message are excluded, leaving 3,185. The first two Qualtrics question-label/import-ID rows are excluded before processing.

The reduction script reads only the columns needed to make these variables and writes an explicit allowlist. It selects the final occurrence of Study 1's duplicated `politics` header, which records the argument direction. It never exports the earlier political-orientation response. The original Qualtrics files are not included.

From the repository root, with your own authorized local copies of the exports:

```sh
python scripts/prepare_manuscript_data.py \
  --study1 /path/to/study1.csv \
  --study2 /path/to/study2.csv \
  --output manuscript/data
python scripts/check_manuscript_data.py
```

The included data reproduce the manuscript's descriptive summaries, Welch t-tests, and conventional-standard-error factorial OLS model. No robust-standard-error or multiple-comparison adjustment is added. These files support the reported illustration rather than every possible analysis of the original studies.
