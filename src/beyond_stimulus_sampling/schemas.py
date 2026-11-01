"""Small strict JSON schemas shared by providers and offline validation."""

from __future__ import annotations

import math
from typing import Any

from .specification import StudyError


def obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1}
CONSTRUCT = obj({"name": TEXT, "definition": TEXT, "low_anchor": TEXT, "high_anchor": TEXT})
PROPOSAL = obj({
    "target": CONSTRUCT,
    "candidates": {"type": "array", "minItems": 3, "maxItems": 8,
                   "items": obj({**CONSTRUCT["properties"], "why_related": TEXT,
                                 "example_change": TEXT})},
})
MESSAGE = obj({"text": TEXT})
ISSUE_KINDS = ["content_changed", "required_content_missing", "instruction_leakage",
               "incoherent", "organization_changed", "unnatural", "unexpected_construct"]


def pool_schema(content_count: int, style_count: int) -> dict:
    return obj({'content_pool': {'type': 'array', 'minItems': content_count,
                                'maxItems': content_count, 'items': TEXT},
                'style_pool': {'type': 'array', 'minItems': style_count,
                              'maxItems': style_count, 'items': TEXT}})


def judge_schema(study: dict, count: int) -> dict:
    scale = {"type": "number", "minimum": study["assessment"]["scale_min"],
             "maximum": study["assessment"]["scale_max"]}
    message = obj({
        "id": TEXT,
        "ratings": obj({d["id"]: scale for d in study["dimensions"]}),
        "content_fidelity": scale, "fluency": scale, "naturalness": scale,
        "naturalness_comment": TEXT,
        "issues": {"type": "array", "maxItems": 12, "items": obj({
            "kind": {"type": "string", "enum": ISSUE_KINDS},
            "quote": TEXT, "explanation": TEXT,
        })},
    })
    return obj({"messages": {"type": "array", "minItems": count, "maxItems": count,
                              "items": message},
                "content_equivalence": scale, "equivalence_explanation": TEXT})


def validate(value: Any, schema: dict, path: str = "response") -> None:
    """Validate the subset of JSON Schema emitted by this package."""
    kind = schema.get("type")
    valid = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool)
                  and math.isfinite(value),
    }.get(kind, True)
    if not valid:
        raise StudyError(f"{path} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise StudyError(f"{path} is outside its permitted values")
    if kind == "object":
        required = set(schema.get("required", []))
        properties = schema.get("properties", {})
        if not required <= set(value):
            raise StudyError(f"{path} is missing fields: {sorted(required - set(value))}")
        if schema.get("additionalProperties") is False and not set(value) <= set(properties):
            raise StudyError(f"{path} has unexpected fields: {sorted(set(value) - set(properties))}")
        for key, child in value.items():
            if key in properties:
                validate(child, properties[key], f"{path}.{key}")
    if kind == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", math.inf):
            raise StudyError(f"{path} has an invalid number of items")
        for i, child in enumerate(value):
            validate(child, schema["items"], f"{path}[{i}]")
    if kind == "string" and len(value.strip()) < schema.get("minLength", 0):
        raise StudyError(f"{path} must contain text")
    if kind in {"number", "integer"}:
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise StudyError(f"{path} is outside the rating scale")
