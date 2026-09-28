"""Google Merchant Center'daki ürün durumu: onaylı / onaylanmayan / sınırlı / bekleyen ve ürün sorunları.

Kaynak: Merchant API v1 `GET products/v1/accounts/{hesap}/products` (sayfa başına en çok 1000, `pageToken` ile sonuna
kadar; sessiz tavan yok). Ürün kaynağındaki alanlar (Google belgesi, 2026-09-28 doğrulandı):
  - `offerId`, `name` (accounts/{a}/products/{dil}~{besleme etiketi}~{offerId}), `productAttributes.title`,
    `productAttributes.gtins` (dizi)
  - `productStatus.destinationStatuses[]`: `reportingContext`, `approvedCountries`, `pendingCountries`,
    `disapprovedCountries`
  - `productStatus.itemLevelIssues[]`: `code`, `severity` (NOT_IMPACTED | DEMOTED | DISAPPROVED), `resolution`,
    `attribute`, `reportingContext`, `description`, `detail`, `documentation`, `applicableCountries`
Google açıklamaları İngilizce verir; ekranda olduğu gibi gösterilir, önem ve çözüm sahibi Türkçe yazılır.

Ürün durumu (bütün gösterim yerleri birlikte):
  onaylanmayan  hiçbir yerde onaylı değil ve en az bir yerde reddedilmiş
  bekleyen      hiçbir yerde onaylı değil, inceleniyor (ya da henüz durum yok)
  sınırlı       bir yerde onaylı ama başka bir yerde reddedilmiş ya da gösterimi düşüren (DEMOTED/DISAPPROVED) sorun var
  onaylı        onaylı ve gösterimi etkileyen sorun yok

Merchant ürünü T-soft ürününe `offerId` ile eşlenir: T-soft ürün kimliği → ürün kodu → barkod (offerId rakamsa) →
Google'daki GTIN. Eşlenemeyen sayısı özetle birlikte tutulur. Satış/gösterim etkisi iş listesinde eşlenen ürünlerden.

Sürekli çekilir: `REFRESH_HOURS`'ta bir süreç içi döngüde, gece işinde ve ekran açıldığında son okuma eskiyse.
`MERCHANT_ACCOUNT_ID` boşsa hiçbir şey yapılmaz. Merchant Center'a yalnız GET gider; yazma çağrısı yoktur.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from datetime import timedelta, timezone
from typing import Any, Iterable, Optional
from urllib.parse import quote

import sqlalchemy as sa
from fastapi import HTTPException, Request

from .store import PRODUCTS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

API = "https://merchantapi.googleapis.com/products/v1/accounts/{account}/products"
#: Google'ın izin verdiği en büyük sayfa (belge: «maximum of 1000»). Sayfa sayısında tavan yok.
PAGE_SIZE = 1000
#: Arka plan okuma aralığı; ekran açıldığında da bu kadar eskiyse yeniden okunur.
REFRESH_HOURS = 6

APPROVED, DISAPPROVED, LIMITED, PENDING = "onayli", "onaylanmayan", "sinirli", "bekleyen"
STATUSES = (DISAPPROVED, LIMITED, PENDING, APPROVED)
STATUS_LABEL = {APPROVED: "Onaylı", DISAPPROVED: "Onaylanmayan", LIMITED: "Sınırlı", PENDING: "Bekleyen"}
#: Liste süzgeci: «sorunlu» = onaylanmayan + sınırlı.
PROBLEM = "sorunlu"

SEV_RANK = {"DISAPPROVED": 3, "DEMOTED": 2, "NOT_IMPACTED": 1}
SEV_LABEL = {"DISAPPROVED": "Onaylanmadı", "DEMOTED": "Gösterimi sınırlı", "NOT_IMPACTED": "Bilgi"}
RESOLUTION_LABEL = {"merchant_action": "Düzeltme bizde (ürün verisi ya da site)",
                    "pending_processing": "Google işliyor; kendiliğinden düzelebilir"}
ATTRIBUTE_LABEL = {"gtins": "barkod (GTIN)", "gtin": "barkod (GTIN)", "image_link": "görsel", "price": "fiyat",
                   "sale_price": "indirimli fiyat", "availability": "stok durumu", "title": "başlık",
                   "description": "açıklama", "link": "ürün adresi", "brand": "marka", "condition": "durum",
                   "google_product_category": "Google kategorisi", "shipping": "kargo", "identifier_exists": "barkod var mı"}
CONTEXT_LABEL = {"SHOPPING_ADS": "Alışveriş reklamları", "FREE_LISTINGS": "Ücretsiz listeler",
                 "DISPLAY_ADS": "Görüntülü reklamlar", "DEMAND_GEN_ADS": "Talep yaratma reklamları",
                 "LOCAL_INVENTORY_ADS": "Yerel envanter reklamları", "FREE_LOCAL_LISTINGS": "Ücretsiz yerel listeler",
                 "YOUTUBE_SHOPPING": "YouTube alışveriş"}

ITEMS = sa.Table(
    "semantic_seo_merchant_items", _md,  # son okumada Merchant'taki her ürün (dil/besleme etiketi başına bir kayıt)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("name", sa.String(400), primary_key=True),       # accounts/{a}/products/{dil}~{etiket}~{offerId}
    sa.Column("offer_id", sa.String(200), nullable=False, index=True),
    sa.Column("title", sa.String(500)),
    sa.Column("gtin", sa.String(40)),
    sa.Column("status", sa.String(16), nullable=False, index=True),
    sa.Column("worst", sa.String(16)),                         # en ağır sorun önemi (DISAPPROVED | DEMOTED | NOT_IMPACTED)
    sa.Column("issue_codes", sa.Text, nullable=False, default=""),  # ",invalid_gtin,image_too_small," — süzgeç için
    sa.Column("issues_json", sa.Text, nullable=False),
    sa.Column("dest_json", sa.Text, nullable=False),
    sa.Column("product_id", sa.String(40), index=True),        # eşlenen T-soft ürünü
    sa.Column("match", sa.String(12)),                         # kimlik | kod | barkod | gtin | None
    sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
)
SNAP = sa.Table(
    "semantic_seo_merchant", _md,  # son okumanın özeti ve (varsa) hatası
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("error", sa.String(500)),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)
HIST = sa.Table(
    "semantic_seo_merchant_hist", _md,  # her başarılı okumada sayılar (eğilim için)
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("total", sa.Integer, nullable=False),
    sa.Column("approved", sa.Integer, nullable=False),
    sa.Column("disapproved", sa.Integer, nullable=False),
    sa.Column("limited", sa.Integer, nullable=False),
    sa.Column("pending", sa.Integer, nullable=False),
    sa.Column("unmatched", sa.Integer, nullable=False),
    sa.Column("read_at", sa.DateTime(timezone=True), nullable=False, index=True),
)
_ready: set[int] = set()


def ensure(eng: sa.engine.Engine) -> None:
    if id(eng) in _ready:
        return
    for t in (ITEMS, SNAP, HIST):
        t.create(eng, checkfirst=True)
    _ready.add(id(eng))


# ------------------------------------------------------------------------------------------------ saf işlevler
_SECRET = re.compile(r"ya29\.[A-Za-z0-9_\-.]+|Bearer\s+\S+|-----BEGIN[^-]*-----.*?-----END[^-]*-----", re.S)


def safe(msg: Any) -> str:
    """Kullanıcıya/kayda giden hata metni: erişim belirteci ve anahtar içeriği silinir."""
    return _SECRET.sub("•••", str(msg))[:500]


def account_id(raw: Optional[str]) -> str:
    return (raw or "").strip().removeprefix("accounts/").strip("/")


def merchant_link(account: str) -> str:
    """Hesap düzeyinde Merchant Center bağlantısı (ürün düzeyindeki adres biçimi belgelenmediği için yok)."""
    return f"https://merchants.google.com/mc/overview?a={quote(account, safe='')}"


def _digits(v: Any) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def parse_issues(raw: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aynı sorun birden çok gösterim yeri için ayrı satır gelir: kod başına tek satır, en ağır önem, yerler ve
    ülkeler birleşik."""
    by: dict[str, dict[str, Any]] = {}
    for i in raw or []:
        code = str(i.get("code") or "").strip()
        if not code:
            continue
        sev = str(i.get("severity") or "").upper()
        cur = by.get(code)
        if cur is None:
            cur = by[code] = {"code": code, "severity": sev, "resolution": i.get("resolution"),
                              "attribute": i.get("attribute"), "description": i.get("description"),
                              "detail": i.get("detail"), "documentation": i.get("documentation"),
                              "contexts": [], "countries": []}
        elif SEV_RANK.get(sev, 0) > SEV_RANK.get(cur["severity"], 0):
            cur["severity"] = sev
        for k in ("resolution", "attribute", "description", "detail", "documentation"):
            if not cur.get(k) and i.get(k):
                cur[k] = i.get(k)
        ctx = i.get("reportingContext")
        if ctx and ctx not in cur["contexts"]:
            cur["contexts"].append(ctx)
        for c in i.get("applicableCountries") or []:
            if c not in cur["countries"]:
                cur["countries"].append(c)
    return sorted(by.values(), key=lambda x: (-SEV_RANK.get(x["severity"], 0), x["code"]))


