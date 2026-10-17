"""The temporary OAuth probe must clean up even when telemetry or restoration fails."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('telemetry_probe', Path(__file__).parents[1] / 'telemetry_smoke.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Response(io.BytesIO):
    status = 200
    headers = {}


class TelemetryProbeCleanup(unittest.TestCase):
    def exercise(self, fail_restore):
        operations = []

        def cli(command, **kwargs):
            service, action = command[1:3]
            operations.append(action)
            if action == 'get-caller-identity':
                return b'{"Account":"026249143093"}'
            if action == 'get-authorizers':
                return json.dumps({'Items': [{'Name': 'organization-jwt', 'AuthorizerId': 'test',
                    'JwtConfiguration': {'Audience': ['human-client'], 'Issuer': 'https://issuer'}}]}).encode()
            if action == 'create-user-pool-client':
                config = json.loads(command[command.index('--cli-input-json') + 1])
                self.assertEqual(config['AllowedOAuthFlows'], ['client_credentials'])
                return b'{"UserPoolClient":{"ClientId":"temporary","ClientSecret":"fake-test-secret"}}'
            if action == 'update-authorizer':
                config = json.loads(command[command.index('--jwt-configuration') + 1])
                if fail_restore and config['Audience'] == ['human-client']:
                    raise subprocess.CalledProcessError(1, ['aws', 'update-authorizer'])
            return b'{}'

        def http(request, **kwargs):
            if request.full_url.endswith('/oauth2/token'):
                return Response(b'{"access_token":"fake-test-token"}')
            return Response(b'{"source":"invalid"}')

        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'report.json'
            with patch.dict(os.environ, {'RUNNER_TEMP': folder}), patch('sys.argv', ['probe', '--report', str(report)]), patch.object(probe.subprocess, 'check_output', side_effect=cli), patch.object(probe.urllib.request, 'urlopen', side_effect=http), patch.object(probe.time, 'sleep'), redirect_stdout(io.StringIO()):
                with self.assertRaises(subprocess.CalledProcessError if fail_restore else AssertionError):
                    probe.main()
            self.assertIn('delete-user-pool-client', operations)
            text = report.read_text()
            self.assertNotIn('fake-test-token', text)
            self.assertNotIn('fake-test-secret', text)
            result = json.loads(text)
            self.assertTrue(result['cleanup']['temporary_client_deleted'])
            self.assertEqual(result['cleanup'].get('original_audience_restored', False), not fail_restore)

    def test_invalid_snapshot_cleans_up(self):
        self.exercise(False)

    def test_restore_failure_still_deletes_client(self):
        self.exercise(True)


class FreshMetricReadiness(unittest.TestCase):
    def test_waits_for_real_cpu_and_memory_points(self):
        snapshot = {'source': 'aws-cloudwatch-ecs', 'service': {'id': 'infra-signal-lab'},
                    'metrics': [{'id': 'cpu', 'points': []}, {'id': 'memory', 'points': [1]}]}
        self.assertFalse(probe.metrics_ready(snapshot, 'infra-signal-lab'))
        snapshot['metrics'][0]['points'] = [1]
        self.assertTrue(probe.metrics_ready(snapshot, 'infra-signal-lab'))

    def test_fixture_source_is_rejected_instead_of_retried(self):
        with self.assertRaises(AssertionError):
            probe.metrics_ready({'source': 'fixtures'}, 'infra-signal-lab')
