"""M10 İlk baskı — kitap kartındaki «Pazardaki benzer kitaplar (dağıtımcı kataloğu)»: kategori eşlemesi (seçim,
kitabın Başarı kaydı, CRM türü), küme koşulları (alt kategori, sayfa ±%25, TİMAŞ dışı, son görüntü), son üç basım
yılında baskı dağılımı (bilinmeyen ayrı), en yüksek baskıdaki 10 kitap, fiyat medyanı, geçmiş isteyen alanların boş
dönmesi, iki görüntüde çıkış, sorgu bilgisi ve uç.

Veriler yapaydır; gerçek katalogla kabul test sunucusunda.
"""

from __future__ import annotations

from datetime import date

import pytest
import sqlalchemy as sa

from semantic_bridge import pazar_dagitim as D
from semantic_bridge import provenance as P
from semantic_bridge.management import ilk_baski_pazar as IBP
from semantic_layer.store.catalog_store import open_store

T = "t1"
D1, D2 = date(2026, 9, 25), date(2026, 10, 1)
R, C = "Edebiyat>Roman", "Çocuk>Roman"


def _b(barkod, *, yil="2025", baski="1. Baskı", fiyat=100.0, sayfa="200", kategori=R, marka="Rakip Yayınları", stok=50):
    return {"barkod": barkod, "urun_ad": f"Kitap {barkod[-3:]}", "yazar": "Yazar", "cevirmen": "", "marka": marka,
            "kategori": kategori, "sayfasayisi": sayfa, "kapak_turu": "Karton Kapak", "kagit_cinsi": "2. Hamur",
            "basimyili": yil, "depo_stok": str(stok), "satis_fiyat": fiyat, "iskonto": "35", "stok_durum": "Satışta",
            "baski_sayisi": baski}


def _rows(b1_stok=50):
    rows = [
        _b("9780000000001", yil="2026", baski="1. Baskı", fiyat=100, sayfa="200", stok=b1_stok),
        _b("9780000000002", yil="2025", baski="2. Baskı", fiyat=120, sayfa="180"),
        _b("9780000000003", yil="2024", baski="5. Baskı", fiyat=140, sayfa="240"),
        _b("9780000000004", yil="2025", baski="", fiyat=90, sayfa="160"),             # baskısı yazılmamış
        _b("9780000000005", yil="2019", baski="12. Baskı", fiyat=200, sayfa="220"),   # eski yıl, en yüksek baskı
    ]
    rows += [_b(f"97800000001{i:02d}", yil="2018", baski="3. Baskı", fiyat=110, sayfa="200") for i in range(8)]
    rows += [
        _b("9780000000901", sayfa="300"),                                  # sayfa aralığı dışında
        _b("9780000000902", sayfa=""),                                     # sayfası yok
        _b("9780000000903", marka="Timaş Yayınları", baski="20. Baskı"),   # TİMAŞ grubu
        _b("9780000000904", kategori=C, baski="4. Baskı"),                 # aynı alt ad, başka üst kategori
        _b("9780000000905", kategori="Edebiyat>Öykü", stok=40),
    ]
    return rows


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("PAZAR_DAGITIM_ARALIK_GUN", "35")
    e = open_store("sqlite://").engine
    D._ready.discard(id(e))
    D.ensure(e)
    return e


def _load(e, d=D1, **kw):
    D.apply(e, T, "basari", d, D.parse(_rows(**kw), "basari"), yontem="elle")
    with e.begin() as c:
        c.execute(D.TITLES.update().where(D.TITLES.c.barkod == "9780000000903").values(timas=True))


def test_not_read_yet(engine):
    out = IBP.similar(engine, T, code="X", pages=200, genre="Roman")
    assert out["durum"] == "okunmadi" and out["kaynak"]["tarih"] is None
    assert IBP.kaynaklar(engine, T, out) is None


def test_cluster_distribution_top_and_price(engine):
    _load(engine)
    out = IBP.similar(engine, T, pages=200, genre="Aşk, Roman")
    assert out["durum"] == "hazir"
    k = out["kategori"]
    assert (k["secili"], k["yontem"]) == (R, "tur_eslesmesi")
    assert k["adaylar"] == [R, C]                                   # aynı alt ad: başlığı çok olan önce
    assert (out["kosul"]["sayfaAlt"], out["kosul"]["sayfaUst"]) == (150, 250)
    assert out["kume"]["baslik"] == 13                              # sayfa dışı, sayfasız, TİMAŞ, başka kategori girmez
    assert out["kume"]["fiyatMedyan"] == 110
    b = out["baskilar"]
    assert b["yillar"] == [2024, 2025, 2026]
    assert (b["baslik"], b["bilinen"], b["bilinmeyen"], b["ilk"], b["ikinci"], b["ucVeUstu"]) == (4, 3, 1, 1, 1, 1)
    assert b["ikinciyeUlasan"] == pytest.approx(2 / 3, abs=1e-4) and b["ucuncuyeUlasan"] == pytest.approx(1 / 3, abs=1e-4)
    y25 = next(y for y in b["yilBazinda"] if y["yil"] == 2025)
    assert (y25["baslik"], y25["bilinen"], y25["ikinciyeUlasan"]) == (2, 1, 1.0)
    top = out["enCokBasilan"]
    assert len(top) == 10 and [t["baski"] for t in top[:2]] == [12, 5]
    assert all(t["barkod"] != "9780000000903" for t in top)         # TİMAŞ en yüksek baskıda olsa da girmez
    assert out["cikis"]["toplam"] is None and out["cikis"]["pencere"] is None and out["cikis"]["not"]
    assert out["ilkYilHizi"]["deger"] is None


