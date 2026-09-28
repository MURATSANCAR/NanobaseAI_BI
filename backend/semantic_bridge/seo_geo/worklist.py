"""Tek iş listesi: bütün SEO & GEO ekranlarının ürettiği işler tek, önceliklendirilmiş kuyrukta.

Her kaynak (collector) başka bir özelliğin KENDİ tablosunu okur; web'e, T-soft'a, CRM'e istek atılmaz, hiçbir yere
yazılmaz. Kaynak iş maddeleri üretir: {key (sabit özet), kaynak, başlık, ayrıntı, sorumlu, etki puanı, puanın
gerekçesi, ekran bağlantısı, ürün, sayı}. Sorumlular: T-soft/site yöneticisi, telif birimi, içerik/editör ekibi,
Timaş BT, yayın/iş birimi, SEO sorumlusu (bizim sistemimizdeki onaylar).

Etki puanı açık ve veriye dayalıdır (uydurma trafik yok):
  önem derecesi puanı (sabit) + satış puanı (T-soft toplam satış adedi, log10) + arama puanı (Search Console son 28 gün
  gösterimi, log10) + tahmini ek tıklama puanı (fırsat hesabının kendi eğrisi, log10) + kayıt sayısı puanı (gruplu
  işlerde, log10). Veri yoksa yalnız önem derecesi kalır; her maddenin yanında hesap yazılıdır.

Durum `semantic_seo_worklist_state`'te (yeni | yapiliyor | bitti | yoksay, sorumlu kişi, not). Kaynak bir maddeyi artık
üretmiyorsa madde listeden kendiliğinden düşer ve `semantic_seo_worklist_log`'a "kendiliğinden kapandı" yazılır;
kaynağı hata veren (koşamayan) kaynağın maddelerine dokunulmaz. Hesap ağırdır: bellekte `CACHE_SECONDS` saklanır.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import math
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from .store import CRM_BOOKS, LINKS, PRODUCTS, PROPOSALS, REDIRECTS, RUNS, SCHEMA, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

# ------------------------------------------------------------------------------------------------ sabitler
OWNERS: dict[str, str] = {
    "tsoft": "T-soft / site yöneticisi",
    "telif": "Telif birimi",
    "icerik": "İçerik / editör ekibi",
    "bt": "Timaş BT",
    "yayin": "Yayın / iş birimi",
    "seo": "SEO sorumlusu",
}
STATUSES: dict[str, str] = {"yeni": "Yeni", "yapiliyor": "Yapılıyor", "bitti": "Bitti", "yoksay": "Yok sayıldı"}
OPEN_STATUSES = ("yeni", "yapiliyor")
SEVERITIES = ("kritik", "yüksek", "orta", "düşük")

#: Önem derecesinin puanı: veri olmadığında sıralamayı bu belirler.
SEVERITY_POINTS: dict[str, float] = {"kritik": 40.0, "yüksek": 25.0, "orta": 12.0, "düşük": 5.0}
#: log10 başına puan: 10 satış → 1 basamak, 100 → 2 …
SALES_POINTS = 10.0
IMPRESSION_POINTS = 8.0
CLICK_POINTS = 12.0
COUNT_POINTS = 4.0

#: Toplama ağırdır (canlıda ilk tur ~5 dk, 2026-09-28): ekran hiçbir zaman toplamayı beklemez. Son liste veritabanında
#: saklanır (köprü yeniden başlasa da kalır) ve anında döner; bu yaştan eskiyse yenisi arka planda toplanır.
STALE_SECONDS = 30 * 60
CACHE_SECONDS = STALE_SECONDS  # eski ad: ekrandaki "şu kadar saniyede bir yenilenir" metni
#: Gece işi: öteki gece işlerinin (eşitleme, tarama, ölçüm) yazması için bekleme; sonra liste yeniden kurulur.
NIGHTLY_DELAY_S = 3 * 3600
#: Yazar güven puanı bunun altındaysa yazar iş listesine girer.
AUTHOR_TRUST_MIN = 70
#: Fırsat maddesi: sayfanın aramalarından tahmini ek tıklama en az bu kadarsa (0 tıklamalık iş anlamsız).
MIN_EST_CLICKS = 1
#: T-soft eşitlemesi bu kadar gündür başarıyla bitmediyse BT işi.
STALE_SYNC_DAYS = 3
#: Fırsat/yarışan maddelerinin ayrıntısında örnek olarak adı geçen arama sayısı (tamamı ilgili ekranda).
EXAMPLE_QUERIES = 3
#: Tek kaynağın hatası ekranda bu uzunlukta gösterilir.
ERROR_TEXT = 300
#: CSV/ekran: ürün sayfası adresi (ürün denetimi ekranında ürün açılır).
PRODUCT_LINK = "/seo-geo/urun-denetimi?urun={pid}"

SOURCES: dict[str, str] = {
    "oneri_onay": "Onay bekleyen öneriler",
    "oneri_yayin": "Onaylı, sitede bekleyen metinler",
    "yonlendirme": "Anasayfaya giden yönlendirmeler",
    "satistan_kalkan": "Satıştan kalkan kitaplar",
    "sema": "Şema denetimi",
    "teknik": "Teknik sağlık",
    "google_tarama": "Google taraması",
    "haklar": "CRM hakları",
    "crm_durum": "CRM yayın durumu",
    "takvim": "Sezon takvimi",
    "yorumlar": "Okur yorumları",
    "video": "Kitap videoları",
    "yazarlar": "Yazar sayfaları",
    "firsatlar": "Arama fırsatları",
    "yarisan": "Yarışan sayfalar",
    "yz_kaynaklari": "Yapay zekânın kaynakları",
    "geri_baglanti": "Gelen bağlantılar",
    "rehberler": "Rehber sayfaları",
    "izleme": "İzleme uyarıları",
    "baglantilar": "Bağlantılar ve eşitleme",
}

# ------------------------------------------------------------------------------------------------ tablolar
STATE = sa.Table(
    "semantic_seo_worklist_state", _md,  # iş maddesinin durumu; kaynak maddeyi ürettikçe açık kalır
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(24), primary_key=True),          # sha1(kaynak|ref)
    sa.Column("ref", sa.String(800), nullable=False),           # okunur anahtar: "kaynak:…"
    sa.Column("source", sa.String(24), nullable=False),
    sa.Column("owner", sa.String(12), nullable=False),
    sa.Column("title", sa.String(500), nullable=False),
    sa.Column("status", sa.String(12), nullable=False),         # yeni | yapiliyor | bitti | yoksay
    sa.Column("assignee", sa.String(120)),                      # serbest metin (AD adı)
    sa.Column("note", sa.String(1000)),
    sa.Column("open", sa.Boolean, nullable=False),              # kaynak hâlâ üretiyor mu
    sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
LOG = sa.Table(
    "semantic_seo_worklist_log", _md,  # durum değişikliği ve kendiliğinden kapanma geçmişi
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("key", sa.String(24), nullable=False, index=True),
    sa.Column("source", sa.String(24), nullable=False),
    sa.Column("owner", sa.String(12), nullable=False),
    sa.Column("title", sa.String(500), nullable=False),
    sa.Column("event", sa.String(16), nullable=False),          # kapandi | yeniden_acildi | durum
    sa.Column("status", sa.String(12)),
    sa.Column("assignee", sa.String(120)),
    sa.Column("note", sa.String(1000)),
    sa.Column("by_user", sa.String(120)),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
)
CACHE = sa.Table(
    "semantic_seo_worklist_cache", _md,  # son toplanan liste (kaynak maddeleri); durumlar STATE'te
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
)
EVENT_LABEL = {"kapandi": "Kendiliğinden kapandı", "yeniden_acildi": "Yeniden açıldı", "durum": "Durum değişti"}

_ready_lock = threading.Lock()
_ready: set[int] = set()


def ensure_tables(eng: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(eng) in _ready:
            return
        STATE.create(eng, checkfirst=True)
        LOG.create(eng, checkfirst=True)
        CACHE.create(eng, checkfirst=True)
        _ready.add(id(eng))


# ------------------------------------------------------------------------------------------------ saf işlevler
def _n(v: Any) -> str:
    """Tam sayı, Türkçe binlik ayırıcıyla."""
    return f"{int(round(float(v or 0))):,}".replace(",", ".")


def _p(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def _log_points(v: Optional[float], per_decade: float) -> float:
    return per_decade * math.log10(1.0 + float(v)) if v and v > 0 else 0.0


def impact_score(severity: str, *, sales: Optional[float] = None, impressions: Optional[float] = None,
                 clicks: Optional[float] = None, count: Optional[int] = None) -> tuple[float, str]:
    """(puan, gerekçe). Her bileşen gerekçede adıyla ve puanıyla yazılır."""
    sev = severity if severity in SEVERITY_POINTS else "orta"
    parts: list[tuple[str, float]] = [(f"önem {sev}", SEVERITY_POINTS[sev])]
    data = False
    if sales and sales > 0:
        parts.append((f"toplam satış {_n(sales)} adet", _log_points(sales, SALES_POINTS)))
        data = True
    if impressions and impressions > 0:
        parts.append((f"Google gösterimi {_n(impressions)} (28 gün)", _log_points(impressions, IMPRESSION_POINTS)))
        data = True
    if clicks and clicks > 0:
        parts.append((f"tahmini ek tıklama {_n(clicks)} (28 gün)", _log_points(clicks, CLICK_POINTS)))
        data = True
    if count and count > 1:
        parts.append((f"{_n(count)} kayıt", _log_points(count, COUNT_POINTS)))
    total = round(sum(p for _, p in parts), 1)
    basis = " + ".join(f"{label} ({_p(p)})" for label, p in parts) + f" = {_p(total)}"
    if not data:
        basis += " · satış ve arama verisi yok; sıra önem derecesine göre"
    return total, basis


def item_key(source: str, ref: str) -> str:
    return hashlib.sha1(f"{source}|{ref}".encode("utf-8")).hexdigest()[:24]


def make_item(source: str, ref: str, owner: str, title: str, detail: str, severity: str, link: str, *,
              product_id: Optional[str] = None, count: Optional[int] = None, sales: Optional[float] = None,
              impressions: Optional[float] = None, clicks: Optional[float] = None) -> dict[str, Any]:
    score, basis = impact_score(severity, sales=sales, impressions=impressions, clicks=clicks, count=count)
    return {"key": item_key(source, ref), "ref": f"{source}:{ref}"[:800], "source": source, "owner": owner,
            "title": title[:500], "detail": detail, "severity": severity if severity in SEVERITY_POINTS else "orta",
            "impact": score, "impactBasis": basis, "link": link, "productId": product_id, "count": count}


def dedupe(items: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aynı anahtar iki kez gelirse etkisi büyük olan kalır."""
    out: dict[str, dict[str, Any]] = {}
    for it in items:
        old = out.get(it["key"])
        if old is None or it["impact"] > old["impact"]:
            out[it["key"]] = it
    return out


