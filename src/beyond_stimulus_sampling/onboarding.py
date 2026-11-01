"""A researcher-led construct review, with checkpoints before generation."""

from __future__ import annotations

import copy
from pathlib import Path

from .providers import ModelProvider
from .schemas import CONSTRUCT, PROPOSAL, validate
from .specification import (StudyError, dimension_summary, fingerprint, load_json,
                            slug, utc_now, validate_provider, validate_study, write_json)
from .workflow import propose


DEFAULT_MODELS = {"codex": "gpt-6.1-sol", "claude": "claude-opus-5-5"}
CLASSIFICATIONS = {
    "same_construct": "Part of the focal construct: include it in the definition.",
    "spillover": "A separate attribute: hold it comparable across conditions.",
    "factor": "A separate attribute: manipulate it independently as another factor.",
    "consequence": "An expected consequence: measure it, but do not reject messages for changing it.",
    "ignore": "Outside this study's scope: record why, without adding it to the audit.",
}


class Questions:
    def __init__(self, path: Path, *, input_fn=input, output_fn=print):
        self.path, self.input, self.output = path, input_fn, output_fn
        self.state = load_json(path) if path.exists() else {"answers": {}}

    def ask(self, key: str, prompt: str, default: str | None = None, *, check=None) -> str:
        answers = self.state["answers"]
        if key in answers:
            return answers[key]
        while True:
            value = self.input(prompt + (f" [{default}]" if default is not None else "") + ": ").strip()
            value = value or (str(default) if default is not None else "")
            if not value:
                self.output("Please enter a response.")
                continue
            if check:
                try:
                    check(value)
                except (ValueError, StudyError) as exc:
                    self.output(str(exc))
                    continue
            answers[key] = value
            self.save()
            return value

    def save(self):
        write_json(self.path, self.state)

    def yes(self, key: str, prompt: str, default: bool = False) -> bool:
        def check(value):
            if value.lower() not in {"y", "yes", "n", "no"}:
                raise ValueError("Enter yes or no.")
        return self.ask(key, prompt + " (yes/no)", "yes" if default else "no", check=check).lower() in {"y", "yes"}

    def number(self, key, prompt, default, *, minimum=0, maximum=None, integer=False):
        cast = int if integer else float
        def check(value):
            number = cast(value)
            if not minimum <= number < float("inf"):
                raise ValueError(f"Enter a finite number at least {minimum}.")
            if maximum is not None and number > maximum:
                raise ValueError(f"Enter a number no greater than {maximum}.")
        return cast(self.ask(key, prompt, str(default), check=check))


def levels_for(q: Questions, key: str, construct: dict) -> list[dict]:
    count = q.number(key + "_count", f"How many ordered levels for {construct['name']}? (2–7)", 2,
                     minimum=2, maximum=7, integer=True)
    levels = []
    for i in range(count):
        default_id = ("low" if i == 0 else "high") if count == 2 else f"level_{i + 1}"
        level_id = slug(q.ask(f"{key}_{i}_id", f"Name for level {i + 1} (lowest to highest)", default_id))
        instruction = construct["low_anchor"] if i == 0 else construct["high_anchor"] if i == count - 1 else None
        instruction = q.ask(f"{key}_{i}_instruction", f"Writing instruction for {level_id}", instruction)
        levels.append({"id": level_id, "instruction": instruction})
    return levels


def review_construct(q: Questions, key: str, construct: dict, *, focal: bool = False) -> dict:
    value = {k: construct[k] for k in CONSTRUCT["properties"]}
    q.output(f"\n{'Focal construct' if focal else 'Candidate'}: {value['name']}\nDefinition: {value['definition']}"
             f"\nLow: {value['low_anchor']}\nHigh: {value['high_anchor']}")
    if q.yes(key + "_edit", "Edit this name, definition, or anchors?"):
        for field in CONSTRUCT["properties"]:
            value[field] = q.ask(key + "_" + field, field.replace("_", " ").capitalize(), value[field])
    return value


