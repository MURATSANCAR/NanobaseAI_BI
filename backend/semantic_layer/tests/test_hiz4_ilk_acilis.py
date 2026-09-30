"""Hız 4. tur (2026-09-29): kişiye ait hazır cevap yokken ekranların ilk açılışı.

Kişiden bağımsız ağır okuma/hesap ortak katmanda bir kez yapılır (bellek + `semantic_hizli_okuma` tablosu); bayatken
eldeki değer hemen döner, kaynak arkada okunur; kişi süzgeci ve yetki bellekteki sonucun üstünde istekte uygulanır.
Her parça için: eski hesap = yeni hesap, köprü yeniden başlayınca (yeni bellek) tablodan okunur, bayat değer hemen döner,
«Yenile» kaynağı bekler. Veriler yapaydır.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa

from semantic_bridge import hizli_kaynak as HK
from semantic_layer.tests.test_hiz_pazarlama_iletisim import SayanBaglanti, SayanCrm, _bekle, _eskit, _okur_engine, _sakin


def _motor():
    from semantic_layer.store.catalog_store import open_store

    return open_store("sqlite://").engine


def _eskit_tablo(engine, ad: str, sn: float) -> None:
    """Kalıcı kaydı `sn` saniye eskitir (köprü kapalıyken zaman geçmiş gibi)."""
    with engine.begin() as c:
        for r in c.execute(sa.select(HK.OKUMA.c.anahtar, HK.OKUMA.c.okundu).where(HK.OKUMA.c.ad == ad)).all():
            at = r.okundu if r.okundu.tzinfo else r.okundu.replace(tzinfo=timezone.utc)
            c.execute(HK.OKUMA.update().where(HK.OKUMA.c.ad == ad, HK.OKUMA.c.anahtar == r.anahtar)
                      .values(okundu=at - timedelta(seconds=sn)))


# ------------------------------------------------------------------ ortak kalıcı katman


def test_kalici_kayit_yeniden_baslayinca_okunur_bayatsa_arkada_tazelenir(monkeypatch):
    e = _motor()
    n = {"x": 0}

    def hesap():
        n["x"] += 1
        return {"rows": [{"gun": date(2026, 9, 1), "tutar": Decimal("12.50"), "an": datetime(2026, 9, 1, 10, 0)}], "n": n["x"]}

    def bellek(bicim="v1"):
        return HK.bellek("t.kalici", 600, kalici=HK.Kalici("t.kalici", lambda: (e, "t1"), bicim=bicim))

    key = ("liste", date(2026, 9, 1), date(2026, 12, 31))
    ilk = HK.oku(bellek(), key, hesap)
    assert n["x"] == 1
    ikinci = HK.oku(bellek(), key, hesap)                     # yeni süreç: tablodan, kaynak okunmaz, türler korunur
    assert ikinci == ilk and n["x"] == 1
    assert isinstance(ikinci["rows"][0]["gun"], date) and ikinci["rows"][0]["tutar"] == Decimal("12.50")

    _eskit_tablo(e, "t.kalici", 700)                          # köprü kapalıyken süre doldu
    b = bellek()
    t0 = time.monotonic()
    assert HK.oku(b, key, hesap)["n"] == 1                    # eldeki hemen
    assert time.monotonic() - t0 < 0.5
    assert _bekle(lambda: n["x"] == 2) and _sakin(b, key)     # kaynak arkada okundu, tabloya yazıldı
    assert HK.oku(bellek(), key, hesap)["n"] == 2 and n["x"] == 2

    assert HK.oku(bellek("v2"), key, hesap)["n"] == 3         # okuma sorgusu değişti: eski kayıt kullanılmaz
    assert HK.oku(bellek("v2"), key, hesap, zorla=True)["n"] == 4   # «Yenile» kaynağı bekler

    monkeypatch.setenv("HIZLI_KAYIT", "0")                    # yan port ölçümü: tablo ne okunur ne yazılır
    assert HK.oku(bellek("v2"), key, hesap)["n"] == 5


def test_kalici_ayri_veritabani(tmp_path, monkeypatch):
    """`HIZLI_KAYIT_DSN`: kayıt portal veritabanına değil ayrı veritabanına yazılır (yan port ölçümü)."""
    e = _motor()
    monkeypatch.setenv("HIZLI_KAYIT_DSN", f"sqlite:///{tmp_path / 'hizli.db'}")
    k = HK.Kalici("t.ayri", lambda: (e, "t1"))
    HK.oku(HK.bellek("t.ayri", 600, kalici=k), "a", lambda: 1)
    assert not sa.inspect(e).has_table("semantic_hizli_okuma") or not e.connect().execute(
        sa.select(sa.func.count()).select_from(HK.OKUMA)).scalar()
    assert HK.oku(HK.bellek("t.ayri", 600, kalici=k), "a", lambda: 2) == 1     # ayrı veritabanından okundu


def test_kalici_dusurulen_deger_tablodan_geri_gelmez():
    e = _motor()
    n = {"x": 0}
    k = HK.Kalici("t.dusur", lambda: (e, "t1"))

    def hesap():
        n["x"] += 1
        return n["x"]

    HK.oku(HK.bellek("t.dusur", 600, kalici=k), "a", hesap)
    b = HK.bellek("t.dusur", 600, kalici=k)
    assert HK.oku(b, "a", hesap) == 1 and n["x"] == 1
    time.sleep(0.01)
    b.dusur()                                                  # yazma sonrası düşürme
    assert HK.oku(b, "a", hesap) == 2                          # eski kayıt geri yüklenmez


def test_isit_gerekirse_taze_kayitta_kaynaga_gitmez():
    e = _motor()
    n = {"x": 0}
    k = HK.Kalici("t.isit", lambda: (e, "t1"))

    def hesap():
        n["x"] += 1
        return n["x"]

    HK.oku(HK.bellek("t.isit", 600, kalici=k), "a", hesap)
    b = HK.bellek("t.isit", 600, kalici=k)
    assert b.isit_gerekirse("a", hesap) is False and n["x"] == 1
    _eskit_tablo(e, "t.isit", 700)
    b2 = HK.bellek("t.isit", 600, kalici=k)
    assert b2.isit_gerekirse("a", hesap) is True
    assert _bekle(lambda: n["x"] == 2)


# ------------------------------------------------------------------ kişi rehberi (me/profile)


def test_rehber_kisiden_bagimsiz_tablodan_ve_bayatken_hemen():
    from semantic_bridge import people as P

    e = _motor()
    P.ensure(e)
    rows = [{"SystemUserId": "a1", "FullName": "Ahmet Yıldız", "DomainName": "TIMAS\\AhmetY", "AdGuid": None, "JobTitle": "Editör"},
            {"SystemUserId": "b1", "FullName": "Büşra A", "DomainName": "TIMAS\\BusraA", "AdGuid": None}]
    calls = []

    def run(sql):
        calls.append(sql)
        return {"records": [dict(r) for r in rows], "dbMs": 42, "physicalSql": sql, "totalRows": len(rows)}

    kalici = HK.Kalici("kisi.rehber", lambda: (e, "t1"), bicim=P.directory_sql("s.dbo"))
    d1 = P.Directory(kalici=kalici)
    ilk, _ = d1.rows("Timas_MSCRM.dbo", run)
    assert [r["username"] for r in ilk] == ["ahmety", "busraa"] and len(calls) == 1
    d2 = P.Directory(kalici=kalici)                           # köprü yeniden başladı
    val, at = d2.read("Timas_MSCRM.dbo", run)
    assert val["rows"] == ilk and len(calls) == 1 and val["sorgu"]["rows"] == 2
    assert P.me(e, "t1", "AhmetY", "Ahmet", val["rows"])["crm"]["title"] == "Editör"   # kişi kendi satırını alır
    key = next(iter(d2._bellek._k))
    _eskit(d2._bellek, key, 400)
    t0 = time.monotonic()
    assert d2.rows("Timas_MSCRM.dbo", run)[0] == ilk and time.monotonic() - t0 < 0.5
    assert _bekle(lambda: len(calls) == 2)                    # CRM arkada
    d2.rows("Timas_MSCRM.dbo", run, fresh=True)               # «Yenile» bekler
    assert len(calls) == 3


# ------------------------------------------------------------------ yeni kitaplar (marketing/new-books)


def _kitap_satiri(stok, gun):
    return {"kitap_id": "11111111-2222-3333-4444-555555555555", "stok_kodu": stok, "ad": "Deniz", "yazar": "Ayşe",
            "yayinevi": "Timaş", "kitaplik": "Roman", "hedef_kitle": "Yetişkin", "statu": None, "kapak": None,
            "t_kitap": gun, "t_proje": None, "t_uretim_dagilim": None, "t_uretim_depo": None, "proje_id": None,
            "proje_adi": None, "sorumlu_ad": "Ayşe", "sorumlu_hesap": "TIMAS\\ayse"}


def test_yeni_kitap_listesi_tablodan_isitma_ve_yenile():
    from semantic_bridge.marketing import sources as MS

    e = _motor()
    fake = SayanCrm({"Yayın günü aralıktaki": [_kitap_satiri("15201.0001", date(2026, 10, 1)),
                                                _kitap_satiri("15201.0002", date(2026, 11, 1))]})
    frm, to = date(2026, 9, 29), date(2027, 1, 27)

    def crm():
        return MS.Crm(lambda: "Timas_MSCRM.dbo", runner=lambda: fake, motor=lambda: (e, "t1"))

    eski = [MS.book_row(r) for r in fake(MS.new_books_sql("Timas_MSCRM.dbo", frm, to))]       # eski hesap
    fake.sql.clear()
    a = crm().new_books(frm, to)
    assert a == eski and fake.say("Yayın günü aralıktaki") == 1
    c2 = crm()
    assert c2.new_books(frm, to) == a and fake.say("Yayın günü aralıktaki") == 1              # yeniden başladı: tablodan
    assert c2.new_books_isit(frm, to) is False                                                  # taze: CRM'e gidilmez
    c2.new_books(frm, to, fresh=True)
    assert fake.say("Yayın günü aralıktaki") == 2
    assert MS.Crm(lambda: "Timas_MSCRM.dbo", runner=lambda: fake).new_books(frm, to) == a      # motorsuz: eskisi gibi


# ------------------------------------------------------------------ Kampüs ajandası (events/me/agenda)


class _AralikCrm(SayanCrm):
    """SQL'in `new_BalangTarihi >= 'a' AND new_BalangTarihi < 'b'` koşulunu uygular (CRM tarihleri UTC)."""

    def __call__(self, sql):
        self.sql.append(sql)
        m = re.search(r"new_BalangTarihi >= '([^']+)' AND e\.new_BalangTarihi < '([^']+)'", sql)
        lo, hi = (datetime.fromisoformat(m.group(1)), datetime.fromisoformat(m.group(2))) if m else (None, None)
        rows = self.cevap["etkinlik"]
        return [dict(r) for r in rows if lo is None or lo <= r["baslangic"] < hi]


