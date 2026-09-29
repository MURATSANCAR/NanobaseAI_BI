"""Sorgu–sayfa eşlemesi: her önemli Google araması için sitemizdeki hedef sayfa.

Kaynak: fırsat listesinin sakladığı Search Console sorgu+sayfa kırılımı (`semantic_seo_opps`, tür `query_page`, son 28
gün; opportunities.source). Search Console'a ayrıca istek atılmaz; hiçbir yere yazılmaz.

Toplam gösterimi en az `MIN_IMPRESSIONS` olan her arama için:
1. Sıralanan sayfa: aramada en çok tıklanan (eşitse en çok gösterilen) adresimiz; türü T-soft ürün kaydından (`SeoLink`)
   ya da `link/getLinks` kaydından (yazar/kategori/yayınevi/…) okunur.
2. Aramanın türü (sözlükle, model yok): kitap adı geçiyorsa `kitap` (ürün adları), yazar adı geçiyorsa `yazar` (T-soft
   `Model` ve yazar sayfaları), soru/liste kalıbıysa `bilgi` ("en iyi", "önerileri", "okunması gereken" …), kategori
   adı geçiyorsa `kategori`, yalnız marka ise `marka`; hiçbiri değilse `diger`.
3. Karar:
   - `eslesme`: sıralanan sayfanın türü aramaya uyuyor (kitap araması → o kitabın sayfası …); hedef sıralanan sayfa.
   - `yanlis` («yanlış sayfa sıralanıyor»): aramaya uyan sayfamız var ama başka bir sayfa sıralanıyor; hedef uyan sayfa.
   - `bosluk`: aramaya uyan sayfamız yok — yazarın sitede sayfası yok, kitap satışta değil, ya da soru/liste araması
     için rehber/liste sayfası yok (rehber taslağı önerilir).
   Sitede hiç ürünü olmayan bir kitabın ya da yazarın adı sözlükte olmadığından tanınmaz; bu aramalar `diger` kalır.

Karar (hedef onayı ya da ret) sorgu başına saklanır; liste CSV olarak indirilir.
"""
from __future__ import annotations

import collections
import csv
import hashlib
import io
import re
import threading
from typing import Any, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from . import connections, hazir, rules
from .cannibal import EDITION_SIMILARITY, LINK_LABEL, same_title, title_tokens
from .opportunities import OPPS, ensure_table as ensure_opps, fold, is_brand, path_key, source
from .pages import _num
from .store import GSC, LINKS, PRODUCTS, _md, iso, loads, now

#: Eşikler ekranda da gösterilir.
MIN_IMPRESSIONS = 30             # bundan az gösterimli arama eşlenmez (28 günlük toplam)
KINDS = {"eslesme": "Doğru sayfa", "yanlis": "Yanlış sayfa sıralanıyor", "bosluk": "Sayfamız yok"}
INTENT_LABEL = {"kitap": "Kitap araması", "yazar": "Yazar araması", "kategori": "Konu/kategori araması",
                "bilgi": "Soru ya da liste araması", "marka": "Marka araması", "diger": "Türü belirlenemedi"}
TYPE_LABEL = {**LINK_LABEL, "home": "Anasayfa", "other": "Diğer sayfa"}
#: Aramanın türünü değiştirmeyen sözcükler (kitap/yazar adı dışında kalanı "boş" saymak için).
GENERIC = frozenset({"kitap", "kitabi", "kitaplari", "kitaplar", "kitabinin", "oku", "okuma", "pdf", "ozet", "ozeti",
                     "fiyat", "fiyati", "fiyatlari", "satin", "al", "yorum", "yorumlari", "konusu", "indir", "e", "sesli",
                     "roman", "romani", "yazar", "yazari", "yazarinin", "kimdir", "hayati", "eserleri", "tum", "butun",
                     "timas", "yayinlari", "yayinevi", "yayinlar", "ve", "ile", "de", "da", "nin", "nun", "in"})
BRAND_WORDS = frozenset({"timas", "yayinlari", "yayinevi", "yayinlar", "yayincilik"})
#: Kategori adında eşleşmeye katılmayan kelimeler ("Roman" kategorisi "roman" kelimesiyle eşleşsin diye GENERIC değil).
CATEGORY_STOP = frozenset({"ve", "ile", "de", "da", "kitap", "kitaplari", "kitaplar", "diger"})
INFO = re.compile(r"\b(en iyi|en cok|en guzel|oneri\w*|tavsiye\w*|liste\w*|okunmasi gereken|okunacak|hangi|nedir|nasil|"
                  r"neden|nicin|ne zaman|kac yas|yas icin|yasa uygun|sinif icin|\d+\s*sinif|\d+\s*yas)\b")