def classify(dests: Iterable[dict[str, Any]], issues: Iterable[dict[str, Any]]) -> str:
    dests = list(dests or [])
    approved = any(d.get("approvedCountries") for d in dests)
    disapproved = any(d.get("disapprovedCountries") for d in dests)
    # Merchant Center ekranının sayımı (2026-09-28 canlıda karşılaştırıldı: 6 onaylanmayan, 0 sınırlı): bir yerde
    # onaylı ürün onaylıdır; «sınırlı» = AYNI gösterim yerinde bazı ülkelerde onaylı, bazılarında reddedilmiş. Başka bir
    # gösterim türündeki ret (ör. keşfet reklamları) ya da yalnız gösterimi azaltan sorun ürünü sınırlı yapmaz — önceki
    # tanım 599–619 ürünü yanlış sınırlı sayıyordu. Bu sorunlar iş listesine sorun kodu başına ayrıca düşer.
    if not approved:
        return DISAPPROVED if disapproved else PENDING
    split = any(d.get("approvedCountries") and d.get("disapprovedCountries") for d in dests)
    return LIMITED if split else APPROVED


def parse_product(p: dict[str, Any]) -> dict[str, Any]:
    attrs = p.get("productAttributes") or {}
    st = p.get("productStatus") or {}
    gtins = attrs.get("gtins") or ([attrs["gtin"]] if attrs.get("gtin") else [])
    dests = [{"context": d.get("reportingContext"), "approved": list(d.get("approvedCountries") or []),
              "pending": list(d.get("pendingCountries") or []),
              "disapproved": list(d.get("disapprovedCountries") or [])}
             for d in st.get("destinationStatuses") or []]
    issues = parse_issues(st.get("itemLevelIssues") or [])
    status = classify(st.get("destinationStatuses") or [], issues)
    worst = max((i["severity"] for i in issues), key=lambda s: SEV_RANK.get(s, 0), default=None)
    return {"name": str(p.get("name") or p.get("offerId") or ""), "offerId": str(p.get("offerId") or ""),
            "title": attrs.get("title") or "", "gtins": [str(g) for g in gtins], "link": attrs.get("link"),
            "status": status, "worst": worst, "issues": issues, "destinations": dests}


