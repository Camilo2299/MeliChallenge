import http from 'k6/http';
import { check } from 'k6';
export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 10, timeUnit: '1s', preAllocatedVUs: 200, maxVUs: 3000,
      stages: [
        { target: 100, duration: '1m' },
        { target: 500, duration: '2m' },
        { target: 1000, duration: '2m' },
        { target: 5000, duration: '3m' },
        { target: 10000, duration: '5m' },
        { target: 10000, duration: '10m' }
      ]
    }
  },
  thresholds: { http_req_failed: ['rate<0.001'], http_req_duration: ['p(95)<200'] }
};
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
export default function () {
  const res = http.get(`${BASE_URL}/v1/services`);
  check(res, { 'status 200': r => r.status === 200 });
}
