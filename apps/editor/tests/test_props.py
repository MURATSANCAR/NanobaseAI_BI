"""Eşya sürekliliğinin saf parçaları (sentetik): sahne sınırı, gözlem birleştirme, A/B kuralı,
yargı akışı, ayar okuma. Model ve veritabanı yok. Çalıştır:

    python3 -m pytest apps/editor/tests/test_props.py
"""

from __future__ import annotations

import asyncio
import os
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

from editor.proofing import _continuity as C  # noqa: E402
from editor.proofing import props  # noqa: E402


def _page(no, *texts, role=None):
    p = {"page_no": no, "spans": [{"idx": i + 1, "text": t} for i, t in enumerate(texts)]}
    if role:
        p["page_role"] = role
    return p


def row(cid, page, value, source="IMAGE", quote=None, name="Ali"):
    return {"character_id": cid, "character_name": name, "page_no": page, "kind": "ESYA", "value": value,
            "source": source, "confidence": 1.0, "quote": quote,
            "bbox": [100, 100, 400, 800] if source == "IMAGE" else None,
            "evidence_id": f"ev-{cid}-{page}", "mention_id": f"m-{cid}-{page}" if source == "IMAGE" else None}


def state(cid, page, kind, st, item="çanta", quote="cümle", name="Ali"):
    return {"character_id": cid, "character_name": name, "item": item, "item_kind": kind, "state": st,
            "page": page, "idx": 1, "quote": quote}


# ------------------------------------------------------------ ayar/sahne
def test_setting_reads_env_then_default(monkeypatch):
    monkeypatch.delenv("EDITOR_PROPS_JUDGE_MIN", raising=False)
    assert C.setting("props_judge_min", 0.5) == 0.5
    monkeypatch.setenv("EDITOR_PROPS_JUDGE_MIN", "0.7")
    assert C.setting("props_judge_min", 0.5) == 0.7
    monkeypatch.setenv("EDITOR_X_FLAG", "0")
    assert C.setting("x_flag", True) is False
    monkeypatch.setenv("EDITOR_X_N", "3")
    assert C.setting("x_n", 1) == 3


def test_scene_breaks_and_scene_numbers():
    pages = [_page(1, "Ali sabah uyandı."), _page(2, "Bahçede oynadı."),
             _page(3, "Ertesi gün okula gitti."), _page(4, "Ders bitti."),
             _page(5, "Etkinlik", role="NON_STORY"), _page(6, "Sonra parka vardılar.")]
    br = C.scene_breaks(pages)
    assert set(br) == {3, 6} and br[3][0]["kind"] == "ZAMAN" and br[6][0]["kind"] == "MEKAN"
    sc = C.scenes(pages, br)
    assert sc[1] == sc[2] and sc[3] == sc[4] and sc[3] == sc[1] + 1 and sc[6] > sc[4]


def test_unreal_pages_only_when_no_real_event():
    evs = [{"page_from": 3, "page_to": 4, "modality": "MEMORY"}, {"page_from": 4, "page_to": 5, "modality": "REALIZED"},
           {"page_from": 8, "page_to": 8, "modality": "DREAM"}]
    assert C.unreal_pages(evs) == {3, 8}


# ------------------------------------------------------------- gözlemler
def test_observations_merge_ledger_and_states():
    obs = props.observations([row("c1", 3, "CANTA"), row("c1", 5, "YOK"), row("c1", 6, "BELIRSIZ")],
                             [state("c1", 4, "CANTA", "BIRAKTI")])
    assert [(o["page"], o["key"], o["state"], o["source"]) for o in obs] == \
        [(3, "CANTA", "YANINDA", "IMAGE"), (4, "CANTA", "BIRAKTI", "STATE"), (5, None, "YOK", "IMAGE")]
    assert props.item_key("DIGER", "Kırmızı Uçurtma") == "DIGER:kırmızı uçurtma"


# --------------------------------------------------------------- A kuralı
def test_rule_a_same_scene_item_vanishes_unless_dropped_or_scene_changes():
    scene_of = {1: 0, 2: 0, 3: 0, 4: 1}
    obs = props.observations([row("c1", 1, "CANTA"), row("c1", 2, "YOK")], [])
    c = props.candidates(obs, scene_of)
    assert len(c) == 1 and c[0]["rule"] == "A" and (c[0]["a"]["page"], c[0]["b"]["page"]) == (1, 2)
    assert c[0]["why"] == "aynı sahnede kayboluyor"
    # metin arada "bıraktı" diyorsa aday değil
    obs = props.observations([row("c1", 1, "CANTA"), row("c1", 3, "YOK")], [state("c1", 2, "CANTA", "BIRAKTI")])
    assert props.candidates(obs, scene_of) == []
    # sahne değiştiyse aday değil
    obs = props.observations([row("c1", 1, "CANTA"), row("c1", 4, "YOK")], [])
    assert props.candidates(obs, scene_of) == []
    # önce yok sonra var: "beliriyor"; başka karakter ve başka eşya (YOK değil) aday kurmaz
    obs = props.observations([row("c1", 1, "YOK"), row("c1", 2, "TOP"), row("c1", 4, "CANTA"),
                              row("c2", 3, "YOK", name="Veli")], [])
    c = props.candidates(obs, scene_of)
    assert len(c) == 1 and c[0]["why"] == "aynı sahnede beliriyor" and c[0]["b"]["page"] == 2