def match_index(rows: Iterable[tuple[Any, Any, Any]]) -> dict[str, dict[str, str]]:
    """T-soft (ürün kimliği, ürün kodu, barkod) → eşleme sözlükleri."""
    idx: dict[str, dict[str, str]] = {"id": {}, "code": {}, "ean": {}}
    for pid, code, barcode in rows:
        pid = str(pid)
        idx["id"][pid] = pid
        if code:
            idx["code"].setdefault(str(code).strip().casefold(), pid)
        ean = _digits(barcode)
        if len(ean) >= 8:
            idx["ean"].setdefault(ean, pid)
    return idx


def match(offer_id: str, gtins: Iterable[str], idx: dict[str, dict[str, str]]) -> tuple[Optional[str], Optional[str]]:
    oid = (offer_id or "").strip()
    if oid in idx["id"]:
        return idx["id"][oid], "kimlik"
    if oid.casefold() in idx["code"]:
        return idx["code"][oid.casefold()], "kod"
    d = _digits(oid)
    if len(d) >= 8 and d == oid and d in idx["ean"]:
        return idx["ean"][d], "barkod"
    for g in gtins or []:
        gd = _digits(g)
        if gd in idx["ean"]:
            return idx["ean"][gd], "gtin"
    return None, None


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {s: 0 for s in STATUSES}
    issues: dict[str, dict[str, Any]] = {}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
        for i in it["issues"]:
            g = issues.get(i["code"])
            if g is None:
                g = issues[i["code"]] = {k: i.get(k) for k in ("code", "severity", "resolution", "attribute",
                                                               "description", "detail", "documentation")}
                g["products"] = 0
            elif SEV_RANK.get(i["severity"], 0) > SEV_RANK.get(g["severity"], 0):
                g["severity"] = i["severity"]
            g["products"] += 1
    rows = sorted(issues.values(), key=lambda g: (-SEV_RANK.get(g["severity"], 0), -g["products"], g["code"]))
    for g in rows:
        g["severityLabel"] = SEV_LABEL.get(g["severity"], g["severity"] or "—")
        g["resolutionLabel"] = RESOLUTION_LABEL.get(g["resolution"] or "", g["resolution"])
        g["attributeLabel"] = ATTRIBUTE_LABEL.get(g["attribute"] or "", g["attribute"])
    return {"total": len(items), "approved": counts[APPROVED], "disapproved": counts[DISAPPROVED],
            "limited": counts[LIMITED], "pending": counts[PENDING],
            "matched": sum(1 for it in items if it.get("productId")),
            "unmatched": sum(1 for it in items if not it.get("productId")), "issues": rows}