def build_study(q: Questions, proposal: dict, provider_config: dict) -> dict:
    """Interpret researcher answers; a model never assigns a construct's role."""
    target = review_construct(q, "target", proposal["proposal"]["target"], focal=True)
    focal_id = slug(target["name"])
    focal = {"id": focal_id, **target, "role": "factor", "facets": [],
             "levels": levels_for(q, "target_levels", target)}
    dimensions, decisions = [focal], []
    q.output("\nFor each candidate, decide what changing it would mean for YOUR research question."
             "\nRelatedness alone does not establish spillover. A facet belongs in the target; an expected"
             "\nconsequence should usually be measured without selecting messages to suppress it.")
    candidates = copy.deepcopy(proposal["proposal"]["candidates"])
    index = 0
    while True:
        if index >= len(candidates):
            if not q.yes(f"add_candidate_{index}", "Add another construct the model missed?"):
                break
            custom = {field: q.ask(f"custom_{index}_{field}", field.replace("_", " ").capitalize())
                      for field in CONSTRUCT["properties"]}
            candidates.append({**custom, "why_related": "Added by researcher", "example_change": "Researcher-specified candidate"})
        candidate = candidates[index]
        key = f"candidate_{index}"
        q.output(f"\nWhy consider {candidate['name']}? {candidate['why_related']}"
                 f"\nExample change: {candidate['example_change']}")
        construct = review_construct(q, key, candidate)
        for number, (classification, explanation) in enumerate(CLASSIFICATIONS.items(), 1):
            q.output(f"  {number}. {explanation} ({classification})")
        def check_choice(value):
            if value not in [str(i) for i in range(1, 6)] + list(CLASSIFICATIONS):
                raise ValueError("Choose 1–5 or a classification name.")
        choice = q.ask(key + "_classification", "Your classification", check=check_choice)
        classification = list(CLASSIFICATIONS)[int(choice) - 1] if choice.isdigit() else choice
        rationale = q.ask(key + "_rationale", "Why is this the appropriate treatment for this research question?")
        dimension_id = None
        if classification == "same_construct":
            focal["facets"].append(construct)
            dimension_id = focal_id
        elif classification != "ignore":
            dimension_id = slug(construct["name"])
            if dimension_id in {d["id"] for d in dimensions}:
                dimension_id += f"_{index + 1}"
            role = {"spillover": "protected", "factor": "factor", "consequence": "consequence"}[classification]
            dimension = {"id": dimension_id, **construct, "role": role}
            if role == "factor":
                dimension["levels"] = levels_for(q, key + "_levels", construct)
            elif role == "protected":
                dimension["hold_constant"] = q.ask(key + "_hold", "What should writers preserve about this attribute?",
                    "Keep this attribute comparable across versions; do not use changes in it to express the target construct.")
            dimensions.append(dimension)
        decisions.append({"construct": construct, "classification": classification,
                          "rationale": rationale, "dimension_id": dimension_id,
                          "source": "researcher_added" if candidate["why_related"] == "Added by researcher" else "model_suggestion"})
        index += 1

    blueprints = []
    q.output("\nNow define the material to hold constant within each message family. Enter shared"
             "\nfacts, claims, or substantive points explicitly; the model should not invent them."
             "\nSeparate points with |. Each context generates all experimental combinations.")
    index = 0
    while True:
        bp_context = q.ask(f"context_{index}", f"Scenario/context {index + 1}", proposal["context"] if index == 0 else None)
        required = q.ask(f"content_{index}", "Required content (separate points with |)")
        blueprints.append({"id": f"context_{index + 1}", "context": bp_context,
                           "required_content": [x.strip() for x in required.split("|") if x.strip()]})
        if not q.yes(f"more_context_{index}", "Add another scenario/context?"):
            break
        index += 1
    families = q.number("families", "How many independently generated families per context?", 5, minimum=1, integer=True)
    min_words = q.number("min_words", "Minimum message length in words", 150, minimum=1, integer=True)
    max_words = q.number("max_words", "Maximum message length in words", 220, minimum=min_words, integer=True)
    requirements = q.ask("requirements", "Other writing requirements (use | between items, or enter none)", "none")
    writing_requirements = [] if requirements.lower() == "none" else [x.strip() for x in requirements.split("|") if x.strip()]
    settings = {"min_words": min_words, "max_words": max_words, "max_word_range": 40,
                "max_attempts": 3, "writer": copy.deepcopy(provider_config), "judges": []}
    q.output("\nThe default judges are two separate calls to your chosen model. Different model families"
             "\ncan provide a useful cross-check; repeated calls to one model are not independent validation.")
    for number in (1, 2):
        config = copy.deepcopy(provider_config)
        if q.yes(f"judge_{number}_custom", f"Use a different provider/model for judge {number}?"):
            config = ask_provider(q, f"judge_{number}")
        settings["judges"].append({"name": f"judge_{number}", **config})
    assessment = {"scale_min": 1, "scale_max": 7, "min_target_difference": 1.5,
                  "max_spillover": 0.75, "min_content_fidelity": 5,
                  "min_fluency": 5, "naturalness_review_below": 4, "critical_issue_consensus": 1}
    q.output("\nStarting criteria on a 1–7 scale: target difference ≥1.5 per ordered step; mean absolute"
             "\nspillover ≤0.75; content fidelity and fluency ≥5; naturalness below 4 flags human review."
             "\nThese are editable starting values, not validated equivalence bounds. Calibrate them"
             "\nagainst human judgments and choose them before generating your final corpus.")
    if q.yes("custom_settings", "Customize these criteria or revision limits?"):
        for key in assessment:
            assessment[key] = q.number("assessment_" + key, key.replace("_", " "), assessment[key],
                                       minimum=0 if key in {"max_spillover", "scale_min"} else 0.001,
                                       integer=key == "critical_issue_consensus")
        for key in ("max_word_range", "max_attempts"):
            settings[key] = q.number(key, key.replace("_", " "), settings[key],
                                     minimum=0 if key == "max_word_range" else 1, integer=True)
    study = {"schema_version": "1.0", "title": q.ask("title", "Study title", f"{target['name']} in context"),
             "context": proposal["context"], "focal_construct": focal_id,
             "dimensions": dimensions, "candidate_review": decisions, "blueprints": blueprints,
             "families_per_context": families, "seed": 2026,
             "writing_requirements": writing_requirements, "generation": settings, "assessment": assessment,
             "setup_provenance": {"proposal_sha256": fingerprint(proposal), "proposal_call_id": proposal.get("call_id"),
                                  "notice": "Definitions and classifications require researcher judgment."},
             "researcher_review": {"completed": False}}
    validate_study(study, reviewed=False)
    q.output("\n" + dimension_summary(study))
    q.output("\nInspect both the construct boundary decisions and the full design before generation."
             "\nModel screening cannot establish discriminant validity or rule out unmeasured spillover.")
    complete = q.yes("complete", "Have you reviewed and accepted this study specification?", True)
    study["researcher_review"] = {"completed": complete, "completed_at": utc_now() if complete else None,
                                  "reviewer": q.ask("reviewer", "Researcher/reviewer name") if complete else None}
    return study


