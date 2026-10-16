#!/usr/bin/env python3
"""Local OAuth code + PKCE smoke test. Access tokens stay only in memory."""
import argparse
import base64
import hashlib
import json
import secrets
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', required=True)
    parser.add_argument('--authorize-url', required=True)
    parser.add_argument('--client-id', required=True)
    parser.add_argument('--report', default='/tmp/meli-authenticated-smoke.json')
    parser.add_argument('--load-test', action='store_true', help='Run separately authorized cloud test: 30 RPS for 60 seconds.')
    parser.add_argument('--resilience-drill', action='store_true', help='Run separately authorized task replacement and controlled revision rollback drill.')
    parser.add_argument('--rollback-only', action='store_true', help='With --resilience-drill, resume rollback without another task stop.')
    parser.add_argument('--capacity-test', action='store_true', help='Run the separately approved 100–10,000 RPS capacity plan.')
    args = parser.parse_args()
    if args.capacity_test and (args.load_test or args.resilience_drill):
        parser.error('Run the capacity plan separately from smoke load or resilience drills.')
    if args.rollback_only and not args.resilience_drill:
        parser.error('--rollback-only requires --resilience-drill')
    authorize = urllib.parse.urlsplit(args.authorize_url)
    if authorize.scheme != 'https' or not (authorize.hostname or '').endswith('.amazoncognito.com'):
        parser.error('Use the HTTPS Cognito authorize URL returned by Terraform.')
    if urllib.parse.urlsplit(args.api_url).scheme != 'https':
        parser.error('The API URL must use HTTPS.')
    callback = 'http://localhost:8085/callback'
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Callback URLs contain one-time codes; never log them.

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(url.query)
            valid = url.path == '/callback' and secrets.compare_digest(query.get('state', [''])[0], state)
            if not valid:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Invalid OAuth callback. Return to the original login window.')
                return
            if 'error' in query:
                result['error'] = query['error'][0]
            elif query.get('code'):
                result['code'] = query['code'][0]
            else:
                self.send_response(400)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(b'Callback received. Close this tab and return to the terminal.')

    # Request only the API scope: we use the access token, not an ID token or
    # identity claims. API Gateway performs JWT signature/issuer/scope validation.
    params = urllib.parse.urlencode({
        'response_type': 'code', 'client_id': args.client_id,
        'redirect_uri': callback, 'scope': 'infra-metrics/read', 'state': state,
        'code_challenge': challenge, 'code_challenge_method': 'S256',
    })
    with HTTPServer(('127.0.0.1', 8085), Handler) as server:
        server.timeout = 1
        print('Opening Cognito login. Complete sign-in in the browser; tokens will not be printed.', flush=True)
        webbrowser.open(urllib.parse.urlunsplit(authorize._replace(query=params)))
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if not result.get('code'):
        raise SystemExit('OAuth login did not complete successfully. Retry the login command.')
    endpoint = urllib.parse.urlunsplit(authorize._replace(path='/oauth2/token', query='', fragment=''))
    body = urllib.parse.urlencode({
        'grant_type': 'authorization_code', 'client_id': args.client_id,
        'code': result.pop('code'), 'redirect_uri': callback, 'code_verifier': verifier,
    }).encode()
    request = urllib.request.Request(endpoint, data=body, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            tokens = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f'Token exchange failed with HTTP {exc.code}; no token contents logged.') from None
    # Cognito's token response does not include a top-level scope field.
    # The protected API requests below verify authorization through API Gateway,
    # which validates the JWT and its required infra-metrics/read scope.
    if not isinstance(tokens.get('access_token'), str) or not tokens['access_token']:
        raise SystemExit('Cognito did not return an access token.')
    if tokens.get('token_type', '').lower() != 'bearer':
        raise SystemExit('Cognito returned an unexpected token type.')
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'api_url': args.api_url, 'checks': []}
    for path in ['/v1/services', '/v1/services?environment=production', '/v1/services/gateway', '/v1/deployments?service_id=gateway', '/v1/summary']:
        request = urllib.request.Request(args.api_url.rstrip('/') + path, headers={'Authorization': 'Bearer ' + tokens['access_token']})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.load(response)
                assert response.status == 200
                if path == '/v1/summary':
                    assert payload['total_services'] == 3 and payload['source'] == 'sample-data'
                elif path == '/v1/services/gateway':
                    assert payload['id'] == 'gateway'
                else:
                    assert len(payload) == {'/v1/services': 3, '/v1/services?environment=production': 2, '/v1/deployments?service_id=gateway': 1}[path]
                report['checks'].append({'path': path, 'status': response.status, 'request_id': response.headers.get('X-Request-ID')})
                print('PASS authenticated GET', path)
        except urllib.error.HTTPError as exc:
            raise SystemExit(f'Authenticated API request failed with HTTP {exc.code}: {path}') from None
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print('Report saved:', args.report, '(no tokens or credentials)')
    if args.load_test or args.resilience_drill or args.capacity_test:
        child_env = os.environ.copy()
        child_env['ACCESS_TOKEN'] = tokens['access_token']
        child_env['BASE_URL'] = args.api_url.rstrip('/')
        root = Path(__file__).resolve().parents[1]
        if args.load_test:
            child_env.update(RATE='30', SECONDS='60', K6_NO_USAGE_REPORT='true')
            subprocess.run(['k6', 'run', '--summary-export', '/tmp/meli-cloud-load.json',
                            str(root / 'performance/loadtest.js')], env=child_env, check=True)
        if args.resilience_drill:
            subprocess.run(['python3', str(root / 'cicd/resilience_drill.py'), '--execute'] +
                           (['--rollback-only'] if args.rollback_only else []), env=child_env, check=True)
        if args.capacity_test:
            subprocess.run(['python3', str(root / 'performance/capacity.py')], env=child_env, check=True)
        child_env.pop('ACCESS_TOKEN', None)


if __name__ == '__main__':
    main()
