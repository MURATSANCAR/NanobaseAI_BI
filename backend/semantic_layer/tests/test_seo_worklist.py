"""Tek iş listesi: puan, sabit anahtar, durum birleştirme, kendiliğinden kapanma ve birkaç kaynak (SQLite bellekte)."""
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from semantic_bridge.seo_geo import worklist as wl
from semantic_bridge.seo_geo.store import (CRM_BOOKS, LINKS, PRODUCTS, PROPOSALS, REDIRECTS, SCHEMA, _md, dumps)

UTC = timezone.utc
T0 = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)


class _Seo:
    def __init__(self, eng, gsc=None, conf=None):
        self.eng, self._gsc, self._conf, self.nightly = eng, gsc or {}, conf or {}, []

    def engine(self):
        return self.eng

    def tenant(self):
        return "t"

    def conf(self, key):
        return self._conf.get(key, "")

    def gsc(self, kind):
        return self._gsc.get(kind)

    def audit(self, *a, **k):
        pass


def _eng():
    eng = sa.create_engine("sqlite://")
    _md.create_all(eng)
    return eng


def _product(c, pid, name, sales, link, barcode="", active=True):
    c.execute(PRODUCTS.insert().values(tenant_id="t", product_id=pid, code=pid, name=name, brand="Timaş", active=active,
                                       score=60, issues_json="[]", rules=",,", synced_at=T0,
                                       data_json=dumps({"CountTotalSales": str(sales), "StatViews": "0", "SeoLink": link,
                                                        "Barcode": barcode})))


def _item(key_ref, source="sema", owner="tsoft", impact_sev="orta", **kw):
    return wl.make_item(source, key_ref, owner, f"İş {key_ref}", "ayrıntı", impact_sev, "/seo-geo/sema", **kw)


# ------------------------------------------------------------------ puan
def test_score_without_data_is_severity_only_and_says_so():
    score, basis = wl.impact_score("kritik")
    assert score == wl.SEVERITY_POINTS["kritik"]
    assert "önem kritik (40,0)" in basis and "önem derecesine göre" in basis


def test_score_adds_log_points_for_sales_impressions_clicks_and_count():
    score, basis = wl.impact_score("orta", sales=999, impressions=9999, clicks=99, count=9)
    # 12 + 10*3 + 8*4 + 12*2 + 4*1
    assert score == 102.0
    assert "toplam satış 999 adet (30,0)" in basis
    assert "Google gösterimi 9.999 (28 gün) (32,0)" in basis
    assert "tahmini ek tıklama 99 (28 gün) (24,0)" in basis
    assert "9 kayıt (4,0)" in basis and basis.endswith("= 102,0")
    assert "önem derecesine göre" not in basis


def test_single_record_and_zero_values_add_nothing():
    assert wl.impact_score("düşük", sales=0, impressions=0, count=1)[0] == wl.SEVERITY_POINTS["düşük"]
    assert wl.impact_score("bilinmeyen")[0] == wl.SEVERITY_POINTS["orta"]


def test_best_seller_outranks_same_severity_item():
    assert wl.impact_score("orta", sales=5000)[0] > wl.impact_score("orta", sales=50)[0] > wl.impact_score("orta")[0]


# ------------------------------------------------------------------ anahtar
def test_item_key_is_stable_and_independent_of_title():
    a = wl.make_item("haklar", "eksik:42", "telif", "Hak eksik: A", "x", "yüksek", "/l")
    b = wl.make_item("haklar", "eksik:42", "telif", "Hak eksik: A (yeni ad)", "y", "orta", "/l", sales=10)
    c = wl.make_item("haklar", "incele:42", "telif", "Hak eksik: A", "x", "yüksek", "/l")
    d = wl.make_item("crm_durum", "eksik:42", "yayin", "Hak eksik: A", "x", "yüksek", "/l")
    assert a["key"] == b["key"] == wl.item_key("haklar", "eksik:42") and len(a["key"]) == 24
    assert len({a["key"], c["key"], d["key"]}) == 3
    assert a["ref"] == "haklar:eksik:42"


def test_dedupe_keeps_higher_impact():
    low, high = _item("x"), _item("x", sales=1000)
    assert wl.dedupe([low, high])[low["key"]]["impact"] == high["impact"]
    assert wl.dedupe([high, low])[low["key"]]["impact"] == high["impact"]


