"""Pool review, yoked sampling, and replay tests using synthetic fixtures."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from beyond_stimulus_sampling.sampling import plan, sample_family
from beyond_stimulus_sampling.specification import StudyError, load_json, validate_study, write_json
from beyond_stimulus_sampling.workflow import run, validate_run
from support import FixtureProvider, study


class PoolProvider:
    def __init__(self):
        self.config = {'kind': 'command', 'model': 'synthetic-pool-fixture', 'command': ['fixture']}
        self.requests = []
        self.duplicate = False

    def complete(self, system, prompt, schema):
        request = json.loads(prompt)
        self.requests.append(request)
        return {'content_pool': [f'Alternative reasoning {0 if self.duplicate else i}'
                                 for i in range(request['requested_content_points'])],
                'style_pool': [f'Organization {i}' for i in range(request['requested_organizational_styles'])]}, {'synthetic': True}


class SamplingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.study = study()
        FixtureProvider.calls = []
        FixtureProvider.interrupt_after = None
        FixtureProvider.fail_initial_fluency = False

    def add_pool(self):
        self.study['blueprints'][0]['sampling'] = {
            'content_pool': [f'Point {i}' for i in range(6)],
            'content_per_family': 2,
            'style_pool': ['Example first', 'Question first', 'Comparison first']}

    def test_planner_caches_suggestions_and_requires_fresh_review(self):
        provider = PoolProvider()
        original = copy.deepcopy(self.study)
        result = plan(self.study, provider, self.root, content_count=6,
                      content_per_family=2, style_count=3)
        self.assertEqual(self.study, original)
        self.assertFalse(result['researcher_review']['completed'])
        with self.assertRaises(StudyError):
            validate_study(result)
        again = plan(self.study, provider, self.root, content_count=6,
                     content_per_family=2, style_count=3)
        self.assertEqual(result['blueprints'], again['blueprints'])
        self.assertEqual(len(provider.requests), 1)
        self.assertNotIn('trust', json.dumps(provider.requests))

    def test_invalid_pool_suggestions_are_not_cached(self):
        provider = PoolProvider()
        provider.duplicate = True
        with self.assertRaises(StudyError):
            plan(self.study, provider, self.root, content_count=3, content_per_family=2)
        self.assertFalse(list((self.root / 'calls').glob('*.json')))

    def test_samples_are_yoked_within_family_and_vary_between_families(self):
        self.add_pool()
        self.study['families_per_context'] = 4
        output = self.root / 'run'
        run(self.study, output, provider_factory=FixtureProvider, progress=lambda _: None)
        manifest = load_json(output / 'manifest.json')
        by_id = {f['id']: f for f in manifest['families']}
        self.assertGreater(len({tuple(f['sampling']['content_indices']) for f in by_id.values()}), 1)
        self.assertGreater(len({f['sampling']['style_index'] for f in by_id.values()}), 1)
        for _, request in FixtureProvider.calls:
            if 'assigned_perspectives' not in request:
                continue
            shared = by_id[request['independent_sample_id']]['blueprint']
            self.assertEqual(request['required_content'], shared['required_content'])
            self.assertEqual(request['shared_argumentation_style'], shared['argumentation_style'])
        self.assertEqual(validate_run(output)['checked_attempts'], 4)
        for i, family in enumerate(manifest['families']):
            self.assertEqual(family, sample_family(self.study['blueprints'][0], self.study['seed'], i))

    def test_revisions_use_the_same_sample_and_tampering_fails(self):
        self.add_pool()
        FixtureProvider.fail_initial_fluency = True
        output = self.root / 'run'
        run(self.study, output, provider_factory=FixtureProvider, progress=lambda _: None)
        writer_requests = [r for _, r in FixtureProvider.calls if 'assigned_perspectives' in r]
        self.assertTrue(any('previous_draft' in r for r in writer_requests))
        self.assertEqual(len({tuple(r['required_content']) for r in writer_requests}), 1)
        self.assertEqual(len({r['shared_argumentation_style'] for r in writer_requests}), 1)
        manifest = load_json(output / 'manifest.json')
        manifest['families'][0]['blueprint']['argumentation_style'] = 'Changed style'
        write_json(output / 'manifest.json', manifest)
        with self.assertRaises(StudyError):
            validate_run(output)

    def test_invalid_study_pools_fail_before_generation(self):
        self.add_pool()
        for key, value in [('content_per_family', 7), ('style_pool', []),
                           ('content_pool', ['Repeated', ' repeated '])]:
            with self.subTest(field=key):
                modified = copy.deepcopy(self.study)
                modified['blueprints'][0]['sampling'][key] = value
                with self.assertRaises(StudyError):
                    validate_study(modified)


if __name__ == '__main__':
    unittest.main()
