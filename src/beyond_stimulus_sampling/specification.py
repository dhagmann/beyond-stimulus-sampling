"""Study definitions are data, rather than changes to the generation code."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StudyError(ValueError):
    """A study or its saved research record is inconsistent."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")
    temp.replace(path)


def protect_run_artifact(root: Path, output: Path) -> None:
    root, output = root.resolve(), output.resolve()
    if output in {root / 'manifest.json', root / 'summary.json'} or any(
            output.is_relative_to(root / folder) for folder in ('calls', 'families')):
        raise StudyError('Report or export output cannot overwrite the frozen run record')


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:70] or "construct"
    return result if result[0].isalpha() else "c_" + result


def _text(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise StudyError(f"{label} must be nonempty text")


def _number(value: Any, label: str, minimum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise StudyError(f"{label} must be a finite number")
    if minimum is not None and value < minimum:
        raise StudyError(f"{label} must be at least {minimum}")


def _integer(value: Any, label: str, minimum: int = 1) -> None:
    _number(value, label, minimum)
    if not isinstance(value, int):
        raise StudyError(f"{label} must be an integer")


def validate_provider(provider: dict[str, Any]) -> None:
    if not isinstance(provider, dict) or provider.get("kind") not in {"codex", "claude", "command"}:
        raise StudyError("Provider kind must be codex, claude, or command")
    _text(provider.get("model"), "provider.model")
    if provider.get("effort", "low") not in {"minimal", "low", "medium", "high", "xhigh", "max"}:
        raise StudyError("Unknown provider effort")
    _integer(provider.get("timeout_seconds", 300), "provider.timeout_seconds")
    if provider["kind"] == "command":
        argv = provider.get("command")
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv):
            raise StudyError("An external provider needs a nonempty argv list, not a shell string")


def validate_study(study: dict[str, Any], *, reviewed: bool = True) -> None:
    try:
        _validate_study(study, reviewed=reviewed)
    except (KeyError, AttributeError, TypeError) as exc:
        raise StudyError("Malformed study specification; check its fields against a bundled example") from exc


def _validate_study(study: dict[str, Any], *, reviewed: bool = True) -> None:
    if not isinstance(study, dict) or study.get("schema_version") != "1.0":
        raise StudyError("Expected a version 1.0 study specification")
    for key in ("title", "context", "focal_construct"):
        _text(study.get(key), key)
    dimensions = study.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise StudyError("A study needs measurement dimensions")
    ids: set[str] = set()
    factors = []
    for dim in dimensions:
        if not isinstance(dim, dict):
            raise StudyError("Each dimension must be an object")
        for key in ("id", "name", "definition", "low_anchor", "high_anchor"):
            _text(dim.get(key), f"dimension.{key}")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", dim["id"]):
            raise StudyError("Dimension IDs must use lower-case letters, numbers, and underscores")
        if dim["id"] in ids:
            raise StudyError(f"Duplicate dimension: {dim['id']}")
        ids.add(dim["id"])
        if dim.get("role") not in {"factor", "protected", "consequence"}:
            raise StudyError(f"Unknown role for {dim['id']}")
        for facet in dim.get("facets", []):
            _text(facet.get("name"), "facet.name")
            _text(facet.get("definition"), "facet.definition")
        if dim["role"] == "factor":
            levels = dim.get("levels")
            if not isinstance(levels, list) or not 2 <= len(levels) <= 7:
                raise StudyError("Each factor needs between two and seven ordered levels")
            level_ids = []
            for level in levels:
                _text(level.get("id"), "level.id")
                _text(level.get("instruction"), "level.instruction")
                if not re.fullmatch(r"[a-z][a-z0-9_]*", level["id"]):
                    raise StudyError("Level IDs must use lower-case letters, numbers, and underscores")
                level_ids.append(level["id"])
            if len(set(level_ids)) != len(level_ids):
                raise StudyError("Factor levels must have unique IDs")
            factors.append(dim)
    if study["focal_construct"] not in {d["id"] for d in factors}:
        raise StudyError("The focal construct must be an experimental factor")
    size = math.prod(len(f['levels']) for f in factors)
    if size > 128:
        raise StudyError("This prototype supports at most 128 cells per family; simplify the design")
    if len({c["id"] for c in cells_for(study)}) != math.prod(len(d["levels"]) for d in factors):
        raise StudyError("Factor and level IDs produce ambiguous cell IDs; use simpler IDs")
    blueprints = study.get("blueprints")
    if not isinstance(blueprints, list) or not blueprints:
        raise StudyError("Provide at least one shared scenario blueprint")
    seen = set()
    for bp in blueprints:
        _text(bp.get("id"), "blueprint.id")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", bp["id"]) or bp["id"] in seen:
            raise StudyError("Blueprint IDs must be safe and unique")
        seen.add(bp["id"])
        _text(bp.get("context"), "blueprint.context")
        facts = bp.get("required_content")
        if not isinstance(facts, list) or not facts:
            raise StudyError("Each blueprint needs shared facts or substantive points")
        for fact in facts:
            _text(fact, "required_content")
        if 'sampling' in bp:
            pool = bp['sampling']
            if not isinstance(pool, dict):
                raise StudyError('Blueprint sampling must be an object')
            for field in ('content_pool', 'style_pool'):
                entries = pool.get(field)
                if not isinstance(entries, list) or not entries:
                    raise StudyError(f'{field} must be a nonempty list')
                for entry in entries:
                    _text(entry, field)
                if len(set(' '.join(x.casefold().split()) for x in entries)) != len(entries):
                    raise StudyError(f'{field} contains duplicate entries')
            _integer(pool.get('content_per_family'), 'content_per_family')
            if pool['content_per_family'] > len(pool['content_pool']):
                raise StudyError('Cannot sample more content points than are available')
    _integer(study.get("families_per_context"), "families_per_context")
    _integer(study.get("seed"), "seed", 0)
    settings = study.get("generation", {})
    for key in ("min_words", "max_words", "max_word_range", "max_attempts"):
        _integer(settings.get(key), f"generation.{key}", 0 if key == "max_word_range" else 1)
    if settings["max_words"] < settings["min_words"]:
        raise StudyError("Maximum words must be at least minimum words")
    if 'writer' in settings:
        validate_provider(settings['writer'])
    if 'writers' in settings:
        profiles = settings['writers']
        if not isinstance(profiles, list) or not profiles:
            raise StudyError('generation.writers must be a nonempty list')
        names = set()
        for profile in profiles:
            _text(profile.get('name'), 'writer.name')
            if profile['name'] in names:
                raise StudyError('Writer profile names must be unique')
            names.add(profile['name'])
            validate_provider(profile)
    elif 'writer' not in settings:
        raise StudyError('Configure a writer provider or named writer profiles')
    judges = settings.get("judges")
    if not isinstance(judges, list) or not judges:
        raise StudyError("At least one judge is required")
    judge_names = set()
    for judge in judges:
        _text(judge.get("name"), "judge.name")
        if judge["name"] in judge_names:
            raise StudyError("Judge names must be unique")
        judge_names.add(judge["name"])
        validate_provider(judge)
    criteria = study.get("assessment", {})
    for key in ("scale_min", "scale_max", "min_target_difference", "max_spillover",
                "min_content_fidelity", "min_fluency", "naturalness_review_below"):
        _number(criteria.get(key), f"assessment.{key}")
    lo, hi = criteria["scale_min"], criteria["scale_max"]
    if hi <= lo:
        raise StudyError("Rating scale maximum must exceed minimum")
    if not 0 < criteria["min_target_difference"] <= hi - lo or not 0 <= criteria["max_spillover"] <= hi - lo:
        raise StudyError("Contrast thresholds must fit the rating scale")
    for key in ("min_content_fidelity", "min_fluency", "naturalness_review_below"):
        if not lo <= criteria[key] <= hi:
            raise StudyError(f"{key} must fit the rating scale")
    for factor in factors:
        if (len(factor["levels"]) - 1) * criteria["min_target_difference"] > hi - lo:
            raise StudyError(f"Target threshold is infeasible for {factor['name']}'s number of levels")
    _integer(criteria.get("critical_issue_consensus", 1), "critical_issue_consensus")
    if criteria.get("critical_issue_consensus", 1) > len(judges):
        raise StudyError("Issue consensus cannot exceed the number of judges")
    if not isinstance(study.get('writing_requirements', []), list):
        raise StudyError('writing_requirements must be a list')
    for requirement in study.get("writing_requirements", []):
        _text(requirement, "writing requirement")
    decisions = study.get("candidate_review", [])
    if not isinstance(decisions, list):
        raise StudyError("candidate_review must be a list")
    allowed = {"same_construct", "spillover", "factor", "consequence", "ignore"}
    for decision in decisions:
        if decision.get("classification") not in allowed:
            raise StudyError("Every proposed construct needs a researcher classification")
        _text(decision.get("rationale"), "classification rationale")
        _text(decision.get("construct", {}).get("name"), "reviewed construct name")
        destination = decision.get("dimension_id")
        if decision["classification"] != "ignore" and destination not in ids:
            raise StudyError("A construct classification must link to an existing dimension")
        role = {"spillover": "protected", "factor": "factor", "consequence": "consequence"}.get(decision["classification"])
        if role and next(d for d in dimensions if d["id"] == destination)["role"] != role:
            raise StudyError("Construct classification and dimension role disagree")
        if decision["classification"] == "same_construct" and destination != study["focal_construct"]:
            raise StudyError("Included facets must link to the focal construct")
    review = study.get("researcher_review", {})
    if not isinstance(review.get("completed"), bool):
        raise StudyError("researcher_review.completed must be true or false")
    if review["completed"]:
        _text(review.get("reviewer"), "researcher reviewer")
    if reviewed and not review["completed"]:
        raise StudyError("Complete the researcher review before generation")


def cells_for(study: dict[str, Any]) -> list[dict[str, Any]]:
    factors = [d for d in study["dimensions"] if d["role"] == "factor"]
    return [
        {"id": "__".join(f"{factor['id']}_{level['id']}" for factor, level in zip(factors, values)),
         "levels": {factor["id"]: level["id"] for factor, level in zip(factors, values)}}
        for values in itertools.product(*(factor["levels"] for factor in factors))
    ]


def dimension_summary(study: dict[str, Any]) -> str:
    lines = [study["title"], f"Context: {study['context']}"]
    for d in study["dimensions"]:
        role = {"factor": "independently manipulated", "protected": "protected from spillover",
                "consequence": "measured consequence; not a rejection criterion"}[d["role"]]
        levels = ", ".join(x["id"] for x in d.get("levels", []))
        lines.append(f"  {d['name']}: {role}" + (f" ({levels})" if levels else ""))
        for facet in d.get("facets", []):
            lines.append(f"    Part of this construct: {facet['name']}")
    total = len(cells_for(study)) * len(study["blueprints"]) * study["families_per_context"]
    lines.append(f"Design: {len(cells_for(study))} cells per family; {total} planned messages")
    lines.append("Acceptance means model screening, not human construct validation.")
    return "\n".join(lines)


def writer_profiles(study: dict) -> list[dict]:
    settings = study['generation']
    return settings.get('writers') or [{'name': 'writer', **settings['writer']}]


def review_details(study: dict) -> str:
    """Show the inputs a researcher is approving without echoing adapter argv."""
    lines = [dimension_summary(study), '\nDefinitions, anchors, and instructions:']
    for dimension in study['dimensions']:
        lines += [f"\n{dimension['name']} ({dimension['role']})",
                  f"  Definition: {dimension['definition']}",
                  f"  Low anchor: {dimension['low_anchor']}",
                  f"  High anchor: {dimension['high_anchor']}"]
        for facet in dimension.get('facets', []):
            lines.append(f"  Included facet: {facet['name']} — {facet['definition']}")
        for level in dimension.get('levels', []):
            lines.append(f"  {level['id']}: {level['instruction']}")
        if dimension.get('hold_constant'):
            lines.append('  Hold fixed: ' + dimension['hold_constant'])
    for blueprint in study['blueprints']:
        lines += [f"\nContext {blueprint['id']}: {blueprint['context']}", '  Required content:']
        lines.extend('  - ' + point for point in blueprint['required_content'])
        if 'sampling' in blueprint:
            pool = blueprint['sampling']
            lines.append(f"  Draw {pool['content_per_family']} content points per family:")
            lines.extend('  - ' + point for point in pool['content_pool'])
            lines.append('  Style pool:')
            lines.extend('  - ' + style for style in pool['style_pool'])
    if study.get('writing_requirements'):
        lines += ['\nWriting requirements:', *('  - ' + text for text in study['writing_requirements'])]
    settings = study['generation']
    lines.append(f"\nLength: {settings['min_words']}–{settings['max_words']} words; "
                 f"spread ≤ {settings['max_word_range']}; attempts ≤ {settings['max_attempts']}")
    for role, providers in [('Writer', writer_profiles(study)), ('Judge', settings['judges'])]:
        for provider in providers:
            lines.append(f"{role} {provider.get('name', '')}: {provider['kind']} / {provider['model']} "
                         f"(effort {provider.get('effort', 'low')})")
    return '\n'.join(lines)
