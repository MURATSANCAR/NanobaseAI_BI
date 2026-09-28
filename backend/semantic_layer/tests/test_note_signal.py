"""Serbest not sinyali (AI fırsatları öneri 16): portal notlarının okunması (gizli ve iptal hariç), ödeme sözü kuralı,
Zeki AI kapalı küme + eşik, maske (iletişim, bilinen ad, «Ad Bey»), metni değişmeyen notun yeniden etiketlenmemesi,
kaynağından silinen notun etiketinin silinmesi, cari görünümü (son 5 not, pencere sayıları, özetin güncelliği), iki
cümlelik özette kaynaksız rakamın düşmesi ve kural özetine dönüş, CRM sorgusunun ad/kimlik doğrulaması, yetki kuralları.

Veriler yapaydır; gerçek kabul test sunucusunda (`scripts/acceptance/zeki-15-16-17-19/`).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from semantic_bridge import access as AC
from semantic_bridge import dealers as D
from semantic_bridge import field_sales as F
from semantic_bridge import musteri as M
from semantic_bridge import note_signal as N
from semantic_layer.store.catalog_store import open_store

TN = "t1"
NOW = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 20)


class Choice:
    def __init__(self, choice, p, margin):
        self.choice, self.probability, self.margin = choice, p, margin

    def confident(self, min_prob, min_margin=0.0):
        return self.probability >= min_prob and self.margin >= min_margin


class Llm:
    def __init__(self, answers=(), text=""):
        self.answers, self.text, self.prompts = list(answers), text, []

    def choose(self, prompt, labels):
        self.prompts.append((prompt, labels))
        return self.answers.pop(0)

    def chat(self, messages, **kw):
        self.prompts.append((messages[-1]["content"], None))
        return self.text


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for reg in (N._ready, F._ready, D._ready, M._ready):
        reg.discard(id(e))
    N.ensure(e)
    D.ensure(e)
    M.ensure(e)
    yield e
    for reg in (N._ready, F._ready, D._ready, M._ready):
        reg.discard(id(e))


def _st(**kw):
    s = N.settings(lambda k: "")
    s.update(kw)
    return s


def _visit(engine, vid, code, notu, day, gizli=False, durum="yapildi", soz=None):
    with engine.begin() as c:
        c.execute(F.VISITS.insert().values(id=vid, tenant_id=TN, tur="cari", hedef_kimlik=code, sahip="bmt1", gerceklesen=day,
                                           durum=durum, notu=notu, gizli=gizli, soz_odeme_tarihi=soz, olusturan="bmt1",
                                           olusturma=NOW))


def _seed(engine):
    _visit(engine, "v1", "120.01", "Ahmet Bey 0532 111 22 33 ile görüştük, ay sonu ödeme yapacak", "2026-09-18", soz="2026-09-30")
    _visit(engine, "v2", "120.01", "Raflar boşalmış, dükkânı devretmeyi düşünüyor", "2026-09-10")
    _visit(engine, "v3", "120.01", "Gizli: ortaklık kavgası", "2026-09-12", gizli=True)
    _visit(engine, "v4", "120.01", "İptal edilen ziyaret", "2026-09-11", durum="iptal")
    _visit(engine, "v5", "120.02", "", "2026-09-11")
    with engine.begin() as c:
        c.execute(D.ACTIONS.insert().values(id="a1", tenant_id=TN, logo_code="120.01", tur="arama", sahip="bmt1", durum="acik",
                                            notu="Yeni çıkan 20 kitaptan sipariş verecek", olusturan="bmt1", olusturma=NOW))
        c.execute(M.ACTIONS.insert().values(id="m1", tenant_id=TN, cari_kodu="120.02", tur="arama", aciklama="Kargo gecikmesinden şikâyetçi",
                                            sahip="bmt1", durum="yapildi", yazan="bmt1", tarih="2026-09-15", olusturma=NOW))


def test_portal_notes_skip_private_cancelled_and_empty(engine):
    _seed(engine)
    notes = {n["id"]: n for n in N.portal_notes(engine, TN)}
    assert set(notes) == {"v1", "v2", "a1", "m1"}
    assert notes["v1"]["sozOdeme"] is True and notes["a1"]["kaynak"] == "bayi-aksiyon" and notes["m1"]["cari"] == "120.02"
    assert set(n["id"] for n in N.portal_notes(engine, TN, {"120.02"})) == {"m1"}


def test_mask_contact_known_names_and_title():
    t = N.mask("Ahmet Bey ile Ayşe Yılmaz konuştu; tel 0532 111 22 33, a@b.com", ["Ayşe Yılmaz"])
    assert "Ahmet" not in t and "Ayşe" not in t and "0532" not in t and "a@b.com" not in t
    assert "[kişi] Bey" in t


def test_classify_rule_model_threshold_and_prune(engine):
    _seed(engine)
    notes = N.portal_notes(engine, TN)
    llm = Llm([Choice("Kapanış sinyali", 0.88, 0.6), Choice("Sipariş niyeti", 0.95, 0.9), Choice("Şikâyet", 0.5, 0.1)])
    out = N.classify(engine, TN, notes, llm, _st(), names=[])
    assert out["kural"] == 1 and out["zeki"] == 2 and out["eminDegil"] == 1
    assert out["degisenCari"] == ["120.01", "120.02"]
    rows = N.signal_rows(engine, TN, "120.01")
    assert rows[("saha-ziyaret", "v1")].etiket == "tahsilat" and rows[("saha-ziyaret", "v1")].yontem == "kural"
    assert {r.etiket for r in rows.values()} == {"tahsilat", "kapanis", "siparis"}
    m1 = N.signal_rows(engine, TN, "120.02")[("musteri-aksiyon", "m1")]
    assert m1.etiket is None and m1.yontem == "emin-degil"
    assert all(labels == list(N.LABELS.values()) for _, labels in llm.prompts)
    assert all("0532" not in p for p, _ in llm.prompts)
    # Değişmeyen not yeniden etiketlenmez.
    assert N.classify(engine, TN, notes, Llm([]), _st())["degismedi"] == len(notes)
    # Gizlenen not kaynaktan düşer, etiketi silinir.
    with engine.begin() as c:
        c.execute(F.VISITS.update().where(F.VISITS.c.id == "v2").values(gizli=True))
    notes = N.portal_notes(engine, TN)
    assert N.prune(engine, TN, notes, ["saha-ziyaret", "bayi-aksiyon", "musteri-aksiyon"]) == 1
    assert ("saha-ziyaret", "v2") not in N.signal_rows(engine, TN, "120.01")


def test_view_and_summary_with_guard(engine):
    _seed(engine)
    notes = N.portal_notes(engine, TN)
    N.classify(engine, TN, notes, Llm([Choice("Kapanış sinyali", 0.9, 0.8), Choice("Sipariş niyeti", 0.9, 0.8),
                                       Choice("Şikâyet", 0.9, 0.8)]), _st())
    v = N.view(engine, TN, "120.01", notes, _st(), TODAY)
    assert v["sayilar"]["tahsilat"] == 1 and v["sayilar"]["kapanis"] == 1 and v["sayilar"]["siparis"] == 1
    assert [n["kaynak"] for n in v["sonNotlar"]] == ["bayi-aksiyon", "saha-ziyaret", "saha-ziyaret"] and v["ozet"] is None
    assert "metin" not in v["sonNotlar"][0]                           # not metni bu uçtan gönderilmez
    # Kaynaksız rakam (5000) düşer, kalan tek cümle; tarih ve notlardaki 20 serbest.
    llm = Llm(text="Cari ay sonu ödeme sözü verdi ve 20 kitaplık sipariş niyeti var. Borcu 5000 TL.")
    out = N.write_summary(engine, TN, "120.01", notes, llm, _st(), [])
    assert out["kaynak"] == "zeki" and "5000" not in out["metin"] and out["dusen"] == 1
    assert "0532" not in llm.prompts[-1][0] and "Gizli" not in llm.prompts[-1][0]
    assert N.write_summary(engine, TN, "120.01", notes, llm, _st(), [])["onbellek"] is True
    assert N.view(engine, TN, "120.01", notes, _st(), TODAY)["ozet"]["guncel"] is True
    # Yeni not gelince özet güncel değildir.
    _visit(engine, "v9", "120.01", "Yeni not", "2026-09-19")
    notes = N.portal_notes(engine, TN)
    assert N.view(engine, TN, "120.01", notes, _st(), TODAY)["ozet"]["guncel"] is False
    # Model bütün cümleleri düşürürse kural özeti.
    out = N.write_summary(engine, TN, "120.02", notes, Llm(text="Toplam 99 şikâyet var."), _st(), [])
    assert out["kaynak"] == "kural" and "şikâyet 1" in out["metin"]
    # Model yok: kural özeti; model gelince yeniden denenir.
    out = N.write_summary(engine, TN, "120.01", notes, None, _st(), [], force=True)
    assert out["kaynak"] == "kural"
    assert N.write_summary(engine, TN, "120.01", notes, Llm(text="Ödeme sözü var."), _st(), [])["kaynak"] == "zeki"


def test_crm_sql_and_mapping():
    sql = N.crm_notes_sql("Timas_MSCRM.dbo", "new_cariid", date(2025, 9, 20))
    assert "new_info" in sql and "new_Tahsilatinfo" in sql and "new_ziyarettipi" in sql and "2025-09-20" in sql
    assert "UPDATE" not in sql.upper() and "INSERT" not in sql.upper()
    one = N.crm_notes_sql("Timas_MSCRM.dbo", "new_cariid", date(2025, 9, 20), "{0F8FAD5B-D9CB-469F-A165-70867728950E}")
    assert "= '0F8FAD5B-D9CB-469F-A165-70867728950E'" in one
    with pytest.raises(N.NoteError):
        N.crm_notes_sql("Timas_MSCRM.dbo", "x; DROP TABLE y", date(2025, 1, 1))
    with pytest.raises(N.NoteError):
        N.crm_notes_sql("Timas_MSCRM.dbo", "new_cariid", date(2025, 1, 1), "1 OR 1=1")
    rows = [{"id": "{AB}", "account_id": "{0F8FAD5B-D9CB-469F-A165-70867728950E}", "tarih": datetime(2026, 9, 1), "info": "Ödeme",
             "tahsilat": "Çek verecek"},
            {"id": "C", "account_id": "bilinmeyen", "info": "x"}]
    out = N.crm_notes(rows, {"0f8fad5b-d9cb-469f-a165-70867728950e": "120.01"})
    assert out == [{"kaynak": "crm-etkinlik", "id": "ab", "cari": "120.01", "tarih": "2026-09-01", "metin": "Ödeme Çek verecek"}]


def test_access_rules():
    assert AC.rule_for("/api/v1/not-sinyali/run-due") == AC.SYSTEM
    assert AC.rule_for("/api/v1/not-sinyali/cari/120.01") == {"sayfa:saha", "sayfa:bayi-risk", "sayfa:musteri-iliskileri"}
