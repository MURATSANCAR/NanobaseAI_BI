"""Quality gate must fail closed and cannot hide per-question regressions."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest

@pytest.fixture
def gate(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[3] / "tests/text2sql/quality-gate.py"
    spec = importlib.util.spec_from_file_location("quality_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baseline = {"summary": {"cases": 2, "table_recall": 1.0, "fully_recalled": 2, "refused": 0},
                "rows": [{"id": x, "question": x, "missing": [], "refusal": None} for x in ("a", "b")]}
    location = tmp_path / "baseline.json"
    location.write_text(json.dumps(baseline))
    monkeypatch.setattr(module, "BASELINE", location)
    current = copy.deepcopy(baseline)
    monkeypatch.setattr(module, "measure", lambda _: current)
    return module, current

def test_unchanged_passes(gate):
    module, _ = gate
    assert module.main([]) == 0

@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), "1", True])
def test_invalid_measurements_fail(gate, value):
    module, current = gate
    current["summary"]["table_recall"] = value
    assert module.main([]) == 1

def test_more_refusals_fail(gate):
    module, current = gate
    current["summary"]["refused"] = 1
    assert module.main([]) == 1

def test_missing_question_fails(gate):
    module, current = gate
    current["rows"].pop()
    assert module.main([]) == 1

def test_per_question_regression_fails_even_with_same_totals(gate):
    module, current = gate
    current["rows"][0]["refusal"] = "unresolved"
    assert module.main([]) == 1

def test_missing_baseline_cannot_be_created_implicitly(gate):
    module, _ = gate
    module.BASELINE.unlink()
    with pytest.raises(SystemExit):
        module.main([])
    assert not module.BASELINE.exists()
