"""M16 lansman risk bayrağı ve M18 hedef açığı ↔ ay planı boşluğu (AI fırsatları öneri 17): kural eşikleri (stok, dağılım,
hedef payı, emsal sapması, siparişsiz gün), düzey, kural cümlesi; Zeki AI cümlesinin gece yazılması, girdisi değişince
kural cümlesine dönüş, kaynaksız rakamlı cümlenin düşmesi; ay planında işi olan/olmayan hedef altı kitap, kural ve Zeki AI
paragrafı, bütçe görmeyen için ciro gizleme.

Veriler yapaydır; gerçek kabul test sunucusunda (`scripts/acceptance/zeki-15-16-17-19/`).
"""
from __future__ import annotations

import pytest

from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import launch as L
from semantic_bridge.marketing import launch_risk as LR
from semantic_bridge.marketing import monthly as M
from semantic_bridge.marketing import monthly_gaps as MG
from semantic_layer.store.catalog_store import open_store

T = "t1"
RS = LR.settings(lambda k: "")


class Chat:
    def __init__(self, text):
        self.text, self.prompts = text, []

    def chat(self, messages, **kw):
        self.prompts.append(messages[-1]["content"])
        return self.text


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for reg in (C._ready, L._ready, M._ready):
        reg.discard(id(e))
    L.ensure(e)
    M.ensure(e)
    yield e
    for reg in (C._ready, L._ready, M._ready):
        reg.discard(id(e))


def _head(**sig):
    base = {"gun": 5, "siparis": 120.0, "fatura": None, "oranEsas": "siparis", "oran": 1.2, "hedefAltinda": False,
            "stokCatismasi": False, "dagilimYok": False, "bekleyen": 10.0, "depo": {"deger": 500.0}}
    base.update(sig)
    return {"id": "ML-2026-0001", "baslik": "Deneme Kitap", "durum": "yayinda", "gun": base["gun"], "sinyal": base}


def test_flag_rules_and_levels():
    f = LR.flag({**_head(), "emsal": {"egri": [30.0] * 30}}, 0.8, RS)
    assert f["duzey"] == "yok" and f["kuralCumlesi"] is None
    f = LR.flag({**_head(siparis=50.0), "emsal": {"egri": [30.0] * 30}}, 0.8, RS)       # 50 / 150 = %33 < %70
    assert [r["kod"] for r in f["nedenler"]] == ["emsal"] and f["duzey"] == "orta"
    assert "emsal ortalaması 150 adet" in f["kuralCumlesi"] and f["kuralCumlesi"].startswith("Kurala göre dikkat")
    f = LR.flag({**_head(stokCatismasi=True, bekleyen=900.0), "emsal": {}}, 0.8, RS)
    assert f["duzey"] == "yuksek" and f["nedenler"][0]["kod"] == "stok" and "900" in f["nedenler"][0]["metin"]
    assert f["notlar"] == ["Emsal eğrisi yok; emsal kuralı uygulanamadı."]
    f = LR.flag({**_head(hedefAltinda=True, oran=0.5, siparis=0.0), "emsal": {}}, 0.8, RS)
    assert {r["kod"] for r in f["nedenler"]} == {"hedef", "siparis"} and f["duzey"] == "yuksek"
    f = LR.flag({**_head(gun=-3, siparis=0.0), "emsal": {"egri": [30.0]}}, 0.8, RS)     # yayından önce: sipariş/emsal kuralı yok
    assert f["duzey"] == "yok"
    f = LR.flag({**_head(oranEsas="fatura", fatura=10.0, siparis=400.0), "emsal": {"egri": [30.0] * 30}}, 0.8, RS)
    assert f["nedenler"][0]["kod"] == "emsal" and "faturalı satış 10 adet" in f["nedenler"][0]["metin"]
    closed = LR.flag({**_head(stokCatismasi=True), "durum": "kapandi", "emsal": {}}, 0.8, RS)
    assert closed["duzey"] == "yok"


def _launch(engine, lid, sig, emsal):
    with engine.begin() as c:
        c.execute(L.LAUNCHES.insert().values(id=lid, tenant_id=T, plan_id="MP-1", stok_kodu="15201.0001", baslik="Deneme Kitap",
                                             yayin_gunu="2026-09-01", yayin_gunu_kaynagi="elle", durum="yayinda", elle_kapandi=False,
                                             olusturan="ayse", olusturma=C.now(),
                                             ozet_json=C.dump({"sinyal": sig, "emsal": emsal})))


