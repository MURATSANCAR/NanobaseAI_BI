"""İhale risk koşulu işaretleme (`tenders_risk`): aday cümle kuraldan ve şartnamenin kendisidir; özet maddesinin alıntısı
metinde yoksa düşer; kategori kapalı küme seçimle (emin «riskli değil» düşer, eşik altı incelenecek); model yoksa kurala
göre; yeniden işaretlemede insan kararı korunur; yazma uçları ihale düzenleme yetkisine bağlı.

Veriler yapaydır; model yerine sahte `choose`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from semantic_bridge import access as A
from semantic_bridge import tenders as T
from semantic_bridge import tenders_risk as R
from semantic_layer.store.catalog_store import open_store

TN = "t1"
SPEC = ("1. İşin konusu okul kütüphaneleri için kitap alımıdır.\n"
        "2. Teslim süresi sözleşme tarihinden itibaren 30 takvim günüdür.\n"
        "3. Süresinde teslim edilmeyen her gün için sözleşme bedelinin binde 3'ü oranında gecikme cezası kesilir.\n"
        "4. İstekliler teklifle birlikte her kalemden bir adet numune sunacaktır.\n"
        "5. Yerli malı teklif eden isteklilere yüzde 15 fiyat avantajı uygulanır.\n"
        "6. Kesin teminat sözleşme bedelinin yüzde 6'sıdır.\n"
        "7. Kitaplar okullara ayrı ayrı teslim edilecek, nakliye yükleniciye aittir.\n")


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    T._ready.discard(id(e))
    R.ensure(e)
    return e


@pytest.fixture(autouse=True)
def _files(tmp_path, monkeypatch):
    monkeypatch.setenv("TENDER_DIR", str(tmp_path / "ihale"))


def test_candidates_are_verbatim_sentences_with_rule_hints():
    cands, dropped = R.candidates(SPEC, {"kosullar": [
        {"deger": "Numune", "kaynak": "İstekliler teklifle birlikte her kalemden bir adet numune sunacaktır."},  # tekrar
        {"deger": "Ceza", "kaynak": "Her gecikme için yüzde 5 ceza uygulanır."}]})                              # metinde yok
    hints = {c["ipucu"] for c in cands}
    assert {"teslim-suresi", "ceza", "numune", "yerli-mali", "teminat", "teslim-yeri"} <= hints
    assert dropped == 1
    assert len([c for c in cands if "numune" in c["alinti"]]) == 1         # özet maddesi tekrar eklenmez
    tf = T.fold(SPEC)
    assert all(T.fold(c["alinti"]) in tf for c in cands)
    assert not any("İşin konusu" in c["alinti"] for c in cands)           # risk sözcüğü olmayan cümle aday değil


def test_classify_closed_set_and_thresholds():
    cands, _ = R.candidates(SPEC)

    def choose(prompt, labels):
        assert R.NONE_LABEL in labels and len(labels) == len(R.CATEGORIES) + 1
        if "bir adet numune" in prompt:
            return SimpleNamespace(choice=R.NONE_LABEL, probability=0.95, margin=0.9)
        if "yüzde 15 fiyat" in prompt:
            return SimpleNamespace(choice=R.CATEGORIES["yerli-mali"], probability=0.55, margin=0.1)
        return SimpleNamespace(choice=R.CATEGORIES["ceza"], probability=0.9, margin=0.8)

    rows = R.classify(cands, choose)
    assert not any("numune" in r["alinti"] for r in rows)                 # emin «riskli değil» düşer
    yerli = next(r for r in rows if "Yerli malı" in r["alinti"])
    assert yerli["kaynak"] == "incele" and yerli["kategori"] == "yerli-mali"   # eşik altı: kural ipucu, incelenecek
    assert all(r["kaynak"] in ("zeki", "incele") for r in rows)
    rule = R.classify(cands, None)
    assert {r["kaynak"] for r in rule} == {"kural"} and len(rule) == len(cands)


def test_model_error_keeps_candidate_for_review():
    cands, _ = R.candidates(SPEC)

    def boom(prompt, labels):
        raise RuntimeError("model yok")
    assert {r["kaynak"] for r in R.classify(cands, boom)} == {"incele"}


def test_save_keeps_human_decision_and_decide_validates(engine):
    t = T.create(engine, TN, "ayse", {"kurum": "Üsküdar İlçe MEM", "kurumTuru": "mem", "konu": "Kitap alımı"})
    rows = R.classify(R.candidates(SPEC)[0], None)
    R.save(engine, t["id"], rows, "sartname.pdf")
    lst = R.listing(engine, TN, t["id"])
    assert len(lst["items"]) == len(rows) and lst["kararsiz"] == len(rows)
    ceza = next(i for i in lst["items"] if i["kategori"] == "ceza")
    out = R.decide(engine, TN, "ayse", t["id"], ceza["id"], {"karar": "engel", "not": "binde 3 yüksek"})
    assert out["karar"] == "engel" and out["kararVeren"] == "ayse"
    with pytest.raises(T.TenderError):
        R.decide(engine, TN, "ayse", t["id"], ceza["id"], {"karar": "belki"})
    with pytest.raises(T.TenderError):
        R.decide(engine, TN, "ayse", t["id"], ceza["id"], {"kategori": "uzay"})
    R.save(engine, t["id"], rows, "sartname.pdf")                          # yeniden işaretleme
    again = R.listing(engine, TN, t["id"])
    kept = next(i for i in again["items"] if i["alinti"] == ceza["alinti"])
    assert kept["karar"] == "engel" and again["engel"] == 1
    with pytest.raises(T.TenderError):
        R.listing(engine, "baska", t["id"])                                  # başka kiracının ihalesi okunmaz


def test_write_endpoints_need_tender_edit():
    assert "ozellik:ihale.duzenle" in A.features_for("POST", "/api/v1/tenders/abc/risk-flags")
    assert "ozellik:ihale.duzenle" in A.features_for("PATCH", "/api/v1/tenders/abc/risk-flags/r1")
    assert "ozellik:ihale.duzenle" not in A.features_for("GET", "/api/v1/tenders/abc/risk-flags")
