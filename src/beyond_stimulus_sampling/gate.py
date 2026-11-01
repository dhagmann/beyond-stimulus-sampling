"""Family-level target and spillover contrasts for arbitrary ordered factors."""

from __future__ import annotations

import itertools
import re
from statistics import mean

from .schemas import judge_schema, validate
from .specification import StudyError, cells_for


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w]+(?:[’'-][\w]+)*\b", text))


def evaluate(study: dict, cells: list[dict], judges: dict[str, dict]) -> dict:
    """No behavioral outcomes enter this decision; consequence ratings are diagnostic."""
    expected = {c["id"] for c in cells_for(study)}
    if len(cells) != len(expected) or {c["id"] for c in cells} != expected:
        raise StudyError("A family must contain every experimental cell exactly once")
    by_id = {c["id"]: c for c in cells}
    for c in cells:
        template = next(x for x in cells_for(study) if x["id"] == c["id"])
        if c["levels"] != template["levels"] or not isinstance(c.get("text"), str) or not c["text"].strip():
            raise StudyError("A message has invalid treatment assignments or missing text")
    expected_judges = {j["name"] for j in study["generation"]["judges"]}
    if set(judges) != expected_judges:
        raise StudyError("All configured judges must assess the complete family")
    ratings = {}
    for name, payload in judges.items():
        validate(payload, judge_schema(study, len(cells)))
        rows = payload["messages"]
        if {row["id"] for row in rows} != expected or len(rows) != len(expected):
            raise StudyError(f"{name} returned duplicate, missing, or unknown message IDs")
        ratings[name] = {r["id"]: r for r in rows}
        for row in rows:
            for issue in row["issues"]:
                if issue["quote"] not in by_id[row["id"]]["text"]:
                    raise StudyError(f"{name}'s evidence is not an exact quotation from its message")
    criteria, settings = study["assessment"], study["generation"]
    failures: list[dict] = []
    review: list[dict] = []
    counts = {c["id"]: word_count(c["text"]) for c in cells}

    def fail(kind: str, message: str, affected: list[str]) -> None:
        failures.append({"kind": kind, "message": message, "cells": sorted(affected)})

    for cell_id, n in counts.items():
        if not settings["min_words"] <= n <= settings["max_words"]:
            fail("length", f"{cell_id}: {n} words is outside {settings['min_words']}–{settings['max_words']}", [cell_id])
        for field, limit in (("content_fidelity", criteria["min_content_fidelity"]),
                             ("fluency", criteria["min_fluency"])):
            value = mean(r[cell_id][field] for r in ratings.values())
            if value < limit:
                fail(field, f"{cell_id}: mean {field} {value:.2f} is below {limit}", [cell_id])
        naturalness = mean(r[cell_id]["naturalness"] for r in ratings.values())
        if naturalness < criteria["naturalness_review_below"]:
            review.append({"kind": "naturalness", "cells": [cell_id], "mean": naturalness,
                           "comments": {j: r[cell_id]["naturalness_comment"] for j, r in ratings.items()}})
        issue_judges: dict[str, list[str]] = {}
        for judge, rows in ratings.items():
            for issue in rows[cell_id]["issues"]:
                if issue["kind"] == "unnatural":
                    review.append({"kind": "naturalness_evidence", "cells": [cell_id],
                                   "judge": judge, **issue})
                else:
                    issue_judges.setdefault(issue["kind"], [])
                    if judge not in issue_judges[issue["kind"]]:
                        issue_judges[issue["kind"]].append(judge)
        for kind, names in issue_judges.items():
            if len(names) >= criteria.get("critical_issue_consensus", 1):
                fail(kind, f"{cell_id}: {kind} flagged by {', '.join(names)}", [cell_id])
    if max(counts.values()) - min(counts.values()) > settings["max_word_range"]:
        fail("length_equivalence", "Within-family word-count spread is too large", list(expected))
    if mean(j["content_equivalence"] for j in judges.values()) < criteria["min_content_fidelity"]:
        fail("content_equivalence", "Shared substantive content differs across the family", list(expected))

    contrasts = []
    factors = [d for d in study["dimensions"] if d["role"] == "factor"]
    for factor in factors:
        order = {level["id"]: i for i, level in enumerate(factor["levels"])}
        for first, second in itertools.combinations(cells, 2):
            changed = [key for key in first["levels"] if first["levels"][key] != second["levels"][key]]
            if changed != [factor["id"]]:
                continue
            low, high = sorted((first, second), key=lambda c: order[c["levels"][factor["id"]]])
            distance = order[high["levels"][factor["id"]]] - order[low["levels"][factor["id"]]]
            for dimension in study["dimensions"]:
                deltas = {name: rows[high["id"]]["ratings"][dimension["id"]]
                                - rows[low["id"]]["ratings"][dimension["id"]]
                          for name, rows in ratings.items()}
                target = dimension["id"] == factor["id"]
                diagnostic = dimension["role"] == "consequence"
                signed = mean(deltas.values())
                absolute = mean(abs(x) for x in deltas.values())
                threshold = (criteria["min_target_difference"] * distance if target
                             else criteria["max_spillover"])
                passed = True if diagnostic else (
                    signed >= threshold and min(deltas.values()) >= 0 if target else absolute <= threshold
                )
                contrast = {"manipulated": factor["id"], "measured": dimension["id"],
                            "low_cell": low["id"], "high_cell": high["id"],
                            "role": "target" if target else ("consequence" if diagnostic else "spillover"),
                            "by_judge": deltas, "mean_signed": signed,
                            "mean_absolute": absolute, "threshold": None if diagnostic else threshold,
                            "passed": passed}
                contrasts.append(contrast)
                if not passed:
                    value = signed if target else absolute
                    fail("target" if target else "spillover",
                         f"Changing {factor['name']} changes {dimension['name']} by {value:.2f}; "
                         + (f"at least {threshold:.2f} with no judge inversion required" if target
                            else f"at most {threshold:.2f} allowed"), [low["id"], high["id"]])
    revise = sorted({c for failure in failures for c in failure["cells"]})
    return {"accepted": not failures, "status": "model_screened" if not failures else "rejected",
            "failures": failures, "review_flags": review, "revise_cells": revise,
            "word_counts": counts, "contrasts": contrasts}
