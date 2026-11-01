"""Frozen runs, cached calls, targeted revision, and model-free replay."""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Callable

from . import PROTOCOL_VERSION
from . import gate, prompts, schemas
from .providers import ModelProvider
from .sampling import sample_family
from .specification import StudyError, cells_for, fingerprint, load_json, utc_now, validate_study, write_json


def protocol_fingerprint() -> str:
    here = Path(__file__).parent
    names = ("prompts.py", "schemas.py", "specification.py", "gate.py", "providers.py", "workflow.py", "sampling.py")
    return fingerprint({"version": PROTOCOL_VERSION,
                        "sources": {n: (here / n).read_text(encoding="utf-8") for n in names}})


def call_request(config: dict, system: str, prompt: str, schema: dict, sample_id: str = "") -> dict:
    return {"provider": config, "system": system, "prompt": prompt, "schema": schema,
            "sample_id": sample_id}


def cached_call(root: Path, provider, system: str, prompt: str, schema: dict,
                *, sample_id: str = "", validate_response: Callable | None = None) -> tuple[dict, str]:
    request = call_request(provider.config, system, prompt, schema, sample_id)
    key = fingerprint(request)
    path = root / "calls" / f"{key}.json"
    if path.exists():
        record = load_json(path)
        if fingerprint(record["request"]) != key or fingerprint(record["response"]) != record["response_sha256"]:
            raise StudyError("An archived model call has changed")
        schemas.validate(record["response"], schema)
        if validate_response:
            validate_response(record["response"])
        return record["response"], key
    response, receipt = provider.complete(system, prompt, schema)
    schemas.validate(response, schema)
    if validate_response:
        validate_response(response)
    write_json(path, {"request": request, "response": response,
                      "response_sha256": fingerprint(response), "receipt": receipt,
                      "completed_at": utc_now()})
    return response, key


def propose(construct: str, context: str, provider, cache_dir: Path) -> dict:
    response, call = cached_call(cache_dir, provider, prompts.PROPOSER_SYSTEM,
                                 prompts.proposal_prompt(construct, context), schemas.PROPOSAL)
    names = [c["name"].casefold().strip() for c in response["candidates"]]
    if len(names) != len(set(names)):
        raise StudyError("The model proposed duplicate candidate constructs; request a fresh proposal")
    return {"schema_version": "1.0", "construct": construct, "context": context,
            "proposal": response, "call_id": call, "created_at": utc_now(),
            "notice": "Model suggestions, not theoretical classifications or validated measures."}


def normalize_judge(response: dict, mapping: dict[str, str], study: dict, cells: list[dict]) -> dict:
    schemas.validate(response, schemas.judge_schema(study, len(cells)))
    ids = [r["id"] for r in response["messages"]]
    if len(ids) != len(set(ids)) or set(ids) != set(mapping):
        raise StudyError("The judge returned duplicate, missing, or unknown blinded message IDs")
    result = copy.deepcopy(response)
    for row in result["messages"]:
        row["id"] = mapping[row["id"]]
        source = next(c["text"] for c in cells if c["id"] == row["id"])
        for issue in row["issues"]:
            if issue["quote"] not in source:
                raise StudyError("Judge evidence must be quoted exactly from the corresponding message")
    return result


def _manifest(study: dict) -> dict:
    families = [sample_family(bp, study['seed'], rep)
                for bp in study["blueprints"] for rep in range(study["families_per_context"])]
    return {"schema_version": "1.0", "protocol": PROTOCOL_VERSION,
            "protocol_sha256": protocol_fingerprint(), "study": study,
            "study_sha256": fingerprint(study), "families": families,
            "created_at": utc_now(), "screening_notice": "Model screening is not human construct validation."}


def check_manifest(manifest: dict, study: dict | None = None) -> None:
    validate_study(manifest["study"])
    if fingerprint(manifest["study"]) != manifest["study_sha256"]:
        raise StudyError("Frozen study settings have changed")
    if study is not None and fingerprint(study) != manifest["study_sha256"]:
        raise StudyError("Study differs from this run; use a new run directory")
    if manifest["protocol_sha256"] != protocol_fingerprint():
        raise StudyError("Generation or validation code changed; use the matching release or start a new run")
    expected = _manifest(manifest["study"])["families"]
    if manifest["families"] != expected:
        raise StudyError("Frozen family plan differs from the study")


def _attempt_paths(root: Path, family_id: str) -> list[Path]:
    return sorted((root / "families" / family_id).glob("attempt_*.json"))


