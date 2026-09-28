"""Benzer kitaplar: kitap sayfasından verilecek site içi bağlantı önerileri («ilgili ürünler»).

Kaynak (CRM .28, yalnız SELECT; 2026-09-28 canlı ölçüm):
- `new_new_kitap_new_emsalkitap3Base` (new_kitapidOne → new_kitapidTwo): editörün girdiği «emsal kitap» bağı; 19.441
  bağ, 6.367 kaynak kitap, 12.583'ünde iki kitap da satışta. Bağın yönü saklanır; iki yönde de öneri olur (yön ekranda).
- `new_new_kitap_new_kitapBase`: set ↔ set parçası ve ambalaj kalemleri ("Boş Koli", "Değerlendirme Testi"). Okur
  önerisi DEĞİLDİR; yalnız birbirine set bağıyla bağlı kitapları öneriden çıkarmak için okunur.
- `new_new_kitap_new_temaBase` → `new_temaBase.new_name` (tema) ve `new_new_kitap_new_yasBase` → `new_yasBase.new_name` (yaş).
Gece (ve ekrandaki düğmeyle) okunur, `semantic_seo_similar_src`'ye yazılır. CRM'e ve T-soft'a hiçbir şey yazılmaz.

Öneri (kitap başına en çok `SUGGESTIONS_PER_BOOK`, ekranda yazılır), sırayla:
1. CRM emsal bağı (iki yön), 2. ortak tema + örtüşen yaş, 3. aynı yazar (T-soft `Model`), 4. aynı dizi (addan tahmin).
Her basamağın içinde hedefin satışına göre. Dışarıda kalan: kitabın kendisi, aynı kitabın başka baskısı (aynı barkod ya
da aynı sayılan ad), set bağıyla bağlı kitaplar, satışta olmayan, CRM'de kitap olmayan ya da yayın durumu uyarılı ürün.

Sayfada zaten var mı: site içi bağlantı grafiğinden (links.py `semantic_seo_links_edges`). Kaynak kitap sayfası taranmadıysa
"bilinmiyor". Hedefin gelen bağlantısı `links.WEAK_INLINKS`ten azsa zayıf, hiç yoksa yetim: bunlar öncelikli.

Karar (onay listesi düzenlenebilir / ret) kitap başına saklanır; onaylananlar CSV olarak T-soft «ilgili ürünler»e elle
girilmek üzere indirilir.
"""
from __future__ import annotations

import collections
import csv
import io
import logging
import os
import re
import threading
import time
from typing import Any, Iterable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from . import crm, rules
from .cannibal import same_title
from .competitors import clean_title
from .links import EDGES, WEAK_INLINKS, url_key
from .opportunities import fold
from .pages import _num
from .store import CRM_BOOKS, PRODUCTS, _md, dumps, iso, loads, now
from .tech import _product_url

log = logging.getLogger("semantic.seo_geo.similar")

#: Kitap başına en çok bu kadar öneri (ekranda yazılır; T-soft «ilgili ürünler» alanı kısa bir liste bekler).
SUGGESTIONS_PER_BOOK = 8
TIERS = ("emsal", "tema", "yazar", "dizi")
TIER_LABEL = {"emsal": "CRM emsal kitap", "tema": "Ortak tema ve yaş", "yazar": "Aynı yazar", "dizi": "Aynı dizi (addan)"}
VIEWS = {"eklenecek": "Eklenecek bağlantılar", "yetimler": "Yetim ve zayıf kitaplara", "hepsi": "Bütün kitaplar"}
SERIES_MIN_CHARS = 5       # dizi adı tahmini en az bu kadar harf (kısa ad "Aşk 2" gibi yanlış dizi kurar)
SERIES_DROP = frozenset({"kitap", "cilt", "sayi", "bolum", "kisim", "seri", "serisi"})

SRC = sa.Table(
    "semantic_seo_similar_src", _md,  # CRM'den okunan bağlar: emsal/set (kitap↔kitap), tema/yas (kitap→ad)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kind", sa.String(8), primary_key=True),     # emsal | set | tema | yas
    sa.Column("a", sa.String(40), primary_key=True),        # kitap kimliği (new_kitapId, büyük harf)
    sa.Column("b", sa.String(200), primary_key=True),       # kitap kimliği ya da tema/yaş adı
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
)
DECISIONS = sa.Table(
    "semantic_seo_similar_decisions", _md,  # kitap başına karar; onaylanan liste karar anındaki hâliyle saklanır
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("product_id", sa.String(40), primary_key=True),
    sa.Column("status", sa.String(16), nullable=False),      # onaylandi | reddedildi
    sa.Column("source_json", sa.Text, nullable=False),       # {id, code, name, url}: kitap satıştan kalksa da CSV doğru kalsın
    sa.Column("targets_json", sa.Text, nullable=False),      # [{id, code, name, url, reason, linked}]
    sa.Column("suggested_json", sa.Text, nullable=False),    # karar anındaki öneriler
    sa.Column("note", sa.String(1000)),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
)