def reconcile(existing: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]],
              ran: set[str]) -> list[tuple[str, str]]:
    """existing: anahtar → {source, open, status}. → [("new"|"reopen"|"close", anahtar)].
    Koşan kaynağın artık üretmediği açık madde kapanır; hata veren kaynağın maddesine dokunulmaz."""
    ops: list[tuple[str, str]] = []
    for k in current:
        row = existing.get(k)
        if row is None:
            ops.append(("new", k))
        elif not row.get("open"):
            ops.append(("reopen", k))
    for k, row in existing.items():
        if row.get("open") and k not in current and row.get("source") in ran:
            ops.append(("close", k))
    return ops


def merge(items: Iterable[dict[str, Any]], states: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Kaynak maddesi + kayıtlı durum. Kaydı olmayan madde "yeni"dir."""
    out = []
    for it in items:
        st = states.get(it["key"]) or {}
        status = st.get("status") or "yeni"
        out.append({**it, "sourceLabel": SOURCES.get(it["source"], it["source"]),
                    "ownerLabel": OWNERS.get(it["owner"], it["owner"]), "status": status,
                    "statusLabel": STATUSES.get(status, status), "assignee": st.get("assignee"), "note": st.get("note"),
                    "updatedBy": st.get("updated_by"), "updatedAt": iso(st.get("updated_at")),
                    "firstSeen": iso(st.get("first_seen"))})
    return out


def _status_ok(status: str, want: str) -> bool:
    if not want:
        return True
    if want == "acik":
        return status in OPEN_STATUSES
    return status in [s for s in want.split(",") if s]


def _fold(s: Any) -> str:
    # "İ".casefold() → "i" + birleşen nokta; nokta atılır ki "is" araması "İş"i bulsun.
    return str(s or "").casefold().replace("̇", "").translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))


def select(items: list[dict[str, Any]], owner: str = "", status: str = "", source: str = "",
           q: str = "") -> list[dict[str, Any]]:
    needle = _fold(q.strip())
    out = [i for i in items if (not owner or i["owner"] == owner) and (not source or i["source"] == source)
           and _status_ok(i["status"], status)
           and (not needle or needle in _fold(f"{i['title']} {i['detail']} {i.get('assignee') or ''}"))]
    return sorted(out, key=lambda i: (-i["impact"], i["title"], i["key"]))


def counts(items: list[dict[str, Any]], owner: str = "", status: str = "", source: str = "",
           q: str = "") -> dict[str, dict[str, int]]:
    """Her boyutun sayısı öteki süzgeçler uygulanmış olarak (sekme sayıları doğru olsun)."""
    return {"owner": _count(select(items, "", status, source, q), "owner"),
            "status": _count(select(items, owner, "", source, q), "status"),
            "source": _count(select(items, owner, status, "", q), "source")}


def _count(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in items:
        out[i[field]] = out.get(i[field], 0) + 1
    return out


def summary(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Sorumlu başına: açık (yeni + yapılıyor), yapılıyor, bitti, açıkların toplam etkisi."""
    out = {o: {"open": 0, "doing": 0, "done": 0, "impact": 0.0} for o in OWNERS}
    for i in items:
        s = out.setdefault(i["owner"], {"open": 0, "doing": 0, "done": 0, "impact": 0.0})
        if i["status"] in OPEN_STATUSES:
            s["open"] += 1
            s["impact"] = round(s["impact"] + i["impact"], 1)
        if i["status"] == "yapiliyor":
            s["doing"] += 1
        if i["status"] == "bitti":
            s["done"] += 1
    return out


# ------------------------------------------------------------------------------------------------ kaynak ortamı
def _num(v: Any) -> float:
    try:
        return float(str(v if v is not None else 0).replace(",", "."))
    except ValueError:
        return 0.0


def _ean(v: Any) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


class Env:
    """Kaynakların ortak, tembel yüklenen verisi: tek toplama turu boyunca bir kez okunur."""

    def __init__(self, seo, today: Optional[date] = None) -> None:
        self.seo = seo
        self.eng = seo.engine()
        self.tenant = seo.tenant()
        self.today = today or date.today()
        self._products: Optional[dict[str, dict[str, Any]]] = None
        self._gsc: Optional[dict[str, tuple[int, int]]] = None
        self._crm: Optional[dict[str, dict[str, Any]]] = None

    def has(self, table: sa.Table) -> bool:
        return sa.inspect(self.eng).has_table(table.name)

    def products(self) -> dict[str, dict[str, Any]]:
        """ürün → {name, active, sales, views, link, ean}. Satış T-soft `CountTotalSales` (paketteki SALES ifadesi)."""
        if self._products is not None:
            return self._products
        out: dict[str, dict[str, Any]] = {}
        with self.eng.connect() as c:
            if self.eng.dialect.name == "postgresql":
                from . import SALES, VIEWS

                data = sa.cast(PRODUCTS.c.data_json, sa.JSON)
                rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.active, SALES, VIEWS,
                                           data["SeoLink"].as_string(), data["Barcode"].as_string())
                                 .where(PRODUCTS.c.tenant_id == self.tenant)).all()
            else:  # sqlite (birim testi): JSON Python'da çözülür
                rows = []
                for pid, name, active, raw in c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.active,
                                                                  PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == self.tenant)):
                    p = loads(raw, {})
                    rows.append((pid, name, active, _num(p.get("CountTotalSales")), _num(p.get("StatViews")),
                                 p.get("SeoLink"), p.get("Barcode")))
        for pid, name, active, sales, views, link, barcode in rows:
            out[str(pid)] = {"name": name or str(pid), "active": bool(active), "sales": float(sales or 0),
                             "views": float(views or 0), "link": str(link or "").strip().strip("/") or None,
                             "ean": _ean(barcode)}
        self._products = out
        return out

    def gsc_paths(self) -> dict[str, tuple[int, int]]:
        """Search Console sayfa satırları: yol → (gösterim, tıklama), son 28 gün."""
        if self._gsc is None:
            from .sunset import gsc_by_path

            g = self.seo.gsc("pages")
            self._gsc = gsc_by_path((g or {}).get("rows") or [])
        return self._gsc

    def impressions_of(self, url_or_link: Any) -> int:
        from .sunset import path_of

        return self.gsc_paths().get(path_of(url_or_link), (0, 0))[0]

    def product_impressions(self, pid: str) -> int:
        p = self.products().get(str(pid))
        return self.impressions_of(p["link"]) if p and p["link"] else 0

    def crm(self) -> dict[str, dict[str, Any]]:
        """EAN → CRM kitap kartı özeti."""
        if self._crm is None:
            with self.eng.connect() as c:
                rows = c.execute(sa.select(CRM_BOOKS.c.ean, CRM_BOOKS.c.name, CRM_BOOKS.c.rights, CRM_BOOKS.c.status_flag,
                                           CRM_BOOKS.c.data_json).where(CRM_BOOKS.c.tenant_id == self.tenant)).all()
            self._crm = {str(e): {"name": n, "rights": r, "flag": f, "data": loads(d, {})} for e, n, r, f, d in rows}
        return self._crm

    def active_with_crm(self) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        crm = self.crm()
        return [(pid, p, crm[p["ean"]]) for pid, p in self.products().items() if p["active"] and p["ean"] in crm]


