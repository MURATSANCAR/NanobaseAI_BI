"""Öneri 13 — M6 sözleşme belgesinden şart çıkarma (`semantic_bridge.contract_extract`).

Sözleşme: her şart belgede birebir alıntıyla gelir; oran, tutar, tarih ve süre alıntının kendisinden kodla okunur
(modelin yazdığı sayı değer olmaz, yalnız alıntıdaki adaylardan birini gösterir); kapalı kümeli alanın değeri kümede
olmalı ve alıntıda o değerin sözcüğü geçmeli; «saklıdır / hariç» cümlesi hak vermez; aynı alana farklı değerler
çıkarsa alan boş kalır ve adaylar «çelişki» olur; öneri sözleşme şartlarının alan adlarıyla gelir ve şart
doğrulamasından geçer; dil/ülke/biçim/bitiş/münhasırlık M54 hak haritasının biçimindedir; modele giden metinde
kimlik ve etiketli kişi satırları yoktur. Model sahtedir; gerçek model ve OCR kabulü test sunucusunda
(scripts/acceptance/zeki-12-13).
"""

from __future__ import annotations

import json

import pytest

from semantic_bridge import contract_extract as CE
from semantic_bridge import contracts_terms as T
from semantic_bridge import doc_extract as X
from semantic_bridge import doc_read as DR
from semantic_layer.store.catalog_store import open_store

TEN = "t1"
DOC = ("TELİF SÖZLEŞMESİ\n"
       "Adı Soyadı: Ayşe Yılmaz\n"
       "T.C. Kimlik No: 12345678901\n"
       "Madde 3. Yayınevi, eserin net satış tutarı üzerinden yazara %10 (yüzde on) telif öder.\n"
       "Madde 4. E-kitap satışlarında telif oranı %25'tir.\n"
       "Madde 5. Yayınevi yazara imza tarihinde 15.000,00 TL avans öder; avans telif ücretinden mahsup edilir.\n"
       "Madde 6. Bu sözleşme 01.01.2026 tarihinden 31.12.2030 tarihine kadar geçerlidir.\n"
       "Madde 7. Yazar, eserin Türkçe dilinde basılı ve e-kitap olarak çoğaltma, yayma ve umuma iletim haklarını "
       "yayınevine münhasır olarak devreder.\n"
       "Madde 8. Sesli kitap hakları yazarda saklıdır.\n")
CFG = {"windowChars": 24000, "overlap": 1}
CFG_READ = {"ocr": False, "timeout": 30, "minChars": 5, "lowConfidence": 0.8}


def reading(text: str = DOC) -> DR.Reading:
    return DR.Reading("s.txt", [{"sayfa": "1", "metin": text, "okuma": DR.METIN, "guven": None}])


def test_rule_layer_reads_terms_from_sentences():
    out = CE.analyse(reading(), names=[], chat=None, cfg=CFG)
    a = out["alanlar"]
    assert a["rates.karton"]["deger"] == 10 and a["rates.ekitap"]["deger"] == 25
    assert a["basis"]["deger"] == "net" and a["paymentType"]["deger"] == "satis"
    assert a["advance"]["deger"] == 15000 and a["currency"]["deger"] == "TRY"
    assert a["start"]["deger"] == "2026-01-01" and a["end"]["deger"] == "2030-12-31"
    assert "%10" in a["rates.karton"]["kanit"][0]["alinti"] and a["advance"]["kanit"][0]["sayfa"] == "1"
    h = out["haklar"]
    assert [x["deger"] for x in h["dil"]] == ["Türkçe"]
    assert sorted(x["deger"] for x in h["format"]) == ["basili", "e-kitap"]      # «sesli … saklıdır» hak vermez
    assert h["munhasirlik"]["deger"] == "munhasir" and h["bitis"]["deger"] == "2030-12-31"
    assert set(h["dil"][0]) >= {"deger", "alinti", "kaynak", "sayfa", "okuma"}   # M54 hak haritası kalem biçimi
    assert sorted(x["deger"] for x in out["maliHaklar"]) == ["cogaltma", "ekitap", "iletim", "yayma"]
    assert out["kaynak"] == "kural" and "bağlı değil" in out["neden"]