def test_rule_a_absence_needs_ledger_not_state_line():
    # metin başka bir eşya durumunu anlatıyor diye çanta "yok" sayılmaz
    obs = props.observations([row("c1", 1, "CANTA")], [state("c1", 2, "TOP", "YANINDA", item="top")])
    assert props.candidates(obs, {1: 0, 2: 0}) == []


# --------------------------------------------------------------- B kuralı
def test_rule_b_broken_then_intact_unless_repaired():
    scene_of = {p: p for p in range(1, 10)}          # her sayfa ayrı sahne: A kuralı susar
    obs = props.observations([row("c1", 6, "OYUNCAK")], [state("c1", 2, "OYUNCAK", "KIRILDI", item="oyuncak")])
    c = props.candidates(obs, scene_of)
    assert len(c) == 1 and c[0]["rule"] == "B" and (c[0]["a"]["page"], c[0]["b"]["page"]) == (2, 6)
    # arada tamir: aday yok
    obs = props.observations([row("c1", 6, "OYUNCAK")], [state("c1", 2, "OYUNCAK", "KIRILDI", item="oyuncak"),
                                                         state("c1", 4, "OYUNCAK", "TAMIR_EDILDI", item="oyuncak")])
    assert props.candidates(obs, scene_of) == []
    # kayboldu → buldu → yanında: buldu açıklamadır
    obs = props.observations([row("c1", 7, "TOP")], [state("c1", 2, "TOP", "KAYBOLDU", item="top"),
                                                     state("c1", 5, "TOP", "BULDU", item="top")])
    assert props.candidates(obs, scene_of) == []
    # DIGER türünde ad eşleşmeli
    obs = props.observations([], [state("c1", 2, "DIGER", "KIRILDI", item="uçurtma"),
                                  state("c1", 5, "DIGER", "YANINDA", item="Uçurtma"),
                                  state("c1", 6, "DIGER", "YANINDA", item="fener")])
    c = props.candidates(obs, scene_of)
    assert len(c) == 1 and c[0]["b"]["page"] == 5


# ------------------------------------------------------------------ yargı
def test_check_judges_both_orders_and_severity():
    class FakeLlm:
        def __init__(self):
            self.calls = []

        async def choose(self, alias, messages, choices, **kw):
            body = messages[0]["content"]
            self.calls.append(body)
            if "yepyeni bir oyuncak" in body:      # işaret, yargı sorusunun kendi metninde geçmemeli
                return {"C": 0.1, "U": 0.85, "B": 0.05}, 1
            return {"C": 0.9, "U": 0.05, "B": 0.05}, 1

    pages = [_page(1, "Ali çantasıyla okula gitti."), _page(2, "Ali sınıfa girdi."),
             _page(3, "Ertesi gün Ali'nin oyuncağı kırıldı."), _page(4, "Ali oyuncağıyla oynadı.")]
    rows = [row("c1", 1, "CANTA"), row("c1", 2, "YOK"), row("c1", 4, "OYUNCAK")]
    states = [state("c1", 3, "OYUNCAK", "KIRILDI", item="oyuncak", quote="Ali'nin oyuncağı kırıldı.")]
    os.environ.pop("EDITOR_PROPS_JUDGE_MIN", None)
    llm = FakeLlm()
    findings, stats = asyncio.run(props.check(rows, states, pages, llm))
    assert stats["candidates"] == 2 and len(llm.calls) == 4
    assert all("[s1 p1]" in b and "Gözlem 1" in b for b in llm.calls)
    by_rule = {f["details"]["rule"]: f for f in findings}
    assert by_rule["A"]["severity"] == "WARN" and by_rule["A"]["bbox"] == [100, 100, 400, 800] and by_rule["A"]["page"] == 2
    assert by_rule["B"]["severity"] == "ERROR" and by_rule["B"]["details"]["a"]["quote"] == "Ali'nin oyuncağı kırıldı."
    assert by_rule["B"]["details"]["b"]["mention_id"] == "m-c1-4"
    # metin değişimi açıklıyorsa (işaret cümlesi) yargı U: bulgu yok
    pages[3] = _page(4, "Babası ona yepyeni bir oyuncak aldı; Ali oyuncağıyla oynadı.")
    findings, stats = asyncio.run(props.check(rows, states, pages, FakeLlm()))
    assert stats["confirmed"] == 0 and all(d["p"] == 0.1 for d in stats["candidates_detail"])


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