# ------------------------------------------------------------------ durum birleştirme ve süzgeç
def test_merge_defaults_to_new_and_uses_saved_status():
    a, b = _item("a"), _item("b", owner="telif", source="haklar")
    states = {b["key"]: {"status": "yapiliyor", "assignee": "ayse.k", "note": "bakıyor", "updated_by": "u",
                         "updated_at": T0, "first_seen": T0}}
    m = {i["key"]: i for i in wl.merge([a, b], states)}
    assert m[a["key"]]["status"] == "yeni" and m[a["key"]]["assignee"] is None
    assert m[b["key"]]["status"] == "yapiliyor" and m[b["key"]]["assignee"] == "ayse.k"
    assert m[b["key"]]["ownerLabel"] == "Telif birimi" and m[b["key"]]["statusLabel"] == "Yapılıyor"


def test_select_counts_and_summary():
    items = wl.merge([_item("a", sales=10), _item("b", owner="telif", source="haklar", impact_sev="kritik"),
                      _item("c", owner="telif", source="haklar")], {})
    items[2]["status"] = "bitti"
    open_ = wl.select(items, status="acik")
    assert [i["title"] for i in open_] == ["İş b", "İş a"]            # etkiye göre
    assert len(wl.select(items, owner="telif")) == 2
    assert len(wl.select(items, q="İŞ C")) == 1
    c = wl.counts(items, owner="telif", status="acik")
    assert c["owner"] == {"tsoft": 1, "telif": 1}                      # sahip süzgeci sayımda uygulanmaz
    assert c["status"] == {"yeni": 1, "bitti": 1}
    s = wl.summary(items)
    assert s["telif"]["open"] == 1 and s["telif"]["done"] == 1 and s["bt"]["open"] == 0


# ------------------------------------------------------------------ kendiliğinden kapanma
def test_reconcile_new_close_reopen_and_failed_source_untouched():
    existing = {"k1": {"source": "sema", "open": True}, "k2": {"source": "sema", "open": True},
                "k3": {"source": "haklar", "open": True}, "k4": {"source": "sema", "open": False}}
    current = {"k1": {}, "k4": {}, "k5": {}}
    ops = set(wl.reconcile(existing, current, ran={"sema"}))
    assert ops == {("close", "k2"), ("reopen", "k4"), ("new", "k5")}   # k3: kaynağı koşmadı, açık kalır


def test_sync_states_closes_logs_and_reopens():
    eng = _eng()
    a, b = _item("a"), _item("b")
    assert wl.sync_states(eng, "t", {a["key"]: a, b["key"]: b}, {"sema"}, T0) == {"new": 2, "reopen": 0, "close": 0}
    wl.set_status(eng, "t", a["key"], "bitti", "ali.v", "tema düzeltildi", "murat", T0)
    # b artık üretilmiyor → kendiliğinden kapanır; a hâlâ üretiliyor, "bitti" kalır
    n = wl.sync_states(eng, "t", {a["key"]: a}, {"sema"}, T0 + timedelta(days=1))
    assert n["close"] == 1
    states = wl.load_states(eng, "t")
    assert states[b["key"]]["open"] is False and states[b["key"]]["closed_at"] is not None
    assert states[a["key"]]["status"] == "bitti" and states[a["key"]]["assignee"] == "ali.v"
    with eng.connect() as c:
        rows = c.execute(sa.select(wl.LOG.c.key, wl.LOG.c.event, wl.LOG.c.closed_at, wl.LOG.c.by_user)).all()
    ev = {(k, e): (closed, by) for k, e, closed, by in rows}
    assert ev[(b["key"], "kapandi")][0] is not None
    assert ev[(a["key"], "durum")][1] == "murat"
    # a kapanıp geri gelirse iş bitmemiştir: "yeni" olur
    wl.sync_states(eng, "t", {}, {"sema"}, T0 + timedelta(days=2))
    wl.sync_states(eng, "t", {a["key"]: a}, {"sema"}, T0 + timedelta(days=3))
    st = wl.load_states(eng, "t")[a["key"]]
    assert st["open"] is True and st["status"] == "yeni" and st["closed_at"] is None
    # kaynağı hata veren madde kapanmaz
    assert wl.sync_states(eng, "t", {}, set(), T0 + timedelta(days=4))["close"] == 0


def test_set_status_unknown_key_is_404():
    import pytest
    from fastapi import HTTPException

    eng = _eng()
    with pytest.raises(HTTPException) as e:
        wl.set_status(eng, "t", "yok", "bitti", "", "", "u")
    assert e.value.status_code == 404


def test_collect_isolates_failing_source():
    def ok(env):
        return [_item("a")]

    def boom(env):
        raise RuntimeError("bağlantı yok")

    items, ran, errors = wl.collect(object(), [("sema", ok), ("teknik", boom)])
    assert list(ran) == ["sema"] and "bağlantı yok" in errors["teknik"] and len(items) == 1


