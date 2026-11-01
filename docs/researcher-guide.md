# Using the harness in a study

## 1. Define the manipulation before writing messages

Start with the construct, the setting, and the comparison the experiment should identify. “Certainty” by itself leaves substantial ambiguity. A fuller description names the speaker and audience, what the message concerns, and which aspect of certainty should vary.

The wizard uses that information to propose a definition, low and high rating anchors, and related attributes. The proposals are prompts for theoretical judgment. They are not a literature review or evidence of discriminant validity. Edit a definition that does not match your theory, and add attributes the model missed.

For each related attribute, the wizard asks whether it is a facet of the focal construct, a distinct source of spillover, another experimental factor, an expected consequence, or outside the study's scope. The distinction depends on the research question. An attribute that belongs within one researcher's definition may be a confound in another design. Record the reasoning rather than relying on the model's sense of semantic similarity.

Expected consequences need special care. If transparency is supposed to increase trust, selecting messages to eliminate trust differences could remove the effect being studied. The consequence category allows diagnostic ratings without making them acceptance criteria or giving writers an instruction to suppress them. Those ratings do not substitute for an experiment with participants.

## 2. Define the stimulus population and shared material

Specify one or more scenario blueprints. Each blueprint contains the context and the substantive facts, claims, or points that every version should preserve. The model is instructed to use that material rather than invent supporting facts. Provide factual content that can remain constant while the intended attribute changes. If a manipulation inherently changes substantive information, decide explicitly which changes belong to the treatment and describe that scope in the construct definition and blueprint.

A family contains every combination of the factors' ordered levels for one blueprint. Generating several families gives multiple realizations of that blueprint; adding blueprints supplies variation in substantive context. Choose contexts to represent the population to which you want to generalize. The harness does not make a convenience set of topics representative.

For variation in content and organization, use `bss plan` to propose pools before running the study. Review and edit the resulting points and styles, then record approval with `bss review --complete`. For each family the engine draws points and a style once and shares those inputs across conditions. Revisions use the original draw. This allows content and style to vary between families while being yoked within a family. The [sampling guide](sampling.md) describes the saved plan and its limitations.

Writers receive each assigned perspective in a separate call, without other conditions' drafts. The same blueprint does not imply a word-for-word template. The content and style checks instead assess whether the resulting family preserves the intended shared material.

The wizard can configure more than one writer model. The harness assigns these models across families in balanced, seeded blocks within each context, and keeps the writer model fixed across all conditions and revisions within a family. Each judge also has its own model configuration and receives a separate context without other judges' ratings. Changing providers does not require changes to the engine.

## 3. Choose screening rules before the final run

All measured dimensions use the study's numerical rating scale and construct-specific anchors. For a target contrast, the mean signed difference across judges must meet the minimum difference, with no judge assigning a reversed ordering. With more than two ordered levels, the minimum is multiplied by the number of steps between the compared levels. Every pair is checked at fixed levels of the other factors.

For each off-target dimension, the harness takes the absolute difference within each judge and then averages those values. Taking absolute values before averaging prevents opposing judge assessments from cancelling out. This check covers protected attributes and unintended changes in other manipulated factors. Consequence dimensions are reported without a gate.

Content fidelity, fluency, word limits, and the allowed word-count spread have separate checks. Judges can flag material content, organization, or coherence problems using exact quotations from the corresponding message. The default rejects a critical issue raised by any judge. The consensus requirement is configurable. Naturalness concerns trigger human-review flags rather than automatic rejection. An uncommon combination of attributes should not fail merely because it is uncommon.

Judges may identify an attribute missing from the specification and flag it as `unexpected_construct`. The console and reports surface the concern for researcher judgment. It does not automatically reject the family or become a writer objective. If the concern warrants changing the construct boundary or criteria, review the specification and start a new run, preserving the earlier record.

The numerical defaults are provisional. A rating difference below a chosen threshold is a descriptive model-screening result, not an equivalence test or proof of no confounding. Calibrate ratings and bounds against human judgments in your setting. Choose the rules before producing the final corpus; retain the full revision history. The software does not perform statistical inference, fit persuasion models, or adjust participant analyses.

## 4. Inspect the process and validate with people

Use the HTML report to read the messages alongside the ratings and contrasts. Inspect rejected attempts as well as accepted ones: repeated failure to separate two constructs may reveal a conceptual boundary problem or a limitation of the generator and judges. The harness stops after the configured number of attempts and reports an incomplete corpus rather than silently dropping the planned families.

Each completed run writes a full report and compact family audits. Use `bss audit RUN --family ID` to regenerate one audit. The compact version displays construct roles, individual judge ratings, intended contrasts, the largest mean absolute spillover for each rated off-target attribute, and the chosen cutoffs. It links to the full messages and revision history. Small designs can fit one printed page. Larger families, additional dimensions, and detailed concerns may extend it.

Different models can supply a useful cross-check, but model calls are not independent human raters. Judges may share blind spots with writers or each other. A protected-attribute audit covers only what was included in the specification. Review messages for omitted attributes, and use human pretests to assess the manipulation, spillover, plausibility, and fit to the intended population. Avoid selecting messages on the participant outcome you later want to estimate.

When reporting the method, describe the construct decisions, stimulus population, number of planned and retained families, providers and model identifiers, criteria, revisions, human-review flags, and human validation. Distinguish model screening from participant evidence. Archive the reviewed specification and the run record with the exact software version used.
