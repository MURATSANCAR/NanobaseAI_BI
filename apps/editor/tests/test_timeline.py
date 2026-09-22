"""Zaman çizelgesinin saf parçaları (sentetik): kalıp çıkarma, sıra denetimi, anı/rüya sayfası
dışlama, yargı akışı. Model ve veritabanı yok. Çalıştır:

    python3 -m pytest apps/editor/tests/test_timeline.py
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

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

from editor.proofing import timeline as T  # noqa: E402


def _page(no, *texts):
    return {"page_no": no, "spans": [{"idx": i + 1, "text": t} for i, t in enumerate(texts)]}


def _kinds(exprs):
    return [(e["page"], e["kind"], e["value"]) for e in exprs]


# ---------------------------------------------------------------- çıkarma
def test_extract_closed_patterns_in_page_order():
    pages = [_page(2, "Ertesi sabah Ali erkenden kalktı.", "Öğlen yemek yediler."),
             _page(1, "Akşam olunca eve döndüler. Her sabah koşardı ama."),
             _page(3, "Üç gün sonra kış geldi. Ali on yaşındaydı.")]
    ex = T.extract(pages)
    assert _kinds(ex) == [(1, "GUN_VAKTI", "AKSAM"), (2, "GUN_GECISI", 1), (2, "GUN_VAKTI", "OGLE"),
                          (3, "GUN_GECISI", 3), (3, "MEVSIM", "KIS"), (3, "YAS", 10)]
    assert ex[1]["tod"] == "SABAH" and ex[1]["quote"] == "Ertesi sabah Ali erkenden kalktı."
    assert ex[5]["subject"] == "ali"
    # "her sabah" genel, "günaydın"/"iyi geceler" selam: alınmaz; "yazı" mevsim değil, "yaz geldi" mevsim
    ex = T.extract([_page(1, "Günaydın dedi. İyi geceler! Yazı yazdı. Yaz geldi, iki hafta sonra bahar bitmişti.")])
    assert _kinds(ex) == [(1, "MEVSIM", "YAZ"), (1, "GUN_GECISI", 14), (1, "MEVSIM", "ILKBAHAR")]


def test_extract_age_year_and_birth():
    ex = T.extract([_page(1, "Ayşe 2015 yılında doğdu.", "2022 yılında Ayşe yedi yaşına bastı.")])
    assert [(e["kind"], e["value"], e.get("year")) for e in ex] == [("DOGUM", 2015, None), ("YAS", 7, 2022)]
    idx = {"ayşe": "c9"}
    assert all(e["subject"] == "c9" for e in T.extract([_page(1, "Ayşe 2015 yılında doğdu.")], idx))


# ------------------------------------------------------------------ sıra
def _e(page, kind, value, **kw):
    return {"page": page, "idx": 1, "pos": 0, "kind": kind, "value": value, "quote": f"{kind} {value} s{page}", **kw}


def test_order_time_of_day_backwards_is_candidate_except_morning():
    # akşam → öğle aynı akışta: aday; gece → sabah örtük yeni gün: aday değil
    c = T.check_order([_e(1, "GUN_VAKTI", "AKSAM"), _e(2, "GUN_VAKTI", "OGLE")])
    assert len(c) == 1 and c[0]["kind"] == "GUN_VAKTI" and (c[0]["a"]["page"], c[0]["b"]["page"]) == (1, 2)
    assert T.check_order([_e(1, "GUN_VAKTI", "GECE"), _e(2, "GUN_VAKTI", "SABAH"), _e(3, "GUN_VAKTI", "AKSAM")]) == []
    # gün geçişi vakti sıfırlar: "ertesi gün" sonra öğle, akşam'dan geri değil
    assert T.check_order([_e(1, "GUN_VAKTI", "AKSAM"), _e(2, "GUN_GECISI", 1, tod=None), _e(2, "GUN_VAKTI", "OGLE")]) == []
    # "ertesi sabah" vakti SABAH yapar; sonra akşam sorun değil, sonra öğle aday
    c = T.check_order([_e(1, "GUN_GECISI", 1, tod="SABAH"), _e(2, "GUN_VAKTI", "AKSAM"), _e(3, "GUN_VAKTI", "OGLE")])
    assert len(c) == 1 and c[0]["a"]["page"] == 2


def test_order_season_age_and_birth_year():
    assert T.check_order([_e(1, "MEVSIM", "KIS"), _e(3, "MEVSIM", "ILKBAHAR")]) == []       # ileri (döngü)
    c = T.check_order([_e(1, "MEVSIM", "YAZ"), _e(3, "MEVSIM", "ILKBAHAR")])
    assert len(c) == 1 and c[0]["kind"] == "MEVSIM"
    c = T.check_order([_e(1, "YAS", 9, subject="ali"), _e(4, "YAS", 7, subject="ali"), _e(5, "YAS", 7, subject="veli")])
    assert len(c) == 1 and c[0]["kind"] == "YAS" and c[0]["why"] == "yaş 9 sonra 7"
    c = T.check_order([_e(1, "DOGUM", 2015, subject="ayşe"), _e(2, "YAS", 7, subject="ayşe", year=2022),
                       _e(3, "YAS", 9, subject="ayşe", year=2026)])
    assert len(c) == 1 and c[0]["kind"] == "TARIH" and c[0]["b"]["page"] == 3


def test_unreal_pages_are_skipped():
    ex = [_e(1, "GUN_VAKTI", "AKSAM"), _e(2, "GUN_VAKTI", "OGLE"), _e(3, "GUN_VAKTI", "GECE")]
    assert len(T.check_order(ex)) == 1
    assert T.check_order(ex, skip_pages={2}) == []


# ----------------------------------------------------------------- yargı
def test_check_judges_both_orders_and_severity():
    class FakeLlm:
        def __init__(self):
            self.calls = []

        async def choose(self, alias, messages, choices, **kw):
            self.calls.append(messages[0]["content"])
            if "hatırladı" in messages[0]["content"]:
                return {"C": 0.05, "U": 0.9, "B": 0.05}, 1
            return {"C": 0.85, "U": 0.1, "B": 0.05}, 1

    pages = [_page(1, "Akşam sofraya oturdular."), _page(2, "Öğlen okulda top oynadı."),
             _page(3, "Ali dokuz yaşındaydı."), _page(4, "Ali yedi yaşındaydı.")]
    llm = FakeLlm()
    findings, stats = asyncio.run(T.check(pages, llm))
    assert stats["candidates"] == 2 and len(llm.calls) == 4
    assert all("[s1 p1]" in b and "İfade 1" in b and "İfade 2" in b for b in llm.calls)
    by_kind = {f["details"]["kind"]: f for f in findings}
    assert by_kind["GUN_VAKTI"]["severity"] == "WARN" and by_kind["GUN_VAKTI"]["page"] == 2
    assert by_kind["YAS"]["severity"] == "ERROR" and by_kind["YAS"]["details"]["a"]["quote"] == "Ali dokuz yaşındaydı."
    # sayfa 2 yalnız anı olayı taşıyorsa sıraya girmez: tek aday
    evs = [{"page_from": 2, "page_to": 2, "modality": "MEMORY"}]
    findings, stats = asyncio.run(T.check(pages, FakeLlm(), evs))
    assert stats["candidates"] == 1 and stats["unreal_pages"] == [2]
    # metin geri dönüşü açıklıyorsa yargı U: bulgu yok
    pages[1] = _page(2, "Öğlen okulda top oynadığını hatırladı.")
    findings, stats = asyncio.run(T.check(pages, FakeLlm()))
    assert stats["confirmed"] == 0 and findings == []


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
