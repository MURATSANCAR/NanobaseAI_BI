"""Editör kararının saf parçaları: gövde doğrulama, isabet formülü, ekrana giden biçim.
Model ve veritabanı yok; uç (card_api) ve şema (025_proof_decision.sql) gerçek PostgreSQL ile
GPU sunucusunda kabul edilir. Çalıştır:

    pytest apps/editor/tests/test_proof_decision.py

`editor.proofing` paketi `editor.db` üzerinden psycopg'yi içe alır; yalnız saf fonksiyonlar
gerektiği için sürücü içe almadan önce taklitlenir (test_appearance.py ile aynı)."""

from __future__ import annotations

import datetime as dt
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool"):
    sys.modules.setdefault(_mod, _Stub(_mod))

from editor.proofing import _decision as D  # noqa: E402


# ------------------------------------------------------------------ doğrulama
def test_accept_has_no_reason():
    out = D.validate({"verdict": "accept", "decidedBy": "editor1"})
    assert out == {"verdict": "ACCEPT", "reason_code": None, "note": None, "decided_by": "editor1"}
    with pytest.raises(D.DecisionError):
        D.validate({"verdict": "ACCEPT", "reasonCode": "OTHER", "decidedBy": "editor1"})


def test_reject_requires_a_reason_from_the_closed_set():
    with pytest.raises(D.DecisionError):
        D.validate({"verdict": "REJECT", "decidedBy": "editor1"})
    with pytest.raises(D.DecisionError):
        D.validate({"verdict": "REJECT", "reasonCode": "BECAUSE", "decidedBy": "editor1"})
    out = D.validate({"verdict": "REJECT", "reasonCode": "text_correct", "note": "  yazım doğru ", "decidedBy": "editor1"})
    assert out["reason_code"] == "TEXT_CORRECT" and out["note"] == "yazım doğru"


def test_note_limit_and_decider_required():
    ok = D.validate({"verdict": "REJECT", "reasonCode": "OTHER", "note": "x" * D.NOTE_MAX, "decidedBy": "e"})
    assert len(ok["note"]) == D.NOTE_MAX
    with pytest.raises(D.DecisionError):
        D.validate({"verdict": "REJECT", "reasonCode": "OTHER", "note": "x" * (D.NOTE_MAX + 1), "decidedBy": "e"})
    with pytest.raises(D.DecisionError):
        D.validate({"verdict": "ACCEPT", "decidedBy": "  "})
    with pytest.raises(D.DecisionError):
        D.validate({"verdict": "MAYBE", "decidedBy": "e"})
    with pytest.raises(D.DecisionError):
        D.validate("not a dict")


def test_reason_codes_match_migration():
    sql = (Path(__file__).resolve().parents[1] / "db" / "migrations" / "025_proof_decision.sql").read_text(encoding="utf-8")
    for code in D.REASON_CODES:
        assert f"'{code}'" in sql
    assert "forbid_change()" in sql  # salt ekleme


# ------------------------------------------------------------------ isabet
def test_precision_formula():
    assert D.precision(0, 0) is None                       # karar yoksa ölçü yok
    assert D.precision(10, 2) == {"accepted": 10, "rejected": 2, "rate": round(10 / 12, 4)}
    assert D.precision(0, 3) == {"accepted": 0, "rejected": 3, "rate": 0.0}


def test_public_shape():
    assert D.public(None) is None
    at = dt.datetime(2026, 9, 23, 10, 0, tzinfo=dt.timezone.utc)
    out = D.public({"verdict": "REJECT", "reason_code": "WRONG_PAGE", "note": None, "decided_by": "editor1", "created_at": at})
    assert out == {"verdict": "REJECT", "reasonCode": "WRONG_PAGE", "note": None, "decidedBy": "editor1", "at": at.isoformat()}
