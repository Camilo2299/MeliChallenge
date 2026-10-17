"""Serialized Actions controller for the lab. Never destroys the control foundation."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
IAC = ROOT / 'iac'
MANIFEST = 'infra-signal/lifecycle.json'


def run(*command, capture=False):
    return subprocess.run(command, check=True, text=True, capture_output=capture).stdout


def aws(*command):
    value = run('aws', *command, '--output', 'json', capture=True)
    return json.loads(value) if value.strip() else {}


def tf(*command, capture=False):
    return run('terraform', '-chdir=' + str(IAC), *command, capture=capture)


def validate_manifest(value):
    if value.get('status') not in ('present', 'absent', 'destroying'):
        raise ValueError('Invalid lifecycle status')
    if not re.fullmatch(r'(?:r[0-9]{1,20})?', value.get('generation', '')):
        raise ValueError('Invalid deployment generation')
    if not re.fullmatch(r'[a-f0-9]{40}', value.get('image', '')):
        raise ValueError('Expected immutable Git SHA image')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['deploy', 'plan', 'destroy-plan', 'destroy', 'rollback'])
    parser.add_argument('--image', default=os.environ.get('GITHUB_SHA', ''))
    parser.add_argument('--confirmation', default='')
    parser.add_argument('--automatic', action='store_true')
    args = parser.parse_args()
    if args.action == 'destroy' and args.confirmation != 'DESTROY infra-signal-lab DATA':
        raise ValueError('Destruction requires the exact data-loss confirmation')
    bucket = os.environ['TF_STATE_BUCKET']
    if bucket != 'infra-signal-lab-tfstate-026249143093-us-east-1':
        raise ValueError('Unexpected state bucket')
    if aws('sts', 'get-caller-identity')['Account'] != '026249143093':
        raise ValueError('Unexpected AWS account')
    if os.environ.get('AWS_REGION') != 'us-east-1':
        raise ValueError('Unexpected AWS region')
    os.environ['TF_VAR_permissions_boundary_arn'] = 'arn:aws:iam::026249143093:policy/meli-ci-lab-runtime-boundary'
    tf('init', '-input=false', '-lockfile=readonly', '-reconfigure',
       '-backend-config=bucket=' + bucket, '-backend-config=key=infra-signal/lab.tfstate',
       '-backend-config=region=us-east-1', '-backend-config=use_lockfile=true', '-backend-config=encrypt=true')
    resources = tf('state', 'list', capture=True).strip()
    manifest_file = Path(os.environ.get('RUNNER_TEMP', '/tmp')) / 'meli-lifecycle.json'
    listing = aws('s3api', 'list-objects-v2', '--bucket', bucket, '--prefix', MANIFEST)
    exists = any(item['Key'] == MANIFEST for item in listing.get('Contents', []))
    if exists:
        aws('s3api', 'get-object', '--bucket', bucket, '--key', MANIFEST, str(manifest_file))
        manifest = validate_manifest(json.loads(manifest_file.read_text()))
    elif resources:
        # Adopt the actual deployed release, without silently changing it on a plan.
        state = json.loads(tf('show', '-json', capture=True))
        definition = next(r for r in state['values']['root_module']['resources'] if r['type'] == 'aws_ecs_task_definition')
        image = json.loads(definition['values']['container_definitions'])[0]['image'].rsplit(':', 1)[1]
        manifest = validate_manifest({'status': 'present', 'generation': '', 'image': image})
    else:
        manifest = validate_manifest({'status': 'absent', 'generation': '', 'image': args.image})
    if args.automatic and manifest['status'] != 'present':
        print('Lab intentionally absent or destruction incomplete; automatic deployment skipped.')
        return
    if manifest['status'] == 'destroying' and args.action not in ('destroy', 'destroy-plan'):
        raise ValueError('Finish the interrupted destruction before recreating the lab')

    def save():
        manifest_file.write_text(json.dumps(manifest))
        aws('s3api', 'put-object', '--bucket', bucket, '--key', MANIFEST, '--body', str(manifest_file), '--server-side-encryption', 'AES256')

    def plan(name, destroy=False, protected=True, targets=()):
        command = ['plan', '-input=false', '-lock-timeout=5m', '-out=' + name,
                   '-var=image_tag=' + manifest['image'],
                   '-var=deployment_generation=' + manifest['generation'],
                   '-var=deletion_protection=' + str(protected).lower()]
        command.extend('-target=' + target for target in targets)
        if destroy:
            command.append('-destroy')
        tf(*command)
        tf('show', '-no-color', name)

    if args.action in ('destroy', 'destroy-plan'):
        if args.action == 'destroy':
            if args.confirmation != 'DESTROY infra-signal-lab DATA':
                raise ValueError('Destruction requires the exact data-loss confirmation')
            manifest['status'] = 'destroying'
            save()  # Survives cancellation; automatic deployments cannot resurrect the lab.
            targets = [name for name in ('aws_lb.internal', 'aws_dynamodb_table.telemetry') if name in resources.splitlines()]
            if targets:
                plan('unprotect.tfplan', protected=False, targets=targets)
                tf('apply', '-input=false', 'unprotect.tfplan')
        plan('destroy.tfplan', destroy=True, protected=False)
        if args.action == 'destroy':
            tf('apply', '-input=false', 'destroy.tfplan')
            if tf('state', 'list', capture=True).strip():
                raise RuntimeError('Resources remain in the application state')
            manifest['status'] = 'absent'
            save()
        return
    # Adopt the AWS-created performance group once; thereafter Terraform owns its lifecycle.
    if args.action == 'deploy' and 'aws_cloudwatch_log_group.insights' not in resources.splitlines():
        group = '/aws/ecs/containerinsights/infra-signal-lab/performance'
        groups = aws('logs', 'describe-log-groups', '--log-group-name-prefix', group).get('logGroups', [])
        if any(item['logGroupName'] == group for item in groups):
            tf('import', '-input=false', '-var=image_tag=' + manifest['image'],
               '-var=deployment_generation=' + manifest['generation'],
               'aws_cloudwatch_log_group.insights', group)
    previous = manifest['image']
    if args.action == 'rollback':
        image = manifest.get('previous_image')
        if not image:
            raise ValueError('No previous successful image recorded')
    elif args.action == 'deploy':
        image = args.image
    else:
        image = manifest['image']
    if not re.fullmatch(r'[a-f0-9]{40}', image):
        raise ValueError('Image must be a full Git SHA')
    aws('ecr', 'describe-images', '--repository-name', 'infra-signal-lab', '--image-ids', 'imageTag=' + image)
    manifest['image'] = image
    if not resources and args.action == 'deploy':
        if manifest['status'] == 'absent' or not manifest['generation']:
            manifest['generation'] = 'r' + os.environ['GITHUB_RUN_ID']
        # Persist before apply so a partial creation reuses the same names on retry.
        manifest['status'] = 'present'
        save()
    plan('deployment.tfplan')
    if args.action == 'plan':
        return
    tf('apply', '-input=false', 'deployment.tfplan')
    outputs = json.loads(tf('output', '-json', capture=True))
    demo_secret = outputs.get('demo_login_secret_arn', {}).get('value')
    if demo_secret:
        run('python3', str(ROOT / 'cicd/create_demo_user.py'), '--profile', '',
            '--pool-id', outputs['cognito_user_pool_id']['value'],
            '--username', os.environ['DEMO_USER_EMAIL'], '--secret-arn', demo_secret)
    aws('ecs', 'wait', 'services-stable', '--cluster', outputs['ecs_cluster']['value'], '--services', outputs['ecs_service']['value'])
    run('bash', str(ROOT / 'cicd/smoke.sh'), outputs['api_url']['value'])
    run('python3', str(ROOT / 'cicd/telemetry_smoke.py'), '--profile', '',
        '--api-url', outputs['api_url']['value'], '--pool-id', outputs['cognito_user_pool_id']['value'],
        '--authorize-url', outputs['cognito_login_url']['value'], '--report', 'telemetry-smoke.json')
    manifest['status'] = 'present'
    if previous != image:
        manifest['previous_image'] = previous
    save()
    with open(os.environ.get('GITHUB_STEP_SUMMARY', os.devnull), 'a') as summary:
        summary.write('Application deployed and authenticated telemetry verified.\n\n' + outputs['dashboard_url']['value'] + '\n')


if __name__ == '__main__':
    main()
