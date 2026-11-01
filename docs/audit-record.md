# The saved audit record

A run stores:

```text
manifest.json                  Frozen study, family plan, study and protocol hashes
calls/<request-sha256>.json     Exact request, parsed response, response hash, execution receipt
families/<id>/attempt_001.json  Texts, call links, blinded mappings, ratings, gate decision
families/<id>/attempt_002.json  Revisions and the new complete-family assessment
summary.json                   Completion counts and remaining review flags
report.html                    Optional standalone report
messages.json                  Optional export for human review and validation
```

The record retains rejected attempts, not only the selected messages. Revisions target the cells implicated in a failed check; each new attempt re-evaluates the complete family. Writers see their own prior draft and relevant feedback, without other conditions' texts. Judges receive shuffled message IDs, construct definitions, and anchors, without treatment assignments or dimension roles. The saved blind mappings allow offline reconstruction.

`bss validate RUN` makes no model calls. It checks the frozen study and family plan; the hashes of the generation, prompt, schema, provider, specification, and gate sources; cached requests and responses; writer text provenance; targeted revision history; blinded judge requests and responses; and recomputed acceptance decisions. It reports incomplete runs explicitly. Report and export commands perform this validation before using saved results.

Hashes detect inconsistent records; they are not signatures or proof that an investigator could not rewrite an entire archive. Record the Git commit or release alongside the archive. A run requires its original protocol sources for validation and resume. Save the matching release rather than silently replaying old runs under new rules. The synthetic demo creates a fresh record under the installed version and labels its fixed messages and invented judgments throughout.

Cache keys include the provider configuration, system instructions, prompt, output schema, and a sampling-slot identifier. The identifier distinguishes family replicates and judge calls with otherwise identical requests. Repeating an interrupted run reuses successful calls for the same slots; changing model, instructions, or criteria requires a new run. The seed fixes content/style draws and message order, not model output or hidden provider versions. A cached replay is reproducible; regenerating through a hosted model need not return the same text.

Before a public release, prepare a deliberate archive of the study settings, relevant prompts, messages, ratings, and code version. Inspect its contents for confidential scenarios and other restricted material. The repository's default ignores local run folders and setup files. The software demonstration and example specifications are suitable for trying the workflow but are not the certainty–persuasion project's data or evidence.
