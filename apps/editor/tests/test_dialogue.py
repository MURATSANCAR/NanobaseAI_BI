"""Diyalog atfı ve sesin saf parçaları (sentetik): katılımcı kümesi, atıf adayı, hitap sınıfı,
hitap adayı, yargı akışı. Model ve veritabanı yok. Çalıştır:

    python3 -m pytest apps/editor/tests/test_dialogue.py
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

from editor.proofing import dialogue as D  # noqa: E402

CHARS = [{"id": "c1", "canonical_name": "Ali", "aliases": []}, {"id": "c2", "canonical_name": "Ayşe", "aliases": ["Ayşecik"]},
         {"id": "c3", "canonical_name": "Dede", "aliases": []}]
IDX = {"ali": "c1", "ayşe": "c2", "ayşecik": "c2", "dede": "c3"}
NAMES_OF = {"c2": ["Ayşe", "Ayşecik"], "c1": ["Ali"], "c3": ["Dede"]}


def _page(no, *texts):
    return {"page_no": no, "spans": [{"idx": i + 1, "text": t} for i, t in enumerate(texts)]}


def line(page, speaker, quote, addressee=None, term="", idx=1):
    names = {"c1": "Ali", "c2": "Ayşe", "c3": "Dede"}
    return {"speaker": names.get(speaker, ""), "speaker_id": speaker, "speaker_name": names.get(speaker, ""),
            "addressee": names.get(addressee, ""), "addressee_id": addressee, "addressee_name": names.get(addressee, ""),
            "address_term": term, "page": page, "idx": idx, "quote": quote}


# ------------------------------------------------------------- katılımcı
def test_presence_from_event_actors_then_participants_then_mentions():
    evs = [{"page_from": 2, "page_to": 3, "modality": "REALIZED", "character_ids": ["c1"], "participants": ["Ali", "Ayşe"]},
           {"page_from": 5, "page_to": 5, "modality": "REALIZED", "character_ids": [], "participants": ["Ayşe", "Bilinmeyen"]}]
    pres = D.presence(evs, [{"page_no": 3, "character_id": "c3"}], IDX)
    assert pres == {2: {"c1"}, 3: {"c1", "c3"}, 5: {"c2"}}       # event_actor varsa ad listesi kullanılmaz
    assert D.present_near(pres, 4, window=1) == {"c1", "c3", "c2"}
    assert D.present_near(pres, 9, window=1) == set()


def test_attribution_candidate_needs_presence_data_and_absent_speaker():
    pres = {2: {"c1"}, 3: {"c1"}}
    lines = [line(2, "c1", "Merhaba!"), line(3, "c2", "Ben de geldim."), line(8, "c3", "Kimse yok."), line(3, None, "…")]
    out = D.attribution_candidates(lines, pres)
    # s.3 Ayşe: sahnede (±1) yalnız Ali → aday; s.8: veri yok → aday değil; konuşanı çözülmemiş → aday değil
    assert [(c["line"]["page"], c["line"]["speaker_id"], c["present"]) for c in out] == [(3, "c2", ["c1"])]


# ------------------------------------------------------------------ hitap
def test_term_category_is_closed_and_name_aware():
    assert D.term_category("abla", NAMES_OF["c2"]) == "AKRABALIK"
    assert D.term_category("Ablacığım", NAMES_OF["c2"]) == "AKRABALIK"
    assert D.term_category("Ayşe", NAMES_OF["c2"]) == "AD" and D.term_category("Ayşecik", NAMES_OF["c2"]) == "AD"
    assert D.term_category("hocam", NAMES_OF["c1"]) == "SAYGI" and D.term_category("Ali Bey", NAMES_OF["c3"]) == "SAYGI"
    assert D.term_category("kaptan", NAMES_OF["c1"]) == "SAYGI" and D.term_category("tombiş", NAMES_OF["c1"]) == "LAKAP"
    assert D.term_category("", NAMES_OF["c1"]) is None
    # adı "Dede" olan karaktere "dede" demek AD sayılır: sınıf değişmez, aday çıkmaz
    assert D.term_category("dede", NAMES_OF["c3"]) == "AD"


def test_address_candidates_need_min_uses_and_dominant_class():
    uses = [line(2, "c1", "Abla, bak!", "c2", "abla"), line(4, "c1", "Abla gel.", "c2", "Abla"),
            line(6, "c1", "Ablacığım!", "c2", "ablacığım"), line(9, "c1", "Ayşe, dur!", "c2", "Ayşe")]
    out = D.address_candidates(uses, NAMES_OF)
    assert len(out) == 1 and out[0]["dominant"] == "AKRABALIK" and out[0]["b"]["page"] == 9 and out[0]["b"]["category"] == "AD"
    assert out[0]["a"]["page"] == 2 and out[0]["uses"] == 4 and abs(out[0]["share"] - 0.75) < 1e-9
    # üçten az kullanım: aday yok; baskın sınıf yok (2/4): aday yok
    assert D.address_candidates(uses[:2], NAMES_OF) == []
    mixed = uses[:2] + [line(6, "c1", "Ayşe!", "c2", "Ayşe"), line(9, "c1", "Ayşe, dur!", "c2", "Ayşe")]
    assert D.address_candidates(mixed, NAMES_OF) == []
    # başka konuşan/hitap edilen çifti ayrı sayılır
    other = uses + [line(3, "c3", "Ayşe kızım.", "c2", "kızım")]
    assert len(D.address_candidates(other, NAMES_OF)) == 1


# ----------------------------------------------------------------- yargı
def test_check_two_questions_per_attribution_and_two_orders_per_address():
    class FakeLlm:
        def __init__(self):
            self.calls = []

        async def choose(self, alias, messages, choices, **kw):
            body = messages[0]["content"]
            self.calls.append((body, tuple(choices)))
            remote = "telsizden" in body             # işaret: uzaktan konuşma metinde (yargı sorusunda geçmeyen kelime)
            if "V" in choices and remote:
                return {"V": 0.9, "Y": 0.05, "B": 0.05}, 1
            if "E" in choices and remote:
                return {"E": 0.9, "H": 0.05, "B": 0.05}, 1
            if "V" in choices:
                return {"V": 0.1, "Y": 0.85, "B": 0.05}, 1
            if "E" in choices:
                return {"E": 0.1, "H": 0.85, "B": 0.05}, 1
            return {"C": 0.7, "U": 0.2, "B": 0.1}, 1

    pages = [_page(2, "Ali: “Abla, bak!”"), _page(3, "Ayşe: “Ben de geldim.”"), _page(4, "Ali: “Abla gel.”"),
             _page(6, "Ali: “Ablacığım!”"), _page(9, "Ali: “Ayşe, dur!”")]
    evs = [{"page_from": 2, "page_to": 4, "modality": "REALIZED", "character_ids": ["c1"], "participants": ["Ali"],
            "summary": "Ali bahçede oynar"}]
    lines = [line(2, "c1", "Abla, bak!", "c2", "abla"), line(3, "c2", "Ben de geldim."), line(4, "c1", "Abla gel.", "c2", "Abla"),
             line(6, "c1", "Ablacığım!", "c2", "ablacığım"), line(9, "c1", "Ayşe, dur!", "c2", "Ayşe")]
    llm = FakeLlm()
    findings, stats = asyncio.run(D.check(lines, pages, llm, evs, [], CHARS))
    assert stats["candidates_attribution"] == 1 and stats["candidates_address"] == 1 and len(llm.calls) == 4
    assert {c[1] for c in llm.calls} == {("V", "Y", "B"), ("E", "H", "B"), ("C", "U", "B")}
    assert all("[s2 p1]" in c[0] for c in llm.calls)
    rules = {f["details"]["rule"]: f for f in findings}
    assert rules["A"]["severity"] == "ERROR" and rules["A"]["page"] == 3 and rules["A"]["quote"] == "Ben de geldim."
    assert rules["A"]["details"]["b"]["present"] == ["Ali"] and rules["A"]["details"]["b"]["events"][0]["summary"] == "Ali bahçede oynar"
    assert rules["B"]["severity"] == "WARN" and rules["B"]["page"] == 9 and rules["B"]["details"]["a"]["address_term"] == "abla"
    # metin uzaktan konuşmayı açıklıyorsa (işaret) atıf bulgusu düşer
    pages[1] = _page(3, "Ayşe telsizden seslendi: “Ben de geldim.”")
    findings, stats = asyncio.run(D.check(lines, pages, FakeLlm(), evs, [], CHARS))
    assert stats["confirmed_attribution"] == 0 and stats["confirmed_address"] == 1


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