def run(study: dict, root: Path, *, provider_factory: Callable = ModelProvider,
        progress: Callable[[str], None] = print) -> dict:
    validate_study(study)
    root = Path(root)
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        check_manifest(manifest, study)
        validate_run(root)
    else:
        if root.exists() and any(root.iterdir()):
            raise StudyError("A new run directory must be empty")
        manifest = _manifest(copy.deepcopy(study))
        write_json(manifest_path, manifest)
    writer = provider_factory(study["generation"]["writer"])
    judges = {j["name"]: provider_factory(j) for j in study["generation"]["judges"]}
    for family in manifest["families"]:
        family_id, blueprint = family["id"], family["blueprint"]
        paths = _attempt_paths(root, family_id)
        previous = load_json(paths[-1]) if paths else None
        if previous and previous["decision"]["accepted"]:
            progress(f"{family_id}: already screened; using saved results")
            continue
        first_attempt = (previous["attempt"] + 1) if previous else 1
        for number in range(first_attempt, study["generation"]["max_attempts"] + 1):
            progress(f"{family_id}: attempt {number}")
            cells = []
            revise = set(previous["decision"]["revise_cells"]) if previous else set()
            for template in cells_for(study):
                prior = next((c for c in previous["cells"] if c["id"] == template["id"]), None) if previous else None
                if prior and template["id"] not in revise:
                    cells.append(copy.deepcopy(prior))
                    continue
                feedback = [f["message"] for f in previous["decision"]["failures"]
                            if template["id"] in f["cells"]] if previous else []
                request = prompts.writer_prompt(study, blueprint, template,
                                                family_id=family_id, prior=prior["text"] if prior else "", feedback=feedback)
                response, call_id = cached_call(root, writer, prompts.WRITER_SYSTEM, request, schemas.MESSAGE,
                                                sample_id=f"writer:{family_id}:{template['id']}:{number}")
                cells.append({**template, "text": response["text"],
                              "text_sha256": fingerprint(response["text"]), "writer_call": call_id})
            assessments, judge_calls = {}, {}
            for name, judge in judges.items():
                shuffled = list(cells)
                random.Random(f"{study['seed']}:{family_id}:{number}:{name}").shuffle(shuffled)
                mapping = {f"message_{i + 1}": cell["id"] for i, cell in enumerate(shuffled)}
                blinded = [{"id": alias, "text": next(c["text"] for c in cells if c["id"] == cell_id)}
                           for alias, cell_id in mapping.items()]
                request = prompts.judge_prompt(study, blueprint, blinded)
                response, call_id = cached_call(root, judge, prompts.JUDGE_SYSTEM, request,
                                                schemas.judge_schema(study, len(cells)),
                                                sample_id=f"judge:{family_id}:{number}:{name}",
                                                validate_response=lambda response: normalize_judge(response, mapping, study, cells))
                assessments[name] = normalize_judge(response, mapping, study, cells)
                judge_calls[name] = {"call_id": call_id, "blind_mapping": mapping}
            decision = gate.evaluate(study, cells, assessments)
            record = {"family_id": family_id, "attempt": number, "cells": cells,
                      "judges": assessments, "judge_calls": judge_calls,
                      "decision": decision, "completed_at": utc_now()}
            record["record_sha256"] = fingerprint(record)
            write_json(root / "families" / family_id / f"attempt_{number:03d}.json", record)
            previous = record
            if decision["accepted"]:
                progress(f"{family_id}: model-screened" + ("; human review flagged" if decision["review_flags"] else ""))
                break
            progress(f"{family_id}: {len(decision['failures'])} issues; revising {len(decision['revise_cells'])} cells")
    return summarize(root)


def summarize(root: Path) -> dict:
    manifest = load_json(root / "manifest.json")
    study = manifest["study"]
    records, missing = [], []
    for family in manifest["families"]:
        paths = _attempt_paths(root, family["id"])
        if paths:
            records.append(load_json(paths[-1]))
        else:
            missing.append(family["id"])
    accepted = [r for r in records if r["decision"]["accepted"]]
    report = {"planned_families": len(manifest["families"]), "screened_families": len(accepted),
              "missing_families": missing, "rejected_families": [r["family_id"] for r in records if not r["decision"]["accepted"]],
              "screened_messages": sum(len(r["cells"]) for r in accepted),
              "total_attempts": sum(len(_attempt_paths(root, f["id"])) for f in manifest["families"]),
              "review_flags": sum(len(r["decision"]["review_flags"]) for r in accepted),
              "complete": len(accepted) == len(manifest["families"]),
              "study_sha256": manifest["study_sha256"], "human_validated": False}
    write_json(root / "summary.json", report)
    return report


