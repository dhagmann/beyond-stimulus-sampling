"""A deliberately synthetic walkthrough; never evidence about real stimuli."""

from __future__ import annotations

import copy
import json
from importlib.resources import files
from pathlib import Path

from .report import render
from .workflow import export_messages, run


class SyntheticProvider:
    def __init__(self, config, fixture):
        self.config, self.fixture = config, fixture

    def complete(self, system, prompt, schema):
        request = json.loads(prompt)
        if "assigned_perspectives" in request:
            instruction = request["assigned_perspectives"][0]["perspective"]
            key = "high" if instruction == self.fixture["study"]["dimensions"][0]["levels"][1]["instruction"] else "low"
            if key == "high" and "previous_draft" not in request:
                key = "high_spillover"
            response = {"text": self.fixture["texts"][key]}
        else:
            rows = []
            for message in request["messages"]:
                key = next(k for k, text in self.fixture["texts"].items() if text == message["text"])
                rows.append({"id": message["id"], "ratings": self.fixture["ratings"][key],
                             "content_fidelity": 6, "fluency": 6, "naturalness": 6,
                             "naturalness_comment": "Synthetic demonstration rating, not a model judgment.", "issues": []})
            response = {"messages": rows, "content_equivalence": 6,
                        "equivalence_explanation": "Fixed synthetic demonstration ratings."}
        return response, {"provider": self.config, "execution": {"synthetic": True, "tools_used": False}}


def demonstrate(root: Path):
    fixture = json.loads(files("beyond_stimulus_sampling").joinpath("data/demo.json").read_text(encoding="utf-8"))
    print("SYNTHETIC DEMO: fixed example messages and invented ratings; no model calls or empirical evidence.")
    summary = run(copy.deepcopy(fixture["study"]), root,
                  provider_factory=lambda config: SyntheticProvider(config, fixture))
    render(root)
    export_messages(root, root / "messages.json")
    print(json.dumps(summary, indent=2))
    print(f"Open {root / 'report.html'} to inspect the initial spillover and revised family.")
