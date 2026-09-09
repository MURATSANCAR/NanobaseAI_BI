import importlib.util
from pathlib import Path
import sys


def test_inventory_never_claims_live_quality():
    directory = Path(__file__).resolve().parents[2] / 'tools' / 'release-gate'
    sys.path.insert(0, str(directory))
    try:
        spec = importlib.util.spec_from_file_location('product_quality_gate', directory / 'run_quality_benchmark.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = module.run_offline_eval('test')
        assert report['fullPass'] is False
        assert all(value is None for value in report['metrics'].values())
        assert report['failures']
    finally:
        sys.path.remove(str(directory))


def test_live_gate_rejects_tampered_evidence_and_unknown_metrics(tmp_path):
    import json
    import hashlib
    directory = Path(__file__).resolve().parents[2] / 'tools' / 'release-gate'
    sys.path.insert(0, str(directory))
    try:
        spec = importlib.util.spec_from_file_location('quality_evidence_test', directory / 'run_quality_benchmark.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        artifact = tmp_path / 'response.json'
        artifact.write_text('{"rows": [1]}')
        ref = {'path': artifact.name, 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}
        evidence = {'release': 'test', 'mode': 'live', 'codeRevision': 'abc', 'catalogHash': 'def',
                    'datasource': 'test', 'generatedAt': '2026-09-09', 'cases': [
                    {'id': 'q1', 'question': 'test', 'response': ref, 'reference': ref,
                     'checks': {'executionResultEquivalence': True}}]}
        path = tmp_path / 'evidence.json'
        path.write_text(json.dumps(evidence))
        report = module.evaluate_live_evidence(path, 'test', module.run_offline_eval('test'))
        assert report['metrics']['executionResultEquivalence'] == 1
        assert not report['fullPass']
        assert report['metrics']['businessAnswerCorrectness'] is None
        artifact.write_text('{"rows": [2]}')
        report = module.evaluate_live_evidence(path, 'test', module.run_offline_eval('test'))
        assert report['metrics']['executionResultEquivalence'] is None
        assert any('changed' in error for error in report['failures'])
        assert not report['fullPass']
    finally:
        sys.path.remove(str(directory))