def test_ajanda_yil_okumasindan_suzulur_pencere_okumasiyla_ayni():
    from semantic_bridge import events_sources as ES

    def ev(i, bas):
        return {"id": f"{i:08d}-0000-0000-0000-000000000000", "ad": f"E{i}", "tip_id": None, "tip": None, "baslangic": bas,
                "bitis": bas, "yer": None, "il": None, "durum": 1, "ziyaret_tipi": None, "katilimci": None, "satilan": None,
                "gelir": None, "gider": None, "oduller": None, "url": None, "sorumlu_hesap": "TIMAS\\ayse", "sorumlu_ad": "Ayşe"}

    # İstanbul günü sınırları (UTC+3): 28 Eyl 21:00 UTC = 29 Eyl 00:00; gece yarısı UTC değeri gün olarak kalır.
    rows = [ev(1, datetime(2026, 9, 28, 20, 59, 59)), ev(2, datetime(2026, 9, 28, 21, 0)), ev(3, datetime(2026, 10, 5, 0, 0)),
            ev(4, datetime(2026, 11, 29, 20, 59)), ev(5, datetime(2026, 11, 29, 21, 0)), ev(6, datetime(2026, 12, 31, 21, 30)),
            ev(7, datetime(2027, 1, 2, 9, 0)), ev(8, datetime(2025, 12, 31, 22, 0))]
    fake = _AralikCrm({"etkinlik": rows})
    e = _motor()
    src = ES.Source(lambda: SayanBaglanti(fake), lambda: None, lambda: "Timas_MSCRM.dbo", motor=lambda: (e, "t1"))
    for frm, to in ((date(2026, 9, 29), date(2026, 11, 29)), (date(2026, 9, 29), date(2026, 11, 30)),
                    (date(2026, 12, 1), date(2027, 1, 31)), (date(2026, 1, 1), date(2026, 1, 2))):
        pencere = sorted(r["id"] for r in src.events(frm, to))                     # eski: kişi başına pencere okuması
        yeni = sorted(r["id"] for r in src.window_events(frm, to))                 # yeni: yıl okumasından süzme
        assert yeni == pencere, (frm, to)
    n = fake.say("new_BalangTarihi >= '2025-12-31 21:00:00'")                      # 2026 yılı okuması
    src.window_events(date(2026, 10, 1), date(2026, 10, 31))
    assert fake.say("new_BalangTarihi >= '2025-12-31 21:00:00'") == n               # aynı yıl okuması bellekten
    src2 = ES.Source(lambda: SayanBaglanti(fake), lambda: None, lambda: "Timas_MSCRM.dbo", motor=lambda: (e, "t1"))
    src2.window_events(date(2026, 10, 1), date(2026, 10, 31))
    assert fake.say("new_BalangTarihi >= '2025-12-31 21:00:00'") == n               # yeniden başladı: tablodan