def test_attach_and_nightly_sentence(engine):
    sig = _head(siparis=50.0)["sinyal"]
    _launch(engine, "ML-2026-0001", sig, {"egri": [30.0] * 30})
    items = LR.attach(engine, T, L.list_launches(engine, T), 0.8, RS)
    r = items[0]["risk"]
    assert r["duzey"] == "orta" and r["cumleKaynak"] == "kural" and r["cumle"] == r["kuralCumlesi"]
    llm = Chat("Sipariş emsallerin gerisinde kalıyor: ilk 5 günde 50 adet, emsal ortalaması 150 adet. Rekor bir düşüş.")
    out = LR.run(engine, T, L.list_launches(engine, T), 0.8, RS, llm, [])
    assert out["bayrakli"] == 1 and out["yazildi"] == 1
    r = LR.attach(engine, T, L.list_launches(engine, T), 0.8, RS)[0]["risk"]
    assert r["cumleKaynak"] == "zeki" and r["cumle"].startswith("Sipariş emsallerin gerisinde") and "Rekor" not in r["cumle"]
    assert LR.run(engine, T, L.list_launches(engine, T), 0.8, RS, llm, [])["degismedi"] == 1
    # Girdi değişince saklı cümle kullanılmaz (kural cümlesi) — gece yeniden yazılana kadar.
    with engine.begin() as c:
        c.execute(L.LAUNCHES.update().values(ozet_json=C.dump({"sinyal": {**sig, "siparis": 40.0}, "emsal": {"egri": [30.0] * 30}})))
    r = LR.attach(engine, T, L.list_launches(engine, T), 0.8, RS)[0]["risk"]
    assert r["cumleKaynak"] == "kural" and "40 adet" in r["cumle"]
    # Kaynaksız rakamlı cümle düşer; hiç cümle kalmazsa kural cümlesi.
    out = LR.run(engine, T, L.list_launches(engine, T), 0.8, RS, Chat("Satış 999 adet eksik."), [])
    assert out["dustu"] == 1
    assert LR.attach(engine, T, L.list_launches(engine, T), 0.8, RS)[0]["risk"]["cumleKaynak"] == "kural"
    assert LR.run(engine, T, L.list_launches(engine, T), 0.8, RS, None, [])["model"] is False


def _month_plan(engine, donem, codes):
    pid = M._open_plan(engine, T, "ayse", donem)
    with engine.begin() as c:
        for i, code in enumerate(codes):
            c.execute(M.ITEMS.insert().values(id=f"i{i}", plan_id=pid, sira=i, tur="backlist", kaynak="kullanici", stok_kodu=code,
                                              baslik=f"Kitap {code}", elle=True))
    return pid


def test_month_gaps_rule_and_paragraph(engine):
    donem = "2026-10"
    _month_plan(engine, donem, ["A"])
    other = C.create_plan(engine, T, "ayse", kind="yeni", baslik="B planı", stok_kodu="B")
    C.replace_tasks(engine, T, "ayse", other, [{"tarih": "2026-10-05", "is": "Bülten", "durum": "bekliyor", "kaynak": "sablon"}], system=True)
    skipped = C.create_plan(engine, T, "ayse", kind="yeni", baslik="D planı", stok_kodu="D")
    C.replace_tasks(engine, T, "ayse", skipped, [{"tarih": "2026-10-05", "is": "Bülten", "durum": "atlandi", "kaynak": "sablon"}], system=True)
    devs = {"A": {"oran": 0.5, "eksik": 1000.0, "ad": "Kitap A"}, "B": {"oran": 0.6, "eksik": 800.0, "ad": "Kitap B"},
            "C": {"oran": 0.3, "eksik": 5000.0, "ad": "Kitap C"}, "D": {"oran": 0.7, "eksik": 100.0, "ad": "Kitap D"}}
    assert MG.planned_codes(engine, T, donem) == {"A", "B"}
    g = MG.gaps(engine, T, donem, devs)
    assert [x["stokKodu"] for x in g["items"]] == ["C", "D"] and (g["hedefAlti"], g["planli"], g["plansiz"]) == (4, 2, 2)
    assert "Kitap C (%30)" in g["kuralParagrafi"] and "pazarlama müdürünün kararıdır" in g["kuralParagrafi"]
    v = MG.with_paragraph(engine, T, g)
    assert v["paragrafKaynak"] == "kural" and v["paragraf"] == g["kuralParagrafi"]
    llm = Chat("Hedefin altında kalan 4 kitaptan 2 tanesine bu ay iş planlanmamış. Kitap C %30 ile en gerideki. Eksik ciro 5000 TL.")
    res = MG.write_paragraph(engine, T, g, llm, [])
    assert res["dusen"] == 1 and "5000" not in res["metin"]
    assert "5000" not in llm.prompts[0]                           # ciro tutarı modele gitmez
    v = MG.with_paragraph(engine, T, g)
    assert v["paragrafKaynak"] == "zeki" and v["eskiParagraf"] is False
    g2 = MG.gaps(engine, T, donem, {**devs, "E": {"oran": 0.2, "eksik": 50.0, "ad": "Kitap E"}})
    v2 = MG.with_paragraph(engine, T, g2)
    assert v2["paragrafKaynak"] == "kural" and v2["eskiParagraf"] is True
    assert all(x["eksik"] is None for x in MG.redact(g2)["items"])
    empty = MG.gaps(engine, T, donem, {})
    assert empty["kuralParagrafi"].endswith("uyarısı yok.")