class SimilarDecision(BaseModel):
    """Modül düzeyinde olmalı (bkz. tests/test_seo_feature_routes.py)."""
    action: str = Field(pattern="^(approve|reject)$")
    targets: list[str] = Field(default_factory=list)      # onaylanan hedef ürün kimlikleri, sıralı
    note: str = Field(default="", max_length=1000)


# ------------------------------------------------------------------ CRM okuması
def crm_queries(p: str) -> dict[str, str]:
    return {
        "emsal": f"SELECT e.new_kitapidOne AS a, e.new_kitapidTwo AS b FROM {p}new_new_kitap_new_emsalkitap3Base e",
        "set": f"SELECT s.new_kitapidOne AS a, s.new_kitapidTwo AS b FROM {p}new_new_kitap_new_kitapBase s",
        "tema": (f"SELECT kt.new_kitapid AS a, t.new_name AS b FROM {p}new_new_kitap_new_temaBase kt"
                 f" JOIN {p}new_temaBase t ON t.new_temaId = kt.new_temaid WHERE t.statecode = 0"),
        "yas": (f"SELECT ky.new_kitapid AS a, y.new_name AS b FROM {p}new_new_kitap_new_yasBase ky"
                f" JOIN {p}new_yasBase y ON y.new_yasId = ky.new_yasid WHERE y.statecode = 0"),
    }


def _id(v: Any) -> str:
    return str(v or "").strip().strip("{}").upper()


def read_crm(schema: str, execute) -> tuple[dict[str, list[tuple[str, str]]], dict[str, str]]:
    """(tür → [(a, b)], tür → hata). Emsal okunamazsa hata fırlar; tema/yaş/set okunamazsa o tür atlanır (eskisi kalır)."""
    out: dict[str, list[tuple[str, str]]] = {}
    errors: dict[str, str] = {}
    for kind, sql in crm_queries(crm._prefix(schema)).items():
        try:
            _, rows, truncated = execute(sql, crm.LIMIT)
            if truncated:
                raise RuntimeError("CRM sonucu kesildi; eksik veriyle yazılmaz.")
            pairs = set()
            for r in rows:
                a = _id(r.get("a"))
                b = _id(r.get("b")) if kind in ("emsal", "set") else re.sub(r"\s+", " ", str(r.get("b") or "")).strip()[:200]
                if a and b and a != b:
                    pairs.add((a, b))
            out[kind] = sorted(pairs)
        except Exception as e:  # noqa: BLE001
            if kind == "emsal":
                raise
            errors[kind] = str(e)[:300]
    return out, errors


# ------------------------------------------------------------------ saf yardımcılar (sınanır)
def series_key(name: Any) -> Optional[str]:
    """Addan dizi tahmini: "Kayıp Kıta 2 - Karanlık Orman" → "kayip kita". Numarasız ad için None."""
    t = re.sub(r"[^a-z0-9]+", " ", fold(clean_title(name or ""))).strip()
    m = re.match(r"^(.+?)\s+(\d{1,2})(?:\s|$)", t)
    if not m:
        m = re.match(r"^(.+?)\s+serisi(?:\s|$)", t)
    if not m:
        return None
    words = [w for w in m.group(1).split() if w not in SERIES_DROP]
    key = " ".join(words)
    return key if len(key.replace(" ", "")) >= SERIES_MIN_CHARS else None


def author_key(p: dict[str, Any]) -> Optional[str]:
    aid = str(p.get("authorId") or "").strip()
    if aid and aid != "0":
        return f"id:{aid}"
    a = fold(p.get("author") or "").strip()
    return f"ad:{a}" if a else None


