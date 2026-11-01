# Working on this package

- Keep all study-specific constructs, contexts, levels, and criteria in specifications, not engine code.
- The researcher owns construct classifications; models propose candidates and supply screening judgments.
- Consequence ratings must not gate acceptance or become writer objectives.
- Preserve rejected attempts, blinded mappings, cached calls, and the distinction between model screening and human validation.
- Keep synthetic fixtures visibly labelled. Do not add raw or identifying participant data, credentials, or private model execution logs. The user-authorized manuscript reproduction data are limited to the exact allowlist checked by `scripts/check_manuscript_data.py`.
- Run `python -m unittest discover -s tests -v` and the offline demo after substantive changes. CI must not call live models.
- Publish authorized changes directly to `main`; do not open a pull request unless explicitly requested.