def fetch(account: str, get: Optional[Any] = None) -> list[dict[str, Any]]:
    """Bütün ürünler, `nextPageToken` bitene kadar. `get(url) → dict` testte değiştirilir."""
    if get is None:
        from . import connections

        def get(url: str) -> dict[str, Any]:
            return connections._google("GET", url)

    base = API.format(account=quote(account, safe=""))
    out: list[dict[str, Any]] = []
    token: Optional[str] = None
    seen: set[str] = set()
    while True:
        url = f"{base}?pageSize={PAGE_SIZE}" + (f"&pageToken={quote(token, safe='')}" if token else "")
        body = get(url) or {}
        out.extend(body.get("products") or [])
        token = body.get("nextPageToken") or None
        if not token:
            return out
        if token in seen:  # Google aynı sayfayı yeniden verirse sonsuz döngü olmasın
            raise RuntimeError("Merchant Center aynı sayfayı yeniden döndürdü; okuma yarıda kesildi.")
        seen.add(token)


def tsoft_rows(eng: sa.engine.Engine, tenant: str) -> list[tuple[Any, Any, Any]]:
    """(ürün kimliği, ürün kodu, barkod) — bütün T-soft ürünleri (etkin olmayan da: Merchant'ta kalmış olabilir)."""
    with eng.connect() as c:
        if eng.dialect.name == "postgresql":
            data = sa.cast(PRODUCTS.c.data_json, sa.JSON)
            return [tuple(r) for r in c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.code,
                                                          data["Barcode"].as_string())
                                                .where(PRODUCTS.c.tenant_id == tenant)).all()]
        return [(pid, code, loads(raw, {}).get("Barcode"))
                for pid, code, raw in c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.code, PRODUCTS.c.data_json)
                                                .where(PRODUCTS.c.tenant_id == tenant))]