def link_graph(edges: Optional[list[dict[str, Any]]]) -> Optional[dict[str, Any]]:
    """edges: [{page, src, dst, nofollow}] → {out: sayfa → hedef anahtarları, inl: hedef → izlenen gelen sayfa sayısı,
    crawled: bağlantısı okunmuş sayfalar}. Tablo yoksa None."""
    if edges is None:
        return None
    out: dict[str, set[str]] = collections.defaultdict(set)
    inl: dict[str, set[str]] = collections.defaultdict(set)
    crawled: set[str] = set()
    for e in edges:
        keys = {url_key(x) for x in (e.get("page"), e.get("src")) if x}
        d = url_key(e["dst"])
        crawled |= keys
        for k in keys:
            out[k].add(d)
        if not e.get("nofollow"):
            inl[d].add(url_key(e.get("src") or e.get("page")))
    return {"out": out, "inl": {k: len(v) for k, v in inl.items()}, "crawled": crawled}


def eligibility(p: dict[str, Any], book: Optional[dict[str, Any]]) -> Optional[str]:
    """None: öneriye girebilir. Değilse neden (sayım için): satista_degil | kitap_degil | durum | adres_yok."""
    if not p.get("active", True):
        return "satista_degil"
    if not p.get("url"):
        return "adres_yok"
    if book:
        kind = (book.get("kind") or "").strip().casefold()
        if book.get("rights") == "kitap_degil" or kind in crm.NON_BOOK_KINDS:
            return "kitap_degil"
        if book.get("statusFlag"):
            return "durum"
    return None


