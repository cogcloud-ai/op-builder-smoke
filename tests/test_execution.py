"""Model-free integration checks against the installed merge candidate.

Only the resume test injects a transport failure; successful calls use the real
declared Cog task. Tests require Pixi and the sibling candidate checkout.
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
        values = output['outputs']
        self.assertEqual(values['original_merge']['findings'], values['handoff_merge']['findings'])
        self.assertEqual(values['original_merge']['provenance'][0]['of'], 2)
        self.assertEqual(values['handoff_merge']['provenance'][0]['of'], 1)
        track = json.loads(Path(output['track']).read_text())
        self.assertEqual([s['status'] for s in track['steps']], ['passed', 'passed'])
        for step in track['steps']:
            self.assertEqual(len(step['cog_sha256']), 64)
            self.assertTrue(Path(step['request']).is_file())
            env = json.loads(Path(step['envelope']).read_text())
            self.assertEqual(env['cog']['id'], 'openteams/cog-merge-findings-candidate')
            self.assertEqual(step['gate']['status'], 'pass')

    def test_real_contract_problem_stops_downstream(self):
        request = json.loads(self.request.read_text())
        request['bundle']['results'] = [[{}]]
        path = Path(self.temp.name) / 'bad.json'
        path.write_text(json.dumps(request))
        code, output = self.run_op(path)
        self.assertEqual(code, 1, output)
        track = json.loads(Path(output['track']).read_text())
        self.assertEqual(track['failed_step'], 'merge')
        self.assertEqual([s['status'] for s in track['steps']], ['failed', 'not-reached'])
        self.assertTrue(track['steps'][0]['problems'])

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
