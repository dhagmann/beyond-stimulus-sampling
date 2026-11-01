import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from beyond_stimulus_sampling import gate, prompts, schemas
from beyond_stimulus_sampling.onboarding import Questions, build_study, initialize
from beyond_stimulus_sampling.providers import ModelProvider, ProviderError
from beyond_stimulus_sampling.report import render
from beyond_stimulus_sampling.specification import StudyError, cells_for, fingerprint, load_json, validate_study, write_json
from beyond_stimulus_sampling.workflow import cached_call, export_messages, normalize_judge, run, validate_run
from support import FixtureProvider, ratings, study


class GateTests(unittest.TestCase):
    def setUp(self):
        self.study = study()
        self.cells = [{**c, "text": "Shared fixture text with an exact quotation."} for c in cells_for(self.study)]
        self.ratings = ratings(self.study, self.cells)

    def test_arbitrary_three_level_factor_and_second_factor(self):
        self.study["dimensions"][0]["levels"].insert(1, {"id": "medium", "instruction": "medium"})
        factor = copy.deepcopy(self.study["dimensions"][0])
        factor.update(id="autonomy", name="autonomy")
        factor["levels"].pop(1)
        self.study["dimensions"].append(factor)
        validate_study(self.study)
        cells = [{**c, "text": "Fixture text"} for c in cells_for(self.study)]
        decision = gate.evaluate(self.study, cells, ratings(self.study, cells))
        self.assertEqual(len(cells), 6)
        self.assertTrue(decision["accepted"])
        self.assertTrue(any(c["threshold"] == 3 for c in decision["contrasts"]))

    def test_judge_disagreement_cannot_cancel_spillover(self):
        for name, delta in (("one", 2), ("two", -2)):
            self.ratings[name]["messages"][1]["ratings"]["warmth"] += delta
        decision = gate.evaluate(self.study, self.cells, self.ratings)
        contrast = next(c for c in decision["contrasts"] if c["measured"] == "warmth")
        self.assertEqual(contrast["mean_signed"], 0)
        self.assertEqual(contrast["mean_absolute"], 2)
        self.assertFalse(decision["accepted"])

    def test_consequences_are_diagnostic_and_absent_from_writer(self):
        for payload in self.ratings.values():
            payload["messages"][0]["ratings"]["trust"] = 1
            payload["messages"][1]["ratings"]["trust"] = 7
        self.assertTrue(gate.evaluate(self.study, self.cells, self.ratings)["accepted"])
        prompt = json.loads(prompts.writer_prompt(self.study, self.study["blueprints"][0], self.cells[0]))
        self.assertNotIn("trust", json.dumps(prompt))
        judge = json.loads(prompts.judge_prompt(self.study, self.study["blueprints"][0], []))
        self.assertTrue(any(d["id"] == "trust" for d in judge["dimensions"]))
        self.assertTrue(all("role" not in d for d in judge["dimensions"]))

    def test_naturalness_flags_do_not_reject(self):
        for payload in self.ratings.values():
            payload["messages"][0]["naturalness"] = 1
        result = gate.evaluate(self.study, self.cells, self.ratings)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["review_flags"])

    def test_one_judge_inversion_cannot_be_hidden_by_average_target_effect(self):
        self.ratings["one"]["messages"][0]["ratings"]["clarity"] = 4
        self.ratings["one"]["messages"][1]["ratings"]["clarity"] = 3
        self.ratings["two"]["messages"][0]["ratings"]["clarity"] = 1
        self.ratings["two"]["messages"][1]["ratings"]["clarity"] = 7
        decision = gate.evaluate(self.study, self.cells, self.ratings)
        target = next(c for c in decision["contrasts"] if c["role"] == "target")
        self.assertGreater(target["mean_signed"], 1.5)
        self.assertFalse(decision["accepted"])

    def test_strict_evidence_and_full_rating_set(self):
        for change in ("missing", "duplicate", "quote", "nan"):
            with self.subTest(change=change):
                payload = copy.deepcopy(self.ratings)
                if change == "missing":
                    del payload["one"]["messages"][0]["ratings"]["warmth"]
                elif change == "duplicate":
                    payload["one"]["messages"][1]["id"] = payload["one"]["messages"][0]["id"]
                elif change == "quote":
                    payload["one"]["messages"][0]["issues"] = [{"kind": "incoherent", "quote": "Invented quote", "explanation": "Test"}]
                else:
                    payload["one"]["messages"][0]["fluency"] = float("nan")
                with self.assertRaises(StudyError):
                    gate.evaluate(self.study, self.cells, payload)

    def test_issue_quotation_must_match_assigned_blind_message(self):
        payload = self.ratings["one"]
        payload["messages"][0]["id"], payload["messages"][1]["id"] = "a", "b"
        payload["messages"][0]["issues"] = [{"kind": "incoherent", "quote": "Wrong", "explanation": "Test"}]
        with self.assertRaises(StudyError):
            normalize_judge(payload, {"a": self.cells[0]["id"], "b": self.cells[1]["id"]}, self.study, self.cells)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "run"
        FixtureProvider.calls = []
        FixtureProvider.interrupt_after = None
        FixtureProvider.fail_initial_fluency = False
        self.study = study()

    def run_study(self):
        return run(self.study, self.root, provider_factory=FixtureProvider, progress=lambda x: None)

    def test_repair_only_failed_cells_but_rejudge_whole_family(self):
        FixtureProvider.fail_initial_fluency = True
        result = self.run_study()
        self.assertTrue(result["complete"])
        writer_calls = [r for _, r in FixtureProvider.calls if "assigned_perspectives" in r]
        self.assertEqual(len(writer_calls), 3)
        self.assertEqual(sum("previous_draft" in r for r in writer_calls), 1)
        self.assertEqual(len([r for _, r in FixtureProvider.calls if "messages" in r]), 4)
        self.assertEqual(validate_run(self.root)["checked_attempts"], 2)

    def test_resume_uses_completed_calls_and_separate_replicates_and_judges(self):
        self.study["families_per_context"] = 2
        FixtureProvider.interrupt_after = 1
        with self.assertRaises(RuntimeError):
            self.run_study()
        FixtureProvider.interrupt_after = None
        self.assertTrue(self.run_study()["complete"])
        self.assertEqual(len(FixtureProvider.calls), 8)
        count = len(FixtureProvider.calls)
        self.run_study()
        self.assertEqual(len(FixtureProvider.calls), count)
        self.assertEqual(validate_run(self.root)["checked_calls"], 8)

    def test_frozen_study_and_message_tampering_fail(self):
        self.run_study()
        modified = copy.deepcopy(self.study)
        modified["assessment"]["max_spillover"] = 2
        with self.assertRaises(StudyError):
            run(modified, self.root, provider_factory=FixtureProvider, progress=lambda x: None)
        path = next((self.root / "families").glob("*/attempt_001.json"))
        record = load_json(path)
        record["cells"][0]["text"] += " tampered"
        write_json(path, record)
        with self.assertRaises(StudyError):
            self.run_study()

    def test_rehashed_blind_mapping_tampering_still_fails(self):
        self.run_study()
        path = next((self.root / "families").glob("*/attempt_001.json"))
        record = load_json(path)
        mapping = record["judge_calls"]["one"]["blind_mapping"]
        mapping["message_1"], mapping["message_2"] = mapping["message_2"], mapping["message_1"]
        record.pop("record_sha256")
        record["record_sha256"] = fingerprint(record)
        write_json(path, record)
        with self.assertRaises(StudyError):
            validate_run(self.root)

    def test_partial_export_requires_explicit_choice(self):
        FixtureProvider.fail_initial_fluency = True
        self.study["generation"]["max_attempts"] = 1
        self.run_study()
        output = Path(self.temp.name) / "export.json"
        with self.assertRaises(StudyError):
            export_messages(self.root, output)
        self.assertEqual(export_messages(self.root, output, allow_partial=True), [])

    def test_html_escapes_researcher_and_model_content(self):
        self.study["title"] = '<script>alert("title")</script>'
        self.run_study()
        html = render(self.root).read_text()
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)
        rows = export_messages(self.root, Path(self.temp.name) / "export.json")
        self.assertTrue(all(r["human_validated"] is False for r in rows))


