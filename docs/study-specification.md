# Study specifications

`bss init` writes a JSON study file. All study-specific definitions and criteria live there. The [examples](../examples/) show complete specifications. `bss review` validates the file and shows its definitions, anchors, level instructions, shared material, pools, model configurations, and criteria. `bss review --complete` records a researcher's acceptance of an example or draft. Starting a run requires `researcher_review.completed: true`.

| Field | Meaning |
| --- | --- |
| `schema_version` | Currently `1.0`. |
| `title`, `context` | Study label and general research setting. |
| `focal_construct` | ID of the primary manipulated dimension. |
| `dimensions` | Definitions, anchors, roles, and any ordered levels or included facets. |
| `candidate_review` | Candidate attributes, researcher classifications and rationales, and links to the resulting dimensions. |
| `blueprints` | Distinct scenario IDs, contexts, required shared content, and optional reviewed content/style pools. |
| `families_per_context` | Independently generated message families for each blueprint. |
| `seed` | Reproducible pool draws, writer-profile assignment, and blinded message order. This is not a model sampling seed. |
| `writing_requirements` | Optional instructions for style, audience, format, or language. |
| `generation` | A writer or named writer profiles, judges, word limits, allowed within-family word-count spread, and attempt limit. |
| `assessment` | Rating scale, target/spillover thresholds, content/fluency floors, and naturalness-review threshold. |
| `researcher_review` | Whether the design was reviewed, by whom, and when. |
| `setup_provenance` | Wizard proposal fingerprint and source call ID, when created through the wizard. |

Each dimension has an `id`, `name`, `definition`, `low_anchor`, `high_anchor`, and `role`. Roles are `factor`, `protected`, or `consequence`. A factor has 2–7 ordered `levels`, each with an ID and a writing instruction. A facet is stored under the focal dimension's `facets`, rather than becoming a separate measured dimension. A protected dimension may have a `hold_constant` instruction. Consequences appear only in judge requests.

For multiple writer models, supply `generation.writers` with unique names:

```json
{
  "writers": [
    {"name": "writer_a", "kind": "codex", "model": "YOUR_MODEL", "effort": "low", "timeout_seconds": 300},
    {"name": "writer_b", "kind": "claude", "model": "YOUR_OTHER_MODEL", "effort": "low", "timeout_seconds": 300}
  ]
}
```

This list takes precedence over `generation.writer`, which remains supported for single-model studies. The harness assigns profiles in seeded, shuffled blocks within each context, so their counts differ by at most one. A family uses one model for every treatment cell and revision. The assignment is recorded in the manifest and checked during replay. If there are fewer families than writer profiles, some profiles will not be used. Model assignment does not guarantee variation in the generated prose.

A blueprint can include `sampling` with a nonempty `content_pool`, `content_per_family`, and a nonempty `style_pool`. Entries are text, and duplicate entries are rejected after whitespace and case normalization. `content_per_family` cannot exceed the number of points. See [sampling](sampling.md) for the planning command, researcher review, and saved draws. Blueprints without this field remain supported.

IDs use lowercase letters, numbers, and underscores, beginning with a letter. Use distinct, short IDs. The prototype supports up to 128 experimental cells per family, although the cost and interpretability of a large factorial design warrant consideration well before that limit.

Changing a study file cannot change an existing run. Start a new output directory when altering definitions, facts, providers, thresholds, or planned sample size. Retain the earlier record so the design history can be reconstructed. The wizard checkpoint (`*.setup.json`) and saved proposal (`*.proposal.json`) preserve the setup decisions. To revisit a completed setup, start a new study file, optionally reusing its proposal with `--proposal`.

The word counter recognizes Unicode word sequences with internal apostrophes or hyphens. It is intended for space-delimited prose. For languages without word boundaries expressed this way, choose and document an appropriate length measure before extending the engine.