def build(products: list[dict[str, Any]], books: dict[str, dict[str, Any]], src: dict[str, list[tuple[str, str]]],
          edges: Optional[list[dict[str, Any]]], per_book: int = SUGGESTIONS_PER_BOOK) -> dict[str, Any]:
    """Bütün öneriler. Girdiler düz veri:

    products: T-soft ürünleri [{id, code, name, url, sales, author, authorId, ean, active}]
    books: EAN → CRM kitap kartı özeti {bookId, kind, rights, statusFlag}
    src: {"emsal": [(a, b)], "set": [(a, b)], "tema": [(kitap, ad)], "yas": [(kitap, ad)]} — kitap kimlikleri büyük harf
    edges: site içi bağlantılar [{page, src, dst, nofollow}] ya da None (tarama tablosu yok)
    """
    g = link_graph(edges)
    skipped: collections.Counter = collections.Counter()
    ok: list[dict[str, Any]] = []
    for p in products:
        b = books.get(p.get("ean") or "")
        why = eligibility(p, b)
        if why:
            skipped[why] += 1
            continue
        ok.append({**p, "book": _id(b["bookId"]) if b else None, "key": url_key(p["url"])})
    by_sales = lambda x: (-(x.get("sales") or 0), x.get("name") or "", x["id"])  # noqa: E731
    ok.sort(key=by_sales)
    by_book: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for p in ok:
        if p["book"]:
            by_book[p["book"]].append(p)

    fwd: dict[str, list[str]] = collections.defaultdict(list)
    back: dict[str, list[str]] = collections.defaultdict(list)
    for a, b in src.get("emsal") or []:
        fwd[a].append(b)
        back[b].append(a)
    set_pairs = {frozenset((a, b)) for a, b in src.get("set") or []}
    themes: dict[str, set[str]] = collections.defaultdict(set)
    ages: dict[str, set[str]] = collections.defaultdict(set)
    for a, n in src.get("tema") or []:
        themes[a].add(n)
    for a, n in src.get("yas") or []:
        ages[a].add(n)
    by_theme: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    by_author: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    by_series: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for p in ok:  # satışa göre sıralı eklenir; listeler de sıralı kalır
        for t in themes.get(p["book"] or "", ()):
            by_theme[t].append(p)
        ak = author_key(p)
        if ak:
            by_author[ak].append(p)
        sk = series_key(p.get("name"))
        if sk:
            by_series[sk].append(p)

    counts: collections.Counter = collections.Counter()
    rows: list[dict[str, Any]] = []
    for s in ok:
        chosen: list[dict[str, Any]] = []
        seen: set[str] = {s["id"]}
        excluded: list[dict[str, Any]] = []

        def excluded_why(t: dict[str, Any]) -> Optional[str]:
            if s.get("ean") and s.get("ean") == t.get("ean"):
                return "baski"
            if s["book"] and t["book"] and frozenset((s["book"], t["book"])) in set_pairs:
                return "set"
            if same_title(s.get("name"), t.get("name")):
                return "baski"
            return None

        def take(cands: Iterable[dict[str, Any]], tier: str, text, note_excluded: bool = False) -> None:
            for t in cands:
                if len(chosen) >= per_book:
                    return
                if t["id"] in seen:
                    continue
                seen.add(t["id"])
                why = excluded_why(t)
                if why:
                    counts[f"excluded_{why}"] += 1
                    if note_excluded:
                        excluded.append({"id": t["id"], "name": t.get("name"), "why": why})
                    continue
                chosen.append({"target": t, "tier": tier, "text": text(t)})

        # 1. emsal: iki yöndeki emsaller satışa göre (yön gerekçede yazılır)
        emsal_total = 0
        if s["book"]:
            out_b = sorted({x for b in fwd.get(s["book"], ()) for x in (p["id"] for p in by_book.get(b, ()))})
            in_b = sorted({x for b in back.get(s["book"], ()) for x in (p["id"] for p in by_book.get(b, ()))})
            idx = {p["id"]: p for b in list(fwd.get(s["book"], ())) + list(back.get(s["book"], ())) for p in by_book.get(b, ())}
            direction = {**{i: "geri" for i in in_b}, **{i: "ileri" for i in out_b}}
            emsal = sorted(idx.values(), key=by_sales)
            emsal_total = len(emsal)  # satıştaki emsallerin hepsi; ekranda "N emsalden M'si listede" diye yazılır
            take(emsal, "emsal", lambda t: ("CRM'de bu kitabın emsali" if direction.get(t["id"]) == "ileri"
                                            else "CRM'de bu kitabı emsal gösteriyor"), note_excluded=True)
            # 2. tema + yaş
            my_themes, my_ages = themes.get(s["book"], set()), ages.get(s["book"], set())
            if my_themes and len(chosen) < per_book:
                # Her temanın en çok satan uygun adayları (elemelere pay bırakarak) toplanır, sonra satışa göre birleşir;
                # sonuç, bütün tema üyeleri sıralansaydı çıkacak ilk `per_book` ile aynıdır.
                pool: dict[str, dict[str, Any]] = {}
                for th in sorted(my_themes):
                    got = 0
                    for t in by_theme.get(th, ()):
                        if got >= per_book * 4:
                            break
                        if t["id"] in seen:
                            continue
                        their = ages.get(t["book"] or "", set())
                        if (my_ages or their) and not (my_ages & their):
                            continue
                        pool[t["id"]] = t
                        got += 1

                def theme_text(t: dict[str, Any]) -> str:
                    common = sorted(my_themes & themes.get(t["book"] or "", set()))
                    age = sorted(my_ages & ages.get(t["book"] or "", set()))
                    return "Ortak tema: " + ", ".join(common) + (f" · yaş: {', '.join(age)}" if age else "")
                take(sorted(pool.values(), key=by_sales), "tema", theme_text)
        # 3. aynı yazar
        ak = author_key(s)
        if ak and len(chosen) < per_book:
            take(by_author.get(ak, ()), "yazar", lambda t: f"Aynı yazar: {t.get('author') or '—'}")
        # 4. aynı dizi (addan)
        sk = series_key(s.get("name"))
        if sk and len(chosen) < per_book:
            take(by_series.get(sk, ()), "dizi", lambda t: f"Adından aynı dizi: «{sk}»")

        sugg = []
        for c in chosen:
            t = c["target"]
            linked = None
            inl = None
            if g is not None:
                inl = g["inl"].get(t["key"], 0)
                if s["key"] in g["crawled"]:
                    linked = t["key"] in g["out"].get(s["key"], set())
            sugg.append({"id": t["id"], "code": t.get("code"), "name": t.get("name"), "url": t["url"],
                         "author": t.get("author"), "sales": t.get("sales") or 0, "reason": c["tier"],
                         "reasonText": c["text"], "linked": linked, "inlinks": inl,
                         "orphan": inl == 0, "weak": inl is not None and 0 < inl < WEAK_INLINKS})
            counts[f"tier_{c['tier']}"] += 1
        if not sugg:
            continue
        add = [x for x in sugg if x["linked"] is not True]
        rows.append({"id": s["id"], "code": s.get("code"), "name": s.get("name"), "url": s["url"], "author": s.get("author"),
                     "sales": s.get("sales") or 0, "crawled": (s["key"] in g["crawled"]) if g is not None else None,
                     "suggestions": sugg, "excluded": excluded, "emsalTotal": emsal_total,
                     "toAdd": sum(1 for x in sugg if x["linked"] is False), "unknown": sum(1 for x in sugg if x["linked"] is None),
                     "alreadyLinked": sum(1 for x in sugg if x["linked"] is True),
                     "orphanTargets": sum(1 for x in add if x["orphan"]), "weakTargets": sum(1 for x in add if x["weak"])})
    emsal_pairs = src.get("emsal") or []
    on_sale = {p["book"] for p in ok if p["book"]}
    summary = {
        "perBook": per_book, "eligible": len(ok), "withSuggestions": len(rows), "skipped": dict(skipped),
        "emsalLinks": len(emsal_pairs), "emsalOnSale": sum(1 for a, b in emsal_pairs if a in on_sale and b in on_sale),
        "setLinks": len(src.get("set") or []), "themes": len(by_theme), "tiers": {t: counts[f"tier_{t}"] for t in TIERS},
        "excluded": {"baski": counts["excluded_baski"], "set": counts["excluded_set"]},
        "graphKnown": g is not None, "crawledSources": sum(1 for r in rows if r["crawled"]),
        "toAdd": sum(r["toAdd"] for r in rows), "alreadyLinked": sum(r["alreadyLinked"] for r in rows),
        "orphanTargets": len({x["id"] for r in rows for x in r["suggestions"] if x["orphan"] and x["linked"] is not True}),
        "weakInlinks": WEAK_INLINKS,
    }
    return {"summary": summary, "rows": rows}


