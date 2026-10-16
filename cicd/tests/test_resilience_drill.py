"""Verify rehearsal cleanup on both a healthy rollout and a failed candidate."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('drill', Path(__file__).parents[1] / 'resilience_drill.py')
drill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drill)
BASELINE = 'arn:aws:ecs:us-east-1:026249143093:task-definition/infra-signal-lab:3'
CANDIDATE = BASELINE.rsplit(':', 1)[0] + ':5'


class Response(io.BytesIO):
    status = 200


class RehearsalTest(unittest.TestCase):
    def exercise(self, fail_candidate):
        state = {'definition': BASELINE}
        operations = []

        def service():
            return {'taskDefinition': state['definition'], 'desiredCount': 2, 'runningCount': 2,
                    'pendingCount': 0, 'deployments': [{'rolloutState': 'COMPLETED'}]}

        def fake_aws(namespace, operation, **kwargs):
            operations.append((operation, kwargs))
            if operation == 'get-caller-identity':
                return {'Account': '026249143093'}
            if operation == 'list-tasks':
                return {'taskArns': ['task-a', 'task-b']}
            if operation == 'describe-task-definition':
                return {'taskDefinition': {'family': 'infra-signal-lab', 'containerDefinitions': []}}
            if operation == 'register-task-definition':
                return {'taskDefinition': {'taskDefinitionArn': CANDIDATE}}
            if operation == 'update-service':
                state['definition'] = kwargs['task_definition']
                return {}
            if operation == 'deregister-task-definition':
                self.assertEqual(state['definition'], BASELINE)
                return {}
            raise AssertionError(operation)

        def fake_wait(definition, **_):
            if definition == CANDIDATE and fail_candidate:
                raise RuntimeError('candidate failed to stabilize')
            return {'elapsed_seconds': 1, 'running': 2, 'healthy_targets': 2}

        tasks = {'tasks': [{'taskArn': 'task-' + az, 'healthStatus': 'HEALTHY', 'availabilityZone': az}
                           for az in ('a', 'b')]}
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / 'report.json'
            with patch.object(drill, 'REPORT', report_path), \
                 patch.object(drill, 'aws', side_effect=fake_aws), \
                 patch.object(drill, 'current', side_effect=service), \
                 patch.object(drill, 'wait_stable', side_effect=fake_wait), \
                 patch.object(drill.subprocess, 'check_output', return_value=json.dumps(tasks)), \
                 patch.object(drill.urllib.request, 'urlopen', side_effect=lambda *a, **k: Response(b'[1,2,3]')), \
                 patch.dict(drill.os.environ, {'BASE_URL': 'https://v1dbllhj9a.execute-api.us-east-1.amazonaws.com',
                                              'ACCESS_TOKEN': 'test-placeholder'}), \
                 patch('sys.argv', ['drill', '--execute', '--rollback-only']), redirect_stdout(io.StringIO()):
                if fail_candidate:
                    with self.assertRaisesRegex(RuntimeError, 'candidate failed'):
                        drill.main()
                else:
                    drill.main()
            report = json.loads(report_path.read_text())
            self.assertTrue(report['baseline_restored'])
            self.assertEqual(report['result'], 'failed' if fail_candidate else 'completed')
            self.assertNotIn('test-placeholder', report_path.read_text())
        self.assertEqual([p['task_definition'] for op, p in operations if op == 'update-service'],
                         [CANDIDATE, BASELINE])
        self.assertEqual(sum(op == 'deregister-task-definition' for op, _ in operations), 1)
        self.assertFalse(any(op == 'stop-task' for op, _ in operations))

    def test_success_restores_baseline_and_retires_auxiliary_revision(self):
        self.exercise(False)

    def test_failed_candidate_restores_baseline_and_preserves_failure_report(self):
        self.exercise(True)

    def test_cli_wrapper_accepts_ecs_service_flag(self):
        with patch.object(drill.subprocess, 'check_output', return_value='{}') as process:
            drill.aws('ecs', 'update-service', service='infra-signal-lab')
        args = process.call_args.args[0]
        self.assertEqual(args[args.index('--service') + 1], 'infra-signal-lab')


if __name__ == '__main__':
    unittest.main()