def test_suggestion_uses_terms_field_names_and_passes_validation():
    o = CE.analyse(reading(), names=[], chat=None, cfg=CFG)["oneri"]
    assert o["rates"] == {"karton": 10, "ekitap": 25} and o["advance"] == 15000 and o["currency"] == "TRY"
    assert o["rights"] == {"cogaltma": True, "yayma": True, "iletim": True, "ekitap": True}
    assert o["language"] == "Türkçe" and o["end"] == "2030-12-31" and o["openEnded"] is False
    assert o["notesLine"].startswith("Münhasırlık: Münhasır") and "gecersiz" not in o
    t = T.clean({k: v for k, v in o.items() if k != "notesLine"})
    assert t["basis"] == "net" and t["paymentType"] == "satis"


def test_model_cannot_inject_numbers_or_unquoted_values():
    sent = []

    def chat(messages):
        sent.append(messages)
        return json.dumps({
            "oran": [{"tur": "sesli", "deger": "%30", "alinti": "Sesli kitap hakları yazarda saklıdır"}],
            "avans": {"deger": "20.000 TL", "alinti": "imza tarihinde 15.000,00 TL avans öder"},
            "para_birimi": {"deger": "USD", "alinti": "ödemeler USD ile yapılır"},
            "ulke": [{"deger": "Türkiye", "alinti": "Türkiye sınırları içinde"}],
            "tip": {"deger": "tek", "alinti": "net satış tutarı üzerinden yazara %10"},
            "format": [{"deger": "sesli", "alinti": "Sesli kitap hakları yazarda saklıdır"}],
        }, ensure_ascii=False)

    out = CE.analyse(reading(), names=[], chat=chat, cfg=CFG)
    a = out["alanlar"]
    assert a["advance"]["deger"] == 15000                 # alıntıdaki sayı; modelin 20.000'i değil
    assert a["currency"]["deger"] == "TRY" and "rates.sesli" not in a
    assert out["haklar"]["ulke"] == [] and "sesli" not in [x["deger"] for x in out["haklar"]["format"]]
    assert a["paymentType"]["deger"] == "satis"
    assert out["atilan"] == 5 and out["kaynak"] == "zeki"
    text = json.dumps(sent, ensure_ascii=False)
    assert "Yılmaz" not in text and "12345678901" not in text   # kimlik ve etiketli kişi satırı modele gitmez


def test_conflicting_values_leave_the_field_empty_with_candidates():
    doc = "Yazara 10.000 TL avans ödenir. İkinci baskıda 5.000 TL avans daha ödenir."
    out = CE.analyse(reading(doc), names=[], chat=None, cfg=CFG)
    adv = out["alanlar"]["advance"]
    assert adv["deger"] is None and sorted(c["deger"] for c in adv["celiski"]) == [5000, 10000]
    assert "advance" not in out["oneri"] and out["oneri"]["currency"] == "TRY"


def test_readers_on_their_own():
    assert CE.read_rate("KDV %18 olarak uygulanır ve telif") is None
    assert CE.read_withholding("Telif ödemelerinden %17 stopaj kesilir") == 17
    assert CE.read_basis("kapak fiyatı üzerinden") == "brut" and CE.read_basis("net satış ve kapak fiyatı") is None
    assert CE.read_payment("basılan her kitap için telif") == "baski"
    assert CE.read_payment("satılan kitaplar için kademeli telif") == "satis-kademeli"
    assert CE.read_payment("basılan kitaplar", "tek") is None
    assert CE.read_currency("5.000 EUR avans") == "EUR" and CE.read_currency("5.000 TL ya da 200 USD") is None
    assert CE.read_rights("Çeviri hakkı hariç tüm haklar devredilir") == []
    assert CE.exclusivity_of("münhasır olmayan lisans") == "munhasir-degil"
    assert CE.read_years("Sözleşmenin süresi 5 (beş) yıldır") == 5


def test_party_names_and_labeled_lines_are_masked():
    doc = DOC + "Yazar ayse@ornek.com adresinden bildirim alır. Ayşe Yılmaz imza."
    got = []
    CE.analyse(reading(doc), names=["Ayşe Yılmaz"], chat=lambda m: got.append(m) or "{}", cfg=CFG)
    text = json.dumps(got, ensure_ascii=False)
    assert "Ayşe" not in text and "ayse@ornek.com" not in text and "[kişisel bilgi]" in text