def _plink(pid: str) -> str:
    return PRODUCT_LINK.format(pid=pid)


def _sum_sales(env: Env, pids: Iterable[Any]) -> float:
    prods = env.products()
    return sum(prods.get(str(p), {}).get("sales", 0.0) for p in set(pids) if p)


# ------------------------------------------------------------------------------------------------ kaynaklar
def src_proposals_waiting(env: Env) -> list[dict[str, Any]]:
    """Onay bekleyen ZEKİ AI önerileri (ürün ve yazar/kategori/yayınevi sayfası)."""
    with env.eng.connect() as c:
        rows = c.execute(sa.select(PROPOSALS.c.id, PROPOSALS.c.product_id, PROPOSALS.c.score_before, PROPOSALS.c.score_after,
                                   PROPOSALS.c.created_at).where(PROPOSALS.c.tenant_id == env.tenant,
                                                                 PROPOSALS.c.status == "hazir")
                         .order_by(PROPOSALS.c.created_at.desc())).all()
    latest: dict[str, Any] = {}
    for r in rows:
        latest.setdefault(str(r[1]), r)
    prods, pages = env.products(), _page_names(env)
    out = []
    for pid, (_id, _pid, before, after, _at) in latest.items():
        score = f" (puan {before} → {after})" if before is not None and after is not None else ""
        if ":" in pid:
            name = pages.get(pid) or pid
            out.append(make_item("oneri_onay", f"hazir:{pid}", "seo", f"Sayfa önerisi onay bekliyor: {name}",
                                 f"ZEKİ AI'ın sayfa başlığı/açıklaması önerisi hazır{score}. Onaylanırsa metin T-soft "
                                 "panelinde elle girilir; sistem hiçbir yere göndermez.", "orta", "/seo-geo/sayfalar"))
            continue
        p = prods.get(pid) or {}
        out.append(make_item("oneri_onay", f"hazir:{pid}", "seo", f"Öneri onay bekliyor: {p.get('name') or pid}",
                             f"ZEKİ AI'ın SEO önerisi hazır{score}. Onaylanan metin CRM kitap kartına / T-soft paneline "
                             "elle girilir; sistem hiçbir yere göndermez.", "orta", _plink(pid), product_id=pid,
                             sales=p.get("sales"), impressions=env.product_impressions(pid)))
    return out


def _page_names(env: Env) -> dict[str, str]:
    """"model:12" → sayfa adı (T-soft bağlantı kaydının başlığından)."""
    from . import rules

    with env.eng.connect() as c:
        rows = c.execute(sa.select(LINKS.c.type, LINKS.c.table_id, LINKS.c.title, LINKS.c.link)
                         .where(LINKS.c.tenant_id == env.tenant)).all()
    return {f"{t}:{tid}": (rules.text_of(title).split("|")[0].strip() or link) for t, tid, title, link in rows if tid}


def src_proposals_approved(env: Env) -> list[dict[str, Any]]:
    """Onaylanan ama sitede henüz görünmeyen metinler: yayın günü bulunmamış (etki tablosunda satırı yok) ürün önerisi
    ya da T-soft bağlantı kaydında henüz aynısı görünmeyen sayfa önerisi. Ürün/sayfa başına en son onay esas alınır (eskisi yenisiyle geçersizdir)."""
    from . import impact

    impact.ensure_table(env.eng)
    with env.eng.connect() as c:
        rows = c.execute(sa.select(PROPOSALS.c.id, PROPOSALS.c.product_id, PROPOSALS.c.status, PROPOSALS.c.fields_json,
                                   PROPOSALS.c.decided_at).where(
            PROPOSALS.c.tenant_id == env.tenant, PROPOSALS.c.status == "onaylandi")
            .order_by(PROPOSALS.c.decided_at.desc().nullslast())).all()
        seen_ids = {pid for (pid,) in c.execute(sa.select(impact.IMPACT.c.proposal_id).where(
            impact.IMPACT.c.tenant_id == env.tenant))}
        links = {f"{t}:{tid}": (title, desc) for t, tid, title, desc in c.execute(
            sa.select(LINKS.c.type, LINKS.c.table_id, LINKS.c.title, LINKS.c.description)
            .where(LINKS.c.tenant_id == env.tenant)) if tid}
    latest: dict[str, Any] = {}
    for r in rows:
        latest.setdefault(str(r[1]), r)
    prods, pages = env.products(), _page_names(env)
    out = []
    for pid, (prop_id, _pid, _status, fields_json, decided_at) in latest.items():
        fields = loads(fields_json, {})
        day = f" ({decided_at:%d.%m.%Y})" if isinstance(decided_at, datetime) else ""
        if ":" in pid:
            cur = links.get(pid)
            if cur and all(impact.same(k, v, fields.get(k)) for k, v in (("SeoTitle", cur[0]), ("SeoDescription", cur[1]))
                           if fields.get(k)):
                continue
            out.append(make_item("oneri_yayin", f"onayli:{prop_id}", "icerik",
                                 f"Onaylanan sayfa metni sitede yok: {pages.get(pid) or pid}",
                                 f"Onaylandı{day}; T-soft panelinde sayfanın başlık/açıklama/tanıtım alanlarına elle "
                                 "girilmeli. Sitede görünmesi gece eşitlemesinde denetlenir.", "yüksek", "/seo-geo/sayfalar"))
            continue
        if prop_id in seen_ids:
            continue
        p = prods.get(pid) or {}
        if p and not p.get("active"):
            continue
        out.append(make_item("oneri_yayin", f"onayli:{prop_id}", "icerik",
                             f"Onaylanan metin sitede yok: {p.get('name') or pid}",
                             f"Onaylandı{day}; SEO başlığı/açıklaması CRM kitap kartına ya da T-soft paneline elle "
                             "girilmeli. Sitede ilk görüldüğü gün etki ölçümü başlar.", "yüksek", _plink(pid),
                             product_id=pid, sales=p.get("sales"), impressions=env.product_impressions(pid)))
    return out


CONFIDENCE_SEVERITY = {"kesin": "yüksek", "yüksek": "orta", "orta": "düşük", "yok": "düşük"}