# ------------------------------------------------------------------ kaynaklar (SQLite)
def _seeded():
    eng = _eng()
    with eng.begin() as c:
        _product(c, "1", "Kitap A", 1200, "kitap-a", "978-0000000011")
        _product(c, "2", "Kitap B", 40, "kitap-b", "9780000000028")
        _product(c, "3", "Pasif C", 900, "pasif-c", "9780000000035", active=False)
    gsc = {"pages": {"start": "2026-08-28", "end": "2026-09-24", "savedAt": None,
                     "rows": [{"keys": ["https://timas.com.tr/kitap-a"], "impressions": 500, "clicks": 20}]}}
    return eng, wl.Env(_Seo(eng, gsc))


def test_products_are_read_with_sales_link_and_ean():
    _, env = _seeded()
    p = env.products()
    assert p["1"]["sales"] == 1200 and p["1"]["link"] == "kitap-a" and p["1"]["ean"] == "9780000000011"
    assert env.product_impressions("1") == 500 and env.product_impressions("2") == 0


def test_waiting_and_approved_proposals():
    from semantic_bridge.seo_geo import impact

    eng, env = _seeded()
    impact.ensure_table(eng)
    with eng.begin() as c:
        def prop(pid_, product, status, at, fields=None):
            c.execute(PROPOSALS.insert().values(id=pid_, tenant_id="t", product_id=product, status=status,
                                                fields_json=dumps(fields or {"SeoTitle": "Yeni"}), before_json="{}",
                                                score_before=40, score_after=90, created_at=at, decided_at=at))
        prop("p1", "1", "hazir", T0)
        prop("p0", "1", "hazir", T0 - timedelta(days=3))              # eski taslak: aynı madde
        prop("p2", "2", "onaylandi", T0)                              # sitede görülmedi → içerik işi
        prop("p3", "1", "onaylandi", T0)                              # sitede görüldü (etki satırı var) → iş yok
        prop("p4", "model:7", "onaylandi", T0, {"SeoTitle": "Yazar X", "SeoDescription": "Açıklama"})
        prop("p5", "category:8", "onaylandi", T0, {"SeoTitle": "Roman"})
        c.execute(impact.IMPACT.insert().values(tenant_id="t", proposal_id="p3", product_id="1", status="olculuyor"))
        c.execute(LINKS.insert().values(tenant_id="t", link="yazar-x", type="model", table_id="7", title="Yazar X",
                                        description="Açıklama", data_json="{}", synced_at=T0))
        c.execute(LINKS.insert().values(tenant_id="t", link="roman", type="category", table_id="8", title="Eski",
                                        description="", data_json="{}", synced_at=T0))
    waiting = wl.src_proposals_waiting(env)
    assert len(waiting) == 1 and waiting[0]["owner"] == "seo" and waiting[0]["productId"] == "1"
    assert "toplam satış 1.200 adet" in waiting[0]["impactBasis"] and "Google gösterimi 500" in waiting[0]["impactBasis"]
    approved = {i["ref"]: i for i in wl.src_proposals_approved(env)}
    assert set(approved) == {"oneri_yayin:onayli:p2", "oneri_yayin:onayli:p5"}   # p4 sitede aynı, p3 ölçülüyor
    assert approved["oneri_yayin:onayli:p2"]["owner"] == "icerik"
    assert approved["oneri_yayin:onayli:p5"]["title"].endswith("Eski")


def test_rights_and_crm_status_only_for_active_books():
    eng, env = _seeded()
    with eng.begin() as c:
        for ean, rights, flag in (("9780000000011", "eksik", None), ("9780000000028", "var", "cekildi"),
                                  ("9780000000035", "eksik", "iptal")):
            c.execute(CRM_BOOKS.insert().values(tenant_id="t", ean=ean, book_id=ean[-3:], name="x", rights=rights,
                                                status_flag=flag, data_json=dumps({"rightsWhy": "İnternet hakkı yok."}),
                                                synced_at=T0))
    rights = wl.src_rights(env)
    assert [(i["productId"], i["owner"], i["severity"]) for i in rights] == [("1", "telif", "yüksek")]
    assert rights[0]["detail"].startswith("İnternet hakkı yok.")
    status = wl.src_crm_status(env)
    assert [(i["productId"], i["owner"]) for i in status] == [("2", "yayin")]     # pasif C listede yok


