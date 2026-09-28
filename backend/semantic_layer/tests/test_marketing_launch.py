"""M16 Lansman: onaylı plandan paket (kontrol listesi planın takvimiyle tek kayıt), durum yürüyüşü, yayın günü değişince
maddelerin kayması, günlük seri (saatlik sipariş Logo alanlarını silmez, Logo veri sonundan sonrası boş, hedefin günlük
payı), stok–talep ve hedef eşiği kuralları, depo kaynağı seçimi, emsalin ilk 7/30 günü, etkinlik birleştirme ve «CRM'e
işlenecek» listesi, D+7/D+30 rakam tablosu, Zeki AI özetinde kaynaksız rakamın düşmesi, karar kaydı ve yetki kuralları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM/Logo kabulü test sunucusunda (`scripts/acceptance/m16/`).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import budget as B
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import launch as L
from semantic_bridge.marketing import launch_report as RP
from semantic_bridge.marketing import launch_sources as S
from semantic_bridge.marketing import launch_track as TR
from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for reg in (C._ready, B._ready, L._ready):
        reg.discard(id(e))
    L.ensure(e)
    B.ensure(e)
    yield e
    for reg in (C._ready, B._ready, L._ready):
        reg.discard(id(e))


def _st(**over):
    s = L.settings(lambda k: "")
    s.update(over)
    return s


def _approved_plan(engine, pub: str, stok: str = "15201.0001", tenant: str = T) -> str:
    pid = C.create_plan(engine, tenant, "ayse", kind="yeni", baslik="Deneme Kitap · yeni kitap pazarlama planı", stok_kodu=stok,
                        crm_kitap_id="0f8fad5b-d9cb-469f-a165-70867728950e", yayin_tarihi=pub, yayin_kaynagi="crm-kitap",
                        hedef={"planId": None})
    p = date.fromisoformat(pub)
    C.replace_tasks(engine, tenant, "ayse", pid, [
        {"gunFarki": -30, "tarih": (p - timedelta(days=30)).isoformat(), "is": "Basın bültenini onayla", "durum": "bekliyor", "kaynak": "sablon"},
        {"gunFarki": 0, "tarih": pub, "is": "Yayın günü gönderileri", "durum": "bekliyor", "kaynak": "sablon", "materyalTur": "sosyal"},
    ], system=True)
    C.replace_lines(engine, tenant, "ayse", pid, [{"kanal": "basin", "tutar": 100}])
    C.submit(engine, tenant, "ayse", pid)
    C.decide(engine, tenant, "zeki", pid, True, "uygun", level="pazarlama", threshold=None)
    return pid


def _launch(engine, pub=None, stok="15201.0001"):
    pub = pub or (C.today() + timedelta(days=10)).isoformat()
    pid = _approved_plan(engine, pub, stok)
    return L.create(engine, T, "ayse", pid, _st(), book_name="Deneme Kitap"), pid


# ------------------------------------------------------------------ açma ve kontrol listesi


def test_launch_needs_an_approved_new_book_plan(engine):
    pid = C.create_plan(engine, T, "ayse", kind="yeni", baslik="Taslak", stok_kodu="X1", yayin_tarihi="2026-12-01", yayin_kaynagi="elle")
    with pytest.raises(C.MarketingError) as e:
        L.create(engine, T, "ayse", pid, _st())
    assert e.value.status == 409


def test_launch_links_plan_calendar_and_adds_launch_items(engine):
    lid, pid = _launch(engine)
    assert lid == f"ML-{C.today().year}-0001"
    full = L.get_full(engine, T, lid)
    kinds = {t["kaynak"] for t in full["tasks"]}
    assert {"sablon", "lansman"} <= kinds
    assert len([t for t in full["tasks"] if t["kaynak"] == "lansman"]) == len(L.DEFAULT_TASKS)
    # Tek kayıt: lansmanda işaretlenen madde planın takviminde de yapılmış görünür.
    tid = next(t["id"] for t in full["tasks"] if t["kaynak"] == "sablon")
    L.set_task(engine, T, "ayse", lid, tid, {"durum": "yapildi", "kanitUrl": "https://ornek.com/gonderi"})
    plan = C.plan_full(engine, T, pid)
    assert next(t for t in plan["tasks"] if t["id"] == tid)["durum"] == "yapildi"
    assert any(e["ne"] == "lansman-madde" for e in C.events(engine, pid))
    with pytest.raises(C.MarketingError):
        L.set_task(engine, T, "ayse", lid, tid, {"kanitUrl": "javascript:alert(1)"})
    with pytest.raises(C.MarketingError) as e:
        L.create(engine, T, "ayse", pid, _st())
    assert e.value.status == 409                                       # aynı planın ikinci lansmanı yok


def test_phase_follows_publication_day():
    t = date(2026, 10, 10)
    assert L.phase("2026-10-12", t) == "hazirlik"
    assert L.phase("2026-10-10", t) == "yayinda" and L.phase("2026-10-04", t) == "yayinda"
    assert L.phase("2026-10-03", t) == "izleme"
    assert L.phase("2026-10-03", t, closed=True) == "kapandi"


def test_moving_the_publication_day_moves_only_pending_template_items(engine):
    lid, _ = _launch(engine, pub="2026-11-20")
    full = L.get_full(engine, T, lid)
    done = next(t for t in full["tasks"] if t["kaynak"] == "lansman")
    L.set_task(engine, T, "ayse", lid, done["id"], {"durum": "yapildi"})
    user = L.add_task(engine, T, "ayse", lid, {"is": "Özel iş", "tarih": "2026-11-25"})
    out = L.update(engine, T, "ayse", lid, {"yayinGunu": "2026-11-27"})
    assert out["yayinGunu"] == "2026-11-27" and out["yayinGunuKaynagi"] == "elle"
    by = {t["id"]: t for t in out["tasks"]}
    assert by[done["id"]]["tarih"] == done["tarih"]                    # yapılan madde yerinde
    assert by[user["id"]]["tarih"] == "2026-11-25"                      # kullanıcının maddesi yerinde
    moved = [t for t in out["tasks"] if t["kaynak"] in ("sablon", "lansman") and t["durum"] == "bekliyor"]
    assert all(t["tarih"] == (date(2026, 11, 27) + timedelta(days=t["gunFarki"])).isoformat() for t in moved)
    with pytest.raises(C.MarketingError):
        L.update(engine, T, "ayse", lid, {"yayinGunuKaynagi": "uretim-depo"})   # okunmamış aday seçilemez


def test_auto_open_window(engine):
    today = C.today()
    _approved_plan(engine, (today + timedelta(days=5)).isoformat(), "A")
    _approved_plan(engine, (today + timedelta(days=60)).isoformat(), "B")
    due = L.plans_due(engine, T, today, 14)
    assert [p["stokKodu"] for p in due] == ["A"]


# ------------------------------------------------------------------ günlük seri ve kurallar


def test_daily_target_is_month_target_over_days_in_month():
    aylik = [{"ay": m, "adet": 310.0 if m == 10 else 0.0, "ciro": 3100.0 if m == 10 else 0.0} for m in range(1, 13)]
    assert L.daily_target(aylik, date(2026, 10, 5)) == pytest.approx(10.0)
    assert L.daily_target(aylik, date(2026, 10, 5), "ciro") == pytest.approx(100.0)
    assert L.daily_target(None, date(2026, 10, 5)) is None


class FakeSources:
    def __init__(self, pub: date, data_end: date, fail_logo: bool = False):
        self.pub, self.end, self.fail = pub, data_end, fail_logo

    def orders(self, codes, frm, to, excluded):
        return {(codes[0], self.pub.isoformat()): {"siparis_adet": 50.0, "siparis_satiri": 5.0, "dagilim_adet": 40.0, "sevk_adet": 10.0},
                (codes[0], (self.pub + timedelta(days=1)).isoformat()): {"siparis_adet": 20.0, "siparis_satiri": 2.0, "dagilim_adet": 0.0,
                                                                         "sevk_adet": 0.0}}, "SELECT siparis"

    def distribution(self, codes, frm, to, excluded):
        return {codes[0]: {"adet": 40.0, "siparis": 3.0, "bayi": 3.0}}, "SELECT dagilim"

    def open_orders(self, codes):
        return {codes[0]: 500.0}, "SELECT acik"

    def pending_items(self, codes):
        return {codes[0]: 12.0}, "SELECT bekleyen"

    def order_time_stock(self, codes, since):
        return {}, "SELECT stok"

    def firms(self):
        if self.fail:
            raise S.SourceError("Veritabanına şu an ulaşılamıyor.")
        return {2026: "411"}

    def data_end(self, firms):
        return self.end

    def daily_sales(self, firms, codes, frm, to):
        return {(codes[0], self.pub.isoformat()): {"adet": 30.0, "ciro": 3000.0}}, ["SELECT fatura"]

    def depot(self, codes):
        return {codes[0]: 100.0}, "SELECT depo"


def test_refresh_writes_orders_sales_until_data_end_and_flags_stock_conflict(engine, monkeypatch):
    today = C.today()
    pub = today - timedelta(days=3)
    lid, _ = _launch(engine, pub=pub.isoformat())
    aylik = [{"ay": m, "adet": 3000.0, "ciro": 30000.0} for m in range(1, 13)]
    monkeypatch.setattr(TR, "_targets", lambda e, t, c, ys: {y: {"year": y, "planId": "BP-1", "aylik": aylik, "adet": 36000.0} for y in ys})
    head = L.get(engine, T, lid)
    rep = TR.refresh(engine, T, [head], FakeSources(pub, data_end=pub + timedelta(days=1)), _st(), logo=True, today=today)
    assert rep["lansman"] == 1 and not rep["hatalar"]
    days = {d["gun"]: d for d in L.days_of(engine, lid)}
    assert days[pub.isoformat()]["siparis_adet"] == 50 and days[pub.isoformat()]["fatura_net_adet"] == 30
    assert days[(pub + timedelta(days=1)).isoformat()]["fatura_net_adet"] == 0          # veri sonu içinde, satış yok
    assert days[(pub + timedelta(days=2)).isoformat()]["fatura_net_adet"] is None       # veri sonundan sonra boş
    assert days[(pub - timedelta(days=1)).isoformat()]["hedef_payi_adet"] is None        # yayından önce hedef payı yok
    assert days[today.isoformat()]["bekleyen_adet"] == 500 and days[today.isoformat()]["depo_stok"] == 100
    h = L.get(engine, T, lid)
    assert h["renk"] == "kirmizi" and h["sinyal"]["stokCatismasi"] and h["sinyal"]["oranEsas"] == "fatura"
    assert h["durum"] == "yayinda"
    # Saatlik sipariş okuması (Logo'suz) günlük Logo alanlarını silmez.
    TR.refresh(engine, T, [L.get(engine, T, lid)], FakeSources(pub, pub + timedelta(days=1)), _st(), logo=False, today=today)
    assert {d["gun"]: d for d in L.days_of(engine, lid)}[pub.isoformat()]["fatura_net_adet"] == 30


def test_a_failed_source_is_reported_not_written_as_zero(engine, monkeypatch):
    today = C.today()
    pub = today - timedelta(days=2)
    lid, _ = _launch(engine, pub=pub.isoformat())
    monkeypatch.setattr(TR, "_targets", lambda *a: {})
    rep = TR.refresh(engine, T, [L.get(engine, T, lid)], FakeSources(pub, pub, fail_logo=True), _st(), logo=True, today=today)
    assert any("Logo" in e for e in rep["hatalar"])
    assert all(d["fatura_net_adet"] is None for d in L.days_of(engine, lid))


def _day(g, **kw):
    return {"gun": g, "siparis_adet": None, "fatura_net_adet": None, "hedef_payi_adet": None, "bekleyen_adet": None,
            "depo_stok": None, "veri_sonu_logo": None, **kw}


def test_evaluate_threshold_basis_and_overdue():
    today = date(2026, 10, 10)
    pub = "2026-10-05"
    days = [_day((date(2026, 10, 5) + timedelta(days=i)).isoformat(), siparis_adet=10.0, hedef_payi_adet=20.0) for i in range(6)]
    ev = L.evaluate(pub, days, [], {}, _st(), today)
    assert ev["sinyal"]["oranEsas"] == "siparis" and ev["sinyal"]["oran"] == pytest.approx(0.5)
    assert ev["renk"] == "kirmizi" and ev["sinyal"]["hedefAltinda"]
    good = [{**d, "siparis_adet": 19.0} for d in days]
    ev2 = L.evaluate(pub, good, [{"durum": "bekliyor", "tarih": "2026-10-01"}], {}, _st(), today)
    assert ev2["renk"] == "sari" and ev2["sinyal"]["gecikenMadde"] == 1
    ev3 = L.evaluate("2026-10-20", [], [], {"dagilim": {"adet": 0}}, _st(), today)
    assert ev3["renk"] == "yesil" and not ev3["sinyal"]["dagilimYok"]            # yayın gelmeden dağılım yokluğu uyarı değil


def test_depot_prefers_crm_signal_only_when_newer_than_logo():
    newer = L.depot_choice(100.0, "2026-08-17", {"stok": 40.0, "zaman": "2026-09-20T10:00:00"})
    assert newer["kaynak"] == "crm" and newer["deger"] == 40
    older = L.depot_choice(100.0, "2026-08-17", {"stok": 40.0, "zaman": "2026-08-01T10:00:00"})
    assert older["kaynak"] == "logo" and older["deger"] == 100


def test_emsal_first_days_start_at_first_sale():
    daily = {"2025-03-01": 0.0, "2025-03-04": 5.0, "2025-03-05": 3.0, "2025-03-20": 2.0}
    r = S.first_days(daily, date(2025, 3, 1), 30, date(2025, 12, 31))
    assert r["ilkGun"] == "2025-03-04" and r["ilk7"] == 8 and r["ilk30"] == 10 and r["tam"]
    short = S.first_days(daily, date(2025, 3, 1), 30, date(2025, 3, 12))
    assert short["ilk7"] == 8 and short["ilk30"] is None and not short["tam"]


# ------------------------------------------------------------------ etkinlik ve medya


def test_events_merge_crm_with_portal_results_and_crm_todo(engine):
    lid, _ = _launch(engine)
    cid = "a1b2c3d4-0000-4000-8000-000000000001"
    crm_rows = [{"crmId": cid, "ad": "İmza günü", "tur": "İmza", "tarih": "2026-10-11", "yer": None, "katilimci": None, "satilan": None,
                 "gelir": None, "gider": None, "durum": S.EVENT_DONE, "durumAdi": "Tamamlandı", "yazar": None}]
    L.save_event(engine, T, "ayse", lid, {"crmId": cid, "katilimci": 120, "satilan": 45})
    L.save_event(engine, T, "ayse", lid, {"ad": "Okul söyleşisi", "tarih": "2026-10-15", "katilimci": 80, "satilan": 20})
    with pytest.raises(C.MarketingError):
        L.save_event(engine, T, "ayse", lid, {"tarih": "2026-10-15"})           # elle kayıtta ad gerekli
    ev = L.merge_events(crm_rows, L.portal_events(engine, lid))
    assert ev["toplam"]["tamamlanan"] == 2 and ev["toplam"]["satilan"] == 65 and ev["toplam"]["katilimci"] == 200
    L.save_media(engine, T, "ayse", lid, {"baslik": "Söyleşi", "mecra": "Gazete", "url": "https://ornek.com/a", "ton": "olumlu"})
    todo = L.crm_todo(ev, L.portal_media(engine, lid), L.get(engine, T, lid))
    assert {t["nereye"] for t in todo} == {"CRM › Etkinlik (mevcut kayıt)", "CRM › Etkinlik (yeni kayıt)", "CRM › Haber / medya yansıması"}
    with pytest.raises(C.MarketingError):
        L.save_media(engine, T, "ayse", lid, {"baslik": "x", "ton": "harika"})


# ------------------------------------------------------------------ değerlendirme


def _review_setup(engine):
    today = C.today()
    pub = today - timedelta(days=8)
    lid, pid = _launch(engine, pub=pub.isoformat())
    rows = {}
    for i in range(7):
        g = (pub + timedelta(days=i)).isoformat()
        rows[g] = {"siparis_adet": 10.0, "fatura_net_adet": 5.0 if i < 3 else None, "fatura_net_ciro": 500.0 if i < 3 else None,
                   "hedef_payi_adet": 10.0, "veri_sonu_logo": (pub + timedelta(days=2)).isoformat()}
    L.upsert_days(engine, lid, rows)
    return lid, pid


def test_review_numbers_and_money_is_never_given_to_the_model(engine):
    lid, _ = _review_setup(engine)
    full = L.get_full(engine, T, lid)
    rk = RP.numbers(full, L.days_of(engine, lid), 7, {"toplam": {"tamamlanan": 1, "katilimci": 50, "satilan": 12}}, {"olumlu": 2})
    by = {r["anahtar"]: r for r in rk["satirlar"]}
    assert by["siparis"]["deger"] == 70 and by["fatura"]["deger"] == 15 and by["kapsanan"]["deger"] == 3
    assert by["hedef"]["deger"] == 70 and by["oranFatura"]["deger"] == 50.0 and by["ciro"]["para"]
    fx = RP.facts(full, rk)
    assert not any("ciro" in f.lower() for f in fx)
    assert RP.redact(rk)["satirlar"][[r["anahtar"] for r in rk["satirlar"]].index("ciro")]["deger"] is None


def test_review_text_drops_invented_numbers_and_keeps_three_suggestions(engine):
    lid, _ = _review_setup(engine)
    full = L.get_full(engine, T, lid)
    rk = RP.numbers(full, L.days_of(engine, lid), 7, {"toplam": {}}, {})
    llm = FakeLlm(["İlk hafta 70 adet sipariş geldi. Satış 9999 adede ulaştı.\nÖNERİLER:\n- Stoku izleyin.\n- Dijitali 12345 TL artırın.\n"
                   "- Etkinlik ekleyin.\n- Basını güçlendirin.\n- Beşinci öneri."])
    ozet, sug, dog = RP.draft_text(llm, full, rk, [])
    assert "70" in ozet and "9999" not in ozet
    assert len(sug) == 3 and not any("12345" in s for s in sug)
    assert dog["dusenSayisi"] >= 2


def test_decision_needs_reason_freezes_numbers_and_goes_to_plan_history(engine):
    lid, pid = _review_setup(engine)
    full = L.get_full(engine, T, lid)
    rk = RP.numbers(full, L.days_of(engine, lid), 7, {"toplam": {}}, {})
    L.review_put_numbers(engine, lid, 7, rk, "sistem")
    with pytest.raises(C.MarketingError):
        L.review_decide(engine, T, "zeki", lid, 7, "artir", "")
    with pytest.raises(C.MarketingError):
        L.review_decide(engine, T, "zeki", lid, 30, "artir", "neden")          # D+30 raporu yok
    rv = L.review_decide(engine, T, "zeki", lid, 7, "artir", "Dijitali ikinci haftaya kaydır")
    assert rv["durum"] == "karar" and rv["kararAdi"] == "Bütçeyi artır"
    with pytest.raises(C.MarketingError) as e:
        L.review_put_numbers(engine, lid, 7, rk, "sistem")
    assert e.value.status == 409
    assert any(ev["ne"] == "lansman-karar" for ev in C.events(engine, pid))


def test_report_pdf_has_no_technology_names(engine):
    pytest.importorskip("fpdf")
    from semantic_bridge.marketing import guard as G

    lid, _ = _review_setup(engine)
    full = L.get_full(engine, T, lid)
    L.review_put_numbers(engine, lid, 7, RP.numbers(full, L.days_of(engine, lid), 7, {"toplam": {}}, {}), "sistem")
    full = L.get_full(engine, T, lid)
    body = RP.report_pdf(full, full["reviews"], False, "ayse")
    assert body[:4] == b"%PDF" and not G.has_tech_name(body.decode("latin-1", "ignore"))


# ------------------------------------------------------------------ SQL ve yetki


def test_sql_is_read_only_and_uses_the_same_definitions():
    o = S.orders_sql("Timas_MSCRM.dbo", ["15201.0001"], date(2026, 10, 1), date(2026, 10, 31), [1, 100000001])
    assert "statuscode NOT IN (1, 100000001)" in o and "DATEADD(HOUR, 3" in o and "N'15201.0001'" in o
    s = S.daily_sales_sql("411", [7, 3], date(2026, 10, 1), date(2026, 10, 31))
    assert "INVOICEREF <> 0" in s and "TRCODE IN (2,3,7,8,9)" in s and "LINENET" in s and "STOCKREF IN (3, 7)" in s
    for sql in (o, s, S.pending_items_sql("Timas_MSCRM.dbo", ["X"]), S.events_sql("Timas_MSCRM.dbo", "0f8fad5b-d9cb-469f-a165-70867728950e")):
        up = sql.upper()
        assert not any(w in up for w in ("INSERT ", "UPDATE ", "DELETE ", "MERGE ", "EXEC "))
    with pytest.raises(S.SourceError):
        S.orders_sql("Timas_MSCRM.dbo", ["x'; DROP TABLE a;--"], date(2026, 10, 1), date(2026, 10, 2), [1])


def test_access_rules_for_launch():
    page = frozenset({A.page("pazarlama-lansman")})
    assert A.rule_for("/api/v1/marketing/launches") == page
    assert A.rule_for("/api/v1/marketing/launches/ML-2026-0001/tracking") == page
    assert A.rule_for("/api/v1/marketing/launches/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/marketing/plans") == frozenset({A.page("pazarlama-yeni-kitap"), A.page("pazarlama-backlist")})
    f = A.features_for
    w = "ozellik:pazarlama.lansman-yaz"
    assert f("POST", "/api/v1/marketing/launches") == [w]
    assert f("PUT", "/api/v1/marketing/launches/ML-2026-0001/tasks/abc") == [w]
    assert f("POST", "/api/v1/marketing/launches/ML-2026-0001/reviews/7/draft") == [w]
    assert f("POST", "/api/v1/marketing/launches/ML-2026-0001/reviews/7/decide") == []   # açıkça verilen plan-onay, uçta
    assert f("POST", "/api/v1/marketing/launches/run-due") == []
    assert f("GET", "/api/v1/marketing/launches/ML-2026-0001/export.pdf") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/marketing/launches/ML-2026-0001") == []
    assert "sayfa:pazarlama-lansman" in A.all_keys() and w not in A.explicit_keys()


def test_tables_are_created(engine):
    names = set(sa.inspect(engine).get_table_names())
    assert {"semantic_mkt_launches", "semantic_mkt_launch_daily", "semantic_mkt_launch_events", "semantic_mkt_launch_media",
            "semantic_mkt_launch_reviews"} <= names


# ------------------------------------------------------------------ uçlar


def test_endpoints_open_mark_and_explicit_decision(monkeypatch, store, settings):
    from fastapi.testclient import TestClient

    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    A._ready.clear()
    A.invalidate()
    for reg in (C._ready, B._ready, L._ready):
        reg.discard(id(store.engine))
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))
    client = TestClient(app)
    pub = C.today() - timedelta(days=1)
    monkeypatch.setattr(TR, "_targets", lambda *a: {})
    src = app.state.marketing["launch"]["sources"]
    fake = FakeSources(pub, pub)
    for name in ("orders", "distribution", "open_orders", "pending_items", "order_time_stock", "firms", "data_end", "daily_sales", "depot"):
        monkeypatch.setattr(src, name, getattr(fake, name))
    monkeypatch.setattr(src, "events", lambda kid: ([], "SELECT"))
    crm = app.state.marketing["crm"]
    monkeypatch.setattr(crm, "book", lambda stok, fresh=False: None)
    monkeypatch.setattr(crm, "email_of", lambda user: None)
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}
    L.ensure(store.engine)
    pid = _approved_plan(store.engine, pub.isoformat(), "N16", tenant=settings.tenant_id)

    r = client.post("/api/v1/marketing/launches", json={"planId": pid}, headers=a)
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    assert client.post("/api/v1/marketing/launches", json={"planId": pid}, headers=a).status_code == 409
    tid = r.json()["tasks"][0]["id"]
    assert client.put(f"/api/v1/marketing/launches/{lid}/tasks/{tid}", json={"durum": "yapildi"}, headers=a).status_code == 200
    assert client.get(f"/api/v1/marketing/launches/{lid}/tracking?gun=7", headers=a).status_code == 200
    assert client.get(f"/api/v1/marketing/launches/{lid}/tracking?gun=5", headers=a).status_code == 400
    assert client.post(f"/api/v1/marketing/launches/{lid}/reviews/7/draft", headers=a).status_code == 202
    denied = client.post(f"/api/v1/marketing/launches/{lid}/reviews/7/decide", json={"karar": "koru", "gerekce": "x"}, headers=a)
    assert denied.status_code == 403                                   # açıkça verilen plan-onay yok
    ok = client.post(f"/api/v1/marketing/launches/{lid}/reviews/7/decide", json={"karar": "koru", "gerekce": "stok yeterli"}, headers=z)
    assert ok.status_code == 200 and ok.json()["review"]["karar"] == "koru"
    assert client.post("/api/v1/marketing/launches/run-due", headers=a).status_code == 403   # kişi zamanlayıcıyı tetikleyemez
    me = client.get("/api/v1/marketing/launches/meta", headers=a).json()["me"]
    assert me["canWrite"] and not me["canDecide"]