def test_long_contract_reads_every_window():
    doc = "\n".join(f"Madde {i}. " + "Taraflar bu maddede yükümlülüklerini yeniden teyit eder. " * 30 for i in range(1, 30))
    n = []
    CE.analyse(DR.Reading("s.pdf", [{"sayfa": str(i), "metin": p, "okuma": DR.METIN, "guven": None}
                                     for i, p in enumerate(doc.split("\n"), start=1)]),
               names=[], chat=lambda m: n.append(1) or "{}", cfg={"windowChars": 5000, "overlap": 1})
    assert len(n) > 1


def test_accept_rejects_unknown_fields(engine):
    row = CE.create(engine, TEN, "ayse", "s.txt", DOC.encode(), None)
    with pytest.raises(CE.ExtractError):
        CE.accept(engine, TEN, "ayse", row["id"], ["bilinmeyen"], None)
    out = CE.accept(engine, TEN, "ayse", row["id"], ["advance", "rates.karton", "rights.ekitap"], "K1")
    assert out["contractKey"] == "K1" and out["accepted"] == ["advance", "rates.karton", "rights.ekitap"]


def test_create_checks_type_and_size(engine):
    with pytest.raises(CE.ExtractError, match="Desteklenmeyen"):
        CE.create(engine, TEN, "ayse", "s.exe", b"MZ", None)
    with pytest.raises(CE.ExtractError, match="uyuşmuyor"):
        CE.create(engine, TEN, "ayse", "s.pdf", b"not a pdf", None)


# ------------------------------------------------------------------------------------------------ uçlar


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTRACT_DOCS_DIR", str(tmp_path / "docs"))
    e = open_store("sqlite://").engine
    CE._ready.discard(id(e))
    CE.ensure(e)
    return e


class FakeRt:
    def __init__(self, llm):
        self.llm = llm

    def llm_for(self, module, priority=None):
        if self.llm is None:
            raise RuntimeError("model yok")
        return self.llm


class EmptyLlm:
    def chat(self, messages, **kw):
        return "{}"


def test_endpoints_upload_read_accept_delete(engine, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from semantic_bridge import contract_extract_api as API
    from semantic_bridge import provenance as P

    monkeypatch.setattr(DR, "settings", lambda: CFG_READ)
    monkeypatch.setattr(X, "settings", lambda conf=None: CFG)
    monkeypatch.setattr(API, "spawn", lambda target, name: target())
    allowed = {"ok": True}
    audits = []
    app = FastAPI()
    API.register(app, rt=lambda: FakeRt(EmptyLlm()), greetings=lambda r: (engine, TEN, "ayse", "Ayşe"),
                 can=lambda u, k: allowed["ok"], audit=lambda *a, **k: audits.append(a), conf=lambda k: "")
    c = TestClient(app)
    base = "/api/v1/editorial/contracts/extracts"
    r = c.put(f"{base}?filename=sozlesme.txt", content=DOC.encode())
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    g = c.get(f"{base}/{eid}").json()
    item = g["item"]
    assert item["status"] == "hazir", item["error"]
    assert item["result"]["oneri"]["advance"] == 15000 and g["model"] is True
    assert not P.uncovered_numbers(g) and not P.problems(g)
    assert c.get(f"{base}/{eid}/file").content == DOC.encode()
    acc = c.post(f"{base}/{eid}/accepted", json={"fields": ["advance"], "key": "K9"})
    assert acc.status_code == 200 and acc.json()["contractKey"] == "K9"
    lst = c.get(f"{base}?key=K9").json()
    assert [x["id"] for x in lst["items"]] == [eid] and not P.uncovered_numbers(lst)
    allowed["ok"] = False
    assert c.put(f"{base}?filename=s.txt", content=b"metin").status_code == 403
    assert c.delete(f"{base}/{eid}").status_code == 403
    allowed["ok"] = True
    assert c.delete(f"{base}/{eid}").json() == {"ok": True}
    assert c.get(f"{base}/{eid}").status_code == 404
    assert [a[2] for a in audits] == ["upload", "accept", "delete"]
