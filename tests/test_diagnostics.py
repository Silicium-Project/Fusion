from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

spec = spec_from_file_location('diagnostics', Path(__file__).resolve().parents[1] / 'infra/delivery/diagnostics.py')
diagnostics = module_from_spec(spec)
spec.loader.exec_module(diagnostics)

def test_cpu_busy_percentage_and_invalid_samples():
    assert diagnostics.cpu_percent((100, 10), (200, 35)) == 75
    assert diagnostics.cpu_percent((100, 10), (100, 10)) is None
    assert diagnostics.cpu_percent((100, 10), (110, 30)) is None

def test_collect_only_observes_expected_channel_and_bounded_commands():
    commands, requests = [], []
    samples = iter([(100, 10), (200, 35)])
    def observe(argv):
        commands.append(argv)
        return {'status': 'ok', 'rows': [{'name': 'silicium-dev-worker'}]} if argv[1] == 'ps' else {'status': 'ok', 'rows': []}
    def request(url, payload=None):
        requests.append((url, payload))
        return {'status': 'ok', 'http_status': 200}
    result = diagnostics.collect('dev', sleep=lambda _: None, cpu=lambda: next(samples), run=observe, request=request)
    assert result['cpu_busy_percent'] == 75
    assert [row[1] for row in commands] == ['ps', 'stats']
    assert all('inspect' not in row and 'logs' not in row and 'restart' not in row for row in commands)
    assert any('8180/health' in row[0] for row in requests)
    assert not any('8080/health' in row[0] for row in requests)
    assert requests[-1][1]['method'] == 'getHealth'
