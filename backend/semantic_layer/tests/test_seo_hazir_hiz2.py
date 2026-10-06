"""SEO & GEO ekran hızı, 2. tur (2026-09-29): kalan yavaş uçlar hazır hesapta (`seo_geo/hazir.py`).

Denetlenen: eski hesap = yeni hesap. Eski uç kodu burada birebir durur (değiştirilen işlevlerin eski gövdesi: ürün
bilgisi, denetim kayıtları, alışveriş denetimi, CRM listesi sorgusu, fırsat sayfası); aynı veriyle eski ve yeni cevap
karşılaştırılır — ilk çağrı (hesap), köprü yeniden kalkmış gibi (tablodan) ve bellekten. Ayrıca: bağlantı grafiği
tarama sürerken son kaydı verir, eskiyince arkada yeniler; açılış ısıtması test veritabanında başlamaz, canlıda
çalışma ortamını bekleyip bütün kayıtlı hesapları ısıtır; «kaynaklar»da hazır kaydın kökeni var, kaynaksız rakam yok.
Kabul (gerçek veriyle, sunucuda): `scripts/acceptance/seo-hiz/kabul_seo_hiz2.py`.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from semantic_bridge import provenance as P
from semantic_bridge import seo_geo
from semantic_bridge.seo_geo import crawlbot as cb
from semantic_bridge.seo_geo import crm as crm_mod
from semantic_bridge.seo_geo import entity as entity_mod
from semantic_bridge.seo_geo import hazir, links as links_mod
from semantic_bridge.seo_geo import opportunities as op
from semantic_bridge.seo_geo import shopping as shop_mod
from semantic_bridge.seo_geo.store import CRM_BOOKS, GSC, LINKS, PRODUCTS, dumps, iso, loads
from semantic_bridge.seo_geo.tech import SNAP, TECH
from semantic_layer.store.catalog_store import open_store

T = "t1"
SITE = "https://timas.com.tr"
NOW = datetime.now(timezone.utc)


def _norm(v):
    return json.loads(json.dumps(v, ensure_ascii=False, default=str))


def _regexp_replace(s, pattern, repl, flags=""):
    return None if s is None else re.sub(pattern, repl, s, count=0 if "g" in (flags or "") else 1)


def _pg_functions(dbapi_conn, _rec=None):
    dbapi_conn.create_function("regexp_replace", 4, _regexp_replace)


def _engine():
    eng = open_store("sqlite://").engine
    event.listen(eng, "connect", _pg_functions)
    with eng.connect() as c:
        _pg_functions(c.connection.driver_connection)
    return eng


@pytest.fixture
def client():
    eng = _engine()
    rt = SimpleNamespace(store=SimpleNamespace(engine=eng), settings=SimpleNamespace(tenant_id=T, connection_file=""),
                         llm=None, llm_for=lambda *a, **k: None)
    app = FastAPI()
    seo = seo_geo.register(app, runtime=lambda: rt, authorize=lambda r: None, session_user=lambda r: "ayse")
    seo.engine()
    hazir.unut()
    return TestClient(app, raise_server_exceptions=True), eng, seo


def _get(c, path, **params):
    data = c.get("/api/v1/seo-geo/" + path, params=params).json()
    k = data.pop("kaynaklar", None)
    return data, k


def _three(c, path, **params):
    """İlk çağrı (hesap), yeniden kalkmış köprü (tablodan), bellekten: üçü aynı olmalı."""
    a, ka = _get(c, path, **params)
    hazir.unut()
    b, kb = _get(c, path, **params)
    d, _ = _get(c, path, **params)
    assert a == b == d, path
    for k in (ka, kb):
        assert k is not None and not k.get("error"), (path, k)
    return a


# ================================================================== veri
def _product(pid, name, sales=0, active=True, score=80, at=None, **extra):
    data = {"ProductId": pid, "ProductCode": f"K{pid}", "ProductName": name, "CountTotalSales": str(sales),
            "StatViews": "0", "SeoLink": f"k-{pid}", **extra}
    return dict(tenant_id=T, product_id=pid, code=f"K{pid}", name=name, brand="Timaş", active=active, score=score,
                issues_json="[]", rules=",", data_json=dumps(data), synced_at=at or datetime(2026, 9, 1, tzinfo=timezone.utc))


def _seed(eng, crm_all=False):
    img = [{"Small": "https://img/1s.jpg", "Big": "https://img/1b.jpg"}]
    rows = [
        _product("1", "Dinle", 120, Model="Sabahattin Ali", Barcode="9786051234567", Stock="5",
                 SellingPriceVatIncluded="45,50", Details="Uzun açıklama", ImageUrls=img, Brand="Timaş", ModelId="7"),
        _product("2", "Dinle (Ciltli)", 80, Model="Sabahattin Ali, Ayşe Kara", Barcode="9786051234567", Stock="0",
                 SellingPrice="100", Vat="10", ModelId="7"),
        _product("3", "KÜRK MANTOLU MADONNA İNDİRİM", 7, Model="Ayşe Kara", Barcode="2001234567890", Stock="3",
                 SellingPriceVatIncluded="30", DiscountedSellingPriceVatIncluded="35", Details="a", ModelId="8"),
        _product("4", "Eski", 500, active=False, Model="Ayşe Kara", Barcode="9780306406157"),
        _product("5", "Yol", 0, Model="Elif Yazar; Mehmet Kara", Barcode="0306406152", Stock="1",
                 SellingPriceVatIncluded="12", Details="x" * 20, ImageUrlCdn="/no-image.png", ModelId="9"),
        _product("6", "Gece", 7, Model="Elif Yazar", Stock="2", SellingPriceVatIncluded="0"),
        _product("7", "Deniz", 7, Barcode="9786059999999"),
    ]
    links = [dict(tenant_id=T, link="sabahattin-ali", type="model", table_id="7", title="Sabahattin Ali | Timaş",
                  description="d", data_json="{}", synced_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
             dict(tenant_id=T, link="ayse-kara", type="model", table_id="8", title="Ayşe Kara", description="",
                  data_json="{}", synced_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
             dict(tenant_id=T, link="roman", type="category", table_id="30", title="Roman", description=None,
                  data_json="{}", synced_at=datetime(2026, 9, 1, tzinfo=timezone.utc))]
    with eng.begin() as c:
        c.execute(PRODUCTS.insert(), rows)
        c.execute(LINKS.insert(), links)
        if crm_all:
            # Test veritabanında JSON'dan barkod okunamaz (EAN boş metin): boş barkodlu kart bütün ürünlere bağlanır.
            c.execute(CRM_BOOKS.insert().values(
                tenant_id=T, ean="", book_id="b1", name="Dinle", rights="var", status_flag="cekildi",
                data_json=dumps({"bookId": "b1", "name": "Dinle", "rights": "var", "statusFlag": "cekildi",
                                 "previewPdf": "https://x/p.pdf", "contracts": [{"inForce": True, "ebook": True}]}),
                synced_at=datetime(2026, 9, 2, tzinfo=timezone.utc)))


# ================================================================== alışveriş
def _old_shopping(seo):
    shop = shop_mod.Shopping(seo)
    site, dups = shop.site(), shop._dups()
    out = []
    for pid, p, score, flag in shop._rows():
        a = shop_mod.audit(p, site, crm_flag=flag, duplicate_gtins=dups)
        out.append({"id": pid, "name": a["name"], "author": a["author"] or None, "url": a["url"],
                    "image": a["image"], "gtin": a["gtin"], "book": a["book"], "price": a["price"],
                    "salePrice": a["salePrice"], "currency": a["currency"], "availability": a["row"]["availability"] or None,
                    "status": a["status"], "issues": a["issues"], "score": score,
                    "sales": shop_mod._num(p.get("CountTotalSales"))})
    out.sort(key=lambda r: (-r["sales"], r["id"]))
    return out, shop_mod.summarize(out)


@pytest.mark.parametrize("crm_all", [False, True])
def test_shopping_equals_old_calculation(client, crm_all):
    c, eng, seo = client
    _seed(eng, crm_all)
    items, summ = _old_shopping(seo)
    assert len(items) == 6 and summ["blocked"] >= 1
    for params in ({}, {"status": "engelleyici"}, {"issue": "gtin_duplicate"}, {"q": "dinle"}, {"start": 2, "limit": 2}):
        got = _three(c, "shopping", **params)
        rows = items
        if params.get("issue"):
            rows = [r for r in rows if any(i["code"] == params["issue"] for i in r["issues"])]
        if params.get("status"):
            rows = [r for r in rows if r["status"] == params["status"]]
        if params.get("q"):
            ql = shop_mod._tr_lower(params["q"])
            rows = [r for r in rows if ql in shop_mod._tr_lower(r["name"] or "") or ql in (r["gtin"] or "")
                    or ql in shop_mod._tr_lower(r["author"] or "")]
        s, n = params.get("start", 0), params.get("limit", 50)
        assert got["total"] == len(rows) and got["items"] == _norm(rows[s:s + n]), params
        assert got["summary"] == _norm(summ)
    # girdi değişince (eşitleme) yeniden hesap, yine eskisiyle aynı
    with eng.begin() as conn:
        conn.execute(PRODUCTS.update().where(PRODUCTS.c.product_id == "6").values(
            active=False, synced_at=datetime(2026, 9, 5, tzinfo=timezone.utc)))
    items, summ = _old_shopping(seo)
    got, _ = _get(c, "shopping")
    assert got["total"] == 5 and got["items"] == _norm(items) and got["summary"] == _norm(summ)


# ================================================================== CRM listesi
def _old_crm(eng, seo, filter="", q="", start=0, limit=50):
    from semantic_bridge.seo_geo import BOOK_EAN, EAN, SALES, VIEWS, _product_view

    site = seo.conf("SEO_SITE_URL")
    data = sa.cast(CRM_BOOKS.c.data_json, sa.JSON)
    cond = [PRODUCTS.c.tenant_id == T, PRODUCTS.c.active.is_(True)]
    if filter in crm_mod.RIGHTS:
        cond.append(CRM_BOOKS.c.rights == filter)
    elif filter == "durum":
        cond.append(CRM_BOOKS.c.status_flag.isnot(None))
    elif filter == "eslesmedi":  # 2026-10-06: yalnız kitap barkodlu ürün (set/siteye özel kod sayılmaz)
        cond.append(sa.and_(CRM_BOOKS.c.ean.is_(None), BOOK_EAN))
    elif filter == "onizleme":
        cond.append(data["previewPdf"].as_string().isnot(None))
    elif filter == "video":
        cond.append(data["video"].as_string().isnot(None))
    if q.strip():
        like = f"%{q.strip()}%"
        cond.append(sa.or_(PRODUCTS.c.name.ilike(like), PRODUCTS.c.code.ilike(like), PRODUCTS.c.brand.ilike(like)))
    j = PRODUCTS.outerjoin(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
    with eng.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(j).where(*cond)).scalar() or 0
        rows = c.execute(sa.select(PRODUCTS, CRM_BOOKS.c.data_json.label("crm_json")).select_from(j).where(*cond)
                         .order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.product_id)
                         .offset(max(0, start)).limit(max(1, min(limit, 200)))).mappings().all()
    items = []
    for r in rows:
        b = loads(r["crm_json"], None) if r["crm_json"] else None
        items.append({**{k: v for k, v in _product_view(dict(r), site).items() if k != "issues"},
                      "crm": ({k: b.get(k) for k in ("bookId", "name", "rights", "rightsWhy", "statusLabel", "statusFlag",
                                                     "previewPdf", "video", "originalTitle", "inForce")} if b else None)})
    return total, _norm(items)


@pytest.mark.parametrize("crm_all", [False, True])
def test_crm_list_equals_old_sql(client, crm_all):
    c, eng, seo = client
    _seed(eng, crm_all)
    for params in ({}, {"filter": "var"}, {"filter": "yok"}, {"filter": "durum"}, {"filter": "eslesmedi"},
                   {"filter": "onizleme"}, {"filter": "video"}, {"q": "dinle"}, {"q": "k3"}, {"start": 2, "limit": 2},
                   {"filter": "eslesmedi", "q": "gece", "start": 0, "limit": 1}):
        got = _three(c, "crm", **params)
        total, items = _old_crm(eng, seo, **params)
        assert got["total"] == total and got["items"] == items, params
    got, _ = _get(c, "crm", filter="var")
    assert got["total"] == (6 if crm_all else 0)


# ================================================================== fırsat listesi
def _old_opportunities(seo, kind="yakin", brand="0", start=0, limit=50):
    data = op.compute(seo)
    ranked = op.rank(data["items"], kind)
    if brand in ("0", "1"):
        ranked = [i for i in ranked if i["brand"] == (brand == "1")]
    page = ranked[start:start + limit]
    products = op.build_product_map(seo) if any(i["page"] for i in page) else {}
    matched = {i["query"]: products.get(op.path_key(i["page"]) or "") if i["page"] else None for i in page}
    done = op.target_proposals(seo, sorted({p["id"] for p in matched.values() if p}))
    items = []
    for i in page:
        p = products.get(op.path_key(i["page"]) or "") if i["page"] else None
        items.append({k: v for k, v in i.items() if k != "kinds"} | {
            "kinds": i["kinds"], "productId": p["id"] if p else None, "productName": p["name"] if p else None,
            "targetProposal": done.get((p["id"], op.fold(i["query"]))) if p else None})
    return {"total": len(ranked), "items": _norm(items), "totals": _norm(data["totals"]), "source": _norm(data["source"]),
            "curve": _norm(data["curve"])}


def _gsc_rows(n=160):
    rows = []
    for i in range(n):
        q = f"{'timaş ' if i % 9 == 0 else ''}kitap {i % 37} {'roman' if i % 2 else 'masal'}"
        rows.append({"keys": [q, f"{SITE}/k-{1 + i % 7}"], "clicks": (i * 7) % 23, "impressions": 50 + (i * 37) % 400,
                     "position": round(1 + (i * 13 % 170) / 10, 1)})
    return rows


def test_opportunities_equal_old_and_follow_source_change(client):
    c, eng, seo = client
    _seed(eng)
    # önce yalnız-sorgu önbelleği, sonra sorgu+sayfa kırılımı: kaynak değişince hazır kayıt da değişir
    with eng.begin() as conn:
        conn.execute(GSC.insert().values(tenant_id=T, kind="queries", start_date="2026-08-30", end_date="2026-09-26",
                                         rows_json=dumps([{**r, "keys": r["keys"][:1]} for r in _gsc_rows(90)]),
                                         saved_at=datetime(2026, 9, 27, tzinfo=timezone.utc)))
    for kind, brand in (("yakin", "0"), ("dusuk_tiklama", "")):
        got = _three(c, "opportunities", kind=kind, brand=brand)
        want = _old_opportunities(seo, kind, brand)
        assert {k: got[k] for k in want} == want and got["source"]["from"] == "queries"
    with eng.begin() as conn:
        conn.execute(op.OPPS.insert().values(tenant_id=T, kind="query_page", start_date="2026-08-30", end_date="2026-09-26",
                                             rows_json=dumps(_gsc_rows()), saved_at=datetime(2026, 9, 28, tzinfo=timezone.utc)))
    for kind, brand, start, limit in (("yakin", "0", 0, 50), ("yakin", "1", 0, 50), ("dusuk_tiklama", "", 3, 5)):
        got = _three(c, "opportunities", kind=kind, brand=brand, start=start, limit=limit)
        want = _old_opportunities(seo, kind, brand, start, limit)
        assert {k: got[k] for k in want} == want and got["source"]["from"] == "query_page", (kind, brand)
        assert got["total"] > 0
    # başka modüllerin kullandığı `computed` da eski hesapla aynı (JSON'dan geçmiş hâli)
    assert op.computed(seo) == _norm(op.compute(seo))


# ================================================================== kimlik
def test_entity_equals_old_per_request_calculation(client):
    c, eng, seo = client
    _seed(eng, crm_all=True)
    ent = seo.entity
    ent.save("author", "sabahattin ali", {"name": "Sabahattin Ali", "status": "wikipedia", "wikidata": "Q1",
                                           "wikipedia": "https://tr.wikipedia.org/wiki/S", "description": "yazar"})
    prods = ent.products()
    authors, gb = ent.authors(prods), ent.google_books(prods)       # eski yol: ürünler istekte açılır
    over = _three(c, "entity")
    counts = {k: sum(1 for a in authors if a["status"] == k) for k in entity_mod.AUTHOR_STATUS}
    assert over["authors"]["counts"] == counts and over["authors"]["total"] == len(authors) == 4
    assert over["authors"]["top"] == _norm([{k: a[k] for k in ("name", "sales", "status", "label")} for a in authors[:10]])
    assert over["books"]["googleBooks"]["total"] == len(gb) and over["books"]["googleBooks"]["ready"] == \
        sum(1 for x in gb if x["ready"])
    au = _three(c, "entity/authors")
    assert au["items"] == _norm([{k: v for k, v in a.items() if k not in ("bookMap", "key")} for a in authors])
    gbr = _three(c, "entity/google-books")
    assert gbr["items"] == _norm(gb) and gbr["total"] == 6
    # Wikidata durumu hazır kayda girmez: denetim yazınca hemen görünür (ürün girdisi değişmeden)
    ent.save("author", "ayse kara", {"name": "Ayşe Kara", "status": "yok"})
    au2, _ = _get(c, "entity/authors", status="yok")
    assert [a["name"] for a in au2["items"]] == ["Ayşe Kara"]


# ================================================================== Google taraması
def _old_product_info(eng):
    from semantic_bridge.seo_geo import SALES

    with eng.connect() as c:
        rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.active, PRODUCTS.c.data_json,
                                   SALES).where(PRODUCTS.c.tenant_id == T)).all()
    out = {}
    for pid, name, active, data, sales in rows:
        p = loads(data, {})
        link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl") or ""
        url = (str(link) if str(link).startswith("http") else f"{SITE}/{str(link).strip('/')}") if link else None
        out[str(pid)] = {"name": name or "", "active": bool(active), "sales": float(sales or 0), "url": url}
    return out


def _old_load_rows(eng):
    with eng.connect() as c:
        rows = c.execute(sa.select(cb.INSPECT).where(cb.INSPECT.c.tenant_id == T)).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["rich"] = loads(d.pop("rich_json"), None)
        d["data"] = loads(d.pop("data_json"), None)
        if d.get("last_crawl") is not None and d["last_crawl"].tzinfo is None:
            d["last_crawl"] = d["last_crawl"].replace(tzinfo=timezone.utc)
        out.append(d)
    return out


def _old_urls(eng, filter="all", start=0, limit=50, q="", kind=""):
    at = datetime.now(timezone.utc)
    prods = _old_product_info(eng)
    rows = _old_load_rows(eng)
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if filter == "not_indexed":
        rows = [r for r in rows if not r.get("error") and r["status"] != "indexed"]
    elif filter == "canonical":
        rows = [r for r in rows if not r.get("error") and r["canonical_mismatch"]]
    elif filter == "stale":
        rows = [r for r in rows if cb.is_stale(r, at)]
    elif filter == "errors":
        rows = [r for r in rows if r.get("error") or r["status"] in cb.ERROR_STATUSES]
    elif filter == "rich":
        rows = [r for r in rows if not r.get("error") and (r.get("rich") or {}).get("issues")]
    needle = q.strip().casefold()
    if needle:
        rows = [r for r in rows if needle in r["url"].casefold()
                or needle in (prods.get(str(r.get("product_id"))) or {}).get("name", "").casefold()]

    def sales(r):
        return (prods.get(str(r.get("product_id"))) or {}).get("sales", 0.0)

    if filter == "stale":
        rows.sort(key=lambda r: (-sales(r), r["url"]))
    else:
        rows.sort(key=lambda r: (r["kind"] != "home", r["kind"] != "product", -sales(r), r["url"]))
    items = []
    for r in rows[start:start + limit]:
        p = prods.get(str(r.get("product_id"))) or {}
        st = cb.row_status(r)
        label, tone = cb.STATUS_LABEL.get(st, (st, "mid"))
        items.append({"url": r["url"], "kind": r["kind"], "productId": r.get("product_id"), "name": p.get("name"),
                      "sales": int(p.get("sales") or 0), "status": st, "statusLabel": label, "tone": tone,
                      "verdict": r.get("verdict"), "coverage": r.get("coverage"), "indexing": r.get("indexing"),
                      "robots": r.get("robots"), "fetch": r.get("fetch"), "lastCrawl": iso(r.get("last_crawl")),
                      "daysSinceCrawl": cb.days_since(r.get("last_crawl"), at),
                      "googleCanonical": r.get("google_canonical"), "userCanonical": r.get("user_canonical"),
                      "canonicalMismatch": bool(r.get("canonical_mismatch")), "crawledAs": r.get("crawled_as"),
                      "rich": r.get("rich"), "data": r.get("data"), "error": r.get("error"),
                      "inspectedAt": iso(r.get("inspected_at"))})
    return {"total": len(rows), "start": start, "items": _norm(items)}


def _inspect_row(url, kind, pid, status, last_days, **kw):
    base = dict(tenant_id=T, url=url, product_id=pid, kind=kind, status=status, verdict="PASS", coverage="Indexed",
                indexing=None, robots="ALLOWED", fetch="SUCCESSFUL",
                last_crawl=(NOW - timedelta(days=last_days, hours=12)) if last_days is not None else None,
                google_canonical=None, user_canonical=None, canonical_mismatch=False, crawled_as="MOBILE",
                rich_json=None, data_json=dumps({"referringUrls": [f"{SITE}/"], "sitemap": []}), error=None,
                inspected_at=NOW - timedelta(days=1, minutes=int(last_days or 0)))
    base.update(kw)
    return base


def _seed_inspect(eng):
    rows = [
        _inspect_row(f"{SITE}/", "home", None, "indexed", 1),
        _inspect_row(f"{SITE}/k-1", "product", "1", "indexed", 3),
        _inspect_row(f"{SITE}/k-2", "product", "2", "crawled_not_indexed", 45, coverage="Crawled - currently not indexed"),
        _inspect_row(f"{SITE}/k-3", "product", "3", "duplicate", None, canonical_mismatch=True,
                     google_canonical=f"{SITE}/k-1", user_canonical=f"{SITE}/k-3"),
        _inspect_row(f"{SITE}/k-5", "product", "5", "indexed", 10,
                     rich_json=dumps({"verdict": "PARTIAL", "types": ["Product"],
                                      "issues": [{"type": "Product", "item": "x", "message": "offers eksik", "severity": "WARNING"}]})),
        _inspect_row(f"{SITE}/k-6", "product", "6", "indexed", 2, error="Google 500: hata"),
        _inspect_row(f"{SITE}/sabahattin-ali", "author", None, "not_found", 100, fetch="NOT_FOUND"),
    ]
    with eng.begin() as c:
        c.execute(cb.INSPECT.insert(), rows)


def test_crawlbot_summary_and_urls_equal_old(client):
    c, eng, seo = client
    _seed(eng)
    _seed_inspect(eng)
    got = _three(c, "crawlbot")
    rows, prods = _old_load_rows(eng), _old_product_info(eng)
    summary = cb.summarize(rows, prods)
    summary["productsActive"] = sum(1 for p in prods.values() if p["active"] and p["url"])
    for k, v in _norm(summary).items():
        assert got["inspect"][k] == v, k
    assert got["inspect"]["lastInspectedAt"] == iso(max(r["inspected_at"] for r in rows))
    assert got["inspect"]["total"] == 7 and got["inspect"]["crawledNotIndexed"] == 1
    for params in ({}, {"filter": "not_indexed"}, {"filter": "canonical"}, {"filter": "stale"}, {"filter": "errors"},
                   {"filter": "rich"}, {"q": "dinle"}, {"kind": "product", "start": 1, "limit": 2}):
        got = _three(c, "crawlbot/urls", **params)
        assert got == _old_urls(eng, **params), params
    # yeni denetim kaydı (tur) → hazır kayıt yenilenir
    with eng.begin() as conn:
        conn.execute(cb.INSPECT.insert(), [_inspect_row(f"{SITE}/k-7", "product", "7", "indexed", 0,
                                                        inspected_at=NOW)])
    got, _ = _get(c, "crawlbot/urls")
    assert got == _old_urls(eng) and got["total"] == 8


# ================================================================== site içi bağlantılar
def _seed_links(eng):
    pages = [(f"{SITE}/", "home", None), (f"{SITE}/k-1", "product", "1"), (f"{SITE}/k-2", "product", "2"),
             (f"{SITE}/sabahattin-ali", "author", None)]
    at = datetime(2026, 9, 20, tzinfo=timezone.utc)
    with eng.begin() as c:
        c.execute(TECH.insert(), [dict(tenant_id=T, url=u, kind=k, product_id=p, status=200, issues=",",
                                       data_json=dumps({"internalLinks": 3, "finalUrl": u}), checked_at=at)
                                  for u, k, p in pages])
        c.execute(SNAP.insert().values(tenant_id=T, kind="sitemaps", saved_at=at,
                                       data_json=dumps({"totalUrls": 3, "missing": [{"url": f"{SITE}/k-5"}]})))
    anchors = {
        f"{SITE}/": [{"href": "/k-1", "text": "Dinle"}, {"href": "/sabahattin-ali", "text": "Sabahattin Ali"},
                     {"href": "/roman", "text": "tıklayın"}],
        f"{SITE}/k-1": [{"href": "/sabahattin-ali", "text": "Sabahattin Ali"}, {"href": "/k-2", "text": ""}],
        f"{SITE}/k-2": [{"href": "/k-1", "text": "detay", "rel": "nofollow"}],
        f"{SITE}/sabahattin-ali": [{"href": "/k-1", "text": "Dinle"}, {"href": "/k-3", "text": "Madonna"}],
    }
    for u, a in anchors.items():
        links_mod.record(eng, T, SITE, u, u, {"anchors": a, "robots": []})


def _old_links(seo, view, kind="", q="", start=0, limit=50):
    data = seo.links.result(force=True)      # eski uç: grafik istekte hesaplanır (bu işlev değişmedi)
    rows = [r for r in data["lists"][view] if (not kind or r.get("kind") == kind) and links_mod._match(r, q)]
    summary = {k: v for k, v in data["summary"].items() if k != "computedAt"}
    return _norm(summary), len(rows), _norm(rows[start:start + limit])


def test_links_equal_old_graph_calculation(client):
    c, eng, seo = client
    _seed(eng)
    _seed_links(eng)
    for view in links_mod.VIEWS:
        for params in ({}, {"kind": "product"}, {"q": "dinle"}, {"start": 1, "limit": 1}):
            got = _three(c, "links", view=view, **params)
            summary, total, items = _old_links(seo, view, **params)
            assert {k: v for k, v in got["summary"].items() if k != "computedAt"} == summary, (view, params)
            assert got["total"] == total and got["items"] == items, (view, params)
    got, _ = _get(c, "links", view="orphans")
    assert got["summary"]["counts"]["orphans"] >= 1 and got["summary"]["crawledPages"] == 4


def test_links_while_crawl_runs_serve_last_record_and_refresh_in_background(client, monkeypatch):
    c, eng, seo = client
    _seed(eng)
    _seed_links(eng)
    first, _ = _get(c, "links", view="orphans")
    seo.tech = SimpleNamespace(state={"running": True})
    # tarama bir sayfa daha yazdı: girdi değişti, ama tur sürerken son kayıt gösterilir (istek grafiği beklemez)
    links_mod.record(eng, T, SITE, f"{SITE}/k-2", f"{SITE}/k-2", {"anchors": [{"href": "/k-5", "text": "Yol"}], "robots": []})
    calls = []
    real = seo.links.result
    monkeypatch.setattr(seo.links, "result", lambda force=False: calls.append(1) or real(force))
    during, _ = _get(c, "links", view="orphans")
    assert (during["summary"], during["items"]) == (first["summary"], first["items"]) and not calls
    # kayıt RUNNING_REUSE'dan eski: yine son kayıt döner, yenisi arkada hesaplanır
    monkeypatch.setattr(links_mod, "RUNNING_REUSE", 0)
    again, _ = _get(c, "links", view="orphans")
    assert (again["summary"], again["items"]) == (first["summary"], first["items"])
    deadline = time.monotonic() + 20
    while hazir._arkada and time.monotonic() < deadline:
        time.sleep(0.05)
    assert calls, "arka plan hesabı koşmadı"
    seo.tech.state["running"] = False
    after, _ = _get(c, "links", view="orphans")
    summary, total, items = _old_links(seo, "orphans")
    assert after["total"] == total and after["items"] == items and after["items"] != first["items"]


# ================================================================== açılış ısıtması
def test_opening_warm_skips_test_database_and_env_off(client, monkeypatch):
    _, _, seo = client
    assert hazir.acilis(seo) is False                  # SQLite: arka plan iş parçacığı test okumalarıyla yarışırdı
    monkeypatch.setenv("SEO_HAZIR_ACILIS", "0")
    assert hazir.acilis(SimpleNamespace()) is False


def test_opening_warm_waits_for_runtime_then_warms_every_registered(monkeypatch):
    monkeypatch.delenv("SEO_HAZIR_ACILIS", raising=False)
    live = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    state = {"rt": None}
    seo = SimpleNamespace(runtime=lambda: state["rt"], conf=lambda k: "")
    done = []
    monkeypatch.setattr(hazir, "isit", lambda s, wait=None, poll=15.0: done.append((s, wait)))
    assert hazir.acilis(seo, poll=0.01, wait=5) is True
    time.sleep(0.1)
    assert not done                                    # çalışma ortamı henüz kurulmadı: bekler
    state["rt"] = SimpleNamespace(store=SimpleNamespace(engine=live))
    deadline = time.monotonic() + 5
    while not done and time.monotonic() < deadline:
        time.sleep(0.01)
    assert done == [(seo, 0)]                          # okuma beklenmez: açılışta arka plan okuması yok


def test_every_new_calculation_is_registered_for_warming(client):
    _, _, seo = client
    names = {n for n, _ in seo.hazir_isiticilar}
    assert {"links", "opportunities", "opportunities.products", "entity", "crawlbot.products", "crawlbot.rows",
            "shopping", "crm.rows", "overview.products", "crm.summary", "faq.list"} <= names


def test_sources_show_ready_record_origin_and_no_uncovered_numbers(client):
    c, eng, seo = client
    _seed(eng, crm_all=True)
    _seed_inspect(eng)
    _seed_links(eng)
    for path in ("shopping", "crm", "crawlbot", "crawlbot/urls", "entity", "links", "opportunities"):
        data = c.get("/api/v1/seo-geo/" + path).json()
        k = data["kaynaklar"]
        assert not k.get("error"), (path, k)
        assert P.uncovered_numbers(data) == [], path
        hz = [s for s in k["sources"].values() if "semantic_seo_hazir" in s["sql"]]
        assert hz and all(s["origin"] for s in hz), path
