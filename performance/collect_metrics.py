#!/usr/bin/env python3
"""Read existing CloudWatch metrics for a finished capacity report; no mutations."""
import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text())
    start = datetime.fromisoformat(report['started_at']) - timedelta(minutes=2)
    end = min(datetime.now(timezone.utc), datetime.fromisoformat(report['finished_at']) + timedelta(minutes=2))
    cluster = ['Name=ClusterName,Value=infra-signal-lab', 'Name=ServiceName,Value=infra-signal-lab']
    alb = ['Name=LoadBalancer,Value=app/infra-signal-lab-alb/1f5529ed7d49bef5']
    queries = [('AWS/ECS', 'CPUUtilization', cluster, ['Average', 'Maximum']),
               ('AWS/ECS', 'MemoryUtilization', cluster, ['Average', 'Maximum']),
               ('AWS/ApplicationELB', 'RequestCount', alb, ['Sum']),
               ('AWS/ApplicationELB', 'TargetResponseTime', alb, ['Average', 'Maximum']),
               ('AWS/ApplicationELB', 'HTTPCode_Target_5XX_Count', alb, ['Sum'])]
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'period_seconds': 60,
              'window_start': start.isoformat(), 'window_end': end.isoformat(), 'metrics': []}
    for namespace, metric, dimensions, stats in queries:
        command = ['aws', '--profile', 'devops-challenge', '--region', 'us-east-1', '--output', 'json',
                   'cloudwatch', 'get-metric-statistics', '--namespace', namespace, '--metric-name', metric,
                   '--dimensions', *dimensions, '--statistics', *stats,
                   '--period', '60', '--start-time', start.isoformat(), '--end-time', end.isoformat()]
        response = json.loads(subprocess.check_output(command, text=True))
        response['Datapoints'].sort(key=lambda p: p['Timestamp'])
        result['metrics'].append({'namespace': namespace, 'metric': metric, **response})
    Path(args.output).write_text(json.dumps(result, indent=2)+'\n')
    print('CloudWatch metric evidence:', args.output)


if __name__ == '__main__':
    main()