def src_redirects(env: Env) -> list[dict[str, Any]]:
    """Anasayfaya giden 301'ler: bekleyenler güven düzeyine göre onaya (SEO), onaylı ve hâlâ anasayfaya gidenler
    T-soft paneline (son eşitlemede hâlâ anasayfaya gidiyorsa satır o eşitlemenin zamanını taşır)."""
    with env.eng.connect() as c:
        rows = c.execute(sa.select(REDIRECTS.c.link, REDIRECTS.c.confidence, REDIRECTS.c.status, REDIRECTS.c.synced_at)
                         .where(REDIRECTS.c.tenant_id == env.tenant)).all()
    if not rows:
        return []
    last = max(r[3] for r in rows)
    pending: dict[str, list[str]] = {}
    approved: list[str] = []
    for link, conf, status, synced in rows:
        if status == "bekliyor":
            pending.setdefault(conf, []).append(link)
        elif status == "onaylandi" and synced == last:
            approved.append(link)
    out = []
    for conf, links in pending.items():
        out.append(make_item("yonlendirme", f"bekliyor:{conf}", "seo",
                             f"{_n(len(links))} yönlendirme önerisi onay bekliyor (güven: {conf})",
                             "Anasayfaya giden eski adresler için hedef önerisi hazır; onaylananlar CSV ile T-soft "
                             "paneline girilir.", CONFIDENCE_SEVERITY.get(conf, "düşük"), "/seo-geo/yonlendirmeler",
                             count=len(links), impressions=sum(env.impressions_of(l) for l in links)))
    if approved:
        out.append(make_item("yonlendirme", "onayli", "tsoft",
                             f"{_n(len(approved))} onaylı yönlendirme T-soft paneline girilmeli",
                             "Onaylanan hedefler son eşitlemede hâlâ anasayfaya gidiyor. Yönlendirmeler ekranından CSV "
                             "indirilip panelde girilmeli; girildikçe liste kendiliğinden kısalır.", "yüksek",
                             "/seo-geo/yonlendirmeler", count=len(approved),
                             impressions=sum(env.impressions_of(l) for l in approved)))
    return out


def src_sunset(env: Env) -> list[dict[str, Any]]:
    from .sunset import ACTIONS, REASON_LABEL, SUNSET, _ensure

    _ensure(env.eng)
    with env.eng.connect() as c:
        rows = c.execute(sa.select(SUNSET).where(SUNSET.c.tenant_id == env.tenant)).mappings().all()
    if not rows:
        return []
    last = max(r["synced_at"] for r in rows)
    prods = env.products()
    out = []
    for r in rows:
        name = r["name"] or r["link"]
        sales = (prods.get(str(r["product_id"])) or {}).get("sales")
        reason = REASON_LABEL.get(r["reason"], r["reason"])
        if r["status"] == "bekliyor":
            out.append(make_item("satistan_kalkan", f"bekliyor:{r['id']}", "seo", f"Satıştan kalkan sayfa kararı: {name}",
                                 f"{reason}. Öneri: {ACTIONS.get(r['action'], r['action'])}. {r['why'] or ''}".strip(),
                                 "orta", "/seo-geo/satistan-kalkan", product_id=r["product_id"], sales=sales,
                                 impressions=r["impressions"]))
        elif r["status"] == "onaylandi" and r["synced_at"] == last:
            act = ACTIONS.get(r["chosen_action"] or r["action"], r["chosen_action"])
            tgt = f" → /{r['chosen_target']}" if r["chosen_target"] else ""
            out.append(make_item("satistan_kalkan", f"onayli:{r['id']}", "tsoft", f"Satıştan kalkan sayfa: {name}",
                                 f"Onaylanan karar T-soft panelinde uygulanmalı: {act}{tgt} (/{r['link']}). {reason}.",
                                 "yüksek" if r["impressions"] else "orta", "/seo-geo/satistan-kalkan",
                                 product_id=r["product_id"], sales=sales, impressions=r["impressions"]))
    return out


def _issue_groups(rows: Iterable[tuple[Any, Any, Any]]) -> dict[str, list[tuple[Any, Any]]]:
    """(ürün, adres, ",a,b,") satırları → sorun → [(ürün, adres)]."""
    out: dict[str, list[tuple[Any, Any]]] = {}
    for pid, url, issues in rows:
        for k in filter(None, str(issues or "").split(",")):
            out.setdefault(k, []).append((pid, url))
    return out


def src_schema(env: Env) -> list[dict[str, Any]]:
    """Şema denetimi: sorun türü başına tek madde (T-soft teması düzeltir)."""
    from .schema import CHECKS

    with env.eng.connect() as c:
        rows = c.execute(sa.select(SCHEMA.c.product_id, SCHEMA.c.url, SCHEMA.c.issues).where(
            SCHEMA.c.tenant_id == env.tenant, SCHEMA.c.product_id != "_org")).all()
    prods = env.products()
    rows = [r for r in rows if (prods.get(str(r[0])) or {}).get("active")]
    out = []
    for k, hits in _issue_groups(rows).items():
        sev, title, why = CHECKS.get(k, ("orta", k, ""))
        out.append(make_item("sema", k, "tsoft", f"Şema: {title} — {_n(len(hits))} kitap sayfası",
                             f"{why} Tema düzeltmesidir; Şema ekranındaki tema isteği belgesi T-soft'a/ajansa iletilir.",
                             sev, "/seo-geo/sema", count=len(hits), sales=_sum_sales(env, (p for p, _ in hits)),
                             impressions=sum(env.impressions_of(u) for _, u in hits)))
    return out


def src_tech(env: Env) -> list[dict[str, Any]]:
    """Teknik tarama: sorun türü başına tek madde (404, canonical, noindex, zincir…)."""
    from .tech import CHECKS, TECH

    if not env.has(TECH):
        return []
    with env.eng.connect() as c:
        rows = c.execute(sa.select(TECH.c.product_id, TECH.c.url, TECH.c.issues).where(
            TECH.c.tenant_id == env.tenant, TECH.c.issues != ",,")).all()
    out = []
    for k, hits in _issue_groups(rows).items():
        sev, title, why = CHECKS.get(k, ("orta", k, ""))
        out.append(make_item("teknik", k, "tsoft", f"Teknik: {title} — {_n(len(hits))} sayfa", why, sev,
                             "/seo-geo/teknik", count=len(hits), sales=_sum_sales(env, (p for p, _ in hits)),
                             impressions=sum(env.impressions_of(u) for _, u in hits)))
    return out


#: Google'ın dizine almadığı sınıflar → önem. "redirect", "alternate" beklenen durumdur; "error" bizim denetim hatamızdır.
CRAWL_SEVERITY = {"noindex": "kritik", "robots_blocked": "kritik", "not_found": "kritik", "soft_404": "yüksek",
                  "fetch_error": "yüksek", "crawled_not_indexed": "yüksek", "discovered_not_crawled": "orta",
                  "unknown": "orta", "duplicate": "orta", "other": "orta"}


def src_crawlbot(env: Env) -> list[dict[str, Any]]:
    from .crawlbot import INSPECT, STATUS_LABEL, row_status

    if not env.has(INSPECT):
        return []
    with env.eng.connect() as c:
        rows = [dict(r) for r in c.execute(sa.select(INSPECT.c.url, INSPECT.c.product_id, INSPECT.c.status,
                                                     INSPECT.c.canonical_mismatch, INSPECT.c.error)
                                           .where(INSPECT.c.tenant_id == env.tenant)).mappings()]
    groups: dict[str, list[dict[str, Any]]] = {}
    mismatch = []
    for r in rows:
        st = row_status(r)
        if st in CRAWL_SEVERITY:
            groups.setdefault(st, []).append(r)
        if not r.get("error") and r.get("canonical_mismatch"):
            mismatch.append(r)
    out = []
    for st, hits in groups.items():
        label = STATUS_LABEL.get(st, (st, ""))[0]
        out.append(make_item("google_tarama", st, "tsoft", f"Google: {label} — {_n(len(hits))} adres",
                             "Google URL Denetimi sonucu. Sayfaların listesi ve Google'ın gerekçesi Google taraması "
                             "ekranında; düzeltme sitede (tema, robots, yönlendirme ya da içerik) yapılır.",
                             CRAWL_SEVERITY[st], "/seo-geo/google-taramasi", count=len(hits),
                             sales=_sum_sales(env, (h.get("product_id") for h in hits)),
                             impressions=sum(env.impressions_of(h["url"]) for h in hits)))
    if mismatch:
        out.append(make_item("google_tarama", "canonical", "tsoft",
                             f"Google başka canonical seçti — {_n(len(mismatch))} adres",
                             "Sayfanın gösterdiği canonical ile Google'ın seçtiği farklı; sayfa kendi adıyla dizine girmiyor.",
                             "yüksek", "/seo-geo/google-taramasi", count=len(mismatch),
                             sales=_sum_sales(env, (h.get("product_id") for h in mismatch)),
                             impressions=sum(env.impressions_of(h["url"]) for h in mismatch)))
    return out


