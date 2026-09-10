"""Sorudaki koşul sonuca taşındı mı — SQL metnine bakmadan, kara kutu olarak.

Bir koşulu değiştirince sonuç değişmiyorsa o koşul muhtemelen düşürülmüştür. "Muhtemelen", çünkü
aynı sonuç tek başına kanıt değil: iki şehirde de veri olmayabilir, iki dönemin toplamı tesadüfen
eşit çıkabilir. Bu yüzden iddia yalnız **kontrollü veride** kurulur — beklenen sonuçlar bilinir ve
birbirinden ayrıdır. Gerçek veride aynı sonuç bir inceleme sinyalidir, hata değil.

Karşılaştırma normalize edilmiş kolon adları ve satır içeriği üzerinden yapılır; yürütme kimliği ve
zaman damgası parmak izine girmez — onlar her koşuda zaten farklıdır.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

from semantic_layer.models import SemanticType
from semantic_layer.runtime.compiler import DeterministicCompiler, default_filters_provider
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog, _run  # noqa: F401


def fingerprint(cols, rows) -> str:
    """Sonucun kendisi: kolon adları ve satır içeriği. Kimlik, zaman, satır sırası dışarıda."""
    payload = {
        "columns": sorted(str(c).strip().lower() for c in cols),
        "rows": sorted(json.dumps([_scalar(v) for v in r], ensure_ascii=False, sort_keys=True) for r in rows),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _scalar(v):
    if isinstance(v, float):
        return round(v, 6)
    return v


def _answer(catalog, profiles, logo_db, question: str):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    comp = DeterministicCompiler(profiles, {"n0": "411", "n1": "01"}, "sqlite",
                                 default_filters=default_filters_provider(catalog, TENANT, DS))
    _, out, cols, rows = _run(comp, catalog, r, logo_db, question)
    return fingerprint(cols, rows), rows


# Kontrollü veride bu çiftlerin sonuçları BİLİNİR ve farklıdır — fixture'daki değerler ayrıdır.
DIFFERENT = [
    ("toptan → perakende", "2026 toptan satış tutarı", "2026 perakende satış tutarı"),
    ("dönem değişimi", "2026 net ciro", "2025 net ciro"),
]

# Aynı soruyu iki ayrı biçimde sormak sonucu değiştirmemeli.
SAME = [
    ("eş anlamlı ölçü", "2026 net ciro", "2026 net ciro nedir?"),
]


@pytest.mark.parametrize("label,a,b", DIFFERENT, ids=[c[0] for c in DIFFERENT])
def test_a_changed_condition_changes_the_answer(catalog, profiles, logo_db, label, a, b):
    fa, rows_a = _answer(catalog, profiles, logo_db, a)
    fb, rows_b = _answer(catalog, profiles, logo_db, b)
    assert rows_a and rows_b, (label, rows_a, rows_b)
    assert fa != fb, f"{label}: koşul değişti ama sonuç aynı — koşul sorguya taşınmamış olabilir"


@pytest.mark.parametrize("label,a,b", SAME, ids=[c[0] for c in SAME])
def test_the_same_question_asked_twice_gives_the_same_answer(catalog, profiles, logo_db, label, a, b):
    fa, _ = _answer(catalog, profiles, logo_db, a)
    fb, _ = _answer(catalog, profiles, logo_db, b)
    assert fa == fb, f"{label}: aynı soru iki biçimde farklı sonuç verdi"


def test_a_negated_question_is_not_the_positive_one(catalog, profiles):
    """"satan" ile "satmayan" aynı plana çözülmemeli: olumsuzluk yutulursa cevap tersine döner."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    pos = r.resolve("en çok satan ürünler")
    neg = r.resolve("hiç satmayan ürünler")
    assert neg.shape == "ABSENCE" and pos.shape != "ABSENCE"
    assert [m["decision"] for m in neg.modifiers] == ["ABSENCE"]
    # olumlu tarafta ölçü çözülür; olumsuz tarafta ölçü uygulanmaz, yokluğu sorulur
    assert any(s.semantic_type == SemanticType.METRIC for s in pos.slots)
