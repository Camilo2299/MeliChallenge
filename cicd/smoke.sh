#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${1:?Usage: bash cicd/smoke.sh https://API_ID.execute-api.REGION.amazonaws.com}"
BASE_URL="${BASE_URL%/}"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
curl --fail --silent --show-error --retry 6 --retry-delay 10 --retry-all-errors \
  --connect-timeout 5 --max-time 15 "$BASE_URL/health/ready" > "$TMP_DIR/ready.json"
python3 - "$TMP_DIR/ready.json" <<'PY'
import json,sys
with open(sys.argv[1]) as f: body=json.load(f)
assert body['status']=='ready', body
PY
CODE=$(curl --silent --show-error --connect-timeout 5 --max-time 15 -o "$TMP_DIR/unauthorized.json" -w '%{http_code}' "$BASE_URL/v1/services")
test "$CODE" = 401
printf 'PASS readiness and JWT rejection without token\n'
# Authenticated business probes are separate: obtain a token through your IdP,
# then supply it securely to your API client. Never persist tokens in Terraform.