def save(eng: sa.engine.Engine, tenant: str, account: str, raw: list[dict[str, Any]], at) -> dict[str, Any]:
    """Okunan ürünleri ayrıştırır, T-soft'a eşler ve son durumu yazar (eski son durum silinir, geçmişe sayı eklenir)."""
    ensure(eng)
    idx = match_index(tsoft_rows(eng, tenant)) if sa.inspect(eng).has_table(PRODUCTS.name) else match_index([])
    items = []
    for p in raw:
        it = parse_product(p)
        it["productId"], it["match"] = match(it["offerId"], it["gtins"], idx)
        items.append(it)
    summ = summarize(items)
    data = {"account": account, "link": merchant_link(account), "summary": summ}
    rows = [dict(tenant_id=tenant, name=it["name"][:400], offer_id=it["offerId"][:200], title=(it["title"] or "")[:500],
                 gtin=(it["gtins"][0] if it["gtins"] else None), status=it["status"], worst=it["worst"],
                 issue_codes="," + ",".join(i["code"] for i in it["issues"]) + "," if it["issues"] else "",
                 issues_json=dumps(it["issues"]), dest_json=dumps(it["destinations"]), product_id=it["productId"],
                 match=it["match"], read_at=at) for it in items]
    uniq = {r["name"]: r for r in rows}  # aynı ad iki kez gelirse sonuncusu
    with eng.begin() as c:
        c.execute(ITEMS.delete().where(ITEMS.c.tenant_id == tenant))
        vals = list(uniq.values())
        for i in range(0, len(vals), 1000):
            c.execute(ITEMS.insert(), vals[i:i + 1000])
        c.execute(SNAP.delete().where(SNAP.c.tenant_id == tenant))
        c.execute(SNAP.insert().values(tenant_id=tenant, data_json=dumps(data), error=None, saved_at=at))
        c.execute(HIST.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, total=summ["total"],
                                       approved=summ["approved"], disapproved=summ["disapproved"],
                                       limited=summ["limited"], pending=summ["pending"], unmatched=summ["unmatched"],
                                       read_at=at))
    return data


def save_error(eng: sa.engine.Engine, tenant: str, message: str, at) -> None:
    """Okuma hatası son okumanın yanına yazılır; eski veri silinmez."""
    ensure(eng)
    with eng.begin() as c:
        n = c.execute(SNAP.update().where(SNAP.c.tenant_id == tenant).values(error=safe(message))).rowcount
        if not n:
            c.execute(SNAP.insert().values(tenant_id=tenant, data_json=dumps({}), error=safe(message), saved_at=at))


def connected(eng: sa.engine.Engine, tenant: str) -> bool:
    """En az bir başarılı okuma var mı (Alışveriş ekranındaki «hesap bağlı» bayrağı)."""
    if not sa.inspect(eng).has_table(HIST.name):
        return False
    with eng.connect() as c:
        return c.execute(sa.select(sa.func.count()).select_from(HIST).where(HIST.c.tenant_id == tenant)).scalar() > 0


def item_view(r: Any) -> dict[str, Any]:
    issues = loads(r["issues_json"], [])
    for i in issues:
        i["severityLabel"] = SEV_LABEL.get(i.get("severity"), i.get("severity"))
        i["attributeLabel"] = ATTRIBUTE_LABEL.get(i.get("attribute") or "", i.get("attribute"))
        i["resolutionLabel"] = RESOLUTION_LABEL.get(i.get("resolution") or "", i.get("resolution"))
        i["contextLabels"] = [CONTEXT_LABEL.get(c, c) for c in i.get("contexts") or []]
    return {"name": r["name"], "offerId": r["offer_id"], "title": r["title"], "gtin": r["gtin"], "status": r["status"],
            "statusLabel": STATUS_LABEL.get(r["status"], r["status"]), "issues": issues,
            "destinations": loads(r["dest_json"], []), "productId": r["product_id"], "match": r["match"]}


