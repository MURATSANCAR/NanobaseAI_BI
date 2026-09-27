"""M46 Bütçe: taban penceresi, öneri, onay akışı (iki göz), revizyon, hedef–gerçekleşme ve %80 sapma uyarısı,
diğer modüllerin okuduğu onaylı hedef sözleşmesi, yetki kuralları.

Veriler yapaydır ve yalnız hesap kurallarını sınar; gerçek Logo/CRM kabulü test sunucusunda (günlük 2026-09-28).
"""

from __future__ import annotations

from datetime import date

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import budget as B
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    B._ready.discard(id(e))
    B.ensure(e)
    return e


def _seed(engine, end: date = date(2026, 8, 17)):
    """2025 tam yıl + 2026 Ocak–Ağustos. İki backlist kitap, 2025'te çıkmış bir kohort kitabı, 2026'da çıkacak iki
    yeni kitap, bir ticari ürün (157), iki departman satırı."""
    rows = []
    for m in range(1, 13):
        rows.append(dict(year=2025, month=m, stok_kodu="K1", adet=100, ciro=10_000, maliyet=2_500, maliyetli_ciro=10_000))
        rows.append(dict(year=2025, month=m, stok_kodu="K2", adet=10, ciro=2_000, maliyet=0, maliyetli_ciro=0))
        rows.append(dict(year=2025, month=m, stok_kodu="15701.01.1", adet=5, ciro=500, maliyet=100, maliyetli_ciro=500))
    for m in range(7, 13):
        rows.append(dict(year=2025, month=m, stok_kodu="N25", adet=60, ciro=6_000, maliyet=1_800, maliyetli_ciro=6_000))
    for m in range(1, 9):
        rows.append(dict(year=2026, month=m, stok_kodu="K1", adet=80 if m < 8 else 40, ciro=9_600 if m < 8 else 4_800,
                         maliyet=2_400, maliyetli_ciro=9_600))
        rows.append(dict(year=2026, month=m, stok_kodu="K2", adet=2, ciro=440, maliyet=0, maliyetli_ciro=0))
    for m in range(3, 9):
        rows.append(dict(year=2026, month=m, stok_kodu="N26A", adet=30, ciro=3_300, maliyet=900, maliyetli_ciro=3_300))
    exp = []
    for y, ms in ((2025, range(1, 13)), (2026, range(1, 9))):
        for m in ms:
            exp.append(dict(year=y, month=m, merkez_kodu="B04-PAZ-01", hesap="760", merkez_adi="PAZARLAMA", hesap_adi="Pazarlama", tutar=1_000 if y == 2025 else 1_300))
            exp.append(dict(year=y, month=m, merkez_kodu="B01-GMD-01", hesap="770", merkez_adi="GENEL MÜDÜRLÜK", hesap_adi="Genel yönetim", tutar=2_000))
    books = [
        dict(stok_kodu="K1", ad="Eski Kitap", yayinevi="Timaş Yayınları", kitaplik="Roman", ilk_yayin="2015-03-01"),
        dict(stok_kodu="K2", ad="Az Satan", yayinevi="Timaş Çocuk", kitaplik="Masal", ilk_yayin=None),
        dict(stok_kodu="N25", ad="Geçen Yılın Yenisi", yayinevi="Timaş Yayınları", kitaplik="Roman", ilk_yayin="2025-07-01"),
        dict(stok_kodu="N26A", ad="Bu Yılın Yenisi", yayinevi="Timaş Yayınları", kitaplik="Roman", ilk_yayin="2026-03-01"),
        dict(stok_kodu="N26B", ad="Gelecek Ay", yayinevi="Timaş Yayınları", kitaplik="Roman", ilk_yayin="2026-10-01"),
        dict(stok_kodu="N27", ad="Seneye", yayinevi="Timaş Çocuk", kitaplik="Masal", ilk_yayin="2027-04-01"),
        # yayın tarihi geçmiş ama Logo'da kartı yok: o kodla yayımlanmamış, hedef almaz
        dict(stok_kodu="E26", ad="Yalnız e-kitap", yayinevi="Timaş Yayınları", kitaplik="Roman", ilk_yayin="2026-05-01"),
    ]
    for b in books:
        b["in_logo"] = b["stok_kodu"] in {"K1", "K2", "N25", "N26A"}
    with engine.begin() as c:
        c.execute(B.SALES.insert(), rows)
        c.execute(B.EXPENSES.insert(), exp)
        c.execute(B.BOOKINFO.insert(), books)
    B.meta_set(engine, "data_end", {"date": end.isoformat()})


