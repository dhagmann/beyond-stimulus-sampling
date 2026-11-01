"""Regressions for behaviors described in the paper. All ratings are synthetic."""

import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from beyond_stimulus_sampling import cli, gate, report
from beyond_stimulus_sampling.onboarding import Questions, build_study
from beyond_stimulus_sampling.specification import StudyError, cells_for, load_json, write_json
from beyond_stimulus_sampling.workflow import export_messages, propose, run, validate_run
from support import FixtureProvider, ratings, study


class ConcernProvider(FixtureProvider):
    unexpected = False

    def complete(self, system, prompt, schema):
        response, receipt = super().complete(system, prompt, schema)
        request = json.loads(prompt)
        if 'messages' in request:
            for message, row in zip(request['messages'], response['messages']):
                payload = json.loads(message['text'])
                if dict(payload['assignments']).get('clarity') == 'low' and not payload['revised']:
                    row['issues'] = [{
                        'kind': 'unexpected_construct' if self.unexpected else 'content_changed',
                        'quote': '"revised": false',
                        'explanation': ('Possible unmeasured dominance. Ask the researcher to classify it.'
                                        if self.unexpected else 'Restore the agreed decision without changing the assigned clarity.')
                    }]
        return response, receipt


class PaperContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.study = study()
        for provider in (FixtureProvider, ConcernProvider):
            provider.calls = []
            provider.interrupt_after = None
            provider.fail_initial_fluency = False
        ConcernProvider.unexpected = False

    def test_revision_receives_the_judges_own_message_evidence(self):
        root = self.folder / 'run'
        run(self.study, root, provider_factory=ConcernProvider, progress=lambda _: None)
        revisions = [request for _, request in ConcernProvider.calls if 'previous_draft' in request]
        self.assertEqual(len(revisions), 1)
        feedback = '\n'.join(revisions[0]['revision_feedback'])
        self.assertIn('Restore the agreed decision', feedback)
        self.assertIn('"revised": false', feedback)
        self.assertTrue(validate_run(root)['complete'])

    def test_unanticipated_construct_is_reported_for_researcher_judgment(self):
        ConcernProvider.unexpected = True
        progress = []
        root = self.folder / 'run'
        summary = run(self.study, root, provider_factory=ConcernProvider, progress=progress.append)
        self.assertTrue(summary['complete'])
        self.assertEqual(summary['total_attempts'], 1)
        self.assertGreater(summary['review_flags'], 0)
        self.assertIn('researcher', ' '.join(progress).lower())
        self.assertIn('dominance', ' '.join(progress).lower())
        self.assertTrue((root / 'report.html').exists())
        self.assertIn('unexpected_construct', (root / 'report.html').read_text())

    def test_multiple_writers_vary_across_families_but_not_within_them(self):
        self.study['families_per_context'] = 4
        self.study['generation']['writers'] = [
            {'name': name, **self.study['generation']['writer'], 'model': name}
            for name in ('writer_a', 'writer_b')]
        FixtureProvider.fail_initial_fluency = True
        root = self.folder / 'run'
        run(self.study, root, provider_factory=FixtureProvider, progress=lambda _: None)
        assignments = {}
        for config, request in FixtureProvider.calls:
            if 'assigned_perspectives' in request:
                assignments.setdefault(request['independent_sample_id'], set()).add(config['model'])
        self.assertTrue(all(len(models) == 1 for models in assignments.values()))
        self.assertEqual(set.union(*assignments.values()), {'writer_a', 'writer_b'})
        self.assertTrue(validate_run(root)['complete'])

    def test_researcher_review_shows_the_actual_definitions_and_inputs(self):
        path = self.folder / 'study.json'
        write_json(path, self.study)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(cli.main(['review', str(path)]), 0)
        for text in ['Definition of clarity', 'Low clarity', 'High clarity',
                     'Keep shared fact', 'test-only']:
            self.assertIn(text, output.getvalue())

    def test_duplicate_construct_suggestions_do_not_poison_the_cache(self):
        class Proposer:
            config = {'kind': 'command', 'model': 'synthetic', 'command': ['fixture']}

            def complete(self, *args):
                construct = {'name': 'Clarity', 'definition': 'Clear language',
                             'low_anchor': 'Unclear', 'high_anchor': 'Clear'}
                return {'target': construct, 'candidates': [
                    {**construct, 'name': name, 'why_related': 'Test', 'example_change': 'Test'}
                    for name in ('Warmth', ' warmth ', 'Trust')]}, {'synthetic': True}

        with self.assertRaises(StudyError):
            propose('Clarity', 'A workplace message', Proposer(), self.folder)
        self.assertFalse(list((self.folder / 'calls').glob('*.json')))

    def test_onboarding_handles_a_second_slug_collision(self):
        construct = {'name': 'clarity', 'definition': 'Definition', 'low_anchor': 'Low', 'high_anchor': 'High'}
        proposal = {'context': 'Workplace', 'proposal': {'target': construct, 'candidates': [
            {**construct, 'name': name, 'why_related': 'Test', 'example_change': 'Test'}
            for name in ('clarity_2', 'clarity', 'ignored')]}}
        q = Questions(self.folder / 'setup.json', input_fn=lambda _: '', output_fn=lambda _: None)
        answers = {'target_edit': 'no', 'target_levels_count': '2', 'target_levels_0_id': 'low',
                   'target_levels_1_id': 'high', 'target_levels_0_instruction': 'low',
                   'target_levels_1_instruction': 'high', 'add_candidate_3': 'no',
                   'context_0': 'Workplace', 'content_0': 'Keep the decision', 'more_context_0': 'no',
                   'families': '1', 'min_words': '10', 'max_words': '200', 'requirements': 'none',
                   'judge_1_custom': 'no', 'judge_2_custom': 'no', 'custom_settings': 'no',
                   'title': 'Study', 'complete': 'yes', 'reviewer': 'Test researcher'}
        for i in range(3):
            answers.update({f'candidate_{i}_edit': 'no', f'candidate_{i}_classification': 'spillover' if i < 2 else 'ignore',
                            f'candidate_{i}_rationale': 'Researcher judgment', f'candidate_{i}_hold': 'Keep this attribute fixed'})
        q.state['answers'] = answers
        result = build_study(q, proposal, self.study['generation']['writer'])
        self.assertEqual(len({d['id'] for d in result['dimensions']}), 3)

    def test_execution_receipt_changes_are_detected_on_replay(self):
        root = self.folder / 'run'
        run(self.study, root, provider_factory=FixtureProvider, progress=lambda _: None)
        path = next((root / 'calls').glob('*.json'))
        call = load_json(path)
        call['receipt'] = {'provider': 'changed after generation'}
        write_json(path, call)
        with self.assertRaises(StudyError):
            validate_run(root)

    def test_compact_family_audit_keeps_ratings_roles_and_cutoffs_together(self):
        root = self.folder / 'run'
        run(self.study, root, provider_factory=FixtureProvider, progress=lambda _: None)
        output = report.audit(root, 'scenario__r001')
        html = output.read_text()
        for text in ['clarity', 'warmth', 'trust', 'consequence', '1.50', '0.75', 'test-only']:
            self.assertIn(text, html)
        self.assertNotIn('<script>', html)

    def test_report_and_export_cannot_overwrite_frozen_records(self):
        root = self.folder / 'run'
        run(self.study, root, provider_factory=FixtureProvider, progress=lambda _: None)
        targets = [root / 'manifest.json', root / 'summary.json',
                   next((root / 'calls').glob('*.json')),
                   next((root / 'families').glob('*/attempt_001.json'))]
        for target in targets:
            original = target.read_bytes()
            for operation in (lambda: report.render(root, target),
                              lambda: report.audit(root, 'scenario__r001', target),
                              lambda: export_messages(root, target)):
                with self.subTest(target=target.name), self.assertRaises(StudyError):
                    operation()
                self.assertEqual(target.read_bytes(), original)
        self.assertTrue(validate_run(root)['complete'])

    def test_malformed_saved_call_returns_a_research_record_error(self):
        root = self.folder / 'run'
        run(self.study, root, provider_factory=FixtureProvider, progress=lambda _: None)
        path = next((root / 'calls').glob('*.json'))
        path.write_text('[null]')
        with self.assertRaises(StudyError):
            validate_run(root)

    def test_custom_report_and_audit_links_resolve_to_the_full_report(self):
        root = self.folder / 'run'
        run(self.study, root, provider_factory=FixtureProvider, progress=lambda _: None)
        output = self.folder / 'review' / 'full report.html'
        report.render(root, output)
        compact = output.parent / 'audit_scenario__r001.html'
        self.assertIn('full%20report.html#scenario__r001', compact.read_text())
        custom_audit = report.audit(root, 'scenario__r001', output.parent / 'single.html')
        self.assertIn('../run/report.html#scenario__r001', custom_audit.read_text())
        with self.assertRaises(StudyError):
            report.render(root, compact)

    def test_saved_writer_assignment_cannot_change_after_generation(self):
        self.study['generation']['writers'] = [
            {'name': name, **self.study['generation']['writer'], 'model': name}
            for name in ('writer_a', 'writer_b')]
        root = self.folder / 'run'
        run(self.study, root, provider_factory=FixtureProvider, progress=lambda _: None)
        manifest = load_json(root / 'manifest.json')
        old = manifest['families'][0]['writer']
        manifest['families'][0]['writer'] = 'writer_a' if old == 'writer_b' else 'writer_b'
        write_json(root / 'manifest.json', manifest)
        with self.assertRaises(StudyError):
            validate_run(root)

    def test_spillovers_cannot_cancel_across_levels_of_another_factor(self):
        factor = copy.deepcopy(self.study['dimensions'][0])
        factor.update(id='autonomy', name='autonomy')
        self.study['dimensions'].append(factor)
        cells = [{**c, 'text': 'Synthetic shared text'} for c in cells_for(self.study)]
        assessments = ratings(self.study, cells)
        for assessment in assessments.values():
            for row, cell in zip(assessment['messages'], cells):
                if cell['levels']['clarity'] == 'high':
                    row['ratings']['warmth'] += 2 if cell['levels']['autonomy'] == 'low' else -2
        decision = gate.evaluate(self.study, cells, assessments)
        contrasts = [c for c in decision['contrasts']
                     if c['manipulated'] == 'clarity' and c['measured'] == 'warmth']
        self.assertEqual(sum(c['mean_signed'] for c in contrasts), 0)
        self.assertTrue(all(c['mean_absolute'] == 2 and not c['passed'] for c in contrasts))
        self.assertFalse(decision['accepted'])


if __name__ == '__main__':
    unittest.main()