def test_redirects_pending_grouped_and_approved_only_while_still_home():
    eng, env = _seeded()
    with eng.begin() as c:
        def red(rid, link, conf, status, at):
            c.execute(REDIRECTS.insert().values(id=rid, tenant_id="t", link=link, confidence=conf, status=status,
                                                synced_at=at))
        red("r1", "kitap-a", "kesin", "bekliyor", T0)
        red("r2", "eski-2", "kesin", "bekliyor", T0)
        red("r3", "eski-3", "orta", "bekliyor", T0)
        red("r4", "eski-4", "kesin", "onaylandi", T0)                           # hâlâ anasayfaya gidiyor
        red("r5", "eski-5", "kesin", "onaylandi", T0 - timedelta(days=1))       # panelde girilmiş
    items = {i["ref"]: i for i in wl.src_redirects(env)}
    assert items["yonlendirme:bekliyor:kesin"]["count"] == 2 and items["yonlendirme:bekliyor:kesin"]["owner"] == "seo"
    assert "Google gösterimi 500" in items["yonlendirme:bekliyor:kesin"]["impactBasis"]
    assert items["yonlendirme:bekliyor:orta"]["severity"] == "düşük"
    assert items["yonlendirme:onayli"]["count"] == 1 and items["yonlendirme:onayli"]["owner"] == "tsoft"


def test_schema_one_item_per_issue_active_books_only():
    eng, env = _seeded()
    with eng.begin() as c:
        for pid, issues in (("1", ",no_isbn,no_offer,"), ("2", ",no_isbn,"), ("3", ",no_isbn,"), ("_org", ",no_book,")):
            c.execute(SCHEMA.insert().values(tenant_id="t", product_id=pid, url=f"https://timas.com.tr/x{pid}", status=200,
                                             issues=issues, checked_at=T0))
    items = {i["ref"]: i for i in wl.src_schema(env)}
    assert set(items) == {"sema:no_isbn", "sema:no_offer"}
    assert items["sema:no_isbn"]["count"] == 2 and "toplam satış 1.240 adet" in items["sema:no_isbn"]["impactBasis"]
    assert items["sema:no_offer"]["severity"] == "kritik" and items["sema:no_offer"]["owner"] == "tsoft"


def test_worklist_cache_reuses_build_within_window():
    eng, _ = _seeded()
    calls = {"n": 0}

    def fake(env):
        calls["n"] += 1
        return [_item("a")]

    clock = {"t": 0.0}
    w = wl.Worklist(_Seo(eng), clock=lambda: clock["t"])
    orig = wl.COLLECTORS
    wl.COLLECTORS = [("sema", fake)]
    try:
        items, _ = w.view(wait=True)
        w.view(wait=True)
        assert calls["n"] == 1 and items[0]["status"] == "yeni"
        clock["t"] = wl.STALE_SECONDS + 1
        w.view(wait=True)
        assert calls["n"] == 2
        # köprü yeniden başladı: bellek boş, liste veritabanından anında gelir, toplama yok
        w2 = wl.Worklist(_Seo(eng), clock=lambda: clock["t"])
        items2, data2 = w2.view()
        assert calls["n"] == 2 and data2 is not None and [i["ref"] for i in items2] == [i["ref"] for i in items]
    finally:
        wl.COLLECTORS = orig


def test_worklist_request_never_waits_when_nothing_saved():
    eng, _ = _seeded()
    w = wl.Worklist(_Seo(eng))
    started = []
    w.start_rebuild = lambda: started.append(1) or True
    items, data = w.view()
    assert items == [] and data is None and started == [1]



def test_grouping_collapses_members_and_keeps_singletons():
    def it(key, gid, impact, status="yeni", title="İş: X"):
        return {"key": key, "ref": key, "source": "haklar", "sourceLabel": "CRM hakları", "owner": "telif",
                "ownerLabel": "Telif", "title": title, "detail": "d", "severity": "orta", "impact": impact,
                "impactBasis": "", "link": "/seo-geo/crm-haklar?urun=1", "productId": "1", "count": None,
                "group": [gid, "Hak eksik — Timaş"] if gid else None, "status": status, "statusLabel": "",
                "assignee": None, "firstSeen": None}
    rows = wl.grouped([it("a", "g1", 50), it("b", "g1", 40, status="yapiliyor"), it("c", "g2", 30), it("d", None, 45)])
    assert [r["key"] for r in rows][:1] == [wl.group_key("g1")]
    g = rows[0]
    assert g["isGroup"] and g["count"] == 2 and g["children"] == ["a", "b"] and g["status"] == "karisik"
    assert g["statusCounts"] == {"yeni": 1, "yapiliyor": 1} and g["impact"] > 50 and g["link"] == "/seo-geo/crm-haklar"
    assert {r["key"] for r in rows[1:]} == {"c", "d"}      # tek üyeli grup ve grupsuz iş olduğu gibi
    assert wl.group_key("x")[0] == "g" and not any(ch in "g" for ch in wl.item_key("s", "r"))