def _plan(items, scenario):
    return next(p for p in items if p["scenario"] == scenario)


def _books(engine, plan_id, **kw):
    return {b["stokKodu"]: b for b in B.books(engine, T, plan_id, **kw)["items"]}


# ------------------------------------------------------------------ pencere ve dağılım

def test_window_is_previous_year_when_complete_else_last_twelve_full_months():
    assert B.window(2026, date(2026, 8, 17))["label"] == "2025 yılı"
    w = B.window(2027, date(2026, 8, 17))
    assert w["label"] == "Ağustos 2025 – Temmuz 2026"
    assert B.from_index(w["start"]) == (2025, 8) and B.from_index(w["end"] - 1) == (2026, 7)
    # ayın son günü dahilse o ay tamdır
    assert B.from_index(B.window(2027, date(2026, 8, 31))["end"] - 1) == (2026, 8)
    with pytest.raises(B.BudgetError):
        B.window(2027, None)


def test_elapsed_shares_prorate_the_current_month():
    e = B.elapsed_shares(2026, date(2026, 8, 17))
    assert e[:7] == [1.0] * 7 and e[7] == pytest.approx(17 / 31) and e[8:] == [0.0] * 4
    assert B.elapsed_shares(2027, None) == [0.0] * 12
    w = B.active_weights([1 / 12] * 12, 10)
    assert sum(w) == pytest.approx(1) and w[:9] == [0.0] * 9


# ------------------------------------------------------------------ öneri

def test_generate_builds_three_scenarios_from_the_2025_base(engine):
    _seed(engine)
    items = B.generate(engine, T, "hazirlayan", {"year": 2026, "params": {"fiyat": 0.2}})
    assert [p["scenario"] for p in items] == ["muhafazakar", "temel", "iyimser"]
    assert all(p["status"] == "taslak" for p in items)
    temel = _plan(items, "temel")
    assert temel["basis"]["pencere"] == "2025 yılı"
    b = _books(engine, temel["id"])
    # ticari ürün (157) hedefe girmez
    assert "15701.01.1" not in b
    # backlist: 1.200 × 1,10 = 1.320 adet; birim fiyat 100 × 1,2 = 120 → 158.400
    assert b["K1"]["segment"] == "backlist" and b["K1"]["adet"] == 1320 and b["K1"]["ciro"] == pytest.approx(158_400)
    assert b["K1"]["marj"] == pytest.approx(0.75)
    # maliyeti olmayan kitap yayınevi ortalamasını alır (Timaş Çocuk'ta maliyet yok → şirket ortalaması)
    assert b["K2"]["oneri"]["marjKaynak"] == "şirket ortalaması"
    # 2025'te çıkan kitap taban yılının içinde: backlist
    assert b["N25"]["segment"] == "backlist" and b["N25"]["adet"] == round(360 * 1.1)
    # 2026'da çıkanlar yeni kitap: kohort (N25) ay başına 60 adet × satış ayı
    assert b["N26A"]["segment"] == "yeni" and b["N26A"]["oneri"]["satisAyi"] == 10
    assert b["N26A"]["adet"] == round(60 * 10 * 1.1)
    assert b["N26B"]["oneri"]["satisAyi"] == 3  # kartı yok ama yayın tarihi henüz gelmedi
    assert "N27" not in b and "E26" not in b
    iyimser = _books(engine, _plan(items, "iyimser")["id"])
    assert iyimser["K1"]["adet"] == 1380
    # departman: 2025 aynı ay × (1 + gider artışı ölçüsü)
    dep = {(d["merkezKodu"], d["hesap"]): d for d in B.departments(engine, T, temel["id"])["items"]}
    g = temel["params"]["gider"]
    assert g == pytest.approx((8 * 3_300) / (8 * 3_000) - 1)
    assert dep[("B04-PAZ-01", "760")]["yillik"] == pytest.approx(12_000 * (1 + g))


