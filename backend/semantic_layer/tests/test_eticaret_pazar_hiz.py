"""M34 pazar yeri uçları hızı (2026-09-29): Logo okuması portal tablosunda ve bellekte, ekranı açan kişi Logo'yu beklemez.

Eski hesap = yeni hesap: eski uç kodunun (istekte Logo okuyup `marketplace_summary` / `marketplace_books`) birebir kopyası
aynı sahte Logo verisiyle koşturulur, yeni ucun cevabıyla karşılaştırılır. Sonra: köprü yeniden başlamış gibi yeni bir
istemci Logo'ya hiç gitmeden aynı cevabı tablodan verir; eski kayıt hemen verilir ve yenisi arkada istenir; «yenile»
Logo'yu bekler; gece turu tabloyu yazar.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import eticaret as E
from semantic_bridge import eticaret_pazar as PZ
from semantic_bridge import eticaret_sources as src
from semantic_layer.tests.test_eticaret import ST, T, _c, _client, _items, _p, _run
from semantic_layer.tests.test_eticaret import engine  # noqa: F401 — fixture

FIRMS = {2025: "211", 2026: "411"}
CUT = date(2026, 8, 17)


class FakeLogo:
    """Firma kopyasına göre satır döndüren sahte Logo; her çağrıyı sayar."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.fail = False

    def runner(self, path, timeout=None):
        def run(sql):
            if self.fail:
                raise src.SourceError("Veritabanına şu an ulaşılamıyor.")
            self.sent.append(sql)
            y = 2025 if "LG_211" in sql else 2026
            if "L_CAPIPERIOD" in sql:
                return [{"FIRMNR": 211}, {"FIRMNR": 411}]
            if "MAX(DATE_)" in sql:
                return [{"son": CUT}]
            if "YEAR(SH.DATE_)" in sql:
                out = []
                for kod, unvan, base in (("120.01", "Kitapyurdu", 1000.0), ("120.02", "Hepsiburada", 700.0), ("120.03", "Trendyol", 0.0)):
                    for ay in range(1, 9):
                        out.append({"kod": kod, "unvan": unvan, "kanal": "E-TICARET", "yil": y, "ay": ay,
                                    "satis": base * ay + (y - 2024) * 13.25, "iade": base * 0.07 * ay,
                                    "satis_adet": 10 * ay, "iade_adet": ay // 3})
                return out
            if "AS stok" in sql:
                return [{"stok": "K31", "ad": "Stoksuz", "satis_adet": 50, "iade_adet": 1, "ciro": 500.0, "son": date(y, 8, 1)},
                        {"stok": "K30", "ad": "Çekilen", "satis_adet": 5, "iade_adet": 0, "ciro": 90.5, "son": date(y, 7, 2)},
                        {"stok": "K99", "ad": "Sitede yok", "satis_adet": 3, "iade_adet": 0, "ciro": 12.0, "son": date(y, 6, 3)}]
            return []
        return run


@pytest.fixture
def logo(monkeypatch):
    f = FakeLogo()
    monkeypatch.setattr(src, "runner", f.runner)
    monkeypatch.setattr(src, "firms_by_year", lambda run: (run("SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1"),
                                                          dict(FIRMS))[1])
    return f


def _seed(engine):
    items = _items([_p("30", "9786050000301", "Çekilen", price=100.0, views=100, sales=5),
                    _p("31", "9786050000318", "Stoksuz", price=100.0, views=50, sales=1)],
                   [_c("c30", "9786050000301", "Çekilen", "K30"), _c("c31", "9786050000318", "Stoksuz", "K31")],
                   stock={"K30": 500.0, "K31": 0.0}, sales={"K31": {"adet": 900.0, "ciro": 1.0}, "K30": {"adet": 12.0, "ciro": 5.0}})
    _run(engine, items)


# ------------------------------------------------------------------ eski uç kodunun kopyası (değiştirilmeden)


def _old_markets(year: int, channels: list[str]) -> dict:
    run = src.runner("/yok")
    firms = src.firms_by_year(run)
    cut = src.read_data_end(run, firms)
    this, prev = E.marketplace_windows(year, cut)
    rows = src.read_marketplaces(run, firms, channels, *prev) + src.read_marketplaces(run, firms, channels, *this)
    out = E.marketplace_summary(rows, year, cut)
    out["kanallar"] = channels
    out["yillar"] = sorted(firms)
    return out


def _old_stock_risk(engine, year: int, st: dict) -> tuple[list, str]:
    run = src.runner("/yok")
    firms = src.firms_by_year(run)
    cut = src.read_data_end(run, firms)
    this, _ = E.marketplace_windows(year, cut)
    rows = src.read_channel_books(run, firms, st["channels"], *this)
    books = E.marketplace_books(rows, E.items_by_code(engine, T, [r["stok"] for r in rows]), st)
    return [b for b in books if b["tukenmeRiski"]], cut.isoformat()


def _plain(out: dict) -> dict:
    return {k: v for k, v in out.items() if k not in ("kaynaklar", "okundu")}


# ------------------------------------------------------------------ testler


def test_new_endpoints_equal_the_old_computation(engine, logo):
    _seed(engine)
    c, _ = _client(engine, {})
    a = {"cookie": "a"}
    for yil in ("?yil=2026", "?yil=2025", ""):
        got = c.get(f"/api/v1/eticaret/marketplaces{yil}", headers=a).json()
        year = int(yil[5:]) if yil else CUT.year
        assert _plain(got) == _old_markets(year, ST["channels"]), yil
        assert got["okundu"]
    risk = c.get("/api/v1/eticaret/marketplaces/stock-risk?yil=2026", headers=a).json()
    old_items, old_cut = _old_stock_risk(engine, 2026, ST)
    assert risk["items"] == old_items and risk["kesim"] == old_cut
    assert [b["stok"] for b in risk["items"]] == ["K31"]
    no_year = c.get("/api/v1/eticaret/marketplaces/stock-risk", headers=a).json()
    assert no_year["items"] == old_items and no_year["yil"] == 2026


def test_second_call_and_restart_do_not_touch_logo(engine, logo):
    _seed(engine)
    a = {"cookie": "a"}
    c1, _ = _client(engine, {})
    first = c1.get("/api/v1/eticaret/marketplaces?yil=2026", headers=a).json()
    risk1 = c1.get("/api/v1/eticaret/marketplaces/stock-risk?yil=2026", headers=a).json()
    n = len(logo.sent)
    assert n > 0
    again = c1.get("/api/v1/eticaret/marketplaces?yil=2026", headers=a).json()
    assert len(logo.sent) == n and _plain(again) == _plain(first)
    # Köprü yeniden başladı (yeni kayıt, boş bellek) ve Logo'ya ulaşılamıyor: saklanan okuma aynı cevabı verir.
    logo.fail = True
    c2, _ = _client(engine, {})
    second = c2.get("/api/v1/eticaret/marketplaces?yil=2026", headers=a).json()
    risk2 = c2.get("/api/v1/eticaret/marketplaces/stock-risk?yil=2026", headers=a).json()
    assert len(logo.sent) == n
    assert _plain(second) == _plain(first) and second["okundu"] == first["okundu"]
    assert risk2["items"] == risk1["items"] and risk2["kesim"] == risk1["kesim"]
    # «i»: saklanan okumada çalışan Logo metni aynen gösterilir.
    sql1 = {s["sql"] for s in first["kaynaklar"]["sources"].values() if s["connection"] == "logo"}
    sql2 = {s["sql"] for s in second["kaynaklar"]["sources"].values() if s["connection"] == "logo"}
    assert sql1 and sql1 == sql2


def test_old_record_is_served_at_once_and_refreshed_in_background(engine, logo):
    p = PZ.PazarOkuma(lambda: engine, lambda: T, lambda: "/yok")
    v = p.pazar(2026, ["E-TICARET"])
    n = len(logo.sent)
    # Kaydı eskit: tabloda okunma anı 2 saat önce; yeni süreç (boş bellek) onu hemen verir, yenisini arkada ister.
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    body = dict(v, okundu=old.isoformat())
    p._yaz(engine, T, PZ._anahtar("pazar", 2026, ["E-TICARET"]), PZ._dump_rows(body), old)
    q = PZ.PazarOkuma(lambda: engine, lambda: T, lambda: "/yok")
    asked: list = []
    q.bellek.isit = lambda key, fn: asked.append(key)          # arka plan işini kaydet, çalıştırma
    got = q.pazar(2026, ["E-TICARET"])
    assert got["rows"] == v["rows"] and got["okundu"] == old.isoformat()
    assert len(logo.sent) == n and asked == [(T, "pazar:2026:E-TICARET")]
    # Taze kayıt arkada yenileme istemez; «Verileri yenile» (arkada=True) ister ama beklemez.
    asked.clear()
    fresh = PZ.PazarOkuma(lambda: engine, lambda: T, lambda: "/yok")
    fresh.bellek.isit = lambda key, fn: asked.append(key)
    p._yaz(engine, T, PZ._anahtar("pazar", 2026, ["E-TICARET"]), PZ._dump_rows(v), datetime.fromisoformat(v["okundu"]))
    fresh.pazar(2026, ["E-TICARET"])
    assert asked == []
    fresh.pazar(2026, ["E-TICARET"], arkada=True)
    assert asked == [(T, "pazar:2026:E-TICARET")] and len(logo.sent) == n


def test_refresh_param_waits_for_logo_and_run_due_writes_the_table(engine, logo):
    _seed(engine)
    a = {"cookie": "a"}
    c, _ = _client(engine, {})
    c.get("/api/v1/eticaret/marketplaces?yil=2026", headers=a)
    n = len(logo.sent)
    c.get("/api/v1/eticaret/marketplaces?yil=2026&yenile=true", headers=a)
    assert len(logo.sent) > n
    # Gece turu (site verisi yokken bile) pazar yeri okumalarını tabloya yazar.
    out = c.post("/api/v1/eticaret/run-due?model=false").json()
    assert out["pazarYeri"]["yil"] == 2026 and out["pazarYeri"]["cari"] == 3 and out["pazarYeri"]["kitap"] == 3
    with engine.connect() as conn:
        keys = {r[0] for r in conn.execute(sa.select(PZ.READS.c.anahtar))}
    assert {"baglam", "pazar:2026:E-TICARET", "risk:2026:E-TICARET"} <= keys


def test_no_record_and_no_logo_is_still_a_plain_503(engine, logo):
    logo.fail = True
    c, _ = _client(engine, {})
    r = c.get("/api/v1/eticaret/marketplaces?yil=2026", headers={"cookie": "a"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ETICARET_SOURCE"
    out = c.post("/api/v1/eticaret/run-due?model=false").json()
    assert "hata" in out["pazarYeri"]


def test_json_round_trip_keeps_types():
    b = {"firms": {2025: "211", 2026: "411"}, "cut": CUT, "q": [{"connection": "logo", "sql": "SELECT 1", "rows": 1}],
         "okundu": "2026-09-29T01:00:00+00:00"}
    assert PZ._load_baglam(PZ._dump_baglam(b)) == b