RIGHTS_ITEMS = {"eksik": ("yüksek", "Hak eksik"), "yok": ("orta", "Sözleşme kaydı yok"), "incele": ("orta", "Hak incelenmeli")}
FLAG_TEXT = {"bizim_degil": "artık bizim ürünümüz değil", "cekildi": "satıştan çekildi", "geri_istendi": "geri istendi",
             "devredildi": "hakları devredildi", "iptal": "iptal edilmiş"}


def src_rights(env: Env) -> list[dict[str, Any]]:
    """Satıştaki kitapta internette gösterim hakkı eksik / belirsiz: telif birimi bakar (ön süzgeç, kesin söz onların)."""
    out = []
    for pid, p, b in env.active_with_crm():
        if b["rights"] not in RIGHTS_ITEMS:
            continue
        sev, label = RIGHTS_ITEMS[b["rights"]]
        why = (b["data"] or {}).get("rightsWhy") or ""
        out.append(make_item("haklar", f"{b['rights']}:{pid}", "telif", f"{label}: {p['name']}",
                             f"{why} Kitaptan alıntı, önizleme ve tanıtım metni hak netleşmeden kullanılmaz.".strip(),
                             sev, f"/seo-geo/crm-haklar?suzgec={b['rights']}&urun={pid}", product_id=pid,
                             sales=p["sales"], impressions=env.product_impressions(pid)))
    return out


def src_crm_status(env: Env) -> list[dict[str, Any]]:
    """CRM yayın durumu satıştan kalkmayı söylüyor ama T-soft'ta ürün aktif."""
    out = []
    for pid, p, b in env.active_with_crm():
        if not b["flag"]:
            continue
        out.append(make_item("crm_durum", f"{b['flag']}:{pid}", "yayin",
                             f"CRM'de {FLAG_TEXT.get(b['flag'], b['flag'])}, sitede satışta: {p['name']}",
                             "Ya ürün sitede satıştan kalkmalı ya da CRM yayın durumu düzeltilmeli. Karar yayın biriminin; "
                             "sayfanın ne olacağı Satıştan kalkan kitaplar ekranında.", "yüksek",
                             f"/seo-geo/crm-haklar?suzgec=durum&urun={pid}", product_id=pid, sales=p["sales"],
                             impressions=env.product_impressions(pid)))
    return out


def src_seasons(env: Env) -> list[dict[str, Any]]:
    """Sezon takvimi: hazırlık penceresindeki ya da süren özel gün için düzeltilecek kitaplar / eksik rehber."""
    from . import seasons

    if not env.has(seasons.DAYS):
        return []
    cal = seasons.calendar(env.seo, seasons.DEFAULT_WEEKS, env.today)
    out = []
    for a in cal.get("actions") or []:
        started = bool(a.get("start")) and date.fromisoformat(a["start"]) <= env.today
        when = f"{date.fromisoformat(a['start']):%d.%m.%Y}" if a.get("start") else "tarih belirsiz"
        if a["kind"] == "duzelt":
            books = a.get("books") or []
            names = ", ".join(b["name"] for b in books[:EXAMPLE_QUERIES]) + (" …" if len(books) > EXAMPLE_QUERIES else "")
            out.append(make_item("takvim", f"duzelt:{a['dayId']}:{a.get('start')}", "icerik",
                                 f"{a['dayName']} ({when}) için {_n(len(books))} kitap sayfası düzeltilmeli",
                                 f"Günün aramalarında çıkacak kitapların SEO puanı düşük ya da kritik sorunu var: {names}.",
                                 "kritik" if started else "yüksek", "/seo-geo/takvim", count=len(books),
                                 sales=_sum_sales(env, (b["id"] for b in books))))
        elif a["kind"] == "rehber":
            out.append(make_item("takvim", f"rehber:{a['dayId']}:{a.get('start')}", "icerik",
                                 f"{a['dayName']} ({when}) için rehber/liste sayfası yok",
                                 "Günün aramalarına cevap veren bir rehber sayfası taslağı Rehberler ekranında istenebilir.",
                                 "yüksek" if started else "orta", "/seo-geo/takvim"))
    return out


def src_reviews(env: Env) -> list[dict[str, Any]]:
    """Çok satan (≥ reviews.PRIORITY_SALES adet) ama hiç okur yorumu olmayan kitaplar: tek madde (yorum isteği süreci)."""
    from . import reviews

    if env.eng.dialect.name != "postgresql":  # ürün satırları paketteki SALES ifadesiyle (Postgres JSON)
        return []
    rows, _ = reviews.Reviews(env.seo).rows()
    zero = [r for r in rows if not r["count"] and r["sales"] >= reviews.PRIORITY_SALES]
    if not zero:
        return []
    return [make_item("yorumlar", "yorumsuz", "yayin",
                      f"{_n(len(zero))} çok satan kitapta hiç okur yorumu yok",
                      f"En az {_n(reviews.PRIORITY_SALES)} adet satmış ama sitede yorumu olmayan kitaplar. Satın alma "
                      "sonrası yorum isteği (e-posta/SMS) site ve CRM sürecidir; bu sistem hiçbir şey göndermez.",
                      "orta", "/seo-geo/yorumlar", count=len(zero), sales=sum(r["sales"] for r in zero))]


def src_video(env: Env) -> list[dict[str, Any]]:
    """CRM'de videosu olan satıştaki kitaplar: sayfada VideoObject şeması yok (tema) ya da bağlantı geçersiz (CRM)."""
    from .video import schema_state, youtube_id

    with env.eng.connect() as c:
        schema = {str(p): (t, at) for p, t, at in c.execute(sa.select(SCHEMA.c.product_id, SCHEMA.c.types_json,
                                                                         SCHEMA.c.checked_at)
                                                            .where(SCHEMA.c.tenant_id == env.tenant))}
    missing, invalid = [], []
    for pid, p, b in env.active_with_crm():
        v = (b["data"] or {}).get("video")
        if not v:
            continue
        if not youtube_id(v):
            invalid.append((pid, p))
            continue
        types, at = schema.get(pid, (None, None))
        if schema_state(loads(types, []), at is not None) != "var":
            missing.append((pid, p))
    out = []
    if missing:
        out.append(make_item("video", "sema_yok", "tsoft", f"{_n(len(missing))} kitap videosunun sayfada şeması yok",
                             "CRM'de YouTube videosu olan kitabın sayfasında VideoObject şeması görünmüyor. Video ekranındaki "
                             "tema isteği ve video site haritası site yöneticisine iletilir.", "orta", "/seo-geo/video",
                             count=len(missing), sales=sum(p["sales"] for _, p in missing)))
    if invalid:
        out.append(make_item("video", "gecersiz", "icerik", f"{_n(len(invalid))} kitapta CRM video bağlantısı geçersiz",
                             "CRM kitap kartındaki video alanı bir YouTube adresi değil; CRM'de düzeltilmeli.", "düşük",
                             "/seo-geo/video", count=len(invalid), sales=sum(p["sales"] for _, p in invalid)))
    return out


def src_authors(env: Env) -> list[dict[str, Any]]:
    """Yazar güven sinyalleri: sayfası olmayan yazar (T-soft) ve puanı düşük yazarın içerik eksikleri (editör)."""
    from . import authors

    if env.eng.dialect.name != "postgresql":  # yazar hesabı Postgres JSON ifadeleriyle
        return []
    rows, _ = authors.Authors(env.seo).rows()
    out = []
    for a in rows:
        if a["score"] is None or a["score"] >= AUTHOR_TRUST_MIN:
            continue
        missing = {i["id"]: i for i in a["checks"] if i["state"] in ("eksik", "kismi")}
        if "page" in missing:
            out.append(make_item("yazarlar", f"sayfa:{a['key']}", "tsoft", f"Yazar sayfası yok: {a['name']}",
                                 missing["page"]["action"] or "", "yüksek", "/seo-geo/yazar-sayfalari", sales=a["sales"]))
        content = [i for k, i in missing.items() if k not in ("page", "sameas") and i["action"]]
        if content:
            out.append(make_item("yazarlar", f"icerik:{a['key']}", "icerik",
                                 f"Yazar güven sinyalleri eksik: {a['name']} (puan {a['score']})",
                                 " ".join(f"{i['title']}: {i['action']}" for i in content), "orta",
                                 "/seo-geo/yazar-sayfalari", sales=a["sales"]))
    return out


