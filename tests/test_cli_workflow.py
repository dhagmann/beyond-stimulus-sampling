"""Exercise the public CLI through stateless command adapters, without models."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CLIWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.env = os.environ.copy()
        self.env['PYTHONPATH'] = str(ROOT / 'src')
        config = {'kind': 'command', 'model': 'synthetic-cli',
                  'command': [sys.executable, str(ROOT / 'tests/fixtures/command_adapter.py')]}
        self.config = self.folder / 'provider.json'
        self.config.write_text(json.dumps(config))

    def cli(self, *args, stdin='', code=0):
        result = subprocess.run([sys.executable, '-m', 'beyond_stimulus_sampling', *map(str, args)],
                                input=stdin, capture_output=True, text=True, env=self.env,
                                cwd=self.folder, timeout=30)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def prepare(self):
        proposal = self.folder / 'proposal.json'
        study = self.folder / 'study.json'
        planned = self.folder / 'planned.json'
        self.cli('propose', '--construct', 'Clarity', '--context', 'A hypothetical workplace message.',
                 '--provider-config', self.config, '--output', proposal)
        answers = ['no', '2', '', '', '', '', 'no', '1', 'Explicitness is a facet.',
                   'no', '2', 'Warmth should be separate.', '', 'no', '4', 'Trust may change.', 'no',
                   '', 'Preserve the decision | Preserve the stated timing', 'no', '2', '10', '200', 'none',
                   'no', 'no', 'no', 'no', 'Synthetic CLI study', 'yes', 'Synthetic researcher']
        self.cli('init', '--output', study, '--proposal', proposal, '--provider-config', self.config,
                 stdin='\n'.join(answers) + '\n')
        self.cli('plan', study, '--output', planned, '--content-pool-size', '6',
                 '--content-per-family', '2', '--style-pool-size', '3')
        return planned

    def test_complete_guided_workflow_repair_export_and_cached_replay(self):
        planned = self.prepare()
        run = self.folder / 'run'
        self.cli('run', planned, '--output', run, code=2)
        self.assertFalse(run.exists(), 'Unreviewed pools must not start generation')
        review = self.cli('review', planned, '--complete', stdin='yes\nSynthetic researcher\n')
        self.assertIn('How clear the explanation is.', review.stdout)
        self.cli('run', planned, '--output', run)
        summary = json.loads((run / 'summary.json').read_text())
        self.assertTrue(summary['complete'])
        self.assertEqual(summary['screened_messages'], 4)
        self.assertEqual(summary['total_attempts'], 4)
        self.assertTrue((run / 'report.html').exists())
        family = json.loads((run / 'manifest.json').read_text())['families'][0]['id']
        self.cli('audit', run, '--family', family)
        self.assertTrue((run / f'audit_{family}.html').exists())
        self.cli('report', run)
        self.cli('export', run, '--output', run / 'messages.json')
        exported = json.loads((run / 'messages.json').read_text())
        self.assertEqual(len(exported), 4)
        self.assertTrue(all(r['screening_status'] == 'model_screened' and not r['human_validated'] for r in exported))
        calls = {p.name: p.read_bytes() for p in (run / 'calls').glob('*.json')}
        self.cli('validate', run)
        self.cli('run', planned, '--output', run)
        self.assertEqual(calls, {p.name: p.read_bytes() for p in (run / 'calls').glob('*.json')})

    def test_exhausted_families_require_explicit_partial_export(self):
        planned = self.prepare()
        specification = json.loads(planned.read_text())
        specification['generation']['writer']['model'] = 'synthetic-always-fail'
        specification['families_per_context'] = 1
        planned.write_text(json.dumps(specification))
        self.cli('review', planned, '--complete', stdin='yes\nSynthetic researcher\n')
        run = self.folder / 'incomplete'
        self.cli('run', planned, '--output', run)
        summary = json.loads((run / 'summary.json').read_text())
        self.assertFalse(summary['complete'])
        self.assertEqual(summary['total_attempts'], 3)
        self.cli('export', run, '--output', run / 'messages.json', code=2)
        self.assertFalse((run / 'messages.json').exists())
        self.cli('export', run, '--output', run / 'messages.json', '--allow-partial')
        self.assertEqual(json.loads((run / 'messages.json').read_text()), [])


if __name__ == '__main__':
    unittest.main()