def view_rows(rows: list[dict[str, Any]], view: str, decided: set[str], q: str = "") -> list[dict[str, Any]]:
    f = fold(q).strip()
    out = [r for r in rows if not f or f in fold(f"{r.get('name') or ''} {r.get('code') or ''} {r.get('author') or ''}")]
    if view == "eklenecek":
        out = [r for r in out if r["id"] not in decided and (r["toAdd"] or r["unknown"])]
        return sorted(out, key=lambda r: (not (r["orphanTargets"] or r["weakTargets"]), -r["sales"], r.get("name") or ""))
    if view == "yetimler":
        out = [r for r in out if r["orphanTargets"] or r["weakTargets"]]
        return sorted(out, key=lambda r: (-r["orphanTargets"], -r["weakTargets"], -r["sales"], r.get("name") or ""))
    return sorted(out, key=lambda r: (-r["sales"], r.get("name") or ""))


def csv_rows(decisions: list[dict[str, Any]]) -> list[list[Any]]:
    """Onaylanan kararlar → her (kaynak, hedef) için bir satır."""
    out = []
    for d in decisions:
        src = d["source"]
        for t in d["targets"]:
            out.append([src.get("code") or src["id"], src.get("name") or "", src.get("url") or "", t.get("code") or t["id"],
                        t.get("name") or "", t.get("url") or "", t.get("reasonText") or TIER_LABEL.get(t.get("reason") or "", ""),
                        {True: "zaten bağlı", False: "eklenmeli"}.get(t.get("linked"), "bilinmiyor"),
                        d.get("decidedBy") or "", d.get("decidedAt") or ""])
    return out


# ------------------------------------------------------------------ çalışan kısım
def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


_ready: set[int] = set()
_ready_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        for t in (SRC, DECISIONS):
            t.create(engine, checkfirst=True)
        _ready.add(id(engine))


