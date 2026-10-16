import http from 'k6/http';
import { check } from 'k6';

const base = (__ENV.BASE_URL || 'http://127.0.0.1:18080').replace(/\/$/, '');
const local = /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(base);
const rate = Number(__ENV.RATE || 10);
const seconds = Number(__ENV.SECONDS || 60);
if (!Number.isInteger(rate) || rate < 1 || rate > (local ? 1000 : 30)) {
  throw new Error('RATE must be 1–1000 locally, or 1–30 for the authorized cloud smoke.');
}
if (!Number.isInteger(seconds) || seconds < 1 || seconds > 60) {
  throw new Error('SECONDS must be 1–60. Larger tests require a separate reviewed plan.');
}
if (!local && (!base.startsWith('https://') || !__ENV.ACCESS_TOKEN)) {
  throw new Error('Cloud tests require HTTPS and ACCESS_TOKEN in the environment.');
}
export const options = {
  scenarios: { bounded: {
    executor: 'constant-arrival-rate', rate, timeUnit: '1s', duration: `${seconds}s`,
    preAllocatedVUs: 20, maxVUs: 100, gracefulStop: '15s',
  } },
  thresholds: {
    http_req_failed: ['rate<0.001'],
    http_req_duration: ['p(95)<200'],
    checks: ['rate==1'],
    dropped_iterations: ['count==0'],
  },
};
export default function () {
  const headers = __ENV.ACCESS_TOKEN ? { Authorization: `Bearer ${__ENV.ACCESS_TOKEN}` } : {};
  const response = http.get(`${base}/v1/services`, { headers, timeout: '10s' });
  check(response, {
    'HTTP 200': r => r.status === 200,
    'three fixture services': r => {
      try { return Array.isArray(r.json()) && r.json().length === 3; } catch (_) { return false; }
    },
  });
}
