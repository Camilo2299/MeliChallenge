#!/usr/bin/env python3
"""Run separately approved capacity stages, stopping at the first failed gate."""
import json
import os
import resource
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

RATES = (100, 500, 1000, 2500, 5000, 10000)
ROOT = Path(__file__).resolve().parents[1]
DEST = Path(os.environ.get('MELI_CAPACITY_REPORT_DIR', '/tmp/meli-capacity'))


def main():
    if os.environ.get('MELI_CAPACITY_APPROVED') != 'true':
        raise SystemExit('The separately reviewed capacity plan must be approved before execution.')
    if not os.environ.get('ACCESS_TOKEN'):
        raise SystemExit('Use the Cognito helper; no token will be written to disk.')
    DEST.mkdir(mode=0o700, exist_ok=True)
    report = {'started_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Authenticated GET /v1/services fixtures; 10-second warmup plus 60-second plateau per stage', 'stages': []}
    try:
        for rate in RATES:
            env = os.environ.copy()
            env.update(RATE=str(rate), K6_NO_USAGE_REPORT='true')
            summary = DEST / f'{rate}.json'
            print(f'Starting capacity stage: {rate} requests/s; 10-second warmup plus 60-second plateau', flush=True)
            usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
            started = time.monotonic()
            completed = subprocess.run(['k6', 'run', '--summary-export', str(summary),
                                        str(ROOT / 'performance/capacity.js')], env=env)
            stage = {'target_rps': rate, 'elapsed_seconds': round(time.monotonic()-started, 3),
                     'exit_code': completed.returncode, 'summary': summary.name}
            if summary.exists():
                metrics = json.loads(summary.read_text())['metrics']
                stage.update(requests=metrics['http_reqs']['count'], observed_rps=metrics['http_reqs']['rate'],
                             p95_ms=metrics['http_req_duration']['p(95)'],
                             p99_ms=metrics['http_req_duration']['p(99)'],
                             error_rate=metrics['http_req_failed']['value'],
                             successful=metrics.get('successful_requests', {}).get('count', 0),
                             responses_429=metrics.get('responses_429', {}).get('count', 0),
                             responses_5xx=metrics.get('responses_5xx', {}).get('count', 0),
                             dropped_iterations=metrics.get('dropped_iterations', {}).get('count', 0))
            if summary.exists():
                steady_count = metrics.get('steady_requests', {}).get('count')
                steady_success = metrics.get('steady_successful_requests', {}).get('count')
                stage.update(steady_requests=steady_count, steady_successful=steady_success,
                             steady_observed_rps=steady_count/60 if steady_count is not None and completed.returncode == 0 else None,
                             steady_successful_rps=steady_success/60 if steady_success is not None and completed.returncode == 0 else None,
                             steady_p95_ms=metrics.get('steady_duration', {}).get('p(95)'),
                             steady_p99_ms=metrics.get('steady_duration', {}).get('p(99)'))
            report['stages'].append(stage)
            # macOS ru_maxrss is bytes; retains the maximum across finished child processes.
            usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
            report['generator_max_rss_bytes_macos'] = usage_after.ru_maxrss
            stage['generator_cpu_core_equivalents'] = round(((usage_after.ru_utime + usage_after.ru_stime) -
                (usage_before.ru_utime + usage_before.ru_stime)) / max(stage['elapsed_seconds'], .001), 3)
            if usage_after.ru_maxrss > 2 * 1024**3 or stage['generator_cpu_core_equivalents'] > 6:
                report['result'] = 'stopped_at_generator_resource_limit'
                raise SystemExit('Generator resource limit reached; higher stages need a separate load generator.')
            if completed.returncode:
                report['result'] = 'stopped_at_failed_stage'
                raise SystemExit(f'Stage {rate} failed a gate; higher stages were not executed.')
        report['result'] = 'all_stages_passed'
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (DEST / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print('Sanitized capacity report:', DEST / 'report.json', flush=True)


if __name__ == '__main__':
    main()
