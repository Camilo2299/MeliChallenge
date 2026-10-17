import http from 'k6/http';
import { check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import exec from 'k6/execution';

const rate = Number(__ENV.RATE);
const allowed = [100, 500, 1000, 2500, 5000, 10000];
const base = (__ENV.BASE_URL || '').replace(/\/$/, '');
if (!allowed.includes(rate) || base !== 'https://v1dbllhj9a.execute-api.us-east-1.amazonaws.com' || !__ENV.ACCESS_TOKEN) {
  throw new Error('Use the reviewed lab URL, an allowed stage rate and an in-memory access token.');
}
const successful = new Counter('successful_requests');
const throttled = new Counter('responses_429');
const serverErrors = new Counter('responses_5xx');
const invalid = new Rate('invalid_responses');
const steadyRequests = new Counter('steady_requests');
const steadySuccess = new Counter('steady_successful_requests');
const steadyDuration = new Trend('steady_duration', true);
const steadyInvalid = new Rate('steady_invalid');
export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: { capacity: {
    executor: 'ramping-arrival-rate', startRate: 1, timeUnit: '1s',
    stages: [{ target: rate, duration: '10s' }, { target: rate, duration: '60s' }],
    preAllocatedVUs: Math.max(100, Math.ceil(rate * 0.12)),
    maxVUs: Math.max(100, Math.ceil(rate * 0.2)), gracefulStop: '10s',
  } },
  thresholds: {
    http_req_failed: [{ threshold: 'rate<0.001', abortOnFail: true, delayAbortEval: '20s' }],
    invalid_responses: [{ threshold: 'rate<0.001', abortOnFail: true, delayAbortEval: '20s' }],
    http_req_duration: [{ threshold: 'p(95)<200', abortOnFail: true, delayAbortEval: '20s' }],
    steady_duration: [{ threshold: 'p(95)<200', abortOnFail: true, delayAbortEval: '20s' }],
    steady_invalid: [{ threshold: 'rate<0.001', abortOnFail: true, delayAbortEval: '20s' }],
    dropped_iterations: [{ threshold: 'count==0', abortOnFail: true, delayAbortEval: '20s' }],
  },
};
export default function () {
  const steady = Date.now() - exec.scenario.startTime >= 10000;
  const response = http.get(`${base}/v1/metrics`, {
    headers: { Authorization: `Bearer ${__ENV.ACCESS_TOKEN}` }, timeout: '5s',
  });
  let valid = false;
  if (response.status === 200) {
    try { const data = response.json(); valid = data.source === 'aws-cloudwatch-ecs' && data.service.id === 'infra-signal-lab' && Array.isArray(data.metrics) && data.metrics.length === 10; } catch (_) { /* Count invalid payload. */ }
  }
  invalid.add(!valid);
  if (steady) {
    steadyRequests.add(1);
    steadySuccess.add(valid ? 1 : 0);
    steadyDuration.add(response.timings.duration);
    steadyInvalid.add(!valid);
  }
  successful.add(valid ? 1 : 0);
  throttled.add(response.status === 429 ? 1 : 0);
  serverErrors.add(response.status >= 500 ? 1 : 0);
  check(response, { 'authenticated real telemetry content is valid': () => valid });
}