class Similar:
    def __init__(self, seo: Any) -> None:
        self.seo = seo
        self._lock = threading.Lock()
        self._read_lock = threading.Lock()
        self._cache: Optional[dict[str, Any]] = None
        self.state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "error": None,
                                      "counts": None, "partial": None}

    def engine(self) -> sa.engine.Engine:
        eng = self.seo.engine()
        ensure(eng)
        return eng

    def site(self) -> str:
        return (self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")

    @staticmethod
    def crm_ready() -> bool:
        from semantic_bridge import admin as admin_mod

        return bool(admin_mod.conf("CRM_SCHEMA")) and bool(crm.CONNECTION_FILE) and os.path.exists(crm.CONNECTION_FILE)

    # -------------------------------------------------------------- CRM okuması (arka planda)
    def start_read(self) -> bool:
        if not self._read_lock.acquire(blocking=False):
            return False
        self.state.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)
        threading.Thread(target=self._read, name="seo-similar-crm", daemon=True).start()
        return True

    def _read(self) -> None:
        from semantic_bridge import admin as admin_mod

        try:
            con = crm.connector()  # kendi bağlantısı; sohbetin bağlantısıyla paylaşılmaz
            try:
                data, errors = read_crm(admin_mod.conf("CRM_SCHEMA"), con.execute)
            finally:
                try:
                    con.close()
                except Exception:  # noqa: BLE001
                    pass
            tenant, at = self.seo.tenant(), now()
            with self.engine().begin() as c:
                for kind, pairs in data.items():
                    c.execute(SRC.delete().where(SRC.c.tenant_id == tenant, SRC.c.kind == kind))
                    vals = [dict(tenant_id=tenant, kind=kind, a=a[:40], b=b[:200], synced_at=at) for a, b in pairs]
                    for i in range(0, len(vals), 2000):
                        c.execute(SRC.insert(), vals[i:i + 2000])
            self.state.update(counts={k: len(v) for k, v in data.items()}, partial=errors or None)
            self._cache = None
        except Exception as e:  # noqa: BLE001
            self.state["error"] = str(e)[:500]
            log.warning("benzer kitaplar CRM okuması başarısız: %s", e)
        finally:
            self.state.update(running=False, finishedAt=iso(now()))
            self._read_lock.release()

    # -------------------------------------------------------------- hesap
    def _edges_exist(self, eng: sa.engine.Engine) -> bool:
        try:
            return sa.inspect(eng).has_table(EDGES.name)
        except Exception:  # noqa: BLE001
            return False

    def _fingerprint(self, c: Any, tenant: str, edges: bool) -> tuple:
        parts = []
        for t, col in ((SRC, SRC.c.synced_at), (PRODUCTS, PRODUCTS.c.synced_at), (CRM_BOOKS, CRM_BOOKS.c.synced_at)):
            parts += list(c.execute(sa.select(sa.func.count(), sa.func.max(col)).where(t.c.tenant_id == tenant)).first())
        if edges:
            parts += list(c.execute(sa.select(sa.func.count(), sa.func.max(EDGES.c.seen_at))
                                    .where(EDGES.c.tenant_id == tenant)).first())
        return tuple(iso(x) if hasattr(x, "tzinfo") else x for x in parts)

    def load(self, c: Any, tenant: str, edges_exist: bool) -> dict[str, Any]:
        site = self.site()
        prows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.code, PRODUCTS.c.name, PRODUCTS.c.active,
                                    PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == tenant)).all()
        products = []
        for pid, code, name, active, dj in prows:
            p = loads(dj, {})
            products.append({"id": pid, "code": code, "name": name or rules.text_of(p.get("ProductName")),
                             "url": _product_url(p, site), "sales": _num(p.get("CountTotalSales")),
                             "author": rules.text_of(p.get("Model")) or None, "authorId": str(p.get("ModelId") or "") or None,
                             "ean": crm.ean_key(p.get("Barcode")) or None,
                             "active": bool(active) and str(p.get("IsActive", "1")).lower() not in ("0", "false")})
        books = {}
        for ean, bid, flag, rights, dj in c.execute(sa.select(CRM_BOOKS.c.ean, CRM_BOOKS.c.book_id, CRM_BOOKS.c.status_flag,
                                                              CRM_BOOKS.c.rights, CRM_BOOKS.c.data_json)
                                                    .where(CRM_BOOKS.c.tenant_id == tenant)):
            books[ean] = {"bookId": bid, "statusFlag": flag, "rights": rights, "kind": loads(dj, {}).get("kind")}
        src: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
        for kind, a, b in c.execute(sa.select(SRC.c.kind, SRC.c.a, SRC.c.b).where(SRC.c.tenant_id == tenant)):
            src[kind].append((a, b))
        edges = None
        if edges_exist:
            edges = [{"page": p, "src": s, "dst": d, "nofollow": bool(nf)} for p, s, d, nf in c.execute(
                sa.select(EDGES.c.page_url, EDGES.c.src_url, EDGES.c.dst_url, EDGES.c.nofollow).where(EDGES.c.tenant_id == tenant))]
        last = c.execute(sa.select(sa.func.max(SRC.c.synced_at)).where(SRC.c.tenant_id == tenant)).scalar()
        return {"products": products, "books": books, "src": dict(src), "edges": edges, "lastRead": iso(last),
                "crmBooks": len(books)}

    def result(self) -> dict[str, Any]:
        tenant = self.seo.tenant()
        eng = self.engine()
        with self._lock:
            has_edges = self._edges_exist(eng)
            with eng.connect() as c:
                fp = self._fingerprint(c, tenant, has_edges)
                cached = self._cache
                if cached and cached["tenant"] == tenant and cached["fp"] == fp:
                    return cached["data"]
                t0 = time.monotonic()
                src = self.load(c, tenant, has_edges)
            data = build(src["products"], src["books"], src["src"], src["edges"])
            data["summary"].update(lastRead=src["lastRead"], crmBooks=src["crmBooks"], computedAt=iso(now()),
                                   seconds=round(time.monotonic() - t0, 1), sourceKinds={k: len(v) for k, v in src["src"].items()})
            data["byId"] = {r["id"]: r for r in data["rows"]}
            self._cache = {"tenant": tenant, "fp": fp, "data": data}
            return data

    def decisions(self, ids: Optional[list[str]] = None) -> dict[str, dict[str, Any]]:
        cond = [DECISIONS.c.tenant_id == self.seo.tenant()]
        if ids is not None:
            if not ids:
                return {}
            cond.append(DECISIONS.c.product_id.in_(ids))
        with self.engine().connect() as c:
            rows = c.execute(sa.select(DECISIONS).where(*cond)).mappings().all()
        return {r["product_id"]: _decision_view(r) for r in rows}