def test_sources_cover_every_number(engine):
    _load(engine)
    out = IBP.similar(engine, T, pages=200, genre="Roman")
    k = P.ekle(out, IBP.kaynaklar(engine, T, out))["kaynaklar"]
    assert P.uncovered_numbers(out) == []
    assert P.problems(out) == []
    sql = k["sources"]["ilkbaski.pazar.kume"]["sql"]
    assert "semantic_pazar_dagitim_titles" in sql and "Edebiyat>Roman" in sql and "2026-09-25" in sql
    assert k["sources"]["ilkbaski.pazar.kume"]["origin"] == ["pazar.dagitim.basari"]


def test_own_basari_record_wins_over_genre(engine):
    _load(engine)
    D.store_pairs(engine, T, {("9780000000904", "15201.01.0001")})
    out = IBP.similar(engine, T, code="15201.01.0001", pages=200, genre="Roman")
    assert (out["kategori"]["secili"], out["kategori"]["yontem"]) == (C, "kitap_kaydi")
    assert out["kume"]["baslik"] == 1
    k = P.ekle(out, IBP.kaynaklar(engine, T, out, "15201.01.0001"))["kaynaklar"]
    assert "ilkbaski.pazar.kitap" in k["sources"] and P.problems(out) == []


def test_user_choice_and_missing_category(engine):
    _load(engine)
    out = IBP.similar(engine, T, pages=200, genre="Roman", kategori="Edebiyat>Öykü")
    assert (out["kategori"]["secili"], out["kategori"]["yontem"], out["kume"]["baslik"]) == ("Edebiyat>Öykü", "secim", 1)
    bad = IBP.similar(engine, T, pages=200, kategori="Yok>Böyle")
    assert bad["durum"] == "kategori_yok" and bad["kategori"]["hata"]
    none = IBP.similar(engine, T, pages=200, genre="Felsefe")
    assert none["durum"] == "kategori_yok" and none["kategori"]["adaylar"] == []
    cats = IBP.categories(engine, T)
    roman = next(c for c in cats["items"] if c["kategori"] == R)
    assert (roman["ust"], roman["alt"], roman["baslik"]) == ("Edebiyat", "Roman", 15)   # TİMAŞ başlığı sayılmaz


def test_no_pages_no_band(engine):
    _load(engine)
    out = IBP.similar(engine, T, pages=None, genre="Roman")
    assert out["kosul"]["sayfaAlt"] is None and out["kume"]["baslik"] == 15              # sayfa dışı ve sayfasız da girer


def test_outflow_after_two_snapshots(engine):
    _load(engine, D1)
    _load(engine, D2, b1_stok=20)                                   # küme içi 30 çıkış; öykü değişmedi
    out = IBP.similar(engine, T, pages=200, genre="Roman")
    assert out["cikis"]["toplam"] == 30 and out["cikis"]["pencere"] == {"bas": "2026-09-25", "son": "2026-10-01"}
    assert out["kaynak"]["tarih"] == "2026-10-01" and out["kaynak"]["ilkGoruntu"] == "2026-09-25"
    k = P.ekle(out, IBP.kaynaklar(engine, T, out))["kaynaklar"]
    assert P.uncovered_numbers(out) == [] and P.problems(out) == []
    assert "semantic_pazar_dagitim_obs" in k["sources"]["ilkbaski.pazar.cikis"]["sql"]


def test_endpoint(engine):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    _load(engine)
    app = FastAPI()
    IBP.register(app, "/fp", lambda request: "ali", lambda: (engine, T), lambda code: None)
    cl = TestClient(app)
    r = cl.get("/fp/market", params={"pages": "200", "genre": "Roman"})
    assert r.status_code == 200
    j = r.json()
    assert j["durum"] == "hazir" and j["kume"]["baslik"] == 13 and "kaynaklar" in j
    assert not j["kaynaklar"].get("error")
    c = cl.get("/fp/market/categories").json()
    assert c["tarih"] == "2026-09-25" and any(x["kategori"] == R for x in c["items"])


def test_forecast_model_untouched():
    """Bağlam bilgisi tahmine karışmaz: tahmin çekirdeği bu modülü içe aktarmaz."""
    import inspect

    from semantic_bridge.management import ilk_baski, ilk_baski_model

    for mod in (ilk_baski, ilk_baski_model):
        assert "ilk_baski_pazar" not in inspect.getsource(mod)
        assert "pazar_dagitim" not in inspect.getsource(mod)
    assert isinstance(IBP.cluster_stmt(T, D1, R, (150, 250)), sa.sql.Select)