def ask_provider(q: Questions, key: str) -> dict:
    def check(value):
        if value not in {"codex", "claude", "command"}:
            raise ValueError("Choose codex, claude, or command.")
    kind = q.ask(key + "_kind", "Provider (codex, claude, command)", "codex", check=check)
    model = q.ask(key + "_model", "Model name", DEFAULT_MODELS.get(kind, "my-model"))
    config = {"kind": kind, "model": model, "effort": "low", "timeout_seconds": 300}
    if kind == "command":
        path = q.ask(key + "_config", "Path to provider JSON (contains command argv; put credentials in the environment)")
        config = load_json(Path(path).expanduser())
    validate_provider(config)
    return config


def initialize(output: Path, *, provider_config: dict | None = None, proposal_path: Path | None = None,
               resume: bool = False, input_fn=input, output_fn=print, provider_factory=ModelProvider) -> dict:
    output = Path(output)
    checkpoint = output.with_suffix(".setup.json")
    if output.exists():
        raise StudyError("The study file already exists; choose a new output path to protect its review record")
    if checkpoint.exists() and not resume:
        raise StudyError(f"A setup checkpoint exists; use --resume or a new output path: {checkpoint}")
    q = Questions(checkpoint, input_fn=input_fn, output_fn=output_fn)
    q.output("Define your construct and context first. A model will suggest related attributes; YOU decide"
             "\nwhether each is part of the construct or represents spillover, a factor, or a consequence."
             "\nAnswers are saved after each step. Use the same init command with --resume if interrupted.")
    try:
        if "proposal" not in q.state and not proposal_path:
            q.ask("construct", "What construct do you want to manipulate?")
            q.ask("context", "In what context? Include speaker, audience, message, and research question")
        if "provider" not in q.state:
            q.state["provider"] = provider_config or ask_provider(q, "writer")
            q.save()
        elif provider_config is not None and provider_config != q.state["provider"]:
            raise StudyError("Provider differs from the saved setup; use the original settings or a new output path")
        config = q.state["provider"]
        if "proposal" not in q.state:
            if proposal_path:
                proposal = load_json(proposal_path)
            else:
                construct = q.ask("construct", "What construct do you want to manipulate?")
                context = q.ask("context", "In what context? Include speaker, audience, message, and research question")
                q.output("Generating candidate constructs from that context…")
                proposal = propose(construct, context, provider_factory(config),
                                   output.parent / (output.stem + ".setup-calls"))
            for field in ("construct", "context"):
                if not isinstance(proposal.get(field), str) or not proposal[field].strip():
                    raise StudyError(f"Proposal is missing {field}")
            validate(proposal.get("proposal"), PROPOSAL)
            q.state["proposal"] = proposal
            q.save()
        study = build_study(q, q.state["proposal"], config)
        write_json(output, study)
        write_json(output.with_suffix(".proposal.json"), q.state["proposal"])
        output_fn(f"Saved study specification: {output}")
        return study
    except (EOFError, KeyboardInterrupt):
        q.save()
        raise StudyError(f"Setup paused. Resume with: bss init --output {output} --resume") from None
