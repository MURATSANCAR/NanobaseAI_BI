"""Yapılandırılmış hak haritası (öneri 18, `rights_map`): her alan hak açıklamasından birebir alıntıyla; alıntısız ya da
alıntısı metinde olmayan değer düşer; biçim ve münhasırlık kapalı kümeden ve alıntıdan kuralla; tarih modelden değil
alıntıdan; ortak not tablosunun üstünde (metin değişince yeniden çıkarılır, onay düşer); M36 aynı haritayı okur.

Veriler yapaydır; model yerine sahte `chat`.
"""

from __future__ import annotations

import json

import pytest

from semantic_bridge import access as A
from semantic_bridge import contracts as C
from semantic_bridge import dijital as D
from semantic_bridge import rights_map as M
from semantic_bridge import rights_notes as RN
from semantic_bridge import royalty as RY
from semantic_layer.store.catalog_store import open_store

T = "t1"
GID = "AAAAAAAA-1111-1111-1111-111111111111"
TEXT = ("Eserin Türkçe dilinde basılı ve e-kitap olarak yayın hakkı münhasır değildir. "
        "Sözleşme 31.12.2030 tarihine kadar geçerlidir. İngilizce'ye çeviri hakkı Almanya ve Avusturya için verilmiştir.")


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for m in (C, RY, D, M):
        m._ready.discard(id(e))
    D.ensure(e)
    RY.ensure(e)
    M.ensure(e)
    return e


class Chat:
    def __init__(self, payload=None, fail=False):
        self.payload, self.fail, self.calls = payload, fail, []

    def chat(self, messages, **kw):
        self.calls.append(messages)
        if self.fail:
            raise RuntimeError("model yok")
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)


def _vals(fields, key):
    v = fields[key]
    return [x["deger"] for x in v] if isinstance(v, list) else (v or {}).get("deger")


def test_rule_extraction_quotes_are_sentences_of_the_text():
    f = M.rule_extract(TEXT)
    assert set(_vals(f, "format")) == {"basili", "e-kitap", "ceviri"}
    assert set(_vals(f, "dil")) == {"Türkçe", "İngilizce"}
    assert _vals(f, "munhasirlik") == "munhasir-degil"          # olumsuzluk kuraldan
    assert f["bitis"]["tarih"] == "2030-12-31"
    tf = M.f(TEXT)
    for k in M.FIELDS:
        for x in (f[k] if isinstance(f[k], list) else [f[k]] if f[k] else []):
            assert M.f(x["alinti"]) in tf and x["kaynak"] == "kural"
    assert f["ulke"] == []                                       # kural ülke uydurmaz


def test_model_values_without_verbatim_quote_are_dropped():
    data = {"ulke": [{"deger": "Almanya", "alinti": "Almanya ve Avusturya için verilmiştir"},
                     {"deger": "Fransa", "alinti": "Fransa için verilmiştir"},                  # metinde yok
                     {"deger": "İsviçre", "alinti": "Almanya ve Avusturya için verilmiştir"}],  # değer alıntıda yok
            "format": [{"deger": "Sesli kitap", "alinti": "Eserin Türkçe dilinde basılı"}],      # alıntıda sesli yok
            "bitis": {"deger": "31.12.2031", "alinti": "Sözleşme 31.12.2030 tarihine kadar geçerlidir"},  # sayı yok
            "munhasirlik": {"deger": "münhasır", "alinti": "yayın hakkı münhasır değildir"}}
    out, dropped = M.validate_model(data, TEXT)
    assert _vals(out, "ulke") == ["Almanya"]
    assert out["format"] == [] and out["bitis"] is None
    assert _vals(out, "munhasirlik") == "munhasir-degil"          # değer modelden değil alıntıdan
    assert dropped == 4


def test_extract_merges_rule_and_model_and_labels_source():
    llm = Chat({"ulke": [{"deger": "Avusturya", "alinti": "Almanya ve Avusturya için"}], "dil": [], "format": []})
    res = M.extract(TEXT, llm)
    assert res["kaynak"] == "zeki" and _vals(res["alanlar"], "ulke") == ["Avusturya"]
    assert "Türkçe" in _vals(res["alanlar"], "dil")               # kural sonucu korunur
    assert M.extract(TEXT, Chat(fail=True))["kaynak"] == "kural"
    assert M.extract(TEXT, None)["neden"] == "model-yok"
    assert M.extract(TEXT, Chat("anlamsız cevap"))["neden"] == "json-yok"