def test_measured_price_increase_uses_books_sold_in_both_periods(engine):
    _seed(engine)
    p = B.default_params(engine, 2027)
    # K1: 2026 Oca–Tem birim 120, 2025 aynı aylar 100; K2: 220 / 200; N26A 2025'te yok → dışarıda
    num = 7 * 9_600 + 7 * 440
    den = 7 * 80 * 100 + 7 * 2 * 200
    assert p["fiyat"] == pytest.approx(round(num / den - 1, 4))
    assert p["tahmin"] is True and p["pencere"] == "Ağustos 2025 – Temmuz 2026"


def test_forecast_replaces_the_backlist_base_beyond_the_data(engine):
    _seed(engine)
    fc = {"start": "2026-08", "p50": {"K1": [50.0] * 12}}
    items = B.generate(engine, T, "u", {"year": 2027, "scenarios": ["temel"], "params": {"fiyat": 0}}, fc)
    b = _books(engine, items[0]["id"])
    assert b["K1"]["oneri"]["yontem"] == "tahmin" and b["K1"]["adet"] == round(600 * 1.1)
    assert b["K2"]["oneri"]["yontem"] == "gecmis"
    # 2026'da çıkan kitaplar 2027 için yeni değil, backlist; 2027'de çıkacak yeni
    assert b["N27"]["segment"] == "yeni"
    prog = {p["yayinevi"]: p for p in B.program(engine, T, items[0]["id"])["items"]}
    assert prog["Timaş Çocuk"]["bilinen"] == 1


def test_recompute_keeps_hand_edited_rows(engine):
    _seed(engine)
    temel = B.generate(engine, T, "u", {"year": 2026, "scenarios": ["temel"]})[0]
    out, diff = B.update_book(engine, T, "u", temel["id"], "K1", {"adet": 5000, "ciro": 600000})
    assert out["elle"] and diff["adet"]["yeni"] == 5000
    B.recompute(engine, T, "u", temel["id"], {"params": {"hacim": {"temel": 0.5}}})
    b = _books(engine, temel["id"])
    assert b["K1"]["adet"] == 5000
    assert b["K2"]["adet"] == round(120 * 1.5)
    with pytest.raises(B.BudgetError):
        B.update_book(engine, T, "u", temel["id"], "K1", {"adet": -1})


# ------------------------------------------------------------------ onay akışı

def test_two_eyes_approval_archives_the_previous_plan_and_revision_replaces_it(engine):
    _seed(engine)
    a, b = B.generate(engine, T, "hazirlayan", {"year": 2026, "scenarios": ["temel", "iyimser"]})
    B.submit(engine, T, "hazirlayan", a["id"])
    with pytest.raises(B.BudgetError) as e:
        B.decide(engine, T, "hazirlayan", a["id"], True)
    assert e.value.status == 409
    with pytest.raises(B.BudgetError):
        B.decide(engine, T, "mudur", a["id"], False)  # gerekçesiz geri gönderme
    B.decide(engine, T, "mudur", a["id"], True, "uygun")
    assert B.plan_summary(engine, T, a["id"])["status"] == "onayli"
    with pytest.raises(B.BudgetError):
        B.update_book(engine, T, "u", a["id"], "K1", {"adet": 1})  # yürürlükteki plan değişmez
    B.submit(engine, T, "hazirlayan", b["id"])
    B.decide(engine, T, "mudur", b["id"], True)
    assert B.plan_summary(engine, T, a["id"])["status"] == "arsiv"
    assert B.approved_targets(engine, T, 2026)["plan"]["id"] == b["id"]
    with pytest.raises(B.BudgetError):
        B.revise(engine, T, "u", b["id"], "")
    r = B.revise(engine, T, "hazirlayan", b["id"], "Okul sezonu zayıf")
    assert r["status"] == "taslak" and r["revisionOf"] == b["id"] and r["totals"]["kitap"] == B.plan_summary(engine, T, b["id"])["totals"]["kitap"]
    B.update_book(engine, T, "hazirlayan", r["id"], "K1", {"adet": 100, "ciro": 12_000})
    B.submit(engine, T, "hazirlayan", r["id"])
    B.decide(engine, T, "mudur", r["id"], True)
    t = B.approved_targets(engine, T, 2026, codes=["K1"])
    assert t["plan"]["id"] == r["id"] and t["plan"]["revisionOf"] == b["id"] and t["items"][0]["hedef"]["adet"] == 100
    info = B.deviations(engine, T, 2026, status="bilgi")["items"]
    assert len(info) == 3 and all(i["kind"] == "revizyon" for i in info)
    with pytest.raises(B.BudgetError):
        B.delete_plan(engine, T, r["id"])