FIT = {"kitap": {"product"}, "yazar": {"model"}, "kategori": {"category"},
       "bilgi": {"category", "blog", "content", "page", "tag"}, "marka": {"home", "brand"}}
_TOKEN = re.compile(r"[a-z0-9]+")


class KeymapDecision(BaseModel):
    """Modül düzeyinde olmalı (bkz. tests/test_seo_feature_routes.py)."""
    query: str = Field(min_length=1, max_length=500)
    target: str = Field(default="", max_length=800)      # onaylanan hedef adres; boş + reject: "hedef yok"
    note: str = Field(default="", max_length=1000)
    action: str = Field(default="approve", pattern="^(approve|reject)$")


DECISIONS = sa.Table(
    "semantic_seo_keymap_decisions", _md,  # sorgu başına hedef kararı; hiçbir yere gönderilmez
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("query_id", sa.String(40), primary_key=True),       # sha1(katlanmış sorgu)
    sa.Column("query", sa.String(500), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),           # onaylandi | reddedildi
    sa.Column("target", sa.String(800)),
    sa.Column("suggested", sa.String(800)),                       # karar anındaki önerilen hedef
    sa.Column("kind", sa.String(16)),                             # karar anındaki durum (eslesme | yanlis | bosluk)
    sa.Column("note", sa.String(1000)),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
)


# ------------------------------------------------------------------ saf işlevler (sınanır)
def tokens(text: Any) -> list[str]:
    return _TOKEN.findall(fold(str(text or "")))


def query_id(query: str) -> str:
    return hashlib.sha1(" ".join(tokens(query)).encode("utf-8")).hexdigest()


def build_index(products: list[dict[str, Any]], link_pages: list[dict[str, Any]]) -> dict[str, Any]:
    """products: [{id, name, url, author, authorId, sales, active}]; link_pages: [{type, id, name, url}].
    Dönen: kitap/yazar/kategori sözlükleri ve adres anahtarı → sayfa."""
    pages: dict[str, dict[str, Any]] = {}
    books: list[dict[str, Any]] = []
    for p in products:
        k = path_key(p.get("url"))
        if k and k != "/":
            pages.setdefault(k, {"type": "product", "id": p["id"], "name": p.get("name"), "url": p.get("url"),
                                 "active": p.get("active", True), "authorId": p.get("authorId")})
        tt = title_tokens(p.get("name"))
        if tt:
            books.append({**p, "tokens": tt, "key": k})
    author_page: dict[str, dict[str, Any]] = {}
    categories: list[dict[str, Any]] = []
    for lp in link_pages:
        k = path_key(lp.get("url"))
        if not k or k == "/":
            continue
        pages.setdefault(k, {"type": lp["type"], "id": str(lp.get("id") or ""), "name": lp.get("name"), "url": lp["url"]})
        if lp["type"] == "model" and lp.get("id"):
            author_page.setdefault(str(lp["id"]), {**lp, "key": k})
        if lp["type"] == "category":
            ct = frozenset(t for t in tokens(lp.get("name")) if t not in CATEGORY_STOP)
            if ct:
                categories.append({**lp, "key": k, "tokens": ct})
    authors: dict[str, dict[str, Any]] = {}
    for p in products:
        name = (p.get("author") or "").strip()
        aid = str(p.get("authorId") or "").strip()
        at = tuple(tokens(name))
        if not at:
            continue
        a = authors.setdefault(" ".join(at), {"name": name, "tokens": frozenset(at), "ids": set(), "books": 0, "active": 0})
        if aid and aid != "0":
            a["ids"].add(aid)
        a["books"] += 1
        a["active"] += 1 if p.get("active", True) else 0
    for aid, lp in author_page.items():  # sayfası olup ürünü olmayan yazar da tanınır
        at = tuple(tokens(lp.get("name")))
        if at:
            authors.setdefault(" ".join(at), {"name": lp.get("name"), "tokens": frozenset(at), "ids": set(), "books": 0,
                                              "active": 0})["ids"].add(aid)
    # Ters dizin: her ad kelimelerinden birinin altında durur. Ad bütünüyle aramada geçiyorsa o kelime de geçer;
    # böylece her arama yalnız kelimelerinin altındaki adlarla karşılaştırılır.
    by_tok: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for b in books:
        by_tok[min(b["tokens"])].append(b)
    by_author: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for a in authors.values():
        by_author[min(a["tokens"])].append(a)
    index = {"pages": pages, "books": books, "bookIndex": by_tok, "authors": list(authors.values()),
             "authorIndex": by_author, "authorPage": author_page, "categories": categories}
    _edition_index(index)
    _category_index(index)
    return index


