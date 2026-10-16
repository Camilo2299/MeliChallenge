#!/usr/bin/env python3
"""Regional EC2 load driver. M2M secret/JWT remain in process memory only."""
import base64
import json
import os
import resource
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path('/opt/meli-capacity')
RATES = [100, 500, 1000, 2500, 5000, 10000]


def aws(*args):
    return subprocess.check_output(['aws', '--region', 'us-east-1', '--output', 'json', *args], text=True)


def machine_token(config):
    response = json.loads(aws('cognito-idp', 'describe-user-pool-client', '--user-pool-id', config['pool_id'],
                              '--client-id', config['client_id']))['UserPoolClient']
    secret = response['ClientSecret']
    credentials = base64.b64encode((config['client_id'] + ':' + secret).encode()).decode()
    request = urllib.request.Request(config['token_url'], data=urllib.parse.urlencode({
        'grant_type': 'client_credentials', 'scope': 'infra-metrics/read'}).encode(), headers={
            'Authorization': 'Basic ' + credentials, 'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(request, timeout=20) as result:
        token = json.load(result)['access_token']
    return token


def upload(config, folder):
    # Only sanitized metrics/logs from k6. config.json, role credentials and tokens are excluded.
    for path in folder.iterdir():
        if path.is_file() and path.suffix in ('.json', '.log'):
            subprocess.run(['aws', 's3', 'cp', str(path), 's3://' + config['bucket'] + '/results/' + folder.name + '/' + path.name,
                            '--region', config['region'], '--only-show-errors'], check=True)


def main():
    config = json.loads((HOME / 'config.json').read_text())
    run_name = sys.argv[1] if len(sys.argv) > 1 else 'regional-1'
    rates = [int(s) for s in sys.argv[2].split(',')] if len(sys.argv) > 2 else RATES
    if any(rate not in RATES for rate in rates) or '/' in run_name or run_name.startswith('.'):
        raise SystemExit('Invalid reviewed run parameters.')
    folder = HOME / 'results' / run_name
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'generator': 'EC2 c7g.2xlarge ARM64 Linux us-east-1a',
              'authentication': 'Temporary Cognito M2M client_credentials, infra-metrics/read scope',
              'stages': [], 'result': 'running'}
    try:
        for rate in rates:
            token = machine_token(config)
            request = urllib.request.Request(config['api_url'] + '/v1/services', headers={'Authorization': 'Bearer ' + token})
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.status == 200 and len(json.load(response)) == 3
            env = os.environ.copy()
            env.update(ACCESS_TOKEN=token, BASE_URL=config['api_url'], RATE=str(rate), K6_NO_USAGE_REPORT='true')
            summary = folder / f'{rate}.json'
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            started = time.monotonic()
            print('Starting authorized regional stage:', rate, flush=True)
            with (folder / f'{rate}.log').open('w') as log:
                code = subprocess.run(['/usr/local/bin/k6', 'run', '--summary-export', str(summary), str(HOME / 'capacity.js')],
                                      env=env, stdout=log, stderr=subprocess.STDOUT).returncode
            env.pop('ACCESS_TOKEN', None)
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            elapsed = time.monotonic()-started
            stage = {'target_rps': rate, 'exit_code': code, 'elapsed_seconds': round(elapsed,3),
                     'generator_max_rss_bytes': after.ru_maxrss*1024,
                     'generator_cpu_core_equivalents': round((after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime)/elapsed,3)}
            if summary.exists():
                metrics = json.loads(summary.read_text())['metrics']
                steady = metrics.get('steady_successful_requests',{}).get('count')
                stage.update(requests=metrics['http_reqs']['count'], successful=metrics.get('successful_requests',{}).get('count',0),
                             overall_observed_rps=metrics['http_reqs']['rate'], error_rate=metrics['http_req_failed']['value'],
                             dropped_iterations=metrics.get('dropped_iterations',{}).get('count',0),
                             responses_429=metrics.get('responses_429',{}).get('count',0),
                             responses_5xx=metrics.get('responses_5xx',{}).get('count',0),
                             steady_successful_requests=steady, steady_successful_rps=steady/60 if steady is not None and code==0 else None,
                             steady_p95_ms=metrics.get('steady_duration',{}).get('p(95)'),
                             steady_p99_ms=metrics.get('steady_duration',{}).get('p(99)'))
            report['stages'].append(stage)
            (folder / 'report.json').write_text(json.dumps(report,indent=2)+'\n')
            upload(config, folder)
            print(json.dumps(stage), flush=True)
            if code:
                report['result'] = 'stopped_at_failed_stage'
                break
        else:
            report['result'] = 'all_stages_passed'
    except Exception as exc:
        report['result'] = 'driver_error'
        report['error_type'] = type(exc).__name__
        # Never print exception bodies or request headers (they may contain credentials).
        print('Regional driver failed:', type(exc).__name__, flush=True)
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (folder / 'report.json').write_text(json.dumps(report,indent=2)+'\n')
        upload(config, folder)
        print('Regional result:', report['result'], flush=True)
    if report['result'] != 'all_stages_passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