class OnboardingTests(unittest.TestCase):
    def test_complete_wizard_from_saved_proposal_requires_no_model_call(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            construct = {"name": "Clarity", "definition": "How clear the message is", "low_anchor": "Unclear", "high_anchor": "Clear"}
            proposal = {"construct": "Clarity", "context": "A workplace announcement", "proposal": {"target": construct,
                "candidates": [{**construct, "name": name, "why_related": "Could covary", "example_change": "Example"}
                               for name in ("Explicitness", "Warmth", "Trust")]}}
            path = folder / "proposal.json"
            write_json(path, proposal)
            responses = iter(["no", "2", "", "", "", "", "no", "1", "Explicitness is a facet in this question",
                              "no", "2", "Warmth should be separate", "", "no", "4", "Trust may be a consequence", "no",
                              "", "Preserve the decision | Preserve the stated timing", "no", "1", "10", "50", "none",
                              "no", "no", "no", "", "yes", "Test researcher"])
            def no_model(config):
                raise AssertionError("Saved proposal should avoid model calls")
            output = folder / "study.json"
            result = initialize(output, provider_config=study()["generation"]["writer"], proposal_path=path,
                                input_fn=lambda prompt: next(responses), output_fn=lambda x: None, provider_factory=no_model)
            validate_study(result)
            self.assertTrue(output.exists())
            self.assertEqual([d["role"] for d in result["dimensions"]], ["factor", "protected", "consequence"])
            self.assertEqual(result["researcher_review"]["reviewer"], "Test researcher")

    def test_each_classification_has_the_correct_operational_role(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = {"name": "focal", "definition": "Target definition", "low_anchor": "low", "high_anchor": "high"}
            classifications = ["same_construct", "spillover", "factor", "consequence", "ignore"]
            candidates = [{**fixture, "name": f"candidate_{i}", "why_related": "Related", "example_change": "Example"}
                          for i in range(5)]
            proposal = {"context": "A manager's message", "proposal": {"target": fixture, "candidates": candidates}}
            q = Questions(Path(temp) / "setup.json", input_fn=lambda prompt: "", output_fn=lambda text: None)
            answers = {"target_edit": "no", "target_levels_count": "2", "target_levels_0_id": "low",
                       "target_levels_1_id": "high", "target_levels_0_instruction": "low", "target_levels_1_instruction": "high",
                       "add_candidate_5": "no", "context_0": "Workplace message", "content_0": "Keep facts | State decision",
                       "more_context_0": "no", "families": "3", "min_words": "100", "max_words": "200",
                       "requirements": "none", "judge_1_custom": "no", "judge_2_custom": "no",
                       "custom_settings": "no", "title": "Study", "complete": "yes", "reviewer": "Researcher"}
            for i, choice in enumerate(classifications):
                answers.update({f"candidate_{i}_edit": "no", f"candidate_{i}_classification": choice,
                                f"candidate_{i}_rationale": "Theory-based researcher judgment"})
            answers.update({"candidate_2_levels_count": "2", "candidate_2_levels_0_id": "low", "candidate_2_levels_1_id": "high",
                            "candidate_2_levels_0_instruction": "low", "candidate_2_levels_1_instruction": "high",
                            "candidate_1_hold": "Hold comparable"})
            q.state["answers"] = answers
            spec = build_study(q, proposal, study()["generation"]["writer"])
            validate_study(spec)
            self.assertEqual([d["role"] for d in spec["dimensions"]], ["factor", "protected", "factor", "consequence"])
            self.assertEqual(spec["dimensions"][0]["facets"][0]["name"], "candidate_0")
            self.assertEqual(len(cells_for(spec)), 4)
            self.assertEqual(len(spec["candidate_review"]), 5)
            self.assertNotIn("candidate_3", prompts.writer_prompt(spec, spec["blueprints"][0], cells_for(spec)[0]))

    def test_interrupted_init_preserves_answers(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "study.json"
            responses = iter(["Target construct"])
            def answer(prompt):
                try:
                    return next(responses)
                except StopIteration:
                    raise EOFError
            with self.assertRaisesRegex(StudyError, "Resume"):
                initialize(output, provider_config=study()["generation"]["writer"], input_fn=answer, output_fn=lambda x: None)
            saved = load_json(output.with_suffix(".setup.json"))
            self.assertEqual(saved["answers"]["construct"], "Target construct")
            self.assertFalse(output.exists())


class TransportTests(unittest.TestCase):
    def test_semantically_invalid_responses_do_not_poison_resume_cache(self):
        class InvalidEvidence:
            config = {"kind": "command", "model": "fixture", "command": ["fixture"]}
            def complete(self, *args):
                return {"text": "A structurally valid but unacceptable answer"}, {"synthetic": True}
        def reject(response):
            raise StudyError("Invalid evidence")
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(StudyError):
                cached_call(Path(temp), InvalidEvidence(), "System", "Prompt", schemas.MESSAGE, validate_response=reject)
            self.assertFalse(list(Path(temp).rglob("*.json")))

    def test_provider_reports_usage_limit_without_recording_account_details(self):
        provider = ModelProvider({"kind": "claude", "model": "fixture"})
        provider._help = "--safe-mode"
        result = subprocess.CompletedProcess([], 1, stdout=json.dumps({"api_error": "usage_limit_reached"}), stderr="private account details")
        with mock.patch("shutil.which", return_value="/fixture/claude"), mock.patch("subprocess.run", return_value=result):
            with self.assertRaisesRegex(ProviderError, "usage limit"):
                provider.complete("System", "Prompt", schemas.MESSAGE)

    def test_cli_preserves_subscription_auth_and_removes_api_routes(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "fixture-subscription-token",
                                         "ANTHROPIC_API_KEY": "fixture-api-key", "CLAUDE_CODE_USE_BEDROCK": "1"}):
            provider = ModelProvider({"kind": "claude", "model": "fixture"})
            env = provider._environment()
            self.assertEqual(env["CLAUDE_CODE_OAUTH_TOKEN"], "fixture-subscription-token")
            self.assertNotIn("ANTHROPIC_API_KEY", env)
            self.assertNotIn("CLAUDE_CODE_USE_BEDROCK", env)

    def test_external_command_receives_structured_input_and_has_no_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / "adapter.py"
            script.write_text('import sys,json\nr=json.load(sys.stdin)\nassert r["allow_tools"] is False\nprint(json.dumps({"text":r["prompt"]}))\n')
            provider = ModelProvider({"kind": "command", "model": "local-fixture", "command": [sys.executable, str(script)]})
            text = "literal $(touch sentinel) ; `echo secret`"
            response, receipt = provider.complete("System", text, schemas.MESSAGE)
            self.assertEqual(response["text"], text)
            self.assertEqual(receipt["execution"]["tools_used"], "adapter responsibility")

    def test_bad_external_response_is_rejected(self):
        provider = ModelProvider({"kind": "command", "model": "fixture", "command": [sys.executable, "-c", "print('{}')"]})
        with self.assertRaises(ProviderError):
            provider.complete("System", "Prompt", schemas.MESSAGE)


if __name__ == "__main__":
    unittest.main()
