#!/usr/bin/env python3
"""Lab-only task replacement and rollback rehearsal. Default: read-only preflight."""
import argparse
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROFILE = 'devops-challenge'
REGION = 'us-east-1'
NAME = 'infra-signal-lab'
REPORT = Path('/tmp/meli-resilience-drill.json')


def aws(aws_service, operation, **kwargs):
    command = ['aws', '--profile', PROFILE, '--region', REGION, '--output', 'json', '--no-cli-pager', aws_service, operation]
    for key, value in kwargs.items():
        command += ['--' + key.replace('_', '-'), str(value)]
    return json.loads(subprocess.check_output(command, text=True))


def current():
    response = aws('ecs', 'describe-services', cluster=NAME, services=NAME)
    if response.get('failures') or len(response['services']) != 1:
        raise RuntimeError('Expected exactly the laboratory ECS service.')
    return response['services'][0]


def stable(service, definition):
    return (service['taskDefinition'] == definition and service['runningCount'] >= service['desiredCount']
            and service['pendingCount'] == 0 and len(service['deployments']) == 1
            and service['deployments'][0].get('rolloutState') == 'COMPLETED')


def wait_stable(definition, deadline=900, excluded_task=None):
    started = time.monotonic()
    while time.monotonic() - started < deadline:
        service = current()
        tasks = aws('ecs', 'list-tasks', cluster=NAME, service_name=NAME)['taskArns']
        if stable(service, definition) and (not excluded_task or excluded_task not in tasks):
            tg = service['loadBalancers'][0]['targetGroupArn']
            targets = aws('elbv2', 'describe-target-health', target_group_arn=tg)['TargetHealthDescriptions']
            healthy = sum(t['TargetHealth']['State'] == 'healthy' for t in targets)
            if healthy >= service['desiredCount']:
                return {'elapsed_seconds': round(time.monotonic() - started, 2),
                        'running': service['runningCount'], 'healthy_targets': healthy}
        time.sleep(10)
    raise RuntimeError('ECS did not return to a healthy stable deployment within 15 minutes.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Requires prior approval of the reviewed drill.')
    parser.add_argument('--rollback-only', action='store_true', help='Resume the approved rollback rehearsal without stopping another task.')
    args = parser.parse_args()
    if aws('sts', 'get-caller-identity')['Account'] != '026249143093':
        raise SystemExit('Unexpected AWS account.')
    service = current()
    baseline = service['taskDefinition']
    if service['desiredCount'] != 2 or not stable(service, baseline):
        raise SystemExit('Require two desired tasks and a stable deployment before this drill.')
    arns = aws('ecs', 'list-tasks', cluster=NAME, service_name=NAME)['taskArns']
    # CLI list arguments are passed separately, never through shell interpolation.
    tasks = json.loads(subprocess.check_output(['aws', '--profile', PROFILE, '--region', REGION,
        'ecs', 'describe-tasks', '--cluster', NAME, '--tasks', *arns], text=True))['tasks']
    if len(tasks) != 2 or any(t.get('healthStatus') != 'HEALTHY' for t in tasks):
        raise SystemExit('Require exactly two healthy tasks.')
    print(json.dumps({'baseline': baseline, 'tasks': [t['taskArn'] for t in tasks],
        'availability_zones': sorted({t['availabilityZone'] for t in tasks}),
        'actions': ['stop exactly one task and wait for replacement',
                    'deploy a new revision with identical image/configuration',
                    'roll back to the original active revision and verify stability'],
        'scope': 'Task replacement and manual revision rollback; no AZ outage or bad-image injection.'}, indent=2), flush=True)
    if not args.execute:
        return
    base = os.environ.get('BASE_URL', '')
    token = os.environ.get('ACCESS_TOKEN', '')
    if base != 'https://v1dbllhj9a.execute-api.us-east-1.amazonaws.com' or not token:
        raise SystemExit('Use the authorized lab URL and an in-memory access token from the login helper.')
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'baseline': baseline,
              'scope': ('Identical-image revision rollback only' if args.rollback_only else
                        'Single-task replacement and identical-image revision rollback'), 'steps': [], 'samples': []}
    done = threading.Event()
    phase = ['preflight']

    def sample():
        while not done.is_set():
            started = time.monotonic()
            try:
                req = urllib.request.Request(base + '/v1/services', headers={'Authorization': 'Bearer ' + token})
                with urllib.request.urlopen(req, timeout=5) as response:
                    payload = json.load(response)
                    status = response.status
                    valid = isinstance(payload, list) and len(payload) == 3
            except Exception:
                status, valid = 0, False
            report['samples'].append({'at': datetime.now(timezone.utc).isoformat(), 'phase': phase[0],
                'status': status, 'valid': valid, 'elapsed_ms': round((time.monotonic()-started)*1000, 2)})
            done.wait(1)
    worker = threading.Thread(target=sample, daemon=True)
    worker.start()
    candidate = None
    baseline_needs_restore = False
    try:
        time.sleep(2)
        if not report['samples'] or not all(s['valid'] for s in report['samples']):
            raise RuntimeError('Authenticated preflight failed; no fault injected.')
        if not args.rollback_only:
            phase[0] = 'single-task-replacement'
            stopped = tasks[0]['taskArn']
            aws('ecs', 'stop-task', cluster=NAME, task=stopped, reason='Authorized single-task resilience rehearsal')
            report['steps'].append({'name': phase[0], 'stopped_task': stopped,
                                   **wait_stable(baseline, excluded_task=stopped)})
        # Clone known-good config: this tests the revision rollback procedure, not failure detection.
        definition = aws('ecs', 'describe-task-definition', task_definition=baseline)['taskDefinition']
        allowed = {'family', 'taskRoleArn', 'executionRoleArn', 'networkMode', 'containerDefinitions',
                   'volumes', 'placementConstraints', 'requiresCompatibilities', 'cpu', 'memory',
                   'pidMode', 'ipcMode', 'proxyConfiguration', 'inferenceAccelerators',
                   'ephemeralStorage', 'runtimePlatform', 'enableFaultInjection'}
        request = {k: v for k, v in definition.items() if k in allowed}
        request['tags'] = [{'key': 'Project', 'value': 'infra-signal'},
                           {'key': 'Environment', 'value': 'lab'},
                           {'key': 'Purpose', 'value': 'authorized-rollback-rehearsal'}]
        with tempfile.TemporaryDirectory(prefix='meli-drill-') as directory:
            path = Path(directory) / 'task.json'
            path.write_text(json.dumps(request)); path.chmod(0o600)
            candidate = aws('ecs', 'register-task-definition', cli_input_json='file://' + str(path))['taskDefinition']['taskDefinitionArn']
        report['candidate'] = candidate
        phase[0] = 'candidate-identical-image'
        baseline_needs_restore = True
        print('Deploying temporary identical-image revision:', candidate, flush=True)
        aws('ecs', 'update-service', cluster=NAME, service=NAME, task_definition=candidate)
        report['steps'].append({'name': phase[0], 'task_definition': candidate, **wait_stable(candidate)})
        print('Candidate stable; restoring baseline:', baseline, flush=True)
        phase[0] = 'rollback-to-baseline'
        aws('ecs', 'update-service', cluster=NAME, service=NAME, task_definition=baseline)
        report['steps'].append({'name': phase[0], **wait_stable(baseline)})
        baseline_needs_restore = False
        report['result'] = 'completed'
    except Exception as exc:
        report['result'] = 'failed'
        report['error_type'] = type(exc).__name__
        raise
    finally:
        try:
            if baseline_needs_restore and current()['taskDefinition'] == baseline:
                baseline_needs_restore = False
            if baseline_needs_restore:
                phase[0] = 'emergency-restore-baseline'
                aws('ecs', 'update-service', cluster=NAME, service=NAME, task_definition=baseline)
                report['steps'].append({'name': phase[0], **wait_stable(baseline)})
                baseline_needs_restore = False
            if candidate and not baseline_needs_restore:
                aws('ecs', 'deregister-task-definition', task_definition=candidate)
        finally:
            done.set(); worker.join(timeout=7)
            report['finished_at'] = datetime.now(timezone.utc).isoformat()
            report['failed_samples'] = sum(not s['valid'] or s['status'] != 200 for s in report['samples'])
            report['baseline_restored'] = not baseline_needs_restore and current()['taskDefinition'] == baseline
            REPORT.write_text(json.dumps(report, indent=2)+'\n')
            print('Sanitized drill report:', REPORT, flush=True)
    if report['failed_samples']:
        raise SystemExit('Drill completed but some sampled requests failed; inspect the report.')
    print('PASS task replacement and controlled revision rollback; baseline restored.', flush=True)


if __name__ == '__main__':
    main()