# ------------------------------------------------------------------ okur meta: kural alanları


def test_okur_kural_alanlari_damga_degisince_eldeki_hemen_yenisi_arkada(monkeypatch):
    from semantic_bridge import readers as R
    from semantic_bridge import readers_core as RC
    from semantic_bridge import readers_segments as RS

    for k in ("READERS_REQUIRE_KVKK", "READERS_CONSENT_SOURCES"):
        monkeypatch.delenv(k, raising=False)
    e = _okur_engine()
    p = RC.Provider(lambda: e, lambda: "t1")
    eski = RS.field_catalog(R.profiles(e, "t1", R.settings()))                # eski hesap
    assert p.kural_alanlari() == eski
    n = {"x": 0}
    fc0 = RS.field_catalog

    def say(profs):
        n["x"] += 1
        return fc0(profs)

    monkeypatch.setattr(RS, "field_catalog", say)
    assert p.kural_alanlari() == eski and n["x"] == 0                          # damga aynı: yeniden kurulmaz
    p2 = RC.Provider(lambda: e, lambda: "t1")
    assert p2.kural_alanlari() == eski and n["x"] == 0                         # yeniden başladı: tablodan
    with e.begin() as c:                                                       # yeni okur, yeni ilgi alanı
        now = datetime(2026, 9, 2, tzinfo=timezone.utc)
        c.execute(R.READERS.insert().values(reader_id="r7", tenant_id="t1", status="aktif", is_minor=False, first_seen=now,
                                            last_touch=now, interests_json=json.dumps([{"ad": "Bilim"}]), attrs_json="{}",
                                            sources_json=json.dumps({"upload": 1}), event_count=0, updated_at=now))
        R._stamp(c, "t1")
    time.sleep(0.002)
    assert p2.kural_alanlari() == eski                                         # eldeki hemen
    assert _bekle(lambda: n["x"] == 1)
    yeni = fc0(R.profiles(e, "t1", R.settings()))
    assert _bekle(lambda: p2.kural_alanlari() == yeni) and yeni != eski