def _decision_view(r: Any) -> dict[str, Any]:
    return {"status": r["status"], "source": loads(r["source_json"], {}), "targets": loads(r["targets_json"], []), "suggested": loads(r["suggested_json"], []),
            "note": r["note"], "decidedBy": r["decided_by"], "decidedAt": iso(r["decided_at"])}


def _row_view(r: dict[str, Any], decision: Optional[dict[str, Any]]) -> dict[str, Any]:
    d = None
    if decision:
        d = {k: v for k, v in decision.items() if k != "suggested"}
        # Öneri listesi kararın ardından değiştiyse ekranda "yeniden bakılmalı" denir.
        d["changed"] = [x.get("id") for x in decision.get("suggested") or []] != [x["id"] for x in r["suggestions"]]
    return {**r, "decision": d}


def register(app, ctx) -> None:
    sim = Similar(ctx.seo)
    ctx.seo.similar = sim

    def nightly() -> None:
        """CRM bağlıysa bağları arka planda yeniden okur; gece işini bekletmez."""
        if sim.crm_ready():
            sim.start_read()

    ctx.seo.nightly.append(("similar", nightly))

    @app.get("/api/v1/seo-geo/similar")
    def seo_similar(request: Request, view: str = "eklenecek", q: str = "", start: int = 0, limit: int = 30) -> dict[str, Any]:
        ctx.gate(request)
        if view not in VIEWS:
            raise _err(422, "Bilinmeyen görünüm.")
        data = sim.result()
        decided = sim.decisions()
        rows = view_rows(data["rows"], view, set(decided), q)
        start = max(0, start)
        page = rows[start:start + max(1, limit)]
        s = data["summary"]
        ready = bool(s.get("emsalLinks")) or bool(s.get("withSuggestions"))
        reason = None
        if not s.get("emsalLinks"):
            reason = ("CRM'deki emsal kitap bağları henüz okunmadı. «CRM'den yeniden oku» düğmesine basın ya da gece "
                      "okumasını bekleyin." if sim.crm_ready() else
                      "CRM bağlantısı tanımlı değil; emsal kitap bağları okunamıyor. Öneriler yalnız yazar ve dizi adından.")
        counts = {v: len(view_rows(data["rows"], v, set(decided))) for v in VIEWS}
        return {"view": view, "views": VIEWS, "start": start, "total": len(rows), "counts": counts, "summary": s,
                "ready": ready, "reason": reason, "state": sim.state, "crmReady": sim.crm_ready(),
                "tiers": [{"id": t, "label": TIER_LABEL[t]} for t in TIERS],
                "decisions": {"onaylandi": sum(1 for d in decided.values() if d["status"] == "onaylandi"),
                              "reddedildi": sum(1 for d in decided.values() if d["status"] == "reddedildi")},
                "items": [_row_view(r, decided.get(r["id"])) for r in page]}

    @app.get("/api/v1/seo-geo/similar/export.csv")
    def seo_similar_export(request: Request):
        """Onaylanan listeler: T-soft «ilgili ürünler» alanına elle girilmek üzere; her (kaynak, hedef) bir satır."""
        ctx.gate(request)
        from fastapi.responses import Response

        decided = sim.decisions()
        items = []
        for pid, d in sorted(decided.items(), key=lambda kv: kv[1]["decidedAt"] or ""):
            if d["status"] != "onaylandi":
                continue
            items.append({"source": d["source"] or {"id": pid}, "targets": d["targets"], "decidedBy": d["decidedBy"],
                          "decidedAt": d["decidedAt"]})
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Kaynak ürün kodu", "Kaynak ürün", "Kaynak adres", "İlgili ürün kodu", "İlgili ürün", "İlgili adres",
                    "Gerekçe", "Sayfada", "Onaylayan", "Tarih"])
        for row in csv_rows(items):
            w.writerow(row)
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="benzer-kitaplar.csv"'})

    @app.post("/api/v1/seo-geo/similar/refresh")
    def seo_similar_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        if not sim.crm_ready():
            raise _err(409, "CRM bağlantısı tanımlı değil.")
        started = sim.start_read()
        if started:
            ctx.seo.audit(user, "run", "similar", "Benzer kitaplar: CRM okuması", {"kind": "similar"})
        return {"started": started, "state": sim.state}

    @app.get("/api/v1/seo-geo/similar/{pid}")
    def seo_similar_one(pid: str, request: Request) -> dict[str, Any]:
        ctx.gate(request)
        data = sim.result()
        r = data["byId"].get(pid)
        d = sim.decisions([pid]).get(pid)
        if not r and not d:
            raise _err(404, "Bu kitap için öneri yok (satışta değil, CRM'de uyarılı ya da benzer kitap bulunamadı).")
        if not r:
            return {"id": pid, "suggestions": [], "excluded": [], "decision": d, "perBook": SUGGESTIONS_PER_BOOK}
        return {**_row_view(r, d), "perBook": SUGGESTIONS_PER_BOOK}

    @app.post("/api/v1/seo-geo/similar/{pid}/decide")
    def seo_similar_decide(pid: str, body: SimilarDecision, request: Request) -> dict[str, Any]:
        """Karar yalnız kaydedilir; T-soft'a yazılmaz. Onaylanan liste CSV ile dışa alınır."""
        user = ctx.approver(request)
        data = sim.result()
        r = data["byId"].get(pid)
        if not r:
            raise _err(404, "Bu kitap için öneri yok.")
        sugg = {x["id"]: x for x in r["suggestions"]}
        targets: list[dict[str, Any]] = []
        if body.action == "approve":
            ids = list(dict.fromkeys(t.strip() for t in body.targets if t.strip()))
            if not ids:
                raise _err(422, "Onay için en az bir kitap seçilmeli.")
            if pid in ids:
                raise _err(422, "Kitap kendisine bağlantı veremez.")
            extra = [i for i in ids if i not in sugg]
            known: dict[str, dict[str, Any]] = {}
            if extra:  # öneride olmayan, elle eklenen kitap: satıştaki ürün olmalı
                site = sim.site()
                with sim.engine().connect() as c:
                    for epid, code, name, dj in c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.code, PRODUCTS.c.name,
                                                                    PRODUCTS.c.data_json).where(
                            PRODUCTS.c.tenant_id == ctx.seo.tenant(), PRODUCTS.c.active.is_(True),
                            sa.or_(PRODUCTS.c.product_id.in_(extra), PRODUCTS.c.code.in_(extra)))):
                        p = loads(dj, {})
                        item = {"id": epid, "code": code, "name": name, "url": _product_url(p, site), "reason": "elle",
                                "reasonText": "Onaylayan elle ekledi", "linked": None}
                        known[epid] = item
                        if code:
                            known[code] = item
                missing = [i for i in extra if i not in known]
                if missing:
                    raise _err(422, "Satışta bulunamayan ürün: " + ", ".join(missing))
            for i in ids:
                x = sugg.get(i) or known[i]
                targets.append({k: x.get(k) for k in ("id", "code", "name", "url", "reason", "reasonText", "linked")})
        source = {"id": r["id"], "code": r.get("code"), "name": r.get("name"), "url": r.get("url")}
        vals = dict(status="onaylandi" if body.action == "approve" else "reddedildi", source_json=dumps(source),
                    targets_json=dumps(targets), suggested_json=dumps([{"id": x["id"]} for x in r["suggestions"]]),
                    note=body.note or None, decided_by=user, decided_at=now())
        tenant = ctx.seo.tenant()
        with sim.engine().begin() as c:
            n = c.execute(DECISIONS.update().where(DECISIONS.c.tenant_id == tenant, DECISIONS.c.product_id == pid)
                          .values(**vals)).rowcount
            if not n:
                c.execute(DECISIONS.insert().values(tenant_id=tenant, product_id=pid, **vals))
        ctx.seo.audit(user, body.action, pid, r.get("name") or pid,
                      {"kind": "similar", "source": source, "targets": [t["id"] for t in targets], "note": body.note})
        d = sim.decisions([pid]).get(pid)
        return _row_view(r, d)
