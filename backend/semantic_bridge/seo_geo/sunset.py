"""Satıştan kalkan kitap sayfaları: her eski adres için ne yapılmalı (301 / stokta yok / 410). Modelsiz, kurallı.

Aday sayfa:
- CRM yayın durumu satıştan kalkmayı söyleyen kitap (etiketin başındaki kod): YS05 artık bizim değil, YS06 devredildi,
  YS12 geri istendi, YS01 iptal, YS11 satıştan çekildi, YS07 baskısı bitti – yeni baskı yapılmayacak. T-soft'ta
  aktif olsun olmasın.
- T-soft'ta pasif olup Search Console'da hâlâ gösterim alan kitap sayfası (son 28 gün).

Öneri kuralları (ilk tutan kazanır, gerekçe yazılır):
1. Aynı kitabın yaşayan başka ürünü varsa → **yeni baskıya 301**: aynı ISBN'li başka aktif ürün; ya da ad (baskı/cilt
   ekleri atılarak) ve yazar aynı aktif ürün; ya da yönlendirme eşleştiricisinin (redirects.suggest) "kesin/yüksek"
   kitap önerisi.
2. Hak bizde değil (bizim değil, devredildi, geri istendi, iptal):
   aranıyorsa (≥ `SEARCHED_MIN` gösterim) ve yazar sayfası varsa → **yazar sayfasına 301** (trafik korunur, kitap
   satılmaz); değilse → **410** (sayfa kalıcı olarak kaldırıldı).
3. Hak bizde (baskısı bitti, çekildi, yalnız T-soft'ta pasif):
   aranıyorsa → **stokta yok olarak kalsın** (sayfa arama gücünü korur; "benzer kitaplar"/yazarın diğer kitapları
   önerilir); aranmıyor ve yazar sayfası varsa → **yazar sayfasına 301**; ikisi de yoksa → stokta yok kalsın.

Karar yalnız kaydedilir (onay yetkisiyle); T-soft'a hiçbir şey yazılmaz. Onaylananlar CSV ile panelden girilir.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import threading
from typing import Any, Optional
from urllib.parse import unquote, urlparse

import sqlalchemy as sa
from fastapi import Request
from pydantic import BaseModel, Field

from . import redirects, rules
from .store import CRM_BOOKS, LINKS, PRODUCTS, _md, iso, loads, now

#: Son 28 günde bu kadar ya da daha çok Google gösterimi alan sayfa "aranıyor" sayılır.
SEARCHED_MIN = 10
#: CRM yayın durumu kodu → neden.
SUNSET_CODES = {"YS01": "iptal", "YS05": "bizim_degil", "YS06": "devredildi", "YS07": "baski_bitti",
                "YS11": "cekildi", "YS12": "geri_istendi"}
REASON_LABEL = {"iptal": "İptal", "bizim_degil": "Artık bizim değil", "devredildi": "Devredildi",
                "baski_bitti": "Baskısı bitti, yeni baskı yok", "cekildi": "Satıştan çekildi",
                "geri_istendi": "Geri istendi", "pasif": "T-soft'ta pasif"}
#: Hakkı bizde olmayan (ya da hiç yayımlanmamış) kitaplar.
GONE_REASONS = {"bizim_degil", "devredildi", "geri_istendi", "iptal"}
ACTIONS = {"yeni_baski_301": "Yeni baskıya 301", "yazar_301": "Yazar sayfasına 301",
           "stokta_yok": "Stokta yok olarak kalsın", "gone_410": "410 — kalıcı olarak kaldırıldı",
           "arama_verisi": "Arama verisi bekleniyor"}
REDIRECT_ACTIONS = {"yeni_baski_301", "yazar_301"}
_EDITION = re.compile(r"\((?:[^)]*)\)|\b(?:yeni|[0-9]+\.?)\s*bask[ıi]\b|\b(?:ciltli|karton kapak|cep boy|b[üu]y[üu]k boy|"
                      r"ciltsiz|kutulu|[öo]zel bask[ıi])\b", re.I)

SUNSET = sa.Table(
    "semantic_seo_sunset", _md,  # satıştan kalkan kitap sayfası için öneri ve karar; gönderim yok
    sa.Column("id", sa.String(16), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("product_id", sa.String(40), nullable=False),
    sa.Column("link", sa.String(600), nullable=False),
    sa.Column("name", sa.String(500)),
    sa.Column("reason", sa.String(24), nullable=False),
    sa.Column("label", sa.String(200)),
    sa.Column("active", sa.Boolean, nullable=False),
    sa.Column("impressions", sa.Integer, nullable=False),
    sa.Column("clicks", sa.Integer, nullable=False),
    sa.Column("action", sa.String(24), nullable=False),
    sa.Column("target", sa.String(600)),
    sa.Column("why", sa.String(800)),
    sa.Column("status", sa.String(16), nullable=False),        # bekliyor | onaylandi | reddedildi
    sa.Column("chosen_action", sa.String(24)),
    sa.Column("chosen_target", sa.String(600)),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("note", sa.String(1000)),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
)
_ready: set[int] = set()
_ready_lock = threading.Lock()


class SunsetDecision(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    choice: str = Field(default="", max_length=24)       # önerilen yerine başka eylem (ACTIONS anahtarı)
    target: str = Field(default="", max_length=600)
    note: str = Field(default="", max_length=1000)


def _ensure(eng: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(eng) in _ready:
            return
        SUNSET.create(eng, checkfirst=True)
        _ready.add(id(eng))


# ------------------------------------------------------------------ saf kurallar
def sunset_reason(label: Optional[str]) -> Optional[str]:
    """CRM yayın durumu etiketi ("YS07 - Baskısı bitti…") → neden; satıştan kalkmayı söylemiyorsa None."""
    code = re.split(r"[\s\-–:]+", (label or "").strip(), maxsplit=1)[0].upper()
    return SUNSET_CODES.get(code)


def path_of(url: Any) -> str:
    """Tam adres ya da göreli bağlantı → karşılaştırma anahtarı (küçük harf, baştaki/sondaki / yok)."""
    s = str(url or "").strip()
    if re.match(r"^[a-z]+://", s, re.I):
        s = urlparse(s).path
    return unquote(s).strip("/").lower()


def gsc_by_path(rows: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    """Search Console sayfa satırları → yol → (gösterim, tıklama)."""
    out: dict[str, tuple[int, int]] = {}
    for r in rows or []:
        keys = r.get("keys") or []
        if not keys:
            continue
        k = path_of(keys[0])
        imp, clk = out.get(k, (0, 0))
        out[k] = (imp + int(r.get("impressions") or 0), clk + int(r.get("clicks") or 0))
    return out


def title_key(name: Any, author: Any) -> str:
    base = _EDITION.sub(" ", rules.text_of(name))
    return f"{redirects._norm_name(base)}|{redirects._norm_name(author)}"


class Editions:
    """Yaşayan (T-soft'ta aktif) kitaplar: ISBN'e ve ad+yazara göre."""

    def __init__(self, products: list[dict[str, Any]]):
        self.by_isbn: dict[str, list[str]] = {}
        self.by_title: dict[str, list[str]] = {}
        for p in products:
            if str(p.get("IsActive", "1")).lower() in ("0", "false"):
                continue
            slug = str(p.get("SeoLink") or "").strip().strip("/")
            if not slug:
                continue
            code = re.sub(r"[^0-9]", "", str(p.get("Barcode") or ""))
            if code:
                self.by_isbn.setdefault(code, []).append(slug)
            self.by_title.setdefault(title_key(p.get("ProductName"), p.get("Model")), []).append(slug)

    def find(self, p: dict[str, Any], idx: Optional[redirects.Index] = None) -> Optional[tuple[str, str]]:
        own = str(p.get("SeoLink") or "").strip().strip("/")
        code = re.sub(r"[^0-9]", "", str(p.get("Barcode") or ""))
        other = [s for s in self.by_isbn.get(code, []) if s != own] if code else []
        if other:
            return other[0], f"Aynı ISBN ({code}) başka bir aktif üründe."
        key = title_key(p.get("ProductName"), p.get("Model"))
        if key.split("|")[0]:
            other = [s for s in self.by_title.get(key, []) if s != own]
            if other:
                return other[0], "Aynı ad ve yazarla aktif kitap var (yeni baskı ya da başka cilt olabilir)."
        if idx is not None and own:
            sug = redirects.suggest(own, idx)
            if sug["target"] and sug["target"] != own and sug["type"] == "product" and sug["confidence"] in ("kesin", "yüksek"):
                return sug["target"], sug["reason"]
        return None


def recommend(reason: str, impressions: int, edition: Optional[tuple[str, str]],
              author_link: Optional[str], searched_min: int = SEARCHED_MIN,
              has_search: bool = True) -> tuple[str, Optional[str], str]:
    """(eylem, hedef, gerekçe). Kurallar dosya başında.

    Arama verisi yoksa (Search Console okunmamış) "aranmıyor" bilinemez: yeni baskı dışında 301/410 önerilmez, karar
    arama verisine kalır. İlk kurulumda veri yokken 281 sayfaya 410, 749'una yazar 301'i öneriliyordu (2026-09-27)."""
    if edition:
        return "yeni_baski_301", edition[0], edition[1]
    if not has_search:
        return ("arama_verisi", None, "Search Console verisi yok; sayfanın aranıp aranmadığı bilinmeden yönlendirme ya da "
                "kalıcı kaldırma önerilmez. Veri gelince yeniden hesaplanır; o zamana kadar sayfa olduğu gibi kalsın.")
    searched = impressions >= searched_min
    seen = f"son 28 günde {impressions} gösterim"
    if reason in GONE_REASONS:
        if searched and author_link:
            return "yazar_301", author_link, f"Hak bizde değil ama sayfa aranıyor ({seen}); yazar sayfası okuru ve trafiği korur."
        if searched:
            return "gone_410", None, f"Hak bizde değil; sayfa aranıyor ({seen}) ama yazar sayfası yok. 410 ya da elle bir hedef seçin."
        return "gone_410", None, f"Hak bizde değil ve sayfa aranmıyor ({seen}); kalıcı olarak kaldırılmalı."
    if searched:
        alt = " Yazarın diğer kitapları önerilsin." if author_link else " Benzer kitaplar önerilsin."
        return "stokta_yok", None, f"Kitap bizim ve sayfa aranıyor ({seen}); sayfa stokta yok olarak kalsın.{alt}"
    if author_link:
        return "yazar_301", author_link, f"Kitap bizim ama sayfa aranmıyor ({seen}); yazar sayfasına yönlensin."
    return "stokta_yok", None, f"Sayfa aranmıyor ({seen}) ve yazar sayfası yok; stokta yok olarak kalabilir."


# ------------------------------------------------------------------ uçlar
def register(app, ctx) -> None:
    seo = ctx.seo
    lock = threading.Lock()

    def eng() -> sa.engine.Engine:
        e = seo.engine()
        _ensure(e)
        return e

    def site() -> str:
        return (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")

    def rebuild() -> int:
        """Adayları yeniden hesaplar; verilmiş kararlar korunur, artık aday olmayan bekleyen kayıt silinir."""
        from . import EAN

        tenant = seo.tenant()
        with lock:
            with eng().connect() as c:
                rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.active, PRODUCTS.c.data_json,
                                           CRM_BOOKS.c.data_json.label("crm")).select_from(
                    PRODUCTS.outerjoin(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN)))
                    .where(PRODUCTS.c.tenant_id == tenant)).all()
                links = c.execute(sa.select(LINKS.c.link, LINKS.c.type, LINKS.c.table_id).where(LINKS.c.tenant_id == tenant)).all()
            g_pages = seo.gsc("pages")
            has_search = bool(g_pages and g_pages.get("rows"))
            gsc = gsc_by_path((g_pages or {}).get("rows") or [])
            prods = [(pid, active, loads(d, {}), loads(cj, None) if cj else None) for pid, active, d, cj in rows]
            editions = Editions([p for _, _, p, _ in prods])
            idx = redirects.Index([{"Type": t, "Link": l} for l, t, _ in links], [p for _, _, p, _ in prods])
            authors = {str(tid): l for l, t, tid in links if t == "model" and tid}
            found: dict[str, dict[str, Any]] = {}
            for pid, active, p, b in prods:
                slug = str(p.get("SeoLink") or "").strip().strip("/")
                if not slug:
                    continue
                label = (b or {}).get("statusLabel")
                reason = sunset_reason(label)
                imp, clk = gsc.get(path_of(slug), (0, 0))
                if not reason:
                    if active or imp <= 0:
                        continue
                    reason = "pasif"
                author = authors.get(str(p.get("ModelId") or ""))
                action, target, why = recommend(reason, imp, editions.find(p, idx), author, has_search=has_search)
                if active:
                    why += " Sitede hâlâ satışta."
                found[pid] = dict(link=slug[:600], name=rules.text_of(p.get("ProductName"))[:500], reason=reason,
                                  label=(label or None) and label[:200], active=bool(active), impressions=imp, clicks=clk,
                                  action=action, target=target, why=why[:800])
            at = now()
            with eng().begin() as c:
                old = {r["product_id"]: r for r in c.execute(sa.select(SUNSET.c.id, SUNSET.c.product_id, SUNSET.c.status)
                                                             .where(SUNSET.c.tenant_id == tenant)).mappings()}
                for pid, vals in found.items():
                    if pid in old:
                        c.execute(SUNSET.update().where(SUNSET.c.id == old[pid]["id"]).values(**vals, synced_at=at))
                    else:
                        sid = hashlib.sha1(f"{tenant}|{pid}".encode()).hexdigest()[:16]
                        c.execute(SUNSET.insert().values(id=sid, tenant_id=tenant, product_id=pid[:40], status="bekliyor",
                                                         synced_at=at, **vals))
                gone = [r["id"] for p, r in old.items() if p not in found and r["status"] == "bekliyor"]
                if gone:
                    c.execute(SUNSET.delete().where(SUNSET.c.id.in_(gone)))
            return len(found)

    def view(r: Any) -> dict[str, Any]:
        s = site()
        tgt = r["chosen_target"] if r["status"] == "onaylandi" else r["target"]
        return {"id": r["id"], "productId": r["product_id"], "link": r["link"], "url": f"{s}/{r['link']}", "name": r["name"],
                "reason": r["reason"], "reasonLabel": REASON_LABEL.get(r["reason"], r["reason"]), "label": r["label"],
                "active": r["active"], "impressions": r["impressions"], "clicks": r["clicks"],
                "action": r["action"], "actionLabel": ACTIONS.get(r["action"], r["action"]), "target": r["target"],
                "targetUrl": f"{s}/{tgt}" if tgt else None, "why": r["why"], "status": r["status"],
                "chosenAction": r["chosen_action"], "chosenTarget": r["chosen_target"], "decidedBy": r["decided_by"],
                "decidedAt": iso(r["decided_at"]), "note": r["note"]}

    @app.get("/api/v1/seo-geo/sunset")
    def seo_sunset(request: Request, action: str = "", status: str = "", q: str = "", start: int = 0,
                   limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        tenant = seo.tenant()
        with eng().connect() as c:
            empty = not c.execute(sa.select(sa.func.count()).select_from(SUNSET).where(SUNSET.c.tenant_id == tenant)).scalar()
        if empty:
            rebuild()
        cond = [SUNSET.c.tenant_id == tenant]
        if action:
            cond.append(SUNSET.c.action == action)
        if status:
            cond.append(SUNSET.c.status == status)
        if q.strip():
            like = f"%{q.strip()}%"
            cond.append(sa.or_(SUNSET.c.link.ilike(like), SUNSET.c.name.ilike(like)))
        with eng().connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(SUNSET).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(SUNSET).where(*cond).order_by(SUNSET.c.impressions.desc(), SUNSET.c.link)
                             .offset(max(0, start)).limit(max(1, limit))).mappings().all()
            by_action = dict(c.execute(sa.select(SUNSET.c.action, sa.func.count()).where(SUNSET.c.tenant_id == tenant)
                                       .group_by(SUNSET.c.action)).all())
            by_status = dict(c.execute(sa.select(SUNSET.c.status, sa.func.count()).where(SUNSET.c.tenant_id == tenant)
                                       .group_by(SUNSET.c.status)).all())
            by_reason = dict(c.execute(sa.select(SUNSET.c.reason, sa.func.count()).where(SUNSET.c.tenant_id == tenant)
                                       .group_by(SUNSET.c.reason)).all())
            last = c.execute(sa.select(sa.func.max(SUNSET.c.synced_at)).where(SUNSET.c.tenant_id == tenant)).scalar()
        g = seo.gsc("pages")
        return {"total": total, "start": max(0, start), "items": [view(r) for r in rows],
                "counts": {"action": by_action, "status": by_status, "reason": by_reason},
                "actions": ACTIONS, "reasons": REASON_LABEL, "searchedMin": SEARCHED_MIN, "lastBuilt": iso(last),
                "gsc": {"start": g["start"], "end": g["end"]} if g else None}

    @app.post("/api/v1/seo-geo/sunset/refresh")
    def seo_sunset_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        n = rebuild()
        seo.audit(user, "run", "sunset", "Satıştan kalkan kitaplar yeniden hesaplandı", {"count": n})
        return {"count": n}

    @app.post("/api/v1/seo-geo/sunset/{sid}/decide")
    def seo_sunset_decide(sid: str, body: SunsetDecision, request: Request) -> dict[str, Any]:
        """Karar yalnız kaydedilir; T-soft'a yazılmaz."""
        from . import _err

        user = ctx.approver(request)
        if body.choice and body.choice not in ACTIONS:
            raise _err(422, "Bilinmeyen eylem.")
        with eng().begin() as c:
            r = c.execute(sa.select(SUNSET).where(SUNSET.c.tenant_id == seo.tenant(), SUNSET.c.id == sid)).mappings().first()
            if not r:
                raise _err(404, "Kayıt bulunamadı.")
            choice = body.choice or r["action"]
            target = (body.target or "").strip().strip("/") or (r["target"] if choice == r["action"] else "")
            if body.action == "approve" and choice in REDIRECT_ACTIONS and not target:
                raise _err(422, "Yönlendirme için hedef adres seçilmeli.")
            approve = body.action == "approve"
            c.execute(SUNSET.update().where(SUNSET.c.id == sid).values(
                status="onaylandi" if approve else "reddedildi", chosen_action=choice if approve else None,
                chosen_target=(target or None) if approve and choice in REDIRECT_ACTIONS else None,
                decided_by=user, decided_at=now(), note=body.note or None))
            r = c.execute(sa.select(SUNSET).where(SUNSET.c.id == sid)).mappings().first()
        seo.audit(user, body.action, sid, r["link"], {"kind": "sunset", "choice": r["chosen_action"], "target": r["chosen_target"]})
        return view(r)

    @app.get("/api/v1/seo-geo/sunset/export.csv")
    def seo_sunset_export(request: Request):
        from fastapi.responses import Response

        ctx.gate(request)
        with eng().connect() as c:
            rows = c.execute(sa.select(SUNSET).where(SUNSET.c.tenant_id == seo.tenant())
                             .order_by(SUNSET.c.status, SUNSET.c.impressions.desc(), SUNSET.c.link)).mappings().all()
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Link", "Kitap", "Neden", "Öneri", "Hedef", "Durum", "Onaylanan eylem", "Onaylanan hedef",
                    "Gösterim (28 gün)", "Gerekçe", "Onaylayan", "Tarih"])
        for r in rows:
            w.writerow([r["link"], r["name"], REASON_LABEL.get(r["reason"], r["reason"]), ACTIONS.get(r["action"], r["action"]),
                        r["target"] or "", r["status"], ACTIONS.get(r["chosen_action"] or "", ""), r["chosen_target"] or "",
                        r["impressions"], r["why"], r["decided_by"] or "", iso(r["decided_at"]) or ""])
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="satistan-kalkan-kitaplar.csv"'})

    def nightly() -> None:
        # Eşitleme ve Search Console okumasından sonra koşar; ağ isteği yok, birkaç saniyelik hesap.
        threading.Thread(target=rebuild, name="seo-sunset", daemon=True).start()

    seo.nightly.append(("sunset", nightly))
