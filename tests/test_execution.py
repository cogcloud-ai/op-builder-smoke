"""Model-free integration checks against the installed cog-word-tally package.

Only the resume test injects a transport failure; successful calls use the real
declared Cog task. Tests require Pixi and the sibling cog-word-tally checkout.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import op_runner
import op_spec


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runs = Path(self.temp.name) / 'runs'
        self.request = ROOT / 'examples/request.json'

    def run_op(self, request=None):
        return op_runner.run(ROOT, request or self.request, runs_dir=self.runs)

    def test_real_handoff_and_durable_evidence(self):
        code, output = self.run_op()
        self.assertEqual(code, 0, output)
        self.assertEqual(output['status'], 'completed')
        first = output['outputs']['first_tally']
        accumulated = output['outputs']['accumulated_tally']
        # the first tally is what the example texts contain
        self.assertEqual(first['counts']['the'], 3)
        self.assertEqual(first['counts']["don't"], 1)
        self.assertEqual(first['total_words'], sum(first['counts'].values()))
        # the handoff was a real data dependency: every first count is
        # preserved, the second texts are added on top, and the total is the sum
        for word, count in first['counts'].items():
            self.assertGreaterEqual(accumulated['counts'][word], count)
        self.assertEqual(accumulated['counts']['the'], 5)
        self.assertEqual(accumulated['counts']['42'], 1)
        self.assertEqual(accumulated['total_words'],
                         first['total_words'] + 10)
        self.assertEqual(accumulated['authority_use'], [])
        track = json.loads(Path(output['track']).read_text())
        self.assertEqual([s['status'] for s in track['steps']], ['passed', 'passed'])
        for step in track['steps']:
            self.assertEqual(len(step['cog_sha256']), 64)
            self.assertTrue(Path(step['request']).is_file())
            env = json.loads(Path(step['envelope']).read_text())
            self.assertEqual(env['cog']['id'], 'openteams/cog-word-tally')
            self.assertEqual(step['gate']['status'], 'pass')
        handoff = json.loads(Path(track['steps'][1]['request']).read_text())
        self.assertEqual(handoff['prior_counts'], first['counts'])

    def test_real_contract_problem_stops_downstream(self):
        # The Op's own input schema refuses an empty texts list before any
        # Cog runs; the Cog's CONTRACT is exercised by handing the second
        # step a prior count it must refuse (negative), which no Op-level
        # schema sees because prior_counts is mapped from the first result.
        request = json.loads(self.request.read_text())
        request['first_texts'] = []
        path = Path(self.temp.name) / 'bad.json'
        path.write_text(json.dumps(request))
        with self.assertRaises(op_spec.OpSpecError):
            self.run_op(path)
        original = op_runner.invoke_cog
        def bad_prior(cog_dir, task, request_path, *args, **kwargs):
            doc = json.loads(Path(request_path).read_text())
            if 'prior_counts' in doc:
                doc['prior_counts'] = {'x': -1}
                Path(request_path).write_text(json.dumps(doc))
            return original(cog_dir, task, request_path, *args, **kwargs)
        with patch.object(op_runner, 'invoke_cog', side_effect=bad_prior):
            code, output = self.run_op()
        self.assertEqual(code, 1, output)
        track = json.loads(Path(output['track']).read_text())
        self.assertEqual(track['failed_step'], 'handoff')
        self.assertEqual([s['status'] for s in track['steps']], ['passed', 'failed'])
        self.assertTrue(track['steps'][1]['problems'])

    def test_resume_keeps_passed_work(self):
        original = op_runner.invoke_cog
        def fail_second(cog_dir, task, request_path, *args, **kwargs):
            if Path(request_path).stem == 'handoff':
                return op_runner.failed_envelope(cog_dir, task, 'Injected transport failure for resume test')
            return original(cog_dir, task, request_path, *args, **kwargs)
        with patch.object(op_runner, 'invoke_cog', side_effect=fail_second):
            code, output = self.run_op()
        self.assertEqual(code, 1, output)
        before = json.loads(Path(output['track']).read_text())
        first_envelope = Path(before['steps'][0]['envelope']).read_bytes()
        with patch.object(op_runner, 'invoke_cog', wraps=original) as invoked:
            code, resumed = op_runner.resume(ROOT, output['run_dir'])
        self.assertEqual(code, 0, resumed)
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(Path(invoked.call_args.args[2]).stem, 'handoff')
        after = json.loads(Path(output['track']).read_text())
        self.assertEqual(first_envelope, Path(after['steps'][0]['envelope']).read_bytes())
        self.assertEqual(len(after['resumes']), 1)
        self.assertEqual(after['status'], 'completed')

    def test_changed_spec_refuses_resume(self):
        code, output = self.run_op()
        self.assertEqual(code, 0)
        track_path = Path(output['track'])
        track = json.loads(track_path.read_text())
        track['spec_sha256'] = '0' * 64
        track_path.write_text(json.dumps(track))
        with self.assertRaisesRegex(op_spec.OpSpecError, 'changed'):
            op_runner.resume(ROOT, output['run_dir'])
