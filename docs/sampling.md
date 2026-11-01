# Content and style sampling

The harness separates variation across families from variation within a family. Substantive points and organizational styles vary across families. Assigned experimental constructs vary within each family while its sampled inputs stay fixed.

## Propose and review pools

After the construct and context have been reviewed through `bss init`, run:

```sh
bss plan study.json --output study-planned.json \
  --content-pool-size 15 --content-per-family 5 --style-pool-size 8
bss review study-planned.json --complete
```

The planner uses the study's writer provider unless `--provider`, `--model`, or `--provider-config` selects another provider. One separate model request proposes both pools for each scenario blueprint. Its inputs contain the context, supplied source material, and the definitions of factors that must remain independently manipulable. They exclude expected-consequence objectives. The prompt forbids outside research, invented evidence, and styles defined by treatment levels.

These instructions do not guarantee factual or theoretical adequacy. Researchers must inspect the suggested points and styles. The planned file is marked unreviewed even if its source study was already approved; generation refuses it until a new researcher review is recorded. Successful planning calls are cached beside the planned file in `*.pool-calls/` for interrupted setup. Those private call records are not included in this repository.

Researchers can also write the pools directly in a study specification:

```json
{
  "id": "workplace_pilot",
  "context": "A manager discusses a hypothetical remote-work pilot.",
  "required_content": ["The proposal is a voluntary, time-limited pilot."],
  "sampling": {
    "content_pool": [
      "Explain how the pilot could reduce commuting.",
      "Explain how shared office days could support coordination.",
      "Explain why an evaluation could inform a later decision."
    ],
    "content_per_family": 2,
    "style_pool": [
      "Open with an everyday example, then explain the proposal.",
      "State the proposal first, then organize the reasons in sequence."
    ]
  }
}
```

All required content remains mandatory. The draw adds the specified number of points to that shared material. Styles describe organization rather than certainty, respect, or another experimental factor. The example is a proposed hypothetical design, not an empirically validated manipulation.

## Draw once, then build the family

The study seed, blueprint ID, and family replicate identify separate pseudo-random streams for content and style. Content is sampled without replacement within a family; the style is selected from the reviewed pool. Sampling across families allows repeated points, styles, or even an identical draw. A finite pool and a seed do not guarantee unique draws or a representative stimulus population.

The manifest saves the selected content indices, style index, pool fingerprint, and resolved shared blueprint. Each writer receives only that family's sampled inputs and its own assigned treatment. Writers do not see the unused pool or other drafts. Judges receive the complete family with shuffled neutral IDs, shared required content, and construct definitions, but no treatment labels or other judges' ratings. Style is not a separately gated construct.

When a comparison fails, the coordinating process requests revisions from the implicated writers using their own drafts and focused feedback. It keeps the sampled inputs unchanged and has all judges reassess the complete family. `bss validate` reconstructs the sampling plan and every request without calling a model. Editing a saved draw, pool, or study causes validation to fail.

The seed controls input selection and blinding order, not hosted-model outputs. Model responses can vary and providers can change their models. The saved record supports exact replay of the archived decisions and conceptual replication of the procedure with other models or researchers.