# ------------------------------------------------------------------ kanal matrisi


def test_matris_bellekten_eski_hesapla_ayni_eslesme_degisince_yeniden():
    from semantic_bridge import sorgu_yakala as Y
    from semantic_bridge.channels import mapping as M
    from semantic_bridge.channels import scorecard as SC
    from semantic_bridge.channels import store as S
    from semantic_layer.store.catalog_store import open_store
    from semantic_layer.tests import test_channels as TC

    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    S.ensure(e)
    TC._seed(e)
    mx = SC.matrix(e, TC.T, 2026, 7)                                          # test_channels ile aynı beklenen değerler
    assert [c["platform"] for c in mx["columns"]] == ["kitapyurdu", "hepsiburada", "timas.com.tr"]
    b1 = next(x for x in mx["items"] if x["stokKodu"] == "B1")
    assert b1["kanallar"]["kitapyurdu"] == {"alim": 1400, "iade": 280, "net": 1120}
    assert b1["toplam"] == pytest.approx(7 * (160 + 50 + 10))
    n = len(SC._MATRIS._k)
    with Y.yakala(e) as q:
        again = SC.matrix(e, TC.T, 2026, 7)
    assert again == mx and len(SC._MATRIS._k) == n                             # bellekten, aynı sonuç
    assert q.of("semantic_channel_book_months")                                # sorgu bilgisi: matrisi kuran okuma
    assert SC.matrix(e, TC.T, 2026, 7, sort="timas.com.tr")["items"][0]["stokKodu"] == "B3"
    assert SC.matrix(e, TC.T, 2026, 7, q="B3")["total"] == 1
    assert SC.matrix(e, TC.T, 2026, 7, size=1)["total"] == 3
    d0 = SC._girdi_damgasi(e, TC.T, 2026)
    with e.begin() as c:                                                       # Zeki AI aday yazımı (onaysız satır)
        c.execute(S.ACCOUNTS.insert().values(tenant_id=TC.T, logo_cari_kodu="ADAY1", durum="bekliyor", guncellendi=S.now()))
    M._save_candidate(e, TC.T, "ADAY1", "kitapyurdu", "zeki", 0.9, {})
    assert SC._girdi_damgasi(e, TC.T, 2026) == d0                             # aday matrisi değiştirmez: bellek geçerli
    M.decide(e, TC.T, "ayse", "HB1", {"platform": "kitapyurdu"})              # eşleme kararı → damga değişir
    assert SC._girdi_damgasi(e, TC.T, 2026) != d0
    b1b = next(x for x in SC.matrix(e, TC.T, 2026, 7)["items"] if x["stokKodu"] == "B1")
    assert b1b["kanallar"]["kitapyurdu"]["alim"] == pytest.approx(1400 + 7 * 60)   # HB1'in satışı artık Kitapyurdu'nda