def test_personal_data_is_masked_before_the_model():
    llm = Chat({})
    M.extract("Onay için yazar@ornek.com adresine ve 0532 123 45 67 numarasına başvurulur.", llm)
    sent = llm.calls[0][1]["content"]
    assert "yazar@ornek.com" not in sent and "0532" not in sent


def _note(engine, text=TEXT, key=GID):
    rows = [{"id": key, "no": "S-1", "kitap": "Kitap", "metin": text}]
    todo = RN.pending(engine, T, rows)

    class Choose:
        def choose(self, prompt, labels):
            from types import SimpleNamespace
            return SimpleNamespace(choice="Format kısıtı", probability=0.9, margin=0.8, method="logprobs")
    RN.classify(engine, T, todo, Choose())


def test_pending_follows_shared_notes_and_text_change_drops_approval(engine):
    _note(engine)
    todo = M.pending(engine, T)
    assert [x["key"] for x in todo] == [GID.lower()]
    assert M.run(engine, T, todo, None)["cikarilan"] == 1
    assert M.pending(engine, T) == []                             # aynı metin yeniden çıkarılmaz
    m = M.for_keys(engine, T, [GID])[GID.lower()]
    assert m["status"] == "oneri" and m["source"] == "kural"
    done = M.decide(engine, T, "telif", m["id"], {"action": "onayla"})
    assert done["status"] == "onayli" and done["approvedBy"] == "telif"
    # Not listesi haritayı aynı metin özetiyle eşler
    n = RY.notes(engine, T)["items"][0]
    assert n["textHash"] == done["hash"]
    # metin değişince yeniden çıkarılır, onay düşer; eski harita yeni metinle gösterilmez
    assert M.for_text(engine, T, GID, TEXT)["id"] == m["id"]
    assert M.for_text(engine, T, GID, TEXT + " Ek madde.") is None
    _note(engine, TEXT + " Ek madde.")
    assert len(M.pending(engine, T)) == 1
    M.run(engine, T, M.pending(engine, T), None)
    assert M.for_keys(engine, T, [GID])[GID.lower()]["status"] == "oneri"


def test_human_edit_is_validated_and_marked(engine):
    _note(engine)
    M.run(engine, T, M.pending(engine, T), None)
    m = M.for_keys(engine, T, [GID])[GID.lower()]
    fields = dict(m["fields"])
    fields["format"] = [x for x in fields["format"] if x["deger"] != "ceviri"]
    out = M.decide(engine, T, "telif", m["id"], {"action": "onayla", "fields": fields})
    assert out["source"] == "insan" and {x["deger"] for x in out["fields"]["format"]} == {"basili", "e-kitap"}
    with pytest.raises(RY.RoyaltyError):
        M.decide(engine, T, "telif", m["id"], {"action": "onayla", "fields": {**fields, "format": [{"deger": "uzay"}]}})
    with pytest.raises(RY.RoyaltyError):
        M.decide(engine, T, "telif", m["id"], {"action": "sil"})
    assert M.decide(engine, T, "telif", m["id"], {"action": "reddet"})["status"] == "reddedildi"


def test_digital_title_reads_the_same_map(engine):
    _note(engine)
    M.run(engine, T, M.pending(engine, T), None)
    D.write_titles(engine, T, [{
        "kitap_id": "K1", "ad": "Kitap", "tip": 1, "hak_notu_var": True,
        "sozlesme_json": D._dump([{"id": GID.upper(), "ad": "S-1", "taraflar": ["Yazar"], "yururlukte": True, "not": TEXT}]),
    }])
    ct = D.get_title(engine, T, "K1", with_sales=False)["sozlesmeler"][0]
    assert ct["hakHaritasi"]["durum"] == "oneri" and "E-kitap" in ct["hakHaritasi"]["ozet"]


def test_summary_line_and_access_rule():
    f = M.rule_extract(TEXT)
    line = M.summary_line(f)
    assert "Basılı" in line and "Münhasır değil" in line and "2030-12-31" in line
    assert "ozellik:haklar.duzenle" in A.features_for("POST", "/api/v1/rights/map/extract")
    assert "ozellik:haklar.duzenle" in A.features_for("POST", "/api/v1/rights/map/3/decide")