def validate_run(root: Path) -> dict:
    manifest = load_json(root / "manifest.json")
    check_manifest(manifest)
    calls = {}
    for path in (root / "calls").glob("*.json"):
        record = load_json(path)
        if fingerprint(record["request"]) != path.stem or fingerprint(record["response"]) != record["response_sha256"]:
            raise StudyError(f"Changed model-call record: {path.name}")
        schemas.validate(record["response"], record["request"]["schema"])
        calls[path.stem] = record
    checked = 0
    study = manifest["study"]
    for family in manifest["families"]:
        paths = _attempt_paths(root, family["id"])
        previous = None
        for number, path in enumerate(paths, 1):
            record = load_json(path)
            stored_hash = record.pop("record_sha256")
            if (fingerprint(record) != stored_hash or record["attempt"] != number
                    or path.name != f"attempt_{number:03d}.json" or record["family_id"] != family["id"]):
                raise StudyError(f"Changed family record: {family['id']}")
            if number > study["generation"]["max_attempts"] or (previous and previous["decision"]["accepted"]):
                raise StudyError("Unexpected attempt after screening or after the attempt limit")
            for cell in record["cells"]:
                call = calls.get(cell["writer_call"])
                if not call or call["response"].get("text") != cell["text"] or fingerprint(cell["text"]) != cell["text_sha256"]:
                    raise StudyError("Message text differs from its source writer response")
                prior = next((c for c in previous["cells"] if c["id"] == cell["id"]), None) if previous else None
                if prior and cell["id"] not in previous["decision"]["revise_cells"]:
                    if cell != prior:
                        raise StudyError("An unaffected cell changed during targeted revision")
                    continue
                feedback = [f["message"] for f in previous["decision"]["failures"] if cell["id"] in f["cells"]] if previous else []
                prompt = prompts.writer_prompt(study, family["blueprint"], cell, family_id=family["id"],
                                               prior=prior["text"] if prior else "", feedback=feedback)
                expected = call_request(study["generation"]["writer"], prompts.WRITER_SYSTEM, prompt,
                                        schemas.MESSAGE, f"writer:{family['id']}:{cell['id']}:{number}")
                if call["request"] != expected:
                    raise StudyError("Writer request differs from its frozen study and revision history")
            reconstructed = {}
            for name, reference in record["judge_calls"].items():
                call = calls.get(reference["call_id"])
                if not call:
                    raise StudyError("Missing judge-call record")
                config = next((j for j in study["generation"]["judges"] if j["name"] == name), None)
                if config is None:
                    raise StudyError("Unknown judge in the run record")
                shuffled = list(record["cells"])
                random.Random(f"{study['seed']}:{family['id']}:{number}:{name}").shuffle(shuffled)
                mapping = {f"message_{i + 1}": cell["id"] for i, cell in enumerate(shuffled)}
                if reference["blind_mapping"] != mapping:
                    raise StudyError("Judge blinding differs from the frozen shuffle")
                blinded = [{"id": alias, "text": next(c["text"] for c in record["cells"] if c["id"] == cell_id)}
                           for alias, cell_id in mapping.items()]
                expected = call_request(config, prompts.JUDGE_SYSTEM,
                                        prompts.judge_prompt(study, family["blueprint"], blinded),
                                        schemas.judge_schema(study, len(record["cells"])),
                                        f"judge:{family['id']}:{number}:{name}")
                if call["request"] != expected:
                    raise StudyError("Judge request differs from the blinded message set")
                reconstructed[name] = normalize_judge(call["response"], reference["blind_mapping"], manifest["study"], record["cells"])
            if reconstructed != record["judges"]:
                raise StudyError("Judge ratings differ from their saved responses")
            if gate.evaluate(manifest["study"], record["cells"], reconstructed) != record["decision"]:
                raise StudyError("An acceptance decision differs from the saved evidence")
            checked += 1
            previous = record
    return {"valid": True, "checked_attempts": checked, "checked_calls": len(calls), **summarize(root)}


def export_messages(root: Path, output: Path, *, allow_partial: bool = False) -> list[dict]:
    summary = validate_run(root)
    if not summary["complete"] and not allow_partial:
        raise StudyError("The corpus is incomplete; inspect the report or explicitly use --allow-partial")
    manifest = load_json(root / "manifest.json")
    rows = []
    for family in manifest["families"]:
        paths = _attempt_paths(root, family["id"])
        if not paths:
            continue
        record = load_json(paths[-1])
        if not record["decision"]["accepted"]:
            continue
        for cell in record["cells"]:
            rows.append({"id": f"{family['id']}__{cell['id']}", "family_id": family["id"],
                         "levels": cell["levels"], "text": cell["text"], "text_sha256": cell["text_sha256"],
                         "screening_status": "model_screened", "human_validated": False,
                         "review_flags": record["decision"]["review_flags"]})
    write_json(output, rows)
    return rows