# ------------------------------------------------------------------ finansal denetim arşivi


def test_denetim_arsivi_degismeyen_dosyayi_yeniden_cozmez(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from semantic_bridge import financial_audit as FA

    monkeypatch.setenv("FINANCIAL_AUDIT_DATA_DIR", str(tmp_path))
    for i in range(3):
        (tmp_path / f"{i:032x}.meta.json").write_text(json.dumps({"id": f"{i:032x}", "year": 2026, "i": i, "x": "a"}))
        os.utime(tmp_path / f"{i:032x}.meta.json", ns=((1000 + i) * 10**9, (1000 + i) * 10**9))
    app = FastAPI()
    FA.register(app, lambda: None, lambda request: None)
    c = TestClient(app)
    first = c.get("/api/v1/financial-audit/runs").json()
    assert [x["i"] for x in first["items"]] == [2, 1, 0] and first["total"] == 3
    ad = tmp_path / f"{1:032x}.meta.json"
    ad.write_text(json.dumps({"id": f"{1:032x}", "year": 2026, "i": 1, "x": "b"}))    # aynı boyut, aynı an: çözülmüş içerik
    os.utime(ad, ns=(1001 * 10**9, 1001 * 10**9))
    assert c.get("/api/v1/financial-audit/runs").json() == first
    (tmp_path / f"{9:032x}.meta.json").write_text(json.dumps({"id": f"{9:032x}", "year": 2026, "i": 9}))
    os.utime(tmp_path / f"{9:032x}.meta.json", (2000, 2000))
    (tmp_path / f"{0:032x}.meta.json").unlink()
    ad.write_text(json.dumps({"id": f"{1:032x}", "year": 2026, "i": 1, "x": "cc"}))   # değişti: yeniden okunur
    os.utime(ad, (1001, 1001))
    out = c.get("/api/v1/financial-audit/runs").json()
    assert [x["i"] for x in out["items"]] == [9, 2, 1] and out["items"][2]["x"] == "cc"
