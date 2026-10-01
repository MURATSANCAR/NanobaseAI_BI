"""Aramadan satışa: sayfa başına teşhis ve ayrıntılı eylem kartları (kuralla, model yok, sabit ürün listesi yok).

Her kart modülde ZATEN olan verinin kendisinden kurulur; hiçbir sisteme yazılmaz:
  stok_yok / satista_degil  T-soft ürün kaydı (stok, aktiflik) + benzer kitap adayları (similar.py) → 301 önerisi
  arama_dustu               Search Console sayfa tıklaması/sırası, iki dönem (site geneli değişim hesaba katılır)
  teknik                    tech.py teknik taraması (404, yönlendirme, noindex, canonical …)
  dizin                     crawlbot.py URL Denetimi (Google dizinde değil)
  zengin_sonuc              crawlbot.py zengin sonuç sorunları (eksik şema alanları → hangi T-soft alanından dolar)
  merchant                  merchant.py Google Merchant ürün sorunları (çözüm, alan, yardım bağlantısı)
  icerik                    ürün denetimi puanı/sorunları + mevcut Zeki AI önerisi (mevcut → önerilen) ya da «Öneri üret»
  sepete_eklenmiyor         Analytics: ziyaret yüksek, sepete ekleme oranı site ortalamasının yarısından az → kontrol listesi
  odeme                     Analytics: sepete ekleme var, beklenen satış ≥ 3, satış yok → sepet/ödeme adımı
  dusen_genel / satissiz_genel  bayraklı sayfada başka neden bulunamazsa genel inceleme kartı

Kart: {code, badge, tone, severity, title (emir kipi), why (kanıt, sayılarla), changeHeads, changes [{label, current,
proposed, ok}], steps (2–5), owner/ownerLabel, impact {value, formula} (veri yoksa None), priority/priorityBasis, links}.
Beklenen etki formülü kartta yazılıdır; uydurma sayı yok. Öncelik = iş listesinin etki puanı + beklenen ₺ puanı.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any, Callable, Iterable, Optional
from urllib.parse import quote

import sqlalchemy as sa

from . import rules
from .store import PRODUCTS, PROPOSALS, loads

log = logging.getLogger("semantic.seo_geo")

#: Beklenen ₺ etkisinin öncelik puanı: log10 başına.
MONEY_POINTS = 8.0
#: Sepete ekleme oranı site ortalamasının bu katının altındaysa «sepete eklenmiyor».
CART_RATE_RATIO = 0.5
#: İçerik kartı: ürün denetimi puanı bunun altında (Ürün denetimi ekranındaki «düzeltilmesi gereken» sınırı).
CONTENT_SCORE = 70
TECH_SERIOUS = ("kritik", "yüksek")
EXPECTED_SALES = 3

BADGE = {"stok_yok": "Stokta yok", "satista_degil": "Satışta değil", "arama_dustu": "Arama görünürlüğü düştü",
         "teknik": "Teknik sorun", "dizin": "Google dizininde değil", "zengin_sonuc": "Zengin sonuç eksiği",
         "merchant": "Google Alışveriş sorunu", "icerik": "Ürün metni zayıf", "sepete_eklenmiyor": "Sepete eklenmiyor",
         "odeme": "Sepet / ödeme adımı", "dusen_genel": "Sert düşüş", "satissiz_genel": "Satışsız trafik"}
TONE = {"kritik": "bad", "yüksek": "bad", "orta": "mid", "düşük": "violet"}

#: Zengin sonuç alanı → hangi T-soft alanından ya da tema ayarından dolar.
RICH_FIELD_SOURCE = {
    "shippingdetails": "T-soft kargo ayarları; tema şablonu ürün şemasına kargo bilgisini eklemeli",
    "hasmerchantreturnpolicy": "T-soft iade koşulları; tema şablonu ürün şemasına iade politikasını eklemeli",
    "gtin": "T-soft ürün barkodu (ISBN)", "gtin13": "T-soft ürün barkodu (ISBN)", "isbn": "T-soft ürün barkodu (ISBN)",
    "aggregaterating": "T-soft ürün yorumları ve puanı (yorum yoksa alan boş kalır)", "review": "T-soft ürün yorumları",
    "pricevaliduntil": "T-soft kampanya bitiş tarihi; tema şablonu eklemeli", "brand": "T-soft marka (yayınevi) alanı",
    "image": "T-soft ürün görseli", "description": "T-soft ürün açıklaması", "offers": "T-soft fiyat ve stok alanları",
    "price": "T-soft satış fiyatı", "availability": "T-soft stok miktarı", "author": "T-soft yazar alanı",
    "sku": "T-soft ürün kodu", "name": "T-soft ürün adı",
}


# ------------------------------------------------------------------------------------------------ biçim
def n(v: Any) -> str:
    return f"{int(round(float(v or 0))):,}".replace(",", ".")


def money(v: Any) -> str:
    return f"{n(v)} ₺"


def pct_text(v: Optional[float], digits: int = 1) -> str:
    if v is None:
        return "—"
    return "%" + f"{v * 100:.{digits}f}".replace(".", ",")


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------------------------------------ bağlam
class Context:
    """Bir istekte kartların ihtiyaç duyduğu tablolar; yalnız ekrandaki sayfalar için okunur."""

    def __init__(self, eng: sa.engine.Engine, tenant: str, conf: Callable[[str], str], th: dict[str, Any],
                 site: str = "https://timas.com.tr", similar: Any = None) -> None:
        self.eng, self.tenant, self.conf, self.th = eng, tenant, conf, th or {}
        self.site = (site or "https://timas.com.tr").rstrip("/")
        self.similar = similar
        self.limits = rules.thresholds(conf)
        self.products: dict[str, dict[str, Any]] = {}
        self.tech_pid: dict[str, dict[str, Any]] = {}
        self.tech_key: dict[str, dict[str, Any]] = {}
        self.insp_pid: dict[str, dict[str, Any]] = {}
        self.insp_key: dict[str, dict[str, Any]] = {}
        self.merchant: dict[str, list[dict[str, Any]]] = {}
        self.proposals: dict[str, dict[str, Any]] = {}
        self._tables: Optional[set[str]] = None

    @classmethod
    def from_seo(cls, seo: Any, th: dict[str, Any]) -> "Context":
        return cls(seo.engine(), seo.tenant(), seo.conf, th, seo.conf("SEO_SITE_URL") or "https://timas.com.tr",
                   getattr(seo, "similar", None))

    def has(self, name: str) -> bool:
        if self._tables is None:
            self._tables = set(sa.inspect(self.eng).get_table_names())
        return name in self._tables

    def _urls(self, keys: Iterable[str]) -> list[str]:
        out = []
        for k in keys:
            if k == "(not set)":
                continue
            base = f"{self.site}/{k}" if k else self.site
            out += [base, base + "/"]
        return out

    def preload(self, items: list[dict[str, Any]]) -> None:
        from .ga4 import norm_path

        pids = sorted({it["productId"] for it in items if it.get("productId")} - set(self.products))
        keys = [it["key"] for it in items]
        if not pids and not keys:
            return
        with self.eng.connect() as c:
            if pids and self.has(PRODUCTS.name):
                for r in c.execute(sa.select(PRODUCTS).where(PRODUCTS.c.tenant_id == self.tenant,
                                                             PRODUCTS.c.product_id.in_(pids))).mappings():
                    self.products[str(r["product_id"])] = {
                        "name": r["name"], "active": bool(r["active"]), "data": loads(r["data_json"], {}),
                        "score": r["score"], "issues": loads(r["issues_json"], []), "syncedAt": r["synced_at"]}
            urls = self._urls(keys)
            from .tech import TECH

            if self.has(TECH.name):
                cond = [TECH.c.url.in_(urls)] + ([TECH.c.product_id.in_(pids)] if pids else [])
                for r in c.execute(sa.select(TECH.c.url, TECH.c.product_id, TECH.c.status, TECH.c.issues, TECH.c.chain_json)
                                   .where(TECH.c.tenant_id == self.tenant, sa.or_(*cond))).mappings():
                    v = {"url": r["url"], "status": r["status"], "chain": loads(r["chain_json"], []) or [],
                         "issues": [i for i in (r["issues"] or "").strip(",").split(",") if i]}
                    self.tech_key.setdefault(norm_path(r["url"]), v)
                    if r["product_id"]:
                        self.tech_pid.setdefault(str(r["product_id"]), v)
            from .crawlbot import INSPECT

            if self.has(INSPECT.name):
                cond = [INSPECT.c.url.in_(urls)] + ([INSPECT.c.product_id.in_(pids)] if pids else [])
                for r in c.execute(sa.select(INSPECT.c.url, INSPECT.c.product_id, INSPECT.c.status, INSPECT.c.coverage,
                                             INSPECT.c.rich_json, INSPECT.c.last_crawl, INSPECT.c.error)
                                   .where(INSPECT.c.tenant_id == self.tenant, sa.or_(*cond))).mappings():
                    v = {"url": r["url"], "status": r["status"], "coverage": r["coverage"], "error": r["error"],
                         "rich": loads(r["rich_json"], None), "lastCrawl": r["last_crawl"]}
                    self.insp_key.setdefault(norm_path(r["url"]), v)
                    if r["product_id"]:
                        self.insp_pid.setdefault(str(r["product_id"]), v)
            from .merchant import ITEMS

            if pids and self.has(ITEMS.name):
                for r in c.execute(sa.select(ITEMS.c.product_id, ITEMS.c.offer_id, ITEMS.c.status, ITEMS.c.issues_json)
                                   .where(ITEMS.c.tenant_id == self.tenant, ITEMS.c.product_id.in_(pids))):
                    self.merchant.setdefault(str(r[0]), []).append({"offerId": r[1], "status": r[2],
                                                                    "issues": loads(r[3], [])})
            if pids and self.has(PROPOSALS.name):
                for r in c.execute(sa.select(PROPOSALS.c.id, PROPOSALS.c.product_id, PROPOSALS.c.status,
                                             PROPOSALS.c.fields_json, PROPOSALS.c.created_at)
                                   .where(PROPOSALS.c.tenant_id == self.tenant, PROPOSALS.c.product_id.in_(pids),
                                          PROPOSALS.c.status.in_(("hazir", "onaylandi")))
                                   .order_by(PROPOSALS.c.created_at.desc())).mappings():
                    self.proposals.setdefault(str(r["product_id"]),
                                              {"id": r["id"], "status": r["status"], "fields": loads(r["fields_json"], {})})

    def tech(self, it: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self.tech_pid.get(it.get("productId") or "") or self.tech_key.get(it["key"])

    def inspect(self, it: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self.insp_pid.get(it.get("productId") or "") or self.insp_key.get(it["key"])

    def similar_targets(self, pid: str) -> list[dict[str, Any]]:
        """Benzer kitaplar ekranının adayları; satışta ve stokta olan ilk üç."""
        if self.similar is None:
            return []
        try:
            row = (self.similar.result().get("byId") or {}).get(pid)
        except Exception as e:  # noqa: BLE001 — aday yoksa kart yine çıkar
            log.info("ga4 kartı: benzer kitap okunamadı: %s", e)
            return []
        sugg = (row or {}).get("suggestions") or []
        self.preload([{"productId": s["id"], "key": "(not set)"} for s in sugg])
        from .shopping import stock_of

        out = []
        for s in sugg:
            p = self.products.get(str(s["id"]))
            if not p or not p["active"]:
                continue
            st = stock_of(p["data"])
            if st is not None and st <= 0:
                continue
            out.append({**s, "stock": st})
            if len(out) >= 3:
                break
        return out


# ------------------------------------------------------------------------------------------------ etki ve öncelik
def evidence(it: dict[str, Any]) -> str:
    c = it["cur"]
    return (f"Son 28 günde {n(c['sessions'])} organik ziyaret, {n(c['carts'])} sepete ekleme, {n(c['purchases'])} satış, "
            f"{money(c['revenue'])} ciro")


def potential(it: dict[str, Any], th: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Sayfanın ürün sayfaları ortalamasıyla satması hâlinde 28 günlük ek ciro."""
    conv, aov = th.get("conv"), th.get("aov")
    c = it["cur"]
    if not conv or not aov or not c["sessions"]:
        return None
    exp = c["sessions"] * conv * aov - c["revenue"]
    if exp <= 0:
        return None
    return {"value": round(exp, 2), "formula": f"{n(c['sessions'])} oturum × {pct_text(conv, 2)} organik dönüşüm "
                                              f"(ürün sayfaları ortalaması) × {money(aov)} ortalama sipariş − bu dönemki "
                                              f"ciro {money(c['revenue'])} ≈ {money(exp)} / 28 gün"}