# ------------------------------------------------------------------ izleme ve uyarı

def _approve(engine, year=2026, scenario="temel", scope=1.0):
    p = B.generate(engine, T, "hazirlayan", {"year": year, "scenarios": [scenario], "params": {"fiyat": 0, "uyariKapsam": scope}})[0]
    B.submit(engine, T, "hazirlayan", p["id"])
    B.decide(engine, T, "mudur", p["id"], True)
    return p


def test_tracking_expected_to_date_and_the_80_percent_alert(engine):
    _seed(engine)
    p = _approve(engine)
    b = _books(engine, p["id"])
    k1 = b["K1"]["izleme"]
    # 2025 aylık dağılımı düz olmadığından beklenen, ciro payının 17 Ağustos'a kadarki kısmıdır
    w = B.normalized(B.plan_summary(engine, T, p["id"])["basis"]["dagilim"]["ciro"])
    share = B.expected_share(w, B.elapsed_shares(2026, date(2026, 8, 17)))
    assert k1["beklenenCiro"] == pytest.approx(b["K1"]["ciro"] * share, rel=1e-6)
    assert k1["gercekCiro"] == pytest.approx(7 * 9_600 + 4_800)
    assert k1["durum"] == "izle"  # 72.000 / ~77.600
    # Az satan kitap %80 altında
    assert b["K2"]["izleme"]["durum"] == "sapma"
    # Ekim'de çıkacak kitapta beklenen yok
    assert b["N26B"]["izleme"]["durum"] == "baslamadi"
    ev = B.evaluate_alerts(engine, T, 2026)
    assert ev["opened"] >= 1
    dev = B.deviations(engine, T, 2026)
    keys = {(d["scope"], d["key"]) for d in dev["items"]}
    assert ("kitap", "K2") in keys
    k2 = next(d for d in dev["items"] if d["key"] == "K2")
    assert k2["modules"] == ["M15", "M17", "M18", "M29", "M30"] and k2["ratio"] < 0.8
    # departman: bütçe 2025 × ölçülen %10; pazarlama 2026'da %30 yüksek → aşım, genel yönetim yerinde
    cost = {d["key"] for d in dev["items"] if d["kind"] == "gider"}
    assert cost == {"B04-PAZ-01|760"}
    # hedef düşürülünce (revizyon) uyarı kapanır
    r = B.revise(engine, T, "hazirlayan", p["id"], "hedef fazla")
    B.update_book(engine, T, "hazirlayan", r["id"], "K2", {"adet": 10, "ciro": 1_000})
    B.submit(engine, T, "hazirlayan", r["id"])
    B.decide(engine, T, "mudur", r["id"], True)
    B.evaluate_alerts(engine, T, 2026)
    assert not any(d["key"] == "K2" for d in B.deviations(engine, T, 2026)["items"])
    closed = B.deviations(engine, T, 2026, status="kapandi")["items"]
    assert any(d["key"] == "K2" for d in closed)


def test_book_alerts_cover_the_books_that_make_the_target(engine):
    """Varsayılan kapsam: hedef cirosunun %80'ini oluşturan kitaplar. Küçük kitap listede «sapma» kalır, uyarı açmaz."""
    _seed(engine)
    p = _approve(engine, scope=0.8)
    assert B.plan_summary(engine, T, p["id"])["params"]["uyariKapsam"] == 0.8
    b = _books(engine, p["id"])
    assert b["K2"]["izleme"]["durum"] == "sapma"
    B.evaluate_alerts(engine, T, 2026)
    keys = {d["key"] for d in B.deviations(engine, T, 2026)["items"] if d["scope"] == "kitap"}
    assert "K2" not in keys
    tr = B.tracking(engine, T, 2026)
    assert tr["uyariKapsam"]["pay"] == 0.8 and "K2" not in B.alert_scope(
        [type("R", (), {"stok_kodu": k, "ciro": v["ciro"]}) for k, v in b.items()], 0.8)
    with pytest.raises(B.BudgetError):
        B.generate(engine, T, "u", {"year": 2026, "scenarios": []})


