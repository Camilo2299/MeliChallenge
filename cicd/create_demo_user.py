#!/usr/bin/env python3
"""Create an operational Cognito demo user without sending an email invitation."""
import argparse
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool-id', required=True)
    parser.add_argument('--username', required=True)
    parser.add_argument('--profile', default='devops-challenge')
    parser.add_argument('--secret-arn', default='')
    args = parser.parse_args()
    def aws(service, *command):
        return subprocess.run(['aws', service, *command, *(['--profile', args.profile] if args.profile else []), '--region', 'us-east-1'], capture_output=True, text=True, check=True).stdout
    caller = json.loads(aws('sts', 'get-caller-identity'))
    if caller['Account'] != '026249143093':
        raise SystemExit('Unexpected AWS account; refusing to create a user.')
    pool = json.loads(aws('cognito-idp', 'describe-user-pool', '--user-pool-id', args.pool_id))
    if pool['UserPool']['Name'] != 'infra-signal-lab':
        raise SystemExit('Unexpected user pool; refusing to create a user.')
    if args.secret_arn and not args.secret_arn.startswith('arn:aws:secretsmanager:us-east-1:026249143093:secret:infra-signal-lab/demo-login-r'):
        raise SystemExit('Unexpected demo secret ARN')
    stored = None
    if args.secret_arn:
        metadata = json.loads(aws('secretsmanager', 'describe-secret', '--secret-id', args.secret_arn))
        if any('AWSCURRENT' in stages for stages in metadata.get('VersionIdsToStages', {}).values()):
            stored = json.loads(json.loads(aws('secretsmanager', 'get-secret-value', '--secret-id', args.secret_arn))['SecretString'])
    password = stored['temporary_password'] if stored else 'Aa7!' + secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory(prefix='meli-cognito-request-') as directory:
        request = Path(directory) / 'request.json'
        request.write_text(json.dumps({
            'UserPoolId': args.pool_id, 'Username': args.username,
            'TemporaryPassword': password, 'MessageAction': 'SUPPRESS',
            'UserAttributes': [{'Name': 'email', 'Value': args.username}],
        }))
        request.chmod(0o600)
        if args.secret_arn and not stored:
            secret_request = Path(directory) / 'secret.json'
            secret_request.write_text(json.dumps({'SecretId': args.secret_arn, 'SecretString': json.dumps({'username': args.username, 'temporary_password': password, 'user_pool_id': args.pool_id})}))
            secret_request.chmod(0o600)
            aws('secretsmanager', 'put-secret-value', '--cli-input-json', 'file://' + str(secret_request))
        try:
            aws('cognito-idp', 'admin-create-user', '--cli-input-json', 'file://' + str(request))
        except subprocess.CalledProcessError as exc:
            if 'UsernameExistsException' in exc.stderr and args.secret_arn:
                print('Demo user exists; no password or user attributes were changed.')
                return
            if 'UsernameExistsException' in exc.stderr:
                raise SystemExit('User already exists; no password or user attributes were changed.') from None
            raise SystemExit('Cognito user creation failed; inspect AWS permissions and pool configuration.') from None
    if args.secret_arn:
        print('Initial demo login provisioned in Secrets Manager; no invitation sent.')
        return
    fd, path = tempfile.mkstemp(prefix='meli-demo-login-', suffix='.txt')
    with os.fdopen(fd, 'w') as stream:
        stream.write('Cognito demonstration account\nUsername: ' + args.username + '\nTemporary password: ' + password + '\nChange the password at the first hosted login. Email remains unverified; no invitation was sent.\n')
    print('Demo user created without an email invitation. Private credential file:', path)
    print('Open the file locally. Do not commit or send it; remove it after completing first sign-in.')


if __name__ == '__main__':
    main()
