"""Maintain retained bootstrap/CI identity; never mutate the root of trust."""
import argparse
import json
import os
from pathlib import Path
import subprocess


def check_changes(plan):
    for resource in plan.get('resource_changes', []):
        actions = resource['change']['actions']
        if 'delete' in actions:
            raise ValueError('Foundation replacement/deletion is prohibited: ' + resource['address'])
        if resource['address'] == 'aws_iam_policy.runtime_boundary' and actions != ['no-op']:
            raise ValueError('Runtime ceiling changes require the external root-of-trust identity')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stack', choices=['bootstrap', 'identity'])
    parser.add_argument('operation', choices=['plan', 'apply'])
    args = parser.parse_args()
    account = subprocess.check_output(['aws', 'sts', 'get-caller-identity', '--query', 'Account', '--output', 'text'], text=True).strip()
    if account != '026249143093' or os.environ['AWS_REGION'] != 'us-east-1':
        raise ValueError('Unexpected AWS account or region')
    path = Path(__file__).resolve().parents[1] / 'iac' / args.stack

    def tf(*parts, capture=False):
        return subprocess.run(['terraform', '-chdir=' + str(path), *parts], check=True, text=True, capture_output=capture).stdout

    tf('init', '-input=false', '-lockfile=readonly', '-reconfigure',
       '-backend-config=bucket=' + os.environ['TF_STATE_BUCKET'],
       '-backend-config=key=infra-signal/' + args.stack + '.tfstate',
       '-backend-config=region=us-east-1', '-backend-config=encrypt=true', '-backend-config=use_lockfile=true')
    tf('plan', '-input=false', '-lock-timeout=5m', '-out=foundation.tfplan')
    check_changes(json.loads(tf('show', '-json', 'foundation.tfplan', capture=True)))
    if args.operation == 'apply':
        tf('apply', '-input=false', 'foundation.tfplan')
    # State/plan JSON may contain the alert email: do not publish it as an artifact.


if __name__ == '__main__':
    main()