def src_opportunities(env: Env) -> list[dict[str, Any]]:
    """Search Console fırsatları, sayfa başına: 4–15. sıradaki aramalar (içerik güçlendirme) ve sırası iyi ama az
    tıklanan aramalar (başlık/meta yeniden yazımı). Marka aramaları ("timaş") hariç: onlar zaten bizim."""
    from .opportunities import computed, path_key

    data = computed(env.seo)
    by_path = {path_key(p["link"]): (pid, p) for pid, p in env.products().items() if p["link"]}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in data.get("items") or []:
        if it.get("brand"):
            continue
        target = path_key(it.get("page")) if it.get("page") else f"?{it['query']}"
        for kind in it["kinds"]:
            groups.setdefault((kind, target or "/"), []).append(it)
    out = []
    for (kind, target), hits in groups.items():
        field = "extraClicks" if kind == "yakin" else "lostClicks"
        est = sum(h.get(field) or 0 for h in hits)
        if est < MIN_EST_CLICKS:
            continue
        hits.sort(key=lambda h: -h["impressions"])
        pid, p = by_path.get(target, (None, None))
        where = p["name"] if p else (hits[0].get("page") or hits[0]["query"])
        examples = ", ".join(f"“{h['query']}”" for h in hits[:EXAMPLE_QUERIES])
        link = _plink(pid) if pid else "/seo-geo/firsatlar"
        if kind == "yakin":
            title = f"İlk üçe yakın: {where} — {_n(len(hits))} arama 4–15. sırada"
            detail = f"Başlık, açıklama ve içerik bu aramalara göre güçlendirilmeli. En çok gösterilen: {examples}."
        else:
            title = f"Az tıklanıyor: {where} — {_n(len(hits))} arama"
            detail = (f"Sıra iyi ama tıklama oranı aynı sıradaki aramaların yarısından az; başlık ve meta açıklama "
                      f"yeniden yazılmalı. En çok gösterilen: {examples}.")
        out.append(make_item("firsatlar", f"{kind}:{target}", "icerik", title, detail, "orta", link, product_id=pid,
                             sales=p["sales"] if p else None, impressions=sum(h["impressions"] for h in hits),
                             clicks=est))
    return out


def src_cannibal(env: Env) -> list[dict[str, Any]]:
    """Zararlı yarışan sayfalar (marka dışı): aynı aramada birden çok adresimiz, hiçbiri öne çıkamıyor."""
    from .cannibal import computed

    out = []
    for g in computed(env.seo).get("items") or []:
        if g.get("severity") != "zararli" or g.get("brand"):
            continue
        actions = []
        for pr in g.get("pairs") or []:
            a = pr.get("action")
            if a and a not in actions:
                actions.append(a)
        pids = [(pg.get("product") or {}).get("id") for pg in g.get("pages") or [] if isinstance(pg, dict)]
        out.append(make_item("yarisan", g["query"], "icerik",
                             f"Yarışan sayfalar: “{g['query']}” — {_n(len(g.get('pages') or []))} adres",
                             " ".join(actions) or "Adreslerden biri asıl seçilmeli; öteki ayrıştırılmalı ya da asıla bağlanmalı.",
                             "yüksek", "/seo-geo/yarisan", sales=_sum_sales(env, pids) or None,
                             impressions=g.get("impressions")))
    return out


def src_ai_sources(env: Env) -> list[dict[str, Any]]:
    """Yapay zekâ cevaplarında sık kaynak gösterilen ama Timaş'ı anmayan siteler: tanıtım/iletişim hedefi."""
    from .ai_sources import ACTIONS, TYPES, computed

    out = []
    for d in (computed(env.seo, None).get("domains") or {}).values():
        if not d.get("target"):
            continue
        share = d.get("mentionShare") or 0
        out.append(make_item("yz_kaynaklari", d["domain"], "seo", f"Tanıtım hedefi: {d['domain']} ({TYPES.get(d['type'], d['type'])})",
                             f"{ACTIONS.get(d['type'], '')} {_n(d['answers'])} cevapta, {_n(d['questionCount'])} ayrı soruda "
                             f"kaynak gösterildi; bu cevapların %{_n(share * 100)}'inde Timaş anıldı.".strip(),
                             "orta", "/seo-geo/kaynaklar", count=d["answers"]))
    return out


def src_backlinks(env: Env) -> list[dict[str, Any]]:
    """Son iki okuma arasında kaybolan gelen bağlantılar, kaynak alan adı başına (iletişim işi)."""
    from .backlinks import Backlinks, diff, domain_of

    bl = Backlinks(env.seo)
    snaps = bl.snaps()
    if len(snaps) < 2:
        return []
    counts, pairs, _ = bl.load(snaps[0]["id"])
    pcounts, ppairs, _ = bl.load(snaps[1]["id"])
    both = {r["target"] for r in counts if r["detailed"]} & {r["target"] for r in pcounts if r["detailed"]}
    lost: dict[str, list[tuple[str, str]]] = {}
    for t, s in diff(ppairs, pairs, both)["lost"]:
        lost.setdefault(domain_of(s), []).append((t, s))
    out = []
    for dom, links in lost.items():
        out.append(make_item("geri_baglanti", f"kayip:{dom}:{snaps[0]['id']}", "seo",
                             f"Kaybolan bağlantı: {dom} — {_n(len(links))} bağlantı",
                             "Bu site önceki okumada sayfalarımıza bağlantı veriyordu, son okumada vermiyor. Sayfa "
                             "kaldırılmış ya da bağlantı silinmiş olabilir; site sahibiyle iletişime geçilebilir.",
                             "orta", "/seo-geo/geri-baglantilar", count=len(links),
                             impressions=sum(env.impressions_of(t) for t, _ in links)))
    return out


def src_guides(env: Env) -> list[dict[str, Any]]:
    from .guides import GUIDES

    if not env.has(GUIDES):
        return []
    with env.eng.connect() as c:
        rows = c.execute(sa.select(GUIDES.c.id, GUIDES.c.title, GUIDES.c.status, GUIDES.c.topic_json).where(
            GUIDES.c.tenant_id == env.tenant, GUIDES.c.status.in_(("hazir", "onaylandi")))).all()
    out = []
    for gid, title, status, topic in rows:
        t = loads(topic, {})
        impr = t.get("impressions")
        name = title or t.get("title") or gid
        if status == "hazir":
            out.append(make_item("rehberler", f"hazir:{gid}", "seo", f"Rehber taslağı onay bekliyor: {name}",
                                 "ZEKİ AI'ın rehber/liste sayfası taslağı hazır; gerçeklik denetimiyle birlikte okunup "
                                 "onaylanmalı ya da reddedilmeli.", "orta", f"/seo-geo/rehberler?taslak={gid}",
                                 impressions=impr))
        else:
            out.append(make_item("rehberler", f"onayli:{gid}", "icerik", f"Onaylanan rehber sitede yayımlanmalı: {name}",
                                 "Onaylanan sayfanın HTML'i Rehberler ekranından indirilip T-soft'ta yeni sayfa olarak "
                                 "açılmalı; sistem hiçbir yere göndermez.", "yüksek", f"/seo-geo/rehberler?taslak={gid}",
                                 impressions=impr))
    return out


#: İzleme uyarısının türü → sorumlu. "crm" ve "tech" kendi kaynaklarında (CRM yayın durumu, Teknik) zaten var.
WATCH_OWNER = {"gsc": "seo", "geo": "seo", "sitemap": "tsoft", "robots": "tsoft", "speed": "tsoft"}
WATCH_SKIP = ("crm", "tech")


def src_watch(env: Env) -> list[dict[str, Any]]:
    from .watch import EVENTS

    if not env.has(EVENTS):
        return []
    with env.eng.connect() as c:
        rows = c.execute(sa.select(EVENTS.c.id, EVENTS.c.kind, EVENTS.c.severity, EVENTS.c.title, EVENTS.c.detail,
                                   EVENTS.c.link).where(EVENTS.c.tenant_id == env.tenant,
                                                        EVENTS.c.resolved_at.is_(None))).all()
    return [make_item("izleme", eid, WATCH_OWNER.get(kind, "seo"), title, detail or "", sev, link or "/seo-geo/izleme")
            for eid, kind, sev, title, detail, link in rows if kind not in WATCH_SKIP]


