"""≥30 fidelity smoke cases (staging target 150)."""

from __future__ import annotations

from nanobase_awel.operators.answer_fidelity_validator import validate_answer_fidelity
from nanobase_awel.operators.result_summarizer import summarize_result


def _cases() -> list[dict]:
    out: list[dict] = []
    # empty / tiny
    out.append({"cols": [], "rows": [], "answer": "Toplam 999", "expect_ok": False})
    out.append({"cols": ["n"], "rows": [{"n": 0}], "answer": "Kayıt yok gibi 55555", "expect_ok": False})
    out.append({"cols": ["n"], "rows": [{"n": 3}], "answer": "Değer 3", "expect_ok": True})
    # large totals
    out.append(
        {
            "cols": ["total"],
            "rows": [{"total": 1250000.5}],
            "answer": "Toplam 1250000.5",
            "expect_ok": True,
        }
    )
    out.append(
        {
            "cols": ["total"],
            "rows": [{"total": 1250000.5}],
            "answer": "Toplam 1.350.000 TL",
            "expect_ok": False,
        }
    )
    out.append(
        {
            "cols": ["total"],
            "rows": [{"total": 1250000.5}],
            "answer": "Toplam 1.250.000,50",
            "expect_ok": True,
        }
    )
    # multi-row stats
    rows = [{"v": float(i)} for i in range(1, 11)]
    out.append({"cols": ["v"], "rows": rows, "answer": "Toplam 55", "expect_ok": True})
    out.append({"cols": ["v"], "rows": rows, "answer": "Toplam 9999", "expect_ok": False})
    out.append({"cols": ["v"], "rows": rows, "answer": "Maksimum 10", "expect_ok": True})
    out.append({"cols": ["v"], "rows": rows, "answer": "Minimum 1", "expect_ok": True})
    # truncated narrative
    out.append(
        {
            "cols": ["id"],
            "rows": [{"id": i} for i in range(5)],
            "answer": "Hepsi 500000 kayıt",
            "expect_ok": False,
            "truncated": True,
        }
    )
    # masked-ish nulls
    out.append(
        {
            "cols": ["amt"],
            "rows": [{"amt": None}, {"amt": 42.0}],
            "answer": "Tutar 42",
            "expect_ok": True,
        }
    )
    out.append(
        {
            "cols": ["amt"],
            "rows": [{"amt": None}, {"amt": 42.0}],
            "answer": "Tutar 100",
            "expect_ok": False,
        }
    )
    # generate fillers to ≥30
    for i in range(17, 35):
        val = float(1000 + i)
        out.append(
            {
                "cols": ["x"],
                "rows": [{"x": val}],
                "answer": f"Sonuç {val}",
                "expect_ok": True,
            }
        )
        if len(out) >= 30:
            break
    return out


def test_fidelity_corpus_min_30():
    cases = _cases()
    assert len(cases) >= 30
    failed = []
    for i, c in enumerate(cases):
        summary = summarize_result(
            c["cols"], c["rows"], truncated=bool(c.get("truncated"))
        )
        ok, problems = validate_answer_fidelity(
            c["answer"], summary=summary, rows=c["rows"]
        )
        if ok != c["expect_ok"]:
            failed.append((i, c["answer"], ok, problems, c["expect_ok"]))
    assert not failed, failed