def _edition_index(index: dict[str, Any]) -> dict[str, Any]:
    """Satıştaki baskı araması için: satıştaki kitaplar çok satandan aza (eşitlikte kayıt sırası) ve kelime → sıra.
    Eskiden her arama için bütün kitaplar yeniden sıralanıp adları yeniden köklenirdi (canlıda 87 sn)."""
    if "activeBySales" not in index:
        active = [b for b in sorted(index["books"], key=lambda x: -(x.get("sales") or 0)) if b.get("active", True)]
        by_tok: dict[str, list[int]] = collections.defaultdict(list)
        for pos, b in enumerate(active):
            for t in b["tokens"]:
                by_tok[t].append(pos)
        index.update(activeBySales=active, editionIndex=by_tok, editionFit={})
    return index


def _category_index(index: dict[str, Any]) -> dict[str, Any]:
    """Kategori adı kelimelerinden en küçüğü → kategorinin sırası (ad bütünüyle aramada geçiyorsa o kelime de geçer)."""
    if "categoryIndex" not in index:
        by_tok: dict[str, list[int]] = collections.defaultdict(list)
        for pos, c in enumerate(index["categories"]):
            by_tok[min(c["tokens"])].append(pos)
        index["categoryIndex"] = by_tok
    return index


def active_edition(b: dict[str, Any], index: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Satışta olmayan kitabın satıştaki başka baskısı: aynı ad (kelime benzerliği ≥ EDITION_SIMILARITY), en çok satan.
    `same_title` ile aynı ölçü; benzerlik eşiği sıfırdan büyük olduğundan en az bir ortak kelime şarttır, adaylar
    yalnız o kelimelerin altındakilerdir. Sonuç kitap başına bir kez hesaplanır."""
    _edition_index(index)
    memo = index["editionFit"]
    if b["id"] in memo:
        return memo[b["id"]]
    tb = b.get("tokens")
    if tb is None:
        tb = title_tokens(b.get("name"))
    found = None
    if tb:
        active = index["activeBySales"]
        for pos in sorted({p for t in tb for p in index["editionIndex"].get(t, ())}):
            x = active[pos]
            if x["id"] == b["id"]:
                continue
            tx = x["tokens"]
            if len(tx & tb) / len(tx | tb) >= EDITION_SIMILARITY:
                found = x
                break
    memo[b["id"]] = found
    return found


def _rest(q: set[str], used: set[str]) -> set[str]:
    return {t for t in q - used if t not in GENERIC}


def match_book(q: set[str], index: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Aramada adı bütünüyle geçen kitap; tek kelimelik adda aramada başka anlamlı kelime (yazar adı dışında) olmamalı.
    Birden çok kitap uyarsa en uzun ad, sonra satıştaki ve çok satan."""
    best = None
    for t in q:
        for b in index["bookIndex"].get(t, ()):
            if not b["tokens"] <= q:
                continue
            if len(b["tokens"]) == 1 and _rest(q, set(b["tokens"]) | set(tokens(b.get("author")))):
                continue
            rank = (len(b["tokens"]), bool(b.get("active", True)), b.get("sales") or 0)
            if best is None or rank > best[0]:
                best = (rank, b)
    return best[1] if best else None


def match_author(q: set[str], index: dict[str, Any]) -> Optional[dict[str, Any]]:
    best = None
    for a in (x for t in q for x in index["authorIndex"].get(t, ())):
        if not a["tokens"] <= q:
            continue
        if len(a["tokens"]) == 1 and (len(next(iter(a["tokens"]))) < 4 or _rest(q, set(a["tokens"]))):
            continue
        rank = (len(a["tokens"]), a["active"], a["books"])
        if best is None or rank > best[0]:
            best = (rank, a)
    return best[1] if best else None


def match_category(q: set[str], index: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Adı bütünüyle aramada geçen en uzun adlı kategori (eşitlikte listede önce gelen)."""
    _category_index(index)
    cats = index["categories"]
    best = None
    for pos in sorted({p for t in q for p in index["categoryIndex"].get(t, ())}):
        c = cats[pos]
        if c["tokens"] <= q and (best is None or len(c["tokens"]) > len(best["tokens"])):
            best = c
    return best


def classify_intent(query: str, index: dict[str, Any]) -> dict[str, Any]:
    """{intent, book?, author?, category?}. Öncelik: kitap > yazar > bilgi > kategori > marka > diğer."""
    q = set(tokens(query))
    folded = " ".join(tokens(query))
    book = match_book(q, index)
    author = match_author(q, index)
    category = match_category(q, index)
    if book:
        return {"intent": "kitap", "book": book, "author": author, "category": category}
    if author:
        return {"intent": "yazar", "author": author, "category": category}
    if INFO.search(folded):
        return {"intent": "bilgi", "category": category}
    if category:
        return {"intent": "kategori", "category": category}
    if is_brand(query) and not (q - BRAND_WORDS - GENERIC):
        return {"intent": "marka"}
    return {"intent": "diger"}


def page_of(url: Optional[str], index: dict[str, Any]) -> dict[str, Any]:
    k = path_key(url)
    if k == "/":
        return {"type": "home", "url": url, "key": k, "name": "Anasayfa", "id": None}
    p = index["pages"].get(k or "")
    if not p:
        return {"type": "other", "url": url, "key": k, "name": None, "id": None}
    return {**p, "url": url, "key": k}


def _target(p: dict[str, Any]) -> dict[str, Any]:
    return {"url": p.get("url"), "type": p.get("type"), "typeLabel": TYPE_LABEL.get(p.get("type") or "", p.get("type")),
            "name": p.get("name"), "id": p.get("id")}


def decide(intent: dict[str, Any], rank: dict[str, Any], index: dict[str, Any]) -> tuple[str, Optional[dict[str, Any]], str]:
    """(durum, hedef, gerekçe). `rank`: sıralanan sayfa (page_of)."""
    kind = intent["intent"]
    rl = TYPE_LABEL.get(rank["type"], rank["type"]).lower()
    if kind == "kitap":
        b = intent["book"]
        fit = b
        if not b.get("active", True):  # satıştaki başka baskısı varsa o hedef
            fit = active_edition(b, index)
            if not fit:
                return "bosluk", None, f"Arama «{b.get('name')}» kitabını arıyor; kitap satışta değil ve satıştaki baskısı yok."
        fit_page = {"type": "product", "url": fit.get("url"), "name": fit.get("name"), "id": fit["id"]}
        if rank["type"] == "product" and (rank.get("id") == fit["id"] or same_title(rank.get("name"), fit.get("name"))):
            if rank.get("active") is False and rank.get("id") != fit["id"]:
                return "yanlis", fit_page, "Kitabın satıştan kalkmış baskısı sıralanıyor; satıştaki baskı hedeflenmeli."
            return "eslesme", _page_as_target(rank), "Arama kitabın adını taşıyor; kitabın sayfası sıralanıyor."
        if rank["type"] == "product":
            return "yanlis", fit_page, f"Arama «{fit.get('name')}» kitabını arıyor; başka bir kitabın sayfası sıralanıyor."
        return "yanlis", fit_page, f"Arama «{fit.get('name')}» kitabını arıyor; {rl} sıralanıyor, kitap sayfası değil."
    if kind == "yazar":
        a = intent["author"]
        page = next((index["authorPage"][i] for i in sorted(a["ids"]) if i in index["authorPage"]), None)
        if not page:
            return "bosluk", None, (f"Arama {a['name']} yazarını arıyor; yazarın sitede sayfası yok"
                                    + (f" ({a['active']} kitabı satışta)." if a["active"] else "."))
        fit_page = {"type": "model", "url": page["url"], "name": page.get("name") or a["name"], "id": str(page.get("id"))}
        if rank.get("key") == page["key"]:
            return "eslesme", fit_page, "Yazar araması yazarın sayfasına düşüyor."
        if rank["type"] == "product":
            return "yanlis", fit_page, "Yazar araması tek bir kitabın sayfasına düşüyor; yazar sayfası hedeflenmeli."
        return "yanlis", fit_page, f"Yazar araması {rl} sıralanıyor; yazar sayfası hedeflenmeli."
    if kind == "kategori":
        c = intent["category"]
        fit_page = {"type": "category", "url": c["url"], "name": c.get("name"), "id": str(c.get("id") or "")}
        if rank.get("key") == c["key"]:
            return "eslesme", fit_page, "Konu araması kategori sayfasına düşüyor."
        return "yanlis", fit_page, f"Konu araması {rl} sıralanıyor; «{c.get('name')}» kategori sayfası hedeflenmeli."
    if kind == "bilgi":
        if rank["type"] in FIT["bilgi"]:
            return "eslesme", _page_as_target(rank), "Soru/liste araması bir liste ya da içerik sayfasına düşüyor."
        c = intent.get("category")
        if c:
            fit_page = {"type": "category", "url": c["url"], "name": c.get("name"), "id": str(c.get("id") or "")}
            return "yanlis", fit_page, (f"Soru/liste araması {rl} sıralanıyor; «{c.get('name')}» kategori sayfası daha uygun, "
                                        "yanına cevap veren bir rehber yazılabilir.")
        return "bosluk", None, ("Soru/liste araması; buna cevap veren rehber ya da liste sayfamız yok. Rehber taslağı "
                                "önerilir (Rehberler ekranı).")
    if kind == "marka":
        if rank["type"] in FIT["marka"]:
            return "eslesme", _page_as_target(rank), "Marka araması anasayfaya ya da yayınevi sayfasına düşüyor."
        home = {"type": "home", "url": "/", "name": "Anasayfa", "id": None}
        return "yanlis", home, f"Marka araması {rl} sıralanıyor; anasayfa hedeflenmeli."
    return "eslesme", _page_as_target(rank), "Aramanın türü belirlenemedi; en çok tıklanan sayfa hedef kabul edildi."


def _page_as_target(p: dict[str, Any]) -> dict[str, Any]:
    return {"type": p.get("type"), "url": p.get("url"), "name": p.get("name"), "id": p.get("id")}


def group(rows: list[dict[str, Any]], min_impr: int = MIN_IMPRESSIONS) -> list[dict[str, Any]]:
    """Search Console satırları ({"keys": [sorgu, sayfa], clicks, impressions, position}) → sorgu başına sayfalar."""
    by_q: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        keys = r.get("keys") or []
        if len(keys) < 2 or not keys[1]:
            continue
        by_q[str(keys[0])].append({"url": str(keys[1]), "clicks": float(r.get("clicks") or 0),
                                   "impressions": float(r.get("impressions") or 0), "position": float(r.get("position") or 0)})
    out = []
    for q, pages in by_q.items():
        impr = sum(p["impressions"] for p in pages)
        if impr < min_impr:
            continue
        pages.sort(key=lambda p: (-p["clicks"], -p["impressions"], p["position"] or 999, p["url"]))
        out.append({"query": q, "impressions": impr, "clicks": sum(p["clicks"] for p in pages), "pages": pages})
    return out


def analyse(rows: list[dict[str, Any]], index: dict[str, Any], min_impr: int = MIN_IMPRESSIONS) -> list[dict[str, Any]]:
    items = []
    for g in group(rows, min_impr):
        top = g["pages"][0]
        rank = page_of(top["url"], index)
        intent = classify_intent(g["query"], index)
        kind, target, reason = decide(intent, rank, index)
        items.append({
            "query": g["query"], "brand": is_brand(g["query"]), "impressions": int(g["impressions"]), "clicks": int(g["clicks"]),
            "intent": intent["intent"], "intentLabel": INTENT_LABEL[intent["intent"]],
            "ranking": {**_target(rank), "clicks": int(top["clicks"]), "impressions": int(top["impressions"]),
                        "position": top["position"]},
            "pages": [{**_target(page_of(p["url"], index)), "clicks": int(p["clicks"]), "impressions": int(p["impressions"]),
                       "position": p["position"]} for p in g["pages"]],
            "kind": kind, "target": _target(target) if target else None, "reason": reason,
        })
    items.sort(key=lambda i: (-i["impressions"], -i["clicks"], i["query"]))
    return items


def totals(items: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out = {k: {"all": 0, "brand": 0, "nonBrand": 0, "impressions": 0} for k in KINDS}
    for i in items:
        t = out[i["kind"]]
        t["all"] += 1
        t["brand" if i["brand"] else "nonBrand"] += 1
        if not i["brand"]:
            t["impressions"] += i["impressions"]
    return out


def csv_rows(items: list[dict[str, Any]], decisions: dict[str, dict[str, Any]]) -> list[list[Any]]:
    out = []
    for i in items:
        d = decisions.get(query_id(i["query"]))
        if i["kind"] == "eslesme" and not d:
            continue
        out.append([i["query"], KINDS[i["kind"]], i["intentLabel"], i["ranking"]["url"] or "",
                    (i["target"] or {}).get("url") or "", i["reason"], i["impressions"], i["clicks"],
                    {"onaylandi": "Onaylandı", "reddedildi": "Reddedildi"}.get((d or {}).get("status"), ""),
                    (d or {}).get("target") or "", (d or {}).get("decidedBy") or "", (d or {}).get("decidedAt") or "",
                    (d or {}).get("note") or ""])
    return out


# ------------------------------------------------------------------ veri
_ready: set[int] = set()
_ready_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) not in _ready:
            DECISIONS.create(engine, checkfirst=True)
            _ready.add(id(engine))


def _site(seo) -> str:
    return (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")


def load_index(seo) -> dict[str, Any]:
    tenant, site = seo.tenant(), _site(seo)
    with seo.engine().connect() as c:
        prows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.active, PRODUCTS.c.data_json)
                          .where(PRODUCTS.c.tenant_id == tenant)).all()
        lrows = c.execute(sa.select(LINKS.c.link, LINKS.c.type, LINKS.c.table_id, LINKS.c.title)
                          .where(LINKS.c.tenant_id == tenant)).all()
    products = []
    for pid, name, active, dj in prows:
        p = loads(dj, {})
        link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl") or ""
        url = str(link) if str(link).startswith("http") else (f"{site}/{str(link).strip('/')}" if link else None)
        products.append({"id": pid, "name": name or rules.text_of(p.get("ProductName")), "url": url,
                         "author": rules.text_of(p.get("Model")) or None, "authorId": str(p.get("ModelId") or "") or None,
                         "sales": _num(p.get("CountTotalSales")), "active": bool(active)})
    link_pages = [{"type": t, "id": str(tid or ""), "url": f"{site}/{str(l).strip('/')}",
                   "name": rules.text_of(title).split("|")[0].strip() or str(l).strip("/").replace("-", " ").title()}
                  for l, t, tid, title in lrows if l and t != "product"]
    return build_index(products, link_pages)


def compute(seo) -> dict[str, Any]:
    """Hesabın kendisi (hazır kayda yazılır): Search Console sorgu+sayfa kırılımı × site sözlüğü."""
    src = source(seo)
    items = analyse(src["rows"], load_index(seo)) if src["from"] == "query_page" else []
    return {"source": {k: v for k, v in src.items() if k != "rows"} | {"rowCount": len(src["rows"])}, "items": items}


def stamp(seo) -> str:
    """Girdiler: fırsat kırılımı (yoksa yalnız-sorgu önbelleği), ürünler, site sayfaları; site adresi."""
    ensure_opps(seo.engine())
    return hazir.damga(seo, [(OPPS, OPPS.c.saved_at, OPPS.c.kind == "query_page"),
                             (GSC, GSC.c.saved_at, GSC.c.kind == "queries"),
                             (PRODUCTS, PRODUCTS.c.synced_at), (LINKS, LINKS.c.synced_at)], ek=(_site(seo),))


def computed(seo) -> dict[str, Any]:
    return hazir.al(seo, "keymap", stamp(seo), lambda: compute(seo))


def decisions(seo) -> dict[str, dict[str, Any]]:
    eng = seo.engine()
    ensure(eng)
    with eng.connect() as c:
        rows = c.execute(sa.select(DECISIONS).where(DECISIONS.c.tenant_id == seo.tenant())).mappings().all()
    return {r["query_id"]: {"status": r["status"], "target": r["target"], "suggested": r["suggested"], "kind": r["kind"],
                            "note": r["note"], "decidedBy": r["decided_by"], "decidedAt": iso(r["decided_at"])} for r in rows}


# ------------------------------------------------------------------ uçlar
def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


def _filter(items: list[dict[str, Any]], brand: str, q: str) -> list[dict[str, Any]]:
    rows = items
    if brand in ("0", "1"):
        rows = [i for i in rows if i["brand"] == (brand == "1")]
    f = fold(q).strip()
    if f:
        rows = [i for i in rows if f in fold(f"{i['query']} {i['ranking']['url'] or ''} {(i['target'] or {}).get('url') or ''}")]
    return rows


def register(app, ctx) -> None:
    seo = ctx.seo
    hazir.kaydet(seo, "keymap", lambda: computed(seo))

    @app.get("/api/v1/seo-geo/keymap")
    def seo_keymap(request: Request, kind: str = "yanlis", brand: str = "0", q: str = "", start: int = 0,
                   limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if kind not in (*KINDS, "hepsi"):
            raise _err(422, "Bilinmeyen durum süzgeci.")
        connected = bool(connections.service_account_email())
        data = computed(seo)
        src = data["source"]
        ready = src["from"] == "query_page"
        reason = None
        if not ready and not connected:
            reason = ("Search Console bağlı değil. Bağlantı Yönetim → SEO & GEO ekranından kurulur; sonra her gece son 28 "
                      "günün arama–sayfa kırılımı okunur.")
        elif not ready:
            reason = ("Hangi aramada hangi sayfanın göründüğü henüz okunmadı. Fırsatlar ekranında «Search Console’dan yeniden "
                      "oku»ya basın ya da gece okumasını bekleyin.")
        dec = decisions(seo)
        base = _filter(data["items"], brand, q)
        rows = [i for i in base if kind == "hepsi" or i["kind"] == kind]
        start = max(0, start)
        page = rows[start:start + max(1, limit)]
        return {"kind": kind, "brand": brand, "start": start, "total": len(rows), "ready": ready, "connected": connected,
                "reason": reason, "source": src, "totals": totals(_filter(data["items"], "", q)),
                "counts": {k: sum(1 for i in base if i["kind"] == k) for k in KINDS},
                "kinds": [{"id": k, "label": v} for k, v in KINDS.items()],
                "decided": {"onaylandi": sum(1 for d in dec.values() if d["status"] == "onaylandi"),
                            "reddedildi": sum(1 for d in dec.values() if d["status"] == "reddedildi")},
                "thresholds": {"minImpressions": MIN_IMPRESSIONS},
                "items": [{**i, "decision": dec.get(query_id(i["query"]))} for i in page]}

    @app.post("/api/v1/seo-geo/keymap/decide")
    def seo_keymap_decide(body: KeymapDecision, request: Request) -> dict[str, Any]:
        """Karar yalnız kaydedilir; T-soft'a yazılmaz."""
        user = ctx.approver(request)
        data = computed(seo)
        qid = query_id(body.query)
        item = next((i for i in data["items"] if query_id(i["query"]) == qid), None)
        if not item:
            raise _err(404, "Bu arama eşleme listesinde yok.")
        target = body.target.strip()
        if body.action == "approve" and not target:
            raise _err(422, "Onay için hedef adres gerekli.")
        if target and "://" not in target:
            target = f"{_site(seo)}/{target.lstrip('/')}"
        vals = dict(query=item["query"][:500], status="onaylandi" if body.action == "approve" else "reddedildi",
                    target=target[:800] or None, suggested=((item["target"] or {}).get("url") or None),
                    kind=item["kind"], note=body.note or None, decided_by=user, decided_at=now())
        eng, tenant = seo.engine(), seo.tenant()
        ensure(eng)
        with eng.begin() as c:
            n = c.execute(DECISIONS.update().where(DECISIONS.c.tenant_id == tenant, DECISIONS.c.query_id == qid)
                          .values(**vals)).rowcount
            if not n:
                c.execute(DECISIONS.insert().values(tenant_id=tenant, query_id=qid, **vals))
        seo.audit(user, body.action, f"keymap:{qid[:12]}", item["query"][:200],
                  {"kind": "keymap", "target": target, "suggested": vals["suggested"], "note": body.note})
        return {**item, "decision": decisions(seo).get(qid)}

    @app.get("/api/v1/seo-geo/keymap/export.csv")
    def seo_keymap_export(request: Request, brand: str = ""):
        """Yanlış sayfa ve boşluk satırları ile karar verilen bütün aramalar."""
        ctx.gate(request)
        from fastapi.responses import Response

        data = computed(seo)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Arama", "Durum", "Arama türü", "Sıralanan sayfa", "Önerilen hedef", "Gerekçe", "Gösterim", "Tıklama",
                    "Karar", "Onaylanan hedef", "Karar veren", "Tarih", "Not"])
        for row in csv_rows(_filter(data["items"], brand, ""), decisions(seo)):
            w.writerow(row)
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="sorgu-sayfa-eslemesi.csv"'})