def src_connections(env: Env) -> list[dict[str, Any]]:
    """Kurulum eksikleri ve duran gece eşitlemesi: Timaş BT."""
    import os

    from . import connections, crm

    out = []
    if not connections.tsoft.configured():
        out.append(make_item("baglantilar", "tsoft", "bt", "T-soft okuma bağlantısı tanımlı değil",
                             "Ürünler okunamıyor; bütün denetimler eski veriyle kalır. Yönetim → SEO & GEO'da yalnız "
                             "okuma yetkili T-soft kullanıcısı tanımlanmalı.", "kritik", "/seo-geo/baglantilar"))
    if not connections.service_account_email():
        out.append(make_item("baglantilar", "google", "bt", "Search Console hizmet hesabı tanımlı değil",
                             "Arama verisi okunamıyor; etki puanlarında gösterim ve tıklama yok. Hizmet hesabı "
                             "Search Console mülküne okuyucu olarak eklenmeli.", "yüksek", "/seo-geo/baglantilar"))
    if not env.seo.conf("CRM_SCHEMA") or not crm.CONNECTION_FILE or not os.path.exists(crm.CONNECTION_FILE):
        out.append(make_item("baglantilar", "crm", "bt", "CRM okuma bağlantısı tanımlı değil",
                             "Hak ve yayın durumu okunamıyor. CRM için yalnız okuma yetkili bağlantı tanımlanmalı.",
                             "yüksek", "/seo-geo/baglantilar"))
    with env.eng.connect() as c:
        last = c.execute(sa.select(sa.func.max(RUNS.c.finished_at)).where(
            RUNS.c.tenant_id == env.tenant, RUNS.c.kind == "tsoft", RUNS.c.error.is_(None),
            RUNS.c.finished_at.isnot(None))).scalar()
    if connections.tsoft.configured():
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is None or now() - last > timedelta(days=STALE_SYNC_DAYS):
            when = f"{last:%d.%m.%Y}" if last else "hiç"
            out.append(make_item("baglantilar", "eslesme", "bt",
                                 f"T-soft eşitlemesi {STALE_SYNC_DAYS} gündür başarıyla bitmedi (son: {when})",
                                 "Gece zamanlayıcısı ve T-soft erişimi denetlenmeli; ekranlar eski veriyi gösteriyor.",
                                 "yüksek", "/seo-geo/baglantilar"))
    return out


COLLECTORS: list[tuple[str, Callable[[Env], list[dict[str, Any]]]]] = [
    ("oneri_onay", src_proposals_waiting),
    ("oneri_yayin", src_proposals_approved),
    ("yonlendirme", src_redirects),
    ("satistan_kalkan", src_sunset),
    ("sema", src_schema),
    ("teknik", src_tech),
    ("google_tarama", src_crawlbot),
    ("haklar", src_rights),
    ("crm_durum", src_crm_status),
    ("takvim", src_seasons),
    ("yorumlar", src_reviews),
    ("video", src_video),
    ("yazarlar", src_authors),
    ("firsatlar", src_opportunities),
    ("yarisan", src_cannibal),
    ("yz_kaynaklari", src_ai_sources),
    ("geri_baglanti", src_backlinks),
    ("rehberler", src_guides),
    ("izleme", src_watch),
    ("baglantilar", src_connections),
]


def collect(env: Env, collectors: Optional[list[tuple[str, Callable[[Env], list[dict[str, Any]]]]]] = None
            ) -> tuple[dict[str, dict[str, Any]], set[str], dict[str, str]]:
    """→ (anahtar → madde, koşan kaynaklar, hata veren kaynak → ileti). Bir kaynak düşerse ötekiler sürer."""
    items: list[dict[str, Any]] = []
    ran: set[str] = set()
    errors: dict[str, str] = {}
    for name, fn in collectors if collectors is not None else COLLECTORS:
        try:
            got = fn(env)
            items += got
            ran.add(name)
        except Exception as e:  # noqa: BLE001 — bir kaynağın hatası listeyi düşürmez; maddeleri kapanmaz
            log.warning("seo worklist source %s failed: %s", name, e)
            errors[name] = str(e)[:ERROR_TEXT]
    return dedupe(items), ran, errors


# ------------------------------------------------------------------------------------------------ durum kaydı
def load_states(eng: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    with eng.connect() as c:
        return {r["key"]: dict(r) for r in c.execute(sa.select(STATE).where(STATE.c.tenant_id == tenant)).mappings()}


def _log_row(tenant: str, st: dict[str, Any], event: str, at: datetime, by: Optional[str] = None,
             closed: bool = False) -> dict[str, Any]:
    return dict(id=uuid.uuid4().hex, tenant_id=tenant, key=st["key"], source=st["source"], owner=st["owner"],
                title=st["title"][:500], event=event, status=st.get("status"), assignee=st.get("assignee"),
                note=st.get("note"), by_user=by, at=at, closed_at=at if closed else None)


def sync_states(eng: sa.engine.Engine, tenant: str, current: dict[str, dict[str, Any]], ran: set[str],
                at: Optional[datetime] = None) -> dict[str, int]:
    """Kaynakların son hâlini durum tablosuna işler: yeni madde kaydı, kendiliğinden kapanma, yeniden açılma."""
    ensure_tables(eng)
    at = at or now()
    existing = load_states(eng, tenant)
    ops = reconcile(existing, current, ran)
    n = {"new": 0, "reopen": 0, "close": 0}
    new_rows, logs = [], []
    with eng.begin() as c:
        for op, k in ops:
            n[op] += 1
            if op == "new":
                it = current[k]
                new_rows.append(dict(tenant_id=tenant, key=k, ref=it["ref"][:800], source=it["source"], owner=it["owner"],
                                     title=it["title"][:500], status="yeni", open=True, first_seen=at))
            elif op == "reopen":
                it, st = current[k], existing[k]
                # Kendiliğinden kapanıp geri gelen iş bitmemiştir: "bitti" yeniden "yeni" olur; yok sayılan öyle kalır.
                status = "yeni" if st.get("status") == "bitti" else st.get("status")
                c.execute(STATE.update().where(STATE.c.tenant_id == tenant, STATE.c.key == k).values(
                    open=True, closed_at=None, status=status, title=it["title"][:500], owner=it["owner"]))
                logs.append(_log_row(tenant, {**st, "status": status, "title": it["title"]}, "yeniden_acildi", at))
            else:
                st = existing[k]
                c.execute(STATE.update().where(STATE.c.tenant_id == tenant, STATE.c.key == k).values(open=False, closed_at=at))
                logs.append(_log_row(tenant, st, "kapandi", at, closed=True))
        for i in range(0, len(new_rows), 1000):
            c.execute(STATE.insert(), new_rows[i:i + 1000])
        for i in range(0, len(logs), 1000):
            c.execute(LOG.insert(), logs[i:i + 1000])
    return n


def set_status(eng: sa.engine.Engine, tenant: str, key: str, status: str, assignee: Optional[str], note: Optional[str],
               user: str, at: Optional[datetime] = None) -> dict[str, Any]:
    if status not in STATUSES:
        raise _err(422, "Bilinmeyen durum.")
    ensure_tables(eng)
    at = at or now()
    with eng.begin() as c:
        st = c.execute(sa.select(STATE).where(STATE.c.tenant_id == tenant, STATE.c.key == key)).mappings().first()
        if not st:
            raise _err(404, "İş maddesi bulunamadı; liste yenilenmiş olabilir.")
        vals = dict(status=status, assignee=(assignee or "").strip()[:120] or None, note=(note or "").strip()[:1000] or None,
                    updated_by=user[:120], updated_at=at)
        c.execute(STATE.update().where(STATE.c.tenant_id == tenant, STATE.c.key == key).values(**vals))
        row = {**dict(st), **vals}
        c.execute(LOG.insert().values(**_log_row(tenant, row, "durum", at, by=user)))
    return row


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


# ------------------------------------------------------------------------------------------------ önbellek
class Worklist:
    """Son liste bellekte ve veritabanında; istek hiçbir zaman toplamayı beklemez (``wait=True`` yalnız gece işi,
    dışa aktarma ve testler için). Aynı anda tek toplama."""

    def __init__(self, seo, clock: Callable[[], float] = time.monotonic) -> None:
        self.seo = seo
        self.clock = clock
        self._lock = threading.Lock()                      # aynı anda tek toplama
        self._mem: dict[str, tuple[float, dict[str, Any]]] = {}
        self.state: dict[str, Any] = {"building": False, "startedAt": None, "finishedAt": None, "error": None}

    # -------------------------------------------------------------- saklama
    def _load(self, tenant: str) -> Optional[tuple[float, dict[str, Any]]]:
        hit = self._mem.get(tenant)
        if hit:
            return hit
        eng = self.seo.engine()
        ensure_tables(eng)
        with eng.connect() as c:
            row = c.execute(sa.select(CACHE.c.data_json, CACHE.c.built_at).where(CACHE.c.tenant_id == tenant)).first()
        if not row:
            return None
        built = row[1] if row[1].tzinfo else row[1].replace(tzinfo=timezone.utc)
        age = max(0.0, (now() - built).total_seconds())
        hit = (self.clock() - age, loads(row[0], {}))
        self._mem[tenant] = hit
        return hit

    def rebuild(self) -> dict[str, Any]:
        """Toplar, durum tablosunu günceller, sonucu saklar. Çağıran bekler."""
        tenant = self.seo.tenant()
        with self._lock:
            self.state.update(building=True, startedAt=iso(now()), error=None)
            try:
                env = Env(self.seo)
                items, ran, errors = collect(env)
                changes = sync_states(env.eng, tenant, items, ran)
                data = {"items": list(items.values()), "errors": errors, "builtAt": iso(now()), "changes": changes}
                with env.eng.begin() as c:
                    c.execute(CACHE.delete().where(CACHE.c.tenant_id == tenant))
                    c.execute(CACHE.insert().values(tenant_id=tenant, data_json=dumps(data), built_at=now()))
                self._mem[tenant] = (self.clock(), data)
                return data
            except Exception as e:  # noqa: BLE001
                self.state["error"] = str(e)[:300]
                raise
            finally:
                self.state.update(building=False, finishedAt=iso(now()))

    def start_rebuild(self) -> bool:
        if self.state["building"] or self._lock.locked():
            return False

        def run() -> None:
            try:
                self.rebuild()
            except Exception:  # noqa: BLE001
                log.exception("seo worklist rebuild failed")

        self.state.update(building=True, startedAt=iso(now()), error=None)
        threading.Thread(target=run, name="seo-worklist-build", daemon=True).start()
        return True

    def build(self, force: bool = False, wait: bool = False) -> Optional[dict[str, Any]]:
        """Eldeki liste (yoksa None). Eskiyse ya da ``force`` ise yenisi arka planda (``wait`` ise burada) toplanır."""
        hit = self._load(self.seo.tenant())
        stale = hit is None or force or self.clock() - hit[0] >= STALE_SECONDS
        if stale:
            if wait:
                return self.rebuild()
            self.start_rebuild()
        return hit[1] if hit else None

    def view(self, force: bool = False, wait: bool = False) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
        data = self.build(force, wait)
        if data is None:
            return [], None
        eng = self.seo.engine()
        states = load_states(eng, self.seo.tenant())
        return merge(data["items"], states), data


# ------------------------------------------------------------------------------------------------ uçlar
class WorklistStatus(BaseModel):
    status: str = Field(pattern="^(yeni|yapiliyor|bitti|yoksay)$")
    assignee: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=1000)


