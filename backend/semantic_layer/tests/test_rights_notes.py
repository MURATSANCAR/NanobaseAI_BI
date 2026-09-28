"""Ortak hak açıklaması sınıflaması (M54 telif + M36 dijital, `rights_notes`): tek soru, tek tablo; bir modülün sorduğu
ya da insanın onayladığı not öbür modülde yeniden sorulmaz; metin değişince ikisi için de yeniden sorulur; HTML/boşluk
farkı aynı not sayılır; dijital okuma ortak sınıftan türetilir.

Veriler yapaydır; model yerine sahte `choose`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from semantic_bridge import contracts as C
from semantic_bridge import dijital as D
from semantic_bridge import rights_notes as RN
from semantic_bridge import royalty as RY
from semantic_layer.store.catalog_store import open_store

T = "t1"
GID = "AAAAAAAA-1111-1111-1111-111111111111"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for m in (C, RY, D):
        m._ready.discard(id(e))
    D.ensure(e)
    RY.ensure(e)
    return e


class Llm:
    def __init__(self, label="Bölge kısıtı", p=0.92, margin=0.8, fail=False):
        self.calls, self.label, self.p, self.margin, self.fail = [], label, p, margin, fail

    def choose(self, prompt, choices):
        self.calls.append((prompt, list(choices)))
        if self.fail:
            raise RuntimeError("model yok")
        return SimpleNamespace(choice=self.label, probability=self.p, margin=self.margin, method="logprobs", probs=None)


def _seed_title(engine, note, cid=GID):
    D.write_titles(engine, T, [{
        "kitap_id": "K1", "ad": "Kitap", "tip": 1, "hak_notu_var": True,
        "sozlesme_json": D._dump([{"id": cid.upper(), "ad": "S-1", "taraflar": ["Yazar"], "yururlukte": True, "not": note}]),
    }])


def test_royalty_classification_is_reused_by_digital_without_asking_again(engine):
    rows = [{"id": "{" + GID.lower() + "}", "no": "S-1", "kitap": "Kitap", "metin": "<p>Yalnız&nbsp;Türkiye'de   satılabilir</p>"}]
    llm = Llm()
    todo = RN.pending(engine, T, rows)
    assert [x["key"] for x in todo] == [GID.lower()]
    assert RN.classify(engine, T, todo, llm)["okunan"] == 1
    # M36 aynı notu CRM'den temizlenmiş biçimde okur → aynı metin, yeniden sorulmaz.
    _seed_title(engine, D.seo_crm.clean(rows[0]["metin"]))
    llm2 = Llm()
    assert D.read_notes(engine, T, llm2, 60)["okunan"] == 0 and llm2.calls == []
    rd = D.note_reads(engine, T)[GID.upper()]
    assert rd["sonuc"] == "kisitliyor" and rd["sinif"] == "bolge"
    # Telif yeniden koşunca da sormaz (tek tablo).
    assert RN.pending(engine, T, rows) == []


def test_digital_first_then_royalty_reads_same_row(engine):
    _seed_title(engine, "Sesli kitap hakkı ayrıca onaya bağlıdır.")
    llm = Llm(label="Onay şartı")
    assert D.read_notes(engine, T, llm, 60)["okunan"] == 1
    assert llm.calls[0][1] == list(RY.NOTE_CLASSES.values())
    items = RY.notes(engine, T)["items"]
    assert len(items) == 1 and items[0]["class"] == "onay" and items[0]["status"] == "oneri" and items[0]["no"] == "S-1"
    assert RN.pending(engine, T, [{"id": GID, "metin": "Sesli kitap hakkı ayrıca onaya bağlıdır."}]) == []


def test_changed_text_is_asked_again_and_clears_approval(engine):
    _seed_title(engine, "Yalnız basılı.")
    D.read_notes(engine, T, Llm(label="Format kısıtı"), 60)
    n = RY.notes(engine, T)["items"][0]
    RY.approve_note(engine, T, "telif", n["id"], {"class": "diger"})
    assert D.note_reads(engine, T)[GID.upper()]["sonuc"] == "kisitlamiyor"      # insan onayı geçerli
    _seed_title(engine, "Yalnız basılı; e-kitap yasak.")
    llm = Llm(label="Format kısıtı")
    assert D.read_notes(engine, T, llm, 60)["okunan"] == 1
    rd = D.note_reads(engine, T)[GID.upper()]
    assert rd["sonuc"] == "kisitliyor" and rd["durum"] == "oneri"


def test_digital_effect_mapping_never_silently_clears():
    assert RN.digital_effect("bolge", "oneri") == "kisitliyor"
    assert RN.digital_effect("format", "onayli") == "kisitliyor"
    assert RN.digital_effect("diger", "oneri") == "kisitlamiyor"
    assert RN.digital_effect("ucret", "oneri") == "belirsiz"
    assert RN.digital_effect("diger", "incele") == "belirsiz"                     # eşik altı
    assert RN.digital_effect(None, "incele") is None


def test_low_probability_goes_to_review(engine):
    _seed_title(engine, "Belirsiz bir madde.")
    D.read_notes(engine, T, Llm(label="Diğer", p=0.5, margin=0.1), 60)
    assert RY.notes(engine, T)["items"][0]["status"] == "incele"
    assert D.note_reads(engine, T)[GID.upper()]["sonuc"] == "belirsiz"


def test_budget_and_errors_leave_the_rest_for_next_run(engine):
    rows = [{"id": f"{i:08d}-0000-0000-0000-000000000000", "metin": f"Not {i}"} for i in range(3)]
    todo = RN.pending(engine, T, rows)
    assert RN.classify(engine, T, todo, Llm(), budget_sec=-1) == {"okunan": 0, "kalan": 3, "hata": 0}
    seen = []
    out = RN.classify(engine, T, todo, Llm(fail=True), progress=seen.append)
    assert out == {"okunan": 0, "kalan": 3, "hata": 3} and seen == [False, False, False]
    assert RN.classify(engine, T, todo, Llm(fail=True), stop_on_error=True)["hata"] == 1
    assert len(RN.pending(engine, T, rows)) == 3


def test_expired_contract_notes_are_not_sent(engine):
    D.write_titles(engine, T, [{
        "kitap_id": "K1", "ad": "Kitap", "tip": 1, "hak_notu_var": True,
        "sozlesme_json": D._dump([{"id": GID, "ad": "S-1", "yururlukte": False, "not": "Eski not"}]),
    }])
    llm = Llm()
    assert D.read_notes(engine, T, llm, 60)["okunan"] == 0 and llm.calls == []
