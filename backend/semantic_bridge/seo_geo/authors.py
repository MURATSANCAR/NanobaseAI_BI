"""Yazar sayfası güven sinyalleri (deneyim–uzmanlık–yetki–güven): çok satan yazarlar için kontrol listesi ve puan.

Her yazar için bakılan (kaynak → sinyal):
- Yazar sayfası var mı: T-soft `link/getLinks` model sayfaları (`semantic_seo_links`), ürünün `ModelId` → `TableId`;
  bulunamazsa ad eşleşmesi.
- Sayfa açıklaması: sayfanın meta açıklaması var ve başlık/ad kopyası değil, uzunluğu eşik içinde.
- Tanıtım metni (biyografi): T-soft'ta yazar sayfasının tanıtım alanı okunamıyor; onaylanmış sayfa önerisinde tanıtım
  metni varsa "hazır", CRM'deki yazar kaydında özgeçmiş/biyografi varsa "kaynak var, yazılmalı".
- Wikidata / Wikipedia: kimlik denetiminin önbelleği (`semantic_seo_entity`, entity.py).
- Kitap sayfalarında yazar şemasına sameAs: şema taraması (`semantic_seo_schema`, `author_no_sameas`).
- Çevirmen/çizer künyesi: CRM kitap kartında çevirmen/çizer yazılıysa T-soft açıklamasında ya da künyesinde
  (Additional6) adı geçiyor mu.
- Ödül: CRM ödül kaydı (`new_odulBase` ↔ `new_contact_new_odulBase`). 2026-09-27 canlı CRM: 2 ödül kaydı, hiçbiri
  kişiye bağlı değil — bu sinyal şimdilik hep "CRM'de yok" çıkar; CRM'e girildikçe dolar.

CRM'den (gece, yalnız okuma) yalnız **uzunluk ve sayı** saklanır: yazar kaydının özgeçmiş/biyografi alanlarının
karakter sayısı ve bağlı ödül sayısı. Metnin kendisi, kişi adı ya da iletişim bilgisi saklanmaz.

Puan: bilinen maddelerin ağırlıklı oranı (bilinmeyen ya da bu yazara uymayan madde paydadan çıkar), 0–100.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

import sqlalchemy as sa
from fastapi import Request

from . import entity as entity_mod, rules
from .store import CRM_BOOKS, LINKS, PRODUCTS, PROPOSALS, SCHEMA, _md, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

#: CRM özgeçmişi bu kadar karakterden kısaysa biyografi kaynağı sayılmaz.
BIO_MIN = 200
#: Onaylı tanıtım metni bu kadar kelimeden kısaysa yetersiz.
INTRO_MIN_WORDS = 60
#: Madde → (ağırlık, başlık).
CHECKS: dict[str, tuple[int, str]] = {
    "page": (20, "Yazar sayfası var"),
    "page_meta": (10, "Sayfa açıklaması uygun"),
    "bio": (20, "Tanıtım metni (biyografi)"),
    "wikidata": (20, "Wikidata / Wikipedia kaydı"),
    "sameas": (15, "Kitap sayfalarında yazar kimlik bağlantısı"),
    "credits": (10, "Çevirmen / çizer künyede"),
    "awards": (5, "Ödüller kayıtlı"),
}
#: Wikidata durumunun ağırlıktan aldığı pay.
WIKIDATA_SHARE = {"wikipedia": 1.0, "wikidata": 0.75, "belirsiz": 0.25, "yok": 0.0}
AWARDS_ROW = "_odul"  # AUTHOR_CRM'de CRM geneli ödül sayıları: bio_len = ödül kaydı, awards = kişiye bağlı kayıt

AUTHOR_CRM = sa.Table(
    "semantic_seo_author_crm", _md,  # CRM yazar kaydının biyografi uzunluğu ve ödül sayısı (kitap EAN'ı başına)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("ean", sa.String(20), primary_key=True),
    sa.Column("contact_id", sa.String(40)),
    sa.Column("bio_len", sa.Integer, nullable=False),
    sa.Column("awards", sa.Integer, nullable=False),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
)
_ready: set[int] = set()
_ready_lock = threading.Lock()


def _ensure(eng: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(eng) in _ready:
            return
        AUTHOR_CRM.create(eng, checkfirst=True)
        _ready.add(id(eng))


def crm_sql(p: str) -> str:
    """Kitabın ana yazarı (`new_yazarid`) → özgeçmiş alanlarının uzunluğu (ntext için DATALENGTH/2) ve ödül bağı sayısı."""
    return (
        "SELECT k.new_ean13 AS ean, CAST(c.ContactId AS nvarchar(40)) AS contact_id,"
        " ISNULL(DATALENGTH(c.new_ozgecmis), 0) / 2 AS long_len, ISNULL(DATALENGTH(c.new_kisaozgecmis), 0) / 2 AS short_len,"
        " ISNULL(DATALENGTH(c.new_Biyografi), 0) / 2 AS bio_len,"
        f" (SELECT COUNT(*) FROM {p}new_contact_new_odulBase o WHERE o.contactid = c.ContactId) AS awards"
        f" FROM {p}new_kitapBase k JOIN {p}ContactBase c ON c.ContactId = k.new_yazarid"
        " WHERE k.statecode = 0 AND k.new_ean13 IS NOT NULL"
    )


def awards_sql(p: str) -> str:
    return (f"SELECT (SELECT COUNT(*) FROM {p}new_odulBase WHERE statecode = 0) AS records,"
            f" (SELECT COUNT(*) FROM {p}new_contact_new_odulBase) AS linked")


# ------------------------------------------------------------------ saf kısım
def credited(crm_names: Optional[str], page_text: str) -> Optional[bool]:
    """CRM'deki çevirmen/çizer adlarının hepsi sayfa metninde geçiyor mu; CRM'de ad yoksa None (madde uymaz)."""
    names = entity_mod.split_authors(crm_names) if crm_names else []
    if not names:
        return None
    text = entity_mod.fold(page_text)
    return all(entity_mod.fold(n) in text for n in names)


def checklist(f: dict[str, Any]) -> tuple[list[dict[str, Any]], Optional[int]]:
    """f: page (bool), pageMetaOk (bool|None), introReady (bool), crmBio (bool|None), wikidata (durum),
    sameas ((geçen, taranan)), credits ((geçen, uyan)), awards (int|None), pageLink (str|None).
    Döner: maddeler [{id, title, weight, state: ok|kismi|eksik|bilinmiyor|uymaz, earned, detail, action}], puan."""
    items: list[dict[str, Any]] = []

    def add(cid: str, state: str, share: float, detail: str, action: Optional[str]) -> None:
        w, title = CHECKS[cid]
        items.append({"id": cid, "title": title, "weight": w, "state": state,
                      "earned": round(w * share, 1) if state not in ("bilinmiyor", "uymaz") else 0,
                      "detail": detail, "action": action})

    if f.get("page"):
        add("page", "ok", 1, f"/{f.get('pageLink') or ''}", None)
    else:
        add("page", "eksik", 0, "Sitede bu yazar için sayfa bulunamadı.",
            "T-soft'ta yazar (model) sayfası açılmalı; kitaplar bu sayfaya bağlanmalı.")
    meta = f.get("pageMetaOk")
    if meta is None:
        add("page_meta", "bilinmiyor" if f.get("page") else "uymaz", 0, "Yazar sayfası yok.", None)
    else:
        add("page_meta", "ok" if meta else "eksik", 1 if meta else 0,
            "Açıklama uygun." if meta else "Meta açıklama boş, kısa/uzun ya da başlığın kopyası.",
            None if meta else "Sayfalar ekranından bu yazar için öneri alınıp onaylanmalı.")
    if f.get("introReady"):
        add("bio", "ok", 1, "Onaylanmış tanıtım metni hazır.", "Metin T-soft panelinde yazar sayfasına girilmeli (gönderim yok).")
    elif f.get("crmBio"):
        add("bio", "kismi", 0.5, "CRM'de yazarın özgeçmişi var; sayfada tanıtım metni yok.",
            "Sayfalar ekranında öneri alınmalı; ZEKİ AI CRM özgeçmişini kaynak alabilir.")
    else:
        add("bio", "eksik", 0, "Ne sayfada ne CRM'de yazarı anlatan metin var.",
            "Editör kısa bir özgeçmiş yazmalı (CRM yazar kaydına), sonra sayfaya öneri alınmalı.")
    wd = f.get("wikidata") or "bekliyor"
    if wd == "bekliyor":
        add("wikidata", "bilinmiyor", 0, "Henüz bakılmadı (Kimlik ekranı gece bakar).", None)
    else:
        share = WIKIDATA_SHARE.get(wd, 0)
        label = entity_mod.AUTHOR_LABEL.get(wd, wd)
        add("wikidata", "ok" if share == 1 else "kismi" if share else "eksik", share, label,
            " ".join(entity_mod.author_needs(wd)) or None)
    ok, checked = f.get("sameas") or (0, 0)
    if not checked:
        add("sameas", "bilinmiyor", 0, "Kitap sayfaları henüz şema taramasından geçmedi.", None)
    else:
        share = ok / checked
        add("sameas", "ok" if ok == checked else "kismi" if ok else "eksik", share,
            f"{checked} taranan kitap sayfasının {ok} tanesinde yazar kimlik bağlantısı (sameAs) var.",
            None if ok == checked else "Tema, yazar şemasına Wikidata/Wikipedia bağlantısını basmalı (Şema → tema isteği).")
    ok, total = f.get("credits") or (0, 0)
    if not total:
        add("credits", "uymaz", 0, "CRM'de çevirmen/çizer yazılı kitabı yok.", None)
    else:
        share = ok / total
        add("credits", "ok" if ok == total else "kismi" if ok else "eksik", share,
            f"Çevirmen/çizeri olan {total} kitabın {ok} tanesinde adı sayfada geçiyor.",
            None if ok == total else "Künye (Additional6) ya da açıklamada çevirmen/çizer adı yazılmalı.")
    aw = f.get("awards")
    if aw is None:
        add("awards", "bilinmiyor", 0, "CRM yazar bilgisi henüz okunmadı.", None)
    elif aw > 0:
        add("awards", "ok", 1, f"CRM'de {aw} ödül kaydı.", "Ödüller yazar sayfasındaki tanıtımda anılmalı.")
    else:
        add("awards", "eksik", 0, "CRM'de bu yazara bağlı ödül kaydı yok.",
            "Yazar ödül aldıysa CRM'e (Ödül kaydı → kişi) girilmeli; tanıtım metni ve Wikidata buna dayanır.")
    known = [i for i in items if i["state"] not in ("bilinmiyor", "uymaz")]
    possible = sum(i["weight"] for i in known)
    score = round(100 * sum(i["earned"] for i in known) / possible) if possible else None
    return items, score


def meta_ok(name: str, title: Any, desc: Any, lim: dict[str, int]) -> bool:
    d, t = rules.text_of(desc), rules.text_of(title)
    if not d or d.casefold() in (t.casefold(), rules.text_of(name).casefold()):
        return False
    return lim["meta_min"] <= len(d) <= lim["meta_max"]


# ------------------------------------------------------------------ servis
class Authors:
    def __init__(self, seo) -> None:
        self.seo = seo
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "error": None, "count": None}

    def engine(self) -> sa.engine.Engine:
        e = self.seo.engine()
        _ensure(e)
        return e

    def ent(self) -> entity_mod.Entity:
        return getattr(self.seo, "entity", None) or entity_mod.Entity(self.seo)

    # ---- CRM okuması (yalnız uzunluk ve sayı)
    def start(self) -> bool:
        from . import crm

        if not self.seo.conf("CRM_SCHEMA") or not crm.CONNECTION_FILE or not os.path.exists(crm.CONNECTION_FILE):
            self.state["error"] = "CRM bağlantısı tanımlı değil."
            return False
        if not self._lock.acquire(blocking=False):
            return False
        self.state.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)
        threading.Thread(target=self._run, name="seo-authors-crm", daemon=True).start()
        return True

    def _run(self) -> None:
        from semantic_bridge.editorial import _prefix

        from . import crm

        try:
            p = _prefix(self.seo.conf("CRM_SCHEMA"))
            con = crm.connector()
            try:
                _, rows, truncated = con.execute(crm_sql(p), crm.LIMIT)
                if truncated:
                    raise RuntimeError("CRM sonucu kesildi; eksik veriyle yazılmaz.")
                _, tot, _ = con.execute(awards_sql(p), 1)
            finally:
                try:
                    con.close()
                except Exception:  # noqa: BLE001
                    pass
            tenant, at = self.seo.tenant(), now()
            vals: dict[str, dict[str, Any]] = {}
            for r in rows:
                ean = crm.ean_key(r.get("ean"))
                if len(ean) < 8:
                    continue
                bio = max(int(r.get("long_len") or 0), int(r.get("short_len") or 0), int(r.get("bio_len") or 0))
                vals[ean] = dict(tenant_id=tenant, ean=ean[:20], contact_id=str(r.get("contact_id") or "")[:40] or None,
                                 bio_len=bio, awards=int(r.get("awards") or 0), synced_at=at)
            t = tot[0] if tot else {}
            vals[AWARDS_ROW] = dict(tenant_id=tenant, ean=AWARDS_ROW, contact_id=None, bio_len=int(t.get("records") or 0),
                                    awards=int(t.get("linked") or 0), synced_at=at)
            with self.engine().begin() as c:
                c.execute(AUTHOR_CRM.delete().where(AUTHOR_CRM.c.tenant_id == tenant))
                v = list(vals.values())
                for i in range(0, len(v), 1000):
                    c.execute(AUTHOR_CRM.insert(), v[i:i + 1000])
            self.state["count"] = len(vals) - 1
        except Exception as e:  # noqa: BLE001
            self.state["error"] = str(e)[:500]
            log.warning("seo authors crm: %s", e)
        finally:
            self.state.update(running=False, finishedAt=iso(now()))
            self._lock.release()

    # ---- hesap
    def rows(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        from . import EAN, SALES, VIEWS, _num

        tenant = self.seo.tenant()
        site = (self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        lim = rules.thresholds(self.seo.conf)
        j = PRODUCTS.outerjoin(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
        with self.engine().connect() as c:
            prods = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.data_json, CRM_BOOKS.c.data_json, EAN.label("ean"))
                              .select_from(j).where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
                              .order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.product_id)).all()
            pages = c.execute(sa.select(LINKS.c.link, LINKS.c.table_id, LINKS.c.title, LINKS.c.description)
                              .where(LINKS.c.tenant_id == tenant, LINKS.c.type == "model")).mappings().all()
            intros = c.execute(sa.select(PROPOSALS.c.product_id, PROPOSALS.c.fields_json).where(
                PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.product_id.like("model:%"),
                PROPOSALS.c.status == "onaylandi")).all()
            schema_rows = dict(c.execute(sa.select(SCHEMA.c.product_id, SCHEMA.c.issues).where(
                SCHEMA.c.tenant_id == tenant, SCHEMA.c.status == 200)).all())
            crm_rows = {r["ean"]: r for r in c.execute(sa.select(AUTHOR_CRM).where(AUTHOR_CRM.c.tenant_id == tenant)).mappings()}
        wd_cache = self.ent().cached("author")
        by_tid = {str(p["table_id"]): p for p in pages if p["table_id"]}
        by_name: dict[str, Any] = {}
        for p in pages:
            nm = rules.text_of(p["title"]).split("|")[0].strip() or p["link"].replace("-", " ")
            by_name.setdefault(entity_mod.fold(nm), p)
            by_name.setdefault(entity_mod.fold(p["link"].replace("-", " ")), p)
        ready_intro = {pid.split(":", 1)[1] for pid, fj in intros
                       if rules.words(loads(fj, {}).get("Intro")) >= INTRO_MIN_WORDS}
        crm_read = bool(crm_rows)
        agg: dict[str, dict[str, Any]] = {}
        for pid, pdata, cdata, ean in prods:
            p = loads(pdata, {})
            b = loads(cdata, None) if cdata else None
            names = entity_mod.split_authors(p.get("Model"))
            for nm in names:
                a = agg.setdefault(entity_mod.fold(nm), {"name": nm, "sales": 0, "books": 0, "tids": set(), "sameOk": 0,
                                                         "sameChecked": 0, "credOk": 0, "credTotal": 0, "bio": 0,
                                                         "awards": None})
                a["sales"] += _num(p.get("CountTotalSales"))
                a["books"] += 1
                if len(names) == 1 and p.get("ModelId") not in (None, "", "0", 0):
                    a["tids"].add(str(p.get("ModelId")))
                issues = schema_rows.get(pid)
                if issues is not None and ",no_book," not in issues:
                    a["sameChecked"] += 1
                    a["sameOk"] += 0 if ",author_no_sameas," in issues else 1
                if b:
                    text = f"{rules.text_of(p.get('Details'))} {rules.text_of(p.get('Additional6'))}"
                    got = [credited(b.get(k), text) for k in ("translators", "illustrators")]
                    got = [g for g in got if g is not None]
                    if got:
                        a["credTotal"] += 1
                        a["credOk"] += 1 if all(got) else 0
                cr = crm_rows.get(ean)
                if cr and len(names) == 1:  # CRM ana yazar bağı yalnız tek yazarlı kitapta bu yazara aittir
                    a["bio"] = max(a["bio"], cr["bio_len"])
                    a["awards"] = max(a["awards"] or 0, cr["awards"])
        out = []
        for key, a in agg.items():
            page = next((by_tid[t] for t in sorted(a["tids"]) if t in by_tid), None) or by_name.get(key)
            wd = wd_cache.get(key[:300], ({}, None))[0]
            facts = {"page": bool(page), "pageLink": page["link"] if page else None,
                     "pageMetaOk": meta_ok(a["name"], page["title"], page["description"], lim) if page else None,
                     "introReady": bool(page) and str(page["table_id"]) in ready_intro,
                     "crmBio": (a["bio"] >= BIO_MIN) if crm_read else None,
                     "wikidata": wd.get("status") or "bekliyor",
                     "sameas": (a["sameOk"], a["sameChecked"]), "credits": (a["credOk"], a["credTotal"]),
                     "awards": (a["awards"] or 0) if crm_read else None}
            items, score = checklist(facts)
            out.append({"key": key, "name": a["name"], "sales": a["sales"], "books": a["books"], "score": score,
                        "page": {"link": page["link"], "url": f"{site}/{page['link']}", "id": str(page["table_id"])} if page else None,
                        "wikidata": wd.get("wikidata"), "wikipedia": wd.get("wikipedia"), "checks": items,
                        "actions": [i["action"] for i in items if i["action"] and i["state"] in ("eksik", "kismi")]})
        out.sort(key=lambda x: (-x["sales"], x["name"]))
        aw = crm_rows.get(AWARDS_ROW)
        meta = {"crmRead": crm_read, "crmLastRead": iso(aw["synced_at"]) if aw else None,
                "crmAwards": {"records": aw["bio_len"], "linked": aw["awards"]} if aw else None}
        return out, meta


def register(app, ctx) -> None:
    au = Authors(ctx.seo)

    @app.get("/api/v1/seo-geo/authors-trust")
    def seo_authors_trust(request: Request, q: str = "", missing: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        rows, meta = au.rows()
        all_count = len(rows)
        scored = [r["score"] for r in rows if r["score"] is not None]
        missing_counts = {cid: sum(1 for r in rows for i in r["checks"] if i["id"] == cid and i["state"] in ("eksik", "kismi"))
                          for cid in CHECKS}
        if missing in CHECKS:
            rows = [r for r in rows if any(i["id"] == missing and i["state"] in ("eksik", "kismi") for i in r["checks"])]
        if q.strip():
            needle = entity_mod.fold(q)
            rows = [r for r in rows if needle in r["key"]]
        s = max(0, start)
        return {"summary": {"authors": all_count,
                            "average": round(sum(scored) / len(scored)) if scored else None,
                            "missing": missing_counts, **meta, "state": au.state},
                "checks": {k: {"weight": w, "title": t} for k, (w, t) in CHECKS.items()},
                "total": len(rows), "start": s,
                "items": [{k: v for k, v in r.items() if k != "key"} for r in rows[s:s + max(1, limit)]]}

    @app.post("/api/v1/seo-geo/authors-trust/refresh")
    def seo_authors_trust_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        started = au.start()
        ctx.seo.audit(user, "run", "authors", "Yazar güven sinyalleri: CRM okuması", {"started": started})
        return {"started": started, "state": au.state}

    def nightly() -> None:
        au.start()  # arka planda; hemen döner

    ctx.seo.nightly.append(("authors", nightly))