def test_department_overrun_opens_a_cost_alert(engine):
    _seed(engine)
    p = B.generate(engine, T, "h", {"year": 2026, "scenarios": ["temel"], "params": {"gider": 0}})[0]
    B.submit(engine, T, "h", p["id"])
    B.decide(engine, T, "m", p["id"], True)
    dep = {(d["merkezKodu"], d["hesap"]): d for d in B.departments(engine, T, p["id"])["items"]}
    assert dep[("B04-PAZ-01", "760")]["izleme"]["durum"] == "asim"
    budget_ytd = 1_000 * (7 + 17 / 31)
    assert dep[("B04-PAZ-01", "760")]["izleme"]["kullanim"] == pytest.approx(8 * 1_300 / budget_ytd, rel=1e-3)
    B.evaluate_alerts(engine, T, 2026)
    cost = [d for d in B.deviations(engine, T, 2026, kind="gider")["items"]]
    assert any(d["key"] == "B04-PAZ-01|760" for d in cost)


def test_contract_monthly_targets_sum_to_the_annual_target(engine):
    _seed(engine)
    assert B.approved_targets(engine, T, 2026)["plan"] is None
    _approve(engine)
    t = B.approved_targets(engine, T, 2026, segment="yeni")
    assert t["items"] and all(i["segment"] == "yeni" for i in t["items"])
    n = next(i for i in t["items"] if i["stokKodu"] == "N26A")
    assert sum(m["adet"] for m in n["aylik"]) == pytest.approx(n["hedef"]["adet"], abs=0.1)
    assert all(m["adet"] == 0 for m in n["aylik"][:2])  # mart öncesi satış beklenmez
    assert "gerceklesme" in n
    with engine.connect() as c:
        rows = c.execute(sa.text("SELECT stok_kodu, hedef_adet FROM semantic_budget_approved_targets WHERE year = 2026")).all()
    assert {r[0] for r in rows} >= {"K1", "N26A"}


def test_notify_sends_one_summary_and_marks_alerts(engine):
    _seed(engine)
    _approve(engine)
    B.evaluate_alerts(engine, T, 2026)
    sent = []
    out = B.notify(engine, T, 2026, ["a@timas.com.tr"], "https://portal/timas/butce", lambda s, t, to: sent.append((s, t, to)) or "sent")
    assert out["status"] == "sent" and len(sent) == 1 and "kitap" in sent[0][1]
    assert B.notify(engine, T, 2026, ["a@timas.com.tr"], "", lambda *a: "sent")["status"] == "yok"
    assert B.notify(engine, T, 2026, [], "", lambda *a: "sent")["status"] == "yok"


# ------------------------------------------------------------------ yetki

def test_budget_rules():
    assert A.rule_for("/api/v1/budget/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/budget/plans") == frozenset({"sayfa:butce"})
    # Okuyan modüller sayfa anahtarını ekler (M29 ilk dağılım).
    assert "sayfa:butce" in A.rule_for("/api/v1/budget/targets")
    assert A.features_for("POST", "/api/v1/budget/plans/generate") == ["ozellik:butce.duzenle"]
    assert A.features_for("PATCH", "/api/v1/budget/plans/abc/books/K1") == ["ozellik:butce.duzenle"]
    assert A.features_for("POST", "/api/v1/budget/plans/abc/approve") == []
    assert A.features_for("POST", "/api/v1/budget/plans/abc/reject") == []
    assert A.features_for("GET", "/api/v1/budget/plans/abc/books") == []
    assert A.features_for("GET", "/api/v1/budget/plans/abc/export.csv") == ["ozellik:veri.disa-aktar"]
    assert "ozellik:butce.onay" in A.explicit_keys()
    assert "ozellik:butce.duzenle" in A.all_keys() and "sayfa:butce" in A.all_keys()
