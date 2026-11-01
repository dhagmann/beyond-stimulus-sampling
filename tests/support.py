"""Deterministic software fixtures, not linguistic or empirical validation."""

import copy
import json


def study():
    provider = {"kind": "command", "model": "test-only", "command": ["test-fixture"]}
    def dimension(identifier, role):
        value = {"id": identifier, "name": identifier, "definition": f"Definition of {identifier}",
                 "low_anchor": f"Low {identifier}", "high_anchor": f"High {identifier}", "role": role}
        if role == "factor":
            value["levels"] = [{"id": "low", "instruction": "low"}, {"id": "high", "instruction": "high"}]
        return value
    return {"schema_version": "1.0", "title": "Software fixture", "context": "Test scenario",
            "focal_construct": "clarity", "dimensions": [dimension("clarity", "factor"),
                dimension("warmth", "protected"), dimension("trust", "consequence")],
            "blueprints": [{"id": "scenario", "context": "Test scenario", "required_content": ["Keep shared fact"]}],
            "candidate_review": [], "families_per_context": 1, "seed": 2026,
            "generation": {"min_words": 1, "max_words": 500, "max_word_range": 50, "max_attempts": 3,
                           "writer": provider, "judges": [{"name": name, **provider} for name in ("one", "two")]},
            "assessment": {"scale_min": 1, "scale_max": 7, "min_target_difference": 1.5,
                "max_spillover": 0.75, "min_content_fidelity": 5, "min_fluency": 5, "naturalness_review_below": 4},
            "researcher_review": {"completed": True, "reviewer": "Software test fixture"}}


class FixtureProvider:
    calls = []
    interrupt_after = None
    fail_initial_fluency = False

    def __init__(self, config):
        self.config = config

    def complete(self, system, prompt, schema):
        cls = type(self)
        if cls.interrupt_after is not None and len(cls.calls) == cls.interrupt_after:
            raise RuntimeError("Simulated interruption")
        request = json.loads(prompt)
        cls.calls.append((copy.deepcopy(self.config), request))
        if "assigned_perspectives" in request:
            pairs = [(d["construct"], d["perspective"]) for d in request["assigned_perspectives"]]
            text = json.dumps({"assignments": pairs, "sample": request["independent_sample_id"],
                               "revised": "previous_draft" in request})
            return {"text": text}, {"synthetic": True}
        rows = []
        for message in request["messages"]:
            payload = json.loads(message["text"])
            values = dict(payload["assignments"])
            scores = {d["id"]: (2 if values[d["name"]] == "low" else 6) if d["name"] in values else 4
                      for d in request["dimensions"]}
            bad = cls.fail_initial_fluency and values.get("clarity") == "low" and not payload["revised"]
            rows.append({"id": message["id"], "ratings": scores, "content_fidelity": 6,
                         "fluency": 1 if bad else 6, "naturalness": 6,
                         "naturalness_comment": "Software fixture", "issues": []})
        return {"messages": rows, "content_equivalence": 6, "equivalence_explanation": "Software fixture"}, {"synthetic": True}


def ratings(spec, cells):
    result = {}
    for judge in spec["generation"]["judges"]:
        rows = []
        for cell in cells:
            scores = {}
            for dim in spec["dimensions"]:
                if dim["role"] == "factor":
                    index = [x["id"] for x in dim["levels"]].index(cell["levels"][dim["id"]])
                    scores[dim["id"]] = 1 + index * 3
                else:
                    scores[dim["id"]] = 4
            rows.append({"id": cell["id"], "ratings": scores, "content_fidelity": 6,
                         "fluency": 6, "naturalness": 6, "naturalness_comment": "Fixture", "issues": []})
        result[judge["name"]] = {"messages": rows, "content_equivalence": 6, "equivalence_explanation": "Fixture"}
    return result
