"""Kampüs «Bugün» özeti (AI fırsatları öneri 19): yalnız yetkili modüllerin maddeleri, e-posta SLA riski, onay
kuyruğunda kişinin kendi gönderdiği işin görünmemesi, okur sesi uyarısının yalnız üretim yetkisine gitmesi, bir kaynak
okunamayınca diğerlerinin sürmesi, kural özeti (üç cümle), Zeki AI özetinde kaynaksız rakamın düşmesi ve girdi aynıyken
modelin yeniden çağrılmaması, yetki kuralı.

Veriler yapaydır; gerçek kabul test sunucusunda (`scripts/acceptance/zeki-15-16-17-19/`).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from semantic_bridge import access as AC
from semantic_bridge import alerts as A
from semantic_bridge import field_sales as F
from semantic_bridge import mailbox as MB
from semantic_bridge import reader_voice as V
from semantic_bridge import today_brief as TB
from semantic_bridge.marketing import core as C
from semantic_layer.store.catalog_store import open_store

TN = "t1"
AT = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 20)
ST = TB.settings(lambda k: "")


class Chat:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def chat(self, messages, **kw):
        self.calls += 1
        self.prompt = messages[-1]["content"]
        return self.text


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for reg in (TB._ready, F._ready, MB._ready, V._ready, C._ready, A._ready):
        reg.discard(id(e))
    for m in (TB, F, MB, V, C):
        m.ensure(e)
    A.ensure(e)
    yield e
    for reg in (TB._ready, F._ready, MB._ready, V._ready, C._ready, A._ready):
        reg.discard(id(e))


def _mail(engine, mid, assignee, due, replied=None, status="atandi"):
    with engine.begin() as c:
        c.execute(MB.MESSAGES.insert().values(id=mid, tenant_id=TN, provider="gmail", provider_id=mid, received_at=AT - timedelta(days=1),
                                              from_addr_hash="h", status=status, assignee=assignee, due_at=due, first_reply_at=replied,
                                              unsure=False, is_hr=False, historical=False, created_at=AT))


def _seed(engine):
    _mail(engine, "m1", "ayse", AT - timedelta(hours=2))            # SLA aşıldı
    _mail(engine, "m2", "ayse", AT + timedelta(hours=1))            # 4 saat içinde dolacak
    _mail(engine, "m3", "Ayse", AT + timedelta(days=2))             # yalnız açık
    _mail(engine, "m4", "ayse", AT - timedelta(hours=5), replied=AT)  # yanıtlanmış: SLA dışı
    _mail(engine, "m5", "mehmet", AT - timedelta(hours=5))          # başkasının
    with engine.begin() as c:
        c.execute(A.RULES.insert().values(id="r1", tenant_id=TN, datasource_id="d", title="İade tutarı", question="q", sql="s",
                                          condition="gt", threshold=1, recipients="[]", status="active", created_by="ayse",
                                          created_at=AT, updated_at=AT, state="triggered"))
        c.execute(F.PLANS.insert().values(id="p1", tenant_id=TN, logo_code="120.1", tutar=10, taksitler_json="[]", durum="onayda",
                                          oneren="mehmet", gonderen="mehmet", olusturma=AT))
        c.execute(F.PLANS.insert().values(id="p2", tenant_id=TN, logo_code="120.2", tutar=10, taksitler_json="[]", durum="onayda",
                                          oneren="ayse", gonderen="ayse", olusturma=AT))
        c.execute(F.EVENTS.insert().values(id="e1", tenant_id=TN, sahip="ayse", tur="tahsilat-red", anahtar="k", baslik="Red",
                                           zaman=AT))
    V.classify(engine, TN, [{"kaynak": "site-yorum", "id": str(i), "anahtar": "K1", "ad": "Kitap", "tarih": "2026-09-10",
                             "metin": "eksik sayfa"} for i in range(3)], None, V.settings(lambda k: ""))
    V.sync_alerts(engine, TN, V.clusters(engine, TN, V.settings(lambda k: ""), TODAY))


def test_collect_filters_by_permission(engine):
    _seed(engine)
    everything = TB.collect(engine, TN, "ayse", lambda k: True, ST, TODAY, AT)
    kinds = [(x["kaynak"], x["baslik"], x["sayi"]) for x in everything["items"]]
    assert ("sla", "Yanıt süresi geçmiş e-posta", 1) in kinds
    assert ("sla", "4 saat içinde yanıt süresi dolacak e-posta", 1) in kinds
    assert ("eposta", "Bana atanmış açık e-posta", 4) in kinds
    assert ("uyari", "Eşiği aşan uyarı kuralım", 1) in kinds
    assert ("onay", "Onayımı bekleyen ödeme planı", 1) in kinds             # kendi gönderdiği (p2) sayılmaz
    assert ("saha", "Görülmemiş saha bildirimim", 1) in kinds
    assert any(x["kaynak"] == "okur-sesi" and x["link"] == "/okur-toplulugu/yorumlar" for x in everything["items"])
    assert everything["items"][0]["oncelik"] == 1 and everything["okunamayan"] == []
    nothing = TB.collect(engine, TN, "ayse", lambda k: False, ST, TODAY, AT)
    assert nothing["items"] == []
    only_prod = TB.collect(engine, TN, "ayse", lambda k: k == "sayfa:uretim", ST, TODAY, AT)
    assert [x["kaynak"] for x in only_prod["items"]] == ["okur-sesi"] and only_prod["items"][0]["link"] == "/uretim"


def test_failing_source_does_not_hide_others(engine, monkeypatch):
    _seed(engine)
    monkeypatch.setattr(TB, "alerts_items", lambda *a: (_ for _ in ()).throw(RuntimeError("tablo bozuk")))
    out = TB.collect(engine, TN, "ayse", lambda k: True, ST, TODAY, AT)
    assert out["okunamayan"] == ["Uyarılar"] and any(x["kaynak"] == "sla" for x in out["items"])


def test_rule_summary_three_sentences():
    assert TB.rule_summary([]).count(".") == 3
    items = [TB.item("sla", "Yanıt süresi geçmiş e-posta", 2, "/x", 1), TB.item("onay", "Onayımı bekleyen plan", 1, "/y", 2),
             TB.item("lansman", "Bugünkü lansman maddem", 3, "/z", 2)]
    s = TB.rule_summary(items)
    assert s.startswith("Öncelik: yanıt süresi geçmiş e-posta 2.") and "onayımı bekleyen plan 1" in s and "bugünkü lansman maddem 3" in s


def test_model_summary_guarded_and_cached(engine):
    _seed(engine)
    data = TB.collect(engine, TN, "ayse", lambda k: True, ST, TODAY, AT)
    llm = Chat("Önce yanıt süresi geçmiş 1 e-postaya bak. Onay bekleyen 1 ödeme planı var. Toplam 17 işin var.")
    out = TB.write(engine, TN, "ayse", data["gun"], data["items"], llm)
    assert out["metin"] and "17" not in out["metin"] and out["dusen"] == 1 and llm.calls == 1
    assert "mehmet" not in llm.prompt                                          # başkasının kaydı yok, kişi adı yok
    again = TB.write(engine, TN, "ayse", data["gun"], data["items"], llm)
    assert again["onbellek"] is True and llm.calls == 1
    assert TB.cached(engine, TN, "ayse", data["gun"], data["items"])["guncel"] is True
    assert TB.cached(engine, TN, "ayse", "2026-09-21", data["items"]) is None   # ertesi gün yeniden
    fewer = data["items"][1:]
    assert TB.cached(engine, TN, "ayse", data["gun"], fewer)["guncel"] is False


def test_access_rule():
    assert AC.rule_for("/api/v1/bugun") == AC.OPEN and AC.rule_for("/api/v1/bugun/ozet") == AC.OPEN