def at_risk(it: dict[str, Any], th: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Sayfa satıyorsa bugünkü cirosu risk altında; satmıyorsa kaçan potansiyel."""
    c = it["cur"]
    if c["revenue"] > 0:
        return {"value": round(c["revenue"], 2), "formula": f"Sayfanın son 28 gündeki organik cirosu {money(c['revenue'])} "
                                                           "bu sorun sürdükçe risk altında"}
    return potential(it, th)


def loss(it: dict[str, Any], th: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Önceki dönem cirosu site geneli değişimle taşınır; bugünkü ciro düşülür."""
    r = th.get("revenueRatio") or 1.0
    prev, cur = it["prev"]["revenue"], it["cur"]["revenue"]
    lost = prev * r - cur
    if prev <= 0 or lost <= 0:
        return None
    return {"value": round(lost, 2), "formula": f"Önceki 28 gün cirosu {money(prev)} × site geneli organik ciro değişimi "
                                               f"{r:.2f} − bu dönemki ciro {money(cur)} ≈ {money(lost)} / 28 gün"}


def cart_gap(it: dict[str, Any], th: dict[str, Any]) -> Optional[dict[str, Any]]:
    c = it["cur"]
    rate, per_cart, aov = th.get("cartRate"), th.get("purchasePerCart"), th.get("aov")
    if not rate or not per_cart or not aov or not c["sessions"]:
        return None
    extra = c["sessions"] * rate - c["carts"]
    val = extra * per_cart * aov
    if val <= 0:
        return None
    return {"value": round(val, 2), "formula": f"({n(c['sessions'])} oturum × {pct_text(rate)} site sepete ekleme oranı − "
                                              f"{n(c['carts'])} sepete ekleme) × {pct_text(per_cart)} sepetten satışa × "
                                              f"{money(aov)} ortalama sipariş ≈ {money(val)} / 28 gün"}


def checkout_gap(it: dict[str, Any], th: dict[str, Any]) -> Optional[dict[str, Any]]:
    c = it["cur"]
    per_cart, aov = th.get("purchasePerCart"), th.get("aov")
    if not per_cart or not aov or not c["carts"]:
        return None
    val = c["carts"] * per_cart * aov - c["revenue"]
    if val <= 0:
        return None
    return {"value": round(val, 2), "formula": f"{n(c['carts'])} sepete ekleme × {pct_text(per_cart)} site sepetten satışa "
                                              f"oranı × {money(aov)} ortalama sipariş − bu dönemki ciro "
                                              f"{money(c['revenue'])} ≈ {money(val)} / 28 gün"}


def clicks_loss(it: dict[str, Any], th: dict[str, Any]) -> Optional[dict[str, Any]]:
    pc, cc = it.get("prevClicks") or 0, it.get("clicks") or 0
    r = th.get("clickRatio") or 1.0
    lost = pc * r - cc
    conv, aov = th.get("conv"), th.get("aov")
    if lost <= 0:
        return None
    if conv and aov:
        val = lost * conv * aov
        return {"value": round(val, 2), "formula": f"(önceki {n(pc)} tıklama × site geneli değişim {r:.2f} − bugünkü {n(cc)}) "
                                                  f"≈ {n(lost)} kaybedilen ziyaret × {pct_text(conv, 2)} dönüşüm × "
                                                  f"{money(aov)} ≈ {money(val)} / 28 gün"}
    return None


def priority(severity: str, it: dict[str, Any], sales: Optional[float], impact: Optional[dict[str, Any]]) -> tuple[float, str]:
    from .worklist import _log_points, _p, impact_score

    score, basis = impact_score(severity, sales=sales, impressions=it.get("impressions"))
    if impact and impact.get("value"):
        pts = _log_points(impact["value"], MONEY_POINTS)
        score = round(score + pts, 1)
        basis = basis.split(" = ")[0] + f" + beklenen etki {money(impact['value'])} ({_p(pts)}) = {_p(score)}"
    return score, basis


# ------------------------------------------------------------------------------------------------ kartlar
def _card(code: str, severity: str, title: str, why: str, owner: str, it: dict[str, Any], *, changes=None,
          heads=("Mevcut", "Önerilen"), steps=None, impact=None, links=None, sales=None) -> dict[str, Any]:
    from .worklist import OWNERS

    pr, basis = priority(severity, it, sales, impact)
    return {"code": code, "badge": BADGE[code], "tone": TONE.get(severity, "mid"), "severity": severity, "title": title,
            "why": why, "changeHeads": list(heads), "changes": changes or [], "steps": steps or [], "owner": owner,
            "ownerLabel": OWNERS.get(owner, owner), "impact": impact, "priority": pr, "priorityBasis": basis,
            "links": links or []}


def _plink(pid: str) -> str:
    return f"/seo-geo/urun-denetimi?urun={quote(pid, safe='')}"


def c_stock(it, ctx: Context, p, detail: bool) -> Optional[dict[str, Any]]:
    from .shopping import stock_of

    if not p or it["cur"]["sessions"] <= 0:
        return None
    stock = stock_of(p["data"])
    inactive = not p["active"]
    if not inactive and (stock is None or stock > 0):
        return None
    synced = p.get("syncedAt")
    when = synced.strftime("%d.%m.%Y %H:%M") if hasattr(synced, "strftime") else "—"
    state = "T-soft’ta satışta değil" if inactive else f"T-soft stok {n(stock)}"
    why = f"{evidence(it)}; {state} (son eşitleme {when})."
    changes = []
    if detail:
        targets = ctx.similar_targets(it["productId"])
        for t in targets:
            from .ga4 import norm_path

            changes.append({"label": "301 yönlendirme", "current": it["path"],
                            "proposed": f"/{norm_path(t['url'])} — {t.get('name') or t['id']} ({t.get('reasonText') or 'benzer kitap'})",
                            "ok": None})
        if not targets:
            changes.append({"label": "Yönlendirme hedefi", "current": it["path"],
                            "proposed": "Satışta ve stokta benzer kitap adayı bulunamadı; Benzer kitaplar ekranında CRM "
                                        "okumasını yenileyin ya da hedefi elle seçin", "ok": False})
    code = "satista_degil" if inactive else "stok_yok"
    title = ("Satışta olmayan kitabın sayfasını benzer kitaba yönlendirin" if inactive else
             "Stokta olmayan kitabın sayfasını benzer kitaba yönlendirin ya da stoğu açın")
    steps = ["Kitabın yeniden basılıp basılmayacağını yayın birimine sorun; stok gelecekse T-soft panelinde stok ve satış "
             "durumunu açın ve sayfayı olduğu gibi bırakın.",
             "Stok gelmeyecekse Benzer kitaplar ekranında bu kitabın adaylarından hedefi seçip onaylayın.",
             "Yönlendirmeler ekranından onaylı 301 listesini indirip T-soft panelinin yönlendirme bölümüne elle girin.",
             "Bir hafta sonra bu ekranda eski sayfanın ziyaretinin yeni sayfaya geçtiğini denetleyin."]
    links = [{"label": "Benzer kitaplar", "to": "/seo-geo/benzer-kitaplar"},
             {"label": "Yönlendirmeler", "to": "/seo-geo/yonlendirmeler"}]
    sev = "yüksek" if it["cur"]["sessions"] >= (ctx.th.get("highTraffic") or math.inf) else "orta"
    return _card(code, sev, title, why, "tsoft", it, changes=changes, heads=("Eski adres", "Önerilen hedef"), steps=steps,
                 impact=at_risk(it, ctx.th) if it["cur"]["revenue"] else potential(it, ctx.th), links=links,
                 sales=_f(p["data"].get("CountTotalSales")))


def c_search(it, ctx: Context, p) -> Optional[dict[str, Any]]:
    from .ga4 import sharp_drop

    pc, cc = it.get("prevClicks"), it.get("clicks")
    if pc is None or not pc:
        return None
    ratio = ctx.th.get("clickRatio") or 1.0
    pos, ppos = it.get("position"), it.get("prevPosition")
    fell = sharp_drop(pc, cc or 0, ratio)
    sank = pos is not None and ppos is not None and pos - ppos >= 3 and pc >= 10
    if not fell and not sank:
        return None
    why = (f"Google tıklaması önceki 28 günde {n(pc)}, bu dönem {n(cc or 0)} (site genelinde değişim {ratio:.2f} kat); "
           f"ortalama sıra {ppos:.1f} → {pos:.1f}" if pos is not None and ppos is not None else
           f"Google tıklaması önceki 28 günde {n(pc)}, bu dönem {n(cc or 0)} (site genelinde değişim {ratio:.2f} kat)")
    why += f"; gösterim {n(it.get('prevImpressions'))} → {n(it.get('impressions'))}."
    changes = [{"label": "Google tıklaması", "current": n(pc), "proposed": n(cc or 0), "ok": False},
               {"label": "Gösterim", "current": n(it.get("prevImpressions")), "proposed": n(it.get("impressions")), "ok": None}]
    if pos is not None and ppos is not None:
        changes.append({"label": "Ortalama sıra", "current": f"{ppos:.1f}", "proposed": f"{pos:.1f}", "ok": pos <= ppos})
    steps = ["Fırsatlar ve etki ekranında bu sayfanın hangi aramalarda sıra kaybettiğine bakın.",
             "Google taraması ekranında sayfanın dizinde ve doğru asıl adreste olduğunu doğrulayın.",
             "Yarışan sayfalar ekranında aynı aramada başka bir sayfamızın öne geçip geçmediğini kontrol edin.",
             "Başlık ve açıklamayı kaybedilen aramalara göre Zeki AI önerisiyle yenileyin (Ürün denetimi)."]
    links = [{"label": "Fırsatlar ve etki", "to": "/seo-geo/firsatlar"},
             {"label": "Google taraması", "to": "/seo-geo/google-taramasi"},
             {"label": "Yarışan sayfalar", "to": "/seo-geo/yarisan"}]
    if it.get("productId"):
        links.append({"label": "Öneri üret", "to": _plink(it["productId"]), "kind": "propose"})
    return _card("arama_dustu", "yüksek" if fell and "dusen_oturum" in it["flags"] else "orta",
                 "Sayfanın Google’daki kaybını bulun ve başlığını kaybedilen aramalara göre yenileyin", why, "seo", it,
                 changes=changes, heads=("Önceki 28 gün", "Bu dönem"), steps=steps, impact=clicks_loss(it, ctx.th),
                 links=links, sales=_f(p["data"].get("CountTotalSales")) if p else None)


TECH_STEP = {
    "not_found": "T-soft panelinde ürünün yayında ve adresinin doğru olduğunu denetleyin; kalkan adres için yönlendirme girin.",
    "server_error": "Sayfanın sunucu hatasını site yöneticisine bildirin; hata sürerse Google sayfayı dizinden düşürür.",
    "fetch_error": "Sayfanın açılmama nedenini (erişim engeli, zaman aşımı) site yöneticisiyle denetleyin.",
    "redirect_loop": "Birbirini gösteren yönlendirmeleri T-soft panelinde kaldırıp tek hedefe bağlayın.",
    "noindex": "T-soft panelinde sayfanın arama motorlarına kapalı ayarını kaldırın.",
    "header_noindex": "Sunucunun gönderdiği dizine kapalı başlığını site yöneticisine kaldırtın.",
    "redirect_chain": "Site içi bağlantıları ve site haritasını zincirin son adresine çevirin.",
    "redirected": "Site içi bağlantıları ve site haritasını yönlendirilen son adrese çevirin.",
    "canonical_other": "Ürün sayfasının asıl adres (canonical) ayarını sayfanın kendi adresine düzeltin.",
    "canonical_broken": "Asıl adres (canonical) ayarını açılan ve yönlenmeyen adrese düzeltin.",
    "canonical_multiple": "Tema şablonunda sayfaya tek bir asıl adres (canonical) etiketi bırakın.",
}


def c_tech(it, ctx: Context, p) -> Optional[dict[str, Any]]:
    from .tech import CHECKS

    t = ctx.tech(it)
    if not t:
        return None
    found = [i for i in t["issues"] if CHECKS.get(i, ("orta",))[0] in TECH_SERIOUS or i == "redirected"]
    if not found:
        return None
    order = {"kritik": 0, "yüksek": 1, "orta": 2, "düşük": 3}
    found.sort(key=lambda i: order.get(CHECKS[i][0], 9))
    worst = CHECKS[found[0]][0]
    chain = " → ".join(f"{x.get('url')} ({x.get('status')})" for x in t["chain"] if isinstance(x, dict)) or None
    why = (f"{evidence(it)}. Teknik taramada {len(found)} sorun: " + ", ".join(CHECKS[i][1] for i in found)
           + f"; son durum kodu {t['status'] if t['status'] is not None else '—'}.")
    changes = [{"label": CHECKS[i][1], "current": chain if i in ("redirect_chain", "redirected", "redirect_loop") and chain
                else (t["url"] or it["path"]), "proposed": CHECKS[i][2], "ok": False} for i in found]
    steps = ["Teknik sağlık ekranında bu adresi açıp sorunun ayrıntısına bakın."]
    steps += [TECH_STEP[i] for i in dict.fromkeys(found) if i in TECH_STEP][:3]
    steps.append("Düzeltmeden sonra Teknik sağlık ekranında taramayı yeniden başlatıp sorunun kalktığını görün.")
    return _card("teknik", worst if worst in TONE else "orta", f"Sayfanın teknik sorununu giderin: {CHECKS[found[0]][1]}",
                 why, "tsoft", it, changes=changes, heads=("Etkilenen adres", "Neden sorun / ne olmalı"), steps=steps,
                 impact=at_risk(it, ctx.th), links=[{"label": "Teknik sorunu aç", "to": "/seo-geo/teknik"}],
                 sales=_f(p["data"].get("CountTotalSales")) if p else None)


def c_index(it, ctx: Context, p) -> Optional[dict[str, Any]]:
    from .crawlbot import STATUS_LABEL
    from .worklist import CRAWL_SEVERITY

    r = ctx.inspect(it)
    if not r or r.get("error") or r["status"] not in CRAWL_SEVERITY or r["status"] == "other":
        return None
    label = STATUS_LABEL.get(r["status"], (r["status"],))[0]
    last = r.get("lastCrawl")
    why = (f"{evidence(it)}. Google’ın son denetim kararı: {label}" + (f" ({r['coverage']})" if r.get("coverage") else "")
           + (f"; son tarama {last.strftime('%d.%m.%Y')}" if hasattr(last, "strftime") else "") + ".")
    steps = ["Google taraması ekranında bu adresin denetim ayrıntısına bakın.",
             "Sayfa dizine kapalıysa ya da bulunamıyorsa önce Teknik sağlık kartındaki sorunu giderin.",
             "Kopya ya da başka asıl adres seçildiyse asıl adres (canonical) ayarını ve site içi bağlantıları bu sayfaya çevirin.",
             "Düzeltmeden sonra Google taraması ekranında adresi yeniden denetletin."]
    return _card("dizin", CRAWL_SEVERITY[r["status"]], "Sayfanın Google dizinine girmesini sağlayın", why, "seo", it,
                 changes=[{"label": "Google durumu", "current": label, "proposed": "Dizinde", "ok": False}],
                 steps=steps, impact=at_risk(it, ctx.th),
                 links=[{"label": "Google taraması", "to": "/seo-geo/google-taramasi"}],
                 sales=_f(p["data"].get("CountTotalSales")) if p else None)


def rich_fields(issues: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """(alan, Google iletisi, önem) — iletideki tırnaklı alan adı; yoksa iletinin kendisi."""
    out, seen = [], set()
    for i in issues or []:
        msg = str(i.get("message") or "")
        m = re.search(r"[\"“']([A-Za-z]+)[\"”']", msg)
        field = m.group(1) if m else (i.get("type") or msg)
        if field in seen:
            continue
        seen.add(field)
        out.append((field, msg, str(i.get("severity") or "")))
    return out


def c_rich(it, ctx: Context, p) -> Optional[dict[str, Any]]:
    r = ctx.inspect(it)
    rich = (r or {}).get("rich") or {}
    fields = rich_fields(rich.get("issues") or [])
    if not fields:
        return None
    changes = [{"label": f, "current": msg or "Eksik ya da hatalı",
                "proposed": RICH_FIELD_SOURCE.get(f.lower(), "Tema şablonu bu alanı ürün şemasına eklemeli"), "ok": False}
               for f, msg, _ in fields]
    why = (f"{evidence(it)}. Google zengin sonuç denetimi bu sayfada {len(fields)} alanı eksik ya da hatalı buldu: "
           + ", ".join(f for f, _, _ in fields) + ".")
    steps = ["Google taraması ekranında «Zengin sonuç sorunları» süzgeciyle sayfanın ayrıntısına bakın.",
             "T-soft alanından dolan eksikleri (barkod, marka, görsel, açıklama, stok) ürün kaydında tamamlayın.",
             "Tema şablonunun eklemesi gerekenleri Şema denetimi ekranındaki tema isteği belgesiyle site yöneticisine iletin.",
             "Düzeltmeden sonra adresi Google taraması ekranında yeniden denetletin."]
    sev = "yüksek" if any(s.upper() == "ERROR" for _, _, s in fields) else "orta"
    return _card("zengin_sonuc", sev, "Ürün sayfasının yapısal verisindeki eksik alanları tamamlayın", why, "tsoft", it,
                 changes=changes, heads=("Google’ın bildirdiği", "Nereden dolar"), steps=steps, impact=at_risk(it, ctx.th),
                 links=[{"label": "Zengin sonuç sorunları", "to": "/seo-geo/google-taramasi?filtre=rich"},
                        {"label": "Şema denetimi", "to": "/seo-geo/sema"}],
                 sales=_f(p["data"].get("CountTotalSales")) if p else None)


def c_merchant(it, ctx: Context, p) -> Optional[dict[str, Any]]:
    from .merchant import ATTRIBUTE_LABEL, RESOLUTION_LABEL, SEV_LABEL, SEV_RANK

    pid = it.get("productId")
    issues: dict[str, dict[str, Any]] = {}
    for m in ctx.merchant.get(pid or "", []):
        for i in m["issues"]:
            if str(i.get("severity") or "").upper() in ("DISAPPROVED", "DEMOTED"):
                cur = issues.get(i["code"])
                if cur is None or SEV_RANK.get(i["severity"], 0) > SEV_RANK.get(cur["severity"], 0):
                    issues[i["code"]] = i
    if not issues:
        return None
    rows = sorted(issues.values(), key=lambda i: -SEV_RANK.get(i["severity"], 0))
    first = rows[0]
    changes = []
    for i in rows:
        attr = ATTRIBUTE_LABEL.get(i.get("attribute") or "", i.get("attribute"))
        changes.append({"label": (i.get("description") or i["code"]) + (f" (alan: {attr})" if attr else ""),
                        "current": f"{SEV_LABEL.get(i['severity'], i['severity'])}" + (f" — {i['detail']}" if i.get("detail") else ""),
                        "proposed": RESOLUTION_LABEL.get(i.get("resolution") or "", i.get("resolution") or "Google’ın açıklamasına göre düzeltin"),
                        "ok": False, "doc": i.get("documentation")})
    why = (f"{evidence(it)}. Google Merchant Center bu ürün için {len(rows)} sorun bildiriyor; en ağırı: "
           f"{first.get('description') or first['code']} ({SEV_LABEL.get(first['severity'], first['severity'])}).")
    steps = ["Google Alışveriş hazırlığı ekranında sorun türüne tıklayıp ürünü açın.",
             "Sorunlu alanı (" + ", ".join(dict.fromkeys(ATTRIBUTE_LABEL.get(i.get("attribute") or "", i.get("attribute") or "ürün verisi") for i in rows))
             + ") T-soft ürün kaydında düzeltin.",
             "Google’ın yardım bağlantısındaki koşulu (ör. geçerli barkod, görsel boyutu) karşıladığınızı denetleyin.",
             "Bir sonraki okumada (6 saatte bir) ürün durumunun «Onaylı»ya döndüğünü görün."]
    links = [{"label": "Merchant’ta gör", "to": f"/seo-geo/alisveris?merchant={quote(first['code'], safe='')}"}]
    return _card("merchant", "yüksek" if first["severity"] == "DISAPPROVED" else "orta",
                 f"Google Alışveriş’teki ürün sorununu düzeltin: {first.get('description') or first['code']}", why, "tsoft",
                 it, changes=changes, heads=("Google’ın kararı", "Çözüm"), steps=steps, impact=at_risk(it, ctx.th),
                 links=links, sales=_f(p["data"].get("CountTotalSales")) if p else None)


CONTENT_RULES = ("title_missing", "title_length", "title_duplicate", "meta_missing", "meta_length", "meta_same_as_title",
                 "desc_missing", "desc_short")


def c_content(it, ctx: Context, p) -> Optional[dict[str, Any]]:
    if not p or (it["cur"]["sessions"] <= 0 and not it.get("clicks")):
        return None
    bad = [i for i in p["issues"] if i.get("rule") in CONTENT_RULES]
    if (p["score"] is None or p["score"] >= CONTENT_SCORE) and not bad:
        return None
    lim = ctx.limits
    d = p["data"]
    prop = ctx.proposals.get(it["productId"])
    pf = (prop or {}).get("fields") or {}
    title, meta, words = rules.text_of(d.get("SeoTitle")), rules.text_of(d.get("SeoDescription")), rules.words(d.get("Details"))
    none_text = "Zeki AI önerisi yok — «Öneri üret»"
    changes = [
        {"label": f"SEO başlığı ({len(title)} karakter; kural {lim['title_min']}–{lim['title_max']})",
         "current": title or "(boş)", "proposed": rules.text_of(pf.get("SeoTitle")) or none_text,
         "ok": lim["title_min"] <= len(title) <= lim["title_max"]},
        {"label": f"Meta açıklama ({len(meta)} karakter; kural {lim['meta_min']}–{lim['meta_max']})",
         "current": meta or "(boş)", "proposed": rules.text_of(pf.get("SeoDescription")) or none_text,
         "ok": lim["meta_min"] <= len(meta) <= lim["meta_max"]},
        {"label": f"Ürün açıklaması ({words} kelime; en az {lim['desc_min_words']})",
         "current": f"{words} kelime", "proposed": (f"Önerilen metin {rules.words(pf.get('Details'))} kelime"
                                                    if pf.get("Details") else none_text),
         "ok": words >= lim["desc_min_words"]},
    ]
    why = (f"{evidence(it)}. Ürün denetimi puanı {p['score']}/100"
           + (f"; sorunlar: " + ", ".join(i.get("title") or i["rule"] for i in bad) if bad else "") + ".")
    state = {"hazir": "onay bekleyen bir Zeki AI önerisi var", "onaylandi": "onaylanmış bir öneri var; sitede henüz görünmüyor"}
    if prop:
        why += f" Bu kitap için {state.get(prop['status'], 'öneri var')}."
    steps = ["Ürün denetimi ekranında kitabı açın.",
             "Öneri yoksa «Öneri üret»e basın; varsa önerilen başlık, meta ve açıklamayı okuyup gerekirse düzeltin.",
             "Onay verebilen kişi öneriyi onaylasın (onay yalnız kayda geçer, hiçbir yere gönderilmez).",
             "Onaylanan metni T-soft panelinde ürünün SEO başlığı, meta açıklama ve açıklama alanlarına elle girin."]
    return _card("icerik", "yüksek" if (p["score"] or 0) < 50 else "orta",
                 "Ürün başlığını, meta açıklamasını ve açıklamasını kurallara göre yenileyin", why, "icerik", it,
                 changes=changes, steps=steps, impact=at_risk(it, ctx.th) if it["cur"]["revenue"] else potential(it, ctx.th),
                 links=[{"label": "Öneriyi aç" if prop else "Öneri üret", "to": _plink(it["productId"]),
                         "kind": "propose"}], sales=_f(d.get("CountTotalSales")))


def checklist(it, ctx: Context, p) -> list[dict[str, Any]]:
    """Fiyat, görsel, açıklama, stok: hangisi veride sorunlu görünüyor."""
    from .shopping import price_of, stock_of

    out = []
    if not p:
        return out
    d = p["data"]
    price, sale = price_of(d)
    out.append({"label": "Fiyat", "current": (money(price) if price is not None else "—") + (f", indirimli {money(sale)}" if sale else ""),
                "proposed": "İndirim var" if sale else "İndirim yok; kampanya ya da kargo eşiğini değerlendirin", "ok": None})
    words = rules.words(d.get("Details"))
    lim = ctx.limits["desc_min_words"]
    out.append({"label": "Ürün açıklaması", "current": f"{words} kelime",
                "proposed": f"en az {lim} kelime (kural)", "ok": words >= lim})
    img_rules = [i.get("title") or i["rule"] for i in p["issues"] if str(i.get("rule", "")).startswith("image")]
    t = ctx.tech(it)
    from .tech import CHECKS, IMAGE_CHECKS

    img_tech = [CHECKS[i][1] for i in (t or {}).get("issues", []) if i in IMAGE_CHECKS]
    probs = img_rules + img_tech
    out.append({"label": "Görsel", "current": ", ".join(probs) if probs else ("Sorun yok" if t else "Görsel sorunu kaydı yok"),
                "proposed": "Kapak görseli net, kitap adını taşıyan alt metinli ve boyutlu olmalı", "ok": not probs})
    st = stock_of(d)
    out.append({"label": "Stok", "current": "—" if st is None else n(st), "proposed": "Stokta olmalı",
                "ok": None if st is None else st > 0})
    return out


def c_cart(it, ctx: Context, p) -> Optional[dict[str, Any]]:
    th = ctx.th
    c = it["cur"]
    rate = th.get("cartRate")
    if it["kind"] != "urun" or not rate or c["sessions"] < (th.get("highTraffic") or math.inf):
        return None
    page_rate = c["carts"] / c["sessions"]
    if page_rate >= rate * CART_RATE_RATIO:
        return None
    changes = [{"label": "Sepete ekleme oranı", "current": pct_text(page_rate), "proposed": f"site ortalaması {pct_text(rate)}",
                "ok": False}] + checklist(it, ctx, p)
    why = (f"{evidence(it)}. Sepete ekleme oranı {pct_text(page_rate)}; ürün sayfalarının ortalaması {pct_text(rate)}. "
           "Sayfa ilgi çekiyor ama okur kitabı sepete eklemiyor.")
    steps = ["Aşağıdaki kontrol listesinde sorunlu görünen maddeden başlayın (fiyat, açıklama, görsel, stok).",
             "Sayfayı telefonda açıp fiyatın, kargo bilgisinin ve «Sepete ekle» düğmesinin ilk ekranda göründüğünü denetleyin.",
             "Açıklama kısa ise Ürün denetimi ekranında Zeki AI önerisiyle genişletin.",
             "Değişiklikten 28 gün sonra bu ekranda sepete ekleme oranını yeniden karşılaştırın."]
    links = [{"label": "Öneri üret", "to": _plink(it["productId"]), "kind": "propose"}] if it.get("productId") else []
    return _card("sepete_eklenmiyor", "orta", "Ziyaret alan ama sepete eklenmeyen kitabın fiyatını, görselini ve açıklamasını gözden geçirin",
                 why, "icerik", it, changes=changes, heads=("Şu an", "Olması gereken"), steps=steps,
                 impact=cart_gap(it, th), links=links, sales=_f(p["data"].get("CountTotalSales")) if p else None)


def c_checkout(it, ctx: Context, p) -> Optional[dict[str, Any]]:
    th = ctx.th
    c = it["cur"]
    per_cart = th.get("purchasePerCart")
    if it["kind"] != "urun" or c["purchases"] > 0 or not per_cart or c["carts"] * per_cart < EXPECTED_SALES:
        return None
    changes = [{"label": "Sepetten satışa", "current": "%0", "proposed": f"site ortalaması {pct_text(per_cart)}", "ok": False}]
    changes += [x for x in checklist(it, ctx, p) if x["label"] in ("Fiyat", "Stok")]
    changes.append({"label": "Kargo ve ödeme", "current": "Veride izlenmiyor",
                    "proposed": "Bu ürüne özel kargo, satış sınırı ya da ödeme kısıtı olmamalı", "ok": None})
    why = (f"{evidence(it)}. {n(c['carts'])} sepete eklemeden site ortalamasıyla ≈{n(c['carts'] * per_cart)} satış "
           "beklenirdi; hiç satış yok. Sorun sepet, kargo ya da ödeme adımında olabilir.")
    steps = ["Siteden kitabı sepete ekleyip ödeme adımına kadar deneyin (kargo ücreti, stok uyarısı, satış sınırı).",
             "T-soft panelinde ürünün stok, satış sınırı, kargo ve ödeme ayarlarını denetleyin.",
             "Fiyat rakip sitelerden belirgin yüksekse Rakipler ekranında aynı kitabın fiyatına bakın.",
             "Düzeltmeden sonra bu ekranda sepetten satışa dönüşü izleyin."]
    return _card("odeme", "yüksek", "Sepete eklenip satın alınmayan kitabın sepet ve ödeme adımını denetleyin", why, "tsoft",
                 it, changes=changes, heads=("Şu an", "Olması gereken"), steps=steps, impact=checkout_gap(it, th),
                 links=[{"label": "Rakipler", "to": "/seo-geo/rakipler"}],
                 sales=_f(p["data"].get("CountTotalSales")) if p else None)


def c_general(it, ctx: Context, p, found: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Bayraklı sayfada başka neden bulunamadıysa genel inceleme kartı (kanıt ve adımlarla)."""
    if found:
        return None
    sales = _f(p["data"].get("CountTotalSales")) if p else None
    if "dusen_oturum" in it["flags"] or "dusen_ciro" in it["flags"]:
        pv, cu = it["prev"], it["cur"]
        why = (f"Organik ziyaret {n(pv['sessions'])} → {n(cu['sessions'])}, satış {n(pv['purchases'])} → {n(cu['purchases'])}, "
               f"ciro {money(pv['revenue'])} → {money(cu['revenue'])} (önceki 28 gün → son 28 gün); site geneli ziyaret "
               f"değişimi {(ctx.th.get('sessionRatio') or 1):.2f} kat. Stok, teknik, dizin ve ürün kaydında bu düşüşü açıklayan "
               "bir kayıt bulunmadı.")
        steps = ["Fırsatlar ve etki ekranında sayfanın arama sıralarındaki değişime bakın.",
                 "Aynı dönemde fiyat, kampanya ya da kapak değişikliği olup olmadığını T-soft panelinden denetleyin.",
                 "Rakipler ekranında aynı kitap aramasında sıranın başka siteye geçip geçmediğine bakın.",
                 "Sezon takviminde kitabın bağlı olduğu dönem geçmiş mi, kontrol edin."]
        what = ("Organik ziyareti ve satışı" if {"dusen_oturum", "dusen_ciro"} <= set(it["flags"])
                else "Organik ziyareti" if "dusen_oturum" in it["flags"] else "Organik satışı")
        return _card("dusen_genel", "orta", f"{what} sert düşen sayfanın nedenini inceleyin", why, "seo", it,
                     changes=[{"label": "Organik ziyaret", "current": n(pv["sessions"]), "proposed": n(cu["sessions"]),
                               "ok": False if "dusen_oturum" in it["flags"] else None},
                              {"label": "Satış", "current": n(pv["purchases"]), "proposed": n(cu["purchases"]), "ok": None},
                              {"label": "Ciro", "current": money(pv["revenue"]), "proposed": money(cu["revenue"]), "ok": None}],
                     heads=("Önceki 28 gün", "Son 28 gün"), steps=steps, impact=loss(it, ctx.th),
                     links=[{"label": "Fırsatlar ve etki", "to": "/seo-geo/firsatlar"},
                            {"label": "Rakipler", "to": "/seo-geo/rakipler"}], sales=sales)
    if "satissiz" in it["flags"]:
        why = (f"{evidence(it)}. Ürün sayfalarının ortalamasıyla ≈{n(it['cur']['sessions'] * (ctx.th.get('conv') or 0))} "
               "satış beklenirdi. Stok, teknik, dizin, Google Alışveriş ve sepet adımında açıklayan bir kayıt bulunmadı.")
        steps = ["Sayfayı telefonda açıp fiyatı, stoğu ve «Sepete ekle» düğmesini denetleyin.",
                 "Okurun bu sayfaya hangi aramayla geldiğini Fırsatlar ve etki ekranında görün; arama başka bir kitabı "
                 "arıyorsa sayfaya o kitaba bağlantı ekleyin.",
                 "Başlık ve açıklamanın aramayla uyumunu Ürün denetimi ekranında Zeki AI önerisiyle gözden geçirin."]
        return _card("satissiz_genel", "orta", "Ziyaret alan ama satmayan kitap sayfasını inceleyin", why, "icerik", it,
                     changes=checklist(it, ctx, p), heads=("Şu an", "Olması gereken"), steps=steps,
                     impact=potential(it, ctx.th),
                     links=([{"label": "Öneri üret", "to": _plink(it["productId"]), "kind": "propose"}]
                            if it.get("productId") else []), sales=sales)
    return None


def cards(it: dict[str, Any], ctx: Context, detail: bool = True) -> list[dict[str, Any]]:
    """Sayfanın bütün kartları, önceliğe göre. `detail=False`: benzer kitap adayları okunmaz (liste/CSV/iş listesi)."""
    if it["kind"] == "belirsiz":
        return []
    p = ctx.products.get(it.get("productId") or "")
    out: list[dict[str, Any]] = []
    for fn in (lambda: c_stock(it, ctx, p, detail), lambda: c_search(it, ctx, p), lambda: c_tech(it, ctx, p),
               lambda: c_index(it, ctx, p), lambda: c_rich(it, ctx, p), lambda: c_merchant(it, ctx, p),
               lambda: c_content(it, ctx, p), lambda: c_cart(it, ctx, p), lambda: c_checkout(it, ctx, p)):
        try:
            card = fn()
        except Exception as e:  # noqa: BLE001 — bir kuralın verisi bozuksa ötekiler yine çıkar
            log.warning("ga4 kartı %s: %s", it.get("key"), e)
            card = None
        if card:
            out.append(card)
    g = c_general(it, ctx, p, out)
    if g:
        out.append(g)
    out.sort(key=lambda c: -c["priority"])
    return out


# ------------------------------------------------------------------------------------------------ Zeki AI özeti
def summary_facts(it: dict[str, Any], cs: list[dict[str, Any]]) -> str:
    lines = [f"Sayfa: {it.get('title') or it['path']} ({it['path']})", evidence(it) + "."]
    for c in cs:
        lines.append(f"Yapılacak: {c['title']}. Kanıt: {c['why']} Sorumlu: {c['ownerLabel']}."
                     + (f" Beklenen etki: {c['impact']['formula']}." if c.get("impact") else ""))
    return "\n".join(lines)


def zeki_summary(seo: Any, facts: str) -> dict[str, Any]:
    """2–3 cümlelik düz dil özet; yalnız olgulardan. Model yoksa ya da olguda olmayan sayı yazarsa özet yok."""
    from semantic_bridge import zeki_text as Z

    try:
        out = Z.interpret(facts, "", rt=seo.runtime(), module="seo",
                          task="Bu sayfanın durumunu ve önce yapılacak işi yöneticiye 2–3 cümleyle anlat. Yalnız olgulardaki "
                               "sayıları kullan; yeni sayı yazma.", max_sentences=3, max_chars=600)
    except Exception as e:  # noqa: BLE001
        log.info("ga4 özeti yazılamadı: %s", e)
        return {"text": None, "source": "yok"}
    return {"text": out.metin if out.kaynak == "zeki" else None, "source": out.kaynak}
