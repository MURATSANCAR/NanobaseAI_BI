"""SEO & GEO ekran hızı (2026-09-29): hazır hesap (`seo_geo/hazir.py`) ve hızlandırılan hesaplar.

Denetlenen: (1) eski hesap = yeni hesap — sorgu–sayfa eşlemesinde satıştaki baskı ve kategori araması, rehber
konularında kümeleme, yazar dışlama ve niyet kalıbı; eski kodlar burada birebir durur, rastgele ama sabit tohumlu
veriyle karşılaştırılır; (2) hazır hesap: ilk hesap = tablodan okunan = bellekten dönen; girdi değişince yeniden
hesaplanır; hesabı kuran okumalar köken olarak yazılır; (3) uçlar: ürün öncelik sırası ve sayfalar eski sorgu/hesapla
aynı; sorgu–sayfa ucunun «kaynaklar»ında hazır kaydın kökeni var, kaynaksız rakam yok.
Kabul (gerçek veriyle, sunucuda): `scripts/acceptance/seo-hiz/`.
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from semantic_bridge import provenance as P
from semantic_bridge import seo_geo
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.seo_geo import guides, hazir, keymap, pages as pages_mod, rules
from semantic_bridge.seo_geo.cannibal import same_title
from semantic_bridge.seo_geo.opportunities import OPPS
from semantic_bridge.seo_geo.store import LINKS, PRODUCTS, PROPOSALS, dumps
from semantic_layer.store.catalog_store import open_store

T = "t1"
SITE = "https://timas.com.tr"


# ================================================================== eski hesaplar (değiştirilmeden kopya)
_NEW_DECIDE = keymap.decide     # kitap dışı türler değişmedi: eski kopya onlarda yeni koda devreder


def _old_match_category(q, index):
    best = None
    for c in index["categories"]:
        if c["tokens"] <= q and (best is None or len(c["tokens"]) > len(best["tokens"])):
            best = c
    return best


def _old_decide(intent, rank, index):
    kind = intent["intent"]
    rl = keymap.TYPE_LABEL.get(rank["type"], rank["type"]).lower()
    if kind == "kitap":
        b = intent["book"]
        fit = b
        if not b.get("active", True):
            fit = next((x for x in sorted(index["books"], key=lambda x: -(x.get("sales") or 0))
                        if x.get("active", True) and x["id"] != b["id"] and same_title(x.get("name"), b.get("name"))), None)
            if not fit:
                return "bosluk", None, f"Arama «{b.get('name')}» kitabını arıyor; kitap satışta değil ve satıştaki baskısı yok."
        fit_page = {"type": "product", "url": fit.get("url"), "name": fit.get("name"), "id": fit["id"]}
        if rank["type"] == "product" and (rank.get("id") == fit["id"] or same_title(rank.get("name"), fit.get("name"))):
            if rank.get("active") is False and rank.get("id") != fit["id"]:
                return "yanlis", fit_page, "Kitabın satıştan kalkmış baskısı sıralanıyor; satıştaki baskı hedeflenmeli."
            return "eslesme", keymap._page_as_target(rank), "Arama kitabın adını taşıyor; kitabın sayfası sıralanıyor."
        if rank["type"] == "product":
            return "yanlis", fit_page, f"Arama «{fit.get('name')}» kitabını arıyor; başka bir kitabın sayfası sıralanıyor."
        return "yanlis", fit_page, f"Arama «{fit.get('name')}» kitabını arıyor; {rl} sıralanıyor, kitap sayfası değil."
    return _NEW_DECIDE(intent, rank, index)


def _old_cluster(items, exclude=None):
    exclude = exclude or []
    clusters = []
    for it in sorted(items, key=lambda x: (-(x.get("impressions") or 0), x["text"])):
        terms = guides.core_terms(it["text"])
        core = {s for s, _ in terms}
        words = {s for s in core if not s.isdigit()}
        rng = guides.ages(it["text"])
        if not words and not rng:
            continue
        if words and any(words == name or (len(words) >= 2 and words <= name) for name in exclude if name):
            continue
        nums = {s for s in core if s.isdigit()}
        for c in clusters:
            if c["_nums"] == nums and c["_ages"] == rng and (guides._similar(words, c["_words"]) or not words and not c["_words"]):
                c["queries"].append(it)
                break
        else:
            clusters.append({"_words": words, "_nums": nums, "_ages": rng, "_terms": terms, "queries": [it]})
    out = []
    for c in clusters:
        head = c["queries"][0]
        pos = [q["position"] for q in c["queries"] if q.get("position")]
        text = head["text"].strip()
        age_tag = {f"yas:{c['_ages'][0]}-{c['_ages'][1]}"} if c["_ages"] else set()
        out.append({
            "key": guides.topic_key(c["_words"] | c["_nums"] | age_tag), "title": text[:1].upper() + text[1:],
            "terms": [w for s, w in c["_terms"] if not s.isdigit()],
            "ages": list(c["_ages"]) if c["_ages"] else None,
            "impressions": sum(int(q.get("impressions") or 0) for q in c["queries"]),
            "clicks": sum(int(q.get("clicks") or 0) for q in c["queries"]),
            "position": round(min(pos), 1) if pos else None,
            "sources": sorted({q.get("source") or "arama" for q in c["queries"]}),
            "queries": [{"text": q["text"], "impressions": int(q.get("impressions") or 0), "clicks": int(q.get("clicks") or 0),
                         "position": q.get("position"), "source": q.get("source") or "arama"} for q in c["queries"]],
        })
    out.sort(key=lambda t: (-t["impressions"], -len(t["queries"]), t["title"]))
    return out


# ================================================================== sabit tohumlu veri
TITLE_WORDS = ["dinle", "madonna", "kürk", "mantolu", "sessiz", "ev", "aşk", "bir", "gece", "yol", "deniz", "çocuk",
               "masal", "tarih", "ruh", "kalp", "yıldız", "şehir", "zaman", "kuş"]
AUTHOR_WORDS = ["ahmet", "ümit", "sabahattin", "ali", "elif", "şafak", "orhan", "mehmet", "ayşe", "kara"]
CAT_WORDS = ["roman", "tarih", "çocuk", "masal", "şiir", "deneme", "din", "tasavvuf", "bilim"]
EDITION = ["(Ciltli)", "Yeni Baskı", "Cep Boy", "Özel Baskı", ""]


def _catalog(seed: int):
    rnd = random.Random(seed)
    products, links = [], []
    for i in range(260):
        title = " ".join(rnd.sample(TITLE_WORDS, rnd.randint(1, 3)))
        name = (title.title() + " " + rnd.choice(EDITION)).strip()
        author = " ".join(rnd.sample(AUTHOR_WORDS, 2)).title()
        products.append({"id": str(i), "name": name, "url": f"{SITE}/k-{i}", "author": author,
                         "authorId": str(sum(map(ord, author)) % 50), "sales": rnd.choice([0, 1, 5, 5, 10, 50, 100]),
                         "active": rnd.random() > 0.35})
    for j in range(25):
        links.append({"type": "model", "id": str(j), "name": " ".join(rnd.sample(AUTHOR_WORDS, 2)).title(),
                      "url": f"{SITE}/yazar-{j}"})
    for j in range(40):
        links.append({"type": "category", "id": str(100 + j), "name": " ".join(rnd.sample(CAT_WORDS, rnd.randint(1, 3))).title(),
                      "url": f"{SITE}/kategori-{j}"})
    links.append({"type": "blog", "id": "900", "name": "Okuma Listesi", "url": f"{SITE}/blog/okuma"})
    return products, links


def _rows(seed: int, products, links):
    rnd = random.Random(seed + 1)
    urls = [p["url"] for p in products] + [l["url"] for l in links] + [f"{SITE}/", f"{SITE}/baska-sayfa"]
    queries = []
    for _ in range(700):
        k = rnd.random()
        if k < 0.4:
            p = rnd.choice(products)
            q = p["name"].lower() + (" " + p["author"].lower() if rnd.random() < 0.3 else "")
        elif k < 0.55:
            q = rnd.choice(products)["author"].lower() + " kitapları"
        elif k < 0.7:
            q = " ".join(rnd.sample(CAT_WORDS, rnd.randint(1, 3))) + rnd.choice(["", " kitapları", " önerileri"])
        elif k < 0.8:
            q = "en iyi " + rnd.choice(CAT_WORDS) + " kitapları"
        elif k < 0.85:
            q = "timaş yayınları"
        else:
            q = " ".join(rnd.sample(TITLE_WORDS + CAT_WORDS, 2))
        queries.append(q)
    rows = []
    for q in queries:
        for _ in range(rnd.randint(1, 3)):
            rows.append({"keys": [q, rnd.choice(urls)], "clicks": rnd.randint(0, 20), "impressions": rnd.randint(5, 90),
                         "position": round(rnd.uniform(1, 30), 1)})
    return rows


# ================================================================== (1) eski = yeni
@pytest.mark.parametrize("seed", [1, 7, 42])
def test_keymap_new_edition_and_category_lookup_equals_old(seed, monkeypatch):
    products, links = _catalog(seed)
    rows = _rows(seed, products, links)
    new = keymap.analyse(rows, keymap.build_index(products, links))
    monkeypatch.setattr(keymap, "decide", _old_decide)
    monkeypatch.setattr(keymap, "match_category", _old_match_category)
    old = keymap.analyse(rows, keymap.build_index(products, links))
    assert old == new
    assert len(new) > 100 and any(i["intent"] == "kitap" for i in new)


def test_active_edition_matches_old_scan_for_every_inactive_book():
    products, links = _catalog(3)
    ix = keymap.build_index(products, links)
    for b in ix["books"]:
        if b.get("active", True):
            continue
        old = next((x for x in sorted(ix["books"], key=lambda x: -(x.get("sales") or 0))
                    if x.get("active", True) and x["id"] != b["id"] and same_title(x.get("name"), b.get("name"))), None)
        assert keymap.active_edition(b, ix) is old


def _guide_items(seed: int):
    rnd = random.Random(seed)
    pool = ["değerler eğitimi", "degerler egitimi", "tasavvuf", "tarihi roman", "roman", "çocuk", "masal", "şiir",
            "bilim kurgu", "kişisel gelişim", "din", "peygamber", "hikaye"]
    tails = [" kitapları", " kitap önerileri", " önerileri", " için kitap", " okunması gereken kitaplar"]
    heads = ["", "en iyi ", "9-11 yaş ", "10 yaş ", "3. sınıf ", "ilkokul ", "lise ", "yeni başlayanlar için "]
    items = []
    for _ in range(600):
        text = rnd.choice(heads) + " ".join(rnd.sample(pool, rnd.randint(1, 2))) + rnd.choice(tails)
        items.append({"text": text, "impressions": rnd.randint(0, 50), "clicks": rnd.randint(0, 5),
                      "position": rnd.choice([None, round(rnd.uniform(1, 40), 1)]), "source": rnd.choice(["arama", "soru"])})
    items += [{"text": "lise kitapları", "impressions": 3, "clicks": 0, "position": None, "source": "arama"},
              {"text": "okul öncesi", "impressions": 3, "clicks": 0, "position": 2.0, "source": "arama"}]
    exclude = [{guides.stem(w) for w in n.split()} for n in ("Tasavvuf", "Tarihi Roman Yazarı", "Çocuk Masal", "Şiir")]
    exclude += [set(), {guides.stem("Bilim"), guides.stem("Kurgu")}]
    return items, exclude


@pytest.mark.parametrize("seed", [2, 11, 99])
def test_guides_indexed_cluster_equals_old(seed):
    items, exclude = _guide_items(seed)
    assert guides.cluster(items, exclude) == _old_cluster(items, exclude)
    assert guides.cluster(items) == _old_cluster(items)


def test_list_intent_single_pattern_equals_old_any():
    items, _ = _guide_items(5)
    texts = [i["text"] for i in items] + ["kürk mantolu madonna", "timaş yayınları kitapları", "hangi kitabı okumalı",
                                          "ne okunmalı", "12/14 yaş grubu", "okuma listesi", "kadınlar için"]
    for t in texts:
        q = guides.norm(t)
        old = bool(q) and not guides._NAV.search(q) and any(p.search(q) for p in guides.INTENT)
        assert guides.is_list_intent(t) == old, t


# ================================================================== (2) hazır hesap
def _regexp_replace(s, pattern, repl, flags=""):
    return None if s is None else re.sub(pattern, repl, s, count=0 if "g" in (flags or "") else 1)


def _pg_functions(dbapi_conn, _rec=None):
    """Canlı veritabanında olan regexp_replace test veritabanında yok: aynı davranışla tanımlanır."""
    dbapi_conn.create_function("regexp_replace", 4, _regexp_replace)


def _engine():
    eng = open_store("sqlite://").engine
    event.listen(eng, "connect", _pg_functions)
    with eng.connect() as c:
        _pg_functions(c.connection.driver_connection)
    return eng


class _Seo:
    def __init__(self, eng):
        self.eng = eng

    def engine(self):
        from semantic_bridge.seo_geo.store import ensure

        ensure(self.eng)
        return self.eng

    def tenant(self):
        return T

    def conf(self, key):
        return ""


def _product(pid, name, sales=0, views=0, score=80, active=True, rules_=",", at=None, **extra):
    data = {"ProductId": pid, "ProductName": name, "CountTotalSales": str(sales), "StatViews": str(views),
            "SeoLink": f"k-{pid}", **extra}
    return dict(tenant_id=T, product_id=pid, code=f"K{pid}", name=name, brand="Timaş", active=active, score=score,
                issues_json="[]", rules=rules_, data_json=dumps(data),
                synced_at=at or datetime(2026, 9, 1, tzinfo=timezone.utc))


def test_hazir_compute_then_table_then_memory_and_recompute_on_change():
    eng = _engine()
    seo = _Seo(eng)
    seo.engine()
    with eng.begin() as c:
        c.execute(PRODUCTS.insert(), [_product("1", "Dinle", 5), _product("2", "Madonna", 9)])
    calls = []

    def compute():
        calls.append(1)
        with eng.connect() as c:
            names = [r[0] for r in c.execute(sa.select(PRODUCTS.c.name).where(PRODUCTS.c.tenant_id == T)
                                             .order_by(PRODUCTS.c.product_id))]
        return {"names": names, "pair": ("a", 1), "at": datetime(2026, 9, 2, tzinfo=timezone.utc)}

    def stamp():
        return hazir.damga(seo, [(PRODUCTS, PRODUCTS.c.synced_at)], ek=("site",))

    first = hazir.al(seo, "deneme", stamp(), compute)
    assert first == {"names": ["Dinle", "Madonna"], "pair": ["a", 1], "at": "2026-09-02T00:00:00+00:00"}
    assert hazir.al(seo, "deneme", stamp(), compute) == first and len(calls) == 1        # bellek
    hazir.unut()
    assert hazir.al(seo, "deneme", stamp(), compute) == first and len(calls) == 1        # tablo
    # hesabı kuran okuma köken olarak yazıldı
    origin = Y.koken_oku(eng, T, hazir.KOKEN + "deneme")
    assert origin and any("semantic_seo_products" in r["sql_text"] for r in origin)
    # girdi değişti → yeniden hesap
    with eng.begin() as c:
        c.execute(PRODUCTS.insert(), [_product("3", "Yeni", 1, at=datetime(2026, 9, 3, tzinfo=timezone.utc))])
    third = hazir.al(seo, "deneme", stamp(), compute)
    assert third["names"] == ["Dinle", "Madonna", "Yeni"] and len(calls) == 2
    # silinen satır da (sayı değişir) yeniden hesaplatır
    with eng.begin() as c:
        c.execute(PRODUCTS.delete().where(PRODUCTS.c.product_id == "3"))
    assert hazir.al(seo, "deneme", stamp(), compute)["names"] == ["Dinle", "Madonna"] and len(calls) == 3


def test_hazir_refuses_values_json_cannot_carry_faithfully():
    eng = _engine()
    seo = _Seo(eng)
    with pytest.raises(TypeError):
        hazir.al(seo, "kume", hazir.damga(seo, []), lambda: {"x": {1, 2}})


def test_isit_waits_for_background_reads_then_warms_every_registered():
    seo = SimpleNamespace(conf=lambda k: "")
    done = []
    busy = {"n": 2}

    def still_busy():
        busy["n"] -= 1
        return busy["n"] > 0

    hazir.mesgul(seo, still_busy)
    hazir.kaydet(seo, "a", lambda: done.append("a"))
    hazir.kaydet(seo, "b", lambda: (_ for _ in ()).throw(RuntimeError("düştü")))
    hazir.kaydet(seo, "c", lambda: done.append("c"))
    out = hazir.isit(seo, wait=5, poll=0)
    assert done == ["a", "c"] and str(out["b"]).startswith("hata") and busy["n"] <= 0


# ================================================================== (3) uçlar
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


def _seed_products(eng):
    rows = [
        _product("1", "Dinle", 100, 5, score=50, rules_=",meta_missing,", ModelId="7", Model="Sabahattin Ali",
                 DefaultCategoryId="30"),
        _product("2", "Dinle (Ciltli)", 100, 9, score=60, ModelId="7", Model="Sabahattin Ali", DefaultCategoryId="30"),
        _product("3", "Madonna", 7, 0, score=90, rules_=",meta_missing,", ModelId="8", Model="Ayşe Kara"),
        _product("4", "Eski", 500, 1, score=40, active=False, ModelId="8", Model="Ayşe Kara"),
        _product("5", "Yol", 0, 0, score=65, ModelId="9", Model="Elif Yazar", BrandId="3"),
        _product("6", "Gece", 7, 0, score=65, ModelId="9", Model="Elif Yazar", BrandId="3"),
        _product("7", "Deniz", 7, 0, score=65),
    ]
    links = [dict(tenant_id=T, link="sabahattin-ali", type="model", table_id="7", title="Sabahattin Ali | Timaş",
                  description="d" * 130, data_json="{}", synced_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
             dict(tenant_id=T, link="ayse-kara", type="model", table_id="8", title="Ayşe Kara", description="",
                  data_json="{}", synced_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
             dict(tenant_id=T, link="roman", type="category", table_id="30", title="Roman", description=None,
                  data_json="{}", synced_at=datetime(2026, 9, 1, tzinfo=timezone.utc))]
    with eng.begin() as c:
        c.execute(PRODUCTS.insert(), rows)
        c.execute(LINKS.insert(), links)


def test_products_priority_order_equals_old_sql(client):
    c, eng, seo = client
    _seed_products(eng)
    from semantic_bridge.seo_geo import SALES, VIEWS

    def old(cond, start, limit):
        with eng.connect() as conn:
            total = conn.execute(sa.select(sa.func.count()).select_from(PRODUCTS).where(*cond)).scalar() or 0
            rows = conn.execute(sa.select(PRODUCTS.c.product_id).where(*cond).order_by(
                SALES.desc(), VIEWS.desc(), PRODUCTS.c.score.asc(), PRODUCTS.c.product_id)
                .offset(start).limit(limit)).all()
        return total, [r[0] for r in rows]

    base = [PRODUCTS.c.tenant_id == T, PRODUCTS.c.active.is_(True)]
    for params, cond in (({}, base), ({"rule": "meta_missing"}, base + [PRODUCTS.c.rules.like("%,meta_missing,%")]),
                         ({"q": "dinle"}, base + [sa.or_(PRODUCTS.c.name.ilike("%dinle%"), PRODUCTS.c.code.ilike("%dinle%"),
                                                         PRODUCTS.c.brand.ilike("%dinle%"))])):
        for start, limit in ((0, 50), (0, 2), (2, 2), (5, 3)):
            data = c.get("/api/v1/seo-geo/products", params={**params, "start": start, "limit": limit}).json()
            total, ids = old(cond, start, limit)
            assert data["total"] == total and [i["id"] for i in data["items"]] == ids, (params, start, limit)
    # Eşitleme ürünü değiştirince hazır sıra yeniden kurulur ve yine eski sorguyla aynıdır. Test veritabanında
    # `CAST(data_json AS JSON)` sayısal yakınlık alır (JSON metni 0 olur): satış/görüntülenme bütün ürünlerde 0, sıra
    # puana düşer. Bu yüzden değişiklik puanı da taşır; eski sıra korunsaydı ilk ürün «1» (puan 50) kalırdı.
    with eng.begin() as conn:
        conn.execute(PRODUCTS.update().where(PRODUCTS.c.product_id == "7").values(
            data_json=dumps({"ProductId": "7", "CountTotalSales": "9999"}), score=1,
            synced_at=datetime(2026, 9, 5, tzinfo=timezone.utc)))
    after = c.get("/api/v1/seo-geo/products").json()
    total, ids = old(base, 0, 50)
    assert after["total"] == total and [i["id"] for i in after["items"]] == ids
    assert ids[0] == "7"


def test_pages_equal_old_per_request_calculation(client):
    c, eng, seo = client
    _seed_products(eng)
    with eng.begin() as conn:
        conn.execute(PROPOSALS.insert().values(id="p1", tenant_id=T, product_id="model:7", status="hazir", fields_json="{}",
                                               before_json="{}", created_at=datetime(2026, 9, 2, tzinfo=timezone.utc)))
    lim = rules.thresholds(seo.conf)
    site = (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
    with eng.connect() as conn:
        links = [dict(r) for r in conn.execute(sa.select(LINKS.c.link, LINKS.c.type, LINKS.c.table_id, LINKS.c.title,
                                                         LINKS.c.description).where(LINKS.c.tenant_id == T)).mappings()]
        prods = [json.loads(r[0]) for r in conn.execute(sa.select(PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == T))]
    st = pages_mod.stats(prods)
    for type_, q in (("model", ""), ("model", "ali"), ("category", ""), ("brand", "")):
        states = {"model:7": "hazir"}
        items = []
        for l in links:
            if l["type"] != type_:
                continue
            s = st.get((type_, str(l["table_id"])), {})
            name = rules.text_of(l.get("title")).split("|")[0].strip() or l["link"].replace("-", " ").title()
            if q.strip() and q.strip().casefold() not in (name + " " + l["link"]).casefold():
                continue
            a = pages_mod.audit(type_, name, l["title"], l["description"], lim)
            items.append({"id": str(l["table_id"]), "name": name, "link": l["link"], "url": f"{site}/{l['link']}",
                          "books": s.get("books", 0), "sales": s.get("sales", 0), "score": a["score"],
                          "issues": len(a["issues"]), "proposal": states.get(f"{type_}:{l['table_id']}")})
        items.sort(key=lambda x: (-x["sales"], -x["books"], x["name"]))
        data = c.get("/api/v1/seo-geo/pages", params={"type": type_, "q": q}).json()
        data.pop("kaynaklar", None)
        assert data == {"total": len(items), "items": items, "withBooks": sum(1 for x in items if x["books"])}, (type_, q)


def test_keymap_endpoint_same_after_restart_and_sources_show_origin(client):
    c, eng, seo = client
    _seed_products(eng)
    rows = [{"keys": ["dinle", f"{SITE}/k-2"], "clicks": 9, "impressions": 80, "position": 2.0},
            {"keys": ["eski", f"{SITE}/k-4"], "clicks": 3, "impressions": 60, "position": 4.0},
            {"keys": ["sabahattin ali kitapları", f"{SITE}/k-1"], "clicks": 5, "impressions": 90, "position": 3.0},
            {"keys": ["roman", f"{SITE}/roman"], "clicks": 1, "impressions": 40, "position": 6.0}]
    with eng.begin() as conn:
        conn.execute(OPPS.insert().values(tenant_id=T, kind="query_page", start_date="2026-08-30", end_date="2026-09-26",
                                          rows_json=dumps(rows), saved_at=datetime(2026, 9, 27, tzinfo=timezone.utc)))
    first = c.get("/api/v1/seo-geo/keymap", params={"kind": "hepsi"}).json()
    hazir.unut()                                   # süreç yeniden başladı: tablodan
    second = c.get("/api/v1/seo-geo/keymap", params={"kind": "hepsi"}).json()
    third = c.get("/api/v1/seo-geo/keymap", params={"kind": "hepsi"}).json()   # bellekten
    k1, k2 = first.pop("kaynaklar"), second.pop("kaynaklar")
    third.pop("kaynaklar")
    assert first == second == third and first["total"] == 4
    direct = json.loads(json.dumps(keymap.compute(seo)["items"]))
    assert [{k: v for k, v in i.items() if k != "decision"} for i in first["items"]] == direct
    for k in (k1, k2):
        assert not k.get("error")
        hz = [s for s in k["sources"].values() if "semantic_seo_hazir" in s["sql"]]
        assert hz and any(any(o in k["sources"] and "semantic_seo_opps" in k["sources"][o]["sql"] for o in s["origin"])
                          for s in hz)
    for d, k in ((first, k1), (second, k2)):
        d["kaynaklar"] = k
        assert P.uncovered_numbers(d) == [] and P.problems(d) == []
