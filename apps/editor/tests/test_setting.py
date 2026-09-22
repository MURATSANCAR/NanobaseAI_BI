"""Mekân tutarlılığının saf parçaları (sentetik): metin–metin çift çıkarma, görsel aspect seçimi,
resim kararı, yargı akışı (metin ve resim yolu). Model ve veritabanı yok. Çalıştır:

    python3 -m pytest apps/editor/tests/test_setting.py
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

from editor.proofing import setting as S  # noqa: E402


def _page(no, *texts):
    return {"page_no": no, "spans": [{"idx": i + 1, "text": t} for i, t in enumerate(texts)]}


def fact(page, place, aspect, value, quote="alıntı", idx=1):
    return {"place": place, "aspect": aspect, "value": value, "page": page, "idx": idx, "quote": quote}


# ------------------------------------------------------------- çıkarma
def test_pair_needs_same_place_same_aspect_different_value_two_pages():
    facts = [fact(3, "Ali'nin odası", "PENCERE_YONU", "bahçeye bakıyor"),
             fact(9, "Ali'nin Odası", "PENCERE_YONU", "sokağa bakıyor"),
             fact(9, "Ali'nin odası", "PENCERE_YONU", "sokağa bakıyor."),      # aynı değer (noktalama): çift değil
             fact(3, "Ali'nin odası", "KAT", "ikinci kat"), fact(5, "mutfak", "KAT", "zemin kat"),  # başka mekân
             fact(3, "ev", "IC_DIS", "IC"), fact(3, "ev", "IC_DIS", "DIS")]                        # aynı sayfa
    out = S.pair_facts(facts)
    assert len(out) == 1 and out[0]["aspect"] == "PENCERE_YONU" and (out[0]["a"]["page"], out[0]["b"]["page"]) == (3, 9)
    # görsel aspect'te küme dışı değer çift kurmaz
    assert S.pair_facts([fact(1, "ev", "ISIK", "loş"), fact(2, "ev", "ISIK", "GECE")]) == []
    assert S.valid_visual("ISIK", "gündüz") == "GUNDUZ" and S.valid_visual("HAVA", "sisli") is None


def test_visual_facts_only_measurable_aspects_on_illustrated_pages():
    facts = [fact(2, "orman", "HAVA", "yağmurlu"), fact(2, "orman", "HAVA", "YAGMURLU", idx=3),
             fact(2, "orman", "DUZEN", "solda kulübe"), fact(4, "ev", "IC_DIS", "IC"), fact(5, "ev", "ISIK", "GECE")]
    out = S.visual_facts(facts, illustrated={2, 5})
    assert [(f["page"], f["aspect"], f["value"]) for f in out] == [(2, "HAVA", "YAGMURLU"), (5, "ISIK", "GECE")]


def test_image_verdict_reads_the_opposing_mass():
    v = S.image_verdict("IC_DIS", "IC", {"I": 0.15, "D": 0.8, "B": 0.05})
    assert v["seen"] == "DIS" and abs(v["p_against"] - 0.8) < 1e-9 and abs(v["p_agree"] - 0.15) < 1e-9
    v = S.image_verdict("HAVA", "GUNESLI", {"G": 0.2, "Y": 0.3, "K": 0.4, "B": 0.1})
    assert v["seen"] == "KARLI" and abs(v["p_against"] - 0.4) < 1e-9
    assert S.image_verdict("ISIK", "GECE", {"G": 0.0, "K": 0.2, "B": 0.8})["seen"] == "GUNDUZ"


# ----------------------------------------------------------------- yargı
def test_check_text_pairs_and_image_questions():
    class FakeLlm:
        def __init__(self):
            self.calls = []

        async def choose(self, alias, messages, choices, **kw):
            c = messages[0]["content"]
            self.calls.append((alias, c if isinstance(c, str) else c[1]["text"], choices))
            if isinstance(c, list):                      # resim sorusu
                return ({"I": 0.1, "D": 0.85, "B": 0.05} if "İÇERİDE" in c[1]["text"] else {"G": 0.9, "K": 0.05, "B": 0.05}), 1
            if "yeni eve geçtiler" in c:          # işaret, yargı sorusunun kendi metninde geçmemeli
                return {"C": 0.1, "U": 0.85, "B": 0.05}, 1
            return {"C": 0.8, "U": 0.1, "B": 0.1}, 1

    pages = [_page(2, "Odanın penceresi bahçeye bakıyordu."), _page(5, "Ali odasının penceresinden sokağı izledi."),
             _page(7, "Odada oturuyorlardı."), _page(8, "Gece olmuştu.")]
    facts = [fact(2, "Ali'nin odası", "PENCERE_YONU", "bahçeye bakıyor", "Odanın penceresi bahçeye bakıyordu."),
             fact(5, "Ali'nin odası", "PENCERE_YONU", "sokağa bakıyor", "Ali odasının penceresinden sokağı izledi."),
             fact(7, "oda", "IC_DIS", "IC", "Odada oturuyorlardı."), fact(8, "dışarısı", "ISIK", "GECE", "Gece olmuştu.")]
    llm = FakeLlm()
    findings, stats = asyncio.run(S.check(facts, pages, llm, illustrated={7, 8}, png_of=lambda p: b"png"))
    assert stats["candidates"] == 1 and stats["visual_facts"] == 2 and len(llm.calls) == 4
    directors = [c for c in llm.calls if c[0] == "book-director"]
    assert len(directors) == 2 and all("[s2 p1]" in c[1] and "Bilgi 1" in c[1] for c in directors)
    visions = [c for c in llm.calls if c[0] == "book-vision-deep"]
    assert {tuple(c[2]) for c in visions} == {("I", "D", "B"), ("G", "K", "B")}
    kinds = {f["details"]["kind"]: f for f in findings}
    assert kinds["TEXT_TEXT"]["page"] == 5 and kinds["TEXT_TEXT"]["details"]["a"]["quote"] == "Odanın penceresi bahçeye bakıyordu."
    # içeride diyen metin, dışarıda gösteren resim (0.85 ≥ 0.7): bulgu; gece/gündüz (0.9 gündüz): bulgu
    img = [f for f in findings if f["details"]["kind"] == "TEXT_IMAGE"]
    assert {(f["page"], f["details"]["b"]["seen"]) for f in img} == {(7, "DIS"), (8, "GUNDUZ")}
    assert all(f["bbox"] == [0, 0, 1000, 1000] and f["quote"] for f in img)
    # png_of yoksa resim yolu kapalı; metin açıklıyorsa (işaret) yargı U
    pages[1] = _page(5, "O yıl yeni eve geçtiler; Ali odasının penceresinden sokağı izledi.")
    findings, stats = asyncio.run(S.check(facts, pages, FakeLlm()))
    assert stats["visual_facts"] == 0 and stats["confirmed_text"] == 0 and findings == []


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
