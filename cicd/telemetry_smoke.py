#!/usr/bin/env python3
"""Bounded live telemetry validation. Temporary M2M client and audience are restored in finally; secrets stay in memory."""
import argparse
import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='devops-challenge')
    parser.add_argument('--report', default='/tmp/meli-real-telemetry.json')
    parser.add_argument('--load-test', action='store_true')
    args = parser.parse_args()
    base = 'https://v1dbllhj9a.execute-api.us-east-1.amazonaws.com'
    api_id, pool, service = 'v1dbllhj9a', 'us-east-1_krpZrFRXe', 'infra-signal-lab'
    oauth = 'https://infra-signal-lab-026249143093.auth.us-east-1.amazoncognito.com'

    def aws(*parts):
        out = subprocess.check_output(['aws', *parts, '--profile', args.profile, '--region', 'us-east-1', '--output', 'json'])
        return json.loads(out) if out.strip() else {}

    assert aws('sts', 'get-caller-identity')['Account'] == '026249143093'
    authors = aws('apigatewayv2', 'get-authorizers', '--api-id', api_id)['Items']
    author = next(a for a in authors if a['Name'] == 'organization-jwt')
    original = copy.deepcopy(author['JwtConfiguration'])
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'api_url': base, 'checks': [], 'cleanup': {}}
    client_id = None
    changed = False
    token = None

    def get(path):
        req = urllib.request.Request(base + path, headers={'Authorization': 'Bearer ' + token})
        for attempt in range(20):
            try:
                with urllib.request.urlopen(req, timeout=15) as res:
                    assert res.status == 200
                    return json.load(res), {'path': path, 'status': res.status, 'request_id': res.headers.get('X-Request-ID'), 'authorization_propagation_retries': attempt}
            except urllib.error.HTTPError as err:
                if err.code not in (401, 403) or attempt == 19:
                    raise
                time.sleep(3)

    try:
        client = aws('cognito-idp', 'create-user-pool-client', '--cli-input-json', json.dumps({
            'UserPoolId': pool, 'ClientName': 'temporary-real-telemetry-probe', 'GenerateSecret': True,
            'AllowedOAuthFlowsUserPoolClient': True, 'AllowedOAuthFlows': ['client_credentials'],
            'AllowedOAuthScopes': ['infra-metrics/read']}))['UserPoolClient']
        client_id = client['ClientId']
        test_config = copy.deepcopy(original)
        test_config['Audience'].append(client_id)
        changed = True
        aws('apigatewayv2', 'update-authorizer', '--api-id', api_id, '--authorizer-id', author['AuthorizerId'],
            '--jwt-configuration', json.dumps(test_config))
        credentials = base64.b64encode((client_id + ':' + client['ClientSecret']).encode()).decode()
        req = urllib.request.Request(oauth + '/oauth2/token', data=urllib.parse.urlencode({'grant_type': 'client_credentials', 'scope': 'infra-metrics/read'}).encode(),
                                     headers={'Authorization': 'Basic ' + credentials, 'Content-Type': 'application/x-www-form-urlencoded'})
        with urllib.request.urlopen(req, timeout=20) as res:
            token = json.load(res)['access_token']
        del credentials, client
        for attempt in range(20):
            try:
                first, _ = get('/v1/metrics')
                break
            except urllib.error.HTTPError as err:
                if err.code not in (401, 403, 503) or attempt == 19:
                    raise RuntimeError(f'Authenticated probe returned HTTP {err.code}') from None
                time.sleep(3)
        assert first['source'] == 'aws-cloudwatch-ecs' and first['service']['id'] == service
        assert len(first['metrics']) == 10
        for metric_id in ('cpu', 'memory'):
            metric = next(m for m in first['metrics'] if m['id'] == metric_id)
            assert metric['points'], f'{metric_id} missing actual CloudWatch samples'
        paths = ['/v1/services', '/v1/services?environment=lab', '/v1/services/' + service,
                 '/v1/deployments?service_id=' + service, '/v1/summary', '/v1/metrics', '/v1/metrics/history']
        for path in paths:
            payload, check = get(path)
            if path.startswith('/v1/services') and not path.startswith('/v1/services/'):
                assert len(payload) == 1 and payload[0]['id'] == service
            elif path == '/v1/summary':
                assert payload['source'] == 'aws-cloudwatch-ecs' and not payload['stale']
            elif path == '/v1/metrics/history':
                assert payload['snapshots'] and all(s['source'] == 'aws-cloudwatch-ecs' for s in payload['snapshots'])
            report['checks'].append(check)
            print('PASS authenticated', path, flush=True)
        deadline = time.monotonic() + 100
        second = first
        while time.monotonic() < deadline:
            time.sleep(3)
            second, _ = get('/v1/metrics')
            if second['collected_at'] != first['collected_at']:
                break
        assert second['collected_at'] != first['collected_at'], 'Collector did not publish a second snapshot'
        report['successive_collections'] = [first['collected_at'], second['collected_at']]
        item = aws('dynamodb', 'get-item', '--table-name', service + '-telemetry', '--consistent-read',
                   '--key', json.dumps({'pk': {'S': service}, 'sk': {'S': 'LATEST'}}))['Item']
        persisted = json.loads(item['payload']['S'])
        assert persisted['source'] == 'aws-cloudwatch-ecs' and item.get('signature', {}).get('S')
        report['dynamodb'] = {'table': service + '-telemetry', 'persisted_collected_at': persisted['collected_at'], 'signature_present': True}
        report['snapshot'] = second
        definition = aws('ecs', 'describe-task-definition', '--task-definition', persisted['service']['task_definition'])['taskDefinition']
        api_container = next(c for c in definition['containerDefinitions'] if c['name'] == 'api')
        secret = next(s for s in api_container['secrets'] if s['name'] == 'SNAPSHOT_SIGNING_KEY')
        metadata = aws('secretsmanager', 'describe-secret', '--secret-id', secret['valueFrom'])
        report['secrets_manager'] = {'name': metadata['Name'], 'injected_environment_name': secret['name'], 'value_logged': False}
        for path in ['/dashboard', '/dashboard.js', '/dashboard/config']:
            with urllib.request.urlopen(base + path, timeout=15) as response:
                assert response.status == 200
            report['checks'].append({'path': path, 'status': 200, 'public_shell_only': True})
        if args.load_test:
            env = dict(os.environ, ACCESS_TOKEN=token, BASE_URL=base, RATE='30', SECONDS='60', SERVICE_COUNT='1', K6_NO_USAGE_REPORT='true')
            subprocess.run(['k6', 'run', '--summary-export', '/tmp/meli-real-telemetry-load.json', str(Path(__file__).resolve().parents[1] / 'performance/loadtest.js')], env=env, check=True)
            report['bounded_load'] = json.loads(Path('/tmp/meli-real-telemetry-load.json').read_text())
        report['result'] = 'PASS'
    finally:
        try:
            if changed:
                for attempt in range(3):
                    try:
                        aws('apigatewayv2', 'update-authorizer', '--api-id', api_id, '--authorizer-id', author['AuthorizerId'], '--jwt-configuration', json.dumps(original))
                        report['cleanup']['original_audience_restored'] = True
                        break
                    except subprocess.CalledProcessError:
                        if attempt == 2:
                            raise
                        time.sleep(3)
        finally:
            try:
                if client_id:
                    aws('cognito-idp', 'delete-user-pool-client', '--user-pool-id', pool, '--client-id', client_id)
                    report['cleanup']['temporary_client_deleted'] = True
            finally:
                token = None
                Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
                print('Report saved:', args.report, '(no tokens or credentials)', flush=True)


if __name__ == '__main__':
    main()