# ------------------------------------------------------------------------------------------------ uçlar
def register(app, ctx) -> None:
    seo = ctx.seo
    lock = threading.Lock()
    state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "error": None}

    def eng() -> sa.engine.Engine:
        e = seo.engine()
        ensure(e)
        return e

    def account() -> str:
        return account_id(seo.conf("MERCHANT_ACCOUNT_ID"))

    def read_snap() -> Optional[dict[str, Any]]:
        with eng().connect() as c:
            r = c.execute(sa.select(SNAP.c.data_json, SNAP.c.error, SNAP.c.saved_at)
                          .where(SNAP.c.tenant_id == seo.tenant())).first()
        if not r:
            return None
        return {**loads(r[0], {}), "error": r[1], "savedAt": iso(r[2]), "_at": r[2]}

    def refresh() -> dict[str, Any]:
        acc = account()
        if not acc:
            raise RuntimeError("Merchant Center kimliği girilmemiş.")
        e, tenant, at = eng(), seo.tenant(), now()
        try:
            raw = fetch(acc)
        except Exception as ex:  # noqa: BLE001 — hata son okumanın yanına yazılır
            save_error(e, tenant, str(ex), at)
            raise
        return save(e, tenant, acc, raw, at)

    def kick() -> bool:
        with lock:
            if state["running"]:
                return False
            state.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)

        def run() -> None:
            try:
                refresh()
            except Exception as ex:  # noqa: BLE001
                state["error"] = safe(ex)
                log.warning("merchant: %s", safe(ex))
            finally:
                state.update(running=False, finishedAt=iso(now()))

        threading.Thread(target=run, name="seo-merchant", daemon=True).start()
        return True

    def stale(snap: Optional[dict[str, Any]]) -> bool:
        at = snap.get("_at") if snap else None
        if at is None:
            return True
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return now() - at > timedelta(hours=REFRESH_HOURS)

    def loop() -> None:
        """Süreç açık kaldıkça REFRESH_HOURS'ta bir; son okuma tazeyse (başka süreç okuduysa) atlanır."""
        time.sleep(180)
        while True:
            try:
                if account() and stale(read_snap()):
                    kick()
            except Exception as ex:  # noqa: BLE001
                log.warning("merchant döngüsü: %s", safe(ex))
            time.sleep(1800)

    threading.Thread(target=loop, name="seo-merchant-loop", daemon=True).start()

    @app.get("/api/v1/seo-geo/merchant")
    def seo_merchant(request: Request, status: str = "", issue: str = "", q: str = "", start: int = 0,
                     limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if status and status not in STATUSES and status != PROBLEM:
            raise HTTPException(422, {"code": "SEO", "message": "Durum onaylanmayan, sinirli, bekleyen, onayli ya da sorunlu olmalı."})
        acc = account()
        snap = read_snap() if acc else None
        if acc and stale(snap):
            kick()
        if snap:
            snap.pop("_at", None)
        cond = [ITEMS.c.tenant_id == seo.tenant()]
        if status == PROBLEM:
            cond.append(ITEMS.c.status.in_((DISAPPROVED, LIMITED)))
        elif status:
            cond.append(ITEMS.c.status == status)
        if issue:
            cond.append(ITEMS.c.issue_codes.contains(f",{issue},", autoescape=True))
        if q.strip():
            like = f"%{q.strip().lower()}%"
            cond.append(sa.or_(sa.func.lower(ITEMS.c.title).like(like), sa.func.lower(ITEMS.c.offer_id).like(like),
                               ITEMS.c.gtin.like(like)))
        order = sa.case({DISAPPROVED: 0, LIMITED: 1, PENDING: 2}, value=ITEMS.c.status, else_=3)
        begin = max(0, start)
        with eng().connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(ITEMS).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(ITEMS).where(*cond).order_by(order, ITEMS.c.title, ITEMS.c.name)
                             .offset(begin).limit(max(1, min(limit, 500)))).mappings().all()
        return {"configured": bool(acc), "snapshot": snap, "state": state, "refreshHours": REFRESH_HOURS,
                "total": total, "start": begin, "items": [item_view(r) for r in rows],
                "statusLabels": STATUS_LABEL}

    @app.post("/api/v1/seo-geo/merchant/refresh")
    def seo_merchant_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        if not account():
            raise HTTPException(409, {"code": "SEO", "message": "Merchant Center kimliği girilmemiş (Yönetim → SEO & GEO)."})
        started = kick()
        seo.audit(user, "run", "merchant", "Google Merchant ürün durumu okuması", {"started": started})
        return {"started": started, "state": state}

    def nightly() -> None:
        if account():
            kick()

    seo.nightly.append(("merchant", nightly))
