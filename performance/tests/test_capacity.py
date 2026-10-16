"""Verify failed capacity stages cannot advance to a higher request rate."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('capacity', Path(__file__).parents[1] / 'capacity.py')
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


class CapacityTest(unittest.TestCase):
    def test_missing_approval_stops_before_any_load(self):
        with patch.dict(capacity.os.environ, {}, clear=True), patch.object(capacity.subprocess, 'run') as run:
            with self.assertRaises(SystemExit):
                capacity.main()
            run.assert_not_called()

    def test_failed_stage_preserves_report_and_does_not_advance(self):
        rates = []

        def fake_run(command, env):
            rate = int(env['RATE']); rates.append(rate)
            metrics = {'http_reqs': {'count': rate*60, 'rate': rate},
                       'http_req_duration': {'p(95)': 100, 'p(99)': 150},
                       'http_req_failed': {'value': 0},
                       'dropped_iterations': {'count': 0},
                       'steady_requests': {'count': rate*60},
                       'steady_successful_requests': {'count': rate*60}}
            Path(command[command.index('--summary-export')+1]).write_text(json.dumps({'metrics': metrics}))
            return SimpleNamespace(returncode=99 if rate == 500 else 0)

        usage = SimpleNamespace(ru_utime=0, ru_stime=0, ru_maxrss=0)
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(capacity, 'DEST', Path(directory)), \
             patch.dict(capacity.os.environ, {'ACCESS_TOKEN': 'test-placeholder', 'MELI_CAPACITY_APPROVED': 'true'}), \
             patch.object(capacity.subprocess, 'run', side_effect=fake_run), \
             patch.object(capacity.resource, 'getrusage', return_value=usage), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, '500 failed'):
                capacity.main()
            report = json.loads((Path(directory)/'report.json').read_text())
            self.assertEqual(report['result'], 'stopped_at_failed_stage')
            self.assertEqual(rates, [100, 500])
            self.assertEqual(report['stages'][0]['steady_observed_rps'], 100)
            self.assertIsNone(report['stages'][1]['steady_observed_rps'])
            self.assertNotIn('test-placeholder', json.dumps(report))


if __name__ == '__main__':
    unittest.main()
