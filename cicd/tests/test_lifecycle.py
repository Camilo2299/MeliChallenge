import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('lifecycle', Path(__file__).parents[1] / 'lifecycle.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LifecycleSafety(unittest.TestCase):
    def test_valid_manifest_preserves_interrupted_destruction(self):
        value = {'status': 'destroying', 'generation': 'r12345', 'image': 'a' * 40}
        self.assertEqual(module.validate_manifest(value), value)

    def test_rejects_unversioned_images_and_generation_injection(self):
        for field, invalid in [('image', 'latest'), ('image', '../other'), ('generation', 'r1 -destroy'), ('status', 'ready')]:
            value = {'status': 'present', 'generation': '', 'image': 'a' * 40}
            value[field] = invalid
            with self.assertRaises(ValueError):
                module.validate_manifest(value)

class ControllerSequence(unittest.TestCase):
    def test_destroy_requires_confirmation_before_any_aws_call(self):
        from unittest.mock import patch
        with patch('sys.argv', ['lifecycle', 'destroy']), patch.object(module, 'aws') as aws:
            with self.assertRaises(ValueError):
                module.main()
            aws.assert_not_called()

    def test_destroy_unprotects_only_existing_protected_resources(self):
        from unittest.mock import patch
        import json
        import os
        import tempfile
        calls = []
        manifest = {'status': 'present', 'generation': '', 'image': 'a' * 40}
        state_lists = iter(['aws_dynamodb_table.telemetry\naws_ecs_service.app', ''])

        def tf(*args, **kwargs):
            calls.append(('tf', args))
            if args[:2] == ('state', 'list'):
                return next(state_lists)
            return ''

        def aws(*args):
            if args[:2] == ('sts', 'get-caller-identity'):
                return {'Account': '026249143093'}
            if args[:2] == ('s3api', 'list-objects-v2'):
                return {'Contents': [{'Key': module.MANIFEST}]}
            if args[:2] == ('s3api', 'get-object'):
                module.Path(args[-1]).write_text(json.dumps(manifest))
            if args[:2] == ('s3api', 'put-object'):
                calls.append(('save', json.loads(module.Path(args[args.index('--body') + 1]).read_text())['status']))
            return {}

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'RUNNER_TEMP': directory, 'TF_STATE_BUCKET': 'infra-signal-lab-tfstate-026249143093-us-east-1', 'AWS_REGION': 'us-east-1'}), patch('sys.argv', ['lifecycle', 'destroy', '--confirmation', 'DESTROY infra-signal-lab DATA']), patch.object(module, 'aws', side_effect=aws), patch.object(module, 'tf', side_effect=tf):
            module.main()
        plans = [args for kind, args in calls if kind == 'tf' and args[0] == 'plan']
        self.assertIn('-target=aws_dynamodb_table.telemetry', plans[0])
        self.assertNotIn('-target=aws_lb.internal', plans[0])
        self.assertIn('-destroy', plans[1])
        mutation = next(i for i, (kind, args) in enumerate(calls) if kind == 'tf' and args[0] == 'apply')
        self.assertLess(calls.index(('save', 'destroying')), mutation)
        self.assertEqual(calls[-1], ('save', 'absent'))