def _check_filters(owner: str, status: str, source: str) -> None:
    if owner and owner not in OWNERS:
        raise _err(422, "Bilinmeyen sorumlu.")
    if source and source not in SOURCES:
        raise _err(422, "Bilinmeyen kaynak.")
    if status and status != "acik" and any(s not in STATUSES for s in status.split(",") if s):
        raise _err(422, "Bilinmeyen durum.")


def register(app, ctx) -> None:
    seo = ctx.seo
    wl = Worklist(seo)

    @app.get("/api/v1/seo-geo/worklist")
    def seo_worklist(request: Request, owner: str = "", status: str = "", source: str = "", q: str = "", start: int = 0,
                     limit: int = 50, refresh: int = 0) -> dict[str, Any]:
        ctx.gate(request)
        _check_filters(owner, status, source)
        items, data = wl.view(force=bool(refresh))
        chosen = select(items, owner, status, source, q)
        s, n = max(0, start), max(1, limit)
        errors = (data or {}).get("errors") or {}
        return {"total": len(chosen), "start": s, "items": chosen[s:s + n],
                "counts": counts(items, owner, status, source, q), "summary": summary(items),
                "owners": OWNERS, "statuses": STATUSES, "sources": SOURCES, "errors": errors,
                "errorLabels": {k: SOURCES.get(k, k) for k in errors},
                "ready": data is not None, "building": wl.state["building"], "buildError": wl.state["error"],
                "builtAt": (data or {}).get("builtAt"), "cacheSeconds": STALE_SECONDS}

    @app.post("/api/v1/seo-geo/worklist/{key}/status")
    def seo_worklist_status(key: str, body: WorklistStatus, request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        row = set_status(seo.engine(), seo.tenant(), key, body.status, body.assignee, body.note, user)
        seo.audit(user, "status", key, row["title"], {"kind": "worklist", "status": body.status,
                                                     "assignee": row.get("assignee"), "source": row["source"]})
        return {"key": key, "status": row["status"], "statusLabel": STATUSES[row["status"]], "assignee": row.get("assignee"),
                "note": row.get("note"), "updatedBy": row.get("updated_by"), "updatedAt": iso(row.get("updated_at"))}

    @app.get("/api/v1/seo-geo/worklist/log")
    def seo_worklist_log(request: Request, start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        eng = seo.engine()
        ensure_tables(eng)
        with eng.connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(LOG).where(LOG.c.tenant_id == seo.tenant())).scalar() or 0
            rows = c.execute(sa.select(LOG).where(LOG.c.tenant_id == seo.tenant()).order_by(LOG.c.at.desc(), LOG.c.id)
                             .offset(max(0, start)).limit(max(1, limit))).mappings().all()
        return {"total": total, "start": max(0, start), "items": [
            {"key": r["key"], "source": r["source"], "sourceLabel": SOURCES.get(r["source"], r["source"]),
             "owner": r["owner"], "ownerLabel": OWNERS.get(r["owner"], r["owner"]), "title": r["title"],
             "event": r["event"], "eventLabel": EVENT_LABEL.get(r["event"], r["event"]), "status": r["status"],
             "statusLabel": STATUSES.get(r["status"] or "", r["status"]), "assignee": r["assignee"], "note": r["note"],
             "by": r["by_user"], "at": iso(r["at"]), "closedAt": iso(r["closed_at"])} for r in rows]}

    @app.get("/api/v1/seo-geo/worklist/export.csv")
    def seo_worklist_export(request: Request, owner: str = "", status: str = "", source: str = "", q: str = ""):
        from fastapi.responses import Response

        ctx.gate(request)
        _check_filters(owner, status, source)
        items, _ = wl.view(wait=True)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Etki", "Sorumlu", "Kaynak", "İş", "Ayrıntı", "Önem", "Kayıt sayısı", "Durum", "Atanan", "Not",
                    "Puan hesabı", "Ekran", "İlk görülme"])
        for i in select(items, owner, status, source, q):
            w.writerow([_p(i["impact"]), i["ownerLabel"], i["sourceLabel"], i["title"], i["detail"], i["severity"],
                        i["count"] or "", i["statusLabel"], i["assignee"] or "", i["note"] or "", i["impactBasis"],
                        i["link"], i["firstSeen"] or ""])
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="seo-is-listesi.csv"'})

    def nightly() -> None:
        # Öteki gece işleri arka planda yazarken beklenir; sonra liste yeniden kurulur ve kapananlar kaydedilir.
        def later() -> None:
            time.sleep(NIGHTLY_DELAY_S)
            try:
                wl.rebuild()
            except Exception:  # noqa: BLE001
                log.exception("seo worklist nightly failed")

        threading.Thread(target=later, name="seo-worklist", daemon=True).start()

    seo.nightly.append(("worklist", nightly))
