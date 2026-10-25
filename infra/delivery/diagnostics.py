#!/usr/bin/env python3
"""Bounded, read-only host observations. Never emit environment, logs or wallet data."""
import argparse
import datetime
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

PORTS = {'dev': (8180, 3300, 46200), 'prod': (8080, 3000, 46100)}

def cpu_sample(read=Path.read_text):
    values = read(Path('/proc/stat')).splitlines()[0].split()[1:9]
    ticks = [int(value) for value in values]
    return sum(ticks), ticks[3] + ticks[4]

def cpu_percent(before, after):
    elapsed, idle = after[0] - before[0], after[1] - before[1]
    return round(100 * (1 - idle / elapsed), 2) if elapsed > 0 and 0 <= idle <= elapsed else None

def command(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=12, check=False)
        if result.returncode:
            return {'status': 'unavailable', 'exit_code': result.returncode}
        # The selected Docker formats contain no environment or application logs.
        text = result.stdout
        if len(text.encode()) > 96 * 1024:
            return {'status': 'unavailable', 'reason': 'output_limit'}
        return {'status': 'ok', 'rows': [json.loads(line) for line in text.splitlines() if line]}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {'status': 'unavailable', 'reason': 'command_unavailable_or_timeout'}

def http_status(url, payload=None):
    headers = {'Content-Type': 'application/json'} if payload is not None else {}
    request = urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            # Keep only the result/code of the explicitly selected RPC method.
            if payload is not None:
                data = json.loads(response.read(4096))
                return {'status': 'ok' if data.get('result') == 'ok' else 'unhealthy',
                    'http_status': response.status, 'rpc_error_code': data.get('error', {}).get('code')}
            return {'status': 'ok', 'http_status': response.status}
    except urllib.error.HTTPError as error:
        return {'status': 'rate_limited' if error.code == 429 else 'unhealthy', 'http_status': error.code}
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return {'status': 'unavailable'}

def collect(channel, sleep=time.sleep, cpu=cpu_sample, run=command, request=http_status):
    if channel not in PORTS:
        raise ValueError('Expected dev or prod')
    first = cpu()
    sleep(1)
    usage = cpu_percent(first, cpu())
    data = Path('/var/lib/silicium-dev' if channel == 'dev' else '/var/lib/silicium')
    disk = shutil.disk_usage(data if data.exists() else '/')
    api, web, network = PORTS[channel]
    containers = run(['docker', 'ps', '--filter', f'label=com.docker.compose.project=silicium{"-dev" if channel == "dev" else ""}',
        '--format', '{"name":{{json .Names}},"image":{{json .Image}},"state":{{json .State}}}'])
    names = [row['name'] for row in containers.get('rows', [])]
    resources = run(['docker', 'stats', '--no-stream', '--format',
        '{"name":{{json .Name}},"cpu":{{json .CPUPerc}},"memory":{{json .MemUsage}},"pids":{{json .PIDs}}}', *names]) if names else {'status': containers['status'], 'rows': []}
    return {'schema_version': 1, 'channel': channel,
        'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'cpu_busy_percent': usage,
        'disk': {'total_bytes': disk.total, 'used_bytes': disk.used, 'free_bytes': disk.free},
        'containers': containers,
        'resources': resources,
        'health': {'api': request(f'http://127.0.0.1:{api}/health'),
            'web': request(f'http://127.0.0.1:{web}/'),
            'network': request(f'http://127.0.0.1:{network}/health')},
        'rpc': request('https://api.devnet.solana.com', {'jsonrpc': '2.0', 'id': 1, 'method': 'getHealth'}) if channel == 'dev' else {'status': 'not_requested'}}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', choices=PORTS, required=True)
    print(json.dumps(collect(parser.parse_args().channel)))
